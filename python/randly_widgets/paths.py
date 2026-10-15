"""Paths are immutable per invocation; imports have no environment/process effects."""
import os, hashlib
from pathlib import Path
EWW_DIR = str(Path(os.environ.get('RANDLY_WIDGETS_CONFIG', '~/.config/eww')).expanduser().resolve())
PROFILE_KEY = hashlib.sha256(EWW_DIR.encode()).hexdigest()[:12]
SURFACE_PREFIX = 'rw-' + PROFILE_KEY + '-'
RUNTIME_BASE = Path(os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}'))
RUNTIME = str(RUNTIME_BASE / 'randly-widgets' / PROFILE_KEY)
STATE_DIR = Path(os.environ.get('XDG_STATE_HOME', str(Path.home()/'.local/state'))) / 'randly-widgets' / PROFILE_KEY
CONF = str(Path(EWW_DIR) / 'instances.json')
LEGACY_CONF = str(Path(EWW_DIR) / 'widgets.conf')
APPLIED = str(Path(RUNTIME) / 'eww-widgets-applied.json')
LOCK = str(Path(RUNTIME) / 'eww-widgets.lock')
DISABLED_FLAG = str(Path(EWW_DIR) / '.disabled')
POWER_STATE = str(Path(os.environ.get('XDG_STATE_HOME', str(Path.home()/'.local/state'))) / 'desktop-power/status.json')
PROFILES_DIR = str(Path(EWW_DIR) / 'profiles')
HOME_WS = (0,0)
ANCHORS = ('top-left','top-right','bottom-left','bottom-right','center')
IMAGE_EXT = ('.jpg','.jpeg','.png','.webp','.gif')
def ensure_runtime():
    Path(RUNTIME).mkdir(parents=True, exist_ok=True, mode=0o700)
    STATE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)

PALETTE_SCSS = str(Path(os.environ.get('XDG_STATE_HOME',str(Path.home()/'.local/state')))/'randly-widgets/palette.scss') if Path(EWW_DIR)==(Path.home()/'.config/eww').resolve() else str(Path(EWW_DIR)/'_colors.scss')
