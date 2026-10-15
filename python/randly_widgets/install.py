"""Transactional activation; restore every touched entrypoint on failure."""
import json,os,shutil,signal,subprocess,time
from datetime import datetime
from pathlib import Path
from .paths import EWW_DIR,STATE_DIR,RUNTIME,PROFILE_KEY
from .storage import atomic_text,write_json
from .composer import publish

BOOTSTRAP="""#!/usr/bin/env python3
import os, sys
from pathlib import Path
sys.path.insert(0, str(Path.home()/'.local/lib'))
"""

def wrapper(command,compat=False):
    text=BOOTSTRAP
    text+="for i,a in enumerate(sys.argv[:-1]):\n    if a in ('--config','-c'): os.environ['RANDLY_WIDGETS_CONFIG']=str(Path(sys.argv[i+1]).expanduser().resolve())\n"
    if compat:text+='from randly_widgets.api import *\n'
    text+='from randly_widgets.cli import main\n'
    text+='if __name__ == "__main__":\n    raise SystemExit(main('+repr(command)+' + sys.argv[1:]))\n'
    return text

def replacements():
    home=Path.home();root=Path(EWW_DIR)
    files={root/'eww.yuck':'(include "generated/current/view.yuck")\n',root/'eww.scss':'@import "generated/current/style";\n',root/'.modular-active':'1\n'}
    scripts={'widgets':([],True),'widget-editor':(['editor'],False),'workspace-watch':(['watch'],False),'planner':(['planner'],False)}
    for name,(command,compat) in scripts.items():files[root/'scripts'/name]=wrapper(command,compat)
    if root!= (home/'.config/eww').resolve():return files
    files[home/'.local/bin/eww-desktop']=wrapper(['start'])
    wayfire=home/'.config/wayfire.ini'
    if wayfire.exists():
        s=wayfire.read_text()
        for a,b in [('~/.config/eww/scripts/widget-editor','~/.local/bin/widgetctl editor'),('~/.config/eww/scripts/widgets menu','~/.local/bin/widgetctl editor palette'),('~/.config/eww/scripts/widgets toggle-all','~/.local/bin/widgetctl toggle-all'),('widgets = ~/.local/bin/eww-desktop','widgets = ~/.local/bin/widgetctl start')]:s=s.replace(a,b)
        files[wayfire]=s
    matugen=home/'.config/matugen/config.toml'
    if matugen.exists():
        s=matugen.read_text().replace("pgrep -x eww >/dev/null && ~/.config/eww/scripts/widgets reload >/dev/null 2>&1 || true","~/.local/bin/widgetctl theme >/dev/null 2>&1 || true")
        s=s.replace("post_hook = '~/.local/bin/widgetctl reload >/dev/null 2>&1 || true'","post_hook = '~/.local/bin/widgetctl theme >/dev/null 2>&1 || true'")
        s=s.replace("output_path = '~/.config/eww/_colors.scss'","output_path = '~/.local/state/randly-widgets/palette.scss'")
        files[matugen]=s
    menu=home/'.local/bin/desktop-menu'
    if menu.exists():
        files[menu]=menu.read_text().replace("[str(HOME / '.config/eww/scripts/widget-editor')]","[str(HOME / '.local/bin/widgetctl'), 'editor']")
    power=home/'.local/lib/desktop_power/effects.py'
    if power.exists():
        s=power.read_text();a=s.index('def widgets(profile):');b=s.index('\n\ndef ',a+5)
        replacement="""def widgets(profile):
    # Only the desktop profile is affected; other Eww projects have separate daemons.
    import hashlib
    config = str((HOME / '.config/eww').resolve())
    key = hashlib.sha256(config.encode()).hexdigest()[:12]
    editing = Path(os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}')) / 'randly-widgets' / key / 'eww-widgets-editing'
    command = [str(HOME / '.local/bin/widgetctl'), '--config', config]
    if not profile['widgets'] and not editing.exists():
        run([*command, 'stop'])
    elif profile['widgets']:
        run([*command, 'start'])
    write_text(STATE / 'eww-revision', WIDGET_REVISION)
"""
        files[power]=s[:a]+replacement+s[b:]
    return files

