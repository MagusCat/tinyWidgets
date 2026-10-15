import fcntl
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
from .config import *
from .registry import KINDS
from .appearance import *
from .adapters.wayfire import *
from .runtime import sync

def notify(title, body=""):
    pass

def cmd_toggle_all():
    """Toggle all desktop widgets globally for resource saving."""
    if os.path.isfile(DISABLED_FLAG):
        try:
            os.remove(DISABLED_FLAG)
        except OSError:
            pass
        sync()
        subprocess.run(["notify-send", "-a", "eww", "-i", "preferences-desktop-theme",
                        "Widgets activados", "Los widgets de escritorio están visibles"],
                       check=False)
    else:
        with open(DISABLED_FLAG, "w") as fh:
            fh.write("1\n")
        sync()
        subprocess.run(["notify-send", "-a", "eww", "-i", "preferences-desktop-theme",
                        "Widgets desactivados", "Ahorro de recursos activo"],
                       check=False)


def fuzzel(options, prompt, free=False):
    cmd = ["fuzzel", "--dmenu", "--prompt", prompt, "--width", "40",
           "--lines", str(max(1, min(len(options), 14)))]
    if not free:
        cmd.append("--only-match")
    res = subprocess.run(cmd, input="\n".join(options), capture_output=True, text=True)
    return res.stdout.strip() if res.returncode == 0 else None


def label(w):
    name = KINDS.get(w["window"], w["window"])
    extra = " · {}×{}".format(*photo_size(w)) if w["window"] in ("photo", "image") else ""
    return f"{'󰈈' if w['show'] else '󰈉'}  {w['id']}  —  {name}{extra}"


def cmd_move(wid):
    widgets = load()
    w = find(widgets, wid)
    if not w:
        return
    cur_num, cur_coords = active_workspace_info()
    if not widget_matches_workspace(w, cur_num, cur_coords):
        target = w.get("opts", {}).get("workspace", "Todos")
        notify(f"Ve a {target}", f"Este widget está configurado para {target}")
        return
    hint = "Dibuja el rectángulo de la foto" if w["window"] in ("photo", "image") \
        else "Haz click (o arrastra) donde va la esquina superior izquierda"
    notify(f"Mover {wid}", hint + " · Esc cancela")
    res = subprocess.run(["slurp", "-f", "%x %y %w %h", "-b", "#00000055", "-c", "#b5c4ffff"],
                         capture_output=True, text=True)
    if res.returncode != 0 or not res.stdout.strip():
        return
    x, y, wdt, hgt = (int(v) for v in res.stdout.split())
    out = first_output()
    if out:  # slurp is global; eww positions are relative to monitor 0
        x -= int(out["geometry"]["x"])
        y -= int(out["geometry"]["y"])
    w.update(anchor="top-left", x=max(0, x), y=max(0, y), show=True)
    if w["window"] in ("photo", "image") and wdt >= 80 and hgt >= 80:
        set_photo_size(w, wdt, hgt)
    save(widgets)
    sync()


def cmd_toggle(wid):
    widgets = load()
    w = find(widgets, wid)
    if w:
        w["show"] = not w["show"]
        save(widgets)
        sync()


def cmd_resize(wid):
    widgets = load()
    w = find(widgets, wid)
    if not w:
        return
    size = fuzzel(["300x300", "360x240", "240x360", "480x320", "320x480", "600x400", "400x600"],
                  f"Tamaño de {wid} (ANCHOxALTO, o escribe uno): ", free=True)
    m = re.fullmatch(r"\s*(\d+)\s*[xX×]\s*(\d+)\s*", size or "")
    if m and all(60 <= int(v) <= 3000 for v in m.groups()):
        set_photo_size(w, *m.groups())
        save(widgets)
        sync()


def pick_folder(current=None):
    pics = os.path.expanduser("~/Imágenes")
    dirs = []
    if os.path.isdir(pics):
        for root, subdirs, _ in os.walk(pics):
            dirs.append(root)
            subdirs[:] = [d for d in subdirs if not d.startswith(".")]
            if len(dirs) > 200:
                break
    home = os.path.expanduser("~")
    shown = [d.replace(home, "~", 1) for d in dirs]
    if current:
        shown.insert(0, current)
    choice = fuzzel(shown, "Carpeta de imágenes (o escribe ruta): ", free=True)
    return choice or None


def cmd_add_photo():
    widgets = load()
    n = 1
    while find(widgets, f"foto{n}"):
        n += 1
    folder = pick_folder("~/Imágenes/widget")
    if not folder:
        return
    w = {"id": f"foto{n}", "window": "photo", "show": True, "anchor": "top-left",
         "x": 200, "y": 200, "opts": {"width": "360", "height": "360", "dir": folder, "interval": "30"}}
    widgets.append(w)
    save(widgets)
    sync()
    cmd_move(w["id"])


def cmd_remove(wid):
    widgets = [w for w in load() if w["id"] != wid]
    save(widgets)
    sync()


def cmd_menu():
    widgets = load()
    entries = {label(w): w["id"] for w in widgets}
    extra = ["󰐕  Agregar foto", "󰏫  Editar instancias", "󰩬  Editor visual (arrastrar)"]
    choice = fuzzel(list(entries) + extra, "Widgets: ")
    if not choice:
        return
    if choice == extra[0]:
        cmd_add_photo()
        return
    if choice == extra[2]:
        subprocess.Popen(["setsid", "-f", os.path.join(EWW_DIR, "scripts", "widget-editor")])
        return
    if choice == extra[1]:
        subprocess.Popen(["setsid", "-f", "kitty", "-e", "nvim", CONF])
        return
    w = find(widgets, entries[choice])
    actions = ["󰆾  Mover", "󰈉  Ocultar" if w["show"] else "󰈈  Mostrar"]
    if w["window"] == "photo":
        actions += ["󰩨  Tamaño", "󰉋  Cambiar carpeta", "󰆴  Eliminar"]
    act = fuzzel(actions, f"{w['id']}: ")
    if not act:
        return
    if "Mover" in act:
        cmd_move(w["id"])
    elif "Ocultar" in act or "Mostrar" in act:
        cmd_toggle(w["id"])
    elif "Tamaño" in act:
        cmd_resize(w["id"])
    elif "Cambiar carpeta" in act:
        folder = pick_folder(w["opts"].get("dir"))
        if folder:
            w["opts"]["dir"] = folder
            save(widgets)
    elif "Eliminar" in act:
        cmd_remove(w["id"])


def cmd_run(wid):
    w = find(load(), wid)
    if w and w['window']=='button':
        from .launchers import entries,launch
        if entries(w):launch(w,0);return
    cmd = w and options(w).get("command", "").strip()
    if cmd:
        subprocess.Popen(["setsid", "-f", "sh", "-c", cmd], stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         cwd=os.path.expanduser("~"), start_new_session=True)
