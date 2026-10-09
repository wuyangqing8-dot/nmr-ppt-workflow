import numpy as np
from scipy.signal import find_peaks
from scipy.optimize import milp,Bounds,LinearConstraint

def make_signals(spectrum):
    x=np.asarray(spectrum['ppm']);y=np.asarray(spectrum['intensity'])
    inds,props=find_peaks(y,prominence=max(np.max(y)*.0015,np.std(np.diff(y))*.8),distance=3)
    valid=[int(k) for k in inds if -.15<=x[k]<=12]
    signals=[];used=set()
    for it in spectrum['integrals']:
        ks=[k for k in valid if it['min']<=x[k]<=it['max']]
        allks=np.flatnonzero((x>=it['min'])&(x<=it['max']))
        if not len(allks):continue
        apex=max(ks or allks.tolist(),key=lambda k:y[k]);used.update(ks)
        signals.append({'id':it['id'],'ppm':float(x[apex]),'min':it['min'],'max':it['max'],
            'height':float(y[apex]),'integral':it['value'],'integral_source':it['source'],
            'components':[float(x[k]) for k in ks], 'multiplicity':'','j_hz':[],'observed':True})
    remaining=sorted([k for k in valid if k not in used],key=lambda k:x[k],reverse=True)
    clusters=[]
    for k in remaining:
        if clusters and abs(x[k]-x[clusters[-1][-1]])<.018:clusters[-1].append(k)
        else:clusters.append([k])
    for ks in clusters:
        apex=max(ks,key=lambda k:y[k])
        signals.append({'id':f'P{len(signals)+1}','ppm':float(x[apex]),'min':float(min(x[ks])),
            'max':float(max(x[ks])),'height':float(y[apex]),'integral':None,
            'components':[float(x[k]) for k in ks],'multiplicity':'','j_hz':[],'observed':True})
    return sorted(signals,key=lambda s:s['ppm'],reverse=True)

