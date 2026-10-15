"""Eww ownership is a config directory, never the executable name."""
import os, signal, subprocess, time
from pathlib import Path
from ..paths import EWW_DIR, RUNTIME, APPLIED, ensure_runtime

def argv(*args): return ['eww','--config',EWW_DIR,'--no-daemonize',*map(str,args)]
def session_env():
    env=os.environ.copy()
    runtime=env.get('XDG_RUNTIME_DIR',f'/run/user/{os.getuid()}'); env['XDG_RUNTIME_DIR']=runtime
    if not env.get('WAYLAND_DISPLAY'):
        try:
            sockets=sorted(p.name for p in Path(runtime).glob('wayland-*') if p.is_socket())
            if sockets: env['WAYLAND_DISPLAY']=sockets[0]
        except OSError: pass
    return env

def eww(*args):
    try: return subprocess.run(argv(*args),capture_output=True,text=True,timeout=5,env=session_env())
    except (OSError,subprocess.TimeoutExpired): return None

def owned_pids(proc_root=None):
    """Verify uid, executable, exact --config and process start time before signaling."""
    found=[]
    for p in Path(proc_root or '/proc').iterdir():
        if not p.name.isdigit(): continue
        try:
            if p.stat().st_uid!=os.getuid(): continue
            cmd=(p/'cmdline').read_bytes().split(b'\0'); args=[a.decode() for a in cmd if a]
            if not args or Path(args[0]).name!='eww': continue
            configs=[args[i+1] for i,a in enumerate(args[:-1]) if a in ('--config','-c')]
            if not any(str(Path(x).expanduser().resolve())==EWW_DIR for x in configs): continue
            start=(p/'stat').read_text().rsplit(')',1)[1].split()[19]
            found.append((int(p.name),start))
        except (OSError,UnicodeError,IndexError): pass
    return found

def stop():
    native=os.environ.get('RANDLY_WIDGETS_MANAGER')
    if native:return subprocess.run([native,'--config',EWW_DIR,'stop'],capture_output=True,timeout=30)
    result=eww('kill'); time.sleep(.15)
    for pid,start in owned_pids():
        try:
            stat=Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()
            if stat[19]==start: os.kill(pid,signal.SIGTERM)
        except (OSError,IndexError): pass
    return result

def start():
    ensure_runtime(); result=eww('ping')
    if result is not None and result.returncode==0: return True
    # Native manager owns lifecycle and the CSS-only provider.
    native=os.environ.get('RANDLY_WIDGETS_MANAGER')
    if native:return subprocess.run([native,'--config',EWW_DIR,'start'],capture_output=True,timeout=30).returncode==0
    log=Path(RUNTIME)/'daemon.log'
    with log.open('a') as f:
        subprocess.Popen(['eww','--config',EWW_DIR,'daemon'],stdin=subprocess.DEVNULL,stdout=f,stderr=f,env=session_env(),start_new_session=True)
    for _ in range(40):
        result=eww('ping')
        if result is not None and result.returncode==0: return True
        time.sleep(.1)
    return False

def restart_daemon():
    stop()
    for pid,start in owned_pids():
        try:
            if Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()[19]==start: os.kill(pid,signal.SIGKILL)
        except (OSError,IndexError): pass
    Path(APPLIED).unlink(missing_ok=True)
    return globals()['start']()
