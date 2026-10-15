from .common import *

class SessionMixin:
    def toggle_show(self, wid):
        w = W.find(self.widgets, wid)
        if w:
            self.push_undo()
            w["show"] = not w["show"]
            self.apply()
            if getattr(self, "current_settings_wid", None) == wid and self.settings_revealer.get_reveal_child():
                self.open_settings(wid)


    def finish(self):
        self.store_changed_positions()
        if self.save_widgets():
            save_prefs(self.prefs)
            Gtk.main_quit()


    def save_widgets(self):
        from randly_widgets.config import Conflict
        try:
            self.widgets = W.save(self.widgets)
            return True
        except Conflict as exc:
            self.show_toast(str(exc))
            self.widgets = W.load()
            self.refresh_rects()
            return False

    def cancel(self):
        from randly_widgets.config import rollback, Conflict
        try:
            rollback(self.original_widgets, W._last_editor_save or self.original_widgets)
        except Conflict as exc:
            self.show_toast(str(exc))
            return
        Gtk.main_quit()
