"""Apply an explicit, molecule checked human environment grouping profile."""
import copy
from app.storage import read_json

def apply_grouping_profile(structure,path):
    profile=read_json(path)
    if profile['structure_smiles']!=structure['smiles']:
        raise ValueError('人工分组文件对应的分子与当前结构不同')
    old=structure['environments'];used=set();result=[]
    for group in profile['groups']:
        members=[]
        for member in group['members']:
            matches=[e for e in old if set(e['atom_ids'])==set(member['atom_ids']) and e.get('proton')==member.get('proton')]
            if len(matches)!=1:raise ValueError('人工分组文件无法唯一匹配原环境 '+group['label'])
            e=matches[0]
            if e['id'] in used:raise ValueError('人工分组重复覆盖原环境')
            members.append(e);used.add(e['id'])
        new=copy.deepcopy(members[0]);new['id']='E'+str(len(result)+1);new['label']=group['label']
        new['atom_ids']=list(dict.fromkeys(a for e in members for a in e['atom_ids']))
        new['coordinates']=[a['xy'] for a in structure['atoms'] if a['id'] in new['atom_ids']]
        new['hydrogen_count']=sum(e['hydrogen_count'] for e in members)
        new['prediction_records']=[r for e in members for r in e.get('prediction_records',[])]
        total=sum(e['hydrogen_count'] for e in members if e.get('predicted_ppm') is not None)
        new['predicted_ppm']=sum(e['predicted_ppm']*e['hydrogen_count'] for e in members if e.get('predicted_ppm') is not None)/total if total else None
        new['prediction_ppm_range']=[min(r['ppm'] for r in new['prediction_records']),max(r['ppm'] for r in new['prediction_records'])] if new['prediction_records'] else None
        new['proton']=None;new['manual_grouping_source']=profile['source']
        new['reason']='按用户参考结构标注分组；预测合并均值仅用于候选匹配，原记录保留'
        new['positions']={group['anchor_atom_id']:group['structure_position']}
        new.update(status='待确认',experimental_ppm=None,signal_id=None,integral=None,confidence=0.,candidates=[],overlap_labels=[],integral_mismatch=None)
        result.append(new)
    if used!={e['id'] for e in old}:raise ValueError('人工分组文件没有覆盖全部原环境')
    structure['environments']=result
    structure['manual_grouping_profile']=str(path)
    return profile
