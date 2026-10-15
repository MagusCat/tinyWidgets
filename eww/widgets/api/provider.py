import json, os, re, subprocess, sys, time, random
from randly_widgets.paths import RUNTIME, STATE_DIR
from randly_widgets.formatting import *

def parse_quota_json(data, now_utc):
    """Extract quota percentage, resets string, label, and values from arbitrary JSON."""
    if not isinstance(data, dict):
        return None
    for k in ("usage", "data", "quota", "status", "utilization"):
        if k in data and isinstance(data[k], dict):
            merged = dict(data)
            merged.update(data[k])
            data = merged
            break

    # 1. Percent
    pct = None
    for k in ("percent", "pct", "utilization", "usage_percent", "used_pct"):
        if k in data:
            try:
                pct = float(data[k])
                break
            except (ValueError, TypeError):
                pass
    if pct is None:
        used = None
        for k in ("used", "consumed", "current", "requests_used", "tokens_used"):
            if k in data:
                try:
                    used = float(data[k])
                    break
                except (ValueError, TypeError):
                    pass
        total = None
        for k in ("total", "limit", "max", "quota", "requests_limit", "tokens_limit"):
            if k in data:
                try:
                    total = float(data[k])
                    break
                except (ValueError, TypeError):
                    pass
        if used is not None and total and total > 0:
            pct = round(100.0 * used / total, 1)
        elif "remaining" in data and total and total > 0:
            try:
                rem = float(data["remaining"])
                pct = round(100.0 * (total - rem) / total, 1)
            except (ValueError, TypeError):
                pass

    if pct is None:
        pct = 0.0
    pct = max(0, min(100, int(round(pct))))

    # 2. Resets / Countdown
    resets_str = ""
    import datetime as dt
    for k in ("resets_at", "reset_time", "expires_at", "next_reset", "window_reset"):
        val = data.get(k)
        if val:
            if isinstance(val, (int, float)):
                sec = max(0, int(val - now_utc.timestamp()))
                if sec >= 86400:
                    resets_str = f"Reinicia en {sec // 86400}d {(sec % 86400) // 3600}h"
                elif sec >= 3600:
                    resets_str = f"Reinicia en {sec // 3600}h {(sec % 3600) // 60}m"
                else:
                    resets_str = f"Reinicia en {sec // 60}m"
                break
            elif isinstance(val, str):
                try:
                    target = dt.datetime.fromisoformat(val.replace("Z", "+00:00"))
                    sec = max(0, int((target - now_utc).total_seconds()))
                    if sec <= 0:
                        resets_str = "Reiniciando…"
                    elif sec >= 86400:
                        resets_str = f"Reinicia en {sec // 86400}d {(sec % 86400) // 3600}h"
                    elif sec >= 3600:
                        resets_str = f"Reinicia en {sec // 3600}h {(sec % 3600) // 60}m"
                    else:
                        resets_str = f"Reinicia en {sec // 60}m"
                    break
                except Exception:
                    pass

    if not resets_str:
        for k in ("resets_in", "reset", "ttl", "time_left"):
            if data.get(k):
                resets_str = str(data[k])
                break

    # 3. Label / Model
    label = data.get("label") or data.get("model") or data.get("provider") or data.get("name") or ""

    # 4. Usage detail (e.g. 510 / 1500 req)
    detail = ""
    used_val = data.get("used") or data.get("current")
    total_val = data.get("total") or data.get("limit")
    unit_val = data.get("unit") or ""
    if used_val is not None and total_val is not None:
        detail = f"{used_val} / {total_val} {unit_val}".strip()

    return {
        "pct": pct,
        "resets": resets_str or "En ciclo",
        "label": label,
        "detail": detail
    }


