"""Build immutable Eww generations and validate them away from the active profile."""
import ast,hashlib,json,os,re,shlex,shutil,subprocess,tempfile,time
from pathlib import Path
from .paths import EWW_DIR,PROFILE_KEY,SURFACE_PREFIX
from .registry import Registry
from .config import load
from .storage import atomic_text,write_json,locked

class BuildError(ValueError):pass

def check_forms(text):
    depth=0;expr_depth=0;quote=None;escape=False;comment=False
    for i,c in enumerate(text):
        if comment:
            if c=='\n':comment=False
            continue
        if quote:
            if escape:escape=False
            elif c=='\\':escape=True
            elif c==quote:quote=None
            continue
        if c==';':comment=True
        elif c in "\"'":quote=c
        elif c=='{':expr_depth+=1
        elif c=='}':expr_depth-=1
        elif c=='[' and expr_depth==0 and re.search(r'[A-Za-z_][\w.]*$',text[:i]):
            raise BuildError('Acceso JSON fuera de expresión Yuck: usa {variable[campo]}')
        elif c=='(':depth+=1
        elif c==')':
            depth-=1
            if depth<0:raise BuildError('Paréntesis Yuck sin apertura')
    if depth or expr_depth or quote:raise BuildError('Yuck incompleto: paréntesis/expresión/cadena sin cerrar')

def check_styles(css,kind):
    if re.search(r'@(import|use|forward|at-root|extend)\b',css):raise BuildError(f'{kind}: regla SCSS que escapa al módulo')
    clean=re.sub(r'//[^\n]*|/\*.*?\*/','',css,flags=re.S)
    depth=0;start=0;quote=None;escape=False;prefix='.rw-desktop.rw-'+kind
    for i,c in enumerate(clean):
        if quote:
            if escape:escape=False
            elif c=='\\':escape=True
            elif c==quote:quote=None
            continue
        if c in "\"'":quote=c;continue
        if c=='{':
            if depth==0:
                header=clean[start:i].strip()
                for selector in header.split(','):
                    selector=selector.strip()
                    if not selector.startswith(prefix) or any(x in selector for x in ['+','~']):raise BuildError(f'{kind}: selector fuera de su raíz: {selector}')
            depth+=1
        elif c=='}':
            depth-=1
            if depth<0:raise BuildError(f'{kind}: llave CSS sin apertura')
            if depth==0:start=i+1
    if depth or quote:raise BuildError(f'{kind}: SCSS incompleto')

def css_failure(text):
    return bool(re.search(r'(?im)SCSS parsing error|CSS parsing error|Theme parsing error|Action failed with error|\bERROR\b|error:',text))

def without_confirmed_success_timeouts(logs):
    """Only for fully verified fixtures: discard Eww's expired SUCCESS reply.

    Never discard a failed action, generic channel errors, or GTK diagnostics.
    The caller must independently confirm every expected instance is active.
    """
    record=r'(?m)^\s*\d{4}-\d\d-\d\dT[^\n]*?\bERROR\s+eww::error_handling_ctx\s*> '
    success=r'(?:sending response from main thread\n\s*\nCaused by:\n[ \t]+0: Failed to send success response from application thread\n[ \t]+1: channel closed|Failed to send success response from application thread\n\s*\nCaused by:\n[ \t]+channel closed)'
    return re.sub(record+success+r'[ \t]*(?:\n|$)', '', logs)

def wait_for_instances(cmd,expected,proc,timeout=3):
    """Open's exit status is not an acknowledgement on Eww 0.5 (100ms IPC)."""
    deadline=time.monotonic()+timeout;active={}
    while time.monotonic()<deadline:
        if proc.poll() is not None:raise BuildError('Eww terminó al abrir las ventanas de prueba')
        result=subprocess.run(cmd+['active-windows'],capture_output=True,text=True,timeout=5)
        if css_failure(result.stdout+result.stderr):raise BuildError('Eww rechazó la consulta de ventanas: '+(result.stderr or result.stdout)[-1000:])
        if result.returncode==0:
            active={a.strip():b.strip() for line in result.stdout.splitlines() if ':' in line for a,b in [line.split(':',1)]}
            if all(active.get(wid)==kind for wid,kind in expected.items()):return
        time.sleep(.05)
    missing=', '.join(wid for wid,kind in expected.items() if active.get(wid)!=kind)
    raise BuildError('Eww no confirmó las ventanas abiertas: '+missing)

def check_shared_styles(text):
    if re.search(r'\.rw-desktop\s+[@$]',text):
        raise BuildError('Sass compartido inválido: mixins/variables no son selectores CSS')

