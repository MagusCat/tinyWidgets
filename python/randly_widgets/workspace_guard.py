"""A latest-event barrier shared by the watcher and in-flight reconciliations."""
import json,time,uuid
from pathlib import Path
from .paths import RUNTIME
from .storage import write_json

def read():
    try:return json.loads((Path(RUNTIME)/'workspace-transition.json').read_text())
    except (OSError,ValueError):return {}

def invalidate(delay=.5):
    state={'token':uuid.uuid4().hex,'ready_at':time.monotonic()+delay}
    write_json(Path(RUNTIME)/'workspace-transition.json',state)
    return state

def ready(token):
    state=read()
    return state.get('token')==token and time.monotonic()>=state.get('ready_at',0)
