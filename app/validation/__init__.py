from pathlib import Path
import csv
from app.storage import save_json

def validate(task):
    problems=[]
    ids=[e['id'] for e in task['structure']['environments']];labels=[e['label'] for e in task['structure']['environments']]
    if len(set(ids))!=len(ids) or len(set(labels))!=len(labels):problems.append('环境 ID 或字母重复')
    atomids={a['id'] for a in task['structure']['atoms']}
    for e in task['structure']['environments']:
        if set(e['atom_ids'])-atomids:problems.append(e['id']+' 存在未知原子 ID')
        if e['hydrogen_count']<=0:problems.append(e['id']+' 氢数不合法')
        if e['status']=='人工确认' and e['experimental_ppm'] is None:problems.append(e['id']+' 确认状态缺实验 ppm')
    for it in task['spectrum']['integrals']:
        if it['value']!=it['immutable_value']:problems.append('原始积分被修改 '+it['id'])
    if problems:raise ValueError('\n'.join(problems))
    return True

def report(task,out):
    validate(task);out=Path(out);envs=task['structure']['environments']
    from app.structure_parser import assess_equivalence
    task['equivalence']=assess_equivalence(task['structure'])
    save_json(out/'equivalence_report.json',task['equivalence'])
    equivalence_lines=['# 氢环境判断与标注规则','',task['equivalence']['method'],
        '',task['equivalence']['display_policy'],'',
        '|标签|理论 H 数|对应原子数|判断|','|---|---:|---:|---|']
    equivalence_lines += [f'|{e["label"]}|{e["hydrogen_count"]}|{len(e["atom_ids"])}|{e["equivalence_status"]}|' for e in envs]
    (out/'氢环境判断报告.md').write_text('\n'.join(equivalence_lines),encoding='utf-8')
    fields=['id','label','atom_ids','proton','hydrogen_count','environment','predicted_ppm','experimental_ppm','delta_ppm','integral','normalized_integral','confidence','status','reason']
    with (out/'assignments.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');writer.writeheader();writer.writerows(envs)
    summary={'environments':len(envs),'manually_confirmed':sum(e['status']=='人工确认' for e in envs),
        'suggested':sum(e.get('experimental_ppm') is not None for e in envs),
        'needs_review':sum(e['status']!='人工确认' for e in envs),
        'integral_mismatch':[e['label'] for e in envs if (e.get('integral_mismatch') or 0)>.3],
        'prediction':task.get('prediction',{}),'assignment':task.get('assignment',{}),'impurities':task['impurities']}
    save_json(out/'review_report.json',summary)
    lines=['# 核磁归属审核报告','',f'结构：{task["structure"]["formula"]}；{len(task["structure"]["atoms"])} 个原子。',
        f'氢环境 {len(envs)} 组；有实验候选 {summary["suggested"]} 组；人工确认 {summary["manually_confirmed"]} 组；待审核 {summary["needs_review"]} 组。',
        '',f'真实预测来源：{task.get("prediction",{}).get("origin","未提供")}',
        '评分是启发式可信度；自动建议不能计作已确认或已证明正确。原始积分未修改，归一化仅用于比较。',
        'CH₂ Ha/Hb 与相邻重叠峰需结合二维核磁或人工判断。未积分区域不具备定量氢数约束。',
        '', '|标签|预测 ppm|实验 ppm|H|原积分|状态|原因|','|---|---:|---:|---:|---:|---|---|']
    for e in envs:lines.append('|'+ '|'.join(str(e.get(k,'')) for k in ['label','predicted_ppm','experimental_ppm','hydrogen_count','integral','status','reason'])+'|')
    lines+=['','## 溶剂与杂质候选']+[f'- {i["name"]}：{i["ppm"]:.3f} ppm，{i["status"]}，{i["reason"]}' for i in task['impurities']]
    (out/'审核报告.md').write_text('\n'.join(lines),encoding='utf-8');return summary