def wrap_window_roots(text):
    """Wrap each window's final child, regardless of module layout/formatting."""
    spans=[]
    for match in re.finditer(r'\(defwindow\s+',text):
        depth=0;expr=0;quote=None;escape=False;comment=False;start=None;root=None
        for i in range(match.start(),len(text)):
            c=text[i]
            if comment:
                if c=='\n':comment=False
                continue
            if quote:
                if escape:escape=False
                elif c=='\\':escape=True
                elif c==quote:quote=None
                continue
            if c in "\"'":quote=c
            elif c==';':comment=True
            elif c=='{':expr+=1
            elif c=='}':expr-=1
            elif expr:continue
            elif c=='(':
                if depth==1:start=i
                depth+=1
            elif c==')':
                depth-=1
                if depth==1 and start is not None:root=(start,i+1)
                if depth==0:break
        if root is None:raise BuildError('Ventana sin contenido')
        spans.append(root)
    prefix='(revealer :transition "crossfade" :duration {(wmotion[wid]?.reveal ?: false) ? (wcfg.m[wid]?.fade_duration ?: "0ms") : (wmotion[wid]?.duration ?: "0ms")} :reveal {(wmotion[wid]?.token == wcfg.m[wid]?.token) && (wcfg.m[wid]?.show ?: false) && (wcfg.r[wid] ?: false)} (transform :class "rw-motion-space" :rotate {wcfg.m[wid]?.rotate ?: 0} :translate-x {wcfg.m[wid]?.x ?: "0%"} :translate-y {wcfg.m[wid]?.y ?: "0%"} :scale-x {wcfg.m[wid]?.sx ?: "100%"} :scale-y {wcfg.m[wid]?.sy ?: "100%"} '
    for start,end in reversed(spans):text=text[:start]+prefix+text[start:end]+'))'+text[end:]
    return text

def render(root=None,widgets=None,config_dir=None,include=None):
    root=Path(root or EWW_DIR);config_dir=Path(config_dir or root).resolve(); registry=Registry(root)
    if registry.errors:raise BuildError(json.dumps(registry.errors,ensure_ascii=False))
    selected={k:m for k,m in registry.modules.items() if (include is not None and k in include) or (include is None and m.get('enabled',True))}
    if not selected:raise BuildError('No hay módulos seleccionados')
    widgets=load() if widgets is None else widgets
    initial={'o':{},'t':{},'g':{},'r':{},'m':{}}
    from .appearance import options,option_context
    context=option_context()
    from .paths import STATE_DIR
    for w in widgets:
        if w['window'] not in selected:continue
        wid=w['id'];initial['o'][wid]=options(w,context);initial['g'][wid]={**selected[w['window']].get('initial',{}),'error':''}
        initial['t'][wid]=initial['g'][wid]
        initial['r'][wid]=not selected[w['window']].get('provider')
    ctl=shlex.quote(str(Path.home()/'.local/bin/widgetctl'))+' --config '+shlex.quote(str(config_dir))
    namespace='rw-'+hashlib.sha256(str(config_dir).encode()).hexdigest()[:12]+'-'
    header=';; Generated by widgetctl. Edit modules and instances, not this file.\n'
    initial_options=initial.pop('o');initial.pop('m')
    yuck=header+'(deflisten wcfg :initial '+json.dumps(json.dumps(initial,ensure_ascii=False),ensure_ascii=False)+' '+json.dumps(ctl+' data')+')\n'
    for name,command,value in [('woptions','options',initial_options),('wframes','frames',{})]:
        yuck+='(deflisten '+name+' :initial '+json.dumps(json.dumps(value,ensure_ascii=False),ensure_ascii=False)+' '+json.dumps(ctl+' '+command)+')\n'
    yuck+='(defvar wmotion "{}")\n'
    yuck+=(root/'shared/common.yuck').read_text().replace('~/.config/eww/scripts/planner',ctl+' planner')+'\n'
    base_style=(root/'shared/base.scss').read_text()
    check_shared_styles(base_style)
    from .paths import PALETTE_SCSS
    palette=Path(PALETTE_SCSS) if root.resolve()==Path(EWW_DIR) and Path(PALETTE_SCSS).exists() else root/'_colors.scss'
    style=palette.read_text()+'\n// RW_PALETTE_END\n'+base_style+'\n'
    seen=set(re.findall(r'\(def(?:window|widget|var|listen|poll)\s+([^\s\[()]+)',yuck))
    for kind,m in selected.items():
        folder=Path(m['path']);text=(folder/'view.yuck').read_text();css=(folder/'style.scss').read_text()
        if '@ASSETS@' in text+css and not m.get('assets'):
            raise BuildError(f'{kind}: declara sus recursos en assets del manifiesto')
        css=css.replace('@ASSETS@', str(folder/'assets'))
        check_forms(text)
        check_styles(css,kind)
        if re.search(r'\(def(?:var|listen|poll)\s+',text):raise BuildError(f'{kind}: usa el proveedor del módulo para datos/estado')
        for name in re.findall(r'\(def(?:window|widget)\s+([^\s\[()]+)',text):
            if not name.startswith('rw-'+kind):raise BuildError(f'{kind}: definición sin prefijo propio: {name}')
            if name in seen:raise BuildError(f'{kind}: definición repetida: {name}')
            seen.add(name)
        if css.strip() and '.rw-desktop.rw-'+kind not in css:raise BuildError(f'{kind}: estilos sin raíz propia')
        # Module styles are nested under their root; global at-rules/imports are not extensions.
        if re.search(r'@(import|use|forward)\b',css):raise BuildError(f'{kind}: no se admiten imports de CSS externos al módulo')
        if m.get('provider'):
            try:ast.parse((folder/m['provider']).read_text())
            except (ValueError,SyntaxError,OSError) as exc:raise BuildError(f'{kind}/provider.py: {exc}') from exc
        text=text.replace('@CTL@',ctl).replace('@NAMESPACE@',namespace).replace('@ASSETS@',str(folder/'assets'))
        # Wrap only window roots; each module keeps its own content and styles.
        text=wrap_window_roots(text)
        # Fixed project paths in helpers must also select the correct profile.
        text=text.replace('~/.config/eww/scripts/planner',ctl+' planner')
        yuck+='\n;; module '+kind+'\n'+text+'\n';style+='\n// module '+kind+'\n'+css+'\n'
    for name in ('themes.scss','effects.scss'):
        extra=root/'shared'/name
        if extra.exists():
            content=extra.read_text();check_shared_styles(content)
            style+='\n// shared '+name+'\n'+content
    yuck=yuck.replace('wcfg.o[','woptions[').replace('wcfg.m[','wframes[')
    check_forms(yuck)
    return yuck,style

