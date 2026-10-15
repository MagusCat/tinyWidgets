"""Providers receive instance-local context and return JSON-compatible mappings."""
import importlib.util,sys
from dataclasses import dataclass,field
from datetime import datetime
from pathlib import Path
from .registry import REGISTRY

@dataclass
class Context:
    widget: dict
    opts: dict
    now: datetime = field(default_factory=lambda:datetime.now().astimezone())
    state: dict = field(default_factory=dict)
    output: str = ''
    stamp: str = ''
    processes: list = field(default_factory=list)

def load_provider(kind,instance,registry=None):
    m=(registry or REGISTRY).modules[kind]
    path=Path(m['path'])/m['provider']
    name='rw_provider_'+str(abs(hash((str(path),instance))))
    spec=importlib.util.spec_from_file_location(name,path); module=importlib.util.module_from_spec(spec)
    sys.modules[name]=module; spec.loader.exec_module(module)
    return module
