from .storage import locked, write_json
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
from .paths import *
from .registry import SCHEMA
from .config import photo_size
from .policy import power_policy
ANIM_KEYS = ["slide", "zoom", "fade", "pop", "float3d", "none", "spin", "zap", "blinds", "helix", "melt", "shatter", "vortex"]


ANIM_IN_KEYS = list(ANIM_KEYS)


ANIM_LABELS = {
    "slide": "Deslizar (GTK)",
    "zoom": "Aparece del fondo / Zoom",
    "fade": "Fundido / Fade",
    "pop": "Pop (Escala)",
    "float3d": "Flotación 3D / Pop-out 3D",
    "none": "Ninguna",
    "spin": "Giro / Spin",
    "zap": "Rayo / Zap",
    "blinds": "Persianas / Blinds",
    "helix": "Hélice / Helix",
    "melt": "Derretir / Melt",
    "shatter": "Estallido / Shatter",
    "vortex": "Vórtice / Vortex",
}


ANIM_DESCRIPTIONS = {
    "slide": "Desplazamiento lateral táctico y fluido exclusivo de widgets",
    "zoom": "Aparece desde el fondo con elevación suave",
    "fade": "Disolución cinematográfica suave de opacidad",
    "pop": "Escala con rebote sutil desde el fondo",
    "float3d": "Emerge desde el fondo proyectándose en 3D fuera de la pantalla",
    "none": "Entrada y salida instantánea sin animación",
    "spin": "Gira mientras escala",
    "zap": "Destello eléctrico",
    "blinds": "Apertura en persiana",
    "helix": "Giro en espiral",
    "melt": "Derretido líquido",
    "shatter": "Fragmentación cristalina",
    "vortex": "Absorción en remolino",
}


from .transitions import KEYS as NATIVE_ANIM_KEYS, LABELS as NATIVE_ANIM_LABELS
ANIM_KEYS += [k for k in NATIVE_ANIM_KEYS if k not in ANIM_KEYS]
ANIM_LABELS.update(NATIVE_ANIM_LABELS)
ANIM_IN_KEYS=list(ANIM_KEYS)
ANIM_MAP = {k: k for k in ANIM_KEYS}
ANIM_MAP.update({
    "slide": "slide", "deslizar": "slide", "deslizamiento": "slide", "deslizar / slide": "slide", "deslizar / slide (css)": "slide",
    "pop": "pop", "pop / zoom": "pop", "pop (escala)": "pop",
    "zoom": "zoom", "escala": "zoom", "escala / zoom": "zoom", "aparece del fondo": "zoom", "aparece del fondo / zoom": "zoom",
    "float3d": "float3d", "3d": "float3d", "flotacion 3d": "float3d", "flotación 3d": "float3d", "pop-out 3d": "float3d",
    "fundido": "fade", "fundido / fade": "fade",
    "glitch": "zap", "rayo": "zap", "rayo / zap": "zap",
    "fire": "zoom", "fuego": "zoom", "fuego / fire": "zoom",
    "blind": "blinds", "persianas": "blinds", "persianas / blinds": "blinds",
    "melter": "melt", "derretir": "melt", "derretir / melt": "melt",
    "estallido": "shatter", "estallido / shatter": "shatter",
    "hélice": "helix", "hélice / helix": "helix",
    "vórtice": "vortex", "vórtice / vortex": "vortex",
    "ninguna": "none",
    "global": "global", "heredar": "global", "heredar (global)": "global",
})


WHEN_KEYS = ["workspace", "reload", "never"]


WHEN_LABELS = {
    "workspace": "Al cambiar de workspace y al recargar",
    "reload": "Solo al recargar",
    "never": "Nunca",
}


WHEN_MAP = {
    "workspace": "workspace", "al cambiar de workspace y al recargar": "workspace",
    "reload": "reload", "solo al recargar": "reload",
    "never": "never", "nunca": "never",
}


