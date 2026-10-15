"""Short lease: crashed editors can never leave provider updates paused."""
import time
from pathlib import Path
from .paths import RUNTIME
from .storage import write_json
from .editor_mailbox import SyncMailbox

class DragLease:
    def __init__(self,root=None):self.path=Path(root or RUNTIME)/'editor-drag.json';self.active=False;self.renew_at=0
    def update(self,active,now=None):
        now=time.monotonic() if now is None else now
        if active and (not self.active or now>=self.renew_at):
            write_json(self.path,{'expires':now+1.5});self.renew_at=now+.5
        elif self.active and not active:self.path.unlink(missing_ok=True)
        self.active=bool(active)
    def close(self):self.path.unlink(missing_ok=True);self.active=False

def dragging(root=None,now=None):
    now=time.monotonic() if now is None else now
    value=SyncMailbox.read(Path(root or RUNTIME)/'editor-drag.json')
    expiry=value.get('expires',0)
    return isinstance(expiry,(int,float)) and expiry>now

def paused_instances(widgets,is_dragging):
    if not is_dragging:return set()
    interactive={'tasks','habits','timer','chest'}
    return {w['id'] for w in widgets if w['window'] not in interactive}

def hold_data(data,previous,paused):
    return {wid:previous.get(wid,value) if wid in paused else value for wid,value in data.items()}
