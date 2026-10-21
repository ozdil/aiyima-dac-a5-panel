"""AIYIMA DAC-A5 Pro ince ayar paneli (GTK4 + libadwaita)."""

import copy
import math
import sys
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

from . import backend as be  # noqa: E402
from . import biquad  # noqa: E402

APP_ID = "dev.ozdil.AiyimaDacPanel"
F_MIN, F_MAX = 20.0, 20000.0
DB_RANGE = 15.0
GAIN_MIN, GAIN_MAX = -15.0, 15.0
TYPE_KEYS = list(biquad.TYPES)
RATE_CHOICES = [0] + be.SUPPORTED_RATES


def fmt_freq(f):
    return f"{f / 1000:.1f} kHz" if f >= 1000 else f"{f:.0f} Hz"


def fmt_rate(r):
    return f"{r / 1000:g} kHz" if r else "—"


# ------------------------------------------------------------------ EQ curve


class EqCurve(Gtk.DrawingArea):
    """Toplam frekans yanıtını çizer; bant tutamaçları sürüklenebilir (frekans/kazanç)."""

    def __init__(self, win):
        super().__init__()
        self.win = win
        self.set_content_height(280)
        self.set_hexpand(True)
        self.set_draw_func(self._draw)
        self._freqs = [F_MIN * (F_MAX / F_MIN) ** (i / 399) for i in range(400)]
        self._drag_band = None
        self._drag_origin = (0, 0)
        drag = Gtk.GestureDrag()
        drag.connect("drag-begin", self._on_begin)
        drag.connect("drag-update", self._on_update)
        drag.connect("drag-end", lambda *a: setattr(self, "_drag_band", None))
        self.add_controller(drag)
        scroll = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.VERTICAL)
        scroll.connect("scroll", self._on_scroll)
        self.add_controller(scroll)
        self._hover = None
        motion = Gtk.EventControllerMotion()
        motion.connect("motion", self._on_motion)
        motion.connect("leave", lambda *a: self._set_hover(None))
        self.add_controller(motion)

    # geometry
    def _pad(self):
        return 46, 14, 14, 26  # left, right, top, bottom

    def _x(self, f, w):
        l, r, _, _ = self._pad()
        return l + (w - l - r) * math.log(f / F_MIN) / math.log(F_MAX / F_MIN)

    def _f(self, x, w):
        l, r, _, _ = self._pad()
        t = min(max((x - l) / max(w - l - r, 1), 0), 1)
        return F_MIN * (F_MAX / F_MIN) ** t

    def _y(self, db, h):
        _, _, t, b = self._pad()
        return t + (h - t - b) * (0.5 - db / (2 * DB_RANGE))

    def _db(self, y, h):
        _, _, t, b = self._pad()
        return (0.5 - (y - t) / max(h - t - b, 1)) * 2 * DB_RANGE

    def _handles(self, w, h):
        prof = self.win.profile
        rate = self.win.graph_rate
        out = []
        for i, b in enumerate(prof.bands):
            c = biquad.coefficients(b.type, b.freq, b.q, b.gain, rate)
            out.append((i, self._x(b.freq, w), self._y(biquad.magnitude_db(c, b.freq, rate), h)))
        return out

    def _nearest(self, x, y):
        w, h = self.get_width(), self.get_height()
        best = None
        for i, hx, hy in self._handles(w, h):
            d = math.hypot(hx - x, hy - y)
            if d < 18 and (best is None or d < best[1]):
                best = (i, d)
        return best[0] if best else None

    # events
    def _set_hover(self, idx):
        if idx != self._hover:
            self._hover = idx
            self.set_cursor_from_name("grab" if idx is not None else None)
            self.queue_draw()

    def _on_motion(self, _c, x, y):
        if self._drag_band is None:
            self._set_hover(self._nearest(x, y))

    def _on_begin(self, _g, x, y):
        self._drag_band = self._nearest(x, y)
        self._drag_origin = (x, y)

    def _on_update(self, _g, dx, dy):
        if self._drag_band is None:
            return
        w, h = self.get_width(), self.get_height()
        x, y = self._drag_origin[0] + dx, self._drag_origin[1] + dy
        freq = round(self._f(x, w))
        gain = round(min(max(self._db(y, h), GAIN_MIN), GAIN_MAX) * 2) / 2
        self.win.set_band(self._drag_band, freq=freq, gain=gain, from_curve=True)

    def _on_scroll(self, _c, _dx, dy):
        if self._hover is None:
            return False
        b = self.win.profile.bands[self._hover]
        q = min(max(b.q * (0.9 if dy > 0 else 1.1), 0.1), 10.0)
        self.win.set_band(self._hover, q=round(q, 2), from_curve=True)
        return True

    # drawing
    def _draw(self, _area, cr, w, h):
        fg = self.get_color()
        try:
            acc = Adw.StyleManager.get_default().get_accent_color_rgba()
        except AttributeError:
            acc = fg
        l, r, t, b = self._pad()

        def rgba(c, a):
            cr.set_source_rgba(c.red, c.green, c.blue, a)

        # grid
        cr.set_line_width(1)
        for f in (20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000):
            x = round(self._x(f, w)) + 0.5
            rgba(fg, 0.08)
            cr.move_to(x, t)
            cr.line_to(x, h - b)
            cr.stroke()
            rgba(fg, 0.55)
            cr.set_font_size(10)
            label = f"{f // 1000}k" if f >= 1000 else str(f)
            ext = cr.text_extents(label)
            cr.move_to(x - ext.width / 2, h - 8)
            cr.show_text(label)
        for db in range(-15, 16, 5):
            y = round(self._y(db, h)) + 0.5
            rgba(fg, 0.22 if db == 0 else 0.08)
            cr.move_to(l, y)
            cr.line_to(w - r, y)
            cr.stroke()
            rgba(fg, 0.55)
            label = f"{db:+d}" if db else "0 dB"
            ext = cr.text_extents(label)
            cr.move_to(l - ext.width - 6, y + 3.5)
            cr.show_text(label)

        prof = self.win.profile
        rate = self.win.graph_rate
        bands = [(b.type, b.freq, b.q, b.gain) for b in prof.bands]
        if self.win.bypass:
            bands = []
        resp_eq = biquad.response(bands, self._freqs, rate)
        pre = 0.0 if self.win.bypass else prof.preamp
        total = [v + pre for v in resp_eq]

        # EQ shape without preamp (thin), total (thick, filled)
        rgba(fg, 0.35)
        cr.set_line_width(1.2)
        cr.set_dash([4, 4])
        for i, (f, v) in enumerate(zip(self._freqs, resp_eq)):
            x, y = self._x(f, w), self._y(max(min(v, DB_RANGE), -DB_RANGE), h)
            cr.move_to(x, y) if i == 0 else cr.line_to(x, y)
        cr.stroke()
        cr.set_dash([])

        y0 = self._y(0, h)
        cr.move_to(self._x(self._freqs[0], w), y0)
        for f, v in zip(self._freqs, total):
            cr.line_to(self._x(f, w), self._y(max(min(v, DB_RANGE), -DB_RANGE), h))
        cr.line_to(self._x(self._freqs[-1], w), y0)
        cr.close_path()
        rgba(acc, 0.14)
        cr.fill()
        cr.set_line_width(2.4)
        rgba(acc, 1)
        for i, (f, v) in enumerate(zip(self._freqs, total)):
            x, y = self._x(f, w), self._y(max(min(v, DB_RANGE), -DB_RANGE), h)
            cr.move_to(x, y) if i == 0 else cr.line_to(x, y)
        cr.stroke()

        cr.new_path()
        # clipping zone
        peak = max(total)
        if peak > 0.05:
            cr.set_source_rgba(0.9, 0.2, 0.2, 0.9)
            cr.set_font_size(11)
            cr.move_to(l + 8, t + 14)
            cr.show_text(f"Tepe +{peak:.1f} dB, kırpılma riski: preamp'i düşür")

        if self.win.bypass:
            return
        for i, hx, hy in self._handles(w, h):
            hy = max(min(hy, h - b), t)
            rad = 9 if i == self._hover or i == self._drag_band else 7
            cr.new_path()
            cr.arc(hx, hy, rad, 0, 2 * math.pi)
            rgba(acc, 1)
            cr.fill_preserve()
            cr.set_source_rgba(1, 1, 1, 0.9)
            cr.set_line_width(1.5)
            cr.stroke()
            cr.set_source_rgba(1, 1, 1, 1)
            cr.set_font_size(10)
            ext = cr.text_extents(str(i + 1))
            cr.move_to(hx - ext.width / 2 - ext.x_bearing, hy + ext.height / 2)
            cr.show_text(str(i + 1))