def auto_assign(environments,signals,impurities=(),integral_scale=None):
    envs=[e for e in environments if e.get('predicted_ppm') is not None]
    if not envs:return {'assigned':0,'review':len(environments),'reason':'缺少真实原子预测映射'}
    ratios=[]
    for e in envs:
        if e['predicted_ppm']<2 or e['hydrogen_count']>6:continue
        ss=[s for s in signals if s['integral'] and abs(s['ppm']-e['predicted_ppm'])<.22]
        if len(ss)==1:ratios.append(e['hydrogen_count']/ss[0]['integral'])
    scale=float(integral_scale or (np.median(ratios) if ratios else 1.))
    # Integral scale is a comparison-only field. Stored values remain unchanged.
    n=len(envs);m=len(signals);cost=np.full((n,m+1),12.)
    confirmed={i['signal_id'] for i in impurities if i['status']=='人工确认'}
    for i,e in enumerate(envs):
        sigma=max(.15,min(.55,e.get('prediction_error',.35)))
        for j,s in enumerate(signals):
            delta=abs(e['predicted_ppm']-s['ppm'])
            if delta>max(.55,1.5*sigma) or s['id'] in confirmed:continue
            c=2*(delta/sigma)**2
            if s['integral'] is None:c+=.8
            if e.get('multiplicity') and s.get('multiplicity'):c+=1.5*(e['multiplicity']!=s['multiplicity'])
            if e.get('j_hz') and s.get('j_hz'):c+=abs(np.mean(e['j_hz'])-np.mean(s['j_hz']))/3
            # broad chemical class guard, only as a soft prior.
            if '芳香' in e['environment'] and s['ppm']<5:c+=4
            cost[i,j]=c
        cost[i,m]=4.5
    # Global assignment allows several environments per real signal. Integral mismatch
    # penalises the sum of H counts; no fabricated split of overlapping data.
    integral_cols=[j for j,s in enumerate(signals) if s['integral'] is not None]
    size=n*(m+1)+2*len(integral_cols)
    objective=np.zeros(size);objective[:n*(m+1)]=cost.ravel()
    objective[n*(m+1):]=.6
    constraints=[];low=[];high=[]
    for i in range(n):
        row=np.zeros(size);row[i*(m+1):(i+1)*(m+1)]=1
        constraints.append(row);low.append(1);high.append(1)
    for k,j in enumerate(integral_cols):
        row=np.zeros(size)
        for i,e in enumerate(envs):row[i*(m+1)+j]=e['hydrogen_count']
        row[n*(m+1)+2*k]=-1;row[n*(m+1)+2*k+1]=1
        constraints.append(row);low.append(signals[j]['integral']*scale);high.append(low[-1])
    upper=np.ones(size);upper[n*(m+1):]=np.inf;lower=np.zeros(size)
    fixed={e['id'] for e in envs if e['status']=='人工确认'}
    for i,e in enumerate(envs):
        if e['id'] not in fixed:continue
        target=next((j for j,s in enumerate(signals) if s['id']==e.get('signal_id')),None)
        if target is None:raise ValueError('人工确认环境没有有效实验信号 '+e['id'])
        if signals[target]['id'] in confirmed:raise ValueError('人工确认环境与已确认杂质冲突 '+e['id'])
        upper[i*(m+1):(i+1)*(m+1)]=0
        lower[i*(m+1)+target]=upper[i*(m+1)+target]=1
    integrality=np.zeros(size);integrality[:n*(m+1)]=1
    fit=milp(objective,integrality=integrality,bounds=Bounds(lower,upper),
        constraints=LinearConstraint(np.asarray(constraints),low,high),options={'time_limit':15})
    if fit.x is None:raise ValueError('全局匹配未得到可行解')
    selections={}
    for i,e in enumerate(envs):
        if e['id'] in fixed:
            j=next(j for j,s in enumerate(signals) if s['id']==e['signal_id']);selections.setdefault(j,[]).append(e);continue
        ordered=np.argsort(cost[i,:m])[:4]
        e['candidates']=[{'signal_id':signals[j]['id'],'ppm':signals[j]['ppm'],'cost':float(cost[i,j])} for j in ordered if cost[i,j]<12]
        j=int(np.argmax(fit.x[i*(m+1):(i+1)*(m+1)]))
        if j==m:
            e.update(experimental_ppm=None,signal_id=None,integral=None,delta_ppm=None,integral_mismatch=None,overlap_labels=[],status='尚未解决',confidence=0.)
            e['reason']+='；没有满足位移/积分约束的实验候选';continue
        s=signals[j];e['signal_id']=s['id'];e['experimental_ppm']=s['ppm'];e['integral']=s['integral']
        e['delta_ppm']=s['ppm']-e['predicted_ppm'];selections.setdefault(j,[]).append(e)
        margin=float(cost[i,ordered[1]]-cost[i,j]) if len(ordered)>1 else 2
        conf=float(np.exp(-cost[i,j]/3)*min(1,max(.25,margin/2)))
        e['confidence']=min(.9,conf);e['status']='自动建议'
        e['reason']+=f'；全局位移/积分约束，Δ={e["delta_ppm"]:+.3f} ppm'
        if margin<.7 or s['integral'] is None or e.get('proton'):e['status']='待确认';e['confidence']=min(.6,e['confidence'])
        if s['integral'] is None:e['reason']+='；此区间没有原始积分'
    for j,items in selections.items():
        s=signals[j];total=sum(e['hydrogen_count'] for e in items)
        mismatch=abs(total-s['integral']*scale)/max(total,1) if s['integral'] is not None else None
        for e in items:
            e['overlap_labels']=[q['label'] for q in items];e['normalized_integral']=s['integral']*scale if s['integral'] is not None else None
            e['integral_mismatch']=mismatch
            if e['id'] in fixed:continue
            if len(items)>1:e['status']='待确认';e['reason']+='；重叠信号 '+ '+'.join(q['label'] for q in items);e['confidence']=min(.5,e['confidence'])
            if mismatch is not None and mismatch>.3:e['status']='待确认';e['reason']+='；积分与理论总氢数不一致';e['confidence']=min(.4,e['confidence'])
    return {'assigned':sum(e.get('experimental_ppm') is not None for e in environments),
        'review':sum(e['status']!='人工确认' for e in environments),'integral_scale':scale,
        'unmatched_signals':[s['id'] for j,s in enumerate(signals) if j not in selections],
        'optimizer':'MILP with shared signal capacity and aggregate integral slack',
        'confidence_note':'启发式评分，不是统计概率；自动结果均需科研审核'}
