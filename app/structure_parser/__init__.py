from pathlib import Path
import tempfile,shutil
from lxml import etree
import numpy as np
from rdkit import Chem
from rdkit.Chem import rdMolDescriptors
from app.storage import save_json

def parse_cdxml(path):
    root=etree.fromstring(Path(path).read_bytes(),etree.XMLParser(resolve_entities=False,no_network=True))
    nodes=root.findall('.//n');bonds=root.findall('.//b')
    bad=[n.get('id') for n in nodes if n.get('NodeType','Element')!='Element' or n.get('p') is None]
    if bad:raise ValueError('CDXML 含缩写/查询/嵌套节点，需先在 ChemDraw 展开或提供手动原子图：'+','.join(bad))
    rw=Chem.RWMol();idmap={};atoms=[]
    for n in nodes:
        a=Chem.Atom(int(n.get('Element','6')));a.SetFormalCharge(int(n.get('Charge','0')))
        if n.get('Isotope'):a.SetIsotope(int(n.get('Isotope')))
        if n.get('NumHydrogens') is not None:a.SetNumExplicitHs(int(n.get('NumHydrogens')));a.SetNoImplicit(True)
        idx=rw.AddAtom(a);idmap[n.get('id')]=idx
        atoms.append({'id':n.get('id'),'index':idx,'element':a.GetSymbol(),'xy':list(map(float,n.get('p').split()))})
    edges=[]
    for b in bonds:
        order=b.get('Order','1');types={'1':Chem.BondType.SINGLE,'2':Chem.BondType.DOUBLE,'3':Chem.BondType.TRIPLE,'1.5':Chem.BondType.AROMATIC}
        if order not in types or b.get('B') not in idmap or b.get('E') not in idmap:raise ValueError('不支持的键或缺失端点：'+str(dict(b.attrib)))
        rw.AddBond(idmap[b.get('B')],idmap[b.get('E')],types[order])
        edges.append({'a':b.get('B'),'b':b.get('E'),'order':order,'display':b.get('Display','Solid')})
    mol=rw.GetMol()
    try:Chem.SanitizeMol(mol)
    except Exception as e:raise ValueError('结构价态/芳香性解析失败，必须人工校正：'+str(e)) from e
    ref=Chem.MolsFromCDXML(Path(path).read_text(encoding='utf-8'))
    if len(ref)!=1 or Chem.MolToSmiles(ref[0])!=Chem.MolToSmiles(mol):raise ValueError('原子图与 RDKit CDXML 解析不一致；请人工确认。')
    ranks=list(Chem.CanonicalRankAtoms(mol,breakTies=False,includeChirality=True))
    groups={}
    for a,row in zip(mol.GetAtoms(),atoms):
        h=a.GetTotalNumHs(includeNeighbors=True);row['h_count']=h;row['rank']=ranks[a.GetIdx()]
        if h and a.GetAtomicNum()!=1:
            key=ranks[a.GetIdx()]
            groups.setdefault(key,[]).append(row)
    environments=[]
    for i,(rank,rows) in enumerate(sorted(groups.items(),key=lambda kv:min(x['index'] for x in kv[1]))):
        a=mol.GetAtomWithIdx(rows[0]['index']);neighbours=sorted(n.GetSymbol() for n in a.GetNeighbors())
        env='芳香 CH' if a.GetIsAromatic() else f'{a.GetSymbol()}H{rows[0]["h_count"]} 邻接 '+','.join(neighbours)
        environments.append({'id':f'E{i+1}','label':letters(i),'atom_ids':[r['id'] for r in rows],
            'hydrogen_count':sum(r['h_count'] for r in rows),'environment':env,'coordinates':[r['xy'] for r in rows],
            'rank':rank,'predicted_ppm':None,'experimental_ppm':None,'integral':None,'confidence':0.,
            'status':'尚未解决','reason':'结构图对称分组；CH₂ 立体等价性需确认','candidates':[],
            'prediction_records':[],'positions':{},'proton':None})
    bbox=list(map(float,root.get('BoundingBox').split()))
    return {'atoms':atoms,'bonds':edges,'bbox':bbox,'smiles':Chem.MolToSmiles(mol),
            'formula':rdMolDescriptors.CalcMolFormula(mol),'environments':environments},mol

