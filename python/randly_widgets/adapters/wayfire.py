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
from ..paths import *
def wf_connect():
    path = os.environ.get("WAYFIRE_SOCKET")
    if not path:
        socks = [f for f in os.listdir(RUNTIME_BASE) if f.startswith("wayfire-") and f.endswith(".socket")]
        if not socks:
            return None
        path = os.path.join(RUNTIME_BASE, socks[0])
    sock = socket.socket(socket.AF_UNIX)
    sock.settimeout(2)
    try:
        sock.connect(path)
    except OSError:
        sock.close()
        return None
    return sock


def wf_send(sock, method, data=None):
    body = json.dumps({"method": method, "data": data or {}}).encode()
    sock.sendall(struct.pack("<I", len(body)) + body)


def wf_recv(sock):
    def exact(n,partial=False):
        data=b''
        while len(data)<n:
            try:chunk=sock.recv(n-len(data))
            except socket.timeout:
                if data or partial:raise ConnectionError('Incomplete Wayfire IPC frame')
                raise
            if not chunk:raise ConnectionError('Wayfire IPC closed')
            data+=chunk
        return data
    (n,)=struct.unpack('<I',exact(4))
    if n>8*1024*1024:raise ValueError('Wayfire IPC frame too large')
    return json.loads(exact(n,partial=True))


def wf_call(method, data=None):
    sock = wf_connect()
    if sock is None:
        return None
    try:
        wf_send(sock, method, data)
        return wf_recv(sock)
    except (OSError, ValueError, struct.error):
        return None
    finally:
        sock.close()


def first_output():
    outs = wf_call("window-rules/list-outputs")
    return outs[0] if isinstance(outs, list) and outs else None


def active_workspace_info():
    """Returns (workspace_number, (x, y))."""
    out = first_output()
    if not out:
        return 1, (0, 0)
    ws = out.get("workspace", {})
    x = int(ws.get("x", 0))
    y = int(ws.get("y", 0))
    grid_w = int(ws.get("grid_width", 3))
    num = y * grid_w + x + 1
    if out.get('wset-index')==2:num=10
    return num, (x, y)

def workspace_snapshot():
    """No guessed workspace when IPC is unavailable; include output and wset."""
    out=first_output()
    if not out or not isinstance(out.get('workspace'),dict):return None
    ws=out['workspace']
    if 'x' not in ws or 'y' not in ws:return None
    return (out.get('id'),out.get('wset-index'),ws['x'],ws['y'],ws.get('grid_width',3))


def is_global_widget(w):
    """Accept legacy labels without treating a list of workspace numbers as global."""
    target=str(w.get('opts',{}).get('workspace','Global')).strip().strip("\"'")
    return not target or any(part.strip().strip("\"'").lower() in ('todos','global','all','*') for part in target.split(','))


def widget_matches_workspace(w, current_num=None, current_coords=None):
    """True if widget w belongs to the active workspace or to all workspaces."""
    if current_num is None or current_coords is None:
        active_num, active_coords = active_workspace_info()
        if current_num is None:
            current_num = active_num
        if current_coords is None:
            current_coords = active_coords
    target = str(w.get("opts", {}).get("workspace", "Todos")).strip().strip("'\"")
    if is_global_widget(w):return True
    parts = [p.strip().strip("'\"").lower() for p in target.split(",")]
    cur_num_str = str(current_num)
    cur_name = f"workspace {current_num}".lower()
    for p in parts:
        if p in ("todos", "global", "all", "*"):
            return True
        if p == cur_num_str or p == cur_name or p == f"ws{cur_num_str}":
            return True
        if f"{current_coords[0]},{current_coords[1]}" in p.replace(" ", ""):
            return True
    return False


def on_home_workspace():
    """True/False, or None when Wayfire can't be asked (then keep things as they are)."""
    out = first_output()
    if not out:
        return None
    ws = out.get("workspace", {})
    return (ws.get("x"), ws.get("y")) == HOME_WS
