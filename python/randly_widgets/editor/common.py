#!/usr/bin/env python3
"""Drag-and-drop editor for the eww desktop widgets (widgets.conf).

A transparent full-screen layer shows every widget as a box over the real one:
  drag            move (the real widget follows when you drop it)
  drag a dot      resize (photos: free width/height; others: width)
  right click     show / hide
  double click    settings of that widget (options from SCHEMA in scripts/widgets)
  + Widget        palette to add widgets or bring back hidden ones
  Supr            delete the hovered widget
  G               grid + snap on/off      [ ]  grid size
  Enter / Listo   keep changes            Esc  undo everything and exit
Positions are saved relative to the nearest screen corner.
"""
import json
import os
import re
import subprocess
import sys
import time

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GtkLayerShell", "0.1")
gi.require_version("Pango", "1.0")
from gi.repository import Gdk, GLib, Gtk, GtkLayerShell, Pango  # noqa: E402
import cairo  # noqa: E402

HERE = os.path.dirname(os.path.realpath(__file__))
from randly_widgets import api as W

PREFS = os.path.join(W.EWW_DIR, "editor.json")
EDITING_FLAG = os.path.join(W.RUNTIME, "eww-widgets-editing")
HANDLE = 14
MIN_PHOTO = 80
MIN_WIDGET = 120
GUIDE_SNAP = 8
LIVE_MS = 80  # live resize push rate; throttled to eliminate lag
EDGE_SNAP = 14
DEFAULT_SIZE = (320, 220)
DEFAULT_SIZES = {k: tuple(m.get("size", DEFAULT_SIZE)) for k,m in W.SCHEMA.items()}


def hex_rgb(value, fallback):
    m = re.fullmatch(r"#?([0-9a-fA-F]{6})", value or "")
    h = m.group(1) if m else fallback
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def palette():
    colors = {}
    try:
        with open(os.path.join(W.EWW_DIR, "_colors.scss")) as fh:
            for line in fh:
                m = re.match(r"\$(\w+):\s*(#[0-9a-fA-F]{6})", line.strip())
                if m:
                    colors[m.group(1)] = m.group(2)
    except OSError:
        pass
    return {
        "primary": hex_rgb(colors.get("primary"), "b5c4ff"),
        "tertiary": hex_rgb(colors.get("tertiary"), "e3badb"),
        "surface": hex_rgb(colors.get("surface_container"), "1e1f25"),
        "text": hex_rgb(colors.get("on_surface"), "e3e1e9"),
        "muted": hex_rgb(colors.get("outline"), "8f909a"),
        "error": hex_rgb(colors.get("error"), "ffb4ab"),
    }


def load_prefs():
    try:
        with open(PREFS) as fh:
            prefs = json.load(fh)
    except (OSError, ValueError):
        prefs = {}
    prefs.setdefault("grid", True)
    prefs.setdefault("step", 20)
    if prefs["step"] not in (5, 10, 20, 30):
        closest = min((5, 10, 20, 30), key=lambda x: abs(x - prefs["step"]))
        prefs["step"] = closest
    prefs.setdefault("sizes", {})
    return prefs


def save_prefs(prefs):
    from randly_widgets.storage import write_json
    write_json(PREFS, prefs)


WF_WS = os.path.expanduser("~/.local/bin/wf-ws")


def current_place():
    """(output id, wset, x, y) of the first output: the widgets' home is workspace 1 there."""
    out = W.first_output() or {}
    ws = out.get("workspace", {})
    return out.get("id"), out.get("wset-index"), ws.get("x"), ws.get("y")


def goto_place(place):
    _, wset, x, y = place
    if None in (wset, x, y):
        return
    n = 10 if wset == 2 else y * 3 + x + 1  # wf-ws numbering: 3x3 grid in wset 1, ws 10 = wset 2
    subprocess.run([WF_WS, "goto", str(n)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def minimize_visible_windows():
    """Minimize only the windows on the current workspace; return their ids to restore later.

    (wm-actions/toggle_showdesktop restores every window onto the current workspace.)
    """
    out = W.first_output()
    if not out:
        return []
    og = out["geometry"]
    ids = []
    for v in W.wf_call("window-rules/list-views") or []:
        if v.get("role") != "toplevel" or not v.get("mapped") or v.get("minimized"):
            continue
        if v.get("output-id") != out["id"] or v.get("wset-index") != out.get("wset-index"):
            continue
        g = v["geometry"]
        cx, cy = g["x"] + g["width"] / 2, g["y"] + g["height"] / 2
        if 0 <= cx < og["width"] and 0 <= cy < og["height"]:
            ids.append(v["id"])
    for vid in ids:
        W.wf_call("wm-actions/set-minimized", {"view_id": vid, "state": True})
    return ids


def layer_geometries_by_id():
    views = W.wf_call("window-rules/list-views") or []
    out = {}
    for v in views:
        appid = v.get("app-id", "")
        if appid.startswith(W.SURFACE_PREFIX):
            out[appid[len(W.SURFACE_PREFIX):]] = v.get("geometry", {})
        elif v.get("title", "").startswith(W.SURFACE_PREFIX):
            out[v.get("title", "")[len(W.SURFACE_PREFIX):]] = v.get("geometry", {})
    return out
