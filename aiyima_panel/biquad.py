"""PipeWire builtin biquad filtrelerinin (spa filter-graph biquad.c) frekans yanıtı."""

import cmath
import math

TYPES = {
    "bq_peaking": "Tepe (Peaking)",
    "bq_lowshelf": "Alçak raf (Low shelf)",
    "bq_highshelf": "Yüksek raf (High shelf)",
}


def coefficients(kind, freq, q, gain_db, rate):
    """(b0, b1, b2, a1, a2) döndürür, a0 ile normalize edilmiş."""
    nyquist = rate / 2.0
    cutoff = freq / nyquist
    a = 10.0 ** (gain_db / 40.0)

    if kind in ("bq_lowshelf", "bq_highshelf"):
        if cutoff >= 1.0:
            return (a * a, 0, 0, 0, 0) if kind == "bq_lowshelf" else (1, 0, 0, 0, 0)
        if cutoff <= 0.0:
            return (1, 0, 0, 0, 0) if kind == "bq_lowshelf" else (a * a, 0, 0, 0, 0)
        w0 = math.pi * cutoff
        s = max(q, 1e-4)
        alpha = math.sin(w0) / 2 * math.sqrt(max((a + 1 / a) * (1 / s - 1) + 2, 0.0))
        k = math.cos(w0)
        k2 = 2 * math.sqrt(a) * alpha
        if kind == "bq_lowshelf":
            b0 = a * ((a + 1) - (a - 1) * k + k2)
            b1 = 2 * a * ((a - 1) - (a + 1) * k)
            b2 = a * ((a + 1) - (a - 1) * k - k2)
            a0 = (a + 1) + (a - 1) * k + k2
            a1 = -2 * ((a - 1) + (a + 1) * k)
            a2 = (a + 1) + (a - 1) * k - k2
        else:
            b0 = a * ((a + 1) + (a - 1) * k + k2)
            b1 = -2 * a * ((a - 1) + (a + 1) * k)
            b2 = a * ((a + 1) + (a - 1) * k - k2)
            a0 = (a + 1) - (a - 1) * k + k2
            a1 = 2 * ((a - 1) - (a + 1) * k)
            a2 = (a + 1) - (a - 1) * k - k2
    elif kind == "bq_peaking":
        if cutoff <= 0.0 or cutoff >= 1.0:
            return (1, 0, 0, 0, 0)
        if q <= 0:
            return (a * a, 0, 0, 0, 0)
        w0 = math.pi * cutoff
        alpha = math.sin(w0) / (2 * q)
        k = math.cos(w0)
        b0 = 1 + alpha * a
        b1 = -2 * k
        b2 = 1 - alpha * a
        a0 = 1 + alpha / a
        a1 = -2 * k
        a2 = 1 - alpha / a
    else:
        return (1, 0, 0, 0, 0)

    return (b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0)


def magnitude_db(coefs, freq, rate):
    b0, b1, b2, a1, a2 = coefs
    z = cmath.exp(-1j * 2 * math.pi * freq / rate)
    h = (b0 + b1 * z + b2 * z * z) / (1 + a1 * z + a2 * z * z)
    return 20 * math.log10(max(abs(h), 1e-9))


def response(bands, freqs, rate):
    """bands: [(kind, freq, q, gain)], toplam yanıt (dB) listesi döndürür."""
    coefs = [coefficients(k, f, q, g, rate) for k, f, q, g in bands]
    return [sum(magnitude_db(c, f, rate) for c in coefs) for f in freqs]
