"""Original, editable SVG artwork for Codeplay in Kart. No external dependencies.
Run: python tools/ui/generate_art.py
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / "assets/ui"


def svg(path, body, width=64, height=64):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">{body}</svg>\n', encoding="utf-8")


icons = {
    "race": '<path d="M15 54V10m1 2c12-8 20 8 34 0v25c-14 8-22-8-34 0"/><path d="M17 15h8v8h-8m8 0h9v8h-9m9-16h8v8h-8m8 0h7v8h-7" fill="#edf5ff" stroke="none"/>',
    "trophy": '<path d="M20 10h24v14c0 11-6 17-12 17s-12-6-12-17Zm0 5H10v7c0 8 6 11 13 11m21-18h10v7c0 8-6 11-13 11M32 41v10m-12 4h24M25 51h14"/>',
    "garage": '<path d="m9 29 23-18 23 18v25H9Zm10 25V31h26v23M20 39h24M20 47h24"/>',
    "settings": '<path d="M13 12v40m19-40v40m19-40v40"/><path d="M7 23h12m7 18h12m7-22h12" stroke-width="9"/>',
    "exit": '<path d="M28 11H12v42h16m8-33 12 12-12 12M24 32h29"/>',
    "back": '<path d="m28 14-18 18 18 18M11 32h43"/>',
    "next": '<path d="m36 14 18 18-18 18M53 32H10"/>',
    "shuffle": '<path d="M10 17h8c12 0 16 30 28 30h8m-9-9 9 9-9 9M10 47h8c5 0 9-6 13-14m7-12c3-3 5-4 8-4h8m-9-9 9 9-9 9"/>',
    "save": '<path d="M12 10h34l7 7v37H12Zm9 0v17h22V10M22 54V37h21v17"/>',
    "lock": '<rect x="15" y="28" width="34" height="27" rx="6"/><path d="M22 28V18a10 10 0 0 1 20 0v10m-10 9v8"/>',
    "helmet": '<path d="M9 37a23 23 0 0 1 46 0v13H26L9 40Zm21-9h24M30 28l-6 11h31"/>',
    "speed": '<path d="M10 49a25 25 0 1 1 44 0M32 16v6M14 26l5 5m31-5-5 5M32 42l12-17"/><circle cx="32" cy="42" r="4"/>',
    "sound": '<path d="m28 14-13 12H7v12h8l13 12Zm10 9a13 13 0 0 1 0 18m8-26a24 24 0 0 1 0 34"/>',
    "display": '<rect x="8" y="10" width="48" height="33" rx="4"/><path d="M32 43v11m-12 0h24"/>',
    "controls": '<path d="M20 20h24c10 0 16 29 8 31-5 2-10-8-13-8H25c-3 0-8 10-13 8-8-2-2-31 8-31ZM19 27v12m-6-6h12m18-4h1m4 8h1"/>',
}
for name, shape in icons.items():
    svg(ART / f"icons/{name}.svg", f'<g fill="none" stroke="#edf5ff" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round">{shape}</g>')

svg(ART / "icons/turbo.svg", '<defs><linearGradient id="g" x2="0" y2="1"><stop stop-color="#fff3a1"/><stop offset="1" stop-color="#ff692f"/></linearGradient></defs><path d="M38 4 10 35h19l-3 25 29-35H36Z" fill="url(#g)" stroke="#ffbb51" stroke-width="2"/><path d="m9 47 9-8m24 12 10-10" stroke="#ff9c41" stroke-width="3" stroke-linecap="round"/>')
svg(ART / "icons/orb.svg", '<defs><radialGradient id="g" cx=".3" cy=".25"><stop stop-color="#e5fffd"/><stop offset=".5" stop-color="#58ffe0"/><stop offset="1" stop-color="#078baf"/></radialGradient></defs><circle cx="32" cy="32" r="28" fill="#36efdf" opacity=".12"/><circle cx="32" cy="32" r="20" fill="url(#g)"/><ellipse cx="32" cy="32" rx="30" ry="10" fill="none" stroke="#9cfff1" stroke-width="2" transform="rotate(-30 32 32)"/><circle cx="25" cy="24" r="5" fill="#fff" opacity=".85"/>')
svg(ART / "icons/mine.svg", '<defs><linearGradient id="g" x2="0" y2="1"><stop stop-color="#53647b"/><stop offset="1" stop-color="#142235"/></linearGradient></defs><path d="m21 24-7-10m29 10 7-10M11 38H4m49 0h7" stroke="#92a1b4" stroke-width="5" stroke-linecap="round"/><ellipse cx="32" cy="42" rx="26" ry="15" fill="#ff6347" opacity=".18"/><path d="M9 40c0-28 46-28 46 0v5c-8 12-38 12-46 0Z" fill="url(#g)" stroke="#a0b3cc" stroke-width="2"/><path d="m16 43 6 7m7-5 6 7m7-8 6 5" stroke="#ffb35c" stroke-width="4"/><circle cx="32" cy="25" r="8" fill="#ff664d"/><circle cx="30" cy="23" r="3" fill="#fff0ce"/>')
svg(ART / "icons/item_empty.svg", '<rect x="11" y="11" width="42" height="42" rx="12" fill="none" stroke="#60738d" stroke-width="2" stroke-dasharray="4 5"/><path d="M24 25c0-10 19-10 17 0-1 6-9 4-9 12m0 7v1" fill="none" stroke="#90a3ba" stroke-width="4" stroke-linecap="round"/>')
svg(ART / "icons/toggle_on.svg", '<rect x="1" y="7" width="46" height="26" rx="13" fill="#ff703e"/><circle cx="34" cy="20" r="9" fill="#fff4e9"/>', 48, 40)
svg(ART / "icons/toggle_off.svg", '<rect x="1" y="7" width="46" height="26" rx="13" fill="#344258"/><circle cx="14" cy="20" r="9" fill="#99aac0"/>', 48, 40)
svg(ART / "icons/slider.svg", '<circle cx="10" cy="10" r="8" fill="#fff1da" stroke="#ff864c" stroke-width="3"/>', 20, 20)

palettes = {
    "valley": ("#254e70", "#f7b17d", "#457975", "#223f4e"),
    "desert": ("#4b456d", "#ffc28b", "#b77552", "#784741"),
    "beach": ("#226f91", "#99e4d1", "#3c9d99", "#186071"),
    "autumn": ("#514563", "#edb080", "#b26448", "#673e45"),
    "snow": ("#345782", "#b7e4f0", "#a0bfd5", "#587f9e"),
    "canyon": ("#573950", "#ffaf78", "#c06b4a", "#713d40"),
    "night": ("#101d43", "#594a87", "#343660", "#18233c"),
    "moor": ("#344957", "#a5baba", "#627c80", "#354d5d"),
    "volcano": ("#24263f", "#c77165", "#683d4a", "#302a3d"),
}
for name, (sky, horizon, far, near) in palettes.items():
    body = f'<defs><linearGradient id="sky" x2="0" y2="1"><stop stop-color="{sky}"/><stop offset="1" stop-color="{horizon}"/></linearGradient></defs><rect width="640" height="320" fill="url(#sky)"/><circle cx="470" cy="105" r="48" fill="#ffe6b2" opacity=".8"/><path d="M0 206 80 110 160 178 270 63 371 183 465 138 550 184 640 114V320H0Z" fill="{far}"/><path d="M0 229 120 174 206 227 320 169 420 228 538 158 640 205V320H0Z" fill="{near}"/>'
    if name == "snow":
        body += '<path d="m215 119 55-56 59 70-42-18-17 12-17-21ZM34 166l46-56 48 41-35-13-13 12-12-15Z" fill="#e1f4f7"/>'
    if name in ("autumn", "valley", "moor"):
        for x, y in [(40, 238), (100, 215), (555, 225), (600, 249)]:
            body += f'<path d="M{x} {y}v-45" stroke="{sky}" stroke-width="7"/><path d="m{x-22} {y-15} 22-62 22 62Z" fill="{far}"/>'
    if name == "beach":
        body += '<path d="M0 255Q150 210 280 261T640 248V320H0Z" fill="#6fc7c3"/><path d="M510 256q3-65 28-100m-2 4q-40-18-61 8 33-6 58 0m3-8q26-24 55 9-30-8-57-1" fill="none" stroke="#163f4e" stroke-width="9"/>'
    if name == "night":
        for i, x in enumerate(range(15, 640, 58)):
            y = 100 + (i * 37) % 95
            body += f'<rect x="{x}" y="{y}" width="38" height="{280-y}" fill="#19263f"/><path d="M{x} {y}h38v{280-y}" stroke="#67e4ed" stroke-width="2" fill="none"/>'
            for yy in range(y + 12, 250, 17):
                body += f'<path d="M{x+9} {yy}h6m8 0h6" stroke="#eb98d2" stroke-width="3"/>'
    if name == "volcano":
        body += '<path d="m210 220 100-142h45l108 156Z" fill="#302a3d"/><path d="m310 78 15 28-12 25 28 30-12 28 30 49" fill="none" stroke="#ff8150" stroke-width="9"/><path d="M308 78h48" stroke="#ffce86" stroke-width="6"/>'
    body += '<path d="M195 340c-40-80 220-75 179-121-16-18-59-21-65-42" fill="none" stroke="#e9ba92" stroke-width="48"/><path d="M195 340c-40-80 220-75 179-121-16-18-59-21-65-42" fill="none" stroke="#253248" stroke-width="39"/><path d="M195 340c-40-80 220-75 179-121-16-18-59-21-65-42" fill="none" stroke="#f4e1b8" stroke-width="2" stroke-dasharray="12 14"/>'
    svg(ART / f"landscapes/{name}.svg", body, 640, 320)

svg(ART / "menu_overlay.svg", '<defs><linearGradient id="shade"><stop stop-color="#080f1e" stop-opacity=".98"/><stop offset=".43" stop-color="#0b1424" stop-opacity=".9"/><stop offset=".75" stop-color="#0a1528" stop-opacity=".12"/></linearGradient><linearGradient id="bottom" x2="0" y2="1"><stop offset=".6" stop-color="#080f1e" stop-opacity="0"/><stop offset="1" stop-color="#080f1e" stop-opacity=".95"/></linearGradient></defs><rect width="1600" height="900" fill="url(#shade)"/><rect width="1600" height="900" fill="url(#bottom)"/><path d="M1250 0 760 900M1290 0 800 900" fill="none" stroke="#7cc9ea" stroke-opacity=".08" stroke-width="2"/><path d="m1370 0-135 250h22L1392 0Z" fill="#ff7946" opacity=".65"/><path d="M64 40h48m-48 0v14M1536 40h-48m48 0v14M64 842h48m-48 0v-14M1536 842h-48m48 0v-14" stroke="#9bb0cb" stroke-opacity=".35" fill="none"/>', 1600, 900)

svg(ROOT / "icon.svg", '<defs><linearGradient id="bg" x2="1" y2="1"><stop stop-color="#243853"/><stop offset="1" stop-color="#090f1e"/></linearGradient><linearGradient id="shell" x2=".8" y2="1"><stop stop-color="#ffc06a"/><stop offset=".6" stop-color="#ff7843"/><stop offset="1" stop-color="#d7442c"/></linearGradient></defs><rect x="8" y="8" width="240" height="240" rx="56" fill="url(#bg)" stroke="#4b6280" stroke-width="3"/><path d="m28 194 110-162h24L52 194Z" fill="#ff8750" opacity=".15"/><path d="M52 144c0-52 33-88 78-88s75 37 75 83v39H96l-44-23Z" fill="url(#shell)"/><path d="M128 103h74l8 36h-99Z" fill="#101d32" stroke="#ffd193" stroke-width="5"/><path d="m139 111-12 19h69l-4-19Z" fill="#69cddd"/><path d="M61 153h31l21 25M79 178h109" stroke="#ffb878" stroke-width="5" fill="none" stroke-linecap="round"/><path d="M171 193h16v16h-16m16 16h16v-16h-16m16-16h16v16h-16" fill="#f1f4ec"/><path d="M34 211h104" stroke="#ff8750" stroke-width="6" stroke-linecap="round"/>', 256, 256)
print(f"UI artwork generated in {ART}")
