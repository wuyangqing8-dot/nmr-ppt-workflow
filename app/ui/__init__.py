"""Chinese review GUI. Task data and export use the same coordinate system."""
import sys,copy,time
from pathlib import Path
import numpy as np
from PySide6.QtCore import Qt,QThread,Signal
from PySide6.QtGui import QPixmap,QPainterPath,QPen,QColor,QFont,QPainter
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,
    QLineEdit,QPushButton,QFileDialog,QMessageBox,QComboBox,QSplitter,QTableWidget,QTableWidgetItem,
    QGraphicsView,QGraphicsScene,QGraphicsTextItem,QGraphicsItem,QDialog,QDialogButtonBox,QLabel,QInputDialog)
from app.storage import read_json
from app.annotation import layout_structure,layout_spectrum,atom_to_slide,ppm_to_x
from app.workflow import create_task,save_task,export_task
from app.validation import report

class Worker(QThread):
    result=Signal(object);failed=Signal(str)
    def __init__(self,fn):super().__init__();self.fn=fn
    def run(self):
        import pythoncom
        pythoncom.CoInitialize()
        try:self.result.emit(self.fn())
        except Exception as e:self.failed.emit(str(e))
        finally:pythoncom.CoUninitialize()

class LabelItem(QGraphicsTextItem):
    def __init__(self,text,position,key,callback,clicked):
        super().__init__(text);self.key=key;self.callback=callback;self.clicked=clicked
        self.setFont(QFont('Arial',14));self.setDefaultTextColor(QColor('#0070C0'));self.document().setDocumentMargin(0)
        self.setPos(position[0]*96,position[1]*96)
        self.setFlags(QGraphicsItem.ItemIsMovable|QGraphicsItem.ItemIsSelectable)
    def mousePressEvent(self,event):
        self.clicked(self.key[0]);super().mousePressEvent(event)
    def mouseReleaseEvent(self,event):
        super().mouseReleaseEvent(event);self.callback(self.key,[self.pos().x()/96,self.pos().y()/96])

class Canvas(QGraphicsView):
    clicked=Signal(float,float)
    def __init__(self):
        super().__init__();self.setScene(QGraphicsScene());self.setRenderHint(QPainter.Antialiasing)
        self.setBackgroundBrush(Qt.white);self.setMinimumWidth(600)
    def resizeEvent(self,e):super().resizeEvent(e);self.fitInView(self.sceneRect(),Qt.KeepAspectRatio)
    def mousePressEvent(self,e):
        p=self.mapToScene(e.position().toPoint());self.clicked.emit(p.x()/96,p.y()/96);super().mousePressEvent(e)

class ImportDialog(QDialog):
    def __init__(self,parent):
        super().__init__(parent);self.setWindowTitle('新建核磁任务');self.resize(850,480)
        layout=QVBoxLayout(self);form=QFormLayout();layout.addLayout(form);self.fields={}
        names={'experiment':'实验 Mnova / XY / JSON','raw':'原始 JDF（可选）','prediction':'预测 Mnova / CSV（可选，同文件会自动发现）',
            'grouping_profile':'人工等效氢分组 JSON（可选）',
            'integrals':'积分 CSV（可选）','structure':'ChemDraw CDXML / CDX','template':'PPT 版式模板','output':'输出文件夹'}
        for key,title in names.items():
            row=QWidget();line=QHBoxLayout(row);line.setContentsMargins(0,0,0,0)
            edit=QLineEdit();button=QPushButton('选择');line.addWidget(edit);line.addWidget(button);self.fields[key]=edit
            button.clicked.connect(lambda checked=False,k=key:self.browse(k));form.addRow(title,row)
        self.solvent=QComboBox();self.solvent.addItems(['CDCl3','DMSO-d6','CD3OD','acetone-d6']);form.addRow('实验溶剂',self.solvent)
        self.ep=QLineEdit();self.ep.setPlaceholderText('留空选择积分最完整的实验页；页号从 0 开始');form.addRow('实验页',self.ep)
        self.pp=QLineEdit();self.pp.setPlaceholderText('留空使用首个预测页；页号从 0 开始');form.addRow('预测页',self.pp)
        self.temp=QLineEdit();self.freq=QLineEdit();form.addRow('温度 °C（可选）',self.temp);form.addRow('频率 MHz（可选）',self.freq)
        self.known=QLineEdit();self.known.setPlaceholderText('已知杂质名称，用逗号分隔，如 DCM');form.addRow('已知杂质',self.known)
        buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel);layout.addWidget(buttons)
        buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject)
        layout.addWidget(QLabel('需有处理后谱线和 ChemDraw/PPT。缺少预测时保留待确认环境；PDF 可作为视觉参考，不能替代定量谱线。'))
    def browse(self,key):
        value=QFileDialog.getExistingDirectory(self,'输出目录') if key=='output' else QFileDialog.getOpenFileName(self,'选择文件')[0]
        if value:self.fields[key].setText(value)

