"""
Codeplay in Kart -- preview renders of the exported props.

Re-imports every ``assets/models/props/*.glb`` (so it also checks the exported files) and
renders each one on a grass plane under golden-hour light, plus a "lineup" scene with
everything placed around the start arch.

Usage::

    blender --background --factory-startup --python tools/blender/render_props_preview.py -- --out <dir> [names...] [--no-lineup] [--size 900]
        [--src <dir with .glb>] [--night] [--ground #rrggbb] [--az -35] [--el 16]

``--night`` renders under a dark blue sky with a dim moon light (to judge emissive materials).
"""

import math
import os
import sys

import bpy
from mathutils import Vector

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
SRC_DIR = os.path.join(PROJECT_ROOT, "assets", "models", "props")


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    opts = {"out": os.path.join(bpy.app.tempdir or "/tmp", "props_previews"), "names": [],
            "lineup": True, "size": 900, "only_lineup": False, "src": SRC_DIR, "night": False,
            "ground": None, "az": -35.0, "el": 16.0}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--out":
            opts["out"] = os.path.abspath(argv[i + 1]); i += 2; continue
        if a == "--size":
            opts["size"] = int(argv[i + 1]); i += 2; continue
        if a == "--src":
            opts["src"] = os.path.abspath(argv[i + 1]); i += 2; continue
        if a == "--ground":
            opts["ground"] = argv[i + 1]; i += 2; continue
        if a in ("--az", "--el"):
            opts[a[2:]] = float(argv[i + 1]); i += 2; continue
        if a == "--night":
            opts["night"] = True; i += 1; continue
        if a == "--no-lineup":
            opts["lineup"] = False
        elif a == "--only-lineup":
            opts["only_lineup"] = True
        else:
            opts["names"].append(a)
        i += 1
    return opts


def srgb(h):
    h = h.lstrip("#")
    out = []
    for i in (0, 2, 4):
        c = int(h[i:i + 2], 16) / 255.0
        out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return tuple(out)


def reset():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.lights, bpy.data.cameras):
        for b in list(coll):
            coll.remove(b)


def setup_render(width, height):
    scene = bpy.context.scene
    engines = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
    for eng in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "CYCLES"):
        if eng in engines:
            scene.render.engine = eng
            break
    if scene.render.engine == "CYCLES":
        scene.cycles.samples = 48
    else:
        ee = scene.eevee
        for attr, val in (("taa_render_samples", 64), ("use_raytracing", True),
                          ("use_shadows", True), ("shadow_ray_count", 2), ("shadow_step_count", 8),
                          ("use_gtao", True), ("fast_gi_distance", 3.0)):
            try:
                setattr(ee, attr, val)
            except (AttributeError, TypeError):
                pass
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    # "Standard" keeps albedo colours close to what a game engine shows (AgX desaturates)
    try:
        scene.view_settings.view_transform = "Standard"
        scene.view_settings.exposure = -0.2
    except TypeError:
        pass