ORDER_KEYS = ["config", "random", "top_to_bottom", "left_to_right"]


ORDER_LABELS = {
    "config": "Como en widgets.conf",
    "random": "Aleatorio",
    "top_to_bottom": "De arriba a abajo",
    "left_to_right": "De izquierda a derecha",
}


ORDER_MAP = {
    "config": "config", "como en widgets.conf": "config",
    "random": "random", "aleatorio": "random",
    "top_to_bottom": "top_to_bottom", "de arriba a abajo": "top_to_bottom",
    "left_to_right": "left_to_right", "de izquierda a derecha": "left_to_right",
}


SKIN_KEYS = ["bento", "cyber", "minimal", "crt", "glass", "pixel", "shell", "gnome", "clean", "notepad"]


SKIN_LABELS = {
    "bento": "Bento (Moderno)",
    "cyber": "Cyberpunk / Neo-Brutalist",
    "minimal": "Minimal Flat",
    "crt": "Retro Phosphor CRT",
    "glass": "Ultra Frosted Glass",
    "pixel": "Pixel 16-bit",
    "shell": "Shell (oh-my-zsh)",
    "gnome": "GNOME (Adwaita)",
    "clean": "Limpio (sin fondo)",
    "notepad": "Bloc de notas",
}


SKIN_MAP = {
    "bento": "bento", "bento (moderno)": "bento",
    "cyber": "cyber", "cyberpunk": "cyber", "cyberpunk / neo-brutalist": "cyber",
    "minimal": "minimal", "minimal flat": "minimal",
    "crt": "crt", "retro crt": "crt", "retro phosphor crt": "crt",
    "glass": "glass", "ultra frosted glass": "glass",
    "pixel": "pixel", "pixel 16-bit": "pixel", "pixelart": "pixel",
    "shell": "shell", "shell (oh-my-zsh)": "shell", "terminal": "shell",
    "gnome": "gnome", "gnome (adwaita)": "gnome", "adwaita": "gnome",
    "clean": "clean", "limpio": "clean", "limpio (sin fondo)": "clean",
    "notepad": "notepad", "bloc de notas": "notepad",
    "global": "global", "heredar": "global",
}


FX_KEYS = ["none", "glow", "float", "float3d", "pulse", "border"]


FX_LABELS = {
    "none": "Ninguno",
    "glow": "Glow suave",
    "float": "Flotación",
    "float3d": "Flotación 3D (Sale de pantalla)",
    "pulse": "Respiración",
    "border": "Borde brillante",
}


FX_DESCRIPTIONS = {
    "none": "Estático y minimalista. Sin movimiento ni auras continuas.",
    "glow": "Aura neón: el borde y los iconos/reloj respiran en el color primario.",
    "float": "Levitación: los iconos de acento flotan suavemente sin mover la tarjeta.",
    "float3d": "Levitación 3D: la tarjeta se eleva hacia el usuario con sombras multicapa profundas y reflejos luminosos.",
    "pulse": "Latido: títulos, iconos y borde laten en el tono secundario.",
    "border": "Borde neón fijo de 2px cuyo color deriva lentamente del primario al terciario.",
}


FX_MAP = {
    "none": "none", "ninguno": "none",
    "glow": "glow", "glow suave": "glow",
    "float": "float", "flotación": "float", "flotacion": "float",
    "float3d": "float3d", "3d": "float3d", "flotacion 3d": "float3d", "flotación 3d": "float3d", "flotacion3d": "float3d",
    "pulse": "pulse", "respiración": "pulse", "respiracion": "pulse",
    "border": "border", "borde brillante": "border",
    "global": "global", "heredar": "global",
}


