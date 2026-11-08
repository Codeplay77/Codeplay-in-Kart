"""Gerador de traçados de pista para o Codeplay in Kart.

Gera circuitos fechados a partir de polígonos em estrela (cantos arredondados pela curva
Catmull-Rom/Bezier usada no Godot), valida restrições físicas e escreve
`scripts/track/track_layouts.gd` com os pontos de controle e os elementos de cada pista
(caixas de item, placas de turbo e rampas).

Uso:
    python tools/track_gen/generate_layouts.py            # gera o .gd
    python tools/track_gen/generate_layouts.py --preview out.png   # + imagem com os traçados

Restrições verificadas (devem bater com scripts/track/track.gd):
  * raio mínimo de curva (planta)            -> MIN_RADIUS
  * distância entre trechos não vizinhos      -> MIN_SEPARATION (guard-rails não se cruzam)
  * inclinação máxima                          -> MAX_GRADE
  * reta de largada                            -> START_STRAIGHT metros retos antes e depois da linha
"""

from __future__ import annotations

import argparse
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT_GD = os.path.join(ROOT, "scripts", "track", "track_layouts.gd")

MIN_SEPARATION = 52.0   # 2 * (meia pista + guard-rail + folga)
MAX_GRADE = 0.11
START_STRAIGHT = 70.0

# Gabaritos: polígonos simples (x, z) em metros. Os cantos são arredondados por filetes;
# cada tentativa aplica variação aleatória, escala e espelhamento.
# id, nome, tema, gabarito, amplitude de elevação, raio mínimo, semente
TRACKS = [
    ("dunas_douradas", "Dunas Douradas", "desert",
     [(0, 0), (320, 0), (390, 70), (330, 170), (200, 130), (110, 210), (-40, 160), (-60, 60)], 7.0, 30, 11),
    ("praia_coqueiral", "Praia Coqueiral", "beach",
     [(0, 0), (360, 0), (400, 90), (330, 170), (250, 120), (170, 170), (60, 170), (-30, 100)], 3.0, 30, 21),
    ("bosque_outonal", "Bosque Outonal", "autumn",
     [(0, 0), (250, -20), (350, 60), (330, 200), (230, 170), (170, 250), (40, 240), (-40, 120)], 9.0, 28, 31),
    ("pico_nevado", "Pico Nevado", "snow",
     [(0, 0), (300, 0), (340, 120), (210, 150), (300, 240), (180, 330), (40, 270), (-30, 130)], 15.0, 26, 41),
    ("canion_vermelho", "Cânion Vermelho", "canyon",
     [(0, 0), (400, 0), (430, 120), (240, 140), (200, 330), (60, 360), (-20, 200)], 11.0, 26, 51),
    ("avenida_neon", "Avenida Neon", "night",
     [(0, 0), (330, 0), (330, 130), (200, 130), (200, 260), (40, 260), (-50, 150)], 3.0, 24, 61),
    ("charneca_nevoa", "Charneca da Névoa", "moor",
     [(0, 0), (380, -40), (300, 120), (390, 260), (160, 220), (-40, 290), (40, 120)], 10.0, 26, 71),
    ("cratera_ardente", "Cratera Ardente", "volcano",
     [(0, 0), (300, 0), (390, 120), (330, 260), (210, 290), (175, 150), (115, 290), (-20, 250), (-60, 100)], 12.0, 24, 81),
    ("oasis_escondido", "Oásis Escondido", "desert",
     [(0, 0), (360, 0), (420, 140), (300, 175), (380, 300), (180, 330), (140, 200), (20, 290), (-60, 140)], 8.0, 24, 91),
    ("ilha_dos_ventos", "Ilha dos Ventos", "beach",
     [(0, 0), (250, 0), (330, -80), (440, 40), (360, 160), (420, 280), (240, 300), (100, 210), (-40, 260), (-70, 100)], 5.0, 24, 101),
    ("geleira_cristal", "Geleira Cristal", "snow",
     [(0, 0), (350, 0), (430, 100), (260, 135), (420, 210), (400, 330), (150, 340), (150, 210), (30, 300), (-50, 150)], 16.0, 23, 111),
    ("metropole_noturna", "Metrópole Noturna", "night",
     [(0, 0), (400, 0), (400, 140), (290, 140), (290, 270), (400, 270), (400, 400), (120, 400), (120, 260), (-30, 260)], 4.0, 22, 121),
    ("desfiladeiro_eco", "Desfiladeiro do Eco", "canyon",
     [(0, 0), (420, 0), (480, 110), (330, 160), (470, 250), (430, 370), (240, 330), (180, 440), (20, 400), (70, 250), (-40, 150)], 14.0, 22, 131),
    ("floresta_ancestral", "Floresta Ancestral", "autumn",
     [(0, 0), (380, -20), (450, 90), (320, 150), (390, 270), (240, 340), (160, 240), (80, 390), (-70, 310), (20, 170), (-70, 90)], 12.0, 22, 141),
    ("coracao_vulcao", "Coração do Vulcão", "volcano",
     [(0, 0), (382, 0), (442, 110), (340, 149), (442, 255), (366, 366), (238, 332), (212, 217), (128, 348), (0, 332), (51, 200), (-60, 119)], 13.0, 20, 157),
]


