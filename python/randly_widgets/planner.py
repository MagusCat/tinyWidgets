#!/usr/bin/env python3
"""Habits + daily tasks helper for eww (window "planner").

  planner habits          stream habits.conf + history as JSON (deflisten)
  planner tasks           stream tasks.md as JSON (deflisten)
  planner habit N         toggle habit N for today
  planner task ID         toggle task ID ("d3" = daily item 3, "t5" = file line 5)
  planner edit habits|tasks   open the config file in the editor

Both streams re-emit when their file changes or the day rolls over.
"""
import datetime as dt
import json
import os
import re
import subprocess
import sys
import time
import unicodedata
from .storage import locked, write_json, atomic_text

from .paths import EWW_DIR
HABITS = os.path.join(EWW_DIR, "habits.conf")
TASKS = os.path.join(EWW_DIR, "tasks.md")
STATE = os.path.expanduser("~/.local/share/eww/planner.json")
if os.path.exists(os.path.join(EWW_DIR,".preview")):
    from .paths import STATE_DIR
    STATE = str(STATE_DIR / "planner.json")
DAYS = 7
EDITOR = os.environ.get("PLANNER_EDITOR", "kitty -e nvim")
CHECK = re.compile(r"^(\s*[-*]\s+\[)([ xX])(\]\s+)(.*)$")
DAILY_HEADERS = ("cada día", "cada dia", "diarias", "daily")


def today(offset=0):
    return (dt.date.today() - dt.timedelta(days=offset)).isoformat()


def clean(text):
    return "".join(c for c in text.replace("\\", "/")
                   if c.isprintable() or unicodedata.category(c) == "Co")


def load_state():
    try:
        with open(STATE) as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        data = {}
    data.setdefault("habits", {})   # {"2026-10-12": ["Agua", ...]}
    data.setdefault("daily", {})    # {"2026-10-12": ["Revisar correo", ...]}
    return data


def save_state(data):
    # Keep ~3 months of history.
    cutoff = today(92)
    for key in ("habits", "daily"):
        data[key] = {d: v for d, v in data[key].items() if d >= cutoff}
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    write_json(STATE,data)


# ── habits ──────────────────────────────────────────────────────────────────
def parse_habits():
    habits = []
    try:
        with open(HABITS, encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                icon, _, name = line.partition("|")
                if not name:
                    icon, name = "󰄬", icon
                habits.append({"icon": icon.strip(), "name": name.strip()})
    except OSError:
        pass
    return habits


def streak(history, name):
    n = 0
    # Today still open does not break the streak.
    start = 0 if name in history.get(today(), []) else 1
    for off in range(start, 400):
        if name in history.get(today(off), []):
            n += 1
        else:
            break
    return n


def render_habits():
    history = load_state()["habits"]
    items = []
    for i, h in enumerate(parse_habits()):
        week = [{"done": h["name"] in history.get(today(off), []), "today": off == 0}
                for off in range(DAYS - 1, -1, -1)]
        items.append({
            "i": i, "icon": clean(h["icon"]), "name": clean(h["name"]),
            "done": week[-1]["done"], "week": week, "streak": streak(history, h["name"]),
        })
    done = sum(1 for h in items if h["done"])
    return {"items": items, "done": done, "total": len(items),
            "pct": round(100 * done / len(items)) if items else 0}


def _toggle_habit(index):
    habits = parse_habits()
    if not 0 <= index < len(habits):
        return
    data = load_state()
    day = data["habits"].setdefault(today(), [])
    name = habits[index]["name"]
    day.remove(name) if name in day else day.append(name)
    save_state(data)


# ── tasks ───────────────────────────────────────────────────────────────────
def parse_tasks():
    """[(section, is_daily, line_no, checked, text)] from tasks.md."""
    out, section, daily = [], "", False
    try:
        with open(TASKS, encoding="utf-8", errors="replace") as fh:
            lines = fh.read().split("\n")
    except OSError:
        return [], []
    for n, line in enumerate(lines):
        if line.startswith("##"):
            section = line.lstrip("#").strip()
            daily = section.lower().startswith(DAILY_HEADERS)
            continue
        m = CHECK.match(line)
        if m:
            out.append((section, daily, n, m.group(2) != " ", m.group(4).strip()))
    return out, lines


def render_tasks():
    tasks, _ = parse_tasks()
    done_today = load_state()["daily"].get(today(), [])
    sections, order = {}, []
    for k, (section, daily, n, checked, text) in enumerate(tasks):
        if section not in sections:
            sections[section] = {"name": clean(section), "daily": daily, "items": []}
            order.append(section)
        done = text in done_today if daily else checked
        sections[section]["items"].append({
            "id": f"d{n}" if daily else f"t{n}", "text": clean(text), "done": done})
    groups = [sections[s] for s in order]
    for g in groups:
        g["done"] = sum(1 for t in g["items"] if t["done"])
        g["total"] = len(g["items"])
    total = sum(g["total"] for g in groups)
    done = sum(g["done"] for g in groups)
    return {"groups": groups, "done": done, "total": total,
            "pct": round(100 * done / total) if total else 0}


def _toggle_task(task_id):
    kind, num = task_id[:1], task_id[1:]
    if kind not in "dt" or not num.isdigit():
        return
    line_no = int(num)
    tasks, lines = parse_tasks()
    match = next((t for t in tasks if t[2] == line_no), None)
    if not match:
        return
    _, daily, _, _, text = match
    if daily:
        data = load_state()
        day = data["daily"].setdefault(today(), [])
        day.remove(text) if text in day else day.append(text)
        save_state(data)
    else:
        m = CHECK.match(lines[line_no])
        lines[line_no] = m.group(1) + (" " if m.group(2) != " " else "x") + m.group(3) + m.group(4)
        tmp = TASKS + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
        os.replace(tmp, TASKS)


# ── plumbing ────────────────────────────────────────────────────────────────
def mtime(path):
    try:
        return os.stat(path).st_mtime_ns
    except OSError:
        return 0


def stream(render, path):
    last = None
    while True:
        if os.getppid() == 1:
            return  # eww went away (reload/restart): don't linger as an orphan
        key = (mtime(path), mtime(STATE), today())
        if key != last:
            last = key
            print(json.dumps(render(), ensure_ascii=False), flush=True)
        time.sleep(1)


def toggle_habit(index):
    with locked(STATE+'.lock'):
        return _toggle_habit(index)

def toggle_task(task_id):
    with locked(STATE+'.lock'):
        with locked(TASKS+'.lock'):
            return _toggle_task(task_id)

def main(argv):
    cmd = argv[0] if argv else ""
    if cmd == "habits":
        stream(render_habits, HABITS)
    elif cmd == "tasks":
        stream(render_tasks, TASKS)
    elif cmd == "habit" and len(argv) > 1 and argv[1].isdigit():
        toggle_habit(int(argv[1]))
    elif cmd == "task" and len(argv) > 1:
        toggle_task(argv[1])
    elif cmd == "edit" and len(argv) > 1 and argv[1] in ("habits", "tasks"):
        path = HABITS if argv[1] == "habits" else TASKS
        subprocess.Popen(["setsid", "-f", "sh", "-c", f'{EDITOR} "{path}"'],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    elif cmd == "--once" and len(argv) > 1:
        print(json.dumps(render_habits() if argv[1] == "habits" else render_tasks(), ensure_ascii=False, indent=1))
    else:
        print(__doc__.strip(), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