from .themes import BACKGROUNDS,BACKGROUND_LABELS,normalize_background,FX as ALL_FX,FX_LABELS as EXTRA_FX_LABELS,FX_DESCRIPTIONS as EXTRA_FX_DESCRIPTIONS
from .transitions import SIZE_KEYS,SIZE_LABELS
SKIN_KEYS += ['monochrome','retro','zsh','terminal']
SKIN_LABELS.update({'monochrome':'Monocromático','retro':'Retro · 4 tonos','zsh':'Zsh','terminal':'Terminal'})
SKIN_MAP.update({k:k for k in ('monochrome','retro','zsh','terminal')})
SKIN_MAP.update({'monocromatico':'monochrome','monocromático':'monochrome','monochromatico':'monochrome','monochromatic':'monochrome','retro paleta reducida':'retro'})
FX_KEYS=list(ALL_FX);FX_LABELS.update(EXTRA_FX_LABELS);FX_DESCRIPTIONS.update(EXTRA_FX_DESCRIPTIONS)
FX_MAP.update({k:k for k in FX_KEYS})
ANIM_MAP['glitch']='glitch'
ANIM_DESCRIPTIONS.update({'vortex':'Giro y escala en espiral sin cambiar el tamaño del contenedor.',
    'zap':'Compresión vertical y expansión rápida.', 'glitch':'Desplazamientos breves sin alterar el espacio del widget.',
    'pop':'Expansión con rebote corto.', 'zoom':'Escala suave sobre el contenido ya preparado.',
    'float3d':'Compresión vertical y desplazamiento suave para sugerir profundidad.'})


def normalize_anim(val):
    if not val:
        return "zoom"
    return ANIM_MAP.get(str(val).strip().lower(), "zoom")


def normalize_when(val):
    if not val:
        return "workspace"
    return WHEN_MAP.get(str(val).strip().lower(), "workspace")


def normalize_order(val):
    if not val:
        return "config"
    return ORDER_MAP.get(str(val).strip().lower(), "config")


def normalize_skin(val):
    if not val:
        return "bento"
    return SKIN_MAP.get(str(val).strip().lower(), "bento")


def normalize_fx(val):
    if not val:
        return "none"
    return FX_MAP.get(str(val).strip().lower(), "none")


STYLE_FILE = os.path.join(EWW_DIR, "style.json")


STYLE_DEFAULTS = {"skin": "bento", "fx": "none", "background": "surface"}


