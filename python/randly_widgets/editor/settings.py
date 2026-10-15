from .common import *

class SettingsMixin:
    def open_settings(self, wid):
        w = W.find(self.widgets, wid)
        if not w:
            return
        self.hide_panel(self.palette_revealer)
        self.current_settings_wid = wid
        meta = W.SCHEMA.get(w["window"], {"icon": "?", "name": w["window"], "options": []})
        box = self.settings_panel
        self.clear(box)
        box.pack_start(self.header(meta["icon"], f"{meta['name']} · {wid}",
                                   revealer=self.settings_revealer), False, False, 0)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        general, grid = self.section("Ajustes")
        content.pack_start(general, False, False, 0)
        if not meta["options"]:
            grid.attach(self.label("Este widget no tiene ajustes.", "panel-sub"), 0, 0, 2, 1)
        current = W.options(w)
        shown = [o for o in meta["options"] if o[2] != "size" and o[0] not in ("workspace", "anim", "anim_out", "skin", "fx", "background", "motion_mode")]
        if meta["options"] and not shown:
            grid.attach(self.label("Solo tamaño: arrastra sus puntos.", "panel-sub"), 0, 0, 2, 1)
        for row, (key, text, kind, default, *rest) in enumerate(shown):
            value = str(current.get(key, default))
            if kind == "bool":
                ctl = Gtk.Switch(active=value == "yes")
                ctl.connect("notify::active",
                            lambda s, _p, k=key: self.set_option(wid, k, "yes" if s.get_active() else "no"))
            elif kind == "choice":
                ctl = Gtk.ComboBoxText()
                for choice in rest[0]:
                    ctl.append_text(choice)
                ctl.set_active(rest[0].index(value) if value in rest[0] else 0)
                ctl.connect("changed", lambda c, k=key: self.set_option(wid, k, c.get_active_text()))
            elif kind == "int":
                ctl = Gtk.SpinButton.new_with_range(0, 4000, 1)
                ctl.set_value(int(value) if value.lstrip("-").isdigit() else int(default))
                ctl.connect("value-changed", lambda s, k=key: self.set_option(wid, k, str(int(s.get_value()))))
            elif kind == "longtext":
                view = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR)
                view.get_buffer().set_text(value.replace("\\n", "\n"))
                view.get_buffer().connect("changed", lambda b, k=key: self.set_option(
                    wid, k, b.get_text(b.get_start_iter(), b.get_end_iter(), False).replace("\n", "\\n")))
                ctl = Gtk.ScrolledWindow(min_content_height=72, max_content_height=140)
                ctl.get_style_context().add_class("textbox")
                ctl.add(view)
                ctl.set_valign(Gtk.Align.START)
            elif kind in ("dir", "file"):
                ctl = Gtk.Box(spacing=4)
                entry = Gtk.Entry(text=value, hexpand=True)
                entry.connect("changed", lambda e, k=key: self.set_option(wid, k, e.get_text()))
                pick = self.icon_button("󰉋" if kind == "dir" else "󰈔",
                                        "Elegir carpeta" if kind == "dir" else "Elegir archivo",
                                        lambda e=entry, knd=kind: (
                                            self.choose_file(e) if knd == "file" else self.choose_folder(e)))
                ctl.pack_start(entry, True, True, 0)
                ctl.pack_start(pick, False, False, 0)
            else:
                ctl = Gtk.Entry(text=value)
                ctl.connect("changed", lambda e, k=key: self.set_option(wid, k, e.get_text()))
            self.form_row(grid, row, text, ctl)

        # Per-widget skin, animation, and juice: advanced, collapsed by default.
        look, grid = self.section("Apariencia y animación", expanded=False, collapsible=True)
        content.pack_start(look, False, False, 0)

        def choice_combo(key, inherit, keys, labels, normalize):
            combo = Gtk.ComboBoxText()
            combo.append("global", inherit)
            for k in keys:
                combo.append(k, labels.get(k, k))
            cur = w.get("opts", {}).get(key, "global") or "global"
            if cur != "global":
                cur = normalize(cur)
            combo.set_active_id(cur if cur in keys or cur == "global" else "global")
            combo.connect("changed", lambda c: self.set_option(wid, key, c.get_active_id() or "global"))
            return combo

        self.form_row(grid, 0, "Skin", choice_combo(
            "skin", "Heredar (general)", W.EDITOR_SKIN_KEYS, W.SKIN_LABELS, W.normalize_skin), "Skin del widget")
        self.form_row(grid, 1, "Entrada", choice_combo(
            "anim", "Heredar (global)", W.EDITOR_ANIM_KEYS, W.ANIM_LABELS, W.normalize_anim), "Animación de entrada")
        self.form_row(grid, 2, "Salida", choice_combo(
            "anim_out", "Heredar (global)", W.EDITOR_ANIM_KEYS, W.ANIM_LABELS, W.normalize_anim), "Animación de salida")
        self.form_row(grid, 3, "Juice", choice_combo(
            "fx", "Heredar (general)", W.EDITOR_FX_KEYS, W.FX_LABELS, W.normalize_fx), "Efecto visual (Juice)")
        self.form_row(grid,4,'Fondo',choice_combo('background','Heredar (general)',W.BACKGROUNDS,W.BACKGROUND_LABELS,W.normalize_background))
        self.form_row(grid,5,'Tamaño dinámico',choice_combo('motion_mode','Heredar (general)',W.SIZE_KEYS,W.SIZE_LABELS,lambda value:value))

        box.pack_start(self.scroller(content, 460), False, False, 0)

        foot = Gtk.Box(spacing=4)
        foot.pack_start(self.icon_button("󰈈" if not w["show"] else "󰈉", "Mostrar" if not w["show"] else "Ocultar",
                                         lambda: self.toggle_show(wid)), False, False, 0)
        foot.pack_start(self.icon_button("󰍹", "Escritorios", lambda: self.toggle_workspace_panel(wid)),
                        False, False, 0)
        foot.pack_start(self.icon_button("󰆴", "Eliminar widget", lambda: self.remove_widget(wid), "danger"),
                        False, False, 0)
        foot.pack_end(self.button("Listo", self.close_settings, "primary"), False, False, 0)
        box.pack_start(foot, False, False, 0)

        self.settings_panel.show_all()
        self.last_settings_rect = self.position_panel_near_widget(
            self.settings_revealer, self.settings_panel, wid)
        self.reveal_panel(self.settings_revealer, self.settings_panel)


    def open_animation(self):
        """Global open/close animation of the widgets (configured via code keys)."""
        self.close_panels()
        anim = W.load_animation()
        box = self.settings_panel
        self.clear(box)
        box.pack_start(self.header("󱐋", "Animación de los widgets", "Efectos de Wayfire al aparecer/desaparecer",
                                   revealer=self.settings_revealer), False, False, 0)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        combos = {}
        self.anim_combos = combos
        spins = {}
        switches = {}

        def anim_combo(key, default, keys=W.EDITOR_ANIM_KEYS):
            combo = Gtk.ComboBoxText()
            for k in keys:
                combo.append(k, W.ANIM_LABELS.get(k, k))
            cur = anim.get(key, default)
            combo.set_active_id(cur if cur in keys else default)
            combo.set_tooltip_text(W.ANIM_DESCRIPTIONS.get(combo.get_active_id(), ""))
            combo.connect("changed", lambda c: c.set_tooltip_text(W.ANIM_DESCRIPTIONS.get(c.get_active_id(), "")))
            combos[key] = combo
            return combo

        def spin(key, lo, hi, step, default):
            sp = Gtk.SpinButton.new_with_range(lo, hi, step)
            sp.set_value(anim.get(key, default))
            spins[key] = sp
            return sp

        # Effects: in/out pairs with their own duration.
        effects, grid = self.section("Efectos")
        content.pack_start(effects, False, False, 0)
        self.form_row(grid, 0, "Entrada", anim_combo("anim_in", "slide", W.EDITOR_ANIM_KEYS), "Animación al aparecer")
        self.form_row(grid, 1, "Duración entrada (ms)", spin("duration_in", 50, 1500, 20, 340))
        self.form_row(grid, 2, "Salida", anim_combo("anim_out", "fade", W.EDITOR_ANIM_KEYS), "Animación al desaparecer")
        self.form_row(grid, 3, "Duración salida (ms)", spin("duration_out", 50, 1500, 20, 220))
        size_mode=Gtk.ComboBoxText()
        for key in W.SIZE_KEYS:size_mode.append(key,W.SIZE_LABELS[key])
        size_mode.set_active_id(anim.get('size_mode','stable'))
        self.form_row(grid,5,'Tamaño dinámico',size_mode,'Esperar el contenido estable o dividir fundido y expansión')
        desc = self.label("", "panel-sub", wrap=True, width=36)
        grid.attach(desc, 0, 4, 2, 1)

        def update_desc(*_):
            parts = [W.ANIM_DESCRIPTIONS.get(combos[k].get_active_id(), "") for k in ("anim_in", "anim_out")]
            desc.set_text(f"Entrada: {parts[0]}\nSalida: {parts[1]}")
        update_desc()

        combo_when = Gtk.ComboBoxText()
        for k in W.WHEN_KEYS:
            combo_when.append(k, W.WHEN_LABELS.get(k, k))
        current_when = anim.get("when", "workspace")
        combo_when.set_active_id(current_when if current_when in W.WHEN_KEYS else "workspace")
        combos["when"] = combo_when
        self.form_row(grid, 6, "Cuándo animar", combo_when)

        # Cascade: advanced, collapsed by default.
        cascade, grid = self.section("Cascada", expanded=False, collapsible=True)
        content.pack_start(cascade, False, False, 0)
        order = Gtk.ComboBoxText()
        for k in W.ORDER_KEYS:
            order.append(k, W.ORDER_LABELS.get(k, k))
        current_ord = anim.get("order", "config")
        order.set_active_id(current_ord if current_ord in W.ORDER_KEYS else "config")
        self.form_row(grid, 0, "Orden", order, "Orden en cascada")
        self.form_row(grid, 1, "Pausa (ms)", spin("stagger", 0, 500, 5, 25), "Pausa entre widgets (ms)")
        self.form_row(grid, 2, "Aleatoriedad (± ms)", spin("jitter", 0, 500, 5, 10))
        for row, (key, text, default) in enumerate((("stagger_in", "Al aparecer", True),
                                                    ("stagger_out", "Al desaparecer", False)), start=3):
            sw = Gtk.Switch(active=bool(anim.get(key, default)))
            switches[key] = sw
            self.form_row(grid, row, text, sw, f"Cascada {text.lower()}")

        def changed(*_):
            update_desc()
            W.save_animation(
                anim_in=combos["anim_in"].get_active_id() or "zoom",
                anim_out=combos["anim_out"].get_active_id() or "fade",
                when=combos["when"].get_active_id() or "workspace",
                order=order.get_active_id() or "config",
                duration_in=int(spins["duration_in"].get_value()),
                duration_out=int(spins["duration_out"].get_value()),
                stagger=int(spins["stagger"].get_value()),
                jitter=int(spins["jitter"].get_value()),
                stagger_in=switches["stagger_in"].get_active(),
                stagger_out=switches["stagger_out"].get_active(),
                size_mode=size_mode.get_active_id() or 'stable',
            )

        for combo in list(combos.values()) + [order,size_mode]:
            combo.connect("changed", changed)
        for sp in spins.values():
            sp.connect("value-changed", changed)
        for sw in switches.values():
            sw.connect("notify::active", changed)

        box.pack_start(self.scroller(content, 480), False, False, 0)

        foot = Gtk.Box(spacing=4)
        foot.pack_start(self.button("󰐊 Probar", self.test_animation,
                                    tooltip="Reproduce salida y entrada en los widgets"), False, False, 0)
        foot.pack_end(self.button("Listo", self.close_settings, "primary"), False, False, 0)
        box.pack_start(foot, False, False, 0)

        wa = self.wa
        pw = 340
        cx = wa["x"] + (wa["width"] - pw) // 2
        cy = max(wa["y"] + 72, wa["y"] + (wa["height"] - 440) // 2)
        self.settings_revealer.set_margin_start(int(cx))
        self.settings_revealer.set_margin_top(int(cy))
        self.settings_panel.show_all()
        self.reveal_panel(self.settings_revealer, self.settings_panel)


    def test_animation(self):
        # Trigger smooth preview without full daemon reload
        cmd = [os.path.join(W.EWW_DIR, "scripts", "widgets"), "preview-anim"]
        if hasattr(self, "anim_combos") and self.anim_combos:
            combo_in = self.anim_combos.get("anim_in")
            combo_out = self.anim_combos.get("anim_out")
            if combo_in and combo_out:
                c_in = combo_in.get_active_id()
                c_out = combo_out.get_active_id()
                if c_in:
                    cmd.append(c_in)
                if c_out:
                    cmd.append(c_out)
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
