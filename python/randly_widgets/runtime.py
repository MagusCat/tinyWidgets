import fcntl
import json
import os
import random
import re
import shlex
import socket
import struct
import subprocess
import sys
import time
from pathlib import Path
from .paths import *
from .registry import SCHEMA, KINDS
from .config import load
from .policy import is_disabled
from .appearance import *
from .adapters.wayfire import *
from .adapters.eww import eww, restart_daemon
from .storage import write_json
from .transitions import set_motion
from . import workspace_guard
def spec(w):
    """eww open arguments for one widget (also its identity for change detection)."""
    args = ["open", "rw-"+w["window"], "--id", w["id"],
            "--pos", f"{w['x']}x{w['y']}", "--anchor", w["anchor"].replace("-", " ")]
    # Options travel through `widgets cfg` (live), so only position forces a reopen.
    return args + ["--arg", f"wid={w['id']}"]


def stagger_pause(anim, elapsed=0.0):
    pause = (anim.get("stagger", 110) + random.uniform(0, anim.get("jitter", 15))) / 1000.0 - elapsed
    if pause > 0:
        time.sleep(pause)


def stagger_order(widgets_list, anim):
    """Widget ids in the configured cascade order."""
    if not widgets_list:
        return []
    order = normalize_order(anim.get("order"))
    all_widgets = {w["id"]: w for w in load()}
    resolved = []
    for item in widgets_list:
        if isinstance(item, dict) and "id" in item:
            resolved.append(item)
        elif isinstance(item, str) and item in all_widgets:
            resolved.append(all_widgets[item])
        elif isinstance(item, str):
            resolved.append({"id": item})
        else:
            resolved.append(item)

    if order == "random":
        resolved = random.sample(resolved, len(resolved))
    elif order in ("top_to_bottom", "left_to_right"):
        sizes = {}
        try:
            with open(os.path.join(EWW_DIR, "editor.json")) as fh:
                sizes = json.load(fh).get("sizes", {})
        except (OSError, ValueError):
            pass
        out = first_output() or {}
        wa = out.get("workarea", {"width": 1920, "height": 1080})

        def pos(w):
            if not isinstance(w, dict) or "anchor" not in w:
                return (0, 0)
            gw, gh = sizes.get(w.get("id", ""), (300, 200))
            x = wa["width"] - w.get("x", 0) - gw if "right" in w.get("anchor", "") else w.get("x", 0)
            y = wa["height"] - w.get("y", 0) - gh if "bottom" in w.get("anchor", "") else w.get("y", 0)
            return (y, x) if order == "top_to_bottom" else (x, y)

        resolved = sorted(resolved, key=pos)
    return [w["id"] if isinstance(w, dict) else str(w) for w in resolved]


WAYFIRE_INI = os.path.expanduser("~/.config/wayfire.ini")


WF_EWW_MATCH = 'app_id contains "rw-desktop-"'


WF_CORE_ANIM = {
    "zoom": "zoom",
    "fade": "fade",
    "spin": "spin",
    "zap": "zap",
    "blinds": "zoom",
    "helix": "spin",
    "melt": "fade",
    "shatter": "zap",
    "vortex": "spin",
    "none": "none",
}


WF_EFFECT_DURATION = {
    "zoom": "animate/zoom_duration",
    "fade": "animate/fade_duration",
    "spin": "animate/spin_duration",
    "zap": "animate/zap_duration",
    "blinds": "animate/zoom_duration",
    "helix": "animate/spin_duration",
    "melt": "animate/fade_duration",
    "shatter": "animate/zap_duration",
    "vortex": "animate/spin_duration",
    "none": "animate/duration",
}


def wf_option(name):
    res = wf_call("wayfire/get-config-option", {"option": name}) if name else None
    return res.get("value") if isinstance(res, dict) and res.get("result") == "ok" else None


def wf_duration(ms, like="", easing_override=None):
    """'<ms>ms <easing>', keeping the easing of an existing Wayfire animation value."""
    if easing_override:
        return f"{int(ms)}ms {easing_override}"
    easing = str(like or "").split()[1:2] or ["circle"]
    return f"{int(ms)}ms {easing[0]}"


def wf_view_ids(wids):
    """{wid: wayfire view id} for the mapped eww windows among wids."""
    want = {f"{SURFACE_PREFIX}{wid}": wid for wid in wids}
    views = wf_call("window-rules/list-views")
    return {want[v["app-id"]]: v["id"] for v in views or []
            if isinstance(v, dict) and v.get("app-id") in want}


def wf_set_close(view_id, effect, ms):
    """Per-view close effect; Wayfire reads it on unmap, so it is exact per widget."""
    core_effect = WF_CORE_ANIM.get(effect, "zoom")
    dkey = WF_EFFECT_DURATION.get(effect, "animate/duration")
    like = wf_option(dkey) if effect!='none' else ""
    for prop, val in (("close-animation-type", core_effect), ("close-animation-duration", wf_duration(ms, like))):
        wf_call("window-rules/set-view-property", {"id": view_id, "property": prop, "value": val})


