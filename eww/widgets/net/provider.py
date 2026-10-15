import json, os, re, subprocess, sys, time, random
from randly_widgets.paths import RUNTIME, STATE_DIR
from randly_widgets.formatting import *

_net_prev = {}


def net_data(opts):
    global _net_prev
    now = time.time()
    rx, tx, iface = 0, 0, "eth0"
    try:
        with open("/proc/net/dev") as f:
            for line in f:
                parts = line.strip().split()
                if not parts or ":" not in parts[0]:
                    continue
                dev = parts[0].split(":")[0]
                if dev == "lo":
                    continue
                r_bytes = int(parts[1])
                t_bytes = int(parts[9])
                rx += r_bytes
                tx += t_bytes
                iface = dev
    except Exception:
        pass

    down_speed_str, up_speed_str = "0 KB/s", "0 KB/s"
    if _net_prev and "time" in _net_prev:
        dt = max(0.4, now - _net_prev["time"])
        drx = max(0, (rx - _net_prev.get("rx", rx)) / dt)
        dtx = max(0, (tx - _net_prev.get("tx", tx)) / dt)

        def fmt(bps):
            if bps >= 1048576:
                return f"{bps / 1048576:.1f} MB/s"
            return f"{bps / 1024:.0f} KB/s"

        down_speed_str = fmt(drx)
        up_speed_str = fmt(dtx)

    _net_prev = {"time": now, "rx": rx, "tx": tx}

    ip = "127.0.0.1"
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("1.1.1.1", 80))
        ip = s.getsockname()[0]
        s.close()
    except Exception:
        pass

    return {
        "down": down_speed_str,
        "up": up_speed_str,
        "ip": ip,
        "iface": iface
    }



def collect(ctx):
    w, opts = ctx.widget, ctx.opts
    now_local = ctx.now
    runner_results, stamps = {w["id"]: ctx.output}, {w["id"]: ctx.stamp}
    procs = ctx.processes
    out = ctx.output or "…"
    return net_data(opts)
