import re
from randly_widgets.formatting import *

def collect(ctx):
    w, opts = ctx.widget, ctx.opts
    now_local = ctx.now
    runner_results, stamps = {w["id"]: ctx.output}, {w["id"]: ctx.stamp}
    procs = ctx.processes
    out = ctx.output or "…"
    stamp = (stamps or {}).get(w["id"], "")
    terminal = opts.get("mono", "yes") == "yes"
    lines = ansi_lines(out)
    chars = int(opts.get("chars") or (80 if terminal else 34))
    if chars > 0:
        if terminal:
            lines = [line[:chars] for line in lines]          # cut, like a terminal
        else:
            # Normal text: wrap each line to the width (colors dropped).
            lines = [[(ch, {}) for ch in seg] for line in lines
                     for seg in wrap("".join(c for c, _ in line), chars).split("\n")]
    try:
        fixed = int(opts.get("lines") or 0)
    except ValueError:
        fixed = 0
    if fixed > 0:
        lines = lines[-fixed:] if opts.get("tail") == "yes" else lines[:fixed]
        lines += [[] for _ in range(fixed - len(lines))]
    height = {"Normal": "1.0", "Amplio": "1.25"}.get(opts.get("spacing"), "0.82")
    return {"markup": f'<span line_height="{height}">' + "\n".join(markup_line(l) for l in lines) + "</span>",
            "stamp": f"actualizado {stamp}" if stamp and opts.get("stamp") == "yes" else ""}