# ------------------------------------------------------------------ Band card


class BandCard(Gtk.Box):
    def __init__(self, win, idx):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.win, self.idx = win, idx
        self.add_css_class("card")
        self.add_css_class("band-card")
        self._lock = False

        title = Gtk.Label(label=f"Bant {idx + 1}", xalign=0)
        title.add_css_class("heading")
        self.append(title)

        self.type_dd = Gtk.DropDown.new_from_strings([biquad.TYPES[k] for k in TYPE_KEYS])
        self.type_dd.connect("notify::selected", self._on_type)
        self.append(self.type_dd)

        self.gain_lbl = Gtk.Label()
        self.gain_lbl.add_css_class("numeric")
        self.gain_lbl.add_css_class("title-3")
        self.append(self.gain_lbl)

        self.gain = Gtk.Scale.new_with_range(Gtk.Orientation.VERTICAL, GAIN_MIN, GAIN_MAX, 0.5)
        self.gain.set_inverted(True)
        self.gain.set_has_origin(False)
        self.gain.set_size_request(-1, 220)
        self.gain.add_mark(0, Gtk.PositionType.RIGHT, None)
        self.gain.connect("value-changed", self._on_gain)
        self.append(self.gain)

        grid = Gtk.Grid(column_spacing=6, row_spacing=6)
        self.freq = Gtk.SpinButton.new_with_range(F_MIN, F_MAX, 1)
        self.freq.set_digits(0)
        self.freq.connect("value-changed", self._on_freq)
        self.q = Gtk.SpinButton.new_with_range(0.1, 10.0, 0.05)
        self.q.set_digits(2)
        self.q.connect("value-changed", self._on_q)
        for r, (name, w) in enumerate((("Hz", self.freq), ("Q", self.q))):
            lbl = Gtk.Label(label=name, xalign=0)
            lbl.add_css_class("dim-label")
            grid.attach(lbl, 0, r, 1, 1)
            w.set_hexpand(True)
            grid.attach(w, 1, r, 1, 1)
        self.append(grid)

    def sync(self):
        b = self.win.profile.bands[self.idx]
        self._lock = True
        self.type_dd.set_selected(TYPE_KEYS.index(b.type) if b.type in TYPE_KEYS else 0)
        self.gain.set_value(b.gain)
        self.freq.set_value(b.freq)
        self.q.set_value(b.q)
        self.gain_lbl.set_label(f"{b.gain:+.1f} dB")
        self._lock = False

    def _on_type(self, dd, _p):
        if not self._lock:
            self.win.set_band(self.idx, type=TYPE_KEYS[dd.get_selected()])

    def _on_gain(self, s):
        self.gain_lbl.set_label(f"{s.get_value():+.1f} dB")
        if not self._lock:
            self.win.set_band(self.idx, gain=round(s.get_value(), 2))

    def _on_freq(self, s):
        if not self._lock:
            self.win.set_band(self.idx, freq=s.get_value())

    def _on_q(self, s):
        if not self._lock:
            self.win.set_band(self.idx, q=round(s.get_value(), 3))


