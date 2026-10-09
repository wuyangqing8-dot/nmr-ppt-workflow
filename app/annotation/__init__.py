import math
import numpy as np

def ppm_to_x(ppm,maximum,minimum,left,width):
    if maximum<=minimum:raise ValueError('ppm 范围必须最大值大于最小值')
    return left+(maximum-ppm)/(maximum-minimum)*width

def atom_to_slide(xy,bbox,box):
    l,t,r,b=bbox;x,y,w,h=box
    return x+(xy[0]-l)/(r-l)*w,y+(xy[1]-t)/(b-t)*h

def segment_distance(p,a,b):
    vx,vy=b[0]-a[0],b[1]-a[1];dx,dy=p[0]-a[0],p[1]-a[1]
    u=max(0.,min(1.,(dx*vx+dy*vy)/max(vx*vx+vy*vy,1e-12)))
    return math.hypot(dx-u*vx,dy-u*vy)

def layout_structure(structure,box,font_size=14):
    atoms={a['id']:atom_to_slide(a['xy'],structure['bbox'],box) for a in structure['atoms']}
    bonds=[(atoms[b['a']],atoms[b['b']]) for b in structure['bonds']];occupied=[];placements=[]
    for e in structure['environments']:
        # Equivalent atoms are already grouped upstream. Display one representative
        # per hydrogen environment, retaining the complete atom mapping for review.
        saved_ids=[aid for aid in e['atom_ids'] if e.get('positions',{}).get(aid)]
        ids=[saved_ids[0] if saved_ids else min(e['atom_ids'],key=lambda aid:atoms[aid][0])]
        for atom_id in ids:
            anchor=atoms[atom_id];saved=e.get('positions',{}).get(atom_id)
            w=max(.13,len(e['label'])*font_size/95);h=font_size/72*1.15
            if saved:pos=tuple(saved)
            else:
                candidates=[]
                for radius in [.18,.25,.34,.43,.55,.7,.85]:
                    for k in range(16):
                        ang=k*math.pi/8;cx=anchor[0]+radius*math.cos(ang);cy=anchor[1]+radius*math.sin(ang)
                        centre=(cx,cy);pos=(cx-w/2,cy-h/2)
                        collision=sum(30 for ox,oy,ow,oh in occupied if abs(cx-(ox+ow/2))<(w+ow)/2+.025 and abs(cy-(oy+oh/2))<(h+oh)/2+.025)
                        atom_pen=sum(15 for ax,ay in atoms.values() if abs(cx-ax)<w/2+.04 and abs(cy-ay)<h/2+.055)
                        bond_pen=sum(8 for a,b in bonds if segment_distance(centre,a,b)<max(.045,h*.35))
                        outside=100 if not (.35<=pos[0]<=12.9-w and .2<=pos[1]<=3.1-h) else 0
                        candidates.append((collision+atom_pen+bond_pen+outside+radius,pos))
                pos=min(candidates,key=lambda x:x[0])[1]
            leader=math.hypot(pos[0]+w/2-anchor[0],pos[1]+h/2-anchor[1])>.44
            occupied.append((*pos,w,h));placements.append({'env_id':e['id'],'atom_id':atom_id,'text':e['label'],'box':[*pos,w,h],'anchor':anchor,'leader':leader})
    return placements

def layout_spectrum(task):
    sp=task['spectrum'];box=task['layout']['spectrum_box'];x,y,w,h=box
    hi,lo=task['layout']['ppm_range'];arr=np.array(sp['intensity']);xx=np.array(sp['ppm'])
    mask=(xx<=hi)&(xx>=lo);ymax=max(float(np.max(arr[mask])),1e-12)/task['layout'].get('display_gain',1.)
    groups={}
    for e in task['structure']['environments']:
        if e.get('experimental_ppm') is None:continue
        key=e.get('signal_id') or str(e['experimental_ppm']);groups.setdefault(key,[]).append(e)
    result=[];occupied=[];side_rows=0
    for key,items in sorted(groups.items(),key=lambda kv:-kv[1][0]['experimental_ppm']):
        ppm=items[0]['experimental_ppm'];cx=ppm_to_x(ppm,hi,lo,x,w)
        k=int(np.argmin(abs(xx-ppm)));height=max(0,arr[k])/ymax
        text='+'.join(e['label'] for e in items)
        pending=any(e['status'] not in ['人工确认','自动建议'] for e in items)
        if pending and not task['layout'].get('hide_uncertainty_marks',True):text+='?'
        tw=max(.2,.115*len(text));th=.22
        py=y+h*.685-min(1,height/1.1)*h*.675-.26;px=cx-tw/2
        saved=items[0].get('positions',{}).get('spectrum')
        leader=False
        if saved:px,py=saved
        else:
            if len(text)>4 and ppm<2 and task['layout'].get('show_leaders',False):
                px=x+w+.10;py=y+.18+side_rows*.29;side_rows+=1;leader=True
            while any(abs(px-ox)<(tw+ow)/2 and abs(py-oy)<th+.03 for ox,oy,ow in occupied):py-=.25
            py=max(y+.03,py);px=min(13.1-tw,max(x,px))
        occupied.append((px,py,tw));result.append({'env_id':items[0]['id'],'signal_id':key,'text':text,'box':[px,py,tw,th],'ppm':ppm,
            'leader':leader,'anchor':[cx,y+h*.685-min(1,height/1.1)*h*.675]})
    return result
