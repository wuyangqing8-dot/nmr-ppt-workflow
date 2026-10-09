from pathlib import Path
from app.storage import read_json

def references(solvent):
    db=read_json(Path(__file__).with_name('reference.json'))
    return db.get(solvent,{})

def detect(signals,solvent,environments,known=()):
    refs=references(solvent);result=[]
    for name,positions in refs.items():
        chosen=[]
        for ppm in positions:
            nearby=[s for s in signals if abs(s['ppm']-ppm)<=.055]
            if nearby:
                s=max(nearby,key=lambda s:s.get('height',1)/(1+abs(s['ppm']-ppm)/.03))
                if s['id'] not in {q['id'] for q in chosen}:chosen.append(s)
        for s in chosen:
            competition=[e['label'] for e in environments if e.get('predicted_ppm') is not None and abs(e['predicted_ppm']-s['ppm'])<.25]
            result.append({'signal_id':s['id'],'name':name,'ppm':s['ppm'],
                'status':'人工确认' if name in known and not competition else '候选杂质',
                'reason':'参考位置附近'+('；存在产物预测竞争：'+','.join(competition) if competition else '；需结合实验条件确认'),
                'confidence':.85 if name in known and not competition else .4,'positions':{}})
    return result
