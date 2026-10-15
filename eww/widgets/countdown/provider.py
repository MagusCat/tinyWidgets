import json, os, re, subprocess, sys, time, random
from randly_widgets.paths import RUNTIME, STATE_DIR
from randly_widgets.formatting import *

def countdown_text(opts, now):
    import datetime as dt
    try:
        target = dt.datetime.strptime(opts.get("date", "").strip(), "%Y-%m-%d %H:%M")
    except ValueError:
        try:
            target = dt.datetime.strptime(opts.get("date", "").strip(), "%Y-%m-%d")
        except ValueError:
            return {"text": "Fecha inválida", "sub": "usa AAAA-MM-DD HH:MM"}
    left = target - now
    sub = f"{target.day} {MONTHS_ES[target.month - 1]} {target.year}, {target:%H:%M}"
    if left.total_seconds() <= 0:
        return {"text": opts.get("done") or "¡Llegó!", "sub": sub}
    days, rest = divmod(int(left.total_seconds()), 86400)
    hours, rest = divmod(rest, 3600)
    return {"text": f"{days}d {hours}h {rest // 60}m" if days else f"{hours}h {rest // 60}m", "sub": sub}



def collect(ctx):
    w, opts = ctx.widget, ctx.opts
    now_local = ctx.now
    runner_results, stamps = {w["id"]: ctx.output}, {w["id"]: ctx.stamp}
    procs = ctx.processes
    out = ctx.output or "…"
    return countdown_text(opts, now_local)
