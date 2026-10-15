<div align="center">

# tinyWidgets

**tiny widget manager for silly things**

A little chaos for your Wayfire desktop. Cats, tiny dashboards, music, pixel art — each in its own corner.

Rust manager · Python editor · Eww widgets

</div>

## Small things, their own space

- Drag, resize, duplicate and configure widgets in a visual editor.
- Keep widgets on one workspace or make them global; save layouts as profiles.
- Mix cats, clocks, music, tasks, GitHub activity, system stats and custom commands.
- Use native entrance/exit effects and wallpaper colors without reopening windows on every palette change.
- Add self-contained components: manifest, view, style, optional provider and bundled assets.

## Requirements

| Required | Details |
| --- | --- |
| Platform | Linux with a Wayland session running **Wayfire** |
| Compositor IPC | Wayfire IPC and window-rules methods available; `WAYFIRE_SOCKET` must point to the current session socket |
| Renderer | **Eww with Wayland support**, compatible with 0.5.0 transforms/revealer; GTK **3.24** and gtk-layer-shell |
| Build tools | Stable Rust + Cargo, `rustfmt`, C compiler (`cc`), system linker and `pkg-config`; GTK3 development libraries and their GLib/GObject/GDK dependencies |
| Python | **3.10+**, PyGObject (`gi`), Pycairo; introspection for GTK3, Gdk, Pango and GtkLayerShell 0.1 |
| Utilities | POSIX shell, `sha256sum` from coreutils |
| Fonts | A Nerd Font for icons; Inter and JetBrains Mono are the default font choices with fallbacks |

The current build has been tested with Rust **1.99.0**, Python **3.14.8** and GTK **3.24.52**. Other versions have not been validated as a compatibility matrix.

Optional dependencies:

| Feature | Dependency |
| --- | --- |
| Music controls | `playerctl` and an MPRIS player |
| GitHub activity | GitHub CLI (`gh`) with an authenticated account |
| GitHub avatar processing | ImageMagick (`magick`); a bundled image is used when no avatar is available |
| Wallpaper palette | Matugen and an SCSS color template |
| Weather | Internet access to wttr.in |
| Custom commands | The programs required by the command you configure |

Install system dependencies with your distribution's package manager. The installer runs as your user and does not install system packages.

## Build & install

```sh
git clone https://github.com/MagusCat/tinyWidgets.git
cd tinyWidgets
./scripts/build.sh
./scripts/test.sh
./scripts/install.sh
```

All three scripts accept `--offline` if Cargo dependencies are already cached. Production binaries are built in `target/release/`; test-only IPC support is never included in the installed manager.

The installer places the launcher in `~/.local/bin`, binaries and Python modules in `~/.local/lib`, and components in `~/.config/eww/widgets`. Existing instances, profiles and custom components are preserved. Unchanged files are left untouched. Replaced files are backed up under `~/.local/state/tinyWidgets/install-backups/`. An existing Eww configuration belonging to another project is rejected.

Inside your Wayfire session:

```sh
~/.local/bin/widgetctl reload
~/.local/bin/widgetctl editor
```

A fresh installation starts with an empty layout. Add widgets in the editor. Add `~/.local/bin/widgetctl start` to Wayfire's autostart to bring them back next session.

## Play with it

```sh
widgetctl catalog
widgetctl add cat --id little-cat
widgetctl set little-cat x=80 y=100 width=420
widgetctl preview-anim vortex fade
widgetctl editor
```

Add `~/.local/bin` to `PATH` to use the short commands. Use `widgetctl --config /path/to/profile ...` for a separate Eww profile.

`widgetctl theme` plays OUT, applies valid colors and plays IN on existing windows. Set `palette_animation=false` for a color-only update. `widgetctl reload` validates and applies component changes and may reopen windows. After rebuilding/reinstalling the native theme bridge, close the editor and run `widgetctl reload` once to load the new library.

## Your own shortcuts

Apps, Chest and action-button widgets start without preselected applications. Open a widget's settings, then **Aplicaciones → Elegir aplicación** to search installed desktop entries. Enter selects a result; Escape returns to the list. Add, rename, reorder or remove shortcuts, or enter a custom command. Each instance keeps its own list; Chest supports 27 slots and the action button keeps one target.

Desktop entries launch through Gio, so their `Exec` fields and file placeholders are handled by the desktop. Custom commands remain explicit shell commands. Existing personal `chest.conf` slots are imported once into existing Chest instances during installation, with a backup; new instances stay empty.

## Motion without a pile-up

Animation settings are available in the editor and through the CLI:

```sh
widgetctl anim when=workspace workspace_delay=650 delay_in=180 max_parallel=4 fps=24 palette_animation=true
```

`workspace_delay` waits for navigation to settle; `delay_in` adds hidden preparation time before entry. `max_parallel` limits simultaneous effects, including when slow providers become ready together. Additional widgets wait their turn; `fps` caps motion updates between 12 and 30. The motion stream keeps only currently mapped widgets. Power policies and editor mode can reduce or disable effects.

Palette changes animate existing windows without reopening or moving them. A newer workspace transition cancels stale work and restores surviving global widgets. Invalid palettes leave colors and visibility intact.

## Bring your own silly thing

```sh
widgetctl new my-widget
```

The command creates a component in the installed configuration. To develop and version it, place its folder under `eww/widgets/` in your checkout, then run the installer.

```text
eww/widgets/my-widget/
├── manifest.json
├── view.yuck
├── style.scss
├── provider.py       # optional
└── assets/           # optional, declared in the manifest
```

Give Yuck definitions the `rw-my-widget` prefix and scope styles under `.rw-desktop.rw-my-widget`. Declare bundled files with `"assets": ["sprite.png"]`; use `@ASSETS@/sprite.png` in views/styles or `ctx.asset("sprite.png")` in providers. Components own their resources. Missing files and paths outside the component are rejected. Downloaded resources need their own cache and a bundled fallback. Personal photos remain user-configured inputs.

## Wallpaper colors

Adapt [examples/matugen.toml](examples/matugen.toml) to your SCSS template. The required variables are shown in [eww/_colors.scss](eww/_colors.scss).

For the default profile, write the palette to `~/.local/state/randly-widgets/palette.scss` and call `widgetctl theme` from the hook. The palette lives outside Eww's watched configuration; invalid CSS keeps the last valid colors. Alternate profiles currently read their own `_colors.scss`.

## Development

Run `./scripts/test.sh` before committing. It covers Rust units, Python regressions and isolated manager/installer integration tests. Graphical checks require a real Wayfire session: `widgetctl validate --graphics`. Automated tests do not measure desktop FPS or prove visual compatibility.

## Current limits & next steps

Wayfire is the only implemented compositor. Widgets in one Eww profile share a renderer process. The editor, data providers and configuration builder remain in Python; the manager and motion/theme runtime use Rust. The GTK3 theme bridge loads only into the managed Eww process and needs compatibility checks when updating Eww. Custom providers and commands execute with your user's permissions.

Next: validate real-session resize/workspace/palette behavior, benchmark larger layouts, finish random/jitter cascade and full-reload exit-transition parity, and extend palette isolation to alternate profiles.

## License

GNU General Public License, version 2 — see [LICENSE](LICENSE).
