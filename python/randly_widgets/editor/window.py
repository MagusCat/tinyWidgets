from .common import *
from .canvas import CanvasMixin
from .interaction import InteractionMixin
from .panels import PanelsMixin
from .settings import SettingsMixin
from .session import SessionMixin

class Editor(CanvasMixin, InteractionMixin, PanelsMixin, SettingsMixin, SessionMixin, Gtk.Window):
    def __init__(self):
        super().__init__()
        self.colors = palette()
        self.prefs = load_prefs()
        import copy
        self.original_widgets = copy.deepcopy(W.load())
        self.original_style = W.load_style()
        self.original_animation = W.load_animation()
        W._last_editor_save = copy.deepcopy(self.original_widgets)
        out = W.first_output() or {}
        ws_num, (wx, wy) = W.active_workspace_info()
        self.current_ws_num = ws_num
        self.current_ws_coords = (wx, wy)
        self.filter_ws = ws_num
        og = out.get("geometry", {"x": 0, "y": 0, "width": 1920, "height": 1080})
        self.ox, self.oy = og["x"], og["y"]
        self.wa = out.get("workarea", {"x": 0, "y": 0, "width": og["width"], "height": og["height"]})
        self.widgets = W.load()
        from randly_widgets.editor_geometry import GeometryTracker
        self.geometry_tracker = GeometryTracker()
        from randly_widgets.editor_activity import DragLease
        self.drag_lease = DragLease()
        self.geometry_cache = {}
        self.saved_rects = {}
        self.style_fx = self.original_style.get("fx", "none")
        self.worker = None
        self.rects = {}       # id -> [x, y, w, h] in output coordinates
        self.draw_rects = {}  # id -> [x, y, w, h] smoothly interpolated coordinates
        self.drag = None      # (id, mode, start_px, start_py, start_rect)
        self.hover = None
        self.mouse = (0, 0)
        self.buttons = []     # (rect, action)
        self.refresh_rects()
        GLib.timeout_add(16, self._anim_tick)

        self.set_app_paintable(True)
        visual = self.get_screen().get_rgba_visual()
        if visual:
            self.set_visual(visual)
        GtkLayerShell.init_for_window(self)
        GtkLayerShell.set_namespace(self, W.SURFACE_PREFIX + "editor")
        GtkLayerShell.set_layer(self, GtkLayerShell.Layer.OVERLAY)
        for edge in (GtkLayerShell.Edge.TOP, GtkLayerShell.Edge.BOTTOM,
                     GtkLayerShell.Edge.LEFT, GtkLayerShell.Edge.RIGHT):
            GtkLayerShell.set_anchor(self, edge, True)
        GtkLayerShell.set_exclusive_zone(self, -1)
        if hasattr(GtkLayerShell, "set_keyboard_mode"):
            GtkLayerShell.set_keyboard_mode(self, GtkLayerShell.KeyboardMode.EXCLUSIVE)
        else:
            GtkLayerShell.set_keyboard_interactivity(self, True)

        self.area = Gtk.DrawingArea()
        self.area.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK
                             | Gdk.EventMask.POINTER_MOTION_MASK)
        self.area.connect("draw", self.on_draw)
        self.area.connect("button-press-event", self.on_press)
        self.area.connect("button-release-event", self.on_release)
        self.area.connect("motion-notify-event", self.on_motion)
        self.connect("key-press-event", self.on_key)
        # Widgets change size on their own (GitHub loading, new tasks): keep boxes in sync.
        GLib.timeout_add(100, self._tick)
        self.debounce = None
        self.settle_source = None
        self.live_source = None
        self.pending_live = None
        self.guides = []
        self.toast = None
        self.just_added = None
        self.home = None
        self.left_home = False
        self.undo_stack = []
        self.redo_stack = []
        self.selected_wid = None
        self.pre_drag_snapshot = None
        self.last_hud_rect = None
        self.build_css()
        overlay = Gtk.Overlay()
        overlay.add(self.area)
        self.overlay = overlay
        self.palette_panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.settings_panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.workspace_panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.grid_panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.profiles_panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.style_panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)

        self.palette_revealer = Gtk.Revealer()
        self.settings_revealer = Gtk.Revealer()
        self.workspace_revealer = Gtk.Revealer()
        self.grid_revealer = Gtk.Revealer()
        self.profiles_revealer = Gtk.Revealer()
        self.style_revealer = Gtk.Revealer()

        for rev, panel, (pw, ph) in [
            (self.palette_revealer, self.palette_panel, (360, -1)),
            (self.settings_revealer, self.settings_panel, (320, -1)),
            (self.workspace_revealer, self.workspace_panel, (320, -1)),
            (self.grid_revealer, self.grid_panel, (320, -1)),
            (self.profiles_revealer, self.profiles_panel, (380, -1)),
            (self.style_revealer, self.style_panel, (340, -1)),
        ]:
            panel.get_style_context().add_class("panel")
            if pw > 0:
                panel.set_size_request(pw, ph)
            rev.set_transition_type(Gtk.RevealerTransitionType.CROSSFADE)
            rev.set_transition_duration(160)
            rev.set_reveal_child(False)
            rev.add(panel)
            overlay.add_overlay(rev)
            overlay.set_overlay_pass_through(rev, True)
            rev.connect("notify::child-revealed", lambda r, _p: not r.get_child_revealed() and r.hide())

        self.palette_revealer.set_halign(Gtk.Align.START)
        self.palette_revealer.set_valign(Gtk.Align.START)
        self.settings_revealer.set_halign(Gtk.Align.START)
        self.settings_revealer.set_valign(Gtk.Align.START)
        self.workspace_revealer.set_halign(Gtk.Align.START)
        self.workspace_revealer.set_valign(Gtk.Align.START)
        self.grid_revealer.set_halign(Gtk.Align.START)
        self.grid_revealer.set_valign(Gtk.Align.START)
        self.profiles_revealer.set_halign(Gtk.Align.START)
        self.profiles_revealer.set_valign(Gtk.Align.START)
        self.style_revealer.set_halign(Gtk.Align.START)
        self.style_revealer.set_valign(Gtk.Align.START)

        self.current_settings_wid = None
        self.last_settings_rect = None
        self.add(overlay)
        from randly_widgets.editor_worker import EditorWorker
        def sample():
            place=current_place()
            if None in place:return None
            return place,layer_geometries_by_id(),W.load_style().get('fx','none')
        self.worker = EditorWorker(W.EWW_DIR,sample)
