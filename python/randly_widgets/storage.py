"""Atomic files and advisory locks, shared by configuration and per-instance state."""
import fcntl, json, os, tempfile
from pathlib import Path
from contextlib import contextmanager
@contextmanager
def locked(path):
    path=Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+') as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        yield

def atomic_text(path, text):
    path=Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix='.'+path.name+'.', dir=path.parent)
    try:
        with os.fdopen(fd,'w') as f:
            f.write(text); f.flush(); os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)

def write_json(path, data):
    atomic_text(path,json.dumps(data,ensure_ascii=False,indent=2)+'\n')
