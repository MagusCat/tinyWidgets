import json, os, re, subprocess, sys, time, random
from randly_widgets.paths import RUNTIME, STATE_DIR
from randly_widgets.formatting import *
from randly_widgets.adapters.wayfire import wf_call
from randly_widgets.appearance import options
def notify(title, body=""):
    pass

INTERPRETERS = {"python", "python3", "node", "bash", "sh", "perl", "ruby", "lua", "java"}


PROTECTED = {"wayfire", "systemd", "dbus-broker", "dbus-daemon", "Xwayland"}


class Procs:
    """Current CPU% / memory of the user's processes, from /proc deltas."""

    def __init__(self):
        self.prev, self.prev_t, self.rows, self.next = {}, None, [], 0
        self.ticks = os.sysconf("SC_CLK_TCK")
        self.page = os.sysconf("SC_PAGE_SIZE")
        self.ncpu = os.cpu_count() or 1

    @staticmethod
    def name_of(pid, comm):
        if comm not in INTERPRETERS:
            return comm
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as fh:
                argv = [a.decode(errors="replace") for a in fh.read().split(b"\0") if a]
        except OSError:
            return comm
        script = next((a for a in argv[1:] if not a.startswith("-")), "")
        return os.path.basename(script) or comm

    def collect(self):
        uid, me = os.getuid(), os.getpid()
        window_pids = {v.get("pid") for v in (wf_call("window-rules/list-views") or [])
                       if v.get("role") == "toplevel"}
        now = time.monotonic()
        rows, cur = [], {}
        for entry in os.listdir("/proc"):
            if not entry.isdigit():
                continue
            pid = int(entry)
            try:
                if os.stat(f"/proc/{pid}").st_uid != uid or pid == me:
                    continue
                with open(f"/proc/{pid}/stat") as fh:
                    stat = fh.read()
                with open(f"/proc/{pid}/cmdline", "rb") as fh:
                    cmdline = fh.read().replace(b"\0", b" ").decode(errors="replace")
            except OSError:
                continue
            if not cmdline.strip() or "/.config/eww/scripts/" in cmdline or "/.local/bin/wf-" in cmdline or "/.local/bin/widgetctl" in cmdline or "/.local/bin/desktop-power" in cmdline:
                continue  # kernel-ish threads / the desktop's own helpers
            comm = stat[stat.index("(") + 1:stat.rindex(")")]
            fields = stat[stat.rindex(")") + 2:].split()
            state, used, rss = fields[0], int(fields[11]) + int(fields[12]), int(fields[21]) * self.page
            cur[pid] = used
            cpu = 0.0
            if self.prev_t is not None and pid in self.prev:
                cpu = 100 * (used - self.prev[pid]) / self.ticks / max(0.001, now - self.prev_t)
            rows.append({"pid": pid, "comm": comm, "name": clean_text(self.name_of(pid, comm), 40),
                         "cpu": round(cpu, 1), "mem": rss,
                         "paused": state == "T", "window": pid in window_pids})
        self.prev, self.prev_t, self.rows = cur, now, rows
        return rows

    def poll(self, widgets, now):
        wanted = [w for w in widgets if w["window"] == "procs" and w["show"]]
        if not wanted:
            return self.rows
        dirty = os.path.join(RUNTIME, "eww-widgets-procs-dirty")
        try:
            every = min(max(1, int(options(w).get("interval") or 3)) for w in wanted)
        except ValueError:
            every = 3
        if now >= self.next or os.path.exists(dirty):
            try:
                os.remove(dirty)
            except OSError:
                pass
            self.next = now + every
            self.collect()
        return self.rows


def human_mem(n):
    return f"{n / 1073741824:.1f} G" if n >= 1073741824 else f"{n / 1048576:.0f} M"


