"""
Codeplay in Kart -- preview renderer for the kart models.

Imports the exported .glb files from assets/models/karts/, assembles complete karts using
the socket empties (body + 4 wheels, left ones mirrored, spoiler, driver) and renders PNGs
with EEVEE, a 3-point light rig and a neutral ground.

Usage::

    blender --background --factory-startup --python tools/blender/render_previews.py -- <out_dir>
        [--mode kart|parts|all] [--only name ...] [--res 1200x900]

  --mode kart   assembled karts, 5 views each (default: all)
  --mode parts  each .glb on its own, 2 views each
  --only        restrict to names (body ids like vortex, or part file names)
  --combo       body:wheel:spoiler (repeatable) -> renders kart_<body>_<wheel>_<spoiler>_<view>.png
  --views       restrict kart views (front34 rear34 side top front cockpit)
"""

import bpy
import math
import os
import sys
from mathutils import Vector, Matrix

V = Vector
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
KART_DIR = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "..", "assets", "models", "karts"))

COMBOS = [
    ("vortex", "classic", "wing"),
    ("brutus", "offroad", "twin"),
    ("falcon", "turbine", "fin"),
    ("bolt", "retro", "duck"),
    ("mantis", "neon", "halo"),
    ("titan", "offroad", "wing"),
]

KART_VIEWS = {
    "front34": (V((1.0, 1.25, 0.55)), 1.0),
    "rear34": (V((-1.1, -1.2, 0.6)), 1.0),
    "side": (V((1.0, 0.0, 0.12)), 1.0),
    "top": (V((0.25, 0.15, 1.0)), 1.0),
    "front": (V((0.0, 1.0, 0.18)), 1.0),
    "cockpit": (V((0.55, -0.45, 0.75)), 0.55),
}
PART_VIEWS = {
    "a": (V((1.0, 0.9, 0.5)), 1.0),
    "b": (V((-0.9, -1.0, 0.45)), 1.0),
}


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out, mode, only, res = None, "all", [], (1200, 900)
    combos, views = [], []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--mode":
            mode = argv[i + 1]
            i += 2
        elif a in ("--only", "--combo", "--views"):
            dst = {"--only": only, "--combo": combos, "--views": views}[a]
            i += 1
            while i < len(argv) and not argv[i].startswith("--"):
                dst.append(argv[i])
                i += 1
        elif a == "--res":
            w, h = argv[i + 1].lower().split("x")
            res = (int(w), int(h))
            i += 2
        else:
            out = a
            i += 1
    if out is None:
        out = os.path.join(os.getcwd(), "renders")
    return out, mode, only, res, [tuple(c.split(":")) for c in combos], views


def reset_scene():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.lights, bpy.data.cameras):
        for d in list(coll):
            if d.users == 0:
                coll.remove(d)


