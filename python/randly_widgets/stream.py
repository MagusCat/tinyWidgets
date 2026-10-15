"""Fixed-size listener pool: options, provider data and native motion are isolated."""
import json,os,signal,time
from pathlib import Path
from .paths import APPLIED,RUNTIME,CONF,EWW_DIR,POWER_STATE
from .config import load
from .registry import REGISTRY,SCHEMA
from .appearance import options,option_context
from .jobs import Scheduler
from .storage import write_json
from .transitions import MotionEngine
from .editor_activity import dragging,paused_instances,hold_data

def read_json(path,default):
    try:return json.loads(Path(path).read_text())
    except (OSError,ValueError):return default

class Configuration:
    def __init__(self):self.revision=None;self.widgets=[];self.opts={}
    def refresh(self):
        paths=[Path(CONF),Path(EWW_DIR)/'style.json',Path(EWW_DIR)/'animation.json',Path(POWER_STATE),Path(RUNTIME)/'eww-widgets-editing',Path(RUNTIME)/'eww-widgets-anim-preview']
        def stamp(p):
            try:return p.stat().st_mtime_ns
            except OSError:return 0
        revision=tuple(map(stamp,paths))
        if revision!=self.revision:
            try:
                widgets=load();context=option_context();opts={w['id']:options(w,context) for w in widgets if w['window'] in SCHEMA}
                self.widgets=widgets;self.opts=opts;self.revision=revision
            except (ValueError,OSError):pass
        return self.widgets,self.opts

class JsonCache:
    """Do not decode large provider snapshots again for every animation frame."""
    def __init__(self):self.values={}
    def read(self,path,default):
        path=Path(path)
        try:stamp=path.stat().st_mtime_ns
        except OSError:stamp=None
        previous=self.values.get(path)
        if previous is None or previous[0]!=stamp:
            value=read_json(path,default);self.values[path]=(stamp,value)
        return self.values[path][1]

def encode(value):return json.dumps(value,ensure_ascii=False,separators=(',',':'))

def frozen_data(data,controls,freezes):
    return {wid:freezes[wid]['data'] if wid in freezes and freezes[wid].get('token')==controls.get(wid,{}).get('token') else value for wid,value in data.items()}

def main(channel='cfg'):
    scheduler=Scheduler() if channel in ('cfg','data') else None
    config=Configuration();motion=MotionEngine();cache=JsonCache();last=None;last_snapshot=None;last_freeze=None
    frame_inputs=None;frame_running=False
    def stopping(*_):raise SystemExit(0)
    for sig in (signal.SIGTERM,signal.SIGINT):signal.signal(sig,stopping)
    try:
        while os.getppid()!=1:
            animating=False
            if channel=='frames':
                snapshot=cache.read(Path(RUNTIME)/'data-snapshot.json',{})
                controls=cache.read(Path(RUNTIME)/'motion.json',{})
                if frame_inputs and frame_inputs[0] is snapshot and frame_inputs[1] is controls and not frame_running:
                    time.sleep(.05);continue
                frames,_,animating=motion.step(controls,snapshot.get('g',{}),snapshot.get('r',{}),snapshot.get('o',{}),time.monotonic())
                frame_inputs=(snapshot,controls);frame_running=animating
                freezes={wid:{'token':state['token'],'data':state['frozen']} for wid,state in motion.states.items() if state['frozen'] is not None}
                if freezes!=last_freeze:
                    write_json(Path(RUNTIME)/'motion-freeze.json',freezes);last_freeze=freezes
                payload=frames
            else:
                cached,opts=config.refresh()
                if channel=='options':payload=opts
                else:
                    active=set(cache.read(APPLIED,{}))
                    visible=[w for w in cached if w['show'] and w['id'] in active and w['window'] in SCHEMA]
                    paused={wid for wid in paused_instances(visible,dragging()) if last_snapshot and last_snapshot.get('r',{}).get(wid)}
                    values=scheduler.tick(visible,lambda w:opts[w['id']],paused=paused)
                    data={w['id']:{**REGISTRY.modules.get(w['window'],{}).get('initial',{}),'error':'',**values.get(w['id'],{})} for w in cached}
                    if paused and last_snapshot:data=hold_data(data,last_snapshot.get('g',{}),paused)
                    ready={w['id']:not REGISTRY.modules.get(w['window'],{}).get('provider') or w['id'] in scheduler.results for w in cached}
                    snapshot={'g':data,'r':ready,'o':opts}
                    if snapshot!=last_snapshot:
                        write_json(Path(RUNTIME)/'data-snapshot.json',snapshot);last_snapshot=snapshot
                    shown=frozen_data(data,cache.read(Path(RUNTIME)/'motion.json',{}),cache.read(Path(RUNTIME)/'motion-freeze.json',{}))
                    if channel=='cfg':
                        # Compatibility until an already-running old generation is reloaded.
                        frames,shown,animating=motion.step(cache.read(Path(RUNTIME)/'motion.json',{}),data,ready,opts,time.monotonic())
                    payload={'g':shown,'r':ready,'t':{w['id']:shown.get(w['id'],{}) for w in visible if w['window']=='clock'}}
                    if channel=='cfg':payload.update(o=opts,m=frames)
            out=encode(payload)
            if out!=last:print(out,flush=True);last=out
            time.sleep((1/30 if animating else .05) if channel in ('frames','cfg') else (.05 if channel=='data' and scheduler.jobs else .2))
    except (BrokenPipeError,KeyboardInterrupt):pass
    finally:
        if scheduler:scheduler.close()
