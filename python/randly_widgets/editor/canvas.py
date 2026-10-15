from .common import *
from randly_widgets.editor_paint import GridCache,widget_bounds,union,pixel_bounds,intersects

class CanvasMixin:
    @staticmethod
    def rounded(cr, x, y, w, h, r):
        r = min(r, w / 2, h / 2)
        cr.new_sub_path()
        cr.arc(x + w - r, y + r, r, -1.5708, 0)
        cr.arc(x + w - r, y + h - r, r, 0, 1.5708)
        cr.arc(x + r, y + h - r, r, 1.5708, 3.1416)
        cr.arc(x + r, y + r, r, 3.1416, 4.7124)
        cr.close_path()


    def text(self, cr, s, x, y, size=13, color=None, bold=False):
        font_face = "JetBrainsMono Nerd Font" if any(ord(ch) >= 0xe000 for ch in s) else "Inter"
        cr.select_font_face(font_face, cairo.FONT_SLANT_NORMAL,
                            cairo.FONT_WEIGHT_BOLD if bold else cairo.FONT_WEIGHT_NORMAL)
        cr.set_font_size(size)
        cr.set_source_rgb(*(color or self.colors["text"]))
        cr.move_to(x, y)
        cr.show_text(s)
        return cr.text_extents(s).x_advance


    def invalidate_widget(self,wid,*rects):
        width=getattr(self,'chip_widths',{}).get(wid,800)
        bounds=[widget_bounds(rect,self.wa,width) for rect in rects]
        if self.drag and self.drag[0]==wid:bounds.append(widget_bounds(self.drag[4],self.wa,width))
        if getattr(self,'last_hud_rect',None):bounds.append(self.last_hud_rect[:4])
        rect=union(bounds)
        if rect:self.area.queue_draw_area(*pixel_bounds(rect))

    def invalidate_guides(self):
        before=getattr(self,'painted_guides',[]);after=list(self.guides)
        if before!=after:
            alloc=self.area.get_allocation()
            for axis,pos in set(before+after):
                rect=[pos-4,0,8,alloc.height] if axis=='v' else [0,pos-4,alloc.width,8]
                self.area.queue_draw_area(*pixel_bounds(rect))
            self.painted_guides=after

    def paint_grid(self,cr):
        if not hasattr(self,'grid_cache'):self.grid_cache=GridCache()
        tile=self.grid_cache.get(self.prefs['step'],self.colors['primary'],self.area.get_scale_factor())
        wa=self.wa;cr.save();cr.rectangle(wa['x'],wa['y'],wa['width'],wa['height']);cr.clip()
        cr.set_source_surface(tile,wa['x'],wa['y']);cr.get_source().set_extend(cairo.EXTEND_REPEAT)
        cr.get_source().set_filter(cairo.FILTER_NEAREST);cr.paint();cr.restore()

    def on_draw(self, _area, cr):
        self.buttons = []
        c = self.colors
        alloc = self.area.get_allocation()
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0, 0, 0, 0.35)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)

        if self.prefs['grid']:self.paint_grid(cr)
        clip=cr.clip_extents()
        try:clips=[(r.x,r.y,r.x+r.width,r.y+r.height) for r in cr.copy_clip_rectangle_list()]
        except cairo.Error:clips=[clip]
        if not hasattr(self,'chip_widths'):self.chip_widths={}
        cur_style_fx = self.style_fx
        for w in self.widgets:
            if not self.is_widget_visible(w):
                continue
            # Do not paint a fake card while the Eww surface is being prepared.
            if w['show'] and w['id'] not in getattr(self,'mapped_ids',set()):continue
            x, y, rw, rh = self.draw_rects.get(w["id"], self.rects[w["id"]])
            active = self.drag and self.drag[0] == w["id"]
            bounds=widget_bounds([x,y,rw,rh],self.wa,self.chip_widths.get(w['id'],800))
            if active:bounds=union([bounds,widget_bounds(self.drag[4],self.wa,800)])
            if not any(intersects(bounds,region) for region in clips):continue
            hot = active or self.hover == w["id"] or getattr(self, "selected_wid", None) == w["id"]
            color = c["primary"] if w["show"] else c["muted"]
            w_fx = w.get("opts", {}).get("fx", "global")
            if w_fx == "global":
                w_fx = cur_style_fx

            if active and self.drag[1] == "move":
                # Draw origin blueprint ghost showing starting position before movement
                ox, oy, ow, oh = self.drag[4]
                cr.save()
                self.rounded(cr, ox, oy, ow, oh, 16)
                cr.set_source_rgba(*c["tertiary"], 0.08)
                cr.fill_preserve()
                cr.set_source_rgba(*c["tertiary"], 0.45)
                cr.set_line_width(1.5)
                cr.set_dash([4, 4])
                cr.stroke()
                self.text(cr, "󰋔 Origen", ox + 8, oy + 16, 10, c["tertiary"], bold=True)

                # Draw sleek motion vector connecting origin to moving widget
                cr.move_to(ox + ow / 2, oy + oh / 2)
                cr.line_to(x + rw / 2, y + rh / 2)
                cr.set_source_rgba(*c["tertiary"], 0.4)
                cr.set_line_width(1.5)
                cr.set_dash([4, 4])
                cr.stroke()
                cr.restore()

            if active:
                # Soft deep drop shadow under moving widget (simulates elevated floating)
                cr.save()
                self.rounded(cr, x + 6, y + 14, rw, rh, 22)
                cr.set_source_rgba(0, 0, 0, 0.42)
                cr.fill()
                cr.restore()
            elif w["show"] and w_fx == "float":
                # Elevation shadow for floating juice
                cr.save()
                self.rounded(cr, x + 2, y + 7, rw, rh, 16)
                cr.set_source_rgba(0, 0, 0, 0.28)
                cr.fill()
                cr.restore()

            if w["show"] and w_fx == "glow":
                cr.save()
                self.rounded(cr, x - 4, y - 4, rw + 8, rh + 8, 20)
                cr.set_source_rgba(*color, 0.25 if hot else 0.14)
                cr.set_line_width(2.0)
                cr.stroke()
                cr.restore()
            elif w["show"] and w_fx == "border":
                cr.save()
                self.rounded(cr, x - 2, y - 2, rw + 4, rh + 4, 18)
                cr.set_source_rgba(*color, 0.85 if hot else 0.55)
                cr.set_line_width(2.0)
                cr.stroke()
                cr.restore()

            self.rounded(cr, x, y, rw, rh, 16)
            cr.set_source_rgba(*color, 0.18 if hot else (0.06 if w["show"] else 0.03))
            cr.fill_preserve()
            cr.set_source_rgba(*color, 1.0 if hot else 0.7)
            cr.set_line_width(2.5 if hot else 1.5)
            cr.set_dash([] if w["show"] else [8, 6])
            cr.stroke()
            cr.set_dash([])

            # Pulsating highlight halo for newly added / unhidden widget
            if getattr(self, "just_added", None) and self.just_added[0] == w["id"]:
                rem = self.just_added[1] - time.time()
                if rem > 0:
                    glow_alpha = 0.6 * (rem / 2.2)
                    cr.save()
                    self.rounded(cr, x - 5, y - 5, rw + 10, rh + 10, 20)
                    cr.set_source_rgba(*c["tertiary"], glow_alpha)
                    cr.set_line_width(3.0)
                    cr.stroke()
                    cr.restore()

            # Label chip.
            name = W.KINDS.get(w["window"], w["window"])
            ws_val = str(w.get("opts", {}).get("workspace", "Todos")).strip()
            if not ws_val or ws_val.lower() in ("todos", "global", "all", "*"):
                ws_tag = " · 󰍹 Global"
            else:
                ws_tag = f" · 󰍹 {ws_val.replace('Workspace ', 'WS ')}"
            chip = (f"{w['id']} · {name}" if w['id'] != name.lower() else w['id']) + ws_tag
            if not w["show"]:
                chip += " · 󰘓"
            font_face = "JetBrainsMono Nerd Font" if any(ord(ch) >= 0xe000 for ch in chip) else "Inter"
            cr.select_font_face(font_face, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
            cr.set_font_size(12)
            tw = cr.text_extents(chip).x_advance
            chip_w = tw + 20
            self.chip_widths[w['id']]=chip_w
            badge_h = 24
            badge_y = y - badge_h - 4 if y - badge_h - 4 >= self.wa["y"] + 2 else y + rh + 4
            cx = max(self.wa["x"] + 2, min(x + 2, self.wa["x"] + self.wa["width"] - chip_w - 2))
            # Subtle shadow
            self.rounded(cr, cx + 1, badge_y + 2, chip_w, badge_h, 12)
            cr.set_source_rgba(0, 0, 0, 0.22)
            cr.fill()
            # Pill above box
            self.rounded(cr, cx, badge_y, chip_w, badge_h, 12)
            cr.set_source_rgba(*c["surface"], 0.94)
            cr.fill_preserve()
            cr.set_source_rgba(*color, 0.6 if hot else 0.3)
            cr.set_line_width(1.0)
            cr.stroke()
            self.text(cr, chip, cx + 10, badge_y + 16, 12, color, bold=True)
            if active:
                info = f"{int(x)}, {int(y)}  ·  {int(rw)}×{int(rh)}"
                self.text(cr, info, x + 12, y + rh - 12, 12, c["text"])
            for hname, (hx, hy) in self.handles(w).items():
                cr.new_path()
                if hname in ("l", "r"):
                    # Width only: sleek pill with center grip dot
                    self.rounded(cr, hx - 5, hy - 18, 10, 36, 5)
                    cr.set_source_rgba(*c["surface"], 0.95)
                    cr.fill_preserve()
                    cr.set_source_rgba(*c["primary"], 1.0)
                    cr.set_line_width(2.5)
                    cr.stroke()
                    cr.arc(hx, hy, 2.5, 0, 6.2832)
                    cr.set_source_rgba(*c["primary"], 0.9)
                    cr.fill()
                else:
                    # Free size: double ring corner dot
                    hot_handle = active and self.drag[1] == f"resize-{hname}"
                    cr.arc(hx, hy, 9 if hot_handle else 7.5, 0, 6.2832)
                    cr.set_source_rgba(*c["surface"], 1.0)
                    cr.fill_preserve()
                    cr.set_source_rgba(*c["primary"], 1.0)
                    cr.set_line_width(2.8)
                    cr.stroke()
                    cr.arc(hx, hy, 3.2, 0, 6.2832)
                    cr.set_source_rgba(*(c["primary"] if hot_handle else c["surface"]), 1.0)
                    cr.fill()

        # Alignment guides while dragging.
        for axis, pos in self.guides:
            # Soft glowing halo
            cr.set_source_rgba(*c["tertiary"], 0.28)
            cr.set_line_width(4)
            if axis == "v":
                cr.move_to(pos + 0.5, 0)
                cr.line_to(pos + 0.5, alloc.height)
            else:
                cr.move_to(0, pos + 0.5)
                cr.line_to(alloc.width, pos + 0.5)
            cr.stroke()

            # Crisp dashed line
            cr.set_source_rgba(*c["tertiary"], 0.95)
            cr.set_line_width(1.5)
            cr.set_dash([6, 4])
            if axis == "v":
                cr.move_to(pos + 0.5, 0)
                cr.line_to(pos + 0.5, alloc.height)
            else:
                cr.move_to(0, pos + 0.5)
                cr.line_to(alloc.width, pos + 0.5)
            cr.stroke()
            cr.set_dash([])

        # Floating Mini Action HUD for active/selected/hovered widget
        target_wid = getattr(self, "selected_wid", None) or (self.hover if not self.drag else None)
        if target_wid and not self.drag:
            tw = W.find(self.widgets, target_wid)
            if tw and self.is_widget_visible(tw) and (not tw['show'] or tw['id'] in self.mapped_ids):
                self.draw_mini_hud(cr, tw)
        else:
            self.last_hud_rect = None

        self.draw_toolbar(cr, alloc.width)
        hint = "Arrastra: mover  ·  2× clic: ajustes  ·  Clic der.: ocultar  ·  Flechas: mover  ·  Ctrl+D: duplicar  ·  Supr: borrar"
        cr.select_font_face("Inter", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
        cr.set_font_size(11)
        tw = cr.text_extents(hint).x_advance
        hx, hy = (alloc.width - tw) / 2, min(alloc.height, self.wa["y"] + self.wa["height"]) - 18
        self.rounded(cr, hx - 10, hy - 15, tw + 20, 22, 6)
        cr.set_source_rgba(*c["surface"], 0.85)
        cr.fill()
        self.text(cr, hint, hx, hy, 11, c["muted"])
        if self.toast and time.monotonic()<self.toast[1]:
            self.draw_tooltip(cr,self.toast[0],alloc.width/2,hy-60)
        return False


    def draw_mini_hud(self, cr, w):
        wid = w["id"]
        if wid not in self.rects or not self.is_widget_visible(w):
            return
        x, y, rw, rh = self.draw_rects.get(wid, self.rects[wid])
        c = self.colors
        mx, my = self.mouse

        btn_size = 28
        spacing = 4
        pad_x = 6
        pad_y = 4
        actions = [
            ("󰒓", lambda wid=wid: self.open_settings(wid), c["primary"]),
            ("󰑓", lambda wid=wid: self.duplicate_widget(wid), c["primary"]),
            ("󰈈" if w["show"] else "󰘓", lambda wid=wid: self.toggle_show(wid), c["tertiary"] if w["show"] else c["muted"]),
            ("󰆴", lambda wid=wid: self.remove_widget(wid), c["error"]),
        ]

        hud_w = pad_x * 2 + len(actions) * btn_size + (len(actions) - 1) * spacing
        hud_h = btn_size + pad_y * 2

        name = W.KINDS.get(w["window"], w["window"])
        ws_val = str(w.get("opts", {}).get("workspace", "Todos")).strip()
        if not ws_val or ws_val.lower() in ("todos", "global", "all", "*"):
            ws_tag = " · 󰍹 Global"
        else:
            ws_tag = f" · 󰍹 {ws_val.replace('Workspace ', 'WS ')}"
        chip = (f"{wid} · {name}" if wid != name.lower() else wid) + ws_tag
        if not w["show"]:
            chip += " · 󰘓"
        font_face = "JetBrainsMono Nerd Font" if any(ord(ch) >= 0xe000 for ch in chip) else "Inter"
        cr.select_font_face(font_face, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        cr.set_font_size(12)
        chip_w = cr.text_extents(chip).x_advance + 20
        badge_y = y - 24 - 4 if y - 24 - 4 >= self.wa["y"] + 2 else y + 6
        cx = max(self.wa["x"] + 2, min(x + 2, self.wa["x"] + self.wa["width"] - chip_w - 2))

        if (x + rw - hud_w) >= (cx + chip_w + 6):
            hud_x = min(x + rw - hud_w, self.wa["x"] + self.wa["width"] - hud_w - 4)
            hud_y = badge_y - (hud_h - 24) / 2
        elif y - hud_h - 6 >= self.wa["y"] + 2:
            hud_x = min(max(cx + chip_w + 6, self.wa["x"] + 2), self.wa["x"] + self.wa["width"] - hud_w - 4)
            hud_y = y - hud_h - 4
        else:
            hud_x = min(max(x + rw - hud_w - 6, self.wa["x"] + 2), self.wa["x"] + self.wa["width"] - hud_w - 4)
            hud_y = y + 6

        self.last_hud_rect = (hud_x - 4, hud_y - 4, hud_w + 8, hud_h + 8, wid)

        cr.save()
        self.rounded(cr, hud_x + 1, hud_y + 2, hud_w, hud_h, 14)
        cr.set_source_rgba(0, 0, 0, 0.32)
        cr.fill()

        self.rounded(cr, hud_x, hud_y, hud_w, hud_h, 14)
        cr.set_source_rgba(*c["surface"], 0.96)
        cr.fill_preserve()
        cr.set_source_rgba(*c["primary"], 0.35)
        cr.set_line_width(1.0)
        cr.stroke()
        cr.restore()

        bx = hud_x + pad_x
        by = hud_y + pad_y
        for icon, act, col in actions:
            btn_rect = (bx, by, btn_size, btn_size)
            is_hot = (btn_rect[0] <= mx <= btn_rect[0] + btn_size and
                      btn_rect[1] <= my <= btn_rect[1] + btn_size)
            if is_hot:
                cr.save()
                self.rounded(cr, bx, by, btn_size, btn_size, 8)
                cr.set_source_rgba(*col, 0.25)
                cr.fill_preserve()
                cr.set_source_rgba(*col, 0.7)
                cr.set_line_width(1.0)
                cr.stroke()
                cr.restore()

            font_face = "JetBrainsMono Nerd Font"
            cr.select_font_face(font_face, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
            cr.set_font_size(14)
            ext = cr.text_extents(icon)
            tx = bx + (btn_size - ext.width) / 2 - ext.x_bearing
            ty = by + (btn_size - ext.height) / 2 - ext.y_bearing
            cr.set_source_rgb(*(col if is_hot else c["text"]))
            cr.move_to(tx, ty)
            cr.show_text(icon)

            self.buttons.append((btn_rect, act))
            bx += btn_size + spacing


    def draw_toolbar(self, cr, width):
        """Compact icon toolbar; labels only where they carry meaning, the rest get a hover tooltip."""
        c = self.colors
        grid_lbl = f"󰆾 {self.prefs['step']}" if self.prefs["grid"] else "󰆾 Off"
        ws_lbl = f"󰈲 WS {self.current_ws_num}" if self.filter_ws is not None else "󰈲 Global"
        # (label, tooltip, action, kind); None = group separator
        items = [
            ("󰕌", "Deshacer (Ctrl+Z)", self.undo, None),
            ("󰑎", "Rehacer (Ctrl+Y)", self.redo, None),
            None,
            ("󰏘", "Perfiles (P)", self.open_profiles_panel, None),
            ("󰔎", "Estilo general (S)", self.open_style_panel, None),
            ("󱐋", "Animación (A)", self.open_animation, None),
            None,
            (ws_lbl, "Alternar escritorio actual / solo globales", self.toggle_ws_filter,
             "accent" if self.filter_ws is not None else None),
            ("󰍹", "Asignar escritorios (W)", lambda: self.open_workspace_panel(), None),
            (grid_lbl, "Cuadrícula (G · [ ])", self.toggle_grid_panel, None),
            None,
            ("+ Widget", "Agregar widget", self.show_palette, "tonal"),
            ("󰜺", "Descartar cambios y salir", self.cancel, "danger"),
            ("Listo", "Guardar y salir (Enter)", self.finish, "primary"),
        ]
        btn_h, pad, gap, sep_w = 32, 4, 2, 9
        cr.set_font_size(12)
        widths = []
        for it in items:
            if it is None:
                widths.append(sep_w)
                continue
            label = it[0]
            font_face = "JetBrainsMono Nerd Font" if any(ord(ch) >= 0xe000 for ch in label) else "Inter"
            cr.select_font_face(font_face, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
            tw = cr.text_extents(label).x_advance
            widths.append(btn_h if len(label) == 1 else tw + 24)
        total = sum(widths) + gap * (len(items) - 1) + pad * 2
        bar_h = btn_h + pad * 2
        x, y = (width - total) / 2, 12
        self.rounded(cr, x, y, total, bar_h, 12)
        cr.set_source_rgba(*c["surface"], 0.97)
        cr.fill_preserve()
        cr.set_source_rgba(*c["muted"], 0.28)
        cr.set_line_width(1.0)
        cr.stroke()
        bx = x + pad
        by = y + pad
        mx, my = self.mouse
        tip = None
        for it, bw in zip(items, widths):
            if it is None:
                cr.set_source_rgba(*c["muted"], 0.3)
                cr.rectangle(bx + sep_w / 2, by + 8, 1, btn_h - 16)
                cr.fill()
                bx += bw + gap
                continue
            label, tooltip, action, kind = it
            rect = (bx, by, bw, btn_h)
            hot = rect[0] <= mx <= rect[0] + bw and rect[1] <= my <= rect[1] + btn_h
            self.rounded(cr, *rect, 8)
            fg = c["text"]
            if kind == "primary":
                cr.set_source_rgba(*c["primary"], 1.0 if hot else 0.88)
                cr.fill()
                fg = c["surface"]
            elif kind == "accent":
                cr.set_source_rgba(*c["tertiary"], 0.26 if hot else 0.14)
                cr.fill()
                fg = c["tertiary"]
            elif kind == "tonal":
                cr.set_source_rgba(*c["primary"], 0.24 if hot else 0.14)
                cr.fill()
                fg = c["primary"]
            elif hot:
                cr.set_source_rgba(*(c["error"] if kind == "danger" else c["primary"]), 0.18)
                cr.fill()
                fg = c["error"] if kind == "danger" else c["primary"]
            else:
                cr.new_path()
            font_face = "JetBrainsMono Nerd Font" if any(ord(ch) >= 0xe000 for ch in label) else "Inter"
            cr.select_font_face(font_face, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
            cr.set_font_size(14 if len(label) == 1 else 12)
            ext = cr.text_extents(label)
            self.text(cr, label, bx + (bw - ext.x_advance) / 2, by + (btn_h - ext.height) / 2 - ext.y_bearing,
                      14 if len(label) == 1 else 12, fg, bold=True)
            if hot:
                tip = (tooltip, bx + bw / 2, y + bar_h + 6)
            self.buttons.append((rect, action))
            bx += bw + gap
        if tip:
            self.draw_tooltip(cr, *tip)


    def draw_tooltip(self, cr, s, cx, top):
        c = self.colors
        cr.select_font_face("Inter", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
        cr.set_font_size(11)
        tw = cr.text_extents(s).x_advance
        tx = max(self.wa["x"] + 4, min(cx - tw / 2 - 8, self.wa["x"] + self.wa["width"] - tw - 20))
        self.rounded(cr, tx, top, tw + 16, 22, 6)
        cr.set_source_rgba(*c["surface"], 0.98)
        cr.fill_preserve()
        cr.set_source_rgba(*c["muted"], 0.35)
        cr.set_line_width(1.0)
        cr.stroke()
        self.text(cr, s, tx + 8, top + 15, 11, c["text"])