def widget_effects(w, anim):
    """(in, out) Wayfire effects of one widget: per-widget opts override the global ones."""
    opts = (w or {}).get("opts", {})

    def pick(key, fallback):
        val = normalize_anim(str(opts.get(key) or "global"))
        return fallback if val == "global" else val
    return pick("anim", anim["anim_in"]), pick("anim_out", anim["anim_out"])


def eww_open_animated(args, wid, effect_in, ms_in, effect_out, ms_out, valid=lambda:True, prepared=False):
    """Map hydrated content hidden, then let GTK reveal it on its frame clock."""
    if not valid() or (not prepared and not set_motion(eww,[wid],False,effect_in,ms_in)):return False
    result=eww(*args)
    if result is None or result.returncode:return False
    if not wait_mapped(wid,valid) or not valid() or not set_motion(eww,[wid],True,effect_in,ms_in):
        eww('close',wid);return False
    return True


def wait_mapped(wid,valid=lambda:True):
    # A successful IPC exit without a body is not a mapping acknowledgement.
    for _ in range(20):
        if not valid():return False
        result=eww('active-windows')
        if result is not None and result.returncode==0 and any(line.split(':')[0].strip()==wid for line in result.stdout.splitlines()):return True
        time.sleep(.025)
    return False


def close_widgets(ids, by_id, anim, animated, stagger, valid=lambda:True):
    """Complete GTK OUT before destroying windows; fast workspace exits skip it."""
    if not ids:
        return
    duration=0;groups={}
    for i,wid in enumerate(ids):
        effect=widget_effects(by_id.get(wid),anim)[1] if animated else 'none'
        ms=anim['duration_out'] if animated and effect!='none' else 0
        duration=max(duration,ms)
        if stagger and animated:
            set_motion(eww,[wid],False,effect,ms)
            if i<len(ids)-1 and valid():stagger_pause(anim)
        else:groups.setdefault((effect,ms),[]).append(wid)
    for (effect,ms),group in groups.items():set_motion(eww,group,False,effect,ms)
    deadline=time.monotonic()+duration/1000+(.08 if duration else 0)
    while time.monotonic()<deadline and valid():time.sleep(min(.02,max(0,deadline-time.monotonic())))
    # Disable any compositor close effect: GTK already performed the transition.
    for view_id in wf_view_ids(ids).values():wf_set_close(view_id,'none',0)
    eww('close',*ids)


def open_widgets(ids, specs, active, by_id, anim, animated, stagger, valid=lambda:True, on_open=lambda _:None, mapping_valid=None):
    """Open only current requests; report only windows actually mapped."""
    opened=[]
    anim=dict(anim)
    if stagger and len(ids)>1:
        # A long list must not turn the entrance cascade into seconds of waiting.
        anim['stagger']=min(anim.get('stagger',110),300/(len(ids)-1))
        anim['jitter']=min(anim.get('jitter',0),anim['stagger']*.15)
    mapping_valid=mapping_valid or valid
    prepared=set();groups={}
    for wid in ids:
        if wid in active:continue
        effect=widget_effects(by_id.get(wid),anim)[0] if animated else 'none'
        ms=anim['duration_in'] if effect!='none' else 0
        groups.setdefault((effect,ms),[]).append(wid)
    for (effect,ms),group in groups.items():
        if valid() and set_motion(eww,group,False,effect,ms):prepared.update(group)
    for i, wid in enumerate(ids):
        if not valid():break
        t0 = time.time()
        if wid in active:
            # A single Eww open replaces this instance. Preserve its ready/idle
            # motion state instead of hiding every binding and restarting IN.
            result=eww(*specs[wid])
            if result is not None and result.returncode==0 and wait_mapped(wid,mapping_valid):
                opened.append(wid);on_open(wid)
            continue
        e_in, e_out = widget_effects(by_id.get(wid), anim) if animated else ("none", "none")
        if eww_open_animated(specs[wid], wid, e_in, anim['duration_in'] if e_in!='none' else 0,e_out,anim['duration_out'],mapping_valid,wid in prepared):
            opened.append(wid);on_open(wid)
        if stagger and i < len(ids) - 1:
            stagger_pause(anim, time.time() - t0)
    return opened


