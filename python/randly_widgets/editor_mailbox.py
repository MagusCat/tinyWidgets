"""Latest-only requests to the existing profile watcher; no per-action process."""
import json,time,uuid,math
from pathlib import Path
from .paths import RUNTIME
from .storage import write_json

class SyncMailbox:
    def __init__(self,root=None):
        self.root=Path(root or RUNTIME)
        self.request_path=self.root/'editor-sync-request.json'
        self.ack_path=self.root/'editor-sync-ack.json'
        self.service_path=self.root/'editor-sync-service.json'
    @staticmethod
    def read(path):
        try:
            value=json.loads(path.read_text());return value if isinstance(value,dict) else {}
        except (OSError,ValueError):return {}
    @staticmethod
    def valid_mode(mode):return type(mode) is bool or mode=='global' or type(mode) is int and 1<=mode<=100
    @staticmethod
    def live(record):
        expiry=record.get('expires',0)
        return type(expiry) in (int,float) and math.isfinite(expiry) and expiry>time.monotonic()
    def heartbeat(self):write_json(self.service_path,{'version':1,'expires':time.monotonic()+2})
    def available(self):
        service=self.read(self.service_path)
        return service.get('version')==1 and self.live(service)
    def submit(self,mode):
        if not self.valid_mode(mode):raise ValueError('Filtro de editor inválido')
        request={'token':uuid.uuid4().hex,'mode':mode,'expires':time.monotonic()+20}
        write_json(self.request_path,request);return request
    def pending(self):
        request=self.read(self.request_path)
        if not isinstance(request.get('token'),str) or not self.live(request):return None
        mode=request.get('mode')
        if not self.valid_mode(mode):return None
        if self.read(self.ack_path).get('token')==request['token']:return None
        if not (self.root/'eww-widgets-editing').exists():return None
        return request
    def current(self,token):
        request=self.read(self.request_path)
        return request.get('token')==token and self.live(request) and (self.root/'eww-widgets-editing').exists()
    def complete(self,request,success):write_json(self.ack_path,{'token':request['token'],'success':bool(success)})
    def cancel(self,token):
        if self.read(self.request_path).get('token')==token:self.request_path.unlink(missing_ok=True)
