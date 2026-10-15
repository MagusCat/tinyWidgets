import json, os, re, subprocess, sys, time, random
from randly_widgets.paths import RUNTIME, STATE_DIR
from randly_widgets.formatting import *

PIXEL_SPRITES = {
    "Gatito 8-bit": {
        "frames": [
            [
                "................",
                "..k...k..k...k..",
                "..kw.wk..kw.wk..",
                "..kwwwkkkkwwwk..",
                ".kwwwwwwwwwwwwk.",
                ".kwwkwwwwwwkwwk.",
                ".kwwwwkppkwwwwk.",
                "kwwwwww..wwwwwwk",
                "kwwwwwwwwwwwwwwk",
                ".kwwwwwwwwwwwwk.",
                "..kwwwwwwwwwwk..",
                "..kwwwwwwwwwwk..",
                "..kwwwwwwwwwwk.k",
                "..kwwkwwwwkwwkkk",
                "..kkkk....kkkk..",
                "................"
            ],
            [
                "................",
                "..k...k..k...k..",
                "..kw.wk..kw.wk..",
                "..kwwwkkkkwwwk..",
                ".kwwwwwwwwwwwwk.",
                ".kww..wwwwww..wk",
                ".kwwwwkppkwwwwk.",
                "kwwwwww..wwwwwwk",
                "kwwwwwwwwwwwwwwk",
                ".kwwwwwwwwwwwwk.",
                "..kwwwwwwwwwwk.k",
                "..kwwwwwwwwwwkkk",
                "..kwwwwwwwwwwk.k",
                "..kwwkwwwwkwwk..",
                "..kkkk....kkkk..",
                "................"
            ],
            [
                "................",
                "..k...k..k...k..",
                "..kwpwk..kwpwk..",
                "..kwwwkkkkwwwk..",
                ".kwwwwwwwwwwwwk.",
                ".kwwppwwwwwwppwk",
                ".kwwwwwwwwwwwwk.",
                "kwwwwwwppwwwwwwk",
                "kwwwwwkwwkwwwwwk",
                ".kwwwwwwwwwwwwk.",
                "..kwwwwwwwwwwk.k",
                "..kwwwwwwwwwwkkk",
                "..kwwwwwwwwwwk.k",
                "..kwwkwwwwkwwk..",
                "..kkkk....kkkk..",
                "................"
            ]
        ],
        "name": "Neko 8-bit"
    },
    "Pikachu": {
        "frames": [
            [
                "kk............kk",
                "kkyk........kykk",
                ".kyyk......kyyk.",
                "..kyykkkkkkyyk..",
                ".kyyyyyyyyyyyyk.",
                ".kykkyyyyykkyyk.",
                "kyywwyyyyyywwyyk",
                "krryyyyyyyyyyrrk",
                "kryyyy..yyyyyyrk",
                ".kyyyyyyyyyyyyk.",
                "..kyyyyyyyyyyk.k",
                "..kyykyyyykyykky",
                "..kyykyyyykykky.",
                "..kkkk....kkkk..",
                "................",
                "................"
            ],
            [
                "kk............kk",
                "kkyk........kykk",
                ".kyyk......kyyk.",
                "..kyykkkkkkyyk..",
                ".kyyyyyyyyyyyyk.",
                ".ky..yyyyyy..yyk",
                "kyywwyyyyyywwyyk",
                "krryyyyyyyyyyrrk",
                "kryyyywwyyyyyyrk",
                ".kyyyyyyyyyyyyk.",
                "..kyyyyyyyyyykkk",
                "..kyykyyyykyyk.k",
                "..kyykyyyykykky.",
                "..kkkk....kkkk..",
                "................",
                "................"
            ],
            [
                "y.kk........kky.",
                "ykkyk......kykky",
                "y.kyyk....kyyk.y",
                "..kyykkkkkkyyk..",
                ".kyyyyyyyyyyyyk.",
                ".kywwyyyyyywwyyk",
                "kyywwyyyyyywwyyk",
                "krrrrwyyyywrrrk.",
                "kryyyywwyyyyyyrk",
                ".kyyyyyyyyyyyyk.",
                "..kyyyyyyyyyykkk",
                "..kyykyyyykyyk.k",
                "..kyykyyyykykky.",
                "..kkkk....kkkk..",
                "................",
                "................"
            ]
        ],
        "name": "Pikachu"
    },
    "Fantasmita Arcade": {
        "frames": [
            [
                ".....kkkkkk.....",
                "...kkrrrrrrkk...",
                "..krrrrrrrrrrk..",
                ".krrwwwwrrwwwwk.",
                ".krwwbbwwrwwbbwk",
                "krrwwbbwwrwwbbww",
                "krrrrwwwwrrrrwww",
                "krrrrrrrrrrrrrrr",
                "krrrrrrrrrrrrrrr",
                "krrrrrrrrrrrrrrr",
                "krrrrrrrrrrrrrrr",
                "krrrrrrrrrrrrrrr",
                "krrrrrrrrrrrrrrr",
                "krrkrrkrrrrkrrkr",
                "kr.krr.krr.krr.k",
                ".k..k...k...k..k"
            ],
            [
                ".....kkkkkk.....",
                "...kkrrrrrrkk...",
                "..krrrrrrrrrrk..",
                ".krrwwwwrrwwwwk.",
                ".krwwbbwwrwwbbwk",
                "krrwwbbwwrwwbbww",
                "krrrrwwwwrrrrwww",
                "krrrrrrrrrrrrrrr",
                "krrrrrrrrrrrrrrr",
                "krrrrrrrrrrrrrrr",
                "krrrrrrrrrrrrrrr",
                "krrrrrrrrrrrrrrr",
                "krrrrrrrrrrrrrrr",
                ".krrkrrkrrkrrkr.",
                "..kr.krr.krr.kr.",
                "...k..k...k..k.."
            ],
            [
                ".....kkkkkk.....",
                "...kkbbbbbbkk...",
                "..kbbbbbbbbbbk..",
                ".kbbwwwwbbwwwwk.",
                ".kbwyywwbbyywwbk",
                "kbbwyywwbbyywwbb",
                "kbbbwwwwbbwwwwbb",
                "kbbbbbbbbbbbbbbb",
                "kbbbbbbbbbbbbbbb",
                "kbwbwbwbwbwbwbwb",
                "kbbbbbbbbbbbbbbb",
                "kbbbbbbbbbbbbbbb",
                "kbbbbbbbbbbbbbbb",
                "kbbkbbkbbbbkbbkb",
                "kb.kbb.kbb.kbb.k",
                ".k..k...k...k..k"
            ]
        ],
        "name": "Arcade Ghost"
    },
    "Corazón Retro": {
        "frames": [
            [
                "................",
                "................",
                "................",
                "...kkk....kkk...",
                "..krrrk..krrrk..",
                ".krrwrrkkrrwrrk.",
                ".krrwrrrrrrrrrk.",
                ".krrrrrrrrrrrrk.",
                "..krrrrrrrrrrk..",
                "...krrrrrrrrk...",
                "....krrrrrrk....",
                ".....krrrrk.....",
                "......krrk......",
                ".......kk.......",
                "................",
                "................"
            ],
            [
                "................",
                "..kkk......kkk..",
                ".krrrk....krrrk.",
                "krrrrrk..krrrrrk",
                "krrwrrrkkrrwrrrk",
                "krrwrrrrrrrrrrrk",
                "krrrrrrrrrrrrrrk",
                ".krrrrrrrrrrrrk.",
                "..krrrrrrrrrrk..",
                "...krrrrrrrrk...",
                "....krrrrrrk....",
                ".....krrrrk.....",
                "......krrk......",
                ".......kk.......",
                "................",
                "................"
            ],
            [
                "y.kkk......kkk.y",
                ".krrrk....krrrk.",
                "krrrrrk..krrrrrk",
                "krrwwrrkkrrwwrrk",
                "krrwwrrrrrrwwrrk",
                "krrrrrrrrrrrrrrk",
                "krrrrrrrrrrrrrrk",
                ".krrrrrrrrrrrrk.",
                "..krrrrrrrrrrk..",
                "y..krrrrrrrrk..y",
                "....krrrrrrk....",
                ".....krrrrk.....",
                "......krrk......",
                ".......kk.......",
                "................",
                "................"
            ]
        ],
        "name": "Pixel Heart"
    },
    "Espada Legendaria": {
        "frames": [
            [
                "..............wk",
                ".............wkb",
                "............wkbb",
                "...........wkbb.",
                "..........wkbb..",
                ".........wkbb...",
                "........wkbb....",
                ".......wkbb.....",
                "......wkbb......",
                ".....wkbb.......",
                "....ykbb........",
                "..yyyky.........",
                ".ykyyyk.........",
                ".k.yky..........",
                "...kyk..........",
                "....k..........."
            ],
            [
                ".............wwk",
                "............wwkb",
                "...........wwkbb",
                "..........wwkbb.",
                ".........wwkbb..",
                "........wwkbb...",
                ".......wwkbb....",
                "......wwkbb.....",
                ".....wwkbb......",
                "....wwkbb.......",
                "...yykbb........",
                "..yyyky.........",
                ".ykyyyk.........",
                ".k.yky..........",
                "...kyk..........",
                "....k..........."
            ],
            [
                "b............wwk",
                ".b..........wwkb",
                "..b........wwkbb",
                "..........wwkbb.",
                ".........wwkbb..",
                "........wwkbb...",
                ".......wwkbb....",
                "......wwkbb.....",
                ".....wwkbb......",
                "....wwkbb.......",
                "...yykbb........",
                "..yyyky.........",
                ".ykyyyk.........",
                ".k.yky..........",
                "...kyk..........",
                "....k..........b"
            ]
        ],
        "name": "Master Sword"
    },
    "Poción Mágica": {
        "frames": [
            [
                "......kkkk......",
                "......kwwk......",
                "......kwwk......",
                ".....kwwwwk.....",
                "....kwwwwwwk....",
                "...kwwwwwwwwk...",
                "..kwwppppppwwk..",
                "..kwppppppppwk..",
                "..kwppppppppwk..",
                "..kwppwpppppwk..",
                "..kwppppppppwk..",
                "..kwppppppppwk..",
                "...kwwwwwwwwk...",
                "....kkkkkkkk....",
                "................",
                "................"
            ],
            [
                "......kkkk......",
                "......kwwk......",
                "......kwwk......",
                ".....kwwwwk.....",
                "....kwwwwwwk....",
                "...kwwpwwwwwk...",
                "..kwwppwpppwwk..",
                "..kwppppppppwk..",
                "..kwppwpppppwk..",
                "..kwppppppppwk..",
                "..kwppppwpppwk..",
                "..kwppppppppwk..",
                "...kwwwwwwwwk...",
                "....kkkkkkkk....",
                "................",
                "................"
            ],
            [
                "....p.kkkk.p....",
                "......kwwk......",
                ".....pkwwkp.....",
                ".....kwwwwk.....",
                "....kwwppwwk....",
                "...kwwppppwwk...",
                "..kwwppppppwwk..",
                "..kwppwppwppwk..",
                "..kwppppppppwk..",
                "..kwppwpppppwk..",
                "..kwppppwpppwk..",
                "..kwppppppppwk..",
                "...kwwwwwwwwk...",
                "....kkkkkkkk....",
                "................",
                "................"
            ]
        ],
        "name": "Magic Elixir"
    },
    "Dino Corredor": {
        "frames": [
            [
                ".........kkkkkkk",
                ".........k.kkkkk",
                ".........kkkkkkk",
                ".........kkkkkkk",
                ".........kkkk...",
                ".........kkkkkkk",
                "k.......kkkk....",
                "kk.....kkkkkkkk.",
                "kkk...kkkkkkk...",
                "kkkkkkkkkkkk....",
                ".kkkkkkkkkkk....",
                "..kkkkkkkkkk....",
                "...kkkkkkk......",
                "...kk...kk......",
                "...kk....kk.....",
                "...kk........... "
            ],
            [
                ".........kkkkkkk",
                ".........k.kkkkk",
                ".........kkkkkkk",
                ".........kkkkkkk",
                ".........kkkk...",
                ".........kkkkkkk",
                "k.......kkkk....",
                "kk.....kkkkkkkk.",
                "kkk...kkkkkkk...",
                "kkkkkkkkkkkk....",
                ".kkkkkkkkkkk....",
                "..kkkkkkkkkk....",
                "...kkkkkkk......",
                "...kk...kk......",
                "....kk...kk.....",
                ".........kk....."
            ],
            [
                ".........kkkkkkk",
                ".........k.kkkkk",
                ".........kkkkkkk",
                ".........kkkkkkk",
                ".........kkkk...",
                ".........kkkkkkk",
                "k.......kkkk....",
                "kk.....kkkkkkkk.",
                "kkk...kkkkkkk...",
                "kkkkkkkkkkkk....",
                ".kkkkkkkkkkk....",
                "..kkkkkkkkkk....",
                "...kkkkkkk......",
                "....kk..kk......",
                "....kk..kk......",
                "................"
            ]
        ],
        "name": "Chrome Dino"
    },
    "Hongo 1-Up": {
        "frames": [
            [
                ".....kkkkkk.....",
                "...kkggggggkk...",
                "..kggggggggggk..",
                ".kggwwggggwwggk.",
                ".kgwwwwggwwwwgk.",
                "kggwwwwggwwwwggk",
                "kggwwwwggwwwwggk",
                "kggggggggggggggk",
                "kgggwwggggwwgggk",
                ".kkkkkkkkkkkkkk.",
                "..kwwwwwwwwwwk..",
                "..kwwkwwwwkwwk..",
                "..kwwkwwwwkwwk..",
                "..kwwwwwwwwwwk..",
                "...kkkkkkkkkk...",
                "................"
            ],
            [
                ".....kkkkkk.....",
                "...kkggggggkk...",
                "..kggggggggggk..",
                ".kggwwggggwwggk.",
                ".kgwwwwggwwwwgk.",
                "kggwwwwggwwwwggk",
                "kggwwwwggwwwwggk",
                "kggggggggggggggk",
                "kgggwwggggwwgggk",
                ".kkkkkkkkkkkkkk.",
                "..kwwwwwwwwwwk..",
                "..kww..wwww..wk.",
                "..kww..wwww..wk.",
                "..kwwwwwwwwwwk..",
                "...kkkkkkkkkk...",
                "................"
            ],
            [
                "y....kkkkkk....y",
                "...kkggggggkk...",
                "..kggggggggggk..",
                ".kggwwggggwwggk.",
                ".kgwwwwggwwwwgk.",
                "kggwwwwggwwwwggk",
                "kggwwwwggwwwwggk",
                "kggggggggggggggk",
                "kgggwwggggwwgggk",
                ".kkkkkkkkkkkkkk.",
                "..kwwwwwwwwwwk..",
                "..kwwkwwwwkwwk..",
                "..kwwkwwwwkwwk..",
                "..kwwwwwwwwwwk..",
                "...kkkkkkkkkk...",
                "................"
            ]
        ],
        "name": "1-Up Mushroom"
    }
}