def activate_files(generation):
    files=replacements();snapshot=STATE_DIR/'activation-backups'/datetime.now().strftime('%Y%m%d-%H%M%S')
    snapshot.mkdir(parents=True)
    entries=[]
    for index,(path,value) in enumerate(files.items()):
        entry={'path':str(path),'backup':str(index),'exists':path.exists(),'mode':path.stat().st_mode&0o777 if path.exists() else 0o644}
        if path.exists():shutil.copy2(path,snapshot/str(index))
        entries.append(entry)
    instance_path=Path(EWW_DIR)/'instances.json'
    entry={'path':str(instance_path),'backup':'instances-before','exists':instance_path.exists(),'mode':0o600}
    if instance_path.exists():shutil.copy2(instance_path,snapshot/'instances-before')
    entries.append(entry)
    current=Path(EWW_DIR)/'generated/current'
    metadata={'files':entries,'current':str(current.readlink()) if current.is_symlink() else None}
    write_json(snapshot/'snapshot.json',metadata)
    try:
        publish(generation,Path(EWW_DIR))
        for path,value in files.items():
            mode=path.stat().st_mode&0o777 if path.exists() else (0o755 if path.parent.name in ('bin','scripts') else 0o644)
            atomic_text(path,value);path.chmod(mode)
    except BaseException:
        restore_files(snapshot);raise
    return snapshot

def restore_files(snapshot):
    snapshot=Path(snapshot);metadata=json.loads((snapshot/'snapshot.json').read_text())
    for entry in metadata['files']:
        p=Path(entry['path'])
        if entry['exists']:atomic_text(p,(snapshot/entry['backup']).read_text());p.chmod(entry['mode'])
        else:p.unlink(missing_ok=True)
    current=Path(EWW_DIR)/'generated/current'
    old=metadata['current']
    if old:
        tmp=current.with_name('.restored');tmp.unlink(missing_ok=True);tmp.symlink_to(old);tmp.replace(current)
    else:current.unlink(missing_ok=True)

def reload_integrations():
    """Reload only known user-owned helpers; never terminate processes by name."""
    from .paths import RUNTIME_BASE
    old=RUNTIME_BASE/'eww-workspace-watch.lock'
    # Existing watcher has no PID owner record, so identify its full script argument.
    expected=str(Path.home()/'.config/eww/scripts/workspace-watch')
    for path in Path('/proc').iterdir():
        if not path.name.isdigit():continue
        try:
            if path.stat().st_uid!=os.getuid():continue
            argv=[x.decode() for x in (path/'cmdline').read_bytes().split(b'\0') if x]
            if not argv or Path(argv[0]).name not in ('python3','python'):continue
            legacy = expected in argv[1:]
            modern = str(Path.home()/'.local/bin/widgetctl') in argv[1:] and argv[-1:] == ['watch']
            if modern:
                configargs=[argv[i+1] for i,a in enumerate(argv[:-1]) if a in ('--config','-c')]
                modern=any(str(Path(x).expanduser().resolve())==EWW_DIR for x in configargs)
            if not (legacy or modern):continue
            start=(path/'stat').read_text().rsplit(')',1)[1].split()[19]
            if (path/'stat').read_text().rsplit(')',1)[1].split()[19]==start:os.kill(int(path.name),signal.SIGTERM)
        except (OSError,UnicodeError,IndexError):pass
    if Path(EWW_DIR)!=(Path.home()/'.config/eww').resolve():return
    try:
        from desktop_power import controller,effects
        from desktop_power.storage import STATE
        owner=json.loads((STATE/'daemon.lock').read_text())
        if effects.process_identity(owner['pid'])[0]==owner['birth']:
            os.kill(owner['pid'],signal.SIGTERM)
            for _ in range(40):
                if effects.process_identity(owner['pid'])[0]!=owner['birth']:break
                time.sleep(.05)
        controller.ensure_daemon(wake=True)
    except (OSError,ValueError,KeyError,ProcessLookupError):pass
