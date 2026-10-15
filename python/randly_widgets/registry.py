"""Widget definitions are data; discovery never imports third-party providers."""
import copy, json, re, shutil
from pathlib import Path
from .paths import EWW_DIR
WORKSPACE_CHOICES=['Todos']+[f'Workspace {i}' for i in range(1,11)]
from .transitions import KEYS as MOTION_KEYS,SIZE_KEYS
from .themes import SKINS,BACKGROUNDS,FX
ANIM_CHOICES=['global']+MOTION_KEYS
SKIN_CHOICES=['global']+SKINS
FX_CHOICES=['global']+FX
COMMON_OPTIONS=[('workspace','Escritorio','choice','Todos',WORKSPACE_CHOICES),('anim','Entrada','choice','global',ANIM_CHOICES),('anim_out','Salida','choice','global',ANIM_CHOICES),('skin','Estilo','choice','global',SKIN_CHOICES),('fx','Efecto','choice','global',FX_CHOICES),('background','Fondo','choice','global',['global']+BACKGROUNDS),('motion_mode','Tamaño dinámico','choice','global',['global']+SIZE_KEYS)]
IDENT=re.compile(r'^[a-z][a-z0-9_-]*$')
INSTANCE_IDENT=re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]*$')
class Registry:
    def __init__(self, root=None):
        self.root=Path(root or EWW_DIR)/'widgets'; self.modules={}; self.errors={}; self.missing={}
        for p in sorted(self.root.glob('*/manifest.json')):
            try:
                m=json.loads(p.read_text()); kind=m['id']
                if not IDENT.fullmatch(kind) or kind!=p.parent.name: raise ValueError('ID inválido o distinto de la carpeta')
                if m.get('version')!=1: raise ValueError('Versión de manifiesto no admitida')
                if kind in self.modules: raise ValueError('ID repetido')
                keys=set()
                for o in m.get('options',[]):
                    if not IDENT.fullmatch(o['key']) or o['key'] in keys: raise ValueError('Opción inválida o repetida')
                    keys.add(o['key'])
                for name in ('view.yuck','style.scss'):
                    if not (p.parent/name).is_file(): raise ValueError(f'Falta {name}')
                from .assets import validate_assets
                validate_assets(p.parent,m.get('assets',[]))
                provider=m.get('provider')
                if provider and provider!='provider.py': raise ValueError('El proveedor debe ser provider.py')
                m['path']=str(p.parent)
                missing=[x for x in m.get('requires',[]) if not shutil.which(x)]
                if missing: self.missing[kind]=missing
                self.modules[kind]=m
            except (ValueError,KeyError,TypeError,OSError) as exc: self.errors[p.parent.name]=str(exc)
        self.modules=dict(sorted(self.modules.items(),key=lambda x:x[1].get('order',999)))
    def schema(self):
        result={}
        for k,m in self.modules.items():
            if not m.get('enabled',True): continue
            meta=copy.deepcopy(m); meta["requires_missing"]=self.missing.get(k,[]); own=[]
            for o in m.get('options',[]):
                row=[o['key'],o['label'],o['type'],o.get('default','')]
                if 'choices' in o: row.append(o['choices'])
                own.append(tuple(row))
            own_keys={x[0] for x in own}; meta['options']=own+[o for o in COMMON_OPTIONS if o[0] not in own_keys]
            result[k]=meta
        return result
REGISTRY=Registry()
SCHEMA=REGISTRY.schema()
KINDS={k:m['name'] for k,m in SCHEMA.items()}
EDITOR_SKIN_KEYS=list(SKINS)
EDITOR_FX_KEYS=list(FX)
EDITOR_ANIM_KEYS=list(MOTION_KEYS)