PIXEL_PALETTES = {
    "Original": {
        "k": "#181825", "w": "#ffffff", "r": "#f38ba8", "y": "#f9e2af",
        "g": "#a6e3a1", "b": "#89b4fa", "p": "#f5c2e7", "o": "#fab387",
        "d": "#585b70", "l": "#bac2de"
    },
    "Game Boy": {
        "k": "#0f380f", "w": "#9bbc0f", "r": "#8bac0f", "y": "#8bac0f",
        "g": "#306230", "b": "#8bac0f", "p": "#8bac0f", "o": "#306230",
        "d": "#306230", "l": "#8bac0f"
    },
    "Cyberpunk": {
        "k": "#09090b", "w": "#00f5ff", "r": "#ff007f", "y": "#ffe600",
        "g": "#00ff66", "b": "#7928ca", "p": "#ff007f", "o": "#ff8800",
        "d": "#1e1e2e", "l": "#80eaff"
    },
    "Monocromo": {
        "k": "#111111", "w": "#f0f0f0", "r": "#d0d0d0", "y": "#e0e0e0",
        "g": "#c0c0c0", "b": "#d0d0d0", "p": "#d8d8d8", "o": "#a0a0a0",
        "d": "#444444", "l": "#aaaaaa"
    },
    "Retro 80s": {
        "k": "#140024", "w": "#fff3fd", "r": "#ff2a85", "y": "#fcee0a",
        "g": "#05ffa1", "b": "#00f0ff", "p": "#b967ff", "o": "#ff7500",
        "d": "#3a1359", "l": "#e0a3ff"
    }
}