def build(root=None,widgets=None,config_dir=None,include=None):
    root=Path(root or EWW_DIR);yuck,style=render(root,widgets,config_dir,include)
    digest=hashlib.sha256((yuck+'\0'+style).encode()).hexdigest()[:20]
    folder=root/'generated'/digest
    folder.mkdir(parents=True,exist_ok=True)
    # Even identical writes trigger Eww's recursive watcher and remap windows.
    for name,content in [('view.yuck',yuck),('style.scss',style)]:
        path=folder/name
        if not path.exists() or path.read_text()!=content:atomic_text(path,content)
    return folder

def publish(folder,root=None):
    root=Path(root or EWW_DIR);target=root/'generated/current';last=root/'generated/previous'
    with locked(root/'generated/publish.lock'):
        if target.is_symlink():
            prev=target.readlink();temp=last.with_name('.previous-new');temp.unlink(missing_ok=True);temp.symlink_to(prev);temp.replace(last)
        temp=target.with_name('.current-new');temp.unlink(missing_ok=True);temp.symlink_to(Path(folder).name);temp.replace(target)

def graphics_available():
    import socket
    runtime=os.environ.get('XDG_RUNTIME_DIR','/run/user/'+str(os.getuid()))
    display=os.environ.get('WAYLAND_DISPLAY','')
    if not display:return False,'WAYLAND_DISPLAY no está definido'
    address=display if display.startswith('/') else str(Path(runtime)/display)
    s=socket.socket(socket.AF_UNIX)
    try:s.connect(address);return True,''
    except OSError as exc:return False,str(exc)
    finally:s.close()

