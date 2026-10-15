import math,time
from pathlib import Path
from randly_widgets.paths import STATE_DIR
from randly_widgets.state import safe
from randly_widgets.storage import locked,write_json
import json

def get_timer_state(wid,focus_min=25,break_min=5):
    path=STATE_DIR/safe(wid)/'timer.json'
    try:return json.loads(path.read_text())
    except (OSError,ValueError):return dict(running=False,left=focus_min*60,total=focus_min*60,mode='focus',updated=time.time())

def save_timer_state(wid,state):
    path=STATE_DIR/safe(wid)/'timer.json'
    with locked(str(path)+'.lock'):write_json(path,state)

def update(wid,opts,action=None):
    focus=max(1,int(opts.get('focus_min') or 25));rest=max(1,int(opts.get('break_min') or 5))
    now=time.time();path=STATE_DIR/safe(wid)/'timer.json'
    with locked(str(path)+'.lock'):
        saved=get_timer_state(wid,focus,rest);st=dict(saved)
        if st['running']:
            st['left']=max(0,st['left']-(now-st.get('updated',now)))
            if st['left']<=0:
                st['mode']='break' if st['mode']=='focus' else 'focus'
                st['left']=(rest if st['mode']=='break' else focus)*60
                st['total']=st['left'];st['running']=False;st['updated']=now
        completed=saved['running'] and not st['running']
        if action=='timer-reset':st=dict(running=False,left=focus*60,total=focus*60,mode='focus',updated=now)
        elif action=='timer-toggle':st['running']=not st['running'];st['updated']=now
        if action or completed:write_json(path,st)
    return st

def collect(ctx):
    st=update(ctx.widget['id'],ctx.opts)
    sec=math.ceil(st['left']);m,s=divmod(sec,60)
    return dict(time=f'{m:02d}:{s:02d}',state='Descanso' if st['mode']=='break' else 'Enfoque',running=st['running'],pct=max(0,min(100,round(100*(1-st['left']/max(1,st['total']))))))
