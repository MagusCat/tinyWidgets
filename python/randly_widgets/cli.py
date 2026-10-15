"""Public CLI. Resolve --config before importing modules that hold profile paths."""
import argparse,copy,importlib,json,os,re,shutil,subprocess,sys,tempfile,time
from pathlib import Path

def parser():
    p=argparse.ArgumentParser(prog='widgetctl',description='Widgets modulares del escritorio')
    p.add_argument('-c','--config',help='Directorio del perfil Eww; no se comparte estado entre perfiles')
    p.add_argument('command',nargs='?',default='list')
    p.add_argument('arguments',nargs=argparse.REMAINDER)
    return p

def main(argv=None):
    ns=parser().parse_args(argv)
    if ns.config:os.environ['RANDLY_WIDGETS_CONFIG']=str(Path(ns.config).expanduser().resolve())
    from .paths import EWW_DIR,ensure_runtime,CONF,RUNTIME,SURFACE_PREFIX
    from . import config
    from .registry import REGISTRY,SCHEMA
    from . import composer
    cmd,args=ns.command,ns.arguments
    try:
        # Inspection and template creation must work without a display or running daemon.
        if cmd in ('list','catalog'):
            usage={}
            for w in config.load():usage.setdefault(w['window'],[]).append(w['id'])
            for kind,m in REGISTRY.modules.items():
                print(f"{kind:12} {m['name']:23} {m.get('decision','disponible'):12} {' '.join(usage.get(kind,[]))}")
            for kind,error in REGISTRY.errors.items():print(kind+': '+error,file=sys.stderr)
            return int(bool(REGISTRY.errors))
        if cmd=='new':return new_widget(args[0] if args else '',EWW_DIR)
        if cmd in ('validate','build'):
            include=[args[0]] if args and not args[0].startswith('-') else None
            if include and include[0] not in REGISTRY.modules:raise ValueError('Tipo de widget desconocido')
            generation=composer.build(include=include)
            print('Estructura válida:',generation)
            if '--graphics' in args:
                composer.validate_graphics(generation);verify_catalog();print('Eww y GTK: correctos')
            else:print('Validación gráfica: pendiente (usa validate --graphics dentro de tu sesión)')
            return 0
        if cmd=='prepare-manager-reload':
            generation=composer.build();composer.validate_graphics(generation)
            current=Path(EWW_DIR)/'generated/current'
            old=str(current.readlink()) if current.is_symlink() else None
            composer.publish(generation)
            print(json.dumps({'generation':str(generation),'old':old}));return 0
        if cmd=='activate':return activate()
        if cmd=='rollback':return rollback(args[0] if args else None)
        if cmd=='preview':return preview(args[0] if args else '')
        if cmd=='status':
            from .adapters.eww import eww
            result=eww('ping');print('Eww: '+('activo' if result is not None and result.returncode==0 else 'inaccesible'))
            print('Perfil:',EWW_DIR);print('Activado:',(Path(EWW_DIR)/'.modular-active').exists());return 0
        if cmd in ('start','stop','restart','reload','sync','sync-leaving','sync-out','watch','editor','edit') and not ((Path(EWW_DIR)/'.modular-active').exists() or (Path(EWW_DIR)/'.preview').exists()):
            raise ValueError('Sistema preparado; actívalo con widgetctl activate dentro de tu sesión gráfica')
        ensure_runtime()
        if cmd=='watch':
            from .watcher import main as watch
            return watch() or 0
        if cmd in ('cfg','data','options','frames'):
            from .stream import main as stream
            return stream(cmd) or 0
        if cmd in ('editor','edit'):
            if not (Path(EWW_DIR)/'.modular-active').exists():raise ValueError('Activa primero con widgetctl activate tras validar en tu sesión gráfica')
            if args:os.environ['WIDGET_EDITOR_OPEN']='palette' if args[0]=='palette' else 'settings:'+args[0]
            from .editor import run
            return run()
        if cmd in ('add','set','enable','disable','remove','duplicate') and args:
            if not (Path(EWW_DIR)/'.modular-active').exists(): raise ValueError('Activa primero con widgetctl activate')
            edit_instance(cmd,args);return 0
        if cmd=='planner':
            from .planner import main as planner
            return planner(args)
        if cmd=='action':return widget_action(args)
        if cmd in ('timer-toggle','timer-reset','pixel-poke'):return widget_action([args[0],cmd])
        if cmd=='proc':return process_action(args)
        if cmd=='profile':
            from . import profiles
            if not args or args[0]=='list':
                for m in profiles.list_profiles():print(m['id']+' — '+m.get('desc',''))
                return 0
            if args[0]=='apply':return 0 if profiles.apply_profile(args[1]) else 1
            if args[0]=='save':profiles.save_current_as_profile(args[1]);return 0
        from . import runtime,actions
        from .adapters import eww as adapter
        if cmd=='start':
            from .policy import is_disabled
            if is_disabled() and not (Path(RUNTIME)/'eww-widgets-editing').exists():return 0
            runtime.clear_stale_editor()
            if not adapter.start():raise ValueError('Eww no pudo iniciar; consulta status y el log del perfil')
            # The watcher owns the initial settled reconciliation, too.
            if os.environ.get('WAYFIRE_SOCKET'):start_watcher()
            else:runtime.sync()
            return 0
        if cmd=='stop':adapter.stop();return 0
        if cmd=='restart':
            if not adapter.restart_daemon():return 1
            return 0 if runtime.sync() else 1
        if cmd in ('reload','sync','sync-leaving','sync-out'):
            if cmd=='reload':
                generation=composer.build();composer.validate_graphics(generation)
                old=(Path(EWW_DIR)/'generated/current').readlink() if (Path(EWW_DIR)/'generated/current').is_symlink() else None
                composer.publish(generation)
                try:
                    if not runtime.reload():raise ValueError('Falló la recarga de Eww')
                    start_watcher(replace=True)
                except BaseException:
                    if old:composer.publish(Path(EWW_DIR)/'generated'/old)
                    raise
                return 0
            mode='global' if args and args[0]=='global' else True if args and args[0]=='on' else False if args and args[0]=='off' else int(args[0]) if args and args[0].isdigit() else None
            return 0 if runtime.sync(mode,leaving_only=cmd!='sync' or '--leaving-only' in args) else 1
        if cmd in ('toggle-all','toggle-global','enable','disable') or cmd=='toggle' and not args:
            from .paths import DISABLED_FLAG
            flag=Path(DISABLED_FLAG)
            enabled=not flag.exists() if cmd not in ('enable','disable') else cmd=='disable'
            if enabled:flag.write_text('1\n')
            else:flag.unlink(missing_ok=True)
            runtime.sync();return 0
        if cmd in ('menu','move','toggle','resize','run','rerun','photos','preview-anim','test-anim','preview-fx','test-fx','style','anim'):
            from .appearance import save_style,load_style,save_animation
            if cmd=='menu':actions.cmd_menu()
            elif cmd in ('move','toggle','resize','run'):getattr(actions,'cmd_'+cmd)(args[0])
            elif cmd=='rerun':(Path(RUNTIME)/('eww-widgets-rerun-'+args[0])).touch()
            elif cmd in ('preview-anim','test-anim'):runtime.preview_animation(*(args+['',''])[:2])
            elif cmd in ('preview-fx','test-fx'):runtime.preview_fx(args[0] if args else None)
            elif cmd=='style':
                if args:save_style(skin=args[0],fx=args[1] if len(args)>1 else None,background=args[2] if len(args)>2 else None)
                else:print(json.dumps(load_style(),ensure_ascii=False))
            elif cmd=='anim':
                from .appearance import ANIM_DEFAULTS,load_animation
                if not args:print(json.dumps(load_animation(),ensure_ascii=False))
                else:
                    positional=[];settings={}
                    for arg in args:
                        if '=' not in arg:positional.append(arg);continue
                        key,value=arg.split('=',1)
                        if key not in ANIM_DEFAULTS:raise ValueError('Opción de animación desconocida: '+key)
                        if isinstance(ANIM_DEFAULTS[key],bool):
                            if value.lower() not in ('true','false','yes','no','1','0','on','off'):raise ValueError('Usa true o false para '+key)
                            settings[key]=value.lower() in ('true','yes','1','on')
                        elif isinstance(ANIM_DEFAULTS[key],int):settings[key]=int(value)
                        else:settings[key]=value
                    if len(positional)>2:raise ValueError('Usa anim [entrada] [salida] opción=valor')
                    save_animation(*positional,**settings)
            elif cmd=='photos':raise ValueError('Las fotos ahora usan el proveedor por instancia; no requieren otro listener')
            return 0
        raise ValueError('Comando desconocido: '+cmd)
    except (ValueError,OSError,KeyError,IndexError) as exc:
        print('widgetctl: '+str(exc),file=sys.stderr);return 1

