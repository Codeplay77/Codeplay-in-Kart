"""Reproducible audio polish. Originals remain untouched.
Requires Python, numpy, scipy and ffmpeg on PATH. No downloads.
Recorded loops stay at their native 44.1 kHz, exported as lossless PCM;
new band-limited arcade cues are synthesized at 48 kHz.
"""
from pathlib import Path
import json
import re
import subprocess
import numpy as np
from scipy import signal
from scipy.io import wavfile

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "assets/audio/sfx"
DEST = ROOT / "assets/audio/refined"
REPORT = []


def decode(path):
    raw = subprocess.check_output(["ffmpeg", "-v", "error", "-i", str(path),
                                   "-ar", "44100", "-ac", "1", "-f", "f32le", "pipe:1"])
    return np.frombuffer(raw, dtype="<f4").astype(float), 44100


def peak_eq(x, rate, hz, db, q=0.8):
    a = 10 ** (db / 40)
    w = 2 * np.pi * hz / rate
    alpha = np.sin(w) / (2 * q)
    b = [1 + alpha * a, -2 * np.cos(w), 1 - alpha * a]
    c = [1 + alpha / a, -2 * np.cos(w), 1 - alpha / a]
    return signal.lfilter(b, c, x)


def clean(x, rate, low, high, dip, periodic=False):
    n = len(x)
    # Warm up filters on repeated cycles; never introduce a zero-state loop seam.
    y = np.tile(x, 5) if periodic else x
    y = signal.sosfilt(signal.butter(2, low, "highpass", fs=rate, output="sos"), y)
    y = peak_eq(y, rate, 2800, dip)
    y = signal.sosfilt(signal.butter(2, high, "lowpass", fs=rate, output="sos"), y)
    return y[3*n:4*n] if periodic else y


def save(name, x, rate, rms_db=-20, peak_db=-5, loop=False):
    x = x - np.mean(x)
    rms = np.sqrt(np.mean(x*x))
    gain = min(10 ** (rms_db / 20) / max(rms, 1e-9),
               10 ** (peak_db / 20) / max(np.max(np.abs(x)), 1e-9))
    x *= gain
    if not loop:
        edge = min(int(rate * 0.006), len(x) // 4)
        x[:edge] *= np.linspace(0, 1, edge)
        x[-edge:] *= np.linspace(1, 0, edge)
    path = DEST / (name + ".wav")
    path.parent.mkdir(parents=True, exist_ok=True)
    wavfile.write(path, rate, np.round(np.clip(x, -1, 1) * 32767).astype("int16"))
    # Godot defaults WAV imports to QOA. Keep these short loops/cues as PCM too.
    import_path = Path(str(path) + ".import")
    if import_path.exists():
        config = import_path.read_text(encoding="utf-8")
        config = re.sub(r"compress/mode=\d+", "compress/mode=0", config)
    else:
        config = '[remap]\n\nimporter="wav"\ntype="AudioStreamWAV"\n\n[params]\n\ncompress/mode=0\n'
    import_path.write_text(config, encoding="utf-8")
    REPORT.append({"file": name + ".wav", "rate": rate, "seconds": round(len(x)/rate, 3),
                   "peak_dbfs": round(float(20*np.log10(max(np.max(abs(x)), 1e-9))), 2),
                   "rms_dbfs": round(float(20*np.log10(max(np.sqrt(np.mean(x*x)), 1e-9))), 2),
                   "loop_seam_step": round(float(abs(x[0]-x[-1])), 6) if loop else None})


def cue(notes, duration, seed=0):
    rate = 48000
    out = np.zeros(int((duration + 0.2) * rate))
    rng = np.random.default_rng(seed)
    for start, frequency, length, amplitude in notes:
        t = np.arange(int(length * rate)) / rate
        envelope = (1 - np.exp(-t / 0.004)) * np.exp(-t / (length * 0.28))
        envelope *= np.minimum(1, (length - t) / 0.025)
        tone = (np.sin(2*np.pi*frequency*t + 0.12*np.sin(2*np.pi*frequency*2*t))
                + 0.16*np.sin(2*np.pi*frequency*2*t)*np.exp(-t/0.06)
                + 0.035*rng.normal(size=len(t))*np.exp(-t/0.009))
        for delay, level in [(0, 1), (0.065, .12), (.115, .06)]:
            i = int((start + delay) * rate)
            count = min(len(t), len(out) - i)
            out[i:i+count] += tone[:count] * envelope[:count] * amplitude * level
    return out, rate


def main():
    for path in list((SOURCE / "engine").rglob("*.ogg")) + [SOURCE / "engine_idle.ogg", SOURCE / "engine_high.ogg", SOURCE / "skid_loop.ogg"]:
        x, rate = decode(path)
        bike = "2stroke" in str(path)
        skid = path.stem == "skid_loop"
        x = clean(x, rate, 65 if bike else (180 if skid else 22),
                  4200 if skid else 6800, -5 if bike or skid else -2.5, periodic=True)
        save(str(path.relative_to(SOURCE).with_suffix("")).replace("\\", "/"), x, rate,
             rms_db=-18, peak_db=-5, loop=True)

    for name, source in {"boost": "boost.ogg", "hit": "item_hit.wav", "crash": "crash.wav",
                         "bump": "bump.wav", "cheer": "crowd_cheer.ogg", "screech": "skid_screech.ogg",
                         "click": "ui_select.wav", "confirm": "ui_confirm.wav", "back": "ui_back.wav"}.items():
        x, rate = decode(SOURCE / source)
        x = clean(x, rate, 45, 8500, -2.5)
        save(name, x, rate, -23 if name in ("click", "back", "confirm") else -20)

    motifs = {
        "beep": ([(0, 660, .18, .7), (0, 1320, .13, .15)], .2),
        "go": ([(0, 880, .4, .7), (0, 1320, .4, .25), (.04, 1760, .28, .12)], .45),
        "pickup": ([(0, 659.25, .16, .6), (.075, 987.77, .19, .6), (.15, 1318.51, .24, .5)], .4),
        "item_ready": ([(0, 783.99, .16, .6), (.09, 1174.66, .27, .5)], .38),
        "drift_level": ([(0, 987.77, .13, .55), (.065, 1480, .2, .4)], .3),
        "lap": ([(0, 659.25, .19, .6), (.11, 830.61, .19, .5), (.22, 987.77, .35, .5)], .6),
        "finish": ([(0, 523.25, .22, .6), (.14, 659.25, .22, .5), (.28, 783.99, .22, .5), (.42, 1046.5, .5, .5)], .95),
    }
    for name, (notes, duration) in motifs.items():
        x, rate = cue(notes, duration)
        save(name, x, rate, -22, -6)
    rate = 48000
    t = np.arange(int(rate * .32)) / rate
    rng = np.random.default_rng(124)
    noise = signal.sosfilt(signal.butter(2, [600, 5200], "bandpass", fs=rate, output="sos"), rng.normal(size=len(t)))
    phase = 2*np.pi*(880*t - 900*t*t)
    x = (.45*np.sin(phase) + .25*noise) * (1-np.exp(-t/.004)) * np.exp(-t/.065)
    save("shoot", x, rate, -22, -6)
    report = ROOT / "docs/audio_processing.json"
    report.write_text(json.dumps(REPORT, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(REPORT)} lossless audio assets and {report.name}")


if __name__ == "__main__":
    main()