class MainWindow(QMainWindow):
    headers=['ID','标签','原子 ID（分号分隔）','H数','预测 ppm','实验 ppm','原积分','可信度','状态','归属依据']
    def __init__(self,task_path=None):
        super().__init__();self.task=None;self.worker=None;self.loading=False
        self.setWindowTitle('NMR 自动归属与科研 PPT');self.resize(1600,950)
        main=QWidget();self.setCentralWidget(main);root=QVBoxLayout(main)
        actions=[('新建任务',self.new),('打开任务',self.open),('保存任务',self.save),('重新匹配',self.reassign),
            ('新增环境',self.add_environment),('合并环境',self.merge),('拆分 CH₂ / 环境',self.split),('确认选中',self.confirm),('溶剂/杂质',self.edit_impurities),
            ('自动排版',self.relayout),('导出审核稿',self.export_draft),('导出已确认 PPT',self.export_final)]
        for index,(name,fn) in enumerate(actions):
            if index%6==0:bar=QHBoxLayout();root.addLayout(bar)
            b=QPushButton(name);bar.addWidget(b);b.clicked.connect(fn)
        split=QSplitter();root.addWidget(split)
        self.canvas=Canvas();split.addWidget(self.canvas)
        self.table=QTableWidget(0,len(self.headers));self.table.setHorizontalHeaderLabels(self.headers)
        self.table.horizontalHeader().moveSection(2,9)
        self.table.setSelectionBehavior(QTableWidget.SelectRows);self.table.setMinimumWidth(570);split.addWidget(self.table)
        self.table.itemChanged.connect(self.changed);self.table.itemSelectionChanged.connect(self.highlight)
        self.canvas.clicked.connect(self.canvas_click);self.statusBar().showMessage('选择新建任务或打开 task.json。')
        if task_path:self.load(read_json(task_path))
    def closeEvent(self,event):
        if self.worker and self.worker.isRunning():
            self.statusBar().showMessage('请等待当前导入或导出完成后关闭窗口。');event.ignore();return
        super().closeEvent(event)
    def run_job(self,fn,done):
        if self.worker and self.worker.isRunning():return
        self.statusBar().showMessage('正在处理，请等待…');self.centralWidget().setEnabled(False)
        self.worker=Worker(fn)
        def finish(result):self.centralWidget().setEnabled(True);done(result)
        def fail(message):self.centralWidget().setEnabled(True);self.statusBar().showMessage('处理失败');QMessageBox.critical(self,'处理失败',message)
        self.worker.result.connect(finish);self.worker.failed.connect(fail);self.worker.start()
    def new(self):
        d=ImportDialog(self)
        if d.exec()!=QDialog.Accepted:return
        try:
            vals={k:v.text().strip() for k,v in d.fields.items()}
            if not vals['output']:raise ValueError('请选择输出文件夹')
            ep=int(d.ep.text()) if d.ep.text() else None;pp=int(d.pp.text()) if d.pp.text() else None
            temp=float(d.temp.text()) if d.temp.text() else None;freq=float(d.freq.text()) if d.freq.text() else None
            self.run_job(lambda:create_task(vals,vals['output'],d.solvent.currentText(),ep,pp,
                [s.strip() for s in d.known.text().split(',') if s.strip()],temp,freq),self.load)
        except Exception as e:QMessageBox.warning(self,'输入检查',str(e))
    def open(self):
        p=QFileDialog.getOpenFileName(self,'打开任务','','JSON (*.json)')[0]
        if p:
            try:self.load(read_json(p))
            except Exception as e:QMessageBox.warning(self,'打开失败',str(e))
    def load(self,task):self.task=task;self.refresh();self.statusBar().showMessage(f'任务已载入：{len(task["structure"]["environments"])} 组氢环境。自动建议需人工审核。')
    def refresh(self):
        self.loading=True;envs=self.task['structure']['environments'];self.table.setRowCount(len(envs))
        for row,e in enumerate(envs):
            vals=[e['id'],e['label'],';'.join(e['atom_ids']),e['hydrogen_count'],e.get('predicted_ppm'),e.get('experimental_ppm'),e.get('integral'),round(e['confidence'],3),e['status'],e['reason']]
            for col,v in enumerate(vals):
                if col in [4,5,6] and v is not None:v=f'{v:.4f}'
                item=QTableWidgetItem('' if v is None else str(v))
                item.setToolTip(str(v))
                if col in [0,4,6,7,9]:item.setFlags(item.flags()&~Qt.ItemIsEditable)
                self.table.setItem(row,col,item)
        for col,width in enumerate([35,35,100,35,65,65,65,55,80,220]):self.table.setColumnWidth(col,width)
        self.loading=False;self.draw()
    def draw(self):
        self.highlights=[];self.label_items=[]
        scene=self.canvas.scene();scene.clear();task=self.task;layout=task['layout'];scene.setSceneRect(0,0,1280,720)
        pix=QPixmap(task['assets']['png']);box=layout['structure_box']
        item=scene.addPixmap(pix.scaled(round(box[2]*96),round(box[3]*96),Qt.IgnoreAspectRatio,Qt.SmoothTransformation));item.setPos(box[0]*96,box[1]*96)
        formula=scene.addText(task['structure'].get('formula',''),QFont('Arial',12));formula.setPos(3.15*96,3.0*96)
        self.atom_locations={a['id']:atom_to_slide(a['xy'],task['structure']['bbox'],box) for a in task['structure']['atoms']}
        x,y,w,h=layout['spectrum_box'];hi,lo=layout['ppm_range']
        xx=np.array(task['spectrum']['ppm']);yy=np.array(task['spectrum']['intensity']);mask=(xx>=lo)&(xx<=hi)
        xx=xx[mask];yy=yy[mask];peak=max(float(np.max(yy)),1e-12)/layout.get('display_gain',1.);path=QPainterPath()
        for n,(px,py) in enumerate(zip(xx,yy)):
            xp=ppm_to_x(px,hi,lo,x,w)*96;yp=(y+h*.685-min(1,max(0,py)/peak/1.1)*h*.675)*96
            path.moveTo(xp,yp) if n==0 else path.lineTo(xp,yp)
        scene.addPath(path,QPen(QColor('#9C1017'),1))
        scene.addLine(x*96,(y+h*.97)*96,(x+w)*96,(y+h*.97)*96,QPen(Qt.black,1))
        for ppm in np.arange(np.ceil(lo*2)/2,hi,.5):
            tx=scene.addText(f'{ppm:.1f}',QFont('Arial',10));tx.setPos(ppm_to_x(ppm,hi,lo,x,w)*96-10,(y+h*.98)*96)
        last_ppm=hi+1
        for it in sorted(task['spectrum']['integrals'],key=lambda it:-(it['min']+it['max'])/2):
            centre=(it['min']+it['max'])/2;centre=min(centre,last_ppm-.14);last_ppm=centre
            tx=scene.addText(f'{it["value"]:.2f}',QFont('Arial',9));tx.setDefaultTextColor(QColor('#15106C'))
            tx.setPos(ppm_to_x(centre,hi,lo,x,w)*96,(y+h*.79)*96);tx.setRotation(90)
        self.label_items=[]
        placements=layout_structure(task['structure'],box)
        for e in task['structure']['environments']:
            places=[p for p in placements if p['env_id']==e['id']]
            for q in places:
                label=LabelItem(q['text'],q['box'][:2],(q['env_id'],q['atom_id']),self.moved,self.select_env);scene.addItem(label);self.label_items.append(label)
        for q in layout_spectrum(task):
            label=LabelItem(q['text'],q['box'][:2],(q['env_id'],'spectrum'),self.moved,self.select_env);scene.addItem(label);self.label_items.append(label)
        for q in placements+layout_spectrum(task):
            if q.get('leader'):
                ax,ay=q['anchor'];px,py,pw,ph=q['box']
                line=scene.addLine(ax*96,ay*96,(px+pw/2)*96,(py+ph/2)*96,QPen(QColor('#BBBBBB'),.6));line.setZValue(-.1)
        for impurity in task['impurities']:
            if impurity['status']=='忽略':continue
            if impurity['status']!='人工确认' and impurity['name'] not in [task['solvent'],'DCM','H2O']:continue
            px=ppm_to_x(impurity['ppm'],hi,lo,x,w)
            tx=scene.addText(impurity['name']+('?' if impurity['status']!='人工确认' else ''),QFont('Arial',14))
            tx.setDefaultTextColor(QColor('#0070C0'));tx.setPos((px-.3)*96,(y+.08)*96)
        self.canvas.fitInView(scene.sceneRect(),Qt.KeepAspectRatio)
    def env(self,eid):return next(e for e in self.task['structure']['environments'] if e['id']==eid)
    def moved(self,key,position):
        e=self.env(key[0]);e.setdefault('positions',{})[key[1]]=position;self.log('移动标签',e['id'])
    def select_env(self,eid):
        row=next(i for i,e in enumerate(self.task['structure']['environments']) if e['id']==eid);self.table.selectRow(row)
    def selected(self):
        rows=sorted({x.row() for x in self.table.selectedIndexes()});return [self.task['structure']['environments'][i] for i in rows]
    def highlight(self):
        if not self.task or self.loading:return
        selected={e['id'] for e in self.selected()}
        for l in self.label_items:l.setDefaultTextColor(QColor('#D26700' if l.key[0] in selected else '#0070C0'))
        # Highlight all corresponding atoms and the experimentally assigned signal.
        if hasattr(self,'highlights'):
            for obj in self.highlights:
                if obj.scene():self.canvas.scene().removeItem(obj)
        self.highlights=[]
        for e in self.selected():
            for aid in e['atom_ids']:
                ax,ay=self.atom_locations[aid];self.highlights.append(self.canvas.scene().addEllipse(ax*96-5,ay*96-5,10,10,QPen(QColor('#D26700'),1)))
            if e.get('experimental_ppm') is not None:
                x,y,w,h=self.task['layout']['spectrum_box'];px=ppm_to_x(e['experimental_ppm'],*self.task['layout']['ppm_range'],x,w)*96
                self.highlights.append(self.canvas.scene().addLine(px,y*96,px,(y+h*.77)*96,QPen(QColor('#D26700'),1,Qt.DashLine)))
    def canvas_click(self,x,y):
        if not self.task:return
        if y<self.task['layout']['spectrum_box'][1]:
            aid=min(self.atom_locations,key=lambda a:(x-self.atom_locations[a][0])**2+(y-self.atom_locations[a][1])**2)
            nearest=[e for e in self.task['structure']['environments'] if aid in e['atom_ids']]
            if nearest:self.select_env(nearest[0]['id'])
        else:
            bx,by,bw,bh=self.task['layout']['spectrum_box'];hi,lo=self.task['layout']['ppm_range'];ppm=hi-(x-bx)/bw*(hi-lo)
            signal=min(self.task['signals'],key=lambda s:abs(s['ppm']-ppm));candidates=[e['label'] for e in self.task['structure']['environments'] if any(c['signal_id']==signal['id'] for c in e['candidates'])]
            self.statusBar().showMessage(f'实验峰 {signal["id"]}：{signal["ppm"]:.4f} ppm；候选环境 '+','.join(candidates))
    def changed(self,item):
        if self.loading or not self.task:return
        e=self.task['structure']['environments'][item.row()];col=item.column();old=copy.deepcopy(e)
        try:
            v=item.text().strip()
            if col==1:
                if not v.isalpha() or not v.islower() or any(q['label']==v and q['id']!=e['id'] for q in self.task['structure']['environments']):raise ValueError('标签需要唯一的小写字母')
                e['label']=v
            elif col==2:
                ids=[x.strip() for x in v.split(';') if x.strip()]
                if not ids or set(ids)-set(self.atom_locations):raise ValueError('原子 ID 不存在')
                e['atom_ids']=ids;e['coordinates']=[a['xy'] for a in self.task['structure']['atoms'] if a['id'] in ids]
            elif col==3:
                count=int(v)
                if count<=0:raise ValueError('氢数必须为正整数')
                e['hydrogen_count']=count
            elif col==5:
                value=float(v) if v else None
                if value is None:e['experimental_ppm']=None;e['signal_id']=None;e['integral']=None
                else:
                    s=min(self.task['signals'],key=lambda s:abs(s['ppm']-value))
                    if abs(s['ppm']-value)>.04:raise ValueError('输入值未对应已检出的实验峰；请先调整峰表/峰区间')
                    e['experimental_ppm']=s['ppm'];e['signal_id']=s['id'];e['integral']=s['integral']
                e['status']='待确认'
            elif col==8:
                if v not in ['自动建议','人工确认','待确认','尚未解决']:raise ValueError('状态必须为自动建议/人工确认/待确认/尚未解决')
                if v=='人工确认' and e['experimental_ppm'] is None:raise ValueError('没有实验峰不能确认')
                e['status']=v
            if col in [1,2,3]:e['status']='待确认'
            self.log('人工修改',e['id']);self.refresh()
        except Exception as err:e.clear();e.update(old);QMessageBox.warning(self,'修改失败',str(err));self.refresh()
    def log(self,action,env):self.task['history'].append({'time':time.strftime('%Y-%m-%d %H:%M:%S'),'action':action,'environment':env})
    def save(self):
        if self.task:
            try:save_task(self.task);report(self.task,self.task['output']);self.statusBar().showMessage('任务与报告已保存')
            except Exception as e:QMessageBox.warning(self,'保存失败',str(e))
    def confirm(self):
        for e in self.selected():
            if e['experimental_ppm'] is not None:e['status']='人工确认';e['reason']+='；人工审核确认';self.log('确认',e['id'])
        if self.task:self.refresh()
    def reassign(self):
        if not self.task:return
        from app.assignment import auto_assign
        confirmed=[copy.deepcopy(e) for e in self.task['structure']['environments'] if e['status']=='人工确认']
        self.task['assignment']=auto_assign(self.task['structure']['environments'],self.task['signals'],self.task['impurities'])
        for saved in confirmed:
            e=self.env(saved['id']);e.clear();e.update(saved)
        self.log('重新匹配','all');self.refresh()
    def merge(self):
        selected=self.selected()
        if len(selected)<2:return
        base=selected[0];base['atom_ids']=list(dict.fromkeys(x for e in selected for x in e['atom_ids']))
        base['coordinates']=[a['xy'] for a in self.task['structure']['atoms'] if a['id'] in base['atom_ids']]
        base['hydrogen_count']=sum(e['hydrogen_count'] for e in selected);base['status']='待确认';base['reason']+='；人工合并环境'
        base['prediction_records']=sum([e['prediction_records'] for e in selected],[]);base['proton']=None
        if all(e.get('predicted_ppm') is not None for e in selected):base['predicted_ppm']=float(np.mean([e['predicted_ppm'] for e in selected]))
        self.task['structure']['environments']=[e for e in self.task['structure']['environments'] if e not in selected[1:]]
        self.log('合并',base['id']);self.refresh()
    def add_environment(self):
        if not self.task:return
        value,ok=QInputDialog.getText(self,'人工建立氢环境','标签, 氢数, CDXML原子ID（多个用分号）')
        if not ok:return
        try:
            label,count,atoms=value.split(',',2);count=int(count);ids=[x.strip() for x in atoms.split(';')]
            if count<=0 or not label.isalpha() or not label.islower() or set(ids)-set(self.atom_locations):raise ValueError('标签、氢数或原子ID不合法')
            envs=self.task['structure']['environments']
            if any(e['label']==label for e in envs):raise ValueError('标签重复')
            eid='E'+str(max([int(e['id'][1:]) for e in envs]+[0])+1)
            envs.append(dict(id=eid,label=label,atom_ids=ids,hydrogen_count=count,environment='人工分组',
                coordinates=[a['xy'] for a in self.task['structure']['atoms'] if a['id'] in ids],rank=None,
                predicted_ppm=None,experimental_ppm=None,integral=None,confidence=0.,status='尚未解决',
                reason='人工建立原子与氢环境关系',candidates=[],prediction_records=[],positions={},proton=None))
            self.log('新增环境',eid);self.refresh()
        except Exception as err:QMessageBox.warning(self,'新增失败',str(err))
    def split(self):
        selected=self.selected()
        if len(selected)!=1:return
        e=selected[0];value,ok=QInputDialog.getText(self,'拆分环境','新标签, 新组氢数, 原子ID用分号（Ha/Hb 可使用同一原子）')
        if not ok:return
        try:
            label,count,atoms=value.split(',',2);count=int(count);ids=atoms.split(';')
            if count<=0 or count>=e['hydrogen_count'] or not label.isalpha() or not label.islower() or set(ids)-set(e['atom_ids']):raise ValueError('拆分氢数、标签或原子 ID 不合法')
            if any(q['label']==label for q in self.task['structure']['environments']):raise ValueError('标签重复')
            new=copy.deepcopy(e);new['id']='E'+str(max(int(q['id'][1:]) for q in self.task['structure']['environments'])+1)
            new.update(label=label,hydrogen_count=count,atom_ids=ids,status='待确认',positions={},prediction_records=[])
            new['coordinates']=[a['xy'] for a in self.task['structure']['atoms'] if a['id'] in ids]
            # Ha/Hb shares a heavy atom; disjoint atom groups divide the original mapping.
            if set(ids)!=set(e['atom_ids']):
                e['atom_ids']=[aid for aid in e['atom_ids'] if aid not in ids]
                e['coordinates']=[a['xy'] for a in self.task['structure']['atoms'] if a['id'] in e['atom_ids']]
            e['hydrogen_count']-=count;e['status']='待确认';self.task['structure']['environments'].append(new)
            self.log('拆分',e['id']);self.refresh()
        except Exception as err:QMessageBox.warning(self,'拆分失败',str(err))
    def relayout(self):
        if not self.task:return
        for e in self.task['structure']['environments']:e['positions']={}
        self.draw();self.log('重新排版','all')
    def edit_impurities(self):
        if not self.task:return
        d=QDialog(self);d.setWindowTitle('溶剂和杂质：候选不会自动排除产物峰');v=QVBoxLayout(d)
        table=QTableWidget(len(self.task['impurities']),4);table.setHorizontalHeaderLabels(['信号ID','名称','ppm','状态']);v.addWidget(table)
        for row,i in enumerate(self.task['impurities']):
            for col,k in enumerate(['signal_id','name','ppm','status']):table.setItem(row,col,QTableWidgetItem(str(i[k])))
        add=QPushButton('添加');v.addWidget(add);add.clicked.connect(lambda:table.insertRow(table.rowCount()))
        buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel);v.addWidget(buttons);buttons.accepted.connect(d.accept);buttons.rejected.connect(d.reject)
        if d.exec()==QDialog.Accepted:
            try:
                rows=[]
                for r in range(table.rowCount()):
                    sid,name,ppm,status=[table.item(r,c).text() for c in range(4)]
                    if sid not in {s['id'] for s in self.task['signals']}:raise ValueError('杂质必须关联真实信号 ID')
                    if status not in ['人工确认','候选杂质','忽略']:raise ValueError('状态应为人工确认/候选杂质/忽略')
                    signal=next(s for s in self.task['signals'] if s['id']==sid)
                    if abs(float(ppm)-signal['ppm'])>.04:raise ValueError('杂质 ppm 与所选真实信号不一致')
                    rows.append(dict(signal_id=sid,name=name,ppm=signal['ppm'],status=status,reason='人工编辑',confidence=1 if status=='人工确认' else .4,positions={}))
                self.task['impurities']=rows;self.log('杂质编辑','all');self.draw()
            except Exception as e:QMessageBox.warning(self,'编辑失败',str(e))
    def export_draft(self):self.export(True)
    def export_final(self):self.export(False)
    def export(self,draft):
        if not self.task:return
        self.run_job(lambda:export_task(self.task,draft),lambda result:self.statusBar().showMessage('已导出 PPTX、PNG、PDF：'+result))

def launch(task=None):
    app=QApplication.instance() or QApplication(sys.argv);w=MainWindow(task);w.show();sys.exit(app.exec())
