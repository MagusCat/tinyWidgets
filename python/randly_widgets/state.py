import json,time
from pathlib import Path
from .paths import RUNTIME,STATE_DIR
from .registry import INSTANCE_IDENT
from .storage import locked,write_json

def safe(wid):
    if not INSTANCE_IDENT.fullmatch(wid): raise ValueError('ID de instancia inválido')
    return wid

def read_event(wid):
    try: return json.loads((Path(RUNTIME)/('event-'+safe(wid)+'.json')).read_text())
    except (OSError,ValueError): return {}

def update_event(wid,changes):
    path=Path(RUNTIME)/('event-'+safe(wid)+'.json')
    with locked(str(path)+'.lock'):
        value=read_event(wid); value.update(changes);write_json(path,value)
    return value

def read_persistent(wid,kind):
    path=STATE_DIR/safe(wid)/(kind+'.json')
    try:return json.loads(path.read_text())
    except (OSError,ValueError):return {}

def write_persistent(wid,kind,data):
    path=STATE_DIR/safe(wid)/(kind+'.json')
    with locked(str(path)+'.lock'):write_json(path,data)