def load_style():
    try:
        with open(STYLE_FILE, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        data = {}
    out = dict(STYLE_DEFAULTS)
    if isinstance(data, dict):
        out.update({k: v for k, v in data.items() if k in STYLE_DEFAULTS})
    out["skin"] = normalize_skin(out.get("skin"))
    out["fx"] = normalize_fx(out.get("fx"))
    out["background"] = normalize_background(out.get("background"))
    return out


def save_style(skin=None, fx=None, background=None):
    with locked(STYLE_FILE + ".lock"):
        data = load_style()
        if skin is not None:
            data["skin"] = normalize_skin(skin)
        if fx is not None:
            data["fx"] = normalize_fx(fx)
        if background is not None:data["background"]=normalize_background(background)
        write_json(STYLE_FILE, data)


ANIM_FILE = os.path.join(EWW_DIR, "animation.json")


ANIM_DEFAULTS = {
    "anim_in": "fade",
    "anim_out": "fade",
    "size_mode": "stable",
    "duration_in": 320,
    "duration_out": 240,
    "when": "workspace",
    "workspace_delay": 650,
    "delay_in": 180,
    "max_parallel": 4,
    "fps": 24,
    "palette_animation": True,
    "stagger": 110,
    "jitter": 15,
    "order": "left_to_right",
    "stagger_in": True,
    "stagger_out": True,
}


def load_animation():
    try:
        with open(ANIM_FILE, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        data = {}
    out = dict(ANIM_DEFAULTS)
    if "type" in data and "anim_in" not in data:
        out["anim_in"] = normalize_anim(data["type"])
        out["anim_out"] = "fade"
    out.update({k: v for k, v in data.items() if k in ANIM_DEFAULTS})
    out["anim_in"] = normalize_anim(out["anim_in"])
    out["anim_out"] = normalize_anim(out["anim_out"])
    out["when"] = normalize_when(out["when"])
    out["order"] = normalize_order(out["order"])
    if out.get("size_mode") not in SIZE_KEYS:out["size_mode"]="stable"
    for key in ("stagger", "jitter"):
        try:
            out[key] = max(0, min(1000, int(out[key])))
        except (TypeError, ValueError):
            out[key] = ANIM_DEFAULTS[key]
    for key in ("duration_in", "duration_out"):
        try:
            out[key] = max(50, min(2000, int(out[key])))
        except (TypeError, ValueError):
            out[key] = ANIM_DEFAULTS[key]
    for key,lo,hi in (("workspace_delay",0,5000),("delay_in",0,5000),("max_parallel",1,16),("fps",12,60)):
        try:out[key]=max(lo,min(hi,int(out[key])))
        except (TypeError,ValueError):out[key]=ANIM_DEFAULTS[key]
    if isinstance(out['palette_animation'],str):out['palette_animation']=out['palette_animation'].lower() in ('true','yes','1','on')
    out["type"] = out["anim_in"]
    return out


def save_animation(anim_in=None, anim_out=None, when=None, **extra):
    with locked(ANIM_FILE + ".lock"):
        data = load_animation()
        if anim_in is not None:
            data["anim_in"] = normalize_anim(anim_in)
            data["type"] = data["anim_in"]
        if anim_out is not None:
            data["anim_out"] = normalize_anim(anim_out)
        if when is not None:
            data["when"] = normalize_when(when)
        for k, v in extra.items():
            if k in ANIM_DEFAULTS:
                if k == "order":
                    data[k] = normalize_order(v)
                else:
                    data[k] = v
        write_json(ANIM_FILE, data)


def option(w, key):
    for k, _, _, default, *_ in SCHEMA.get(w["window"], {}).get("options", []):
        if k == key:
            return w["opts"].get(k, default)
    return w["opts"].get(key, "")


def option_context():
    """Read shared settings once per batch, regardless of instance count."""
    return dict(style=load_style(),animation=load_animation(),policy=power_policy(),
                editing=os.path.exists(os.path.join(RUNTIME,'eww-widgets-editing')),
                previewing=os.path.exists(os.path.join(RUNTIME,'eww-widgets-anim-preview')))


def options(w,context=None):
    """All options of a widget with defaults filled in (strings, bools as yes/no)."""
    context=option_context() if context is None else context
    out = {k: w["opts"].get(k, default)
           for k, _, _, default, *_ in SCHEMA.get(w["window"], {}).get("options", [])}
    out = {k: ('yes' if v else 'no') if isinstance(v, bool) else str(v) if isinstance(v, (int,float)) else v for k,v in out.items()}
    out['namespace'] = SURFACE_PREFIX + w.get('id','')
    if w["window"] in ("photo", "image"):
        out["width"], out["height"] = (str(v) for v in photo_size(w))
    if w["window"] == "image":
        filepath = os.path.expanduser(out.get("file", ""))
        out["file_resolved"] = filepath if os.path.isfile(filepath) else ""
        out["bg_size"] = "contain" if out.get("fit") == "Contener (entera)" else "cover"
    if w["window"] == "disks":
        out["mount_list"] = [m for m in out.get("mounts", "").split() if m]
    if w["window"] == "command":
        out["card_class"] = {"Sin marco (transparente)": "frame-none", "Terminal oscuro": "frame-terminal"}.get(out.get("card_style"), "")
        out["pad_class"] = {"Sin relleno": "pad-none", "Compacto": "pad-compact"}.get(out.get("padding"), "")
        out["halign"] = {"Centro": "center", "Derecha": "end"}.get(out.get("align"), "start")
        out["xalign"] = {"Centro": 0.5, "Derecha": 1.0}.get(out.get("align"), 0.0)
    if w["window"] == "api":
        out["style_class"] = {"Minimalista": "minimal", "Doble barra": "dual", "Clásico": "classic"}.get(out.get("style"), "modern")
        if out.get("accent") == "Personalizado" and out.get("custom_color"):
            c = out.get("custom_color", "#a855f7")
            out["custom_style"] = f"border-color: {c};"
    # The chosen width is the widget's outer width; CSS min-width excludes the card's
    # horizontal padding + border, so eww gets the inner value.
    if str(out.get("width", "")).isdigit():
        cmd_pad = 0 if out.get("card_style") == "Sin marco (transparente)" or out.get("padding") == "Sin relleno" else (16 if out.get("padding") == "Compacto" else 38)
        pad = {"clock": 24, "habits": 34, "tasks": 34, "photo": 0, "image": 0, "command": cmd_pad}.get(w["window"], 38)
        out["inner"] = str(max(0, int(out["width"]) - pad))
    # Characters that fit per text line at the chosen width (labels are cut/wrapped
    # to this, otherwise GTK sizes the widget to the full text length).
    width = int(out.get("width") or 0) if str(out.get("width", "")).isdigit() else 0
    raw_chars = w.get("opts", {}).get("chars")
    if raw_chars and str(raw_chars).isdigit() and int(raw_chars) > 0:
        out["chars"] = int(raw_chars)
    elif width:
        per_char = {"small": 6.6, "large": 11.5}.get(
            {"Pequeño": "small", "Grande": "large"}.get(out.get("font", ""), ""), 8.2)
        if w["window"] == "command" and out.get("mono") == "yes":
            out["chars"] = max(80, int((width - 40) / 7.3))
        else:
            reserved = {"tasks": 110, "habits": 210}.get(w["window"], 40)
            out["chars"] = max(8, int((width - reserved) / (7.3 if w["window"] in ("tasks", "habits") else per_char)))
    if "font" in out:
        out["font_class"] = {"Pequeño": "small", "Grande": "large"}.get(out["font"], "medium")
    if "accent" in out:
        out["accent_class"] = {"Secundario": "secondary", "Terciario": "tertiary",
                               "Rojo": "error", "Cian": "cyan", "Verde": "green",
                               "Púrpura": "purple", "Ámbar": "amber", "Rosa": "rose",
                               "Personalizado": "custom"}.get(out["accent"], "primary")
    # ── Style & Skin Resolution ──
    global_style = context["style"]
    raw_skin = w.get("opts", {}).get("skin", "global")
    skin_key = normalize_skin(raw_skin)
    if skin_key == "global":
        skin_key = global_style["skin"]
    background=normalize_background(w.get("opts",{}).get("background","global"))
    if background=="global":background=global_style["background"]
    out["background"]=background
    out["skin_class"] = f"skin-{skin_key} bg-{background}"
    out["skin"] = skin_key

    raw_fx = w.get("opts", {}).get("fx", "global")
    fx_key = normalize_fx(raw_fx)
    if fx_key == "global":
        fx_key = global_style["fx"]
    out["fx_class"] = f"fx-{fx_key}" if fx_key != "none" else ""
    out["fx"] = fx_key
    policy = context["policy"]
    out['skin_class'] += ' power-' + policy.get('mode', 'complete')
    if not policy.get('ambient_effects', True):
        out['fx_class'] = ''
        out['fx'] = 'none'

    # Mount/unmount motion belongs to GtkRevealer, independent of ambient FX.
    editing = context["editing"]
    previewing = context["previewing"]
    out["anim_class"] = "editing" if editing and not previewing else ""
    out["is_editing"] = "yes" if editing else "no"
    out["power_style"] = ""

    motion_mode=w.get("opts",{}).get("motion_mode","global")
    out["motion_mode"]=motion_mode if motion_mode in SIZE_KEYS else context["animation"]["size_mode"]
    out["anim"] = w.get("opts", {}).get("anim", "global")
    return out