def setup_render(res):
    sc = bpy.context.scene
    engines = [i.identifier for i in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
    eng = next((e for e in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE") if e in engines), "CYCLES")
    sc.render.engine = eng
    if eng == "CYCLES":
        sc.cycles.samples = 32
    else:
        ee = sc.eevee
        for attr, val in (("taa_render_samples", 48), ("use_raytracing", True), ("use_shadows", True),
                          ("use_gtao", True), ("shadow_ray_count", 2), ("shadow_step_count", 8)):
            try:
                setattr(ee, attr, val)
            except (AttributeError, TypeError):
                pass
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = "PNG"
    try:
        sc.view_settings.view_transform = "AgX"
        sc.view_settings.look = "AgX - Punchy"
    except TypeError:
        pass
    world = bpy.data.worlds.get("preview") or bpy.data.worlds.new("preview")
    sc.world = world
    if not world.node_tree:
        world.use_nodes = True
    bg = next(n for n in world.node_tree.nodes if n.type == "BACKGROUND")
    bg.inputs["Color"].default_value = (0.42, 0.47, 0.55, 1.0)
    bg.inputs["Strength"].default_value = 0.55


def add_light(name, kind, loc, target, energy, size=1.0, color=(1, 1, 1)):
    ld = bpy.data.lights.new(name, kind)
    ld.energy = energy
    ld.color = color
    if kind == "AREA":
        ld.size = size
    if kind == "SUN":
        ld.angle = math.radians(3)
    ob = bpy.data.objects.new(name, ld)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = V(loc)
    d = V(target) - V(loc)
    ob.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    return ob


def setup_stage():
    me = bpy.data.meshes.new("ground")
    s = 30
    me.from_pydata([(-s, -s, 0), (s, -s, 0), (s, s, 0), (-s, s, 0)], [], [(0, 1, 2, 3)])
    g = bpy.data.objects.new("ground", me)
    bpy.context.scene.collection.objects.link(g)
    m = bpy.data.materials.new("ground_mat")
    bsdf = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (0.16, 0.165, 0.175, 1)
    bsdf.inputs["Roughness"].default_value = 0.8
    me.materials.append(m)
    add_light("key", "SUN", (3, 2.5, 5), (0, 0, 0), 3.2, color=(1.0, 0.96, 0.9))
    add_light("fill", "AREA", (-3.5, 2.0, 1.8), (0, 0, 0.4), 450, size=4, color=(0.8, 0.88, 1.0))
    add_light("rim", "AREA", (-1.0, -4.0, 2.5), (0, 0, 0.5), 650, size=3)
    cam_data = bpy.data.cameras.new("cam")
    cam_data.lens = 50
    cam = bpy.data.objects.new("cam", cam_data)
    bpy.context.scene.collection.objects.link(cam)
    bpy.context.scene.camera = cam
    return cam


def import_glb(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    return [o for o in bpy.data.objects if o not in before]


def find(objs, prefix):
    for o in objs:
        if o.name == prefix or o.name.startswith(prefix + "."):
            return o
    return None


def place_part(path, matrix):
    objs = import_glb(path)
    roots = [o for o in objs if o.parent is None]
    for r in roots:
        r.matrix_world = matrix @ r.matrix_world
    return objs


def scene_bounds():
    mn = V((1e9, 1e9, 1e9))
    mx = V((-1e9, -1e9, -1e9))
    for o in bpy.context.scene.objects:
        if o.type != "MESH" or o.name == "ground":
            continue
        for c in o.bound_box:
            w = o.matrix_world @ V(c)
            mn = V((min(mn.x, w.x), min(mn.y, w.y), min(mn.z, w.z)))
            mx = V((max(mx.x, w.x), max(mx.y, w.y), max(mx.z, w.z)))
    return mn, mx


def aim_camera(cam, direction, zoom=1.0, target=None):
    mn, mx = scene_bounds()
    center = (mn + mx) / 2 if target is None else V(target)
    radius = (mx - mn).length / 2
    fov = cam.data.angle
    dist = radius / math.tan(fov / 2) * 1.05 * zoom
    d = direction.normalized()
    cam.location = center + d * dist
    cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    cam.data.clip_start = 0.01
    cam.data.clip_end = 100


def render(path):
    bpy.context.scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    print("[render_previews] wrote", path)


def assemble_kart(body, wheel, spoiler):
    body_objs = import_glb(os.path.join(KART_DIR, "body_%s.glb" % body))
    bpy.context.view_layer.update()
    sockets = {}
    for key in ("socket_wheel_fl", "socket_wheel_fr", "socket_wheel_rl", "socket_wheel_rr",
                "socket_spoiler", "socket_driver"):
        o = find(body_objs, key)
        if o is None:
            print("[render_previews] MISSING", key, "in", body)
            continue
        sockets[key] = o.matrix_world.copy()
    wpath = os.path.join(KART_DIR, "wheel_%s.glb" % wheel)
    for key, mirror in (("socket_wheel_fl", True), ("socket_wheel_fr", False),
                        ("socket_wheel_rl", True), ("socket_wheel_rr", False)):
        if key not in sockets:
            continue
        m = sockets[key]
        if mirror:
            m = m @ Matrix.Diagonal((-1, 1, 1, 1))
        place_part(wpath, m)
    spath = os.path.join(KART_DIR, "spoiler_%s.glb" % spoiler)
    if "socket_spoiler" in sockets and os.path.exists(spath):
        place_part(spath, sockets["socket_spoiler"])
    dpath = os.path.join(KART_DIR, "driver.glb")
    if "socket_driver" in sockets and os.path.exists(dpath):
        place_part(dpath, sockets["socket_driver"])


def main():
    out, mode, only, res, combos, views = parse_args()
    os.makedirs(out, exist_ok=True)
    setup_render(res)
    if mode in ("kart", "all"):
        for body, wheel, spoiler in (combos or COMBOS):
            if only and body not in only:
                continue
            reset_scene()
            cam = setup_stage()
            assemble_kart(body, wheel, spoiler)
            for view, (d, zoom) in KART_VIEWS.items():
                if views and view not in views:
                    continue
                tgt = None
                if view == "cockpit":
                    tgt = (0, 0.0, 0.5)
                aim_camera(cam, d, zoom, tgt)
                name = "%s_%s_%s" % (body, wheel, spoiler) if combos else body
                render(os.path.join(out, "kart_%s_%s.png" % (name, view)))
    if mode in ("parts", "all"):
        files = sorted(f for f in os.listdir(KART_DIR) if f.endswith(".glb"))
        for f in files:
            name = f[:-4]
            if only and name not in only:
                continue
            reset_scene()
            cam = setup_stage()
            objs = import_glb(os.path.join(KART_DIR, f))
            mn, mx = scene_bounds()
            if mn.z < -1e-3:
                for o in objs:
                    if o.parent is None:
                        o.location.z -= mn.z
                bpy.context.view_layer.update()
            for view, (d, zoom) in PART_VIEWS.items():
                aim_camera(cam, d, zoom)
                render(os.path.join(out, "part_%s_%s.png" % (name, view)))


if __name__ == "__main__":
    main()
