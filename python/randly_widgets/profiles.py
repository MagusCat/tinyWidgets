import fcntl
from pathlib import Path
from .storage import write_json
import json
import os
import random
import re
import shlex
import socket
import struct
import subprocess
import sys
import time
from .paths import *
from .config import load, save
from .appearance import *
def list_profiles():
    """Return list of available profiles with metadata."""
    profiles = []
    if not os.path.isdir(PROFILES_DIR):
        return profiles
    for fname in sorted(os.listdir(PROFILES_DIR)):
        if fname.endswith(".json"):
            path = os.path.join(PROFILES_DIR, fname)
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                    data["filename"] = fname
                    data["id"] = os.path.splitext(fname)[0]
                    profiles.append(data)
            except (OSError, ValueError):
                continue
    return profiles


def apply_profile(name,reconcile=True):
    """Load a profile by name and apply its widgets and animation."""
    fname = name if name.endswith(".json") else f"{name}.json"
    path = os.path.join(PROFILES_DIR, fname)
    if not os.path.exists(path):
        if os.path.isdir(PROFILES_DIR):
            for f in os.listdir(PROFILES_DIR):
                if f.lower() == fname.lower():
                    path = os.path.join(PROFILES_DIR, f)
                    break
    if not os.path.exists(path):
        return False
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return False
    if "widgets" in data and isinstance(data["widgets"], list):
        import copy
        load()
        save(copy.deepcopy(data["widgets"]))
    if "animation" in data and isinstance(data["animation"], dict):
        save_animation(**data["animation"])
    if reconcile:
        from .runtime import sync
        sync()
    return True


def save_current_as_profile(name, desc="Perfil personalizado", icon="󰏘"):
    """Save current widgets and animation configuration as a profile."""
    os.makedirs(PROFILES_DIR, exist_ok=True)
    if not name or Path(name).name != name or name in (".", ".."): raise ValueError("Nombre de perfil inválido")
    fname = f"{name}.json"
    path = os.path.join(PROFILES_DIR, fname)
    data = {
        "name": name,
        "desc": desc,
        "icon": icon,
        "animation": load_animation(),
        "widgets": load()
    }
    data["version"] = 1
    write_json(path,data)
    return True