def sprite_to_markup(grid, colors):
    lines = []
    h = len(grid)
    w = max(len(row) for row in grid) if grid else 0
    for y in range(0, h, 2):
        row = []
        cur_style = None
        run = []
        for x in range(w):
            c_top = grid[y][x] if x < len(grid[y]) else '.'
            c_bot = grid[y+1][x] if y+1 < h and x < len(grid[y+1]) else '.'
            col_top = colors.get(c_top)
            col_bot = colors.get(c_bot)

            if not col_top and not col_bot:
                char = ' '
                fg, bg = None, None
            elif col_top and not col_bot:
                char = '▀'
                fg, bg = col_top, None
            elif not col_top and col_bot:
                char = '▄'
                fg, bg = col_bot, None
            elif col_top == col_bot:
                char = '█'
                fg, bg = col_top, None
            else:
                char = '▀'
                fg, bg = col_top, col_bot

            style = (fg, bg)
            if style != cur_style:
                if run:
                    txt = ''.join(run)
                    cfg, cbg = cur_style
                    attr = ''
                    if cfg: attr += f' foreground="{cfg}"'
                    if cbg: attr += f' background="{cbg}"'
                    row.append(f'<span{attr}>{txt}</span>' if attr else txt)
                cur_style = style
                run = [char]
            else:
                run.append(char)
        if run:
            txt = ''.join(run)
            cfg, cbg = cur_style
            attr = ''
            if cfg: attr += f' foreground="{cfg}"'
            if cbg: attr += f' background="{cbg}"'
            row.append(f'<span{attr}>{txt}</span>' if attr else txt)
        lines.append(''.join(row))
    return '\n'.join(lines)


