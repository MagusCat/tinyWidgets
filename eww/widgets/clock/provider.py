import json, os, re, subprocess, sys, time, random
from randly_widgets.paths import RUNTIME, STATE_DIR
from randly_widgets.formatting import *

def clock_text(opts, now_utc):
    import datetime as dt
    now = now_utc.astimezone()
    tz = opts.get("timezone", "").strip()
    if tz:
        try:
            from zoneinfo import ZoneInfo
            now = now_utc.astimezone(ZoneInfo(tz))
        except Exception:
            pass
    es = opts.get("lang") != "English"
    fmt = opts.get("time_format", "24h")
    time_s = now.strftime({"24h con segundos": "%H:%M:%S", "12h": "%I:%M %p"}.get(fmt, "%H:%M"))
    day = DAYS_ES[now.weekday()] if es else now.strftime("%A")
    month = MONTHS_ES[now.month - 1] if es else now.strftime("%B")
    date_s = {
        "12/10/2026": now.strftime("%d/%m/%Y"),
        "Lunes": day,
        "Oculta": "",
    }.get(opts.get("date_format"), f"{day}, {now.day} {month}")
    h, user = now.hour, os.environ.get("USER", "")
    if es:
        greet = "Buenas noches" if h < 5 or h >= 20 else "Buenos días" if h < 12 else "Buenas tardes"
    else:
        greet = "Good night" if h < 5 else "Good morning" if h < 12 else "Good afternoon" if h < 18 else "Good evening"
    return {"time": time_s, "date": date_s, "greeting": f"{greet}, {user}"}



def collect(ctx):
    import datetime as dt
    return clock_text(ctx.opts, dt.datetime.now(dt.timezone.utc))