def new_widget(kind,root):
    from .registry import IDENT
    from .storage import write_json
    if not IDENT.fullmatch(kind):raise ValueError('Usa un nombre como mi-widget')
    folder=Path(root)/'widgets'/kind
    if folder.exists():raise ValueError('Ya existe ese módulo')
    folder.mkdir(parents=True)
    write_json(folder/'manifest.json',dict(id=kind,version=1,name=kind.replace('-',' ').title(),desc='Mi widget personalizado',icon='󰋩',size=[320,160],order=100,enabled=True,group='generic',base_id=kind,provider=None,requires=[],interval=60,initial={},options=[dict(key='text',label='Texto',type='text',default='Hola, mundo'),dict(key='width',label='Ancho',type='size',default='320')]))
    (folder/'view.yuck').write_text('(defwindow rw-'+kind+' [wid]\n  :monitor 0 :geometry (geometry :x "40px" :y "60px" :width "0px" :height "0px" :anchor "top left")\n  :stacking "bg" :exclusive false :focusable false :namespace "@NAMESPACE@${wid}"\n  (box :class "rw-desktop rw-'+kind+' wroot ${wcfg.o[wid]?.skin_class ?: \'skin-bento\'}"\n    (box :class "card" :style "min-width: ${wcfg.o[wid]?.inner ?: 282}px;"\n      (label :text {wcfg.o[wid]?.text ?: "Hola, mundo"}))))\n')
    (folder/'style.scss').write_text('.rw-desktop.rw-'+kind+' .card { color: $on_surface; }\n')
    print('Creado:',folder);print('Personaliza manifest.json, view.yuck y style.scss; provider.py es opcional.');return 0

