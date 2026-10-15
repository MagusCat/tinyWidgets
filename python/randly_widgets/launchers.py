"""Instance-owned launch targets. Desktop entries launch through Gio, never shell Exec parsing."""
import json
import subprocess
from pathlib import Path


def parse(raw):
    if raw in (None, ''):
        return []
    if isinstance(raw,str):
        try:raw=json.loads(raw)
        except ValueError as exc:raise ValueError('La lista de accesos no es JSON válido') from exc
    if not isinstance(raw,list) or len(raw)>100:
        raise ValueError('Usa una lista de hasta 100 accesos')
    result=[]
    for entry in raw:
        if entry is None:
            result.append(None);continue
        if not isinstance(entry,dict):raise ValueError('Acceso inválido')
        item={key:entry.get(key,'') for key in ('name','icon','desktop_id','cmd')}
        if any(not isinstance(v,str) for v in item.values()):raise ValueError('Los campos de un acceso deben ser texto')
        desktop=item['desktop_id']
        if desktop and ('/' in desktop or '\\' in desktop or '..' in desktop or not desktop.endswith('.desktop')):
            raise ValueError('ID de aplicación inválido')
        if desktop and item['cmd']:raise ValueError('Elige aplicación o comando, no ambos')
        if not desktop and not item['cmd'].strip():raise ValueError('El acceso necesita una aplicación o comando')
        item['name']=item['name'].strip() or desktop.removesuffix('.desktop') or item['cmd']
        item['icon']=item['icon'] or '󰀻'
        result.append(item)
    return result


def entries(widget):
    opts=widget.get('opts',{})
    if 'launchers' in opts:return parse(opts['launchers'])
    # Preserve only explicitly saved legacy entries; no built-in favorites.
    raw=opts.get('apps','')
    if isinstance(raw,str) and raw.strip() and not raw.lstrip().startswith('['):
        return parse([{'name':name.strip(),'cmd':name.strip()} for name in raw.split(',') if name.strip()])
    return parse(raw)


def app_data(widget):
    apps=[{'id':i,'name':entry['name'],'icon':entry['icon']} for i,entry in enumerate(entries(widget)) if entry]
    return {'apps':apps,'empty':not apps}


def desktop_class():
    import gi
    try:
        gi.require_version('GioUnix','2.0')
        from gi.repository import GioUnix
        return GioUnix.DesktopAppInfo
    except (ImportError,ValueError):
        from gi.repository import Gio
        return Gio.DesktopAppInfo


def launch(widget,index):
    targets=entries(widget)
    if not 0<=index<len(targets) or targets[index] is None:raise ValueError('Acceso inexistente')
    target=targets[index]
    if target['desktop_id']:
        app=desktop_class().new(target['desktop_id'])
        if app is None:raise ValueError('La aplicación ya no está instalada: '+target['desktop_id'])
        app.launch([],None)
    else:
        subprocess.Popen(['sh','-c',target['cmd']],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,cwd=str(Path.home()),start_new_session=True)


def migrate_chest(widgets,source):
    """Import existing personal slots once; new instances remain empty."""
    from .chest import parse as legacy_parse
    source=Path(source)
    if not source.is_file():return False
    slots=legacy_parse(source)
    if not any(slots):return False
    changed=False
    for widget in widgets:
        if widget['window']=='chest' and 'launchers' not in widget.get('opts',{}):
            widget.setdefault('opts',{})['launchers']=json.dumps([{'icon':s['icon'],'name':s['label'],'cmd':s['cmd']} if s and s['cmd'] else None for s in slots],ensure_ascii=False)
            changed=True
    return changed