def pixel_data(opts, now_local, wid):
    sp_key = opts.get("sprite", "Gatito 8-bit")
    pal_key = opts.get("palette", "Original")
    palette = dict(PIXEL_PALETTES.get(pal_key, PIXEL_PALETTES["Original"]))

    if sp_key == "Personalizado" and opts.get("custom_art", "").strip():
        raw_art = opts["custom_art"].strip().splitlines()
        grid = [row.rstrip() for row in raw_art]
        markup = sprite_to_markup(grid, palette)
        return {"markup": markup, "caption": "Arte personalizado"}

    sp_info = PIXEL_SPRITES.get(sp_key, PIXEL_SPRITES["Gatito 8-bit"])
    frames = sp_info["frames"]

    poke_file = os.path.join(RUNTIME, f"eww-pixel-poke-{wid}")
    poked = False
    try:
        if os.path.exists(poke_file):
            with open(poke_file) as pf:
                ts = float(pf.read().strip())
            if time.time() - ts < 2.5:
                poked = True
            else:
                os.remove(poke_file)
    except (OSError, ValueError):
        pass

    if poked and len(frames) > 2:
        frame_idx = 2
        caption = "¡Poke! ♥"
    elif opts.get("animate", "yes") == "yes":
        frame_idx = int(time.time() * 1.6) % min(2, len(frames))
        caption = sp_info.get("name", sp_key)
    else:
        frame_idx = 0
        caption = sp_info.get("name", sp_key)

    grid = frames[frame_idx]
    markup = sprite_to_markup(grid, palette)
    return {"markup": markup, "caption": caption}



def collect(ctx):
    w, opts = ctx.widget, ctx.opts
    now_local = ctx.now
    runner_results, stamps = {w["id"]: ctx.output}, {w["id"]: ctx.stamp}
    procs = ctx.processes
    out = ctx.output or "…"
    return pixel_data(opts, now_local, w["id"])
