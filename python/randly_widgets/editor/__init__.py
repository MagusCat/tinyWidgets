from .common import *
from pathlib import Path
from .window import Editor

def main():
    # Keep the editor on the current active workspace; minimize only its visible windows while editing.
    start = current_place()
    hidden = minimize_visible_windows()
    ws_num, _ = W.active_workspace_info()
    try:
        from randly_widgets.storage import write_json
        write_json(Path(W.RUNTIME)/'editor-place.json',list(W.workspace_snapshot() or ()))
        with open(EDITING_FLAG, "w", encoding="utf-8") as f:
            f.write(str(ws_num))
    except OSError:
        pass
    editor = None
    try:
        editor = Editor()
        editor.home = start
        editor.connect("destroy", Gtk.main_quit)
        try:
            gi.require_version("GLibUnix", "2.0")
            from gi.repository import GLibUnix
            add_signal = GLibUnix.signal_add
        except (ImportError, ValueError):
            add_signal = GLib.unix_signal_add
        for sig in (2, 15):  # SIGINT, SIGTERM: still restore windows and widgets
            add_signal(GLib.PRIORITY_DEFAULT, sig, lambda *_: Gtk.main_quit() or False)
        editor.show_all()
        editor.request_sync()
        # WIDGET_EDITOR_OPEN=palette | settings:<id> | workspaces[:<id>] opens a panel right away (scripting/testing).
        opening = os.environ.get("WIDGET_EDITOR_OPEN", "")
        if opening == "palette":
            GLib.idle_add(editor.show_palette)
        elif opening == "style":
            GLib.idle_add(editor.open_style_panel)
        elif opening == "grid":
            GLib.idle_add(editor.open_grid_panel)
        elif opening == "animation":
            GLib.idle_add(editor.open_animation)
        elif opening == "profiles":
            GLib.idle_add(editor.open_profiles_panel)
        elif opening.startswith("settings:"):
            GLib.idle_add(editor.open_settings, opening.split(":", 1)[1])
        elif opening == "workspaces" or opening.startswith("workspaces:"):
            target = opening.split(":", 1)[1] if ":" in opening else None
            GLib.idle_add(editor.open_workspace_panel, target)
        Gtk.main()
    finally:
        if editor and editor.worker:editor.worker.stop()
        if editor and editor.drag_lease:editor.drag_lease.close()
        try:
            os.remove(EDITING_FLAG)
            (Path(W.RUNTIME)/'editor-place.json').unlink(missing_ok=True)
        except OSError:
            pass
        for vid in hidden:
            W.wf_call("wm-actions/set-minimized", {"view_id": vid, "state": False})
        if not (editor and editor.left_home) and start != current_place():
            goto_place(start)
        W.sync()
    return 0



def run():
    import fcntl
    with open(os.path.join(W.RUNTIME, "eww-widget-editor.lock"), "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 0
        return main()
