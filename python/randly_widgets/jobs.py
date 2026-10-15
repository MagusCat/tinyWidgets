"""Bounded, cancelable jobs; one slow custom provider cannot block the stream."""
import copy,json,multiprocessing,os,signal,subprocess,time
from datetime import datetime
from pathlib import Path
from .paths import RUNTIME
from .providers import Context,load_provider
from .registry import REGISTRY
from .storage import write_json

def command_output(command,timeout=15):
    """Bounded output; shell and descendants belong to this worker's process group."""
    with __import__('tempfile').TemporaryFile() as f:
        def limit_output():
            import resource
            resource.setrlimit(resource.RLIMIT_FSIZE,(262144,262144))
        p=subprocess.Popen(['sh','-c',command],stdout=f,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,preexec_fn=limit_output)
        try:p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            p.kill();p.wait();raise TimeoutError('Comando: tiempo agotado')
        f.seek(0);return f.read(50000).decode(errors='replace').strip('\r\n')

def run_job(connection,kind,ctx,registry):
    try:
        os.setsid()
        with open(os.devnull,'w') as null:
            os.dup2(null.fileno(),1);os.dup2(null.fileno(),2)
        command=ctx.opts.get('command','').strip()
        if command:
            ctx.output=command_output(command)
            ctx.stamp=time.strftime('%H:%M:%S')
        data=load_provider(kind,ctx.widget['id'],registry).collect(ctx)
        if not isinstance(data,dict): raise ValueError('collect(ctx) debe devolver un objeto JSON')
        if len(json.dumps(data,ensure_ascii=False,allow_nan=False).encode())>262144: raise ValueError('Datos del widget demasiado grandes')
        connection.send((True,data,ctx.state,ctx.output,ctx.stamp))
    except BaseException as exc:
        # Do not include command contents or source data in shared diagnostics.
        try:connection.send((False,{'error':type(exc).__name__+': '+str(exc)[:160]},ctx.state,'',''))
        except (OSError,BrokenPipeError):pass
    finally:connection.close()

class Scheduler:
    def __init__(self,registry=None,limit=4):
        self.registry=registry or REGISTRY;self.limit=limit;self.jobs={};self.results={};self.states={};self.due={};self.signatures={};self.modules={};self.stamps={};self.outputs={}
    def terminate(self,wid):
        job=self.jobs.pop(wid,None)
        if not job:return
        process,connection,_,_=job
        try:
            # Child called setsid; never signal the parent's process group.
            if process.is_alive() and os.getpgid(process.pid)==process.pid:os.killpg(process.pid,signal.SIGKILL)
            elif process.is_alive():process.kill()
        except (OSError,ProcessLookupError):pass
        process.join(timeout=.3);connection.close();process.close()
    def close(self):
        for wid in list(self.jobs):self.terminate(wid)
    def collect_finished(self,now):
        for wid,(p,c,started,signature) in list(self.jobs.items()):
            if c.poll():
                try:
                    ok,data,state,out,stamp=c.recv()
                    if signature==self.signatures.get(wid):
                        self.results[wid]=data;self.states[wid]=state
                        self.outputs[wid]=out;self.stamps[wid]=stamp
                except (EOFError,OSError):self.results[wid]={'error':'El proveedor terminó sin datos'}
                self.terminate(wid)
            elif now-started>20:
                self.results[wid]={'error':'Tiempo agotado (20 s)'};self.terminate(wid)
            elif not p.is_alive():
                self.results[wid]={'error':'El proveedor terminó sin datos'};self.terminate(wid)
    def tick(self,widgets,options,now=None,paused=()):
        now=time.monotonic() if now is None else now
        active={w['id']:w for w in widgets}
        self.collect_finished(now)
        for wid in list(self.jobs):
            if wid not in active:self.terminate(wid)
        for wid in set(self.results)-set(active):
            self.results.pop(wid,None);self.states.pop(wid,None);self.due.pop(wid,None);self.signatures.pop(wid,None);self.modules.pop(wid,None);self.outputs.pop(wid,None);self.stamps.pop(wid,None)
        for wid,w in active.items():
            kind=w['window'];m=self.registry.modules.get(kind,{})
            if not m.get('provider') or not m.get('enabled',True):continue
            if kind in self.registry.missing:
                self.results[wid]={'error':'Falta: '+', '.join(self.registry.missing[kind])};continue
            try:opts=options(w)
            except Exception:
                self.results[wid]={'error':'Opciones inválidas'};continue
            cosmetic={'namespace','workspace','anim','anim_out','skin','skin_class','fx','fx_class','background','anim_class','is_editing','power_style','motion_mode'}
            signature=json.dumps([kind,{k:v for k,v in opts.items() if k not in cosmetic}],sort_keys=True)
            changed=signature!=self.signatures.get(wid)
            if changed:
                self.terminate(wid);self.signatures[wid]=signature;self.due[wid]=0;self.modules.pop(wid,None)
            trigger=Path(RUNTIME)/f'eww-widgets-rerun-{wid}'
            event=Path(RUNTIME)/f'event-{wid}.json'
            event_version=event.stat().st_mtime_ns if event.exists() else 0
            prev_event=self.states.setdefault(wid,{}).get('_event',0)
            forced=trigger.exists() or event_version!=prev_event
            if wid in paused and not forced:continue
            mode=opts.get('run','Cada N segundos')
            if mode=='Solo al hacer click' and not forced:
                if changed:self.results[wid]={'markup':'Click para ejecutar','text':'Click para ejecutar'}
                continue
            if mode=='Solo una vez' and wid in self.results and not changed and not forced:continue
            if wid in self.jobs or (now<self.due.get(wid,0) and not forced):continue
            if m.get('execution','worker')!='inline' and len(self.jobs)>=self.limit:continue
            try:interval=max(.2,float(opts.get('interval') or m.get('interval',1)))
            except (ValueError,TypeError):interval=5
            self.due[wid]=now+interval;trigger.unlink(missing_ok=True)
            self.states[wid]['_event']=event_version
            ctx=Context(copy.deepcopy(w),copy.deepcopy(opts),state=copy.deepcopy(self.states.get(wid,{})),output=self.outputs.get(wid,''),stamp=self.stamps.get(wid,''))
            if m.get('execution','worker')=='inline':
                try:
                    module=self.modules.get(wid)
                    if module is None:module=load_provider(kind,wid,self.registry);self.modules[wid]=module
                    data=module.collect(ctx)
                    if not isinstance(data,dict):raise ValueError('collect debe devolver un objeto JSON')
                    json.dumps(data)
                    self.results[wid]=data;self.states[wid]=ctx.state
                except Exception as exc:self.results[wid]={'error':type(exc).__name__+': '+str(exc)[:160]}
            else:
                context=multiprocessing.get_context('fork');parent,child=context.Pipe(duplex=False)
                p=context.Process(target=run_job,args=(child,kind,ctx,self.registry));p.start();child.close()
                self.jobs[wid]=(p,parent,now,signature)
        return {wid:{**self.registry.modules.get(w['window'],{}).get('initial',{}),'error':'',**self.results.get(wid,{})} for wid,w in active.items()}
