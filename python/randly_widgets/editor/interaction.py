from .common import *

class InteractionMixin:
    def expected_corner(self, w, size):
        wa, (gw, gh) = self.wa, size
        left = wa["x"] + w["x"]
        right = wa["x"] + wa["width"] - w["x"] - gw
        top = wa["y"] + w["y"]
        bottom = wa["y"] + wa["height"] - w["y"] - gh
        anchor = w["anchor"]
        if anchor == "center":
            return (wa["x"] + (wa["width"] - gw) // 2, wa["y"] + (wa["height"] - gh) // 2)
        return (right if "right" in anchor else left, bottom if "bottom" in anchor else top)


    def position_panel_near_widget(self, revealer, panel, wid, avoid_rect=None):
        """Position panel adjacent to widget `wid` so the widget remains visible and within screen."""
        wa = self.wa
        screen_x, screen_y = wa["x"], wa["y"]
        screen_w, screen_h = wa["width"], wa["height"]

        if wid and wid in self.rects:
            wx, wy, ww, wh = self.rects[wid]
        else:
            wx = screen_x + (screen_w - 360) // 2
            wy = screen_y + 120
            ww, wh = 360, 200

        pw = max(panel.get_size_request()[0], panel.get_preferred_width()[1], 320)
        _, nat_h = panel.get_preferred_height()
        ph = max(nat_h, 240) if nat_h > 0 else 320

        if avoid_rect:
            ax, ay, aw, ah = avoid_rect
            space_right_of_avoid = (screen_x + screen_w) - (ax + aw)
            space_left_of_widget = wx - screen_x

            if space_right_of_avoid >= pw + 20:
                px = ax + aw + 16
            elif space_left_of_widget >= pw + 20:
                px = wx - pw - 16
            elif ax - pw - 16 >= screen_x + 16:
                px = ax - pw - 16
            else:
                px = max(screen_x + 16, min(ax + aw + 16, screen_x + screen_w - pw - 16))
            py = ay
        else:
            space_right = (screen_x + screen_w) - (wx + ww)
            space_left = wx - screen_x
            if space_right >= pw + 24:
                px = wx + ww + 20
            elif space_left >= pw + 24:
                px = wx - pw - 20
            else:
                if space_right >= space_left:
                    px = min(wx + ww + 20, screen_x + screen_w - pw - 16)
                else:
                    px = max(wx - pw - 20, screen_x + 16)
            py = wy

        px = max(screen_x + 16, min(px, screen_x + screen_w - pw - 16))
        min_top = max(screen_y + 16, 84)
        max_top = screen_y + screen_h - ph - 24
        if max_top >= min_top:
            py = max(min_top, min(py, max_top))
        else:
            py = min_top

        revealer.set_margin_start(int(px))
        revealer.set_margin_top(int(py))
        return (px, py, pw, ph)


    def refresh_rects(self):
        geoms_by_id=getattr(self,'geometry_cache',{})
        self.geometry_tracker.prune(w['id'] for w in self.widgets)
        rects={};mapped=set()
        for w in self.widgets:
            wid=w['id'];g=geoms_by_id.get(wid,{})
            size=self.prefs['sizes'].get(wid,DEFAULT_SIZES.get(w['window'],DEFAULT_SIZE))
            if len(size)<2 or min(size[:2])<40:size=DEFAULT_SIZE
            x,y=self.expected_corner(w,size)
            raw=[int(g.get(k,0)) for k in ('x','y','width','height')] if g else None
            rect=self.geometry_tracker.resolve(wid,raw,[x,y,*size[:2]])
            rects[wid]=rect
            if wid in self.geometry_tracker.accepted and (raw and min(raw[2:])>=40 or wid in self.geometry_tracker.pending):
                mapped.add(wid)
                self.prefs['sizes'][wid]=list(rect[2:])
        self.mapped_ids=mapped
        self.draw_rects={wid:r for wid,r in self.draw_rects.items() if wid in rects}
        self.rects=rects
        self.saved_rects={wid:list(r) for wid,r in rects.items()}
        for wid,rect in rects.items():self.draw_rects.setdefault(wid,list(rect))


    def is_widget_visible(self, w):
        if getattr(self, "filter_ws", None) is None:
            return W.is_global_widget(w)
        return W.widget_matches_workspace(w, self.filter_ws, self.current_ws_coords)


    def toggle_ws_filter(self):
        if getattr(self, "filter_ws", None) is not None:
            self.filter_ws = None
            try:
                with open(EDITING_FLAG, "w", encoding="utf-8") as f:
                    f.write("global")
            except OSError:
                pass
            self.request_sync('global')
        else:
            self.filter_ws = self.current_ws_num
            try:
                with open(EDITING_FLAG, "w", encoding="utf-8") as f:
                    f.write(str(self.filter_ws))
            except OSError:
                pass
            self.request_sync(self.filter_ws)
        self.refresh_rects()
        self.area.queue_draw()


    def _anim_tick(self):
        if hasattr(self,'drag_lease'):self.drag_lease.update(bool(self.drag))
        changed=False
        for wid,target in self.rects.items():
            current=self.draw_rects.setdefault(wid,list(target))
            if self.drag and self.drag[0]==wid:
                next_rect=list(target)  # Pointer tracking is exact; never stretch the frame.
            else:
                next_rect=[target[i] if abs(target[i]-current[i])<.5 else current[i]+(target[i]-current[i])*.45 for i in (0,1)]+list(target[2:])
            if next_rect!=current:
                self.draw_rects[wid]=next_rect;changed=True
                if hasattr(self,'invalidate_widget'):self.invalidate_widget(wid,current,next_rect)
        if hasattr(self,'invalidate_guides'):self.invalidate_guides()
        if changed and not hasattr(self,'invalidate_widget'):self.area.queue_draw()
        return True


    def snap(self, value, lo, hi, size):
        if self.prefs["grid"]:
            step = self.prefs["step"]
            value = round((value - lo) / step) * step + lo
        # Always stick to the screen edges when close.
        if abs(value - lo) < EDGE_SNAP:
            value = lo
        if abs(value + size - hi) < EDGE_SNAP:
            value = hi - size
        return value


    def push_undo(self):
        import copy
        snapshot = (copy.deepcopy(self.widgets), copy.deepcopy(self.rects), copy.deepcopy(self.prefs))
        self.undo_stack.append(snapshot)
        if len(self.undo_stack) > 30:
            self.undo_stack.pop(0)
        self.redo_stack.clear()


    def undo(self):
        if not self.undo_stack:
            return
        import copy
        curr = (copy.deepcopy(self.widgets), copy.deepcopy(self.rects), copy.deepcopy(self.prefs))
        self.redo_stack.append(curr)
        widgets, rects, prefs = self.undo_stack.pop()
        self.widgets = widgets
        self.rects = rects
        self.prefs = prefs
        if self.selected_wid and not W.find(self.widgets, self.selected_wid):
            self.selected_wid = None
        self.save_widgets()
        self.request_sync(self.filter_ws if getattr(self, "filter_ws", None) is not None else 'global')
        self.area.queue_draw()


    def redo(self):
        if not self.redo_stack:
            return
        import copy
        curr = (copy.deepcopy(self.widgets), copy.deepcopy(self.rects), copy.deepcopy(self.prefs))
        self.undo_stack.append(curr)
        widgets, rects, prefs = self.redo_stack.pop()
        self.widgets = widgets
        self.rects = rects
        self.prefs = prefs
        if self.selected_wid and not W.find(self.widgets, self.selected_wid):
            self.selected_wid = None
        self.save_widgets()
        self.request_sync(self.filter_ws if getattr(self, "filter_ws", None) is not None else 'global')
        self.area.queue_draw()


    def duplicate_widget(self, wid):
        w = W.find(self.widgets, wid)
        if not w:
            return
        self.push_undo()
        import copy
        new_w = copy.deepcopy(w)
        base = new_w["id"].rstrip("0123456789")
        n = 2
        while W.find(self.widgets, f"{base}{n}"):
            n += 1
        new_id = f"{base}{n}"
        new_w["id"] = new_id

        orig_r = self.rects.get(wid, [self.wa["x"] + 100, self.wa["y"] + 100, 300, 200])
        wa = self.wa
        nx = min(orig_r[0] + 24, wa["x"] + wa["width"] - orig_r[2] - 10)
        ny = min(orig_r[1] + 24, wa["y"] + wa["height"] - orig_r[3] - 10)
        self.rects[new_id] = [nx, ny, orig_r[2], orig_r[3]]
        self.to_conf(new_w, self.rects[new_id])
        self.widgets.append(new_w)
        self.selected_wid = new_id
        self.apply()
        self.trigger_add_pulse(new_id)


    def apply(self, settle_id=None, requested=None):
        self.store_changed_positions()
        if not self.save_widgets():return
        self.request_sync()
        save_prefs(self.prefs)
        self.settle(settle_id, requested)


    def store_changed_positions(self):
        # Reanchoring unchanged widgets would force-close/reopen the entire desktop.
        for w in self.widgets:
            wid=w['id']
            if wid in self.rects and self.rects[wid]!=self.saved_rects.get(wid):
                self.to_conf(w,self.rects[wid])
                if hasattr(self,'geometry_tracker'):self.geometry_tracker.expect(wid,self.rects[wid])
        self.saved_rects={wid:list(r) for wid,r in self.rects.items()}

    def request_sync(self,mode=None):
        if mode is None:mode=self.filter_ws if self.filter_ws is not None else 'global'
        if self.worker:self.worker.request(mode)
        return True

    def settle(self,wid=None,requested=None):
        # Geometry arrives from the worker; never poll compositor/config from GTK.
        self.settle_source=None
        self.pending_settle=(wid,requested,time.monotonic()+.9) if wid and requested else None

    def show_toast(self, text):
        self.toast=(text,time.monotonic()+4)
        self.area.queue_draw()


    def trigger_add_pulse(self, wid):
        self.just_added = (wid, time.time() + 2.2)
        if getattr(self,'pulse_source',None):GLib.source_remove(self.pulse_source)

        def pulse():
            if self.just_added and time.time() < self.just_added[1]:
                self.invalidate_widget(wid,self.draw_rects.get(wid,self.rects.get(wid,[0,0,0,0])))
                return True
            self.just_added = None
            self.pulse_source = None
            self.invalidate_widget(wid,self.draw_rects.get(wid,self.rects.get(wid,[0,0,0,0])))
            return False

        self.pulse_source = GLib.timeout_add(40, pulse)


    def _tick(self):
        if not self.worker:return True
        received,pending=self.worker.take()
        if received:
            (place,geometries,fx),success=received
            if self.home and place and None not in place and place!=self.home:
                self.left_home=True;self.finish();return False
            if not success:self.show_toast('No se pudo mostrar el widget; tu configuración está guardada.')
            changed=geometries!=self.geometry_cache or fx!=self.style_fx
            if not self.drag and not pending:
                self.geometry_cache=geometries;self.style_fx=fx
                old_rects={wid:list(rect) for wid,rect in self.rects.items()}
                old_mapped=set(self.mapped_ids)
                self.refresh_rects()  # Two samples confirm a real allocation, even unchanged.
                if self.rects!=old_rects or self.mapped_ids!=old_mapped or changed:self.area.queue_draw()
                settle=getattr(self,'pending_settle',None)
                if settle and time.monotonic()>=settle[2]:
                    wid,requested,_=settle;self.pending_settle=None
                    if wid in self.mapped_ids and wid in self.rects:
                        w=W.find(self.widgets,wid);real_w,real_h=self.rects[wid][2:]
                        if w and real_w>requested[0]+4:
                            w['opts']['width']=str(int(real_w))
                            if w['window']=='photo':w['opts']['height']=str(int(real_h))
                            self.save_widgets()
        if self.toast and time.monotonic()>self.toast[1]:
            self.toast=None;self.area.queue_draw()
        return True

    def widget_at(self, px, py):
        for w in reversed(self.widgets):
            if not self.is_widget_visible(w):
                continue
            if w['show'] and w['id'] not in getattr(self,'mapped_ids',set()):continue
            x, y, rw, rh = self.draw_rects.get(w["id"], self.rects[w["id"]])
            if x <= px <= x + rw and y <= py <= y + rh:
                return w
        return None


    @staticmethod
    def resize_kind(w):
        """'free' (width and height: 4 corner dots), 'width' (2 side handles) or None (fixed)."""
        if w["window"] in ("photo", "image"):
            return "free"
        opts = W.SCHEMA.get(w["window"], {}).get("options", [])
        return "width" if any(key == "width" for key, *_ in opts) else None


    def handles(self, w):
        if not w["show"] or not self.is_widget_visible(w):
            return {}
        x, y, rw, rh = self.draw_rects.get(w["id"], self.rects[w["id"]])
        kind = self.resize_kind(w)
        if kind == "free":
            return {"tl": (x, y), "tr": (x + rw, y), "bl": (x, y + rh), "br": (x + rw, y + rh)}
        if kind == "width":
            return {"l": (x, y + rh / 2), "r": (x + rw, y + rh / 2)}
        return {}


    def on_handle(self, w, px, py):
        for name, (hx, hy) in self.handles(w).items():
            tall = 22 if name in ("l", "r") else HANDLE  # side handles are tall pills
            if abs(px - hx) <= HANDLE and abs(py - hy) <= tall:
                return name
        return None


    def widget_or_handle_at(self, px, py):
        """Handles sit on the frame's edge, partly outside it: check them first."""
        for w in reversed(self.widgets):
            if not self.is_widget_visible(w):
                continue
            if self.on_handle(w, px, py):
                return w
        return self.widget_at(px, py)


    def guide_lines(self, skip):
        """Edges and centers of the other widgets and of the screen."""
        wa = self.wa
        xs = [wa["x"], wa["x"] + wa["width"], wa["x"] + wa["width"] / 2]
        ys = [wa["y"], wa["y"] + wa["height"], wa["y"] + wa["height"] / 2]
        for w in self.widgets:
            if w["id"] == skip or not w["show"] or not self.is_widget_visible(w):
                continue
            x, y, rw, rh = self.rects[w["id"]]
            xs += [x, x + rw, x + rw / 2]
            ys += [y, y + rh, y + rh / 2]
        return xs, ys


    def grid(self, v, origin):
        if not self.prefs["grid"]:
            return v
        step = self.prefs["step"]
        return round((v - origin) / step) * step + origin


    def snap_span(self, start, size, lines, origin):
        """Snap a moving span: a guide (edge/center within GUIDE_SNAP) wins over the grid."""
        best = None
        for offset in (0, size, size / 2):
            for line in lines:
                d = abs(start + offset - line)
                if d <= GUIDE_SNAP and (best is None or d < best[0]):
                    best = (d, line - offset, line)
        if best:
            return best[1], best[2]
        return self.grid(start, origin), None


    def snap_edge(self, value, lines, origin):
        """Resize edges follow the pointer 1:1; only stick to alignment guides (no grid steps)."""
        best = min(((abs(value - line), line) for line in lines), default=(GUIDE_SNAP + 1, None))
        if best[0] <= GUIDE_SNAP:
            return best[1], best[1]
        return value, None


    def to_conf(self, w, rect, h_side=None, v_side=None):
        """Store the rect relative to a workarea corner (nearest one unless forced)."""
        x, y, rw, rh = rect
        wa = self.wa
        right = (h_side == "right") if h_side else x + rw / 2 > wa["x"] + wa["width"] / 2
        bottom = (v_side == "bottom") if v_side else y + rh / 2 > wa["y"] + wa["height"] / 2
        w["anchor"] = f"{'bottom' if bottom else 'top'}-{'right' if right else 'left'}"
        w["x"] = max(0, int(round(wa["x"] + wa["width"] - x - rw if right else x - wa["x"])))
        w["y"] = max(0, int(round(wa["y"] + wa["height"] - y - rh if bottom else y - wa["y"])))


    def pin_for_resize(self, w, handle):
        """Anchor the widget on the side that must stay still, so live resizing grows the other way."""
        h_side = "right" if "l" in handle else "left"
        v_side = "bottom" if "t" in handle else ("top" if "b" in handle else None)
        self.to_conf(w, self.rects[w["id"]], h_side, v_side)
        self.save_widgets()
        self.request_sync(self.filter_ws if getattr(self, "filter_ws", None) is not None else 'global')


    def on_press(self, _area, ev):
        px, py = ev.x, ev.y
        for (bx, by, bw, bh), action in self.buttons:
            if bx <= px <= bx + bw and by <= py <= by + bh:
                if ev.button == 1 and action:
                    action()
                return True
        w = self.widget_or_handle_at(px, py)
        self.set_focus(None)
        if not w:
            self.selected_wid = None
            panel_open = (self.palette_revealer.get_reveal_child() or
                          self.settings_revealer.get_reveal_child() or
                          self.workspace_revealer.get_reveal_child() or
                          self.grid_revealer.get_reveal_child() or
                          self.profiles_revealer.get_reveal_child())
            if panel_open:
                self.close_panels()
            self.area.queue_draw()
            return True
        self.selected_wid = w["id"]
        if ev.type == Gdk.EventType._2BUTTON_PRESS and ev.button == 1:
            self.drag = None
            self.open_settings(w["id"])
            return True
        if ev.button == 3:
            self.push_undo()
            w["show"] = not w["show"]
            self.apply()
        elif ev.button == 1:
            import copy
            self.pre_drag_snapshot = (copy.deepcopy(self.widgets), copy.deepcopy(self.rects), copy.deepcopy(self.prefs))
            handle = self.on_handle(w, px, py)
            if handle:
                self.pin_for_resize(w, handle)
            mode = f"resize-{handle}" if handle else "move"
            self.drag = (w["id"], mode, px, py, list(self.rects[w["id"]]))
        self.area.queue_draw()
        return True


    def on_motion(self, _area, ev):
        old_hover=self.hover
        old_button=next((i for i,(r,act) in enumerate(self.buttons) if act and r[0]<=self.mouse[0]<=r[0]+r[2] and r[1]<=self.mouse[1]<=r[1]+r[3]),None)
        self.mouse = (ev.x, ev.y)
        if self.drag:
            wid, mode, sx, sy, (x, y, rw, rh) = self.drag
            dx, dy = ev.x - sx, ev.y - sy
            wa = self.wa
            xs, ys = self.guide_lines(wid)
            self.guides = []
            if mode == "move":
                nx, gx = self.snap_span(x + dx, rw, xs, wa["x"])
                ny, gy = self.snap_span(y + dy, rh, ys, wa["y"])
                self.guides = [("v", gx)] * (gx is not None) + [("h", gy)] * (gy is not None)
                self.rects[wid] = [nx, ny, rw, rh]
            else:
                handle = mode.split("-", 1)[1]
                w = W.find(self.widgets, wid)
                min_w = MIN_PHOTO if w["window"] in ("photo", "image") else MIN_WIDGET
                left, top, right, bottom = x, y, x + rw, y + rh
                if "l" in handle:
                    left, g = self.snap_edge(x + dx, xs, wa["x"])
                    left = min(left, right - min_w)
                    self.guides.append(("v", g))
                if "r" in handle:
                    right, g = self.snap_edge(x + rw + dx, xs, wa["x"])
                    right = max(right, left + min_w)
                    self.guides.append(("v", g))
                if "t" in handle:
                    top, g = self.snap_edge(y + dy, ys, wa["y"])
                    top = min(top, bottom - MIN_PHOTO)
                    self.guides.append(("h", g))
                if "b" in handle:
                    bottom, g = self.snap_edge(y + rh + dy, ys, wa["y"])
                    bottom = max(bottom, top + MIN_PHOTO)
                    self.guides.append(("h", g))
                self.guides = [g for g in self.guides if g[1] is not None]
                self.rects[wid] = [left, top, right - left, bottom - top]
                self.live_resize(wid)
        else:
            w = self.widget_or_handle_at(ev.x, ev.y)
            if not w and getattr(self, "last_hud_rect", None):
                hx, hy, hw, hh, hwid = self.last_hud_rect
                if hx <= ev.x <= hx + hw and hy <= ev.y <= hy + hh:
                    w = W.find(self.widgets, hwid)
            self.hover = w["id"] if w else None
            win = self.area.get_window()
            if win:
                on_btn = any(bx <= ev.x <= bx + bw and by <= ev.y <= by + bh
                             for (bx, by, bw, bh), act in self.buttons if act)
                handle = w and self.on_handle(w, ev.x, ev.y)
                name = ("pointer" if on_btn else
                        {"tl": "nwse-resize", "br": "nwse-resize", "tr": "nesw-resize", "bl": "nesw-resize",
                         "l": "ew-resize", "r": "ew-resize"}.get(handle) or ("grab" if w else "default"))
                if name!=getattr(self,'cursor_name',None):
                    self.cursors=getattr(self,'cursors',{})
                    if name not in self.cursors:self.cursors[name]=Gdk.Cursor.new_from_name(self.get_display(),name)
                    win.set_cursor(self.cursors[name]);self.cursor_name=name
        new_button=next((i for i,(r,act) in enumerate(self.buttons) if act and r[0]<=ev.x<=r[0]+r[2] and r[1]<=ev.y<=r[1]+r[3]),None)
        if old_hover!=self.hover or not self.drag and old_button!=new_button:self.area.queue_draw()
        return True


    def store_size(self, wid):
        w = W.find(self.widgets, wid)
        _, _, rw, rh = self.rects[wid]
        if w["window"] == "photo":
            W.set_photo_size(w, rw, rh)
        elif w["window"] == "image":
            w["opts"]["width"], w["opts"]["height"] = str(int(rw)), str(int(rh))
        else:
            w["opts"]["width"] = str(int(rw))
        return w


    def live_resize(self, wid):
        """While dragging, push the new size to the real widget (throttled)."""
        self.pending_live = wid
        if self.live_source:
            return

        def push():
            self.live_source = None
            if self.pending_live and self.drag:
                self.store_size(self.pending_live)
                self.save_widgets()  # wcfg picks it up; the pinned side stays put
            return False

        self.live_source = GLib.timeout_add(LIVE_MS, push)


    def on_release(self, _area, ev):
        if self.drag and ev.button == 1:
            wid, mode, sx, sy, start_rect = self.drag
            if self.rects.get(wid) != start_rect and getattr(self, "pre_drag_snapshot", None):
                self.undo_stack.append(self.pre_drag_snapshot)
                if len(self.undo_stack) > 30:
                    self.undo_stack.pop(0)
                self.redo_stack.clear()
            self.pre_drag_snapshot = None
            self.drag = None
            self.guides = []
            requested = None
            if mode.startswith("resize"):
                self.store_size(wid)
                requested = tuple(self.rects[wid][2:])
            self.apply(wid if requested else None, requested)
            if getattr(self, "current_settings_wid", None) == wid and self.settings_revealer.get_reveal_child():
                self.last_settings_rect = self.position_panel_near_widget(
                    self.settings_revealer, self.settings_panel, wid)
                if self.workspace_revealer.get_reveal_child():
                    self.position_panel_near_widget(
                        self.workspace_revealer, self.workspace_panel, wid, avoid_rect=self.last_settings_rect)
        return True


    def on_key(self, _w, ev):
        key = Gdk.keyval_name(ev.keyval)
        panel_open = (self.palette_revealer.get_reveal_child() or
                      self.settings_revealer.get_reveal_child() or
                      self.workspace_revealer.get_reveal_child() or
                      self.grid_revealer.get_reveal_child() or
                      self.profiles_revealer.get_reveal_child() or
                      self.style_revealer.get_reveal_child())
        if key == "Escape" and panel_open:
            self.close_panels()
            return True
        if isinstance(self.get_focus(), (Gtk.Entry, Gtk.TextView)):
            return False  # typing in a settings field

        ctrl = bool(ev.state & Gdk.ModifierType.CONTROL_MASK)
        shift = bool(ev.state & Gdk.ModifierType.SHIFT_MASK)
        if ctrl and key in ("z", "Z"):
            if shift:
                self.redo()
            else:
                self.undo()
            return True
        if ctrl and key in ("y", "Y"):
            self.redo()
            return True
        if ctrl and key in ("d", "D"):
            target = getattr(self, "selected_wid", None) or self.hover
            if target:
                self.duplicate_widget(target)
            return True

        if key in ("Escape", "Return", "KP_Enter"):
            self.finish()
        elif not ctrl and key in ("p", "P"):
            self.open_profiles_panel()
        elif not ctrl and key in ("s", "S"):
            self.open_style_panel()
        elif not ctrl and key in ("g", "G"):
            self.cycle_grid()
        elif not ctrl and key in ("a", "A"):
            self.open_animation()
        elif not ctrl and key in ("w", "W"):
            self.open_workspace_panel()
        elif key == "bracketleft":
            steps = [5, 10, 20, 30]
            cur = self.prefs.get("step", 20)
            idx = steps.index(cur) if cur in steps else 2
            self.prefs["step"] = steps[max(0, idx - 1)]
            self.prefs["grid"] = True
            save_prefs(self.prefs)
            if self.grid_revealer.get_reveal_child():
                self.open_grid_panel()
        elif key == "bracketright":
            steps = [5, 10, 20, 30]
            cur = self.prefs.get("step", 20)
            idx = steps.index(cur) if cur in steps else 2
            self.prefs["step"] = steps[min(len(steps) - 1, idx + 1)]
            self.prefs["grid"] = True
            save_prefs(self.prefs)
            if self.grid_revealer.get_reveal_child():
                self.open_grid_panel()
        elif key in ("Delete", "BackSpace") and (getattr(self, "selected_wid", None) or self.hover):
            self.remove_widget(getattr(self, "selected_wid", None) or self.hover)
        elif key in ("Up", "Down", "Left", "Right"):
            target = getattr(self, "selected_wid", None) or self.hover
            if target and target in self.rects:
                step = self.prefs.get("step", 20) if shift else 1
                if ctrl:
                    step = 10
                dx = -step if key == "Left" else (step if key == "Right" else 0)
                dy = -step if key == "Up" else (step if key == "Down" else 0)
                self.push_undo()
                rx, ry, rw, rh = self.rects[target]
                wa = self.wa
                nx = max(wa["x"], min(rx + dx, wa["x"] + wa["width"] - rw))
                ny = max(wa["y"], min(ry + dy, wa["y"] + wa["height"] - rh))
                self.rects[target] = [nx, ny, rw, rh]
                w = W.find(self.widgets, target)
                if w:
                    self.to_conf(w, self.rects[target])
                    self.save_widgets()
                    self.request_sync(self.filter_ws if getattr(self, "filter_ws", None) is not None else 'global')
                self.area.queue_draw()
                return True
        self.area.queue_draw()
        return True


    def cycle_grid(self):
        """Cycle through: Desactivado -> 5px -> 10px -> 20px -> 30px -> Desactivado."""
        if not self.prefs["grid"]:
            self.prefs["grid"] = True
            self.prefs["step"] = 5
        elif self.prefs["step"] == 5:
            self.prefs["step"] = 10
        elif self.prefs["step"] == 10:
            self.prefs["step"] = 20
        elif self.prefs["step"] == 20:
            self.prefs["step"] = 30
        else:
            self.prefs["grid"] = False
        save_prefs(self.prefs)
        self.area.queue_draw()
        if self.grid_revealer.get_reveal_child():
            self.open_grid_panel()


    def toggle_grid(self):
        self.cycle_grid()


    def remove_widget(self, wid):
        w = W.find(self.widgets, wid)
        if not w:
            return
        self.push_undo()
        self.widgets.remove(w)
        self.rects.pop(wid, None)
        self.hover = None
        if getattr(self, "selected_wid", None) == wid:
            self.selected_wid = None
        self.close_panels()
        self.apply()


    def build_css(self):
        c = self.colors

        def rgb(col, a=1.0):
            return "rgba({},{},{},{})".format(*(int(v * 255) for v in col), a)

        # Design tokens: spacing 4/8/12/16 px, radius 6/8/12 px, type 11/12/13 px.
        css = f"""
        .panel {{ background-color: {rgb(c['surface'], 0.98)}; border-radius: 12px; padding: 12px;
                 border: 1px solid {rgb(c['muted'], 0.28)};
                 box-shadow: 0 4px 12px rgba(0, 0, 0, 0.30); }}
        .panel label {{ font-family: Inter; font-size: 12px; color: {rgb(c['text'])}; }}
        .panel .panel-icon {{ font-family: "JetBrainsMono Nerd Font Propo"; font-size: 14px;
                      color: {rgb(c['primary'])}; background-color: {rgb(c['primary'], 0.14)};
                      border-radius: 8px; min-width: 28px; min-height: 28px; }}
        .panel .panel-title {{ font-size: 13px; font-weight: 700; }}
        .panel .panel-sub {{ font-size: 11px; color: {rgb(c['muted'])}; }}
        .panel .panel-grip {{ font-family: "JetBrainsMono Nerd Font Propo"; font-size: 12px; color: {rgb(c['muted'], 0.7)}; }}
        .panel .section {{ border-top: 1px solid {rgb(c['muted'], 0.18)}; padding-top: 8px; }}
        .panel .group-title {{ font-size: 11px; font-weight: 700; color: {rgb(c['muted'])}; }}
        .panel .field {{ font-size: 12px; }}
        .panel expander title label {{ font-size: 11px; font-weight: 700; color: {rgb(c['muted'])}; }}
        .panel expander arrow {{ color: {rgb(c['muted'])}; min-width: 12px; min-height: 12px; }}
        .wcard {{ background-image: none; background-color: {rgb(c['primary'], 0.06)};
                 border-radius: 8px; padding: 4px 8px; border: 1px solid {rgb(c['muted'], 0.18)};
                 box-shadow: none; min-height: 36px;
                 transition: background-color 120ms ease, border-color 120ms ease; }}
        .wcard:hover {{ background-color: {rgb(c['primary'], 0.14)}; border-color: {rgb(c['primary'], 0.45)}; }}
        .wcard:disabled {{ opacity: 0.45; }}
        .panel .wcard-icon {{ font-family: "JetBrainsMono Nerd Font Propo"; font-size: 16px;
                             color: {rgb(c['primary'])}; }}
        .panel .wcard-name {{ font-size: 12px; font-weight: 700; }}
        .panel .wcard-desc {{ font-size: 11px; color: {rgb(c['muted'])}; }}
        .panel .wcard-tag {{ font-size: 11px; font-weight: 700; padding: 0 4px; border-radius: 6px; }}
        .panel .wcard-tag-ok {{ color: {rgb(c['primary'])}; background-color: {rgb(c['primary'], 0.14)}; }}
        .panel .wcard-tag-warn {{ color: {rgb(c['tertiary'])}; background-color: {rgb(c['tertiary'], 0.16)}; }}
        .panel .wcard-tag-dim {{ color: {rgb(c['muted'])}; background-color: {rgb(c['muted'], 0.12)}; }}
        .panel switch {{ min-height: 18px; min-width: 34px; border-radius: 99px; }}
        .panel switch slider {{ min-height: 14px; min-width: 14px; border-radius: 99px; }}
        .panel combobox button, .panel entry, .panel spinbutton {{ min-height: 28px; font-size: 12px; border-radius: 6px; }}
        .panel combobox button {{ padding: 0 8px; }}
        .textbox {{ border-radius: 6px; border: 1px solid {rgb(c['muted'], 0.35)}; }}
        .pbtn {{ background-image: none; background-color: {rgb(c['primary'], 0.10)};
                border-radius: 8px; padding: 0 12px; border: 1px solid transparent; box-shadow: none; min-height: 28px;
                transition: background-color 120ms ease, border-color 120ms ease; }}
        .pbtn label {{ font-weight: 700; font-size: 12px; }}
        .pbtn:hover {{ background-color: {rgb(c['primary'], 0.20)}; border-color: {rgb(c['primary'], 0.35)}; }}
        .pbtn:active {{ background-color: {rgb(c['primary'], 0.30)}; }}
        .pbtn.icon {{ padding: 0; min-width: 28px; }}
        .pbtn.icon label {{ font-family: "JetBrainsMono Nerd Font Propo"; font-size: 14px; }}
        .pbtn.primary {{ background-color: {rgb(c['primary'])}; }}
        .pbtn.primary:hover {{ background-color: {rgb(c['primary'], 0.85)}; }}
        .panel .pbtn.primary label {{ color: {rgb(c['surface'])}; }}
        .panel .pbtn.danger label {{ color: {rgb(c['error'])}; }}
        .pbtn.danger:hover {{ background-color: {rgb(c['error'], 0.16)}; border-color: {rgb(c['error'], 0.4)}; }}
        .panel button:focus, .panel entry:focus, .panel spinbutton:focus, .panel switch:focus {{
            outline: 2px solid {rgb(c['primary'], 0.8)}; outline-offset: 1px; }}
        .ws-pill {{ background-image: none; background-color: {rgb(c['primary'], 0.08)};
                   color: {rgb(c['text'])}; border-radius: 6px; padding: 0 4px;
                   border: 1px solid {rgb(c['muted'], 0.18)}; box-shadow: none; min-width: 26px; min-height: 26px;
                   transition: background-color 120ms ease, color 120ms ease; }}
        .ws-pill label {{ font-weight: 700; font-size: 11px; }}
        .ws-pill:hover {{ background-color: {rgb(c['primary'], 0.20)}; }}
        .ws-pill:checked, .ws-pill:active {{ background-color: {rgb(c['primary'])}; border-color: {rgb(c['primary'])}; }}
        .ws-pill:checked label, .ws-pill:active label {{ color: {rgb(c['surface'])}; }}
        .ws-pill.todos {{ padding: 0 12px; min-height: 28px; }}
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css.encode())
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
