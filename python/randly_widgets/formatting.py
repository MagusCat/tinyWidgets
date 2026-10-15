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
DAYS_ES = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]


MONTHS_ES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
             "septiembre", "octubre", "noviembre", "diciembre"]


def clean_text(text, limit=2000):
    # eww renders labels containing backslashes as blank; keep Nerd Font glyphs.
    import unicodedata
    text = text.replace("\\", "/")[:limit]
    return "".join(c for c in text if c == "\n" or c.isprintable() or unicodedata.category(c) == "Co")


ANSI16 = ["#45475a", "#f38ba8", "#a6e3a1", "#f9e2af", "#89b4fa", "#f5c2e7", "#94e2d5", "#bac2de",
          "#585b70", "#f38ba8", "#a6e3a1", "#f9e2af", "#89b4fa", "#f5c2e7", "#94e2d5", "#cdd6f4"]


def xterm256(n):
    if n < 16:
        return ANSI16[n]
    if n >= 232:
        v = 8 + (n - 232) * 10
        return f"#{v:02x}{v:02x}{v:02x}"
    n -= 16
    steps = [0, 95, 135, 175, 215, 255]
    return "#{:02x}{:02x}{:02x}".format(steps[n // 36], steps[(n // 6) % 6], steps[n % 6])


def sgr(style, params):
    params = params or [0]
    i = 0
    while i < len(params):
        p = params[i]
        if p == 0:
            style = {}
        elif p == 1:
            style = dict(style, bold=True)
        elif p == 22:
            style = {k: v for k, v in style.items() if k != "bold"}
        elif 30 <= p <= 37 or 90 <= p <= 97:
            style = dict(style, fg=ANSI16[p - 30 if p < 90 else p - 82])
        elif p == 39:
            style = {k: v for k, v in style.items() if k != "fg"}
        elif p == 38 and i + 2 < len(params) and params[i + 1] == 5:
            style, i = dict(style, fg=xterm256(params[i + 2] % 256)), i + 2
        elif p == 38 and i + 4 < len(params) and params[i + 1] == 2:
            r, g, b = (max(0, min(255, v)) for v in params[i + 2:i + 5])
            style, i = dict(style, fg=f"#{r:02x}{g:02x}{b:02x}"), i + 4
        i += 1
    return style


def ansi_lines(text):
    """Lines of (char, style) cells; handles SGR colors and cursor column moves (G/C)."""
    import unicodedata
    lines, line, col, style, i = [], [], 0, {}, 0
    text = text.replace("\r\n", "\n")
    while i < len(text):
        ch = text[i]
        if ch == "\x1b" and i + 1 < len(text) and text[i + 1] == "[":
            j = i + 2
            while j < len(text) and not ("@" <= text[j] <= "~"):
                j += 1
            final, raw = (text[j] if j < len(text) else ""), text[i + 2:j]
            nums = [int(x) if x.isdigit() else 0 for x in raw.lstrip("?").split(";")] if raw else []
            if final == "m":
                style = sgr(style, nums)
            elif final in "GC":
                n = nums[0] if nums and nums[0] else 1
                target = n - 1 if final == "G" else col + n
                if target < col:  # moving back: later text overwrites from there
                    line, col = line[:target], target
                while col < target:
                    line.append((" ", {}))
                    col += 1
            i = j + 1
            continue
        if ch == "\x1b" and i + 1 < len(text) and text[i + 1] == "]":  # OSC ... BEL / ST
            j = text.find("\x07", i)
            k = text.find("\x1b\\", i)
            ends = [e for e in (j, k) if e != -1]
            i = (min(ends) + (1 if min(ends) == j else 2)) if ends else len(text)
            continue
        if ch == "\n":
            lines.append(line)
            line, col = [], 0
        elif ch == "\t":
            for _ in range(8 - col % 8):
                line.append((" ", style))
                col += 1
        elif ch == "\\":
            line.append(("/", style))  # eww blanks labels containing backslashes
            col += 1
        elif ch.isprintable() or unicodedata.category(ch) == "Co":
            line.append((ch, style))
            col += 1
        i += 1
    if line or not lines:
        lines.append(line)
    while lines and not lines[-1]:
        lines.pop()
    return lines[:400]


def markup_line(cells):
    import html
    out, run, cur = [], [], None
    for ch, st in cells + [(None, None)]:
        if st != cur or ch is None:
            if run:
                body = html.escape("".join(run), quote=False)
                attrs = (f' foreground="{cur["fg"]}"' if cur.get("fg") else "") + \
                        (' weight="bold"' if cur.get("bold") else "")
                out.append(f"<span{attrs}>{body}</span>" if attrs else body)
            run, cur = [], st
        if ch is not None:
            run.append(ch)
    return "".join(out)


def fit_lines(text, chars, lines, tail):
    """Wrap to the widget width; with a fixed height keep exactly `lines` lines."""
    out = wrap(text, chars).split("\n")
    try:
        lines = int(lines)
    except (TypeError, ValueError):
        lines = 0
    if lines > 0:
        out = out[-lines:] if tail else out[:lines]
        out += [""] * (lines - len(out))
    return "\n".join(out)


def wrap(text, chars):
    import textwrap
    lines = []
    for line in text.split("\n"):
        lines += textwrap.wrap(line, chars, break_long_words=True, replace_whitespace=False) or [""]
    return "\n".join(lines[:40])