def preview_animation(anim_in=None, anim_out=None):
    """Replay out → in on the visible widgets with the given effects (editor 'Probar')."""
    anim = load_animation()
    if anim_in:
        anim["anim_in"] = normalize_anim(anim_in)
    if anim_out:
        anim["anim_out"] = normalize_anim(anim_out)
    anim["stagger"] = max(150, anim.get("stagger", 110))
    preview_flag = os.path.join(RUNTIME, "eww-widgets-anim-preview")
    with open(LOCK, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        place=workspace_snapshot();token=workspace_guard.read().get('token')
        valid=lambda:place is not None and workspace_snapshot()==place and workspace_guard.ready(token)
        if not valid():return
        res = eww("active-windows")
        active = set()
        if res is not None and res.returncode == 0:
            active = {line.split(":")[0].strip() for line in res.stdout.splitlines() if ":" in line}
        widgets = [w for w in load() if w["id"] in active and w["window"] in KINDS]
        if not widgets:
            cur_num, cur_coords = active_workspace_info()
            widgets = [w for w in load() if w["show"] and w["window"] in KINDS and widget_matches_workspace(w, cur_num, cur_coords)]
        if not widgets:
            return
        ids = stagger_order(widgets, anim)
        plain = {w['id']:w for w in widgets}
        try:
            with open(preview_flag, "w") as fh:
                fh.write("1")
            if active & set(plain):
                close_widgets(ids, plain, anim, True, True,valid)
            if not valid():return
            prime_data(load())
            opened=open_widgets(ids, {w['id']:spec(w) for w in widgets},set(),plain,anim,True,True,valid)
            if not valid():close_widgets(opened,plain,anim,False,False)
            total_open_time = len(ids) * (anim.get("stagger", 110) / 1000.0) + (anim.get("duration_in", 340) / 1000.0) + 0.35
            time.sleep(total_open_time)
        finally:
            try:
                os.remove(preview_flag)
            except OSError:
                pass


def preview_fx(fx_key=None, duration=3.5):
    """Temporarily showcase the active Juice FX on desktop widgets."""
    if fx_key:
        save_style(fx=fx_key)
    preview_flag = os.path.join(RUNTIME, "eww-widgets-anim-preview")
    try:
        with open(preview_flag, "w") as fh:
            fh.write("1")
        time.sleep(duration)
    finally:
        try:
            os.remove(preview_flag)
        except OSError:
            pass


def apply_animation(active=True, anim=None):
    """GTK handles widget transitions; compositor globals are never rewritten."""
    return True


def apply_in_rules(active=True, anim=None):
    """Compatibility hook: native GTK transitions need no compositor rules."""
    pass


def reload():
    native=os.environ.get('RANDLY_WIDGETS_MANAGER')
    if native:return subprocess.run([native,'--config',EWW_DIR,'restart'],capture_output=True,timeout=40).returncode==0
    """Restart this profile's daemon to avoid Eww 0.5's reload IPC deadline."""
    editing = os.path.exists(os.path.join(RUNTIME, "eww-widgets-editing"))
    anim = load_animation()
    res = eww("active-windows")
    if res is not None and res.returncode == 0:
        # Play each widget's out effect (none while editing); reopening waits for it to finish.
        animated = not editing and anim["when"] != "never"
        ids = stagger_order([line.split(":")[0].strip() for line in res.stdout.splitlines() if ":" in line], anim)
        close_widgets(ids, {w["id"]: w for w in load()}, anim, animated, animated and anim["stagger_out"])
    if not restart_daemon():return False
    return sync(reloading=True)



def clear_stale_editor():
    """A crashed editor must not expose all workspaces at the next login."""
    with open(Path(RUNTIME)/'eww-widget-editor.lock','a+') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return
        for name in ('eww-widgets-editing','editor-place.json','eww-widgets-anim-preview','editor-drag.json','editor-sync-request.json'):
            (Path(RUNTIME)/name).unlink(missing_ok=True)


def prime_data(widgets):
    """Hydrate new bindings; never reset existing surfaces after an empty IPC reply."""
    from .registry import REGISTRY
    payload=None
    for _ in range(3):
        result=eww('get','wcfg')
        try:
            value=json.loads(result.stdout) if result is not None and result.returncode==0 else None
            if isinstance(value,dict) and 'g' in value:payload=value;break
        except (ValueError,TypeError):pass
        time.sleep(.04)
    if payload is None:return False
    legacy='o' in payload or 'm' in payload
    old_motion=payload.get('m',{})
    old=payload.get('g',{});ready=payload.get('r',{})
    payload={'g':{},'t':{},'r':{}};opts={};context=option_context()
    for w in widgets:
        kind=w['window'];wid=w['id']
        if kind not in KINDS:continue
        opts[wid]=options(w,context)
        payload['g'][wid]={**REGISTRY.modules[kind].get('initial',{}),'error':'',**old.get(wid,{})}
        payload['r'][wid]=ready.get(wid,not REGISTRY.modules[kind].get('provider'))
        if kind=='clock':payload['t'][wid]=payload['g'][wid]
    if legacy:
        payload.update(o=opts,m=old_motion)
        result=eww('update','wcfg='+json.dumps(payload,ensure_ascii=False))
    else:result=eww('update','woptions='+json.dumps(opts,ensure_ascii=False),'wcfg='+json.dumps(payload,ensure_ascii=False))
    return result is not None and result.returncode==0


def _legacy_sync(visible=None, reloading=False, leaving_only=False,request_token=None):
    """Reconcile the latest workspace/configuration, without queuing stale opens."""
    request=workspace_guard.read().get('token')
    with open(LOCK, 'w') as lock:
        # A waiting caller must not replay an old workspace after a newer one.
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return True
        editing=os.path.exists(os.path.join(RUNTIME,'eww-widgets-editing'))
        disabled=is_disabled() and not editing
        place=workspace_snapshot()
        if place is None and not disabled and visible is not False:return False
        cur_num=10 if place and place[1]==2 else (place[3]*place[4]+place[2]+1 if place else 1)
        cur_coords=(place[2],place[3]) if place else (0,0)
        widgets=load()
        try:revision=os.stat(CONF).st_mtime_ns
        except OSError:revision=0
        def place_valid():
            if request_token:
                from .editor_mailbox import SyncMailbox
                if not SyncMailbox(RUNTIME).current(request_token):return False
            return (workspace_guard.ready(request) and workspace_snapshot()==place
                    and not (is_disabled() and not editing))
        def valid():
            try:current_revision=os.stat(CONF).st_mtime_ns
            except OSError:current_revision=0
            return current_revision==revision and place_valid()
        target=visible
        if target is None and editing:
            try:selection=Path(RUNTIME,'eww-widgets-editing').read_text().strip()
            except OSError:selection=''
            target=int(selection) if selection.isdigit() else 'global'
        editor_home=None
        if editing:
            try:editor_home=tuple(json.loads(Path(RUNTIME,'editor-place.json').read_text()))
            except (OSError,ValueError):pass
        if editing and (editor_home and editor_home!=place or isinstance(target,int) and not isinstance(target,bool) and target!=cur_num):target=False
        def matches(w):
            if disabled or target is False:return False
            if target=='global' or editing and target is True:return is_global_widget(w)
            if target is True:return True
            return widget_matches_workspace(w,target if isinstance(target,int) else cur_num,cur_coords)
        res=eww('active-windows')
        if res is None or res.returncode:return False
        active={line.split(':')[0].strip() for line in res.stdout.splitlines() if ':' in line}
        try:applied=json.loads(Path(APPLIED).read_text())
        except (OSError,ValueError):applied={}
        applied={wid:args for wid,args in applied.items() if wid in active}
        wanted={w['id']:spec(w) for w in widgets if w['show'] and w['window'] in KINDS and matches(w)}
        by_id={w['id']:w for w in widgets}
        anim=load_animation()
        policy=power_policy()
        factor=float(policy.get('animation_factor',1))
        for key in ('duration_in','duration_out'):anim[key]=round(anim[key]*factor)
        when=normalize_when(anim.get('when','workspace'))
        animated=not editing and factor>0 and (when=='workspace' or when=='reload' and reloading)
        if request_token and not place_valid():return False
        leaving=active-set(wanted)
        if leaving:
            # Leaving during workspace navigation is always immediate.
            close_widgets(sorted(leaving),by_id,anim,animated and reloading,False,valid)
            for wid in leaving:applied.pop(wid,None)
        if leaving_only or not valid():
            write_json(APPLIED,applied);return True
        opening=[wid for wid,args in wanted.items() if not(wid in active and applied.get(wid)==args)]
        if opening:
            if any(wid not in active for wid in opening) and not prime_data(widgets):return False
            stagger=animated and anim['stagger_in']
            ids=stagger_order([by_id[x] for x in opening],anim) if stagger else opening
            def mapped(wid):
                applied[wid]=wanted[wid]
                write_json(APPLIED,applied)
            opened=open_widgets(ids,wanted,active,by_id,anim,animated,stagger,valid,mapped,place_valid)
            if not place_valid():
                close_widgets(opened,by_id,anim,False,False)
                for wid in opened:applied.pop(wid,None)
            else:
                for wid in opened:applied[wid]=wanted[wid]
            write_json(APPLIED,applied)
            return not place_valid() or (valid() and len(opened)==len(opening))
        write_json(APPLIED,applied)
    return True


def sync(visible=None,reloading=False,leaving_only=False,request_token=None):
    native=os.environ.get('RANDLY_WIDGETS_MANAGER')
    if not native:return _legacy_sync(visible,reloading,leaving_only,request_token)
    command='sync-leaving' if leaving_only else 'sync'
    mode='on' if visible is True else 'off' if visible is False else str(visible) if visible is not None else None
    args=[native,'--config',EWW_DIR,command]+([mode] if mode else [])
    result=subprocess.run(args,capture_output=True,text=True,timeout=30)
    return result.returncode==0
