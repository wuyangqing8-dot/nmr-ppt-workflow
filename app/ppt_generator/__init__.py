from pathlib import Path
import copy,json
import numpy as np
from pptx import Presentation
from pptx.util import Inches,Pt
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR
from app.annotation import layout_structure,layout_spectrum
from app.storage import save_json

def template_layout(path):
    p=Presentation(path);s=p.slides[0]
    pictures=[sh for sh in s.shapes if sh.shape_type==13]
    oles=[sh for sh in s.shapes if sh.shape_type==7]
    def box(sh):return [v/914400 for v in [sh.left,sh.top,sh.width,sh.height]]
    structure=box(oles[0]) if oles else [1,.55,11.33,2.6]
    # Preserve template's horizontal spectrum extent; keep peaks below structure for new work.
    spectrum=box(max(pictures,key=lambda sh:sh.width*sh.height)) if pictures else [.8,3.35,11.7,3.2]
    lower=max(3.3,structure[1]+structure[3]+.2)
    spectrum=[spectrum[0],lower,spectrum[2],min(3.65,7.5-lower-.4)]
    styles=[]
    for sh in s.shapes:
        if sh.has_text_frame:
            for para in sh.text_frame.paragraphs:
                for r in para.runs:
                    color=None
                    try:color=str(r.font.color.rgb)
                    except (AttributeError,TypeError):pass
                    styles.append({'font':r.font.name,'size':r.font.size.pt if r.font.size else None,'color':color})
    return {'slide_size':[p.slide_width/914400,p.slide_height/914400], 'structure_box':structure,
        'spectrum_box':spectrum,'ppm_range':[8.3,-.2],'font':'Arial','size':16,'color':'0070C0','source_styles':styles,
        'show_leaders':False,'show_formula':False,'hide_uncertainty_marks':True}

def plot_spectrum(task,out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    sp=task['spectrum'];box=task['layout']['spectrum_box'];hi,lo=task['layout']['ppm_range']
    x=np.array(sp['ppm']);y=np.array(sp['intensity']);mask=(x<=hi)&(x>=lo)
    peak=max(float(np.max(y[mask])),1e-12)
    peak=peak/task['layout'].get('display_gain',1.)
    fig=plt.figure(figsize=(box[2],box[3]),facecolor='white');ax=fig.add_axes([0,.30,1,.69])
    ax.plot(x[mask],y[mask],color='#9C1017',linewidth=.85)
    ax.set_xlim(hi,lo);ax.set_ylim(-peak*.025,peak*1.1);ax.axis('off')
    # A separate ppm axis leaves room for unchanged integral numbers.
    axis=fig.add_axes([0,.18,1,.10]);axis.set_xlim(hi,lo);axis.set_ylim(0,1)
    axis.spines[['top','left','right']].set_visible(False);axis.set_yticks([])
    ticks=np.arange(np.ceil(lo*2)/2,hi+.001,.5);axis.set_xticks(ticks)
    axis.tick_params(axis='x',labelsize=11,length=3,pad=2);axis.set_xlabel('chemical shift(ppm)',fontname='Arial',fontsize=12,labelpad=0)
    last_c=hi+1
    for it in sorted(sp['integrals'],key=lambda it:-(it['min']+it['max'])/2):
        if it['max']<lo or it['min']>hi:continue
        c=(it['min']+it['max'])/2
        label_c=min(c,last_c-.14);last_c=label_c
        axis.plot([it['min'],it['max']],[1.02,1.02],color='#537723',lw=.6,clip_on=False)
        if label_c!=c:axis.plot([c,label_c],[1.02,.94],color='#537723',lw=.6,clip_on=False)
        axis.text(label_c,.9,f'{it["value"]:.2f}',rotation=90,ha='center',va='top',color='#15106C',fontsize=9,fontname='Arial')
    for ext in ['png','pdf','svg']:fig.savefig(Path(out)/('spectrum.'+ext),dpi=300)
    plt.close(fig)
    return str((Path(out)/'spectrum.png').resolve())

def add_text(slide,text,box,style,color=None):
    x,y,w,h=box;sh=slide.shapes.add_textbox(Inches(x),Inches(y),Inches(w),Inches(h))
    tf=sh.text_frame;tf.margin_left=tf.margin_right=tf.margin_top=tf.margin_bottom=0
    tf.word_wrap=False;p=tf.paragraphs[0];p.text=text
    for r in p.runs:r.font.name=style['font'];r.font.size=Pt(style['size']);r.font.color.rgb=RGBColor.from_string(color or style['color'])
    return sh

def add_leader(slide,placement):
    if not placement.get('leader'):return
    ax,ay=placement['anchor'];x,y,w,h=placement['box']
    line=slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT,Inches(ax),Inches(ay),Inches(x+w/2),Inches(y+h/2))
    line.line.color.rgb=RGBColor.from_string('BBBBBB');line.line.width=Pt(.45)

