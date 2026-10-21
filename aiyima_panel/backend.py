"""PipeWire filter-chain EQ, ALSA donanım kontrolleri ve saat (örnekleme hızı) arka ucu.

Cihaza yalnızca standart UAC2 kontrolleri (PCM ses/mute) üzerinden dokunulur.
HID kanalına hiçbir şey yazılmaz.
"""

import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

USB_CARD_MATCH = ("USB HIFI Audio", "Feixiang")
CONF_DIR = Path.home() / ".config/pipewire/pipewire.conf.d"
DEFAULT_CONF = CONF_DIR / "98-koss-pro4aa-eq.conf"
APP_DIR = Path.home() / ".config/aiyima-dac-panel"
PRESET_DIR = APP_DIR / "presets"
SUPPORTED_RATES = [44100, 48000, 88200, 96000, 176400, 192000]
ENV = dict(os.environ, LC_ALL="C")


def _run(args, check=False):
    return subprocess.run(args, capture_output=True, text=True, env=ENV, check=check)


# --------------------------------------------------------------------------- EQ


@dataclass
class Band:
    name: str
    type: str
    freq: float
    q: float
    gain: float


@dataclass
class EqProfile:
    name: str
    preamp: float
    bands: list = field(default_factory=list)  # list[Band]
    builtin: bool = False
    description: str = ""

    def to_json(self):
        return {
            "name": self.name,
            "preamp": self.preamp,
            "bands": [{k: v for k, v in asdict(b).items() if k != "name"} for b in self.bands],
        }

    @classmethod
    def from_json(cls, data):
        bands = [
            Band(f"eq_band_{i + 1}", b["type"], float(b["freq"]), float(b["q"]), float(b["gain"]))
            for i, b in enumerate(data["bands"])
        ]
        return cls(data.get("name", "Adsız"), float(data.get("preamp", 0.0)), bands)


@dataclass
class ChainConf:
    path: Path
    description: str
    capture_name: str
    playback_name: str
    target: str
    profile: EqProfile


_NODE_RE = re.compile(
    r"name\s*=\s*(\w+)\s*label\s*=\s*(\w+)\s*control\s*=\s*\{\s*"
    r'"Freq"\s*=\s*([-\d.]+)\s*"Q"\s*=\s*([-\d.]+)\s*"Gain"\s*=\s*([-\d.]+)\s*\}'
)


def _prop(text, key, default=""):
    m = re.search(rf'{re.escape(key)}\s*=\s*"?([^"\n]+?)"?\s*$', text, re.M)
    return m.group(1).strip() if m else default


def find_conf():
    if DEFAULT_CONF.exists():
        return DEFAULT_CONF
    for p in sorted(CONF_DIR.glob("*.conf")):
        if "filter-chain" in p.read_text(errors="ignore") and "eq_band_" in p.read_text(errors="ignore"):
            return p
    return DEFAULT_CONF


def load_conf(path=None):
    path = Path(path or find_conf())
    if not path.exists():
        return ChainConf(
            path, "AIYIMA DAC-A5 Pro (EQ)", "effect_input.aiyima_eq", "effect_output.aiyima_eq",
            "alsa_output.usb-Feixiang_USB_HIFI_Audio-01.analog-stereo",
            EqProfile("Düz", 0.0, [Band(f"eq_band_{i + 1}", "bq_peaking", f, 1.0, 0.0)
                                  for i, f in enumerate([60, 250, 1000, 4000, 10000])]),
        )
    text = path.read_text()
    preamp = 0.0
    bands = []
    for name, label, freq, q, gain in _NODE_RE.findall(text):
        if name == "eq_preamp":
            preamp = float(gain)
        else:
            bands.append(Band(name, label, float(freq), float(q), float(gain)))
    cap = re.search(r"capture\.props\s*=\s*\{(.*?)\}", text, re.S)
    play = re.search(r"playback\.props\s*=\s*\{(.*?)\}", text, re.S)
    desc = _prop(text, "node.description", "AIYIMA DAC-A5 Pro (EQ)")
    m = re.search(r"\((.*) EQ\)", desc)
    return ChainConf(
        path,
        desc,
        _prop(cap.group(1), "node.name") if cap else "effect_input.aiyima_eq",
        _prop(play.group(1), "node.name") if play else "effect_output.aiyima_eq",
        _prop(play.group(1), "target.object") if play else "",
        EqProfile(m.group(1) if m else "Mevcut", preamp, bands),
    )