# Curva igual à do Godot (Bezier com alças Catmull-Rom (p[i+1]-p[i-1])/6)

def dense_curve(pts: np.ndarray, steps: int = 40) -> np.ndarray:
    n = len(pts)
    out = []
    for i in range(n):
        p0, p1 = pts[i], pts[(i + 1) % n]
        t0 = (pts[(i + 1) % n] - pts[(i - 1) % n]) / 6.0
        t1 = (pts[(i + 2) % n] - pts[i]) / 6.0
        c0, c1 = p0 + t0, p1 - t1
        for s in range(steps):
            t = s / steps
            u = 1 - t
            out.append(u ** 3 * p0 + 3 * u * u * t * c0 + 3 * u * t * t * c1 + t ** 3 * p1)
    return np.array(out)


def resample(poly: np.ndarray, step: float) -> np.ndarray:
    seg = np.linalg.norm(np.diff(np.vstack([poly, poly[:1]]), axis=0), axis=1)
    cum = np.concatenate([[0], np.cumsum(seg)])
    total = cum[-1]
    s = np.arange(0, total, step)
    closed = np.vstack([poly, poly[:1]])
    res = np.empty((len(s), 3))
    for k in range(3):
        res[:, k] = np.interp(s, cum, closed[:, k])
    return res


def analyze(points: np.ndarray, min_radius: float) -> tuple[bool, dict]:
    poly = resample(dense_curve(points), 2.0)
    n = len(poly)
    length = n * 2.0
    xz = poly[:, [0, 2]]
    k = 3
    a, c = np.roll(xz, k, axis=0), np.roll(xz, -k, axis=0)
    d1, d2 = xz - a, c - xz
    ang = np.arctan2(d1[:, 0] * d2[:, 1] - d1[:, 1] * d2[:, 0], (d1 * d2).sum(1))
    dist = (np.linalg.norm(d1, axis=1) + np.linalg.norm(d2, axis=1)) * 0.5
    radii = dist / np.maximum(np.abs(ang), 1e-6)
    sub = xz[::3]
    m = len(sub)
    dm = np.linalg.norm(sub[:, None, :] - sub[None, :, :], axis=2)
    idx = np.arange(m)
    arc = np.abs(idx[:, None] - idx[None, :])
    arc = np.minimum(arc, m - arc) * 6.0
    min_sep = dm[arc > 130].min()
    grade = np.abs(np.diff(np.concatenate([poly[:, 1], poly[:1, 1]]))) / 2.0
    s_cells = int(START_STRAIGHT / 2.0)
    start_r = np.concatenate([radii[-s_cells:], radii[:s_cells]]).min()
    info = dict(length=length, min_radius=radii.min(), min_sep=min_sep, max_grade=grade.max(),
                start_radius=start_r, radii=radii, poly=poly)
    info["why"] = ("raio" if radii.min() < min_radius else "") + (" sep" if min_sep < MIN_SEPARATION else "") + (" grade" if grade.max() > MAX_GRADE else "") + (" start" if start_r <= 220 else "") + (" len" if not 850 <= length <= 2000 else "")
    ok = (radii.min() >= min_radius and min_sep >= MIN_SEPARATION and grade.max() <= MAX_GRADE
          and start_r > 220 and 850 <= length <= 2000)
    return ok, info