def render_powerpoint(path,out):
    import win32com.client,pythoncom
    pythoncom.CoInitialize()
    try:
        app=win32com.client.Dispatch('PowerPoint.Application')
        try:p=app.Presentations.Open(str(Path(path).resolve()),True,False,False)
        except pythoncom.com_error:
            app.Visible=True
            p=app.Presentations.Open(str(Path(path).resolve()),True,False,False)
        try:
            out=Path(out).resolve();out.mkdir(parents=True,exist_ok=True)
            p.Slides.Item(1).Export(str(out/'preview.png'),'PNG',1920,1080)
            p.SaveAs(str(out/'preview.pdf'),32)
        finally:p.Close()
    finally:pythoncom.CoUninitialize()

def generate(task,out,allow_draft=True):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    unresolved=[e for e in task['structure']['environments'] if e['status']!='人工确认']
    review_required=bool(unresolved or not task['structure']['environments'])
    if review_required and not allow_draft:raise ValueError('尚有未确认归属或缺少人工环境；请审核后导出最终 PPT，或导出带状态的审核稿。')
    layout=task['layout'];p=Presentation()
    p.slide_width=Inches(13.333333);p.slide_height=Inches(7.5);slide=p.slides.add_slide(p.slide_layouts[6])
    pic=slide.shapes.add_picture(task['assets']['emf'],*[Inches(v) for v in layout['structure_box']]);pic.name='Structure_original_vector'
    formula=task['structure'].get('formula','')
    if formula and layout.get('show_formula',True):
        sh=add_text(slide,formula,layout.get('formula_box',[3.15,3.00,7.1,.25]),{'font':'Arial','size':12,'color':'000000'})
        sh.name='MolecularFormula'
        import re
        paragraph=sh.text_frame.paragraphs[0];paragraph.clear()
        for token in re.findall(r'[A-Z][a-z]?|\d+|[^A-Za-z\d]+',formula):
            run=paragraph.add_run();run.text=token;run.font.name='Arial';run.font.size=Pt(12)
            run.font.color.rgb=RGBColor.from_string('000000')
            if token.isdigit():run._r.get_or_add_rPr().set('baseline','-25000')
    # python-pptx's WMF reader recognises EMF bytes but assigns a WMF MIME type.
    # Keep the true EMF format, otherwise PowerPoint rejects the package.
    from pptx.opc.packuri import PackURI
    imagepart=slide.part.related_part(pic._element.blipFill.blip.rEmbed)
    imagepart._partname=PackURI('/ppt/media/structure.emf');imagepart._content_type='image/x-emf'
    spectrum=plot_spectrum(task,out)
    slide.shapes.add_picture(spectrum,*[Inches(v) for v in layout['spectrum_box']])
    structure_labels=layout_structure(task['structure'],layout['structure_box'],layout['size'])
    spectral_labels=layout_spectrum(task)
    # Each equivalent hydrogen environment receives exactly one structure label.
    for e in task['structure']['environments']:
        places=[q for q in structure_labels if q['env_id']==e['id']]
        for q in places:
            if layout.get('show_leaders',True):add_leader(slide,q)
            sh=add_text(slide,q['text'],q['box'],layout);sh.name=f'StructureLabel_{q["env_id"]}_{q["atom_id"]}'
    for q in spectral_labels:
        if layout.get('show_leaders',True):add_leader(slide,q)
        sh=add_text(slide,q['text'],q['box'],layout);sh.name='PeakLabel_'+q['signal_id']
    # Provisional chemical interpretations are separate from confirmed atom/peak
    # assignments and retain their uncertainty explicitly in the visible text.
    for q in task.get('peak_annotations',[]):
        if q.get('status')!='confirmed' and '?' not in q['text'] and not layout.get('hide_uncertainty_marks',False):
            raise ValueError('未确认的峰注释必须带问号')
        sh=add_text(slide,q['text'],q['box'],{**layout,'size':q.get('size',layout['size'])})
        sh.name='ProvisionalPeak_'+q['id']
    if task.get('peak_annotations'):
        slide.notes_slide.notes_text_frame.text=task.get('peak_interpretation_notes','')
    from app.annotation import ppm_to_x
    for i in task['impurities']:
        if i['status']!='人工确认' and not (i['name'] in [task['solvent'],'DCM','H2O'] and i['status']=='候选杂质'):continue
        x,y,w,h=layout['spectrum_box'];px=ppm_to_x(i['ppm'],*layout['ppm_range'],x,w)
        pos=i.get('positions',{}).get('spectrum') or [px-.3,y+.08]
        text=i['name']+('?' if i['status']!='人工确认' and not layout.get('hide_uncertainty_marks',False) else '')
        sh=add_text(slide,text,[*pos,.8,.25],layout);sh.name='Impurity_'+i['signal_id']
        # Use editable native font baselines for the stoichiometric numbers.
        import re
        paragraph=sh.text_frame.paragraphs[0];paragraph.clear()
        for token in re.findall(r'\d+|\D+',text):
            run=paragraph.add_run();run.text=token
            run.font.name=layout['font'];run.font.size=Pt(layout['size'])
            run.font.color.rgb=RGBColor.from_string(layout['color'])
            if token.isdigit():run._r.get_or_add_rPr().set('baseline','-25000')
    if review_required:
        note=task.get('review_note') or '峰字母为推定归属，尚未确认。'
        add_text(slide,note,[.35,7.2,12.6,.18],{'font':'Microsoft YaHei','size':9,'color':'777777'})
    target=out/('assignment_draft.pptx' if review_required else 'assignment.pptx');p.save(target)
    render_powerpoint(target,out)
    task['last_export']={'pptx':str(target.resolve()),'draft':review_required,'structure_labels':structure_labels,'spectrum_labels':spectral_labels,'peak_annotations':task.get('peak_annotations',[]),'show_leaders':layout.get('show_leaders',True)}
    save_json(out/'export_manifest.json',task['last_export'])
    return str(target.resolve())

def reproduce_reference(template,out):
    """Stage 1 only: read human labels dynamically, keep original OLE/vector/integrals."""
    out=Path(out);out.mkdir(parents=True,exist_ok=True);p=Presentation(template)
    labels=[]
    for slide in p.slides:
        for sh in list(slide.shapes):
            if sh.has_text_frame and sh.text:
                labels.append({'text':sh.text,'box':[v/914400 for v in [sh.left,sh.top,sh.width,sh.height]],'source':'参考 PPT 人工标注'})
                replacement=copy.deepcopy(sh._element);sh._element.getparent().replace(sh._element,replacement)
    target=out/'reference_reproduced.pptx';p.save(target);render_powerpoint(target,out)
    save_json(out/'reference_labels.json',labels)
    return str(target.resolve())
