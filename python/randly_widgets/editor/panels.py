from .common import *

class PanelsMixin:
    @staticmethod
    def styled(widget, *classes):
        for cls in classes:
            widget.get_style_context().add_class(cls)
        return widget


    def label(self, text, *classes, xalign=0.0, wrap=False, width=None):
        lbl = Gtk.Label(label=text, xalign=xalign)
        if wrap:
            lbl.set_line_wrap(True)
            lbl.set_max_width_chars(width or 24)
        return self.styled(lbl, *classes)


    def setup_panel_drag(self, ebox, revealer):
        ebox.set_events(Gdk.EventMask.BUTTON_PRESS_MASK |
                        Gdk.EventMask.BUTTON_RELEASE_MASK |
                        Gdk.EventMask.POINTER_MOTION_MASK |
                        Gdk.EventMask.ENTER_NOTIFY_MASK)
        drag_state = {"dragging": False, "start_x": 0, "start_y": 0, "orig_m_x": 0, "orig_m_y": 0}

        def on_press(_w, ev):
            if ev.button == 1:
                self.overlay.reorder_overlay(revealer, -1)
                win = revealer.get_window()
                if win:
                    win.raise_()
                drag_state["dragging"] = True
                drag_state["start_x"] = ev.x_root
                drag_state["start_y"] = ev.y_root
                drag_state["orig_m_x"] = revealer.get_margin_start()
                drag_state["orig_m_y"] = revealer.get_margin_top()
                w = ebox.get_window()
                if w:
                    w.set_cursor(Gdk.Cursor.new_from_name(self.get_display(), "grabbing"))
                return True
            return False

        def on_release(_w, ev):
            if ev.button == 1 and drag_state["dragging"]:
                drag_state["dragging"] = False
                w = ebox.get_window()
                if w:
                    w.set_cursor(Gdk.Cursor.new_from_name(self.get_display(), "grab"))
                if revealer == self.settings_revealer:
                    pw = revealer.get_allocated_width() or 360
                    ph = revealer.get_allocated_height() or 300
                    self.last_settings_rect = (revealer.get_margin_start(), revealer.get_margin_top(), pw, ph)
                return True
            return False

        def on_motion(_w, ev):
            if drag_state["dragging"]:
                dx = ev.x_root - drag_state["start_x"]
                dy = ev.y_root - drag_state["start_y"]
                new_x = drag_state["orig_m_x"] + dx
                new_y = drag_state["orig_m_y"] + dy
                wa = self.wa
                pw = revealer.get_allocated_width() or 360
                ph = revealer.get_allocated_height() or 300
                new_x = max(wa["x"] + 10, min(new_x, wa["x"] + wa["width"] - pw - 10))
                new_y = max(wa["y"] + 10, min(new_y, wa["y"] + wa["height"] - ph - 10))
                revealer.set_margin_start(int(new_x))
                revealer.set_margin_top(int(new_y))
                return True
            return False

        def on_enter(_w, _ev):
            w = ebox.get_window()
            if w:
                w.set_cursor(Gdk.Cursor.new_from_name(self.get_display(), "grab"))
            return False

        ebox.connect("button-press-event", on_press)
        ebox.connect("button-release-event", on_release)
        ebox.connect("motion-notify-event", on_motion)
        ebox.connect("enter-notify-event", on_enter)


    def header(self, icon, title, sub=None, revealer=None):
        ebox = Gtk.EventBox()
        ebox.set_visible_window(False)
        box = Gtk.Box(spacing=8)
        box.pack_start(self.label(icon, "panel-icon", xalign=0.5), False, False, 0)
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0, valign=Gtk.Align.CENTER)
        title_lbl = self.label(title, "panel-title")
        title_lbl.set_ellipsize(Pango.EllipsizeMode.END)
        text.pack_start(title_lbl, False, False, 0)
        if sub:
            text.pack_start(self.label(sub, "panel-sub"), False, False, 0)
        box.pack_start(text, True, True, 0)
        grip = self.label("󰇛", "panel-grip")
        grip.set_valign(Gtk.Align.CENTER)
        grip.set_tooltip_text("Arrastra para mover el panel")
        box.pack_end(grip, False, False, 0)
        ebox.add(box)
        if revealer:
            self.setup_panel_drag(ebox, revealer)
        return ebox


    def button(self, text, callback, *classes, tooltip=None):
        btn = self.styled(Gtk.Button(label=text), "pbtn", *classes)
        if tooltip:
            btn.set_tooltip_text(tooltip)
        btn.connect("clicked", lambda *_: callback())
        return btn


    def icon_button(self, icon, tooltip, callback, *classes):
        return self.button(icon, callback, "icon", *classes, tooltip=tooltip)


    def form_row(self, grid, row, text, ctl, tooltip=None):
        """One label + control row; labels stay single-line so switches never stretch."""
        field = self.label(text, "field")
        field.set_valign(Gtk.Align.CENTER)
        field.set_ellipsize(Pango.EllipsizeMode.END)
        field.set_width_chars(min(len(text), 22))  # min width = full short label; long schema texts ellipsize
        field.set_tooltip_text(tooltip or text)
        grid.attach(field, 0, row, 1, 1)
        if isinstance(ctl, Gtk.Switch):
            ctl.set_hexpand(False)
            ctl.set_halign(Gtk.Align.END)
        else:
            ctl.set_hexpand(True)
        if ctl.get_valign() == Gtk.Align.FILL:
            ctl.set_valign(Gtk.Align.CENTER)
        grid.attach(ctl, 1, row, 1, 1)


    def section(self, title, expanded=True, collapsible=False):
        """Grouped block with a small header; collapsible ones use a Gtk.Expander. Returns (widget, grid)."""
        grid = Gtk.Grid(column_spacing=12, row_spacing=4)
        if collapsible:
            wrap = Gtk.Expander(label=title.upper(), expanded=expanded)
            grid.set_margin_top(8)
            wrap.add(grid)
        else:
            wrap = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            wrap.pack_start(self.label(title.upper(), "group-title"), False, False, 0)
            wrap.pack_start(grid, False, False, 0)
        return self.styled(wrap, "section"), grid


    def scroller(self, child, max_h=None):
        """Panels never grow off-screen: content scrolls inside a capped height."""
        cap = max_h or (self.wa["height"] - 220)
        scroll = Gtk.ScrolledWindow(max_content_height=max(200, min(cap, self.wa["height"] - 220)),
                                    propagate_natural_height=True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.add(child)
        return scroll


    @staticmethod
    def clear(box):
        for child in box.get_children():
            box.remove(child)


    @staticmethod
    def reveal(panel):
        # show_all() skips widgets marked no_show_all, so lift it for this call.
        panel.set_no_show_all(False)
        panel.show_all()
        panel.set_no_show_all(True)


    def reveal_panel(self, revealer, panel=None):
        revealer.show_all()
        self.overlay.set_overlay_pass_through(revealer, False)
        self.overlay.reorder_overlay(revealer, -1)
        revealer.set_reveal_child(True)
        win = revealer.get_window()
        if win:
            win.raise_()


    def hide_panel(self, revealer):
        revealer.set_reveal_child(False)
        self.overlay.set_overlay_pass_through(revealer, True)


    def close_panels(self):
        self.hide_panel(self.palette_revealer)
        self.hide_panel(self.settings_revealer)
        self.hide_panel(self.workspace_revealer)
        self.hide_panel(self.grid_revealer)
        self.hide_panel(self.profiles_revealer)
        self.hide_panel(self.style_revealer)
        self.current_settings_wid = None
        self.last_settings_rect = None
        self.set_focus(None)


    def close_settings(self):
        self.hide_panel(self.settings_revealer)
        self.hide_panel(self.workspace_revealer)
        self.current_settings_wid = None
        self.last_settings_rect = None
        self.set_focus(None)


    def close_workspace_panel(self):
        self.hide_panel(self.workspace_revealer)
        self.set_focus(None)


    def close_grid_panel(self):
        self.hide_panel(self.grid_revealer)
        self.set_focus(None)


    def close_profiles_panel(self):
        self.hide_panel(self.profiles_revealer)
        self.set_focus(None)


    def close_style_panel(self):
        self.hide_panel(self.style_revealer)
        self.set_focus(None)


    def open_style_panel(self):
        """Dedicated popup panel to select and manage general widget style (skin & fx)."""
        self.close_panels()
        box = self.style_panel
        self.clear(box)

        box.pack_start(self.header("󰔎", "Estilo general de widgets", revealer=self.style_revealer), False, False, 0)

        section, grid = self.section("Global")
        style = W.load_style()

        combo_skin = Gtk.ComboBoxText()
        for k in W.EDITOR_SKIN_KEYS:
            combo_skin.append(k, W.SKIN_LABELS.get(k, k))
        cur_skin = style.get("skin", "bento")
        combo_skin.set_active_id(cur_skin if cur_skin in W.EDITOR_SKIN_KEYS else "bento")
        self.form_row(grid, 0, "Estilo", combo_skin, "Estilo global")

        combo_fx = Gtk.ComboBoxText()
        for k in W.EDITOR_FX_KEYS:
            combo_fx.append(k, W.FX_LABELS.get(k, k))
        cur_fx = style.get("fx", "none")
        combo_fx.set_active_id(cur_fx if cur_fx in W.EDITOR_FX_KEYS else "none")
        self.form_row(grid, 1, "Efecto", combo_fx, "Efecto visual (efecto) global")

        lbl_desc = self.label(W.FX_DESCRIPTIONS.get(cur_fx, ""), "panel-sub", wrap=True, width=36)
        grid.attach(lbl_desc, 0, 2, 2, 1)

        combo_background=Gtk.ComboBoxText()
        for key in W.BACKGROUNDS:combo_background.append(key,W.BACKGROUND_LABELS[key])
        combo_background.set_active_id(style.get('background','surface'))
        self.form_row(grid,3,'Fondo',combo_background,'Color derivado de la paleta activa')

        def on_style_changed(*_):
            new_skin = combo_skin.get_active_id() or "bento"
            new_fx = combo_fx.get_active_id() or "none"
            W.save_style(skin=new_skin, fx=new_fx,background=combo_background.get_active_id() or 'surface')
            lbl_desc.set_text(W.FX_DESCRIPTIONS.get(new_fx, ""))
            self.area.queue_draw()

        combo_skin.connect("changed", on_style_changed)
        combo_fx.connect("changed", on_style_changed)
        combo_background.connect('changed',on_style_changed)
        box.pack_start(section, False, False, 0)

        def test_live_juice():
            import threading
            fx = combo_fx.get_active_id() or "glow"
            threading.Thread(target=lambda: W.preview_fx(fx, 4.0), daemon=True).start()

        # Helper button: reset all widgets to inherit the global style
        def apply_to_all():
            self.push_undo()
            for w in self.widgets:
                w.setdefault("opts", {})["skin"] = "global"
                w.setdefault("opts", {})["fx"] = "global"
            self.apply()

        foot = Gtk.Box(spacing=4)
        foot.pack_start(self.button("󰐊 Probar", test_live_juice,
                                    tooltip="Probar efecto en vivo en el escritorio"), False, False, 0)
        foot.pack_start(self.icon_button("󰄬", "Aplicar estilo global a todos los widgets", apply_to_all),
                        False, False, 0)
        foot.pack_end(self.button("Listo", self.close_panels, "primary"), False, False, 0)
        box.pack_start(foot, False, False, 0)

        self.style_panel.show_all()
        pw = 340
        _, nat_h = self.style_panel.get_preferred_height()
        ph = min(nat_h, self.wa["height"] - 140) if nat_h > 0 else 280
        cx = max(self.wa["x"] + 12, self.wa["x"] + (self.wa["width"] - pw) // 2)
        cy = max(self.wa["y"] + 40, self.wa["y"] + (self.wa["height"] - ph) // 2)
        self.style_revealer.set_margin_start(int(cx))
        self.style_revealer.set_margin_top(int(cy))
        self.reveal_panel(self.style_revealer, self.style_panel)


    def open_profiles_panel(self):
        """Dedicated popup panel to select and manage desktop modes / profiles."""
        self.close_panels()
        box = self.profiles_panel
        self.clear(box)

        box.pack_start(self.header("󰏘", "Modos y Perfiles", revealer=self.profiles_revealer), False, False, 0)

        profiles = W.list_profiles()
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)

        for p in profiles:
            p_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            icon_lbl = self.label(p.get("icon", "󰏘"), "wcard-icon")
            icon_lbl.set_valign(Gtk.Align.CENTER)
            p_box.pack_start(icon_lbl, False, False, 0)

            t_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0, valign=Gtk.Align.CENTER)
            t_box.pack_start(self.label(p.get("name", p["id"]), "wcard-name"), False, False, 0)
            desc_lbl = self.label(p.get("desc", ""), "wcard-desc", wrap=True, width=30)
            t_box.pack_start(desc_lbl, False, False, 0)
            p_box.pack_start(t_box, True, True, 0)

            apply_btn = self.button("Aplicar", lambda pid=p["id"]: self.apply_profile_action(pid), "primary")
            apply_btn.set_valign(Gtk.Align.CENTER)
            p_box.pack_end(apply_btn, False, False, 0)

            card = self.styled(Gtk.Box(), "wcard")
            card.pack_start(p_box, True, True, 0)
            content.pack_start(card, False, False, 0)

        box.pack_start(self.scroller(content, 320), False, False, 0)

        # Quick save current layout as new profile
        save_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        entry = Gtk.Entry(placeholder_text="Guardar diseño actual como…", hexpand=True)
        entry.get_style_context().add_class("textbox")
        save_box.pack_start(entry, True, True, 0)

        def save_new():
            name = entry.get_text().strip()
            if name:
                W.save_current_as_profile(name)
                self.open_profiles_panel()

        entry.connect("activate", lambda *_: save_new())
        save_box.pack_start(self.icon_button("󰆓", "Guardar como perfil nuevo", save_new), False, False, 0)
        save_box.pack_end(self.button("Listo", self.close_panels, "primary"), False, False, 0)
        box.pack_start(save_box, False, False, 0)

        self.profiles_panel.show_all()
        pw = 380
        _, nat_h = self.profiles_panel.get_preferred_height()
        ph = min(nat_h, self.wa["height"] - 140) if nat_h > 0 else 360
        cx = max(self.wa["x"] + 12, self.wa["x"] + (self.wa["width"] - pw) // 2)
        cy = max(self.wa["y"] + 40, self.wa["y"] + (self.wa["height"] - ph) // 2)
        self.profiles_revealer.set_margin_start(int(cx))
        self.profiles_revealer.set_margin_top(int(cy))
        self.reveal_panel(self.profiles_revealer, self.profiles_panel)


    def apply_profile_action(self, profile_id):
        self.push_undo()
        self.selected_wid = None
        self.current_settings_wid = None
        self.hover = None
        self.drag = None
        self.guides = []
        W.apply_profile(profile_id,reconcile=False)
        self.request_sync()
        W._last_editor_save = W.load()
        self.widgets = W.load()
        rects = {}
        for w in self.widgets:
            wid = w["id"]
            kind = w.get("window", "")
            default_sz = DEFAULT_SIZES.get(kind, DEFAULT_SIZE)
            opt_w = int(w.get("opts", {}).get("width", 0)) if str(w.get("opts", {}).get("width", "")).isdigit() else 0
            opt_h = int(w.get("opts", {}).get("height", 0)) if str(w.get("opts", {}).get("height", "")).isdigit() else 0
            sz_w = opt_w if opt_w >= 40 else default_sz[0]
            sz_h = opt_h if opt_h >= 40 else default_sz[1]
            size = (sz_w, sz_h)
            self.prefs["sizes"][wid] = [sz_w, sz_h]
            x, y = self.expected_corner(w, size)
            rects[wid] = [int(x), int(y), int(size[0]), int(size[1])]
        self.rects = rects
        self.close_panels()
        self.area.queue_draw()
        GLib.timeout_add(350, lambda: self.settle() or False)


    def show_palette(self):
        self.close_panels()
        box = self.palette_panel
        self.clear(box)
        box.pack_start(self.header("󰐕", "Agregar widget", revealer=self.palette_revealer),
                       False, False, 0)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)

        groups = (("Widgets del sistema", None), ("Genéricos", "generic"))
        for title, group in groups:
            content.pack_start(self.label(title.upper(), "group-title"), False, False, 0)
            flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=2,
                                min_children_per_line=2, column_spacing=4, row_spacing=4, homogeneous=True)
            for kind, meta in W.SCHEMA.items():
                if meta.get("group") == group:
                    flow.add(self.palette_card(kind, meta))
            content.pack_start(flow, False, False, 0)

        box.pack_start(self.scroller(content, 380), False, False, 0)

        foot = Gtk.Box(spacing=4)
        foot.pack_end(self.button("Cerrar", self.close_panels), False, False, 0)
        box.pack_start(foot, False, False, 0)

        self.palette_panel.show_all()
        pw = 360
        _, nat_h = self.palette_panel.get_preferred_height()
        ph = min(nat_h, self.wa["height"] - 140) if nat_h > 0 else 340
        cx = max(self.wa["x"] + 12, self.wa["x"] + (self.wa["width"] - pw) // 2)
        cy = max(self.wa["y"] + 30, self.wa["y"] + (self.wa["height"] - ph) // 2)
        self.palette_revealer.set_margin_start(int(cx))
        self.palette_revealer.set_margin_top(int(cy))
        self.reveal_panel(self.palette_revealer, self.palette_panel)


    def palette_card(self, kind, meta):
        instances = [w for w in self.widgets if w["window"] == kind]
        hidden = [w for w in instances if not w["show"]]
        if hidden:
            tag, tag_cls, action = "󰈈 Oculto", "wcard-tag-warn", (lambda wid=hidden[0]["id"]: self.unhide(wid))
        elif instances and meta.get("single"):
            tag, tag_cls, action = "󰄬 En uso", "wcard-tag-dim", None
        elif instances:
            tag, tag_cls, action = f"+ Añadir ({len(instances)})", "wcard-tag-ok", (lambda k=kind: self.add_widget(k))
        else:
            tag, tag_cls, action = "+ Añadir", "wcard-tag-ok", (lambda k=kind: self.add_widget(k))

        card_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        card_box.set_tooltip_text(meta["name"] + ((" · Falta: " + ", ".join(meta["requires_missing"])) if meta.get("requires_missing") else ""))
        icon_lbl = self.label(meta["icon"], "wcard-icon")
        icon_lbl.set_valign(Gtk.Align.CENTER)
        card_box.pack_start(icon_lbl, False, False, 0)

        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        name_lbl = self.label(meta["name"], "wcard-name")
        name_lbl.set_ellipsize(Pango.EllipsizeMode.END)
        name_lbl.set_valign(Gtk.Align.CENTER)
        text_box.set_valign(Gtk.Align.CENTER)
        text_box.pack_start(name_lbl, False, False, 0)
        card_box.pack_start(text_box, True, True, 0)

        tag_lbl = self.label(tag, "wcard-tag", tag_cls)
        tag_lbl.set_valign(Gtk.Align.CENTER)
        card_box.pack_end(tag_lbl, False, False, 0)

        card = self.styled(Gtk.Button(), "wcard")
        card.add(card_box)
        card.set_sensitive(action is not None and not meta.get("requires_missing"))
        if action:
            card.connect("clicked", lambda *_, a=action: a())
        return card


    def unhide(self, wid):
        w = W.find(self.widgets, wid)
        if w:
            w["show"] = True
            self.close_panels()
            self.apply()
            self.trigger_add_pulse(wid)


    def add_widget(self, kind):
        try:
            if not W.ensure_current(kind): return
        except (ValueError, OSError) as exc:
            self.show_toast(str(exc))
            return
        base = W.SCHEMA[kind].get("base_id", kind)
        wid, n = base, 2
        while W.find(self.widgets, wid):
            wid, n = f"{base}{n}", n + 1
        cur_ws = self.filter_ws if isinstance(self.filter_ws, int) else getattr(self, "current_ws_num", 1)
        opts = {"workspace": f"Workspace {cur_ws}" if self.filter_ws is not None else "Global", "skin": "global", "fx": "global", "anim": "global", "anim_out": "global"}
        self.push_undo()
        self.widgets.append({"id": wid, "window": kind, "show": True, "anchor": "top-left",
                             "x": 0, "y": 0, "opts": opts})
        size = tuple(self.prefs["sizes"].get(wid, DEFAULT_SIZES.get(kind, DEFAULT_SIZE)))
        wa = self.wa
        self.rects[wid] = [wa["x"] + (wa["width"] - size[0]) // 2,
                           wa["y"] + (wa["height"] - size[1]) // 2, size[0], size[1]]
        self.close_panels()
        self.apply()
        self.trigger_add_pulse(wid)


    def set_option(self, wid, key, value):
        w = W.find(self.widgets, wid)
        if not w:
            return
        w["opts"][key] = value
        if w["window"] in ("photo", "image") and key in ("width", "height") and value.isdigit():
            if w["window"] == "photo":
                W.set_photo_size(w, *(w["opts"].get(k, "360") for k in ("width", "height")))
            else:
                w["opts"][key] = value
            r = self.rects[wid]
            r[2], r[3] = int(w["opts"]["width"]), int(w["opts"]["height"])
            self.area.queue_draw()
        if self.debounce:
            GLib.source_remove(self.debounce)
        self.debounce = GLib.timeout_add(450, self._debounced_apply)


    def _debounced_apply(self):
        self.debounce = None
        self.apply()
        return False


    def choose_folder(self, entry):
        self.hide()
        dialog = Gtk.FileChooserDialog(title="Carpeta de imágenes", action=Gtk.FileChooserAction.SELECT_FOLDER)
        dialog.add_buttons("Cancelar", Gtk.ResponseType.CANCEL, "Elegir", Gtk.ResponseType.OK)
        current = os.path.expanduser(entry.get_text() or "~")
        if os.path.isdir(current):
            dialog.set_current_folder(current)
        if dialog.run() == Gtk.ResponseType.OK:
            entry.set_text(dialog.get_filename().replace(os.path.expanduser("~"), "~", 1))
        dialog.destroy()
        self.show_all()


    def choose_file(self, entry):
        self.hide()
        dialog = Gtk.FileChooserDialog(title="Elegir archivo de imagen", action=Gtk.FileChooserAction.OPEN)
        dialog.add_buttons("Cancelar", Gtk.ResponseType.CANCEL, "Elegir", Gtk.ResponseType.OK)
        img_filter = Gtk.FileFilter()
        img_filter.set_name("Imágenes (*.png, *.jpg, *.jpeg, *.webp, *.gif)")
        for ext in ("*.png", "*.jpg", "*.jpeg", "*.webp", "*.gif", "*.PNG", "*.JPG", "*.JPEG", "*.WEBP", "*.GIF"):
            img_filter.add_pattern(ext)
        dialog.add_filter(img_filter)
        all_filter = Gtk.FileFilter()
        all_filter.set_name("Todos los archivos")
        all_filter.add_pattern("*")
        dialog.add_filter(all_filter)
        current = os.path.expanduser(entry.get_text() or "~")
        if os.path.isfile(current):
            dialog.set_filename(current)
        elif os.path.isdir(current):
            dialog.set_current_folder(current)
        if dialog.run() == Gtk.ResponseType.OK:
            entry.set_text(dialog.get_filename().replace(os.path.expanduser("~"), "~", 1))
        dialog.destroy()
        self.show_all()


    def build_workspace_selector(self, wid, key, value):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        raw = str(value or "Todos").strip()
        is_todos = not raw or raw.lower() in ("todos", "global", "all", "*")
        selected_nums = set()
        if not is_todos:
            for part in raw.split(","):
                m = re.search(r"\d+", part)
                if m:
                    selected_nums.add(int(m.group()))
            if not selected_nums:
                is_todos = True

        updating = False

        def get_display_text():
            if is_todos or not selected_nums:
                return "󰈈 Global · visible en cada escritorio"
            return "󰨇 Visible en: " + ", ".join(f"W-{n}" for n in sorted(selected_nums))

        lbl = self.label(get_display_text(), "panel-sub")
        btn_todos = self.styled(Gtk.ToggleButton(label="󰈈  Global"), "ws-pill", "todos")
        btn_todos.set_halign(Gtk.Align.START)
        btn_todos.set_active(is_todos)

        row_nums = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        num_buttons = {}

        def on_todos_toggled(btn):
            nonlocal is_todos, updating
            if updating:
                return
            updating = True
            if btn.get_active():
                is_todos = True
                selected_nums.clear()
                for b in num_buttons.values():
                    b.set_active(False)
                self.set_option(wid, key, "Global")
            else:
                if not selected_nums:
                    cur = getattr(self, "current_ws_num", 1)
                    selected_nums.add(cur)
                    num_buttons[cur].set_active(True)
                    self.set_option(wid, key, f"Workspace {cur}")
                    is_todos = False
            lbl.set_text(get_display_text())
            updating = False

        def on_num_toggled(btn, num):
            nonlocal is_todos, updating
            if updating:
                return
            updating = True
            if btn.get_active():
                selected_nums.add(num)
                is_todos = False
                btn_todos.set_active(False)
            else:
                selected_nums.discard(num)
                if not selected_nums:
                    is_todos = True
                    btn_todos.set_active(True)

            if is_todos:
                self.set_option(wid, key, "Global")
            else:
                sorted_nums = sorted(selected_nums)
                if len(sorted_nums) == 1:
                    val_str = f"Workspace {sorted_nums[0]}"
                else:
                    val_str = ", ".join(f"Workspace {n}" for n in sorted_nums)
                self.set_option(wid, key, val_str)
            lbl.set_text(get_display_text())
            updating = False

        btn_todos.connect("toggled", on_todos_toggled)

        for i in range(1, 10):
            b = self.styled(Gtk.ToggleButton(label=str(i)), "ws-pill")
            b.set_tooltip_text(f"Workspace {i}")
            b.set_active(i in selected_nums)
            b.connect("toggled", on_num_toggled, i)
            num_buttons[i] = b
            row_nums.pack_start(b, False, False, 0)

        box.pack_start(btn_todos, False, False, 0)
        box.pack_start(row_nums, False, False, 0)
        box.pack_start(lbl, False, False, 0)
        return box


    def toggle_workspace_panel(self, wid=None):
        if self.workspace_revealer.get_reveal_child():
            self.workspace_revealer.set_reveal_child(False)
        else:
            self.open_workspace_panel(wid)


    def open_workspace_panel(self, target_wid=None):
        """Dedicated window/panel to assign workspaces to widgets without closing widget settings."""
        self.palette_revealer.set_reveal_child(False)
        box = self.workspace_panel
        self.clear(box)

        box.pack_start(self.header("󰍹", "Asignar escritorios", revealer=self.workspace_revealer),
                       False, False, 0)

        if not self.widgets:
            box.pack_start(self.label("No hay widgets configurados.", "panel-sub"), False, False, 4)
            foot = Gtk.Box(spacing=4)
            foot.pack_end(self.button("Listo", self.close_workspace_panel, "primary"), False, False, 0)
            box.pack_start(foot, False, False, 0)
            self.workspace_panel.show_all()
            self.workspace_revealer.show_all()
            self.overlay.reorder_overlay(self.workspace_revealer, -1)
            self.workspace_revealer.set_reveal_child(True)
            return

        initial_wid = target_wid or getattr(self, "current_settings_wid", None) or self.hover or self.widgets[0]["id"]
        if not W.find(self.widgets, initial_wid):
            initial_wid = self.widgets[0]["id"]

        picker_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        picker_lbl = self.label("Widget", "field")
        picker_lbl.set_valign(Gtk.Align.CENTER)
        picker_box.pack_start(picker_lbl, False, False, 0)

        combo = Gtk.ComboBoxText()
        combo_wids = []
        active_idx = 0
        for i, w in enumerate(self.widgets):
            wname = W.KINDS.get(w["window"], w["window"])
            combo.append_text(f"{w['id']} · {wname}")
            combo_wids.append(w["id"])
            if w["id"] == initial_wid:
                active_idx = i

        combo.set_active(active_idx)
        combo.set_hexpand(True)
        picker_box.pack_start(combo, True, True, 0)
        box.pack_start(picker_box, False, False, 0)

        selector_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.pack_start(selector_container, False, False, 0)

        current_active = [initial_wid]

        def update_selector(wid):
            self.clear(selector_container)
            current_active[0] = wid
            w = W.find(self.widgets, wid)
            if not w:
                return
            val = w.get("opts", {}).get("workspace", "Todos")
            ctl = self.build_workspace_selector(wid, "workspace", val)
            selector_container.pack_start(ctl, False, False, 0)
            self.workspace_panel.show_all()

        update_selector(initial_wid)

        def on_combo_changed(c):
            idx = c.get_active()
            if 0 <= idx < len(combo_wids):
                update_selector(combo_wids[idx])

        combo.connect("changed", on_combo_changed)

        foot = Gtk.Box(spacing=4)
        foot.pack_end(self.button("Listo", self.close_workspace_panel, "primary"), False, False, 0)
        box.pack_start(foot, False, False, 0)

        self.workspace_panel.show_all()
        avoid = getattr(self, "last_settings_rect", None) if self.settings_revealer.get_reveal_child() else None
        self.position_panel_near_widget(self.workspace_revealer, self.workspace_panel, initial_wid, avoid_rect=avoid)
        self.reveal_panel(self.workspace_revealer, self.workspace_panel)


    def toggle_grid_panel(self):
        if self.grid_revealer.get_reveal_child():
            self.close_grid_panel()
        else:
            self.open_grid_panel()


    def open_grid_panel(self):
        """Dedicated popup panel to select grid snap options: Desactivado, 5px, 10px, 20px, 30px."""
        self.close_panels()
        box = self.grid_panel
        self.clear(box)

        box.pack_start(self.header("󰆾", "Cuadrícula y Alineación", revealer=self.grid_revealer),
                       False, False, 0)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4, halign=Gtk.Align.CENTER)

        options = [
            ("Off", False, None),
            ("5px", True, 5),
            ("10px", True, 10),
            ("20px", True, 20),
            ("30px", True, 30),
        ]

        def set_grid_option(enabled, step_val):
            self.prefs["grid"] = enabled
            if step_val is not None:
                self.prefs["step"] = step_val
            save_prefs(self.prefs)
            self.area.queue_draw()
            self.open_grid_panel()

        for label, enabled, step_val in options:
            is_active = (not self.prefs["grid"] and not enabled) or (self.prefs["grid"] and enabled and self.prefs["step"] == step_val)
            btn = self.styled(Gtk.Button(label=label), "pbtn", *(("primary",) if is_active else ()))
            btn.connect("clicked", lambda _b, en=enabled, st=step_val: set_grid_option(en, st))
            row.pack_start(btn, False, False, 0)

        box.pack_start(row, False, False, 0)

        foot = Gtk.Box(spacing=4)
        foot.pack_start(self.label("G: activar/desactivar  ·  [ ]: tamaño", "panel-sub"), False, False, 0)
        foot.pack_end(self.button("Listo", self.close_grid_panel, "primary"), False, False, 0)
        box.pack_start(foot, False, False, 0)

        wa = self.wa
        pw = 320
        cx = wa["x"] + (wa["width"] - pw) // 2
        cy = wa["y"] + 72
        self.grid_revealer.set_margin_start(int(cx))
        self.grid_revealer.set_margin_top(int(cy))
        self.grid_panel.show_all()
        self.reveal_panel(self.grid_revealer, self.grid_panel)
