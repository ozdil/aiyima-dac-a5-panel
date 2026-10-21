"""Yerleşik EQ hazır ayarları.

Hepsi mevcut filter-chain ile aynı bant düzenini kullanır
(alçak raf, alçak raf, tepe, tepe, yüksek raf), böylece PipeWire'ı
yeniden başlatmadan canlı uygulanırlar. Preamp, toplam yanıtın tepesi
0 dB'i geçmeyecek şekilde otomatik hesaplanır.
"""

import functools
import math

from . import biquad

LS, PK, HS = "bq_lowshelf", "bq_peaking", "bq_highshelf"

# (ad, açıklama, [(tip, frekans, Q, kazanç) x 5])
BUILTIN = [
    ("Düz", "EQ etkisiz, referans dinleme",
     [(LS, 60, 0.7, 0), (LS, 150, 0.7, 0), (PK, 1000, 1.0, 0), (PK, 3000, 1.0, 0), (HS, 8000, 0.7, 0)]),
    ("Bas Güçlendirme", "Alt bas ve basa sıcak bir destek",
     [(LS, 60, 0.7, 6), (LS, 150, 0.7, 1.5), (PK, 1000, 1.0, 0), (PK, 3000, 1.0, 0), (HS, 8000, 0.7, 0)]),
    ("Tiz Parlaklık", "Detay ve hava hissi için üst frekans vurgusu",
     [(LS, 60, 0.7, 0), (LS, 150, 0.7, 0), (PK, 1000, 1.0, 0), (PK, 4000, 1.0, 2), (HS, 8000, 0.7, 4)]),
    ("V-Şekli", "Eğlenceli: güçlü bas, geride orta, parlak tiz",
     [(LS, 60, 0.7, 5), (LS, 150, 0.7, 1), (PK, 800, 0.8, -3), (PK, 3500, 1.2, 1.5), (HS, 9000, 0.7, 4)]),
    ("Vokal", "Sesleri öne çıkarır, bası hafifçe toplar",
     [(LS, 80, 0.7, -2), (LS, 200, 0.7, -1), (PK, 1500, 0.9, 3), (PK, 3000, 1.4, 2), (HS, 10000, 0.7, -1)]),
    ("Rock", "Vurucu bas ve gitar/zil netliği",
     [(LS, 80, 0.7, 4), (LS, 250, 0.7, -1), (PK, 900, 1.0, -1.5), (PK, 3000, 1.0, 3), (HS, 9000, 0.7, 3)]),
    ("Elektronik", "Derin sub-bas ve parlak üst uç",
     [(LS, 50, 0.7, 6), (LS, 120, 0.7, 2), (PK, 500, 1.0, -2), (PK, 2500, 1.0, 1), (HS, 10000, 0.7, 4)]),
    ("Akustik / Klasik", "Doğal tını, hafif sıcaklık ve hava",
     [(LS, 80, 0.7, 1.5), (LS, 200, 0.7, 1), (PK, 1200, 0.8, 0), (PK, 3500, 1.5, 1.5), (HS, 12000, 0.7, 2)]),
    ("Gece (Düşük Ses)", "Loudness: kısık seste kaybolan bas ve tizi telafi eder",
     [(LS, 60, 0.7, 7), (LS, 150, 0.7, 2), (PK, 1000, 1.0, 0), (PK, 4000, 1.0, 2), (HS, 10000, 0.7, 5)]),
    ("Konuşma / Podcast", "Uğultuyu keser, anlaşılırlığı artırır, sert 's' seslerini yumuşatır",
     [(LS, 100, 0.7, -6), (LS, 200, 0.7, -2), (PK, 2500, 1.0, 3), (PK, 6000, 2.0, -2), (HS, 10000, 0.7, -2)]),
]


@functools.lru_cache(maxsize=64)
def _auto_preamp(bands, rate):
    freqs = [20 * (1000 ** (i / 299)) for i in range(300)]
    peak = max(biquad.response(bands, freqs, rate))
    return 0.0 if peak <= 0 else -math.ceil(peak * 2) / 2


def auto_preamp(bands, rate=48000):
    return _auto_preamp(tuple(tuple(b) for b in bands), rate)


def builtin_profiles():
    from .backend import Band, EqProfile

    out = []
    for name, desc, bands in BUILTIN:
        prof = EqProfile(
            name, auto_preamp(bands),
            [Band(f"eq_band_{i + 1}", t, float(f), float(q), float(g)) for i, (t, f, q, g) in enumerate(bands)],
        )
        prof.builtin = True
        prof.description = desc
        out.append(prof)
    return out