def render_conf(conf: ChainConf, profile: EqProfile):
    def node(name, label, f, q, g):
        return (
            "                    {\n"
            "                        type    = builtin\n"
            f"                        name    = {name}\n"
            f"                        label   = {label}\n"
            f'                        control = {{ "Freq" = {f:.1f} "Q" = {q:.3f} "Gain" = {g:.2f} }}\n'
            "                    }\n"
        )

    names = ["eq_preamp"] + [f"eq_band_{i + 1}" for i in range(len(profile.bands))]
    nodes = node("eq_preamp", "bq_highshelf", 0.0, 1.0, profile.preamp)
    nodes += "".join(node(n, b.type, b.freq, b.q, b.gain) for n, b in zip(names[1:], profile.bands))
    links = "".join(
        f'                    {{ output = "{a}:Out" input = "{b}:In" }}\n' for a, b in zip(names, names[1:])
    )
    desc = f"AIYIMA DAC-A5 Pro ({profile.name} EQ)"
    return f"""# {profile.name} parametrik EQ profili (AIYIMA DAC-A5 Pro)
# aiyima-dac-panel tarafından {time.strftime('%Y-%m-%d %H:%M')} tarihinde yazıldı.

context.modules = [
    {{ name = libpipewire-module-filter-chain
        args = {{
            node.description = "{desc}"
            media.name       = "{desc}"
            filter.graph = {{
                nodes = [
{nodes}                ]
                links = [
{links}                ]
            }}
            audio.channels = 2
            audio.position = [ FL FR ]
            capture.props = {{
                node.name        = "{conf.capture_name}"
                media.class      = Audio/Sink
                device.icon-name = "audio-headphones"
                priority.driver  = 2100
                priority.session = 2100
            }}
            playback.props = {{
                node.name          = "{conf.playback_name}"
                node.passive       = true
                target.object      = "{conf.target}"
                stream.dont-remix  = true
            }}
        }}
    }}
]
"""


def save_conf(conf: ChainConf, profile: EqProfile):
    """Yedek alıp yapılandırmayı yazar. Yedek yolunu döndürür (yoksa None)."""
    backup = None
    if conf.path.exists():
        backup = conf.path.with_name(conf.path.name + f".bak-{time.strftime('%Y%m%d-%H%M%S')}")
        shutil.copy2(conf.path, backup)
    conf.path.parent.mkdir(parents=True, exist_ok=True)
    tmp = conf.path.with_suffix(".tmp")
    tmp.write_text(render_conf(conf, profile))
    tmp.replace(conf.path)
    return backup


def restart_pipewire():
    return _run(["systemctl", "--user", "restart", "pipewire", "pipewire-pulse", "wireplumber"])


def _dump():
    r = _run(["pw-dump"])
    try:
        return json.loads(r.stdout or "[]")
    except json.JSONDecodeError:
        return []


def find_node_id(node_name):
    for o in _dump():
        if o.get("type") == "PipeWire:Interface:Node" and o["info"]["props"].get("node.name") == node_name:
            return o["id"]
    return None


def read_live(node_id):
    """Canlı filter-chain parametreleri: {'eq_band_1:Gain': 5.0, ...}"""
    r = _run(["pw-dump", str(node_id)])
    try:
        obj = json.loads(r.stdout)[0]
    except (json.JSONDecodeError, IndexError):
        return {}
    for p in obj["info"].get("params", {}).get("Props", []):
        it = p.get("params")
        if isinstance(it, list) and it and str(it[0]).startswith("eq_"):
            return {it[i]: it[i + 1] for i in range(0, len(it) - 1, 2)}
    return {}


