"""Draw-only native Eww transforms, driven by the existing data stream."""
import copy,json,math,uuid
from pathlib import Path
from .paths import RUNTIME
from .storage import write_json

KEYS=['fade','zoom','pop','vortex','zap','glitch','spin','float3d','slide','slideleft','slideright','slideup','slidedown','none']
LABELS={'fade':'Fundido','zoom':'Zoom','pop':'Pop','vortex':'Vórtice','zap':'Zap','glitch':'Glitch',
        'spin':'Giro','float3d':'Profundidad','slide':'Deslizar','slideleft':'Hacia la izquierda',
        'slideright':'Hacia la derecha','slideup':'Hacia arriba','slidedown':'Hacia abajo','none':'Ninguna'}
SIZE_KEYS=['stable','staged']
SIZE_LABELS={'stable':'Animar ya expandido','staged':'Fundido y después expansión'}

def native(effect):
    # Revealer handles opacity only; transforms never change GTK allocation.
    return 'none' if effect=='none' else 'crossfade'

def set_motion(client,ids,reveal,effect='none',duration=0):
    path=Path(RUNTIME)/'motion.json'
    try:state=json.loads(path.read_text())
    except (OSError,ValueError):state={}
    if not isinstance(state,dict):state={}
    for wid in ids:
        state[wid]={'reveal':reveal,'effect':effect,'ms':max(0,int(duration)),
                    'transition':native(effect),'duration':f'{max(0,int(duration))}ms','token':uuid.uuid4().hex}
    result=client('update','wmotion='+json.dumps(state,separators=(',',':')))
    if result is None or result.returncode:return False
    write_json(path,state)
    return True

def requests():
    try:
        value=json.loads((Path(RUNTIME)/'motion.json').read_text())
        return value if isinstance(value,dict) else {}
    except (OSError,ValueError):return {}

def pose(effect,p):
    p=max(0.,min(1.,p));e=1-(1-p)**3;q=1-e
    sx=sy=1.;x=y=rotate=0.
    if effect=='zoom':sx=sy=.68+.32*e
    elif effect=='pop':
        if p<.62:sx=sy=.68+.32*(1-(1-p/.62)**3)
        elif p<.82:sx=sy=1-.025*math.sin((p-.62)/.2*math.pi/2)
        else:sx=sy=.975+.025*(p-.82)/.18
    elif effect=='vortex':sx=sy=.12+.88*e;rotate=-85*q
    elif effect in ('spin','helix'):sx=sy=.8+.2*e;rotate=-45*q
    elif effect in ('zap','blinds','shatter'):
        sx=.025+.975*max(0,(p-.2)/.8)**.5;sy=.025+.975*min(1,p/.4)
    elif effect=='glitch':x=math.sin(p*73)*6*(1-p)**2;y=math.sin(p*43)*1.5*(1-p)**2
    elif effect=='float3d':sx=.82+.18*e;sy=.6+.4*e;y=10*q
    elif effect in ('slide','slideup','melt'):y=18*q
    elif effect=='slidedown':y=-18*q
    elif effect=='slideleft':x=18*q
    elif effect=='slideright':x=-18*q
    if p>=1:sx=sy=1.;x=y=rotate=0.
    return {'sx':f'{round(sx*100)}%','sy':f'{round(sy*100)}%',
            'x':f'{round(x+(1-sx)*50)}%','y':f'{round(y+(1-sy)*50)}%','rotate':round(rotate,4)}

class MotionEngine:
    """Bounded settling and frozen entry frames, independent for each instance."""
    def __init__(self):self.states={}
    def step(self,controls,data,ready,opts,now):
        frames={};shown_data={};running=False
        for wid,value in data.items():
            request=controls.get(wid,{})
            state=self.states.get(wid)
            if state is None or state['token']!=request.get('token'):
                was_shown=bool(state and state.get('shown'))
                state={'token':request.get('token'),'started':None,'since':now,'stable':now,
                       'signature':None,'frozen':None,'shown':was_shown,'ready_since':None}
                if not request.get('reveal') and was_shown:state['started']=now
                self.states[wid]=state
            reveal=bool(request.get('reveal'));ms=request.get('ms',0)
            effect=request.get('effect','none');mode=opts.get(wid,{}).get('motion_mode','stable')
            duration=ms/1000 if effect!='none' else 0
            waiting=False
            if reveal and ready.get(wid):
                if state['started'] is None:
                    if state['ready_since'] is None:state['ready_since']=now
                    signature=json.dumps(value,sort_keys=True,ensure_ascii=False)
                    if signature!=state['signature']:state['signature']=signature;state['stable']=now
                    waiting=bool(duration and mode=='stable' and now-state['stable']<.06 and now-state['ready_since']<.24)
                    if not waiting:state['started']=now;state['frozen']=copy.deepcopy(value)
            elif reveal:waiting=True
            if not reveal and state['started'] is None:
                frames[wid]=dict(pose('none',1),show=False,fade_duration='0ms');shown_data[wid]=value;continue
            if waiting:
                frames[wid]=dict(pose('zoom',0),show=False,fade_duration='0ms');shown_data[wid]=value
                running|=bool(ready.get(wid));continue
            p=min(1,max(0,(now-state['started'])/duration)) if duration else 1
            if reveal:
                if mode=='staged' and effect!='none':
                    # Opacity arrives first; expansion follows without reallocating.
                    expand=max(0,(p-.3)/.7)
                    frame=pose(effect,expand)
                    if effect=='fade':frame=pose('zoom',.4+.6*expand)
                else:frame=pose(effect,p)
            else:frame=pose(effect,1-p)
            frame['show']=reveal
            frame['fade_duration']=f'{round(ms*(.3 if mode=="staged" and reveal else 1))}ms' if duration else '0ms'
            frames[wid]=frame;state['shown']=reveal
            shown_data[wid]=state['frozen'] if p<1 and state['frozen'] is not None else value
            running|=p<1
            if p>=1:state['frozen']=None
        for wid,frame in frames.items():frame['token']=controls.get(wid,{}).get('token')
        self.states={wid:s for wid,s in self.states.items() if wid in data}
        return frames,shown_data,running
