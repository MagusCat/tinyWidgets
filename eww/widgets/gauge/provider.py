import re
from randly_widgets.formatting import *

def collect(ctx):
    w, opts = ctx.widget, ctx.opts
    now_local = ctx.now
    runner_results, stamps = {w["id"]: ctx.output}, {w["id"]: ctx.stamp}
    procs = ctx.processes
    out = ctx.output or "…"
    m = re.search(r"-?\d+(?:[.,]\d+)?", out)
    value = float(m.group().replace(",", ".")) if m else 0.0
    try:
        top = float(opts.get("max") or 100) or 100
    except ValueError:
        top = 100
    shown = int(value) if value == int(value) else round(value, 1)
    return {"text": f"{shown}{opts.get('unit', '')}" if m else (out or "…"),
            "pct": max(0, min(100, round(100 * value / top, 1)))}