def edit_instance(command,args):
    from . import config
    from .registry import REGISTRY,INSTANCE_IDENT
    from .adapters.eww import eww
    from . import runtime
    from .paths import EWW_DIR
    widgets=config.load();name=args[0]
    if command=='add':
        if name not in REGISTRY.modules:raise ValueError('No existe ese tipo de widget')
        meta=REGISTRY.modules[name]
        if not meta.get('enabled',True):raise ValueError('Tipo retirado; restáuralo explícitamente antes de usarlo')
        wid=args[args.index('--id')+1] if '--id' in args else meta.get('base_id',name)
        if config.find(widgets,wid):raise ValueError('ID ya utilizado')
        widgets.append(dict(id=wid,window=name,show=True,anchor='top-left',x=40,y=60,opts={}))
    else:
        w=config.find(widgets,name)
        if not w:raise ValueError('Instancia desconocida: '+name)
        if command=='duplicate':
            n=2
            while config.find(widgets,name+str(n)):n+=1
            other=copy.deepcopy(w);other.update(id=name+str(n),x=w['x']+24,y=w['y']+24);widgets.append(other)
        elif command=='remove':widgets=[v for v in widgets if v['id']!=name]
        elif command in ('enable','disable'):w['show']=command=='enable'
        elif command=='set':
            for part in args[1:]:
                key,sep,value=part.partition('=')
                if not sep:raise ValueError('Usa opción=valor')
                if key in ('x','y'):w[key]=int(value)
                elif key=='anchor':w[key]=value
                else:w['opts'][key]=value
    if command=='add' and (Path(EWW_DIR)/'.modular-active').exists():
        from .api import ensure_current
        if not ensure_current(name):raise ValueError('No se pudo cargar el tipo '+name)
    config.save(widgets)
    if (Path(EWW_DIR)/'.modular-active').exists():
        # Existing types are already compiled; sync only touches instance windows.
        runtime.sync()
    print('Configuración guardada')

