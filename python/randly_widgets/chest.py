#!/usr/bin/env python3
"""Chest launcher helper for eww.

  chest          stream chest.conf as JSON (deflisten); re-emits when the file changes
  chest --once   print the JSON once
  chest run N    run slot N's command detached and close the chest
"""
import json
import os
import subprocess
import sys
import time
import unicodedata

from .paths import EWW_DIR
CONF = os.path.join(EWW_DIR, "chest.conf")
COLS, ROWS = 9, 3


def parse(source=None):
    slots = []
    try:
        with open(source or CONF, encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                line = raw.rstrip("\r\n")
                if not line.strip() or line.lstrip().startswith("#"):
                    continue
                if line.strip() == "-":
                    slots.append(None)
                    continue
                parts = line.split("|", 2)  # command keeps any further '|'
                parts += [""] * (3 - len(parts))
                icon, label, cmd = (p.strip() for p in parts)
                slots.append({"icon": icon, "label": label, "cmd": cmd} if cmd or icon else None)
    except OSError:
        pass
    return slots[: COLS * ROWS]


def clean(text):
    # eww renders labels containing backslashes as blank; drop control chars too.
    # Keep private-use code points (Nerd Font glyphs): str.isprintable() is False for them.
    return "".join(c for c in text.replace("\\", "/")
                   if c.isprintable() or unicodedata.category(c) == "Co")


def data(slots=None):
    slots = parse() if slots is None else slots
    rows = []
    for r in range(ROWS):
        row = []
        for c in range(COLS):
            i = r * COLS + c
            s = slots[i] if i < len(slots) else None
            row.append({
                "i": i,
                "icon": clean(s["icon"]) if s else "",
                "label": clean(s.get("name",s.get("label",""))) if s else "",
                "used": bool(s and (s.get("cmd") or s.get("desktop_id"))),
            })
        rows.append(row)
    labels = [slot["label"] for row in rows for slot in row]
    return {"rows": rows, "labels": labels, "count": sum(1 for s in slots[:COLS*ROWS] if s)}


def render():
    return json.dumps(data(),ensure_ascii=False)


def run(index):
    slots = parse()
    from .state import update_event
    update_event("cofre", {"open":False,"hover":-1})
    if 0 <= index < len(slots) and slots[index] and slots[index]["cmd"]:
        subprocess.Popen(
            ["setsid", "-f", "sh", "-c", slots[index]["cmd"]],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            cwd=os.path.expanduser("~"), start_new_session=True,
        )


def stream():
    last_out = None
    last_mtime = None
    while True:
        try:
            mtime = os.stat(CONF).st_mtime_ns
        except OSError:
            mtime = 0
        if mtime != last_mtime:
            last_mtime = mtime
            out = render()
            if out != last_out:
                print(out, flush=True)
                last_out = out
        time.sleep(2)


if __name__ == "__main__":
    args = sys.argv[1:]
    if args[:1] == ["run"] and len(args) == 2 and args[1].lstrip("-").isdigit():
        run(int(args[1]))
    elif args[:1] == ["--once"]:
        print(render())
    else:
        try:
            stream()
        except (KeyboardInterrupt, BrokenPipeError):
            pass