def set_live(node_id, values):
    """values: {'eq_band_1:Gain': 3.0, ...} — PipeWire'ı yeniden başlatmadan uygular."""
    if node_id is None or not values:
        return
    body = " ".join(f'"{k}" {float(v):.4f}' for k, v in values.items())
    subprocess.Popen(
        ["pw-cli", "set-param", str(node_id), "Props", f"{{ params = [ {body} ] }}"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=ENV,
    )


def profile_values(profile: EqProfile):
    vals = {"eq_preamp:Gain": profile.preamp}
    for b in profile.bands:
        vals.update({f"{b.name}:Freq": b.freq, f"{b.name}:Q": b.q, f"{b.name}:Gain": b.gain})
    return vals


# ---------------------------------------------------------------------- Presets


def _slug(name):
    s = re.sub(r"[^\w-]+", "-", name.strip().lower()).strip("-")
    return s or "preset"


def list_presets():
    """Önce yerleşik hazır ayarlar, sonra kullanıcınınkiler (aynı ad kullanıcıda ise onunki geçerli)."""
    from .presets import builtin_profiles

    PRESET_DIR.mkdir(parents=True, exist_ok=True)
    user = []
    for p in sorted(PRESET_DIR.glob("*.json")):
        try:
            prof = EqProfile.from_json(json.loads(p.read_text()))
        except (json.JSONDecodeError, KeyError, ValueError):
            continue
        prof.builtin, prof.description = False, "Kendi hazır ayarın"
        user.append(prof)
    names = {u.name for u in user}
    return [b for b in builtin_profiles() if b.name not in names] + user


def save_preset(profile: EqProfile):
    PRESET_DIR.mkdir(parents=True, exist_ok=True)
    path = PRESET_DIR / f"{_slug(profile.name)}.json"
    path.write_text(json.dumps(profile.to_json(), ensure_ascii=False, indent=2))
    return path


def delete_preset(name):
    path = PRESET_DIR / f"{_slug(name)}.json"
    if path.exists():
        path.unlink()


# ------------------------------------------------------------------------- ALSA


def find_card():
    try:
        text = Path("/proc/asound/cards").read_text()
    except OSError:
        return None
    for line in text.splitlines():
        m = re.match(r"\s*(\d+)\s+\[", line)
        if m and any(s in line for s in USB_CARD_MATCH):
            return int(m.group(1))
    return None


@dataclass
class HwState:
    card: int
    volume: int  # 0..7
    vol_max: int
    db_min: float
    db_max: float
    mute: bool


def _cget(card, name):
    r = _run(["amixer", "-c", str(card), "cget", f"name={name}"])
    m = re.search(r": values=([^\n]+)", r.stdout)
    return r.stdout, (m.group(1) if m else "")


def read_hw(card):
    out, vals = _cget(card, "PCM Playback Volume")
    if not vals:
        return None
    vmax = int(re.search(r"max=(\d+)", out).group(1)) if "max=" in out else 7
    dbm = re.search(r"dBminmax-min=([-\d.]+)dB,max=([-\d.]+)dB", out)
    _, sw = _cget(card, "PCM Playback Switch")
    return HwState(
        card, int(vals.split(",")[0]), vmax,
        float(dbm.group(1)) if dbm else -42.0, float(dbm.group(2)) if dbm else 0.0,
        sw.strip() == "off",
    )


def set_hw_volume(card, step):
    _run(["amixer", "-c", str(card), "cset", "name=PCM Playback Volume", f"{step},{step}"])


def set_hw_mute(card, mute):
    _run(["amixer", "-c", str(card), "cset", "name=PCM Playback Switch", "off" if mute else "on"])


@dataclass
class StreamState:
    running: bool
    rate: int
    fmt: str


def read_stream(card):
    try:
        text = Path(f"/proc/asound/card{card}/stream0").read_text()
    except OSError:
        return None
    pb = text.split("Capture:")[0]
    running = "Status: Running" in pb
    rate = re.search(r"Momentary freq = (\d+)", pb)
    alt = re.search(r"Altset = (\d+)", pb)
    fmt = "—"
    if alt:
        block = re.search(rf"Altset {alt.group(1)}\n\s+Format: (\S+)", pb)
        fmt = block.group(1) if block else "—"
    return StreamState(running, int(rate.group(1)) if rate else 0, fmt if running else "—")


# ------------------------------------------------------------------------ Clock


def read_clock():
    r = _run(["pw-metadata", "-n", "settings", "0"])
    out = {}
    for k, v in re.findall(r"key:'([\w.-]+)' value:'([^']*)'", r.stdout):
        out[k] = v
    return out


def set_force_rate(rate):
    """0 = otomatik (uygulamanın hızını izler)."""
    _run(["pw-metadata", "-n", "settings", "0", "clock.force-rate", str(int(rate))])