# ------------------------------------------------------------------ Window


class PanelWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="AIYIMA DAC-A5 Pro")
        self.set_default_size(1120, 900)

        self.conf = be.load_conf()
        self.saved = copy.deepcopy(self.conf.profile)  # diskteki hali
        self.live_types = [b.type for b in self.saved.bands]  # çalışan filtre tipleri
        self.profile = copy.deepcopy(self.saved)
        self.node_id = be.find_node_id(self.conf.capture_name)
        self._sync_from_live()
        self.bypass = False
        self.graph_rate = 48000
        self.card = be.find_card()
        self._pending = {}
        self._flush_id = 0
        self._hw_lock = False
        self._seed_presets()

        self.toasts = Adw.ToastOverlay()
        view = Adw.ToolbarView()
        header = Adw.HeaderBar()
        self.stack = Adw.ViewStack()
        switcher = Adw.ViewSwitcher(stack=self.stack, policy=Adw.ViewSwitcherPolicy.WIDE)
        header.set_title_widget(switcher)
        refresh = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text="Cihazdan yeniden oku")
        refresh.connect("clicked", lambda *_: self.reload_all())
        header.pack_end(refresh)
        view.add_top_bar(header)

        self.banner = Adw.Banner()
        self.banner.connect("button-clicked", self._on_banner)
        view.add_top_bar(self.banner)

        self.stack.add_titled_with_icon(self._build_eq_page(), "eq", "Ekolayzır", "media-eq-symbolic")
        self.stack.add_titled_with_icon(self._build_device_page(), "device", "Cihaz", "audio-card-symbolic")
        view.set_content(self.stack)
        self.toasts.set_child(view)
        self.set_content(self.toasts)

        self._sync_eq_ui()
        self._refresh_device()
        GLib.timeout_add_seconds(2, self._tick)

    # ------------------------------------------------------------- state
    def _sync_from_live(self):
        if self.node_id is None:
            return
        live = be.read_live(self.node_id)
        if not live:
            return
        self.profile.preamp = float(live.get("eq_preamp:Gain", self.profile.preamp))
        for b in self.profile.bands:
            b.freq = float(live.get(f"{b.name}:Freq", b.freq))
            b.q = float(live.get(f"{b.name}:Q", b.q))
            b.gain = float(live.get(f"{b.name}:Gain", b.gain))

    def _seed_presets(self):
        if not any(p.name == self.saved.name for p in be.list_presets()):
            be.save_preset(self.saved)

    def toast(self, text):
        self.toasts.add_toast(Adw.Toast(title=text, timeout=3))

    def push_live(self, values):
        if self.bypass:
            return
        self._pending.update(values)
        if not self._flush_id:
            self._flush_id = GLib.timeout_add(35, self._flush)

    def _flush(self):
        be.set_live(self.node_id, self._pending)
        self._pending = {}
        self._flush_id = 0
        return False

    def set_band(self, idx, from_curve=False, **kw):
        b = self.profile.bands[idx]
        for k, v in kw.items():
            setattr(b, k, v)
        live = {}
        for k in ("freq", "q", "gain"):
            if k in kw:
                live[f"{b.name}:{k.capitalize() if k != 'q' else 'Q'}"] = kw[k]
        self.push_live(live)
        if from_curve:
            self.band_cards[idx].sync()
        self.curve.queue_draw()
        self._update_banner()

    def _types_changed(self):
        return [b.type for b in self.profile.bands] != self.live_types

    def _dirty(self):
        return be.profile_values(self.profile) != be.profile_values(self.saved) or (
            [b.type for b in self.profile.bands] != [b.type for b in self.saved.bands]
        )

    def _update_banner(self):
        if self._types_changed():
            self.banner.set_title("Filtre tipi değişti: kaydedip PipeWire'ı yeniden başlatınca devreye girer")
            self.banner.set_button_label("Kaydet ve yeniden başlat")
            self.banner.set_revealed(True)
        elif self._dirty():
            self.banner.set_title("Değişiklikler canlı uygulanıyor ama henüz kalıcı değil")
            self.banner.set_button_label("Kalıcı kaydet")
            self.banner.set_revealed(True)
        else:
            self.banner.set_revealed(False)

    def _on_banner(self, _b):
        if self._types_changed():
            self._confirm_restart()
        else:
            self.save_persistent()

    def save_persistent(self, restart=False):
        try:
            backup = be.save_conf(self.conf, self.profile)
        except OSError as e:
            self.toast(f"Kaydedilemedi: {e}")
            return
        self.saved = copy.deepcopy(self.profile)
        self.conf.description = f"AIYIMA DAC-A5 Pro ({self.profile.name} EQ)"
        if restart:
            self._restart()
        else:
            self.toast("Kaydedildi" + (f" (yedek: {backup.name})" if backup else ""))
        self._update_banner()

    def _confirm_restart(self):
        dlg = Adw.AlertDialog(
            heading="PipeWire yeniden başlatılsın mı?",
            body="Profil diske yazılacak ve ses servisi yeniden başlatılacak. "
                 "Çalan ses bir an kesilir.",
        )
        dlg.add_response("cancel", "Vazgeç")
        dlg.add_response("ok", "Kaydet ve yeniden başlat")
        dlg.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)
        dlg.connect("response", lambda _d, r: r == "ok" and self.save_persistent(restart=True))
        dlg.present(self)

    def _restart(self):
        self.toast("PipeWire yeniden başlatılıyor…")

        def work():
            be.restart_pipewire()
            node = None
            for _ in range(20):
                GLib.usleep(250_000)
                node = be.find_node_id(self.conf.capture_name)
                if node is not None:
                    break
            GLib.idle_add(done, node)

        def done(node):
            self.node_id = node
            self.live_types = [b.type for b in self.profile.bands]
            self._update_banner()
            self.toast("Yeni profil devrede" if node else "EQ düğümü bulunamadı")
            return False

        threading.Thread(target=work, daemon=True).start()

    def reload_all(self):
        self.node_id = be.find_node_id(self.conf.capture_name)
        self._sync_from_live()
        self._sync_eq_ui()
        self._refresh_device()
        self.toast("Yeniden okundu")

    # ------------------------------------------------------------- EQ page
    def _build_eq_page(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        box.set_margin_top(18)
        box.set_margin_bottom(24)
        box.set_margin_start(18)
        box.set_margin_end(18)

        curve_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        curve_card.add_css_class("card")
        curve_card.add_css_class("curve-card")
        self.curve = EqCurve(self)
        curve_card.append(self.curve)
        hint = Gtk.Label(
            label="Noktaları sürükle: frekans ve kazanç · Nokta üzerinde tekerlek: Q",
            xalign=0,
        )
        hint.add_css_class("dim-label")
        hint.add_css_class("caption")
        hint.set_margin_start(12)
        hint.set_margin_bottom(8)
        curve_card.append(hint)
        box.append(curve_card)

        group = Adw.PreferencesGroup(title="Profil")
        self.preset_row = Adw.ComboRow(title="Hazır ayar")
        self.preset_row.set_model(Gtk.StringList())
        btns = Gtk.Box(spacing=6, valign=Gtk.Align.CENTER)
        for icon, tip, cb in (
            ("document-save-as-symbolic", "Hazır ayar olarak kaydet", self._on_preset_save),
            ("user-trash-symbolic", "Hazır ayarı sil", self._on_preset_delete),
        ):
            b = Gtk.Button(icon_name=icon, tooltip_text=tip)
            b.add_css_class("flat")
            b.connect("clicked", cb)
            btns.append(b)
        self.preset_row.add_suffix(btns)
        self.preset_row.connect("notify::selected", self._on_preset_selected)
        group.add(self.preset_row)

        self.bypass_row = Adw.SwitchRow(title="EQ'yu devre dışı bırak", subtitle="Karşılaştırma için düz yanıt")
        self.bypass_row.connect("notify::active", self._on_bypass)
        group.add(self.bypass_row)

        self.preamp_row = Adw.SpinRow.new_with_range(-24.0, 6.0, 0.5)
        self.preamp_row.set_title("Preamp")
        self.preamp_row.set_subtitle("Kırpılmayı önlemek için toplam kazanç (dB)")
        self.preamp_row.set_digits(1)
        self.preamp_row.connect("notify::value", self._on_preamp)
        group.add(self.preamp_row)
        box.append(group)

        bands_title = Gtk.Label(label="Bantlar", xalign=0)
        bands_title.add_css_class("heading")
        box.append(bands_title)
        bands = Gtk.Box(spacing=12, homogeneous=True)
        self.band_cards = [BandCard(self, i) for i in range(len(self.profile.bands))]
        for c in self.band_cards:
            bands.append(c)
        box.append(bands)

        clamp = Adw.Clamp(maximum_size=1200, child=box)
        return Gtk.ScrolledWindow(child=clamp, hscrollbar_policy=Gtk.PolicyType.NEVER)

    def _sync_eq_ui(self):
        self._lock_preamp = True
        self.preamp_row.set_value(self.profile.preamp)
        self._lock_preamp = False
        for c in self.band_cards:
            c.sync()
        self._reload_presets(select=self.profile.name)
        self.curve.queue_draw()
        self._update_banner()

    def _reload_presets(self, select=None):
        self._lock_presets = True
        self.presets = be.list_presets()
        model = Gtk.StringList()
        for p in self.presets:
            model.append(p.name)
        self.preset_row.set_model(model)
        self.preset_row.set_selected(Gtk.INVALID_LIST_POSITION)
        self.preset_row.set_subtitle("Özel ayar (kaydedilmemiş)")
        for i, p in enumerate(self.presets):
            if p.name == select:
                self.preset_row.set_selected(i)
                self.preset_row.set_subtitle(p.description)
        self._lock_presets = False

    def _on_preset_selected(self, row, _p):
        i = row.get_selected()
        if 0 <= i < len(getattr(self, "presets", [])):
            row.set_subtitle(self.presets[i].description)
        if not getattr(self, "_lock_presets", False):
            self._on_preset_apply(None)

    def _on_preamp(self, row, _p):
        if getattr(self, "_lock_preamp", False):
            return
        self.profile.preamp = row.get_value()
        self.push_live({"eq_preamp:Gain": self.profile.preamp})
        self.curve.queue_draw()
        self._update_banner()

    def _on_bypass(self, row, _p):
        if row.get_active():
            vals = {"eq_preamp:Gain": 0.0}
            vals.update({f"{b.name}:Gain": 0.0 for b in self.profile.bands})
            be.set_live(self.node_id, vals)
            self.bypass = True
        else:
            self.bypass = False
            be.set_live(self.node_id, be.profile_values(self.profile))
        self.curve.queue_draw()

    def _on_preset_apply(self, _b):
        i = self.preset_row.get_selected()
        if i == Gtk.INVALID_LIST_POSITION or i >= len(self.presets):
            return
        p = copy.deepcopy(self.presets[i])
        if len(p.bands) != len(self.profile.bands):
            self.toast("Bant sayısı farklı: bu panel şimdilik aynı bant sayısını destekliyor")
            return
        for dst, src in zip(self.profile.bands, p.bands):
            dst.type, dst.freq, dst.q, dst.gain = src.type, src.freq, src.q, src.gain
        self.profile.preamp, self.profile.name = p.preamp, p.name
        be.set_live(self.node_id, be.profile_values(self.profile))
        self._sync_eq_ui()
        self.toast(f"“{p.name}” uygulandı")

    def _on_preset_save(self, _b):
        dlg = Adw.AlertDialog(heading="Hazır ayar olarak kaydet")
        entry = Gtk.Entry(text=self.profile.name, activates_default=True)
        dlg.set_extra_child(entry)
        dlg.add_response("cancel", "Vazgeç")
        dlg.add_response("ok", "Kaydet")
        dlg.set_default_response("ok")
        dlg.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)

        def on_resp(_d, r):
            name = entry.get_text().strip()
            if r != "ok" or not name:
                return
            self.profile.name = name
            be.save_preset(self.profile)
            self._reload_presets(select=name)
            self._update_banner()
            self.toast(f"“{name}” kaydedildi")

        dlg.connect("response", on_resp)
        dlg.present(self)

    def _on_preset_delete(self, _b):
        i = self.preset_row.get_selected()
        if i == Gtk.INVALID_LIST_POSITION or i >= len(self.presets):
            return
        name = self.presets[i].name
        if self.presets[i].builtin:
            self.toast("Yerleşik hazır ayarlar silinemez")
            return
        dlg = Adw.AlertDialog(heading=f"“{name}” silinsin mi?")
        dlg.add_response("cancel", "Vazgeç")
        dlg.add_response("del", "Sil")
        dlg.set_response_appearance("del", Adw.ResponseAppearance.DESTRUCTIVE)

        def on_resp(_d, r):
            if r == "del":
                be.delete_preset(name)
                self._reload_presets(select=self.profile.name)

        dlg.connect("response", on_resp)
        dlg.present(self)

    # ------------------------------------------------------------- device page
    def _build_device_page(self):
        page = Adw.PreferencesPage()

        hw = Adw.PreferencesGroup(
            title="Donanım ses seviyesi",
            description="DAC'ın kendi UAC2 kontrolü: 8 kademe, 6 dB adımlarla. "
                        "Bit-perfect için 0 dB önerilir, sesi yazılımdan ya da ön paneldeki düğmeden ayarla.",
        )
        self.hw_row = Adw.ActionRow(title="Seviye")
        self.hw_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 7, 1)
        self.hw_scale.set_digits(0)
        self.hw_scale.set_draw_value(False)
        self.hw_scale.set_size_request(320, -1)
        self.hw_scale.set_valign(Gtk.Align.CENTER)
        for v in range(8):
            self.hw_scale.add_mark(v, Gtk.PositionType.BOTTOM, None)
        self.hw_scale.connect("value-changed", self._on_hw_volume)
        self.hw_row.add_suffix(self.hw_scale)
        hw.add(self.hw_row)
        self.mute_row = Adw.SwitchRow(title="Sessiz (mute)")
        self.mute_row.connect("notify::active", self._on_hw_mute)
        hw.add(self.mute_row)
        page.add(hw)

        st = Adw.PreferencesGroup(title="Akış")
        self.st_status = Adw.ActionRow(title="Durum")
        self.st_rate = Adw.ActionRow(title="Örnekleme hızı")
        self.st_fmt = Adw.ActionRow(title="Format")
        for row in (self.st_status, self.st_rate, self.st_fmt):
            lbl = Gtk.Label()
            lbl.add_css_class("dim-label")
            lbl.add_css_class("numeric")
            row.add_suffix(lbl)
            row.value = lbl
            st.add(row)
        page.add(st)

        clk = Adw.PreferencesGroup(
            title="Örnekleme hızı",
            description="Otomatik modda PipeWire çalan dosyanın hızına geçer (44.1/48/96/192 kHz). "
                        "Zorlama bu oturum için geçerlidir.",
        )
        self.rate_row = Adw.ComboRow(title="Hızı sabitle")
        self.rate_row.set_model(Gtk.StringList.new(["Otomatik"] + [fmt_rate(r) for r in be.SUPPORTED_RATES]))
        self.rate_row.connect("notify::selected", self._on_rate)
        clk.add(self.rate_row)
        self.clk_default = Adw.ActionRow(title="Varsayılan saat hızı")
        lbl = Gtk.Label()
        lbl.add_css_class("dim-label")
        self.clk_default.add_suffix(lbl)
        self.clk_default.value = lbl
        clk.add(self.clk_default)
        page.add(clk)

        info = Adw.PreferencesGroup(title="Cihaz")
        for title, val in (
            ("USB kimliği", "262a:9123 · Savitech SA9123L · UAC2"),
            ("DAC yongası", "ESS ES9018K2M"),
            ("Desteklenen hızlar", "44.1 – 192 kHz, 16/24 bit"),
            ("EQ yapılandırması", str(self.conf.path).replace(str(be.Path.home()), "~")),
        ):
            row = Adw.ActionRow(title=title, subtitle=val, subtitle_selectable=True)
            info.add(row)
        page.add(info)
        return page

    def _refresh_device(self):
        self.card = be.find_card() if self.card is None else self.card
        hw = be.read_hw(self.card) if self.card is not None else None
        self.hw_row.set_sensitive(hw is not None)
        self.mute_row.set_sensitive(hw is not None)
        if hw:
            self._hw_lock = True
            self.hw_scale.set_range(0, hw.vol_max)
            self.hw_scale.set_value(hw.volume)
            self.mute_row.set_active(hw.mute)
            self._hw_lock = False
            self._update_hw_subtitle(hw.volume)
        else:
            self.hw_row.set_subtitle("DAC bulunamadı")
        s = be.read_stream(self.card) if self.card is not None else None
        if s:
            self.st_status.value.set_label("Çalıyor" if s.running else "Boşta")
            self.st_rate.value.set_label(fmt_rate(s.rate) if s.running else "—")
            self.st_fmt.value.set_label(s.fmt)
            if s.running and s.rate:
                self.graph_rate = s.rate
        clk = be.read_clock()
        self.clk_default.value.set_label(fmt_rate(int(clk.get("clock.rate", "0") or 0)))
        forced = int(clk.get("clock.force-rate", "0") or 0)
        self._hw_lock = True
        self.rate_row.set_selected(RATE_CHOICES.index(forced) if forced in RATE_CHOICES else 0)
        self._hw_lock = False

    def _update_hw_subtitle(self, step):
        db = -42 + 6 * step
        self.hw_row.set_subtitle(f"Kademe {int(step)}/7 · {db:+d} dB" if db else f"Kademe {int(step)}/7 · 0 dB")

    def _on_hw_volume(self, s):
        step = int(round(s.get_value()))
        self._update_hw_subtitle(step)
        if not self._hw_lock and self.card is not None:
            be.set_hw_volume(self.card, step)

    def _on_hw_mute(self, row, _p):
        if not self._hw_lock and self.card is not None:
            be.set_hw_mute(self.card, row.get_active())

    def _on_rate(self, row, _p):
        if self._hw_lock:
            return
        be.set_force_rate(RATE_CHOICES[row.get_selected()])
        GLib.timeout_add(600, lambda: (self._refresh_device(), False)[1])

    def _tick(self):
        if self.stack.get_visible_child_name() == "device" and not self.hw_scale.has_focus():
            self._refresh_device()
        else:
            s = be.read_stream(self.card) if self.card is not None else None
            if s and s.running and s.rate and s.rate != self.graph_rate:
                self.graph_rate = s.rate
                self.curve.queue_draw()
        return True


CSS = """
.band-card { padding: 14px; }
.curve-card { padding: 6px 6px 0 6px; }
"""


class PanelApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)

    def do_startup(self):
        Adw.Application.do_startup(self)
        prov = Gtk.CssProvider()
        prov.load_from_string(CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), prov, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def do_activate(self):
        win = self.get_active_window() or PanelWindow(self)
        if getattr(self, "start_page", None):
            win.stack.set_visible_child_name(self.start_page)
        win.present()


def main():
    argv = list(sys.argv)
    page = "device" if "--cihaz" in argv else None
    argv = [a for a in argv if a != "--cihaz"]
    app = PanelApp()
    app.start_page = page
    return app.run(argv)