def start_watcher(replace=False):
    from .paths import EWW_DIR
    if not os.environ.get('WAYFIRE_SOCKET'):return
    ctl=str(Path.home()/'.local/bin/widgetctl')
    if replace:
        from .watcher import stop_owned
        stop_owned()
    subprocess.Popen([ctl,'--config',EWW_DIR,'watch'],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)

def widget_action(args):
    from .config import load,find,save
    from .providers import load_provider,Context
    from .appearance import options
    from .state import read_event,update_event
    from .paths import RUNTIME
    wid,action=args[:2];widget=find(load(),wid)
    if not widget:raise ValueError('Instancia desconocida')
    opts=options(widget);kind=widget['window'];now=time.time()
    if kind=='cat' and action=='poke':
        import random
        update_event(wid,dict(says=random.choice(['meow','mrrp?','purrr','nya~','mew!']),until=now+2.5))
    elif kind=='chest':
        if action in ('toggle','close'):update_event(wid,dict(open=not read_event(wid).get('open',False) if action=='toggle' else False,hover=-1))
        elif action=='hover':update_event(wid,dict(hover=int(args[2])))
        elif action=='critter':
            import random
            name=args[2]
            if name not in ('raccoon','rat'):raise ValueError('Mascota inválida')
            update_event(wid,{name+'_says':random.choice(['zzz…','*yawn*','meow?'] if name=='raccoon' else ['squeak!','cheese?','eek!']),name+'_until':now+2})
        elif action=='launch':
            from .chest import parse
            slots=parse();i=int(args[2]);update_event(wid,dict(open=False,hover=-1))
            if 0<=i<len(slots) and slots[i] and slots[i]['cmd']:subprocess.Popen(['sh','-c',slots[i]['cmd']],start_new_session=True)
    elif kind=='procs' and action=='proc':
        try:
            process_action(args[2:])
            update_event(wid,{'error':''})
        except ValueError as exc:
            update_event(wid,{'error':str(exc)})
    elif kind=='music' and action=='music':
        command=args[2]
        if command not in ('previous','next','play-pause'):raise ValueError('Acción de música inválida')
        chosen=load_provider(kind,wid).collect(Context(widget,opts)).get('player')
        if chosen:subprocess.run(['playerctl','-p',chosen,command],timeout=3,check=False)
    elif kind=='timer' and action in ('timer-toggle','timer-reset'):
        load_provider(kind,wid).update(wid,opts,action)
    elif kind=='pixel' and action=='pixel-poke':
        if opts.get('click_action')=='Siguiente personaje':
            m=load_provider(kind,wid);names=list(m.PIXEL_SPRITES);cur=opts.get('sprite',names[0]);widget['opts']['sprite']=names[(names.index(cur)+1)%len(names)] if cur in names else names[0];ws=load();ws=[widget if w['id']==wid else w for w in ws];save(ws)
        else:(Path(RUNTIME)/('eww-pixel-poke-'+wid)).write_text(str(now))
    else:raise ValueError('Acción no válida para este widget')
    (Path(RUNTIME)/('eww-widgets-rerun-'+wid)).touch();return 0

def process_action(args):
    import signal
    command,tokens=args[:2]
    if command not in ('pause','term','kill'):raise ValueError('Acción de proceso inválida')
    protected={'wayfire','waybar','eww','systemd','dbus-broker','dbus-daemon','Xwayland','pipewire','pipewire-pulse','wireplumber'}
    targets=[]
    for value in tokens.split(','):
        pid,sep,start=value.partition(':')
        if not sep or not pid.isdigit() or not start.isdigit():raise ValueError('Actualiza la lista antes de actuar sobre ese proceso')
        p=Path('/proc')/pid
        try:
            fields=(p/'stat').read_text().rsplit(')',1)[1].split()
            if p.stat().st_uid!=os.getuid() or fields[19]!=start:continue
            if (p/'comm').read_text().strip() in protected or int(pid)==os.getpid():continue
            commandline=(p/'cmdline').read_bytes()
            if any(x in commandline for x in (b'/.local/bin/widgetctl',b'/.local/bin/desktop-power',b'/.local/bin/wf-')):continue
            targets.append((int(pid),fields[0]=='T',start))
        except OSError:pass
    if not targets:raise ValueError('El proceso cambió, terminó o está protegido; actualiza la lista')
    all_paused=all(t[1] for t in targets)
    sig={'pause':signal.SIGCONT if all_paused else signal.SIGSTOP,'term':signal.SIGTERM,'kill':signal.SIGKILL}[command]
    for pid,_,start in targets:
        try:
            if Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()[19]==start:os.kill(pid,sig)
        except OSError:pass
    return 0

