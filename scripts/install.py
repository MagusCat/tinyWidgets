"""Install user-owned artifacts; back up replaced files, preserve instance data."""
import json, os, shutil, subprocess, sys, tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def install(home):
    home = Path(home)
    for name in ('randly-widget-manager', 'librandly_widget_theme.so'):
        if not (ROOT/'target/release'/name).is_file():
            raise RuntimeError('Falta compilación de producción: ejecuta scripts/build.sh')
    config = home / '.config/eww'
    if (config/'eww.yuck').exists() and not (config/'.modular-active').exists():
        raise RuntimeError('Configuración Eww ajena detectada; migrar manualmente antes de instalar.')
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    backup = home / '.local/state/tinyWidgets/install-backups' / stamp
    changed = []
    def put(source, dest, replace=True):
        source, dest = Path(source), Path(dest)
        if (dest.exists() or dest.is_symlink()) and not replace:
            return
        if dest.exists() or dest.is_symlink():
            saved = backup / dest.relative_to(home)
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dest, saved)
        dest.parent.mkdir(parents=True, exist_ok=True)
        # Replace atomically rather than following a destination symlink.
        fd, temporary = tempfile.mkstemp(dir=dest.parent, prefix='.tinywidgets-')
        os.close(fd)
        try:
            shutil.copy2(source, temporary)
            os.replace(temporary, dest)
        finally:
            Path(temporary).unlink(missing_ok=True)
        changed.append(str(dest.relative_to(home)))
    for folder in ('python/randly_widgets', 'eww/widgets', 'eww/shared'):
        base = ROOT/folder
        dest = home/'.local/lib/randly_widgets' if folder.startswith('python/') else config/folder.split('/',1)[1]
        for source in sorted(base.rglob('*')):
            if source.is_file() and not {'.git', '__pycache__'}.intersection(source.parts) and source.suffix != '.pyc':
                put(source, dest/source.relative_to(base))
    for name in ('instances.json', 'animation.json', 'style.json', '_colors.scss'):
        put(ROOT/'eww'/name, config/name, replace=False)
    # Existing generations stay active until an explicit widgetctl reload.
    fresh = not (config/'eww.yuck').exists()
    if fresh:
        (config/'eww.yuck').write_text('(include "generated/current/view.yuck")\n')
        (config/'eww.scss').write_text('@import "generated/current/style";\n')
        (config/'.modular-active').write_text('1\n')
    for name in ('randly-widget-manager', 'librandly_widget_theme.so'):
        put(ROOT/'target/release'/name, home/'.local/lib/randly-widgets'/name)
    put(ROOT/'bin/widgetctl', home/'.local/bin/widgetctl')
    palette = home/'.local/state/randly-widgets/palette.scss'
    put(config/'_colors.scss', palette, replace=False)
    if fresh:
        env = {**os.environ, 'HOME':str(home), 'RANDLY_WIDGETS_CONFIG':str(config), 'PYTHONPATH':str(home/'.local/lib')}
        subprocess.run([sys.executable, '-c', 'from randly_widgets.composer import build,publish; publish(build())'], env=env, check=True)
    backup.mkdir(parents=True, exist_ok=True)
    (backup/'manifest.json').write_text(json.dumps({'installed':changed}, indent=2)+'\n')
    print(f'Instalado. Respaldo: {backup}')
    print('En tu sesión Wayfire: ~/.local/bin/widgetctl reload')
    return backup

if __name__ == '__main__':
    try:
        install(Path.home())
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f'Instalación: {exc}')
