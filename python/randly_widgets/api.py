from .paths import *
from .registry import *
from .config import load, save as _save, find, photo_size, set_photo_size, rollback
from .policy import power_policy, is_disabled
from .appearance import *
from .adapters.wayfire import *
from .adapters.eww import eww, restart_daemon
from .runtime import *
from .profiles import *
from .actions import *
_last_editor_save = None
def save(widgets):
    global _last_editor_save
    result=_save(widgets)
    _last_editor_save=result
    return result

def ensure_current(kind=None):
    from . import composer
    from pathlib import Path
    active=Path(EWW_DIR)/'generated/current'
    if active.is_symlink():
        text=(active/'view.yuck').read_text()
        if kind is None or '(defwindow rw-'+kind+' ' in text:return True
    generation=composer.build()
    composer.validate_graphics(generation)
    composer.publish(generation)
    return reload()
