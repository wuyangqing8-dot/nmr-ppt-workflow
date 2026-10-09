from pathlib import Path
import csv,os,subprocess,tempfile,time,shutil
import numpy as np
from app.storage import read_json,save_json,fingerprint

class ImportProblem(ValueError):pass

def find_mnova():
    if os.environ.get('MNOVA_EXE'):return os.environ['MNOVA_EXE']
    candidates=[Path(r'D:/MestReNova 15/nova2/MestReNova.exe')]
    for root in [Path(r'C:/Program Files'),Path(r'C:/Program Files (x86)')]:
        candidates.extend(root.glob('Mestrelab*/MestReNova*/MestReNova.exe'))
    return str(next((p for p in candidates if p.exists()),''))

def export_mnova(path,out,timeout=90):
    """Use supported -sf entry point; ASCII staging avoids Mnova CLI Unicode corruption."""
    path=Path(path).resolve();out=Path(out);out.mkdir(parents=True,exist_ok=True)
    cache=out/'mnova_export.json';stamp=out/'source.json'
    fp=fingerprint(path)
    fp['exporter']=fingerprint(Path(__file__).with_name('export_mnova.qs'))['sha256']
    if cache.exists() and stamp.exists() and read_json(stamp)==fp:return read_json(cache)
    exe=find_mnova()
    if not exe:raise ImportProblem('未找到 Mnova；请设置 MNOVA_EXE 或导入导出的 JSON/CSV/TXT。')
    stage=Path(tempfile.mkdtemp(prefix='nmr_export_'))
    try:
        shutil.copy2(path,stage/'input.mnova')
        shutil.copy2(Path(__file__).with_name('export_mnova.qs'),stage/'export.qs')
        args=[exe,str(stage/'export.qs'),'-sf',f'exportWorkflow,{(stage/"input.mnova").as_posix()},{stage.as_posix()}']
        subprocess.Popen(args,creationflags=0x08000000)
        target=stage/'mnova_export.json';start=time.monotonic()
        while time.monotonic()-start<timeout:
            if target.exists():
                try:
                    d=read_json(target)
                    if d.get('errors'):raise ImportProblem('; '.join(d['errors']))
                    if not any(pg.get('spectra') for pg in d['pages']):raise ImportProblem('Mnova 未导出谱图；请检查文件或软件许可。')
                    d['source']=str(path);save_json(cache,d);save_json(stamp,fp);return d
                except (OSError,ValueError) as e:
                    if isinstance(e,ImportProblem):raise
            time.sleep(.3)
        raise ImportProblem('Mnova 导出超时。可在 Mnova 中执行生成的 export_mnova.qs，或导入 ASCII/CSV 数据。')
    finally:shutil.rmtree(stage,ignore_errors=True)

def classify(spec):
    title=str(spec.get('title',''));origin=str(spec.get('params',{}).get('Origin',''))
    if 'predict' in (title+' '+origin).lower() or origin=='Mnova Best':return 'prediction'
    if origin in ['JEOL','Bruker','Varian','Agilent']:return 'experiment'
    return 'unknown'

def spectrum_from_export(spec,page):
    t=spec.get('trace')
    if not t or not t.get('intensities'):raise ImportProblem('缺少处理后谱线数据')
    y=np.asarray(t['intensities'],float)
    if not np.isfinite(y).all():raise ImportProblem('谱线包含非有限数值')
    # Mnova rangeIntensities returns descending positions; verified against PDF/JEOL.
    x=float(t['max'])-np.arange(len(y))*float(t['step'])
    ints=[dict(it,id=f'I{i+1}',source='Mnova stored integral',immutable_value=it['value']) for i,it in enumerate(spec.get('integrals',[]))]
    bounds=spec.get('displayBounds') or {}
    return {'ppm':x.tolist(),'intensity':y.tolist(),'integrals':ints,'peaks':spec.get('peaks',[]),
            'title':spec.get('title',''),'params':spec.get('params',{}),'page':page,
            'source_kind':'Mnova processed spectrum','display_bounds':bounds,'display_geometry':spec.get('displayGeometry',{}),
            'multiplets':spec.get('multiplets',[])}

def read_xy(path):
    """Mnova ASCII XY, CSV matrix by columns, and headered ppm,intensity."""
    text=Path(path).read_text(encoding='utf-8-sig');rows=[]
    for line in text.splitlines():
        line=line.strip()
        if not line or line.startswith(('#',';','//')):continue
        parts=line.replace(',',' ').split()
        try:rows.append([float(v) for v in parts])
        except ValueError:continue
    a=np.asarray(rows,float)
    if a.ndim!=2 or a.shape[1]<2 or a.shape[0]<3:raise ImportProblem('需要两列 ppm 与 intensity；不支持无坐标单列或转置 CSV。')
    a=a[:,:2]
    if not np.isfinite(a).all() or len(np.unique(a[:,0]))!=len(a):raise ImportProblem('ppm 数据不合法或重复')
    delta=np.diff(a[:,0])
    if not ((delta>0).all() or (delta<0).all()):raise ImportProblem('ppm 必须单调；可能选择了峰表而非谱线')
    a=a[np.argsort(a[:,0])[::-1]]
    return {'ppm':a[:,0].tolist(),'intensity':a[:,1].tolist(),'integrals':[],'peaks':[],
            'params':{},'page':None,'title':Path(path).stem,'source_kind':'exported XY','display_bounds':{}}

def read_integrals(path):
    with open(path,encoding='utf-8-sig',newline='') as f:
        rows=list(csv.DictReader(f))
    return [dict(id=f'I{i+1}',min=float(r['min']),max=float(r['max']),value=float(r['value']),
                 immutable_value=float(r['value']),source=str(Path(path).resolve())) for i,r in enumerate(rows)]

def inspect_jdf(path):
    import nmrglue as ng
    d,y=ng.jeol.read(str(path))
    return {'shape':list(y.shape),'dtype':str(y.dtype),'header':d['header'],
            'usage':'原始 FID，仅检查元数据；流程优先使用 Mnova 已处理谱。'}
