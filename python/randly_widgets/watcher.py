import fcntl,json,os,socket,struct,sys,time
from pathlib import Path
from .paths import RUNTIME, CONF
from .adapters.wayfire import wf_send,wf_recv
EVENTS = ["wset-workspace-changed", "output-wset-changed"]

def owned_watchers(proc_root=Path('/proc')):
    from .paths import EWW_DIR
    expected=str(Path.home()/'.local/bin/widgetctl');found=[]
    for path in proc_root.iterdir():
        if not path.name.isdigit():continue
        try:
            if path.stat().st_uid!=os.getuid():continue
            argv=[x.decode() for x in (path/'cmdline').read_bytes().split(b'\0') if x]
            if not argv or Path(argv[0]).name not in ('python','python3') or expected not in argv[1:] or argv[-1:]!=['watch']:continue
            configs=[argv[i+1] for i,a in enumerate(argv[:-1]) if a in ('--config','-c')]
            if not any(str(Path(c).expanduser().resolve())==EWW_DIR for c in configs):continue
            found.append((int(path.name),(path/'stat').read_text().rsplit(')',1)[1].split()[19]))
        except (OSError,UnicodeError,IndexError):pass
    return found

def stop_owned():
    import signal
    for pid,birth in owned_watchers():
        try:
            if Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()[19]==birth:os.kill(pid,signal.SIGTERM)
        except (OSError,IndexError):pass
    for _ in range(20):
        if not owned_watchers():break
        time.sleep(.025)
def lock_or_exit():
    fd=os.open(str(Path(RUNTIME)/'eww-workspace-watch.lock'),os.O_RDWR|os.O_CREAT,0o600)
    try: fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError: sys.exit(0)
    return fd

def connect(path):
    sock=socket.socket(socket.AF_UNIX);sock.settimeout(2);sock.connect(path);return sock

def conf_mtime():
    try:return Path(CONF).stat().st_mtime_ns
    except OSError:return 0

def sync(path=None):
    from .runtime import sync as reconcile
    return reconcile()


def sync_leaving():
    from .runtime import sync as reconcile
    return reconcile(leaving_only=True)


def main():
    from concurrent.futures import ThreadPoolExecutor
    from .workspace_guard import invalidate
    _lock=lock_or_exit()  # held for process lifetime
    path=os.environ.get('WAYFIRE_SOCKET')
    if not path:sys.exit('WAYFIRE_SOCKET is not set')
    from .editor_mailbox import SyncMailbox
    mailbox=SyncMailbox();heartbeat=0;future_request=None
    failures=0;future=None
    # Keep receiving/invalidation responsive even while GTK maps a widget or a
    # stagger is playing. One worker, no backlog of historical workspaces.
    with ThreadPoolExecutor(max_workers=1,thread_name_prefix='widget-reconcile') as worker:
        while True:
            sock=None
            try:
                sock=connect(path)
                wf_send(sock,'window-rules/events/watch',{'events':EVENTS});wf_recv(sock)
                failures=0;seen=conf_mtime();leave=False;pending=True;audit=time.monotonic()+2
                deadline=invalidate(.5)['ready_at']
                while True:
                    now=time.monotonic()
                    if now>=heartbeat:mailbox.heartbeat();heartbeat=now+1
                    editor_request=mailbox.pending()
                    if future is not None and future.done():
                        success=future.result()
                        if future_request:mailbox.complete(future_request,success);future_request=None
                        if success is False:pending=True;deadline=max(deadline,time.monotonic()+.1)
                        future=None
                        editor_request=mailbox.pending()
                    if time.monotonic()>=audit:
                        pending=True;audit=time.monotonic()+2
                    changed=conf_mtime()
                    if changed!=seen:seen=changed;pending=True
                    if future is None:
                        if leave:
                            future=worker.submit(sync_leaving);leave=False
                        elif editor_request and time.monotonic()>=deadline:
                            future_request=editor_request
                            from .runtime import sync as reconcile
                            future=worker.submit(reconcile,editor_request['mode'],request_token=editor_request['token'])
                            pending=False
                        elif pending and time.monotonic()>=deadline:
                            future=worker.submit(sync);pending=False
                    sock.settimeout(.03 if pending or future or (Path(RUNTIME)/'eww-widgets-editing').exists() else .25)
                    try:msg=wf_recv(sock)
                    except socket.timeout:continue
                    if msg.get('event') in EVENTS:
                        deadline=invalidate(.5)['ready_at']
                        leave=True;pending=True
            except (OSError,ConnectionError,ValueError,struct.error):
                invalidate(.5)
                failures+=1
                if failures>15:return
                time.sleep(2)
            finally:
                if sock is not None:sock.close()
