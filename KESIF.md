# AIYIMA DAC-A5 Pro — cihaz keşfi (2026-10-21, salt okunur)

## USB
- ID `262a:9123` (Savitech SA9123L köprüsü), üretici dizesi "Feixiang", USB 2.0 High Speed, UAC2.
- 4 arayüz: 0 = HID, 1 = AudioControl, 2 = Playback stream, 3 = Capture stream (köprünün sahte girişi; WirePlumber kuralıyla kapalı).
- Playback: S16_LE ve S24_3LE, 44.1/48/88.2/96/176.4/192 kHz, async + feedback EP.
- Çıkış terminali tipi `0x0605` (SPDIF arayüzü): SA9123L, I2S/SPDIF ile ES9018K2M'yi besliyor.

## UAC2 kontrolleri (ALSA card 2)
| Kontrol | Tür | Değer |
|---|---|---|
| PCM Playback Switch | bool, rw | on |
| PCM Playback Volume | 0..7, rw | 6,6 (-42..0 dB, 6 dB adım) |
| Clock Source 1/2 Validity | bool, ro | on |
| Clock Frequency | UAC2 clock, rw | stream açılırken ayarlanıyor |

EQ, dijital filtre, DPLL, kazanç, giriş seçimi gibi kontroller **yok**.

## HID (hidraw7)
Rapor tanımlayıcısı (86 bayt): Consumer page (0x0C), usage 0 olan 8 adet 1-bitlik input (buton/olay biti),
Report ID'si olmayan **16 baytlık output raporu** (usage 0). Belgelenmemiş bir vendor komut kanalı olabilir;
Savitech şablonlarında genelde bulunur. İçeriği bilinmiyor, yazılmadı.
Not: `/dev/hidraw7` izinleri `crwxrwxrwx root:resolve`.

## Mevcut yazılım katmanı
- `~/.config/wireplumber/wireplumber.conf.d/aiyima-dac-a5-pro.conf`: ad düzeltme, S24_3LE, tüm hızlar, suspend kapalı, capture kapalı.
- `~/.config/pipewire/pipewire.conf.d/98-koss-pro4aa-eq.conf`: filter-chain EQ; sistemdeki
  "AIYIMA DAC-A5 Pro (Koss Pro/4AA EQ)" sink'i bu (cihaz değil). Preamp -6 dB + 5 biquad bant. Varsayılan sink bu.
- `99-custom-audio.conf`: clock 48 kHz varsayılan, 44.1–192 kHz izinli, quantum 512.
