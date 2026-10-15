import re
from randly_widgets.formatting import *

def collect(ctx):
    w, opts = ctx.widget, ctx.opts
    now_local = ctx.now
    runner_results, stamps = {w["id"]: ctx.output}, {w["id"]: ctx.stamp}
    procs = ctx.processes
    out = ctx.output or "…"
    return {"text": wrap(clean_text(opts.get("text", "").replace("\\n", "\n")), opts.get("chars", 34))}