def make_layout(rng: np.random.Generator, template: list, elev: float, min_radius: float = 30.0) -> np.ndarray | None:
    """Gabarito -> cantos arredondados com filetes circulares -> pontos de controle."""
    verts = np.array(template, dtype=float)
    verts = verts - verts.mean(axis=0)
    verts *= rng.uniform(0.95, 1.12)
    verts += rng.normal(0, 10.0, verts.shape)
    if rng.uniform() < 0.5:
        verts[:, 0] *= -1
        verts = verts[::-1]
    ang = rng.uniform(0, 2 * math.pi)
    rot = np.array([[math.cos(ang), -math.sin(ang)], [math.sin(ang), math.cos(ang)]])
    verts = verts @ rot.T
    corners = len(verts)
    n = corners
    fillets = []
    for i in range(n):
        p_prev, v, p_next = verts[i - 1], verts[i], verts[(i + 1) % n]
        u = (v - p_prev) / np.linalg.norm(v - p_prev)
        w = (p_next - v) / np.linalg.norm(p_next - v)
        turn = math.atan2(u[0] * w[1] - u[1] * w[0], u @ w)
        rf = rng.uniform(min_radius * 1.05, min_radius * 2.6)
        t = rf * math.tan(abs(turn) / 2)
        lim = 0.48 * min(np.linalg.norm(v - p_prev), np.linalg.norm(p_next - v))
        if t > lim:
            rf *= lim / t
            t = lim
        if rf < min_radius * 0.95:
            return None
        fillets.append((v - u * t, v + w * t, turn, rf, u))
    pts = []
    straight_mid = []
    for i in range(n):
        t1, t2, turn, rf, u = fillets[i]
        arc_len = abs(turn) * rf
        m = max(2, int(math.ceil(arc_len / 22.0)))
        normal = np.array([-u[1], u[0]]) * (1 if turn > 0 else -1)
        center = t1 + normal * rf
        a0 = math.atan2(t1[1] - center[1], t1[0] - center[0])
        for j in range(m + 1):
            a = a0 + turn * j / m
            pts.append(center + rf * np.array([math.cos(a), math.sin(a)]))
        nxt = fillets[(i + 1) % n][0]
        seg = np.linalg.norm(nxt - t2)
        k = max(1, int(round(seg / 60.0)))
        first = len(pts)
        for j in range(1, k):
            pts.append(t2 + (nxt - t2) * j / k)
        straight_mid.append((seg, first, k, t2, nxt))
    pts = np.array(pts)
    seg, first, k, a, b = max(straight_mid, key=lambda x: x[0])
    if seg < 150:
        return None
    mid = (a + b) / 2
    idx = int(np.argmin(np.linalg.norm(pts - mid, axis=1)))
    pts[idx] = mid
    pts = np.roll(pts, -idx, axis=0)
    clean = [pts[0]]
    for p in pts[1:]:
        if np.linalg.norm(p - clean[-1]) > 6.0:
            clean.append(p)
    pts = np.array(clean)
    if rng.uniform() < 0.5:
        pts = np.vstack([pts[:1], pts[1:][::-1]])
    n = len(pts)
    seglen = np.linalg.norm(np.roll(pts, -1, axis=0) - pts, axis=1)
    s = np.concatenate([[0], np.cumsum(seglen)[:-1]]) / seglen.sum()
    y = np.zeros(n)
    for kk in (1, 2, 3):
        y += rng.uniform(-1, 1) * np.sin(2 * math.pi * kk * s + rng.uniform(0, 2 * math.pi)) / kk
    y -= y[0]
    flat = np.minimum(1.0, np.minimum(s, 1 - s) * 8.0)
    y = y * flat
    if np.abs(y).max() > 0:
        y = y / np.abs(y).max() * elev
    grade = np.abs(np.diff(np.concatenate([y, y[:1]]))) / np.maximum(seglen, 1.0)
    if grade.max() > MAX_GRADE * 0.7:
        y *= MAX_GRADE * 0.7 / grade.max()
    return np.stack([pts[:, 0], y, pts[:, 1]], axis=1)


def choose_features(info: dict) -> dict:
    """Escolhe posições (fração da volta) para itens, turbos e rampa em trechos retos."""
    radii = info["radii"]
    n = len(radii)
    straight = np.array([radii[max(0, i - 10):i + 10].min() if i >= 10 else min(radii[:i + 10].min(), radii[i - 10:].min()) for i in range(n)]) > 140

    def nearest_straight(frac: float, avoid: list[float]) -> float:
        best, bd = frac, 1e9
        for i in range(n):
            if not straight[i]:
                continue
            f = i / n
            if any(min(abs(f - a), 1 - abs(f - a)) < 0.05 for a in avoid):
                continue
            d = min(abs(f - frac), 1 - abs(f - frac))
            if d < bd:
                bd, best = d, f
        return round(best, 3)

    used: list[float] = [0.0]
    items = []
    for f in (0.22, 0.5, 0.78):
        v = nearest_straight(f, used)
        items.append(v)
        used.append(v)
    boosts = []
    for f, lat in ((0.12, 0.35), (0.4, -0.35), (0.66, 0.0)):
        v = nearest_straight(f, used)
        boosts.append((v, lat))
        used.append(v)
    long_straight = np.array([all(straight[(i + j) % n] for j in range(0, 30)) for i in range(n)])
    ramp = None
    for f in (0.58, 0.3, 0.85, 0.45):
        cands = [i / n for i in range(n) if long_straight[i] and all(min(abs(i / n - a), 1 - abs(i / n - a)) > 0.06 for a in used)]
        if cands:
            ramp = round(min(cands, key=lambda c: min(abs(c - f), 1 - abs(c - f))), 3)
            break
    return dict(items=items, boosts=boosts, ramp=ramp)