def setup_world_and_lights(night=False, ground="#6f9643"):
    world = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    nt = world.node_tree
    bg = next(n for n in nt.nodes if n.type == "BACKGROUND")
    bg.inputs[0].default_value = (*srgb("#1a2240" if night else "#8fb0dc"), 1.0)
    bg.inputs[1].default_value = 0.35 if night else 0.55

    sun_data = bpy.data.lights.new("sun", "SUN")
    sun_data.energy = 0.35 if night else 3.6
    sun_data.color = (0.6, 0.7, 1.0) if night else (1.0, 0.82, 0.62)
    sun_data.angle = math.radians(2.5)
    sun = bpy.data.objects.new("sun", sun_data)
    sun_dir = Vector((-0.42, 0.85, -0.62)).normalized()
    sun.rotation_euler = sun_dir.to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.collection.objects.link(sun)

    ground_mat = bpy.data.materials.new("ground")
    bsdf = next(n for n in ground_mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (*srgb(ground), 1.0)
    bsdf.inputs["Roughness"].default_value = 0.95
    bpy.ops.mesh.primitive_plane_add(size=400, location=(0, 0, 0))
    ground = bpy.context.active_object
    ground.data.materials.append(ground_mat)


def wire_vertex_colors(objs):
    """Make sure imported vertex colours drive Base Color (importer versions differ)."""
    for o in objs:
        if o.type != "MESH" or not o.data.color_attributes:
            continue
        layer = o.data.color_attributes[0].name
        for slot in o.material_slots:
            mat = slot.material
            if mat is None:
                continue
            mat.use_backface_culling = True
            nt = mat.node_tree
            if any(n.type == "VERTEX_COLOR" for n in nt.nodes):
                continue
            bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
            if bsdf is None or bsdf.inputs["Base Color"].is_linked:
                continue
            vc = nt.nodes.new("ShaderNodeVertexColor")
            vc.layer_name = layer
            nt.links.new(vc.outputs["Color"], bsdf.inputs["Base Color"])


def import_glb(path, location=(0, 0, 0), rot_z=0.0):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    roots = [o for o in new if o.parent is None]
    for r in roots:
        r.location = Vector(location) + r.location
        r.rotation_mode = "XYZ"
        r.rotation_euler.z += rot_z
    for o in new:
        if o.type == "MESH":
            for slot in o.material_slots:
                if slot.material:
                    slot.material.use_backface_culling = True
    wire_vertex_colors(new)
    return new


def world_bbox(objs):
    pts = []
    bpy.context.view_layer.update()
    for o in objs:
        if o.type == "MESH":
            pts += [o.matrix_world @ Vector(c) for c in o.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return lo, hi


def add_camera(location, target, lens=50.0):
    cam_data = bpy.data.cameras.new("cam")
    cam_data.lens = lens
    cam = bpy.data.objects.new("cam", cam_data)
    bpy.context.scene.collection.objects.link(cam)
    cam.location = location
    d = Vector(target) - Vector(location)
    cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.camera = cam
    cam_data.clip_end = 1000
    return cam


def frame_camera(objs, azimuth_deg=-35.0, elevation_deg=16.0, lens=50.0, margin=1.12):
    lo, hi = world_bbox(objs)
    center = (lo + hi) * 0.5
    radius = (hi - lo).length * 0.5
    fov = 2 * math.atan(18.0 / lens)
    dist = radius / math.sin(fov / 2) * margin
    az, el = math.radians(azimuth_deg), math.radians(elevation_deg)
    direction = Vector((math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el)))
    add_camera(center + direction * dist, center, lens)


def render(path):
    bpy.context.scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    print("rendered", path)


LINEUP = [
    ("start_arch", (0, 4, 0), 0),
    ("grandstand", (17.5, 10, 0), -math.pi / 2),
    ("tree_pine", (-15, 14, 0), 0), ("tree_pine", (-21, 22, 0), 1.3), ("tree_pine", (-12.5, 26, 0), 2.1),
    ("tree_round", (-17, 3, 0), 0.4), ("tree_round", (-26, 11, 0), 2.0),
    ("bush", (-11.5, -2, 0), 0), ("bush", (-13, 7, 0), 1.0), ("bush", (11.5, -3.5, 0), 2.0),
    ("rock_a", (-13.5, -8, 0), 0.5), ("rock_b", (-18, -3, 0), 0.0), ("rock_c", (12.5, -9, 0), 0.8),
    ("tire_stack", (9.4, -4.2, 0), 0), ("tire_stack", (10.0, -4.2, 0), 0.5), ("tire_stack", (9.7, -3.7, 0), 1),
    ("tire_stack", (-9.4, -4.2, 0), 0), ("tire_stack", (-10.0, -4.2, 0), 0.5),
    ("traffic_cone", (-3, -7, 0), 0), ("traffic_cone", (-1, -7.3, 0), 0), ("traffic_cone", (1, -7.3, 0), 0),
    ("traffic_cone", (3, -7, 0), 0),
    ("flag_pole", (-10.8, -1.5, 0), 0.3), ("flag_pole", (10.8, -1.5, 0), 0.3),
]


def main():
    opts = parse_args()
    os.makedirs(opts["out"], exist_ok=True)
    src = opts["src"]
    names = opts["names"] or sorted(f[:-4] for f in os.listdir(src) if f.endswith(".glb"))
    ground = opts["ground"] or ("#2a2c33" if opts["night"] else "#6f9643")
    if not opts["only_lineup"]:
        for name in names:
            reset()
            setup_render(opts["size"], opts["size"])
            setup_world_and_lights(opts["night"], ground)
            objs = import_glb(os.path.join(src, name + ".glb"))
            frame_camera(objs, opts["az"], opts["el"])
            render(os.path.join(opts["out"], name + ".png"))
    if opts["lineup"]:
        reset()
        setup_render(1600, 900)
        setup_world_and_lights()
        for name, loc, rot in LINEUP:
            import_glb(os.path.join(SRC_DIR, name + ".glb"), loc, rot)
        for k in range(10):
            import_glb(os.path.join(SRC_DIR, "fence_segment.glb"), (-9.8, -14 + k * 4, 0), math.pi / 2)
        add_camera((-5.5, -30, 6.0), (0.5, 4, 4.0), lens=32)
        render(os.path.join(opts["out"], "lineup.png"))


if __name__ == "__main__":
    main()
