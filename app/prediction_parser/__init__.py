import csv,copy
import numpy as np
from rdkit import Chem
from app.structure_parser import letters

def attach_prediction(structure,mol,predicted_molecule,origin):
    pmol=Chem.MolFromMolBlock(predicted_molecule['molfile'],removeHs=False)
    if pmol is None or Chem.MolToSmiles(pmol)!=Chem.MolToSmiles(mol):raise ValueError('预测分子与 CDXML 结构不一致')
    match=mol.GetSubstructMatch(pmol,useChirality=True)
    if len(match)!=pmol.GetNumAtoms():raise ValueError('未能建立完整预测原子映射')
    # Symmetry-related isomorphisms produce the same equivalence environment.
    by_index={a['index']:a for a in structure['atoms']}
    records=predicted_molecule.get('prediction') or [];grouped={}
    mapping={}
    for n,row in enumerate(records):
        atomrefs=row['atom'] if isinstance(row['atom'],list) else [row['atom']]
        shift=row['shift'];value=float(shift['value'] if isinstance(shift,dict) else shift)
        error=float(shift.get('error',.35)) if isinstance(shift,dict) else .35
        for ref in atomrefs:
            idx=int(ref['index'])-1
            if not 0<=idx<len(match):raise ValueError('预测原子编号超界')
            atom=by_index[match[idx]];h=ref.get('h');mapping[str(ref['index'])]=atom['id']
            # Keep genuine predictor's Ha/Hb separation; average only symmetry-equivalent atoms.
            key=(atom['rank'],h)
            grouped.setdefault(key,[]).append({'atom_id':atom['id'],'index':ref['index'],'h':h,
                'ppm':value,'error':error,'js':row.get('js',[]),'record':n})
    if not records:return {'origin':origin,'mapping':mapping,'coverage':0,'warning':'预测谱存在，但原子预测记录为空'}
    old={e['rank']:e for e in structure['environments']};envs=[];covered=set()
    for (rank,h),rows in sorted(grouped.items(),key=lambda kv:(min(r['index'] for r in kv[1]),str(kv[0][1]))):
        if rank not in old:continue
        e=copy.deepcopy(old[rank]);e['id']=f'E{len(envs)+1}';e['label']=letters(len(envs));e['proton']=h
        ids=list(dict.fromkeys(r['atom_id'] for r in rows));e['atom_ids']=ids
        e['coordinates']=[a['xy'] for a in structure['atoms'] if a['id'] in ids]
        e['hydrogen_count']=len(ids) if h else sum(a['h_count'] for a in structure['atoms'] if a['id'] in ids)
        e['predicted_ppm']=float(np.mean([r['ppm'] for r in rows]));e['prediction_error']=max(r['error'] for r in rows)
        e['prediction_records']=rows;e['prediction_origin']=origin
        e['reason']='真实预测原子映射；结构图同构检查通过'+('；Ha/Hb 映射需立体化学审核' if h else '')
        envs.append(e);covered.update(ids)
    for e in structure['environments']:
        missing=[x for x in e['atom_ids'] if x not in covered]
        if missing:
            q=copy.deepcopy(e);q['id']=f'E{len(envs)+1}';q['label']=letters(len(envs));q['atom_ids']=missing
            q['coordinates']=[a['xy'] for a in structure['atoms'] if a['id'] in missing]
            q['hydrogen_count']=sum(a['h_count'] for a in structure['atoms'] if a['id'] in missing)
            q['reason']='预测未覆盖此环境';envs.append(q)
    structure['environments']=envs
    return {'origin':origin,'mapping':mapping,'coverage':len(covered),'records':len(records),
            'structure_consistent':True,'mapping_method':'chirality-aware graph isomorphism; equivalent atoms share rank'}

def attach_csv(structure,path):
    with open(path,encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
    if not rows or 'ppm' not in rows[0]:raise ValueError('预测 CSV 必须有 ppm 列；atom_ids 使用 CDXML ID，多个 ID 用分号分隔')
    byid={a['id'] for a in structure['atoms']};count=0
    for row in rows:
        ids=set(row.get('atom_ids','').split(';'))-{''}
        if ids-byid:raise ValueError('预测 CSV 包含未知 CDXML 原子 ID')
        for e in structure['environments']:
            if ids and ids==set(e['atom_ids']):
                e['predicted_ppm']=float(row['ppm']);e['prediction_error']=float(row.get('error') or .35)
                e['multiplicity']=row.get('multiplicity','');e['prediction_origin']=str(path);count+=1
    return {'origin':str(path),'mapped_environments':count,'unmapped_peak_rows':len(rows)-count,
            'warning':'无完整 atom_ids 映射的峰仅作为预测峰候选，不声明原子归属' if count<len(rows) else ''}