def build_all() -> list[dict]:
    results = []
    for tid, name, theme, template, elev, min_r, seed in TRACKS:
        why = {}
        for attempt in range(3000):
            rng = np.random.default_rng(seed * 1000 + attempt)
            pts = make_layout(rng, template, elev, min_r)
            if pts is None:
                why['fillet'] = why.get('fillet', 0) + 1
                continue
            ok, info = analyze(pts, min_r * 0.8)
            for w in info["why"].split():
                why[w] = why.get(w, 0) + 1
            if ok:
                feats = choose_features(info)
                results.append(dict(id=tid, name=name, theme=theme, points=pts, info=info, feats=feats))
                print(f"{tid:20s} tentativa {attempt:4d}  {info['length']:6.0f} m  raio mín {info['min_radius']:5.1f}  "
                      f"sep {info['min_sep']:5.1f}  rampa {feats['ramp']}")
                break
        else:
            print(f"!! {tid}: nenhum traçado válido {why}")
    return results


def write_gd(results: list[dict]) -> None:
    lines = [
        "class_name TrackLayouts",
        "extends RefCounted",
        "## ARQUIVO GERADO por tools/track_gen/generate_layouts.py — não edite à mão.",
        "## Pontos de controle (x, altura, z) e elementos de cada pista.",
        "",
        "const LAYOUTS := {",
    ]
    for r in results:
        pts = ", ".join(f"Vector3({p[0]:.1f}, {p[1]:.2f}, {p[2]:.1f})" for p in r["points"])
        f = r["feats"]
        boosts = ", ".join(f"[{b[0]}, {b[1]}]" for b in f["boosts"])
        ramp = "[]" if f["ramp"] is None else f"[[{f['ramp']}, 0.38]]"
        lines.append(f'\t"{r["id"]}": {{')
        lines.append(f"\t\t\"points\": [{pts}],")
        lines.append(f"\t\t\"items\": {f['items']},")
        lines.append(f"\t\t\"boosts\": [{boosts}],")
        lines.append(f"\t\t\"ramps\": {ramp},")
        lines.append("\t},")
    lines.append("}")
    with open(OUT_GD, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")
    print("->", OUT_GD)


def preview(results: list[dict], path: str) -> None:
    from PIL import Image, ImageDraw
    cols = 4
    cell = 360
    rows = math.ceil(len(results) / cols)
    img = Image.new("RGB", (cols * cell, rows * cell), (24, 26, 32))
    dr = ImageDraw.Draw(img)
    for idx, r in enumerate(results):
        poly = r["info"]["poly"]
        xz = poly[:, [0, 2]]
        mn, mx = xz.min(0), xz.max(0)
        sc = (cell - 60) / max(mx - mn)
        ox, oy = (idx % cols) * cell + 30, (idx // cols) * cell + 40
        ys = poly[:, 1]
        yr = max(ys.max() - ys.min(), 1)
        for i in range(len(xz)):
            a = (xz[i] - mn) * sc
            b = (xz[(i + 1) % len(xz)] - mn) * sc
            t = (ys[i] - ys.min()) / yr
            col = (int(80 + 175 * t), int(200 - 100 * t), int(255 - 200 * t))
            dr.line([ox + a[0], oy + a[1], ox + b[0], oy + b[1]], fill=col, width=5)
        s0 = (xz[0] - mn) * sc
        dr.ellipse([ox + s0[0] - 7, oy + s0[1] - 7, ox + s0[0] + 7, oy + s0[1] + 7], fill=(255, 255, 255))
        s1 = (xz[8] - mn) * sc
        dr.ellipse([ox + s1[0] - 4, oy + s1[1] - 4, ox + s1[0] + 4, oy + s1[1] + 4], fill=(255, 80, 40))
        dr.text((ox, oy - 30), f"{r['name']} ({r['theme']}) {r['info']['length']:.0f} m", fill=(240, 240, 240))
    img.save(path)
    print("preview ->", path)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", default="")
    args = ap.parse_args()
    res = build_all()
    write_gd(res)
    if args.preview:
        preview(res, args.preview)
