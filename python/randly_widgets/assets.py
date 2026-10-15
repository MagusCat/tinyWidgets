"""Bundled resources belong to one component; never resolve outside it."""
from pathlib import Path


def asset_path(component, name):
    if not isinstance(name, str) or not name or '\\' in name:
        raise ValueError('Nombre de asset inválido')
    relative = Path(name)
    if relative.is_absolute() or any(part in ('.', '..') for part in relative.parts):
        raise ValueError('El asset debe ser relativo a assets/ del componente')
    component = Path(component).resolve()
    folder = component/'assets'
    path = folder/relative
    if not folder.resolve().is_relative_to(component) or not path.resolve().is_relative_to(folder.resolve()):
        raise ValueError('El asset escapa del componente')
    if not path.is_file():
        raise ValueError(f'Falta asset: {name}')
    return path


def validate_assets(component, names):
    if not isinstance(names, list) or any(not isinstance(n, str) for n in names):
        raise ValueError('assets debe ser una lista de rutas relativas')
    if len(set(names)) != len(names):
        raise ValueError('Asset duplicado')
    for name in names:
        asset_path(component, name)
