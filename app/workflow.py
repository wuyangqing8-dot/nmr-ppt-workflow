from pathlib import Path
from app.storage import save_json,read_json,fingerprint
from app.nmr_import import export_mnova,classify,spectrum_from_export,read_xy,read_integrals,inspect_jdf
from app.structure_parser import export_original,parse_cdxml,manual_structure
from app.prediction_parser import attach_prediction,attach_csv
from app.assignment import make_signals,auto_assign
from app.solvent_detection import detect
from app.ppt_generator import template_layout,generate
from app.validation import report

def create_task(inputs,out,solvent='CDCl3',experiment_page=None,prediction_page=None,known=(),temperature=None,frequency=None):
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=True)
    inputs={k:str(Path(v).resolve()) for k,v in inputs.items() if v}
    if not inputs.get('structure') or not inputs.get('template'):raise ValueError('需要 ChemDraw 结构与 PPT 模板')
    assets=export_original(inputs['structure'],out/'assets')
    try:structure,mol=parse_cdxml(assets['cdxml'])
    except ValueError as e:structure=manual_structure(assets['cdxml'],e);mol=None
    d=None
    if inputs.get('experiment','').lower().endswith('.mnova'):
        d=export_mnova(inputs['experiment'],out/'experiment_export')
        available=[(p['index'],s) for p in d['pages'] for s in p['spectra'] if classify(s)=='experiment']
        if not available:raise ValueError('Mnova 文件中没有可核实来源的实验谱；请导入 ASCII 或指定实验数据来源')
        candidates=[v for v in available if experiment_page is None or v[0]==experiment_page]
        if not candidates:raise ValueError('指定实验页不存在；页号从 0 开始')
        page,spec=max(candidates,key=lambda ps:len(ps[1]['integrals']))
        spectrum=spectrum_from_export(spec,page)
    elif inputs.get('experiment','').lower().endswith('.json'):
        d=read_json(inputs['experiment']);available=[(p['index'],s) for p in d['pages'] for s in p['spectra'] if classify(s)=='experiment']
        page,spec=max([v for v in available if experiment_page is None or v[0]==experiment_page],key=lambda ps:len(ps[1]['integrals']))
        spectrum=spectrum_from_export(spec,page)
    elif inputs.get('experiment'):spectrum=read_xy(inputs['experiment'])
    else:raise ValueError('需要已处理实验 Mnova 或 ASCII/CSV/TXT 谱线')
    if inputs.get('integrals'):spectrum['integrals']=read_integrals(inputs['integrals'])
    prediction={};pd=d
    if inputs.get('prediction','').lower().endswith('.mnova'):pd=export_mnova(inputs['prediction'],out/'prediction_export')
    elif inputs.get('prediction','').lower().endswith('.json'):pd=read_json(inputs['prediction'])
    if inputs.get('prediction','').lower().endswith(('.csv','.txt')):prediction=attach_csv(structure,inputs['prediction'])
    elif pd:
        pages=[p for p in pd['pages'] if p.get('molecules') and any(classify(s)=='prediction' for s in p['spectra'])]
        if prediction_page is not None:pages=[p for p in pages if p['index']==prediction_page]
        if pages:
            page=pages[0];spec=next(s for s in page['spectra'] if classify(s)=='prediction')
            prediction=attach_prediction(structure,mol,page['molecules'][0],spec['params'].get('Origin','unknown')) if mol is not None else {'origin':spec['params'].get('Origin','unknown'),'warning':'原子图未经验证，自动原子映射已暂停'}
            prediction['page']=page['index'];prediction['all_available_pages']=[p['index'] for p in pd['pages'] if p.get('molecules')]
    if inputs.get('grouping_profile'):
        from app.assignment.manual import apply_grouping_profile
        apply_grouping_profile(structure,inputs['grouping_profile'])
    signals=make_signals(spectrum);impurities=detect(signals,solvent,structure['environments'],known)
    assignment=auto_assign(structure['environments'],signals,impurities)
    layout=template_layout(inputs['template'])
    geom=spectrum.get('display_geometry') or {}
    if geom.get('unit') and geom.get('zero'):
        slope=(geom['unit']['y']-geom['zero']['y'])/geom.get('unitIntensity',1)
        if slope<0:
            display_max=(geom['top']-geom['zero']['y'])/slope
            if display_max>0:layout['display_gain']=max(spectrum['intensity'])/display_max
            layout['display_gain_source']='Mnova scaleToPage transform'
    bounds=spectrum.get('display_bounds') or {}
    if bounds.get('max') is not None and bounds['max']-bounds['min']<15:layout['ppm_range']=[bounds['max'],bounds['min']]
    task={'version':1,'inputs':inputs,'sources':{k:fingerprint(v) for k,v in inputs.items()},'assets':assets,
        'structure':structure,'spectrum':spectrum,'signals':signals,'prediction':prediction,'assignment':assignment,
        'impurities':impurities,'solvent':solvent,'temperature':temperature,'frequency':frequency,
        'layout':layout,'output':str(out),'history':[]}
    if inputs.get('raw'):task['raw_inspection']=inspect_jdf(inputs['raw'])
    save_task(task);report(task,out);return task

def save_task(task):
    from app.validation import validate
    validate(task);save_json(Path(task['output'])/'task.json',task)

def export_task(task,allow_draft=True):
    from app.validation import validate
    validate(task);result=generate(task,task['output'],allow_draft);report(task,task['output']);save_task(task);return result