def validate_graphics(folder,root=None,widgets=None):
    """Disposable config and daemon; no changes or signals to desktop Eww."""
    available,reason=graphics_available()
    if not available:raise BuildError('Validación gráfica pendiente: '+reason)
    root=Path(root or EWW_DIR)
    configured_widgets=load() if widgets is None else widgets
    with tempfile.TemporaryDirectory(prefix='rw-verify-') as temp:
        test=Path(temp);text=(folder/'view.yuck').read_text()
        # Freeze initial data: validation never starts real data providers.
        text=re.sub(r'\(deflisten (wcfg|woptions|wframes) :initial ("(?:[^"\\]|\\.)*") ("(?:[^"\\]|\\.)*")\)', r'(defvar \1 \2)', text)
        initial=re.search(r'\(defvar wcfg ("(?:[^"\\]|\\.)*")\)',text)
        if initial:
            data=json.loads(json.loads(initial.group(1)))
            data['r']={w['id']:True for w in configured_widgets}
            text=text[:initial.start(1)]+json.dumps(json.dumps(data,ensure_ascii=False))+text[initial.end(1):]
        frames={w['id']:{'show':True,'token':'verify','fade_duration':'0ms','sx':'100%','sy':'100%','x':'0%','y':'0%','rotate':0} for w in configured_widgets}
        text=re.sub(r'\(defvar wframes ("(?:[^"\\]|\\.)*")\)',lambda _: '(defvar wframes '+json.dumps(json.dumps(frames))+')',text)
        (test/'eww.yuck').write_text(text)
        (test/'eww.scss').write_text((folder/'style.scss').read_text())
        cmd=['eww','--config',str(test),'--no-daemonize']
        proc=None
        try:
            with (test/'daemon.log').open('w') as log:
                proc=subprocess.Popen(cmd+['daemon'],stdout=log,stderr=log)
                for _ in range(30):
                    if proc.poll() is not None:break
                    ping=subprocess.run(cmd+['ping'],capture_output=True,timeout=3)
                    if ping.returncode==0:break
                    time.sleep(.1)
                expected = {'rw-'+w['window'] for w in configured_widgets if w['show']}
                result = None
                for attempt in range(30):
                    result=subprocess.run(cmd+['list-windows'],capture_output=True,text=True,timeout=5)
                    if css_failure(result.stdout + result.stderr):raise BuildError('Eww rechazó estilos: '+(result.stderr or result.stdout)[-1800:])
                    loaded=set(re.findall(r'(?<![\w-])rw-[\w-]+', result.stdout))
                    if result.returncode==0 and expected <= loaded: break
                    logs=(test/'daemon.log').read_text(errors='replace')
                    if proc.poll() is not None or re.search(r'(?im)\bERROR\b|error:',logs): break
                    time.sleep(.1)
                if result is None or result.returncode or not expected <= loaded:
                    logs=(test/'daemon.log').read_text(errors='replace')
                    missing=', '.join(sorted(expected-loaded)) if result is not None else 'configuración'
                    raise BuildError('Eww no cargó la candidata ('+missing+'). '+(logs[-1800:] or (result.stderr if result else '') or 'Sin diagnóstico del daemon'))
                # Eww 0.5 silently drops startup Sass errors, while its reload
                # IPC response expires after 100ms. Its file watcher uses an
                # internal receiver without that deadline, and reports success
                # only after both Sass compilation and GTK CSS loading finish.
                for attempt in range(60):
                    if attempt % 10 == 0:
                        with (test/'eww.scss').open('a') as style:
                            style.write('\n/* widgetctl validation */\n')
                    time.sleep(.1)
                    logs=(test/'daemon.log').read_text(errors='replace')
                    if css_failure(logs):raise BuildError('Eww rechazó estilos: '+logs[-1800:])
                    if 'Reloaded config successfully' in logs:break
                    if proc.poll() is not None:raise BuildError('Eww terminó al validar estilos: '+logs[-1800:])
                else:raise BuildError('Eww no confirmó la compilación de estilos: '+logs[-1800:])
                # Update shared controls once, then acknowledge each mapping
                # independently instead of queuing opens on expired IPC replies.
                motion=json.dumps({v['id']:{'reveal':True,'token':'verify','transition':'none','duration':'0ms'} for v in configured_widgets})
                updated=subprocess.run(cmd+['update','wmotion='+motion],capture_output=True,text=True,timeout=5)
                if updated.returncode or css_failure(updated.stdout+updated.stderr):raise BuildError('No se pudo mostrar la candidata: '+updated.stderr[-500:])
                verified={}
                for w in configured_widgets:
                    if w['show']:
                        opened=subprocess.run(cmd+['open','rw-'+w['window'],'--id','verify-'+w['id'],'--arg','wid='+w['id']],capture_output=True,text=True,timeout=5)
                        if css_failure(opened.stdout + opened.stderr):raise BuildError('CSS rechazado al abrir '+w['id']+': '+(opened.stderr or opened.stdout)[-1800:])
                        if opened.returncode:raise BuildError('No renderiza '+w['id']+': '+opened.stderr[-500:])
                        verified['verify-'+w['id']]='rw-'+w['window']
                        wait_for_instances(cmd,verified,proc)
                time.sleep(.3)
                # No exception is allowed if even one fixture disappeared.
                wait_for_instances(cmd,verified,proc)
                logs=(test/'daemon.log').read_text(errors='replace')
                failures=without_confirmed_success_timeouts(logs)
                if css_failure(failures):raise BuildError('Errores Eww/GTK: '+failures[-1800:])
        except BaseException as exc:
            from .paths import STATE_DIR
            STATE_DIR.mkdir(parents=True,exist_ok=True)
            report=STATE_DIR/'validation-last.log'
            atomic_text(report,str(exc)+'\n\n'+(test/'daemon.log').read_text(errors='replace'))
            raise BuildError(str(exc)+'\nDiagnóstico guardado en '+str(report)) from exc
        finally:
            try:subprocess.run(cmd+['kill'],capture_output=True,timeout=3)
            except (OSError,subprocess.TimeoutExpired):pass
            if proc and proc.poll() is None:
                proc.terminate()
                try:proc.wait(timeout=3)
                except subprocess.TimeoutExpired:proc.kill();proc.wait()
    return True