def procs_view(opts, rows):
    which = opts.get("which", "")
    hide = set(opts.get("hide", "").split())
    flt = opts.get("filter", "").strip().lower()
    if opts.get("group", "yes") == "yes":
        groups = {}
        for r in rows:
            g = groups.setdefault(r["name"], {"pids": [], "name": r["name"], "comm": r["comm"], "cpu": 0.0,
                                               "mem": 0, "paused": True, "window": False})
            g["pids"].append(r["pid"])
            g["cpu"] += r["cpu"]
            g["mem"] += r["mem"]
            g["paused"] = g["paused"] and r["paused"]
            g["window"] = g["window"] or r["window"]
        rows = list(groups.values())
    else:
        rows = [dict(r, pids=[r["pid"]]) for r in rows]
    out = []
    for r in rows:
        # /proc comm is cut at 15 chars: compare hidden names the same way.
        if {r["name"], r["comm"], r["name"][:15], r["comm"][:15]} & (hide | {h[:15] for h in hide}):
            continue
        if which.startswith("En segundo plano") and r["window"]:
            continue
        if which.startswith("Con ventana") and not r["window"]:
            continue
        if flt and flt not in r["name"].lower() and flt not in r["comm"].lower():
            continue
        out.append(r)
    key = {"Memoria": lambda r: -r["mem"], "Nombre": lambda r: r["name"].lower()}.get(
        opts.get("sort"), lambda r: (-r["cpu"], -r["mem"]))
    out.sort(key=key)
    try:
        count = max(1, int(opts.get("count") or 8))
    except ValueError:
        count = 8
    chars = int(opts.get("chars", 30))
    return {"rows": [{"pid": ",".join(map(str, r["pids"])),
                      "name": r["name"][:max(6, chars - 22)] + (f" ×{len(r['pids'])}" if len(r["pids"]) > 1 else ""),
                      "cpu": f"{r['cpu']:.0f}%", "mem": human_mem(r["mem"]), "paused": r["paused"],
                      "window": r["window"]} for r in out[:count]],
            "total": len(out)}


def cmd_proc(action, pid_text):
    """pause (toggle SIGSTOP/SIGCONT), term (SIGTERM) or kill (SIGKILL) one or more of your PIDs."""
    import signal
    pids = [p for p in pid_text.split(",") if p.isdigit()]
    procs, names = [], set()
    for p in pids:
        pid = int(p)
        try:
            if os.stat(f"/proc/{pid}").st_uid != os.getuid():
                continue
            with open(f"/proc/{pid}/comm") as fh:
                comm = fh.read().strip()
            with open(f"/proc/{pid}/stat") as fh:
                stat = fh.read()
        except OSError:
            continue  # already gone
        if comm in PROTECTED:
            notify("Protegido", f"{comm} es parte de la sesión; no se detiene desde aquí")
            return
        procs.append((pid, stat[stat.rindex(")") + 2:].split()[0] == "T"))
        names.add(comm)
    if not procs:
        notify("No se pudo", "El proceso ya no existe o no es tuyo")
        return
    # A group pauses/resumes together: resume only if every process is paused.
    all_paused = all(paused for _, paused in procs)
    sig = {"pause": signal.SIGCONT if all_paused else signal.SIGSTOP,
           "term": signal.SIGTERM, "kill": signal.SIGKILL}.get(action)
    if sig is None:
        return
    failed = []
    for pid, _ in procs:
        try:
            os.kill(pid, sig)
        except OSError as exc:
            failed.append(exc.strerror)
    if failed:
        notify("No se pudo", f"{', '.join(sorted(names))}: {failed[0]}")
    open(os.path.join(RUNTIME, "eww-widgets-procs-dirty"), "w").close()



def collect(ctx):
    w, opts = ctx.widget, ctx.opts
    now_local = ctx.now
    runner_results, stamps = {w["id"]: ctx.output}, {w["id"]: ctx.stamp}
    procs = ctx.processes
    out = ctx.output or "…"
    p=Procs()
    p.prev=ctx.state.get('prev',{})
    p.prev_t=ctx.state.get('prev_t')
    rows=p.collect()
    ctx.state.update(prev=p.prev,prev_t=p.prev_t)
    result=procs_view(opts,rows)
    for item in result['rows']:
        identities=[]
        for pid in item['pid'].split(','):
            try:
                start=open('/proc/'+pid+'/stat').read().rsplit(')',1)[1].split()[19]
                identities.append(pid+':'+start)
            except OSError: pass
        item['pid']=','.join(identities)
    from randly_widgets.state import read_event
    result['error'] = read_event(w['id']).get('error','')
    return result
