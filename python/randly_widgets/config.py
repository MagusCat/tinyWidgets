"""Versioned instances, one-time legacy import and three-way concurrent edits."""
import copy, json, shlex
from pathlib import Path
from .paths import CONF, LEGACY_CONF, ANCHORS
from .registry import INSTANCE_IDENT
from .storage import locked, write_json
_MISSING=object()
_baseline=None
class ConfigError(ValueError): pass
class Conflict(ConfigError): pass

def validate(widgets):
    if not isinstance(widgets,list): raise ConfigError('widgets debe ser una lista')
    ids=set()
    for w in widgets:
        wid=w.get('id','')
        if not isinstance(wid,str) or not INSTANCE_IDENT.fullmatch(wid) or wid in ids: raise ConfigError(f'ID inválido/repetido: {wid}')
        ids.add(wid)
        if not isinstance(w.get('window'),str) or not isinstance(w.get('show'),bool): raise ConfigError(f'Tipo/visibilidad inválidos: {wid}')
        if w.get('anchor') not in ANCHORS: raise ConfigError(f'Anclaje inválido: {wid}')
        for key in ('x','y'):
            if not isinstance(w.get(key),int): raise ConfigError(f'Posición inválida: {wid}')
        if not isinstance(w.get('opts',{}),dict): raise ConfigError(f'Opciones inválidas: {wid}')
    return widgets

def parse_legacy(text):
    result=[]
    for n,raw in enumerate(text.splitlines(),1):
        if not raw.strip() or raw.lstrip().startswith('#'): continue
        try:
            wid,kind,show,anchor,x,y,*rest=shlex.split(raw)
            if show not in ('on','off'): raise ValueError('show debe ser on/off')
            opts={}
            for part in rest:
                k,sep,v=part.partition('=')
                if not sep: raise ValueError('opción sin =')
                opts[k]=v
            result.append(dict(id=wid,window=kind,show=show=='on',anchor=anchor,x=int(float(x)),y=int(float(y)),opts=opts))
        except ValueError as exc: raise ConfigError(f'widgets.conf:{n}: {exc}') from exc
    return validate(result)

def _read(path):
    if not path.exists(): return {'version':1,'revision':0,'widgets':[]}
    try: data=json.loads(path.read_text())
    except (OSError,ValueError) as exc: raise ConfigError(f'{path}: {exc}') from exc
    if data.get('version')!=1: raise ConfigError('Versión de configuración no admitida')
    validate(data.get('widgets')); return data

def migrate():
    path=Path(CONF)
    with locked(str(path)+'.lock'):
        if path.exists(): return False
        old=Path(LEGACY_CONF)
        widgets=parse_legacy(old.read_text()) if old.exists() else []
        write_json(path,dict(version=1,revision=1,widgets=widgets))
    return True

def load():
    global _baseline
    path=Path(CONF)
    if path.exists(): widgets=_read(path)['widgets']
    else:
        old=Path(LEGACY_CONF); widgets=parse_legacy(old.read_text()) if old.exists() else []
    _baseline=copy.deepcopy(widgets)
    return copy.deepcopy(widgets)

def _merge(base,desired,current,path=''):
    if desired==base: return _MISSING if current is _MISSING else copy.deepcopy(current)
    if current==base or desired==current: return _MISSING if desired is _MISSING else copy.deepcopy(desired)
    if all(isinstance(x,dict) for x in (base,desired,current)):
        result={}
        for key in base.keys()|desired.keys()|current.keys():
            v=_merge(base.get(key,_MISSING),desired.get(key,_MISSING),current.get(key,_MISSING),path+'.'+key)
            if v is not _MISSING: result[key]=v
        return result
    raise Conflict(f'Cambio simultáneo en {path}; vuelve a cargar antes de guardar')

def merge_widgets(base,desired,current):
    bm={w['id']:w for w in base}; dm={w['id']:w for w in desired}; cm={w['id']:w for w in current}
    merged={}
    for k in bm.keys()|dm.keys()|cm.keys():
        v=_merge(bm.get(k,_MISSING),dm.get(k,_MISSING),cm.get(k,_MISSING),k)
        if v is not _MISSING: merged[k]=v
    order=[w['id'] for w in current]+[w['id'] for w in desired if w['id'] not in cm]
    return [merged[k] for k in order if k in merged]

def save(widgets, base=None):
    global _baseline
    validate(widgets); path=Path(CONF)
    with locked(str(path)+'.lock'):
        current=_read(path)
        original=base if base is not None else _baseline
        if original is None: original=copy.deepcopy(current['widgets'])
        merged=merge_widgets(original,widgets,current['widgets']); validate(merged)
        write_json(path,dict(version=1,revision=current['revision']+1,widgets=merged))
    _baseline=copy.deepcopy(merged)
    return copy.deepcopy(merged)

def rollback(original,last_written):
    """Revert only fields this editor changed, preserving external edits."""
    path=Path(CONF)
    with locked(str(path)+'.lock'):
        current=_read(path)
        merged=merge_widgets(last_written,original,current['widgets'])
        write_json(path,dict(version=1,revision=current['revision']+1,widgets=merged))
    return merged

def find(widgets,wid): return next((w for w in widgets if w['id']==wid),None)

def photo_size(w):
    def num(v,d=360):
        try: return int(v)
        except (TypeError,ValueError): return d
    opts=w.get('opts',{}); size=opts.get('size',360)
    return num(opts.get('width',size)),num(opts.get('height',size))

def set_photo_size(w,width,height):
    w['opts'].pop('size',None);w['opts'].update(width=str(int(width)),height=str(int(height)))