def api_data(opts, now_local, out=None):
    import datetime as dt
    provider = opts.get("provider", "Claude (Sesión)")
    style_opt = opts.get("style", "Moderno (Glow + Chips)")
    layout = "minimal" if style_opt == "Minimalista" else ("dual" if style_opt == "Doble barra" or provider == "Claude (Ambas)" else ("classic" if style_opt == "Clásico" else "modern"))

    res = {
        "layout": layout,
        "pct": 0,
        "pct_text": "0%",
        "label": "",
        "subtitle": "",
        "detail": "",
        "resets": "",
        "alert": "normal",
        "bar1_pct": 0, "bar1_text": "0%", "bar1_label": "Sesión (5h)", "bar1_resets": "",
        "bar2_pct": 0, "bar2_text": "0%", "bar2_label": "Semanal (7d)", "bar2_resets": "",
    }
    now_utc = dt.datetime.now(dt.timezone.utc)

    def format_countdown(iso_str):
        if not iso_str:
            return ""
        try:
            target = dt.datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
            sec = max(0, int((target - now_utc).total_seconds()))
            if sec <= 0:
                return "Reiniciando…"
            if sec >= 86400:
                d = sec // 86400
                h = (sec % 86400) // 3600
                return f"Reinicia en {d}d {h}h"
            h = sec // 3600
            m = (sec % 3600) // 60
            return f"Reinicia en {h}h {m}m" if h else f"Reinicia en {m}m"
        except Exception:
            return ""

    if provider.startswith("Claude"):
        claude_path = os.path.expanduser("~/.claude.json")
        try:
            with open(claude_path) as f:
                cdata = json.load(f)
            u = cdata.get("cachedUsageUtilization", {}).get("utilization", {})
            fh = u.get("five_hour") or {}
            sd = u.get("seven_day") or {}
            fh_pct = max(0, min(100, int(fh.get("utilization") or 0)))
            sd_pct = max(0, min(100, int(sd.get("utilization") or 0)))
            fh_res = format_countdown(fh.get("resets_at"))
            sd_res = format_countdown(sd.get("resets_at"))

            if provider == "Claude (Semanal)":
                res["pct"] = sd_pct
                res["pct_text"] = f"{sd_pct}%"
                res["label"] = "Semanal 7d"
                res["subtitle"] = "Claude Code"
                res["resets"] = sd_res or "En ciclo"
                res["alert"] = "crit" if sd_pct >= 85 else ("warn" if sd_pct >= 60 else "normal")
            elif provider == "Claude (Ambas)":
                res["layout"] = "dual"
                res["bar1_pct"] = fh_pct
                res["bar1_text"] = f"{fh_pct}%"
                res["bar1_label"] = "Sesión (5h)"
                res["bar1_resets"] = fh_res or "En ciclo"
                res["bar2_pct"] = sd_pct
                res["bar2_text"] = f"{sd_pct}%"
                res["bar2_label"] = "Semanal (7d)"
                res["bar2_resets"] = sd_res or "En ciclo"
                res["subtitle"] = "Claude Code"
                res["alert"] = "crit" if (fh_pct >= 85 or sd_pct >= 85) else ("warn" if (fh_pct >= 60 or sd_pct >= 60) else "normal")
            else:  # Claude (Sesión)
                res["pct"] = fh_pct
                res["pct_text"] = f"{fh_pct}%"
                res["label"] = "Sesión 5h"
                res["subtitle"] = "Claude Code"
                res["resets"] = fh_res or "En ciclo"
                res["alert"] = "crit" if fh_pct >= 85 else ("warn" if fh_pct >= 60 else "normal")
        except Exception:
            res["label"] = "Claude Code"
            res["resets"] = "Sin datos en .claude.json"

    elif provider in ("Gemini", "Gemini 1.5 Flash", "Gemini 1.5 Pro", "Codex", "Lectura de archivo JSON"):
        if provider.startswith("Codex"):
            default_file = os.path.expanduser("~/.config/codex/usage.json")
        elif provider.startswith("Gemini"):
            default_file = os.path.expanduser("~/.config/gemini/usage.json")
        else:
            default_file = ""

        target_path = os.path.expanduser(opts.get("json_path", "") or default_file)

        raw_json_obj = None
        raw = (out or "").strip()
        if raw and raw not in ("…", "tiempo agotado (20 s)"):
            try:
                raw_json_obj = json.loads(raw)
            except Exception:
                pass

        if not raw_json_obj and target_path and os.path.isfile(target_path):
            try:
                with open(target_path) as jf:
                    raw_json_obj = json.load(jf)
            except Exception:
                pass

        if raw_json_obj:
            sub = (raw_json_obj.get("subtitle") if isinstance(raw_json_obj, dict) else None) or ("Google AI Studio" if "gemini" in provider.lower() else ("OpenAI Codex" if "codex" in provider.lower() else "JSON"))
            # Check for multi-models array
            raw_models = raw_json_obj.get("models") if isinstance(raw_json_obj, dict) else (raw_json_obj if isinstance(raw_json_obj, list) else None)
            if raw_models and isinstance(raw_models, list):
                parsed_list = []
                for m_item in raw_models:
                    pm = parse_quota_json(m_item, now_utc)
                    pm["name"] = m_item.get("name") or pm["label"] or "Modelo"
                    pm["pct_text"] = f"{pm['pct']}%"
                    pm["alert"] = "crit" if pm["pct"] >= 85 else ("warn" if pm["pct"] >= 60 else "normal")
                    parsed_list.append(pm)

                specific = None
                if provider in ("Gemini 1.5 Flash", "Gemini 1.5 Pro"):
                    for pm in parsed_list:
                        if provider.lower() in pm["name"].lower():
                            specific = pm
                            break

                if specific:
                    res["pct"] = specific["pct"]
                    res["pct_text"] = specific["pct_text"]
                    res["label"] = specific["name"]
                    res["subtitle"] = sub
                    res["detail"] = specific["detail"]
                    res["resets"] = specific["resets"]
                    res["alert"] = specific["alert"]
                else:
                    res["has_models"] = True
                    res["models"] = parsed_list
                    res["subtitle"] = sub
                    if parsed_list:
                        res["pct"] = parsed_list[0]["pct"]
                        res["pct_text"] = parsed_list[0]["pct_text"]
                        res["label"] = parsed_list[0]["name"]
                        res["detail"] = parsed_list[0]["detail"]
                        res["resets"] = parsed_list[0]["resets"]
                        res["alert"] = parsed_list[0]["alert"]
            else:
                parsed = parse_quota_json(raw_json_obj, now_utc)
                res["pct"] = parsed["pct"]
                res["pct_text"] = f"{parsed['pct']}%"
                res["label"] = parsed["label"] or (opts.get("title") or provider)
                res["subtitle"] = sub
                res["detail"] = parsed["detail"]
                res["resets"] = parsed["resets"]
                res["alert"] = "crit" if parsed["pct"] >= 85 else ("warn" if parsed["pct"] >= 60 else "normal")
        else:
            res["pct"] = 0
            res["pct_text"] = "0%"
            res["label"] = provider
            res["resets"] = f"Archivo no encontrado ({os.path.basename(target_path)})" if target_path else "Sin datos"

    else:  # Comando o API
        raw = (out or "").strip()
        parsed = None
        if raw and raw not in ("…", "tiempo agotado (20 s)"):
            try:
                parsed = parse_quota_json(json.loads(raw), now_utc)
            except Exception:
                m = re.search(r"-?\d+(?:[.,]\d+)?", raw)
                if m:
                    pct = float(m.group().replace(",", "."))
                    pct_val = max(0, min(100, int(round(pct))))
                    parsed = {"pct": pct_val, "resets": "En ejecución", "label": opts.get("title") or "API", "detail": ""}
                else:
                    res["resets"] = raw[:25]
        if parsed:
            res["pct"] = parsed["pct"]
            res["pct_text"] = f"{parsed['pct']}%"
            res["label"] = parsed["label"] or (opts.get("title") or "API")
            res["subtitle"] = "API"
            res["detail"] = parsed["detail"]
            res["resets"] = parsed["resets"]
            res["alert"] = "crit" if parsed["pct"] >= 85 else ("warn" if parsed["pct"] >= 60 else "normal")
        else:
            res["pct"] = 0
            res["pct_text"] = "0%"
            res["label"] = opts.get("title") or "API"
            res["resets"] = "Esperando salida…"

    return res



def collect(ctx):
    w, opts = ctx.widget, ctx.opts
    now_local = ctx.now
    runner_results, stamps = {w["id"]: ctx.output}, {w["id"]: ctx.stamp}
    procs = ctx.processes
    out = ctx.output or "…"
    data=api_data(opts, now_local, runner_results.get(w["id"]))
    if data.get('resets','').startswith(('Archivo no encontrado','Sin datos')):
        data['pct_text']='—'
        data['detail']='Sin datos disponibles'
    return data