def letters(i):
    value=''
    while True:
        value=chr(97+i%26)+value;i=i//26-1
        if i<0:return value

def assess_equivalence(structure):
    """Audit the graph grouping; predictor Ha/Hb alone is not proof of inequivalence."""
    atoms={a['id']:a for a in structure['atoms']};rows=[]
    for e in structure['environments']:
        ranks={atoms[aid].get('rank') for aid in e['atom_ids']}
        if e.get('manual_grouping_source'):
            status='按用户参考标注合并等效氢；保留完整预测记录'
        elif None in ranks or len(ranks)!=1:
            status='人工分组，图等价性待确认'
        elif e.get('proton'):
            status='同类重原子图等价；Ha/Hb 化学等价性待确认'
        else:
            status='按完整分子图对称性归为同一环境'
        e['equivalence_status']=status
        rows.append({'id':e['id'],'label':e['label'],'atom_ids':e['atom_ids'],
            'hydrogen_count':e['hydrogen_count'],'proton':e.get('proton'),
            'graph_ranks':sorted(r for r in ranks if r is not None),'assessment':status})
    method='按用户参考人工等效分组；原始图对称分组及 Ha/Hb 预测记录保留，可追溯'
    if not structure.get('manual_grouping_profile'):method='完整分子图、元素/键级/同位素/手性对称分组；保留真实预测 Ha/Hb 待确认'
    return {'method':method,
        'display_policy':'每个氢环境仅一个结构标签；不因 ppm 接近合并不同环境',
        'environments':rows}

def manual_structure(path,error):
    root=etree.fromstring(Path(path).read_bytes(),etree.XMLParser(resolve_entities=False,no_network=True))
    atoms=[]
    for n in root.findall('.//n'):
        if n.get('p'):
            atoms.append({'id':n.get('id'),'index':len(atoms),'element':n.get('Element','?'),
                'xy':list(map(float,n.get('p').split())),'h_count':None,'rank':None})
    return {'atoms':atoms,'bonds':[],'bbox':list(map(float,root.get('BoundingBox').split())),
        'smiles':None,'formula':'人工确认结构','environments':[],'parse_warning':str(error),
        'manual_mode':True,'warning':'仅显示原图及原子坐标；连接图与氢数未经验证，必须人工建立环境。'}

def export_original(path,out):
    """ChemDraw's verified COM MIME export retains original bond/text drawing."""
    import win32com.client
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    stage=Path(tempfile.mkdtemp(prefix='nmr_chem_'))
    try:
        src=stage/('input'+Path(path).suffix);shutil.copy2(path,src)
        a=win32com.client.gencache.EnsureDispatch('ChemDraw.Application');d=a.Documents.Open(str(src))
        try:
            for ext,mime in [('emf','image/x-emf'),('svg','image/svg+xml'),('png','image/png')]:
                target=stage/('structure.'+ext);d.SaveAs(str(target),mime)
                if not target.exists() or target.stat().st_size<100:raise ValueError('ChemDraw 导出失败：'+ext)
                shutil.copy2(target,out/target.name)
            if src.suffix.lower()=='.cdx':
                d.SaveAs(str(stage/'structure.cdxml'),'text/xml');shutil.copy2(stage/'structure.cdxml',out/'structure.cdxml')
            else:shutil.copy2(src,out/'structure.cdxml')
        finally:d.Close(False)
    finally:shutil.rmtree(stage,ignore_errors=True)
    return {ext:str((out/('structure.'+ext)).resolve()) for ext in ['emf','svg','png','cdxml']}
