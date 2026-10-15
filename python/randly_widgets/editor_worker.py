"""One coalescing worker for editor IPC; no GTK or configuration globals here."""
import threading,time
from .editor_mailbox import SyncMailbox

class EditorWorker:
    def __init__(self,config,sample,execute=None,mailbox=None):
        self.mailbox=mailbox or SyncMailbox()
        self.config=config;self.sample=sample;self.execute=execute or self._execute
        self.lock=threading.Lock();self.wake=threading.Event();self.stopped=threading.Event()
        self.version=0;self.done=0;self.mode=None;self.requested_at=0.;self.snapshot=None;self.sample_version=0
        self.thread=threading.Thread(target=self._run,name='widget-editor-ipc',daemon=True)
        self.thread.start()
    def request(self,mode):
        with self.lock:
            self.version+=1;self.mode=mode;self.requested_at=time.monotonic()
        self.wake.set()
    def take(self):
        with self.lock:
            snapshot=self.snapshot if self.sample_version==self.version else None;self.snapshot=None
            return snapshot,self.done!=self.version
    def stop(self):
        self.stopped.set();self.wake.set();self.thread.join(timeout=3)
    def _execute(self,mode):
        if not self.mailbox.available():return False
        with self.lock:
            if self.mode is not None and self.mode!=mode:return True
            version=self.version
        request=self.mailbox.submit(mode)
        try:
            while not self.stopped.is_set() and time.monotonic()<request['expires']:
                with self.lock:
                    if self.version!=version:return True  # Latest edit replaces this request.
                ack=self.mailbox.read(self.mailbox.ack_path)
                if ack.get('token')==request['token']:return bool(ack.get('success'))
                if not self.mailbox.available():return False
                self.stopped.wait(.02)
            return False
        finally:self.mailbox.cancel(request['token'])
    def _run(self):
        next_sample=0
        while not self.stopped.is_set():
            with self.lock:version,done,mode,at=self.version,self.done,self.mode,self.requested_at
            if version!=done and time.monotonic()-at>=.04:
                try:success=self.execute(mode)
                except (OSError,ValueError):success=False
                with self.lock:self.done=version
                next_sample=0
            else:success=True
            if self.stopped.is_set():break
            if time.monotonic()>=next_sample:
                try:snapshot=self.sample()
                except (OSError,ValueError,ConnectionError):snapshot=None
                if snapshot is not None:
                    with self.lock:self.snapshot=(snapshot,success);self.sample_version=version
                next_sample=time.monotonic()+(.12 if time.monotonic()-at<.8 else .4)
            self.wake.wait(.02);self.wake.clear()