def verify_catalog():
    from .registry import REGISTRY
    from . import composer
    fixtures=[dict(id='test-'+k,window=k,show=True,anchor='top-left',x=0,y=0,opts={}) for k,m in REGISTRY.modules.items() if m.get('enabled',True)]
    generation=composer.build(widgets=fixtures)
    return composer.validate_graphics(generation,widgets=fixtures)

def preview(kind):
    from .registry import REGISTRY
    from . import composer
    from .storage import write_json
    from .paths import EWW_DIR
    if kind not in REGISTRY.modules:raise ValueError('Tipo desconocido')
    source=Path(EWW_DIR);root=Path.home()/'.cache/randly-widgets'/('preview-'+kind)
    if root.exists():shutil.rmtree(root)
    root.mkdir(parents=True)
    for name in ('widgets','shared','assets'):
        if (source/name).exists():shutil.copytree(source/name,root/name)
    for name in ('_colors.scss','style.json','animation.json','habits.conf','tasks.md','chest.conf'):
        if (source/name).exists():shutil.copy2(source/name,root/name)
    widgets=[dict(id='preview',window=kind,show=True,anchor='top-left',x=40,y=60,opts={})]
    write_json(root/'instances.json',dict(version=1,revision=1,widgets=widgets));(root/'.preview').touch()
    gen=composer.build(root,widgets,root,include=[kind]);composer.publish(gen,root)
    (root/'eww.yuck').write_text('(include "generated/current/view.yuck")\n');(root/'eww.scss').write_text('@import "generated/current/style";\n')
    available,why=composer.graphics_available()
    print('Previsualización aislada:',root)
    if not available:raise ValueError('No hay acceso gráfico: '+why)
    subprocess.run([str(Path.home()/'.local/bin/widgetctl'),'--config',str(root),'start'],check=True)
    return 0

def activate():
    from . import composer,config
    from .paths import EWW_DIR,ensure_runtime
    from .adapters import eww
    from .storage import atomic_text
    root=Path(EWW_DIR)
    # Validation is deliberately before any migration, stop or production file change.
    generation=composer.build();composer.validate_graphics(generation);verify_catalog()
    ensure_runtime()
    from .install import activate_files,restore_files
    snapshot=activate_files(generation)
    try:
        config.migrate()
        if not eww.restart_daemon():raise ValueError('El nuevo Eww no arrancó')
        from .runtime import sync
        if not sync():raise ValueError('No se pudo abrir el escritorio nuevo')
        from .install import reload_integrations
        reload_integrations()
        start_watcher()
        print('Sistema modular activado. Respaldo:',snapshot)
        return 0
    except BaseException:
        eww.stop();restore_files(snapshot);eww.start()
        raise

def rollback(snapshot=None):
    from .paths import STATE_DIR,EWW_DIR
    from .install import restore_files,reload_integrations
    from .adapters import eww
    root=STATE_DIR/'activation-backups'
    choices=sorted(p for p in root.glob('*') if (p/'snapshot.json').exists())
    selected=Path(snapshot) if snapshot else (choices[-1] if choices else None)
    if selected is None:raise ValueError('Todavía no hay una activación que revertir')
    from .paths import CONF
    current=Path(CONF)
    if current.exists():
        saved=STATE_DIR/('personalizaciones-antes-de-revertir-'+str(int(time.time()))+'.json')
        shutil.copy2(current,saved)
        print('Personalizaciones preservadas:',saved)
    eww.stop();restore_files(selected);reload_integrations()
    if Path(EWW_DIR)==(Path.home()/'.config/eww').resolve():
        subprocess.run([str(Path.home()/'.local/bin/eww-desktop')],check=True)
    else:eww.start()
    print('Restaurado:',selected)
    return 0
