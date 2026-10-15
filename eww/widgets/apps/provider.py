import json, os, re, subprocess, sys, time, random
from randly_widgets.paths import RUNTIME, STATE_DIR
from randly_widgets.formatting import *

DEFAULT_APPS_LIST = [
    {"id": "term", "name": "Terminal", "icon": "", "cmd": "kitty &"},
    {"id": "web", "name": "Navegador", "icon": "󰈹", "cmd": "xdg-open https:// &"},
    {"id": "files", "name": "Archivos", "icon": "󰉋", "cmd": "thunar ~ &"},
    {"id": "discord", "name": "Legcord", "icon": "󰙯", "cmd": "legcord &"},
    {"id": "code", "name": "Editor", "icon": "󰨞", "cmd": "kitty -e nvim &"},
    {"id": "music", "name": "Música", "icon": "󰓇", "cmd": "spotify &"},
    {"id": "editor", "name": "Ajustes", "icon": "󰒓", "cmd": f"{os.path.expanduser('~/.local/bin/widgetctl')} editor &"},
]


def apps_data(opts):
    raw = (opts.get("apps") or "").strip()
    keys = [k.strip().lower() for k in raw.split(",") if k.strip()] if raw else []
    if not keys:
        return {"apps": DEFAULT_APPS_LIST}
    mapped = {a["id"]: a for a in DEFAULT_APPS_LIST}
    res_apps = []
    for k in keys:
        if k in mapped:
            res_apps.append(mapped[k])
        else:
            res_apps.append({"id": k, "name": k.capitalize(), "icon": "󰀻", "cmd": f"{k} &"})
    return {"apps": res_apps}



def collect(ctx):
    w, opts = ctx.widget, ctx.opts
    now_local = ctx.now
    runner_results, stamps = {w["id"]: ctx.output}, {w["id"]: ctx.stamp}
    procs = ctx.processes
    out = ctx.output or "…"
    return apps_data(opts)
