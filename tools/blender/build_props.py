"""
Codeplay in Kart -- procedural environment / track props
=========================================================

Builds every prop used by the first track, "Vale do Por do Sol" (Sunset Valley),
fully procedurally (bmesh + metaballs + a little noise) and exports each one to
``assets/models/props/<name>.glb``.  A second group of themed props (desert / canyon cacti
and mesa, beach palm and umbrella set, snowy pine, snowman and crystals, autumn pumpkins,
dead tree, lava rock, night-city street lamp / neon billboard / building, fern and grass
ground cover) lives in the "Themed props" section and is registered in the same ``PROPS``.

Usage (from the project root)::

    blender --background --factory-startup --python tools/blender/build_props.py
    # build only some props / custom output dir:
    blender -b --factory-startup --python tools/blender/build_props.py -- tree_pine rock_a --out /tmp/props

Conventions (see docs/ASSET_CONTRACT.md):
  * Blender Z-up, metres, real-world scale. The glTF exporter converts to Y-up.
  * Every prop is ONE mesh object whose origin is the centre of its base, on the ground (Z = 0).
  * Materials use only scalar Principled BSDF values. Organic props (trees, bush, rocks) also
    carry a vertex colour layer (COLOR_0 in glTF); their materials have a *white* base colour
    so that the engine multiplies albedo x vertex colour correctly.
  * Things that "face" somewhere (grandstand, banners) face -Y; roads run along Y.

How to add a new prop:
  1. write ``def build_<name>() -> bpy.types.Object`` using the helpers below
     (``Part`` + ``lathe`` / ``sweep`` / ``tube`` / ``box`` / ``extrude_x`` / ``sheet`` ...),
  2. register it in ``PROPS`` at the bottom with a triangle budget and the vertex-colour flag.

Everything is seeded, so the output is reproducible run after run.
"""

import math
import os
import random
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector, noise
from mathutils.bvhtree import BVHTree

TAU = math.tau


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
DEFAULT_OUT_DIR = os.path.join(PROJECT_ROOT, "assets", "models", "props")


def parse_args():
    """Arguments after ``--``: optional prop names and ``--out <dir>``."""
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    names, out_dir = [], DEFAULT_OUT_DIR
    i = 0
    while i < len(argv):
        if argv[i] == "--out" and i + 1 < len(argv):
            out_dir = os.path.abspath(argv[i + 1])
            i += 2
            continue
        names.append(argv[i])
        i += 1
    return names, out_dir


def clamp01(x):
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


def smoothstep(e0, e1, x):
    t = clamp01((x - e0) / (e1 - e0))
    return t * t * (3.0 - 2.0 * t)


def lerp(a, b, t):
    return a + (b - a) * t


def srgb_to_linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def hexcol(h):
    """'#rrggbb' (sRGB, as picked in any colour picker) -> linear RGB tuple."""
    h = h.lstrip("#")
    return tuple(srgb_to_linear(int(h[i:i + 2], 16) / 255.0) for i in (0, 2, 4))


def mix(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def scale_col(c, k):
    return tuple(x * k for x in c)


def ramp(stops, t):
    """Piecewise-linear colour ramp. ``stops`` = [(position, colour), ...] sorted by position."""
    t = clamp01(t)
    for (p0, c0), (p1, c1) in zip(stops, stops[1:]):
        if t <= p1:
            return mix(c0, c1, (t - p0) / max(p1 - p0, 1e-6))
    return stops[-1][1]


def nz(p, scale=1.0, seed=0.0):
    """Perlin noise in [-1, 1] at point ``p`` (seed shifts the sample space)."""
    return noise.noise(Vector(p) * scale + Vector((seed * 17.31, seed * 5.77, seed * 11.13)))


# Scalar Principled BSDF values only (procedural textures do not survive glTF export).
# Colours are authored in sRGB hex.  For vertex-coloured props the base colour is forced to
# white and a "Color Attribute" node feeds Base Color (that is what the glTF exporter
# recognises to emit COLOR_0).

MATERIALS = {
    "bark":         dict(color="#6e4a32", roughness=0.92),
    "leaves":       dict(color="#4f8f3a", roughness=0.78),
    "leaves_dark":  dict(color="#2c6644", roughness=0.80),
    "flowers":      dict(color="#ffd0dc", roughness=0.60),
    "rock":         dict(color="#a39586", roughness=0.86),
    "moss":         dict(color="#6f9a3c", roughness=0.90),
    "rubber":       dict(color="#1d1d21", roughness=0.86),
    "paint_white":  dict(color="#f1efe9", roughness=0.42),
    "paint_red":    dict(color="#d9261f", roughness=0.38),
    "paint_orange": dict(color="#ff6512", roughness=0.42),
    "paint_yellow": dict(color="#ffc01c", roughness=0.40),
    "paint_black":  dict(color="#18191d", roughness=0.45),
    "metal":        dict(color="#c5cad1", roughness=0.30, metallic=0.9),
    "metal_dark":   dict(color="#34373e", roughness=0.42, metallic=0.75),
    "wood":         dict(color="#b07a46", roughness=0.80),
    "wood_dark":    dict(color="#7a4e2e", roughness=0.85),
    "concrete":     dict(color="#bdb5a8", roughness=0.92),
    "seat":         dict(color="#1d72c8", roughness=0.40),
    "seat_alt":     dict(color="#ffb21e", roughness=0.40),
    "banner":       dict(color="#1f5fbf", roughness=0.55),
    "flag":         dict(color="#ff5a1f", roughness=0.70),
    "start_light":  dict(color="#ff2a18", roughness=0.20, emission="#ff2a18", emission_strength=6.0),
    "snow":         dict(color="#eef3fa", roughness=0.75),
    "sandstone":    dict(color="#c8743f", roughness=0.92),
    "cactus":       dict(color="#3f7f3a", roughness=0.70),
    "sand":         dict(color="#e2c48e", roughness=0.95),
    "grass":        dict(color="#5f9a3a", roughness=0.85),
    "leaf_litter":  dict(color="#d0622a", roughness=0.80),
    "pumpkin":      dict(color="#f0791c", roughness=0.55),
    "hay":          dict(color="#d8b45c", roughness=0.95),
    "fabric_a":     dict(color="#f0453a", roughness=0.85),
    "fabric_b":     dict(color="#fbf3e2", roughness=0.85),
    "glass":        dict(color="#1b2640", roughness=0.12, metallic=0.3),
    "lava":         dict(color="#ff6a1a", roughness=0.55, emission="#ff5a0f", emission_strength=4.0),
    "crystal":      dict(color="#8fe6ff", roughness=0.08, emission="#3fd2ff", emission_strength=0.6),
    "lamp_light":   dict(color="#fff4e2", roughness=0.30, emission="#ffe3b8", emission_strength=8.0),
    "neon":         dict(color="#ff3fd8", roughness=0.25, emission="#ff22cc", emission_strength=6.0),
    "neon_alt":     dict(color="#3ff4ff", roughness=0.25, emission="#22e6ff", emission_strength=6.0),
    "window_light": dict(color="#ffd99a", roughness=0.35, emission="#ffc875", emission_strength=3.0),
}


class BuildState:
    """Per-prop build settings (set by ``main`` before each builder runs)."""
    vertex_colors = False


VC_LAYER = "Col"


def _socket(node, *names):
    for s in node.inputs:
        if s.identifier in names or s.name in names:
            return s
    return None


def material(name):
    """Return (creating on first use) the material ``name`` from ``MATERIALS``."""
    mat = bpy.data.materials.get(name)
    if mat:
        return mat
    spec = MATERIALS[name]
    mat = bpy.data.materials.new(name)
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    col = hexcol(spec["color"])
    use_vc = BuildState.vertex_colors
    base = (1.0, 1.0, 1.0) if use_vc else col
    _socket(bsdf, "Base Color").default_value = (*base, 1.0)
    _socket(bsdf, "Roughness").default_value = spec.get("roughness", 0.5)
    _socket(bsdf, "Metallic").default_value = spec.get("metallic", 0.0)
    if "emission" in spec:
        _socket(bsdf, "Emission Color", "Emission").default_value = (*hexcol(spec["emission"]), 1.0)
        _socket(bsdf, "Emission Strength").default_value = spec.get("emission_strength", 1.0)
    if use_vc:
        attr = nt.nodes.new("ShaderNodeVertexColor")
        attr.layer_name = VC_LAYER
        attr.location = (bsdf.location.x - 300, bsdf.location.y)
        nt.links.new(attr.outputs["Color"], _socket(bsdf, "Base Color"))
    mat.diffuse_color = (*col, 1.0)
    # all prop geometry is closed (thin things like flags are solidified), so export
    # single-sided materials (glTF doubleSided = false) -> cheaper and no z-fighting backfaces
    mat.use_backface_culling = True
    return mat


def reset_scene():
    """Delete every object and orphan data block so each prop starts from scratch."""
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.metaballs, bpy.data.curves):
        for block in list(coll):
            coll.remove(block)


def link(obj):
    bpy.context.scene.collection.objects.link(obj)
    return obj


def apply_modifiers(obj):
    """Bake the evaluated mesh (modifiers / metaball tessellation) into a plain mesh object."""
    dg = bpy.context.evaluated_depsgraph_get()
    dg.update()
    me = bpy.data.meshes.new_from_object(obj.evaluated_get(dg))
    if obj.type == "MESH":
        old = obj.data
        obj.modifiers.clear()
        obj.data = me
        bpy.data.meshes.remove(old)
        return obj
    new = link(bpy.data.objects.new(obj.name + "_mesh", me))
    new.matrix_world = obj.matrix_world.copy()
    bpy.data.objects.remove(obj, do_unlink=True)
    return new


def join_objects(objs, name):
    """Join objects into a single mesh object called ``name`` (materials are merged)."""
    objs = [o for o in objs if o is not None]
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    if len(objs) > 1:
        bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    obj.name = name
    obj.data.name = name
    return obj


def tri_count(obj):
    return sum(len(p.vertices) - 2 for p in obj.data.polygons)


def bbox(obj):
    xs = [v.co.x for v in obj.data.vertices]
    ys = [v.co.y for v in obj.data.vertices]
    zs = [v.co.z for v in obj.data.vertices]
    return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


class Part:
    """Accumulates geometry (with per-face material indices) into one bmesh.

    ``recalc_normals`` should only be used for parts made exclusively of closed solids;
    open surfaces (decals, flags) are built with correct winding instead.
    """

    def __init__(self, name, recalc_normals=False):
        self.name = name
        self.bm = bmesh.new()
        self.mat_names = []
        self.recalc_normals = recalc_normals
        self._uv = None

    def mi(self, mat_name):
        """Material slot index for ``mat_name`` (added on first use)."""
        if mat_name not in self.mat_names:
            self.mat_names.append(mat_name)
        return self.mat_names.index(mat_name)

    @property
    def uv(self):
        if self._uv is None:
            self._uv = self.bm.loops.layers.uv.new("UVMap")
        return self._uv

    def merge(self, other_bm):
        """Append another bmesh (its material indices must already refer to this part)."""
        tmp = bpy.data.meshes.new("_merge_tmp")
        other_bm.to_mesh(tmp)
        other_bm.free()
        self.bm.from_mesh(tmp)
        bpy.data.meshes.remove(tmp)

    def finish(self, smooth=None):
        """Create the object.  smooth: None = fully smooth, 'flat', or an angle in degrees."""
        bm = self.bm
        if self.recalc_normals:
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.normal_update()
        for f in bm.faces:
            f.smooth = smooth != "flat"
        if isinstance(smooth, (int, float)):
            limit = math.radians(smooth)
            for e in bm.edges:
                if e.is_manifold and e.calc_face_angle(0.0) > limit:
                    e.smooth = False
        me = bpy.data.meshes.new(self.name)
        bm.to_mesh(me)
        bm.free()
        for m in self.mat_names:
            me.materials.append(material(m))
        return link(bpy.data.objects.new(self.name, me))


def lathe(part, profile, segments, mat=None, mats=None, closed=False, radial_fn=None,
          matrix=None, phase=0.0):
    """Revolve a (r, z) profile around +Z.

    * Walk the profile so that the *outside* of the surface is on the right-hand side
      (e.g. bottom -> top along an outer wall); faces then point outwards.
    * Points with r == 0 become a single pole vertex.
    * ``mats``: one material name per profile edge (overrides ``mat``).
    * ``radial_fn(theta, i, r, z) -> (r, z)`` deforms each ring vertex (lobes, droop, flare).
    """
    bm = part.bm
    M = matrix or Matrix.Identity(4)
    rings = []
    for i, (r, z) in enumerate(profile):
        if r < 1e-6:
            rings.append([bm.verts.new(M @ Vector((0.0, 0.0, z)))])
            continue
        ring = []
        for j in range(segments):
            th = phase + TAU * j / segments
            rr, zz = radial_fn(th, i, r, z) if radial_fn else (r, z)
            ring.append(bm.verts.new(M @ Vector((rr * math.cos(th), rr * math.sin(th), zz))))
        rings.append(ring)
    n_edges = len(profile) if closed else len(profile) - 1
    for i in range(n_edges):
        a, b = rings[i], rings[(i + 1) % len(rings)]
        idx = part.mi(mats[i] if mats else mat)
        if len(a) == 1 and len(b) == 1:
            continue
        for j in range(segments):
            j2 = (j + 1) % segments
            if len(a) == 1:
                vs = (a[0], b[j2], b[j])
            elif len(b) == 1:
                vs = (a[j], a[j2], b[0])
            else:
                vs = (a[j], a[j2], b[j2], b[j])
            bm.faces.new(vs).material_index = idx
    return rings


def _frames(path, up_hint=None):
    """Parallel-transport frames (tangent, normal, binormal) along a polyline."""
    n_pts = len(path)
    tangents = []
    for i in range(n_pts):
        a = path[max(i - 1, 0)]
        b = path[min(i + 1, n_pts - 1)]
        tangents.append((b - a).normalized())
    t0 = tangents[0]
    hint = up_hint or (Vector((0, 0, 1)) if abs(t0.z) < 0.9 else Vector((1, 0, 0)))
    n = (hint - t0 * hint.dot(t0)).normalized()
    frames = []
    for i, t in enumerate(tangents):
        if i > 0:
            q = tangents[i - 1].rotation_difference(t)
            n = q @ n
            n = (n - t * n.dot(t)).normalized()
        frames.append((t, n, t.cross(n)))
    return frames


def sweep(part, path, radii, sides, mat, cap_start=False, cap_end=False, up_hint=None,
          radial_fn=None, squash=(1.0, 1.0), phase=0.0):
    """Sweep a circle (``sides`` vertices) along ``path`` with per-point ``radii``.

    ``squash`` scales the cross-section along (normal, binormal) -> elliptical tubes.
    ``radial_fn(theta, i, r) -> r`` lets callers sculpt the section (root flares...).
    """
    bm = part.bm
    path = [Vector(p) for p in path]
    idx = part.mi(mat)
    rings = []
    for i, ((t, n, b), p) in enumerate(zip(_frames(path, up_hint), path)):
        ring = []
        for j in range(sides):
            th = phase + TAU * j / sides
            r = radii[i]
            if radial_fn:
                r = radial_fn(th, i, r)
            off = n * (math.cos(th) * r * squash[0]) + b * (math.sin(th) * r * squash[1])
            ring.append(bm.verts.new(p + off))
        rings.append(ring)
    for a, b in zip(rings, rings[1:]):
        for j in range(sides):
            j2 = (j + 1) % sides
            bm.faces.new((a[j], a[j2], b[j2], b[j])).material_index = idx
    if cap_start:
        bm.faces.new(list(reversed(rings[0]))).material_index = idx
    if cap_end:
        bm.faces.new(rings[-1]).material_index = idx
    return rings


def tube(part, p0, p1, r, sides, mat, caps=False, up_hint=None):
    return sweep(part, [p0, p1], [r, r], sides, mat, caps, caps, up_hint=up_hint)


def box(part, center, size, mat, bevel=0.0, segments=2, matrix=None, profile=0.5):
    """Axis-aligned box (optionally rounded with a bevel), then optionally transformed."""
    bm = bmesh.new()
    res = bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=Vector(size), verts=res["verts"])
    if bevel > 0.0:
        bmesh.ops.bevel(bm, geom=list(bm.edges), offset=bevel, offset_type="OFFSET",
                        profile_type="SUPERELLIPSE", segments=segments, profile=profile,
                        affect="EDGES", clamp_overlap=True)
    M = Matrix.Translation(Vector(center)) @ (matrix or Matrix.Identity(4))
    bmesh.ops.transform(bm, matrix=M, verts=bm.verts)
    idx = part.mi(mat)
    for f in bm.faces:
        f.material_index = idx
    part.merge(bm)


def quad(part, pts, mat, uvs=None, facing=None):
    """One face from points.  ``facing``: flip the winding if the normal opposes this vector."""
    bm = part.bm
    pts = [Vector(p) for p in pts]
    if facing is not None:
        nrm = (pts[1] - pts[0]).cross(pts[-1] - pts[0])
        if nrm.dot(Vector(facing)) < 0:
            pts.reverse()
            if uvs:
                uvs = list(reversed(uvs))
    f = bm.faces.new([bm.verts.new(p) for p in pts])
    f.material_index = part.mi(mat)
    if uvs:
        layer = part.uv
        for loop, uv in zip(f.loops, uvs):
            loop[layer].uv = uv
    return f


def extrude_x(part, pts_yz, x0, x1, mat):
    """Closed prism: polygon in the YZ plane extruded from x0 to x1 (use recalc_normals)."""
    bm = part.bm
    idx = part.mi(mat)
    a = [bm.verts.new((x0, y, z)) for y, z in pts_yz]
    b = [bm.verts.new((x1, y, z)) for y, z in pts_yz]
    faces = [bm.faces.new(a), bm.faces.new(list(reversed(b)))]
    n = len(pts_yz)
    for i in range(n):
        i2 = (i + 1) % n
        faces.append(bm.faces.new((a[i], b[i], b[i2], a[i2])))
    for f in faces:
        f.material_index = idx
    return faces


def sheet(part, grid, thickness, mat, rim_mat=None):
    """Thin double-sided sheet (flags, pennants) from a grid of points ``grid[row][col]``.

    The front side faces (d col) x (d row); it gets UVs 0..1, the back side gets mirrored
    UVs so a texture reads correctly from both sides.  Edges are closed with a rim.
    """
    bm = part.bm
    rows, cols = len(grid), len(grid[0])
    uv = part.uv
    idx = part.mi(mat)
    ridx = part.mi(rim_mat or mat)

    def normal_at(r, c):
        du = grid[r][min(c + 1, cols - 1)] - grid[r][max(c - 1, 0)]
        dv = grid[min(r + 1, rows - 1)][c] - grid[max(r - 1, 0)][c]
        return du.cross(dv).normalized()

    front = [[None] * cols for _ in range(rows)]
    back = [[None] * cols for _ in range(rows)]
    for r in range(rows):
        for c in range(cols):
            n = normal_at(r, c) * (thickness * 0.5)
            front[r][c] = bm.verts.new(grid[r][c] + n)
            back[r][c] = bm.verts.new(grid[r][c] - n)

    def uvf(r, c, mirror):
        u = c / (cols - 1)
        return ((1.0 - u) if mirror else u, r / (rows - 1))

    for r in range(rows - 1):
        for c in range(cols - 1):
            cells = [(r, c), (r, c + 1), (r + 1, c + 1), (r + 1, c)]
            f = bm.faces.new([front[i][j] for i, j in cells])
            f.material_index = idx
            for loop, (i, j) in zip(f.loops, cells):
                loop[uv].uv = uvf(i, j, False)
            cells.reverse()
            f = bm.faces.new([back[i][j] for i, j in cells])
            f.material_index = idx
            for loop, (i, j) in zip(f.loops, cells):
                loop[uv].uv = uvf(i, j, True)
    boundary = ([((0, c), (0, c + 1)) for c in range(cols - 1)] +
                [((r, cols - 1), (r + 1, cols - 1)) for r in range(rows - 1)] +
                [((rows - 1, c + 1), (rows - 1, c)) for c in range(cols - 1)] +
                [((r + 1, 0), (r, 0)) for r in range(rows - 1)])
    for (ra, ca), (rb, cb) in boundary:
        f = bm.faces.new((front[rb][cb], front[ra][ca], back[ra][ca], back[rb][cb]))
        f.material_index = ridx


def displace(bm, amount, scale, seed=0.0, verts=None, weight_fn=None):
    """Push vertices along their normals by Perlin noise (organic irregularity)."""
    bm.normal_update()
    verts = list(verts if verts is not None else bm.verts)
    offsets = []
    for v in verts:
        w = weight_fn(v.co) if weight_fn else 1.0
        offsets.append(v.normal * (nz(v.co, scale, seed) * amount * w))
    for v, o in zip(verts, offsets):
        v.co += o


def metaball_mesh(name, balls, resolution, threshold=0.6, stiffness=2.0):
    """Tessellate a set of metaballs [(center, radius), ...] into a mesh object.

    Blender's field is ``stiffness * (1 - d^2/R^2)^3``; a low threshold/stiffness ratio keeps
    each ball close to its full radius with only a small fillet where balls meet, which gives
    distinct "puffs" instead of one soft blob.  See ``puff_radius``.
    """
    mb = bpy.data.metaballs.new(name)
    mb.resolution = resolution
    mb.render_resolution = resolution
    mb.threshold = threshold
    obj = link(bpy.data.objects.new(name, mb))
    for co, radius in balls:
        e = mb.elements.new()
        e.co = co
        e.radius = radius
        e.stiffness = stiffness
    obj = apply_modifiers(obj)
    bpy.data.metaballs.remove(mb)
    return obj


def decimate_to(obj, target_tris):
    tris = tri_count(obj)
    if tris > target_tris:
        mod = obj.modifiers.new("decimate", "DECIMATE")
        mod.ratio = target_tris / tris
        apply_modifiers(obj)
    return obj


def edit_mesh(obj, fn):
    """Run ``fn(bm)`` on an object's mesh data."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    fn(bm)
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()


def set_smooth(obj, smooth=None):
    def _apply(bm):
        bm.normal_update()
        for f in bm.faces:
            f.smooth = True
        if smooth is not None:
            limit = math.radians(smooth)
            for e in bm.edges:
                e.smooth = not (e.is_manifold and e.calc_face_angle(0.0) > limit)
    edit_mesh(obj, _apply)


def _hemisphere_dirs(n):
    """Cosine-weighted hemisphere directions around +Z (deterministic Fibonacci spiral)."""
    dirs = []
    golden = math.pi * (3.0 - math.sqrt(5.0))
    for i in range(n):
        r = math.sqrt((i + 0.5) / n)
        a = i * golden
        dirs.append(Vector((r * math.cos(a), r * math.sin(a), math.sqrt(max(0.0, 1.0 - r * r)))))
    return dirs


def bake_ao(obj, samples=24, max_dist=2.0, ground=True):
    """Per-vertex ambient occlusion (1 = open sky, 0 = fully occluded) by ray casting.

    The ground plane (z = 0) also occludes, which grounds trees and rocks nicely.
    """
    me = obj.data
    verts = [v.co.copy() for v in me.vertices]
    bvh = BVHTree.FromPolygons(verts, [tuple(p.vertices) for p in me.polygons])
    dirs = _hemisphere_dirs(samples)
    ao = []
    for v in me.vertices:
        n = v.normal
        rot = n.to_track_quat("Z", "Y")
        origin = v.co + n * 0.01
        hits = 0.0
        for d in dirs:
            rd = rot @ d
            loc, _, _, dist = bvh.ray_cast(origin, rd, max_dist)
            if loc is not None:
                hits += 1.0 - 0.5 * (dist / max_dist)
            elif ground and rd.z < -1e-4 and origin.z > -0.05:
                t = (origin.z + 0.02) / -rd.z
                if t < max_dist:
                    hits += 1.0 - 0.5 * (t / max_dist)
        ao.append(clamp01(1.0 - hits / samples))
    return ao


class Sample:
    """What a colour function gets for every face corner."""
    __slots__ = ("co", "normal", "face_normal", "mat", "ao", "index", "face_center")


def paint(obj, color_fn, ao=None):
    """Write a CORNER-domain float colour layer computed by ``color_fn(Sample)``."""
    me = obj.data
    if VC_LAYER in me.color_attributes:
        me.color_attributes.remove(me.color_attributes[VC_LAYER])
    attr = me.color_attributes.new(VC_LAYER, "FLOAT_COLOR", "CORNER")
    mats = [m.name for m in me.materials]
    s = Sample()
    for poly in me.polygons:
        s.mat = mats[poly.material_index]
        s.face_normal = poly.normal
        s.face_center = poly.center
        for li in poly.loop_indices:
            vi = me.loops[li].vertex_index
            v = me.vertices[vi]
            s.co, s.normal, s.index = v.co, v.normal, vi
            s.ao = ao[vi] if ao else 1.0
            c = color_fn(s)
            attr.data[li].color = (c[0], c[1], c[2], 1.0)
    me.color_attributes.active_color = attr
    try:
        me.color_attributes.render_color_index = me.color_attributes.find(VC_LAYER)
    except (AttributeError, TypeError):
        pass


BARK = [(0.0, hexcol("#3b2519")), (0.55, hexcol("#5e3d29")), (1.0, hexcol("#8a5f3f"))]
PINE = [(0.0, hexcol("#12342a")), (0.35, hexcol("#1f5238")), (0.62, hexcol("#2f7445")),
        (0.85, hexcol("#56984a")), (1.0, hexcol("#9cc75e"))]
BROADLEAF = [(0.0, hexcol("#1e4424")), (0.35, hexcol("#2f6a2c")), (0.62, hexcol("#4a8f35")),
             (0.85, hexcol("#76b041")), (1.0, hexcol("#b2d25a"))]
ROCK = [(0.0, hexcol("#5f5650")), (0.45, hexcol("#9a8c7e")), (0.8, hexcol("#c2b3a0")),
        (1.0, hexcol("#ddd0bb"))]
MOSS = [(0.0, hexcol("#3d6a2a")), (0.6, hexcol("#6e9a38")), (1.0, hexcol("#a6c04e"))]


def bark_color(s):
    streak = nz((s.co.x * 9.0, s.co.y * 9.0, s.co.z * 1.4), 1.0, 3.0)
    t = 0.55 + 0.35 * streak
    c = ramp(BARK, t * (0.55 + 0.45 * s.ao))
    return c


def foliage_color(palette, s, warm=0.0, seed=0.0):
    up = s.normal.z * 0.5 + 0.5
    hue = nz(s.co, 0.45, seed)
    t = 0.02 + 0.62 * s.ao ** 1.5 + 0.26 * up + 0.10 * hue
    c = ramp(palette, t)
    if warm:
        c = mix(c, hexcol("#c9b04a"), warm * clamp01(0.5 + hue) * up * s.ao)
    return c


def root_flare(n_roots, height, strength, phase):
    """radial_fn for lathe(): buttress roots fading out with height."""
    def fn(th, i, r, z):
        f = clamp01(1.0 - z / height) ** 1.5
        roots = (0.5 + 0.5 * math.cos(n_roots * th + phase)) ** 2
        return r * (1.0 + strength * f * roots), z
    return fn


# Pine tier cross-section: (radial fraction, height fraction) from the underside pole near the
# trunk, outwards along the underside, around the rolled rim and up the top to the apex.
PINE_TIER = [(0.00, 0.30), (0.30, 0.17), (0.62, 0.07), (0.86, 0.015), (0.98, 0.045),
             (1.00, 0.12), (0.93, 0.21), (0.75, 0.37), (0.53, 0.56), (0.31, 0.75),
             (0.13, 0.91), (0.00, 1.00)]


def _pine_deform(radius, lobes, phase, amp, h):
    """radial_fn for a pine tier: drooping lobed rim (shared by the snowy variant)."""
    def deform(th, i, r, z):
        s = r / radius
        w = smoothstep(0.35, 1.0, s)
        k = (lobes * (th + phase / lobes) / TAU)
        a = amp[int(math.floor(k + 0.5)) % lobes]
        lobe = (0.5 + 0.5 * math.cos(lobes * th + phase)) ** 1.6 * a
        lobe += 0.12 * (0.5 + 0.5 * math.cos(2 * lobes * th + phase * 2 + 1.0))
        r2 = r * (1.0 + w * (0.30 * lobe - 0.13))
        z2 = z - h * w * w * (0.17 * lobe - 0.06)
        return r2, z2
    return deform


def pine_tier(part, z0, z1, radius, lobes, phase, rng, segments=52):
    h = z1 - z0
    amp = [rng.uniform(0.75, 1.25) for _ in range(lobes)]
    deform = _pine_deform(radius, lobes, phase, amp, h)

    tilt = Matrix.Rotation(rng.uniform(-0.05, 0.05), 4, "X") @ Matrix.Rotation(rng.uniform(-0.05, 0.05), 4, "Y")
    profile = [(s * radius, z0 + t * h) for s, t in PINE_TIER]
    M = Matrix.Translation((0, 0, z0)) @ tilt @ Matrix.Translation((0, 0, -z0))
    lathe(part, profile, segments, "leaves_dark", radial_fn=deform, matrix=M)


def build_tree_pine():
    rng = random.Random(7)
    trunk = Part("pine_trunk")
    lathe(trunk, [(0.34, -0.08), (0.30, 0.10), (0.235, 0.35), (0.20, 0.9), (0.17, 2.0),
                  (0.13, 3.6), (0.09, 5.2), (0.05, 6.8), (0.0, 7.3)],
          12, "bark", radial_fn=root_flare(5, 0.75, 0.65, 0.4))
    displace(trunk.bm, 0.015, 5.0, seed=1)
    trunk_obj = trunk.finish()

    foliage = Part("pine_foliage")
    # (bottom z, top z, radius, lobe count)
    tiers = [(1.65, 4.20, 2.50, 9), (2.80, 5.30, 2.08, 8), (3.92, 6.35, 1.67, 8),
             (5.00, 7.38, 1.25, 7), (6.05, 8.45, 0.83, 6)]
    for z0, z1, radius, lobes in tiers:
        pine_tier(foliage, z0, z1, radius, lobes, rng.uniform(0, TAU), rng)
    displace(foliage.bm, 0.05, 1.1, seed=2)
    foliage_obj = foliage.finish()

    obj = join_objects([trunk_obj, foliage_obj], "tree_pine")
    ao = bake_ao(obj, samples=28, max_dist=2.6)

    def color(s):
        if s.mat == "bark":
            return bark_color(s)
        return foliage_color(PINE, s, warm=0.25, seed=4.0)

    paint(obj, color, ao)
    return obj


# Metaball settings for crisp foliage puffs: threshold/stiffness = 0.03 -> each puff's visible
# radius is PUFF_K x its element radius (solve stiffness*(1-k^2)^3 = threshold).
PUFF_THRESHOLD, PUFF_STIFFNESS = 0.06, 2.0
PUFF_K = math.sqrt(1.0 - (PUFF_THRESHOLD / PUFF_STIFFNESS) ** (1.0 / 3.0))


def puff_cluster(rng, center, semi_axes, n_dirs, radius_range, min_dir_z=-0.5, core_radius=0.0,
                 shell=0.8):
    """Foliage puffs spread over an ellipsoid shell (Fibonacci directions, jittered).

    Returns metaball elements [(center, element_radius)] plus the visible puff centres/radii.
    Puffs whose direction points too far down (``min_dir_z``) are skipped so the underside
    stays open and branches show.  ``core_radius`` adds one big filler puff in the middle.
    """
    c = Vector(center)
    ax, ay, az = semi_axes
    golden = math.pi * (3.0 - math.sqrt(5.0))
    puffs = []
    for i in range(n_dirs):
        z = 1.0 - 2.0 * (i + 0.5) / n_dirs
        if z < min_dir_z:
            continue
        rad = math.sqrt(max(0.0, 1.0 - z * z))
        a = i * golden + rng.uniform(-0.25, 0.25)
        d = Vector((rad * math.cos(a), rad * math.sin(a), z))
        s = shell * rng.uniform(0.88, 1.10)
        pos = c + Vector((d.x * ax * s, d.y * ay * s, d.z * az * s))
        puffs.append((pos, rng.uniform(*radius_range)))
    if core_radius > 0.0:
        puffs.append((c.copy(), core_radius))
    balls = [(tuple(p), r / PUFF_K) for p, r in puffs]
    return balls, puffs


def build_tree_round():
    """~6.5 m broadleaf: flared trunk forking into limbs under a canopy of distinct puffs."""
    rng = random.Random(21)
    wood = Part("round_wood")
    flare = root_flare(4, 0.9, 0.55, 0.9)
    trunk_path = [(0, 0, -0.10), (0.0, 0.0, 0.25), (0.03, 0.01, 0.8), (0.06, 0.03, 1.5),
                  (0.03, 0.06, 2.2), (-0.03, 0.04, 2.9), (-0.06, 0.02, 3.6)]
    trunk_r = [0.36, 0.30, 0.25, 0.22, 0.20, 0.16, 0.10]
    sweep(wood, trunk_path, trunk_r, 12, "bark",
          radial_fn=lambda th, i, r: flare(th, 0, r, trunk_path[i][2])[0])
    for ang, z_start, length, lift, r0 in [
            (0.3, 1.95, 1.55, 1.55, 0.14), (2.4, 2.15, 1.45, 1.65, 0.13), (4.3, 2.35, 1.35, 1.5, 0.12),
            (1.3, 2.75, 1.0, 1.15, 0.08), (5.3, 2.95, 0.9, 1.05, 0.075)]:
        d = Vector((math.cos(ang), math.sin(ang), 0.0))
        start = Vector((0.02, 0.03, z_start))
        path = [start, start + d * (0.30 * length) + Vector((0, 0, 0.35 * lift)),
                start + d * (0.65 * length) + Vector((0, 0, 0.72 * lift)),
                start + d * length + Vector((0, 0, lift))]
        sweep(wood, path, [r0, r0 * 0.78, r0 * 0.55, r0 * 0.32], 8, "bark", cap_end=True)
    displace(wood.bm, 0.012, 5.0, seed=3)
    wood_obj = wood.finish()

    balls, puffs = puff_cluster(rng, (0.0, 0.0, 4.55), (1.95, 1.95, 1.35), 24, (0.66, 1.15),
                                min_dir_z=-0.62, core_radius=1.55, shell=0.86)
    canopy = metaball_mesh("round_canopy", balls, resolution=0.085,
                           threshold=PUFF_THRESHOLD, stiffness=PUFF_STIFFNESS)
    decimate_to(canopy, 6900)

    def bumpy(bm):
        displace(bm, 0.05, 1.4, seed=5)
        displace(bm, 0.02, 4.0, seed=6)
    edit_mesh(canopy, bumpy)
    canopy.data.materials.append(material("leaves"))
    set_smooth(canopy)

    obj = join_objects([wood_obj, canopy], "tree_round")
    ao = bake_ao(obj, samples=32, max_dist=1.6)
    tint = [rng.uniform(-1.0, 1.0) for _ in puffs]

    def color(s):
        if s.mat == "bark":
            return bark_color(s)
        i = min(range(len(puffs)), key=lambda k: (s.co - puffs[k][0]).length - puffs[k][1])
        c = foliage_color(BROADLEAF, s, warm=0.3, seed=7.0)
        shade = hexcol("#9fbf3c") if tint[i] > 0 else hexcol("#1f5a36")
        return mix(c, shade, 0.16 * abs(tint[i]))

    paint(obj, color, ao)
    return obj


def build_bush():
    """~1.2 m round shrub made of many small puffs, dotted with five-petal blossoms."""
    rng = random.Random(33)
    balls, puffs = puff_cluster(rng, (0.0, 0.0, 0.50), (0.60, 0.56, 0.42), 22, (0.19, 0.30),
                                min_dir_z=-0.3, core_radius=0.47, shell=0.92)
    body = metaball_mesh("bush_body", balls, resolution=0.026,
                         threshold=PUFF_THRESHOLD, stiffness=PUFF_STIFFNESS)
    decimate_to(body, 1560)

    def shape(bm):
        zmin = min(v.co.z for v in bm.verts)
        for v in bm.verts:
            v.co.z = max(v.co.z - zmin - 0.06, -0.06)
        displace(bm, 0.018, 3.5, seed=8)
    edit_mesh(body, shape)
    body.data.materials.append(material("leaves"))
    set_smooth(body)

    blossoms = Part("bush_flowers")
    cands = [v for v in body.data.vertices if v.normal.z > 0.15 and v.co.z > 0.4]
    rng.shuffle(cands)
    chosen = []
    for v in cands:
        if all((v.co - c).length > 0.26 for c, _ in chosen):
            chosen.append((v.co.copy() + v.normal * 0.01, v.normal.copy()))
        if len(chosen) == 12:
            break

    def petals(th, i, r, z):
        return r * (0.45 + 0.55 * abs(math.cos(2.5 * th))), z
    for c, n in chosen:
        M = (Matrix.Translation(c) @ n.to_track_quat("Z", "Y").to_matrix().to_4x4() @
             Matrix.Rotation(rng.uniform(0, TAU), 4, "Z"))
        lathe(blossoms, [(0.0, -0.012), (0.075, 0.0), (0.0, 0.022)], 15, "flowers",
              radial_fn=petals, matrix=M)
    flowers_obj = blossoms.finish()

    obj = join_objects([body, flowers_obj], "bush")
    ao = bake_ao(obj, samples=28, max_dist=0.5)
    petal_cols = [hexcol("#fff3f6"), hexcol("#ff8db6"), hexcol("#ffffff")]
    flower_pts = [c for c, _ in chosen]
    tint = [rng.uniform(-1.0, 1.0) for _ in puffs]

    def color(s):
        if s.mat == "flowers":
            k = min(range(len(flower_pts)), key=lambda j: (s.co - flower_pts[j]).length_squared)
            if (s.co - flower_pts[k]).length < 0.03:
                return hexcol("#ffc21c")
            return petal_cols[k % 3]
        i = min(range(len(puffs)), key=lambda k: (s.co - puffs[k][0]).length - puffs[k][1])
        c = foliage_color(BROADLEAF, s, warm=0.2, seed=11.0)
        shade = hexcol("#9fbf3c") if tint[i] > 0 else hexcol("#1f5a36")
        return mix(c, shade, 0.15 * abs(tint[i]))

    paint(obj, color, ao)
    return obj


def rock_chunk(part, rng, center, size, n_planes=11, embed=0.12, lean=(0.0, 0.0), yaw=None,
               taper=0.0, mats=("rock", "moss")):
    """Chiselled boulder.

    An icosphere is squashed into a lumpy ellipsoid, then "chiselled" by clamping it against
    random cutting planes: every plane leaves a large flat facet.  A couple of smoothing passes
    round the ridges where facets meet, giving the stylised faceted-but-soft look.  The lowest
    part is flattened into a base and buried ``embed`` metres into the ground.
    """
    sx, sy, sz = size
    seed = rng.uniform(0.0, 100.0)
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=4, radius=1.0)
    for v in bm.verts:
        d = v.co.normalized()
        lump = 1.0 + 0.10 * nz(d, 1.2, seed) + 0.04 * nz(d, 2.8, seed + 1)
        narrow = 1.0 - taper * (d.z * 0.5 + 0.5)
        v.co = Vector((d.x * sx * 0.5 * narrow, d.y * sy * 0.5 * narrow, d.z * sz * 0.5)) * lump

    def chisel(n, depth):
        n = n.normalized()
        support = max(v.co.dot(n) for v in bm.verts)
        limit = support * depth
        for v in bm.verts:
            excess = v.co.dot(n) - limit
            if excess > 0.0:
                v.co -= n * excess

    chisel(Vector((rng.uniform(-0.25, 0.25), rng.uniform(-0.25, 0.25), 1.0)), rng.uniform(0.70, 0.80))
    for k in range(n_planes):
        a = k * TAU / n_planes + rng.uniform(-0.3, 0.3)
        e = rng.uniform(0.2, 0.95) if rng.random() < 0.7 else rng.uniform(-0.3, 0.2)
        chisel(Vector((math.cos(a) * math.cos(e), math.sin(a) * math.cos(e), math.sin(e))),
               rng.uniform(0.62, 0.80))
    for _ in range(1):
        bmesh.ops.smooth_vert(bm, verts=bm.verts, factor=0.4,
                              use_axis_x=True, use_axis_y=True, use_axis_z=True)
    zs = [v.co.z for v in bm.verts]
    zmin, zmax = min(zs), max(zs)
    base = zmin + (zmax - zmin) * 0.16
    for v in bm.verts:
        v.co.z = max(v.co.z, base)
    for v in bm.verts:
        v.co.z = (v.co.z - base) / (zmax - base) * (sz + embed) - embed
        v.co.x += lean[0] * max(v.co.z, 0.0)
        v.co.y += lean[1] * max(v.co.z, 0.0)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.004)
    rot = Matrix.Rotation(yaw if yaw is not None else rng.uniform(0, TAU), 4, "Z")
    bmesh.ops.transform(bm, matrix=Matrix.Translation(Vector(center)) @ rot, verts=bm.verts)
    idx = part.mi(mats[0])
    part.mi(mats[1])
    for f in bm.faces:
        f.material_index = idx
    part.merge(bm)


def finish_rock(part, name, seed, target_tris=2900):
    obj = part.finish()
    decimate_to(obj, target_tris)
    set_smooth(obj, 40)
    obj.name = name
    obj.data.name = name
    me = obj.data
    height = max(v.co.z for v in me.vertices)
    mats = [m.name for m in me.materials]
    rock_i, moss_i = mats.index("rock"), mats.index("moss")

    def moss_weight(p, n):
        w = n.z + 0.20 * nz(p, 1.1, seed) + 0.07 * nz(p, 3.5, seed + 1)
        return smoothstep(0.50, 0.80, w) * smoothstep(0.2, 0.5, p.z / height + 0.05)

    for poly in me.polygons:
        poly.material_index = moss_i if moss_weight(poly.center, poly.normal) > 0.5 else rock_i
    ao = bake_ao(obj, samples=24, max_dist=min(1.2, height))

    def color(s):
        strata = nz((s.co.x * 0.5, s.co.y * 0.5, s.co.z * 3.2), 1.0, seed + 2)
        grain = nz(s.co, 3.0, seed + 3)
        t = 0.50 + 0.30 * strata + 0.10 * grain + 0.18 * s.face_normal.z
        t *= 0.45 + 0.55 * s.ao ** 1.4
        c = ramp(ROCK, t)
        w = moss_weight(s.co, (s.face_normal + s.normal).normalized())
        m = ramp(MOSS, 0.25 + 0.55 * s.ao + 0.25 * grain)
        return mix(c, m, w)

    paint(obj, color, ao)
    return obj


def build_rock_a():
    """Big rounded boulder (~2.6 m) with a smaller chunk leaning on it."""
    rng = random.Random(101)
    p = Part("rock_a")
    rock_chunk(p, rng, (-0.15, 0.0, 0.0), (2.7, 2.1, 1.55), n_planes=14, yaw=0.3)
    rock_chunk(p, rng, (1.1, -0.6, 0.0), (1.05, 0.95, 0.8), n_planes=9)
    return finish_rock(p, "rock_a", 1.0)


def build_rock_b():
    """Tall standing stone (~2.9 m), slightly leaning, with a small rock at its foot."""
    rng = random.Random(202)
    p = Part("rock_b")
    rock_chunk(p, rng, (0.0, 0.0, 0.0), (1.7, 1.4, 2.9), n_planes=13, lean=(0.10, 0.04), yaw=0.8,
               taper=0.45)
    rock_chunk(p, rng, (-0.72, 0.45, 0.0), (0.85, 0.75, 0.62), n_planes=8)
    return finish_rock(p, "rock_b", 2.0)


def build_rock_c():
    """Low cluster of three rocks (~2 m footprint)."""
    rng = random.Random(303)
    p = Part("rock_c")
    rock_chunk(p, rng, (-0.35, 0.05, 0.0), (1.45, 1.15, 0.95), n_planes=10)
    rock_chunk(p, rng, (0.68, -0.28, 0.0), (0.95, 0.85, 0.66), n_planes=9)
    rock_chunk(p, rng, (0.38, 0.66, 0.0), (0.62, 0.52, 0.42), n_planes=8)
    return finish_rock(p, "rock_c", 3.0)


# Tyre cross-section (r, z), walked bottom sidewall -> tread -> top sidewall -> bore
# (outside on the right-hand side, see lathe()).  Squarish car tyre: bulging sidewalls,
# tight shoulders, flat tread, visible bead lip in the bore.
TIRE_PROFILE = [(0.172, 0.022), (0.185, 0.008), (0.215, 0.002), (0.255, 0.004), (0.282, 0.012),
                (0.296, 0.030), (0.301, 0.052), (0.302, 0.066), (0.303, 0.100), (0.302, 0.134),
                (0.301, 0.148), (0.296, 0.170), (0.282, 0.188), (0.255, 0.196), (0.215, 0.198),
                (0.185, 0.192), (0.172, 0.178), (0.163, 0.150), (0.161, 0.100), (0.163, 0.050)]
TIRE_PAINTED_EDGES = range(6, 10)


def build_tire_stack():
    """Three stacked tyres (0.6 m wide, 0.6 m tall) with red/white/red painted bands."""
    rng = random.Random(5)
    p = Part("tire_stack")
    for k, paint_mat in enumerate(["paint_red", "paint_white", "paint_red"]):
        mats = ["rubber"] * len(TIRE_PROFILE)
        for e in TIRE_PAINTED_EDGES:
            mats[e] = paint_mat
        tilt = (Matrix.Rotation(rng.uniform(-0.03, 0.03), 4, "X") @
                Matrix.Rotation(rng.uniform(-0.03, 0.03), 4, "Y"))
        M = Matrix.Translation((rng.uniform(-0.02, 0.02), rng.uniform(-0.02, 0.02),
                                k * 0.197)) @ tilt
        squash = rng.uniform(0.004, 0.009)

        def squish(th, i, r, z, k=k, squash=squash):
            return r * (1.0 + squash * math.sin(2 * th + k * 1.7)), z
        lathe(p, TIRE_PROFILE, 32, mats=mats, closed=True, radial_fn=squish, matrix=M,
              phase=rng.uniform(0, 1))
    return p.finish(smooth=50)


def build_traffic_cone():
    p = Part("traffic_cone")
    prof = [(0.168, 0.030), (0.168, 0.048), (0.150, 0.060), (0.138, 0.10), (0.118, 0.205),
            (0.101, 0.300), (0.086, 0.380), (0.071, 0.455), (0.059, 0.520), (0.042, 0.610),
            (0.031, 0.665), (0.022, 0.692), (0.011, 0.703), (0.0, 0.706)]
    mats = ["paint_orange"] * (len(prof) - 1)
    mats[4] = mats[7] = "paint_white"
    lathe(p, prof, 26, mats=mats)
    outline = []
    half, rad = 0.20, 0.055
    for cx, cy, a0 in [(1, 1, 0), (-1, 1, 90), (-1, -1, 180), (1, -1, 270)]:
        for s in range(5):
            a = math.radians(a0 + s * 22.5)
            outline.append(((half - rad) * cx + rad * math.cos(a), (half - rad) * cy + rad * math.sin(a)))
    bm = p.bm
    idx = p.mi("rubber")
    rings = []
    for z, inset in [(0.0, 0.0), (0.024, 0.0), (0.036, 0.012)]:
        ring = []
        for x, y in outline:
            v = Vector((x, y, 0.0))
            v = v - v.normalized() * inset
            ring.append(bm.verts.new((v.x, v.y, z)))
        rings.append(ring)
    n = len(outline)
    bm.faces.new(list(reversed(rings[0]))).material_index = idx
    for a, b in zip(rings, rings[1:]):
        for j in range(n):
            j2 = (j + 1) % n
            bm.faces.new((a[j], a[j2], b[j2], b[j])).material_index = idx
    bm.faces.new(rings[-1]).material_index = idx
    return p.finish(smooth=40)


def box_truss(part, origin, axis, length, u, v, hu, hv, panel, chord_r, brace_r, mat):
    """Square-section aluminium truss: 4 chords + rungs + zig-zag diagonals on every face."""
    origin, axis, u, v = Vector(origin), Vector(axis).normalized(), Vector(u), Vector(v)
    corners = [u * hu + v * hv, -u * hu + v * hv, -u * hu - v * hv, u * hu - v * hv]
    n = max(1, round(length / panel))
    step = length / n
    for c in corners:
        tube(part, origin + c, origin + c + axis * length, chord_r, 10, mat, caps=True)
    for k in range(n + 1):
        s = axis * (k * step)
        for i in range(4):
            a, b = corners[i], corners[(i + 1) % 4]
            tube(part, origin + s + a, origin + s + b, brace_r, 6, mat)
            if k < n:
                s2 = axis * ((k + 1) * step)
                if (k + i) % 2 == 0:
                    tube(part, origin + s + a, origin + s2 + b, brace_r, 6, mat)
                else:
                    tube(part, origin + s + b, origin + s2 + a, brace_r, 6, mat)


def build_start_arch():
    """Start/finish gantry over a 16 m road running along Y.

    Legs at x = +-9 m, clear width 16.5 m (inside of the crash pads), clear height 5.5 m
    (bottom of the start-light pod).  Banner/checkers/lights on both faces (+-Y).
    """
    parts = []
    metal = Part("arch_truss")
    for sx in (-1, 1):
        box_truss(metal, (sx * 9.0, 0, 1.8), (0, 0, 1), 8.0, Vector((1, 0, 0)), Vector((0, 1, 0)),
                  0.4, 0.4, 0.8, 0.055, 0.026, "metal")
    box_truss(metal, (-9.4, 0, 9.3), (1, 0, 0), 18.8, Vector((0, 1, 0)), Vector((0, 0, 1)),
              0.4, 0.5, 0.94, 0.055, 0.026, "metal")
    for x in (-1.25, 1.25):
        tube(metal, (x, 0, 6.2), (x, 0, 6.6), 0.04, 8, "metal")
    for sx in (-1, 1):
        tube(metal, (sx * 9.0, 0, 9.95), (sx * 9.0, 0, 11.3), 0.035, 8, "metal", caps=True)
    parts.append(metal.finish(smooth=40))

    solid = Part("arch_solids", recalc_normals=True)
    for sx in (-1, 1):
        x = sx * 9.0
        box(solid, (x, 0, 0.08), (1.9, 1.9, 0.16), "concrete", bevel=0.04, segments=1)
        box(solid, (x, 0, 0.98), (1.5, 1.5, 1.64), "paint_red", bevel=0.16, segments=3)
        box(solid, (x, 0, 1.38), (1.54, 1.54, 0.26), "paint_white", bevel=0.12, segments=3)
        box(solid, (x, 0, 1.83), (1.0, 1.0, 0.06), "metal_dark", bevel=0.02, segments=1)
        box(solid, (x, 0, 9.88), (0.98, 0.98, 0.14), "paint_red", bevel=0.05, segments=2)
        bm = bmesh.new()
        bmesh.ops.create_uvsphere(bm, u_segments=12, v_segments=8, radius=0.08)
        bmesh.ops.translate(bm, vec=(x, 0, 11.32), verts=bm.verts)
        for f in bm.faces:
            f.material_index = solid.mi("paint_yellow")
        solid.merge(bm)
    box(solid, (0, 0, 7.66), (15.6, 0.30, 2.30), "metal_dark", bevel=0.09, segments=3)
    box(solid, (0, 0, 5.95), (3.6, 0.42, 0.74), "paint_black", bevel=0.1, segments=3)
    parts.append(solid.finish(smooth=40))

    deco = Part("arch_decals")
    x0, x1 = -7.45, 7.45
    for side in (-1, 1):
        y = side * (0.15 + 0.004)
        facing = (0, side, 0)
        u0, u1 = (0.0, 1.0) if side < 0 else (1.0, 0.0)
        quad(deco, [(x0, y, 7.12), (x1, y, 7.12), (x1, y, 8.66), (x0, y, 8.66)], "banner",
             uvs=[(u0, 0), (u1, 0), (u1, 1), (u0, 1)], facing=facing)
        cols, rows, z0, z1 = 70, 2, 6.62, 7.04
        w, h = (x1 - x0) / cols, (z1 - z0) / rows
        for r in range(rows):
            for c in range(cols):
                m = "paint_black" if (r + c) % 2 == 0 else "paint_white"
                xa, za = x0 + c * w, z0 + r * h
                quad(deco, [(xa, y, za), (xa + w, y, za), (xa + w, y, za + h), (xa, y, za + h)], m,
                     facing=facing)
    parts.append(deco.finish(smooth="flat"))

    lights = Part("arch_lights")
    lens = [(0.17, 0.0), (0.165, 0.03), (0.13, 0.065), (0.07, 0.088), (0.0, 0.094)]
    bezel = [(0.215, -0.01), (0.215, 0.025), (0.19, 0.035), (0.172, 0.03)]
    for side in (-1, 1):
        R = Matrix.Rotation(side * -math.pi / 2, 4, "X")
        for i in range(5):
            x = (i - 2) * 0.66
            M = Matrix.Translation((x, side * 0.205, 5.93)) @ R
            lathe(lights, lens, 18, "start_light", matrix=M)
            lathe(lights, bezel, 18, "metal", matrix=M)
            visor = Matrix.Translation((x, side * 0.30, 6.17)) @ Matrix.Rotation(side * -0.32, 4, "X")
            box(lights, (0, 0, 0), (0.46, 0.20, 0.025), "paint_black", bevel=0.008, segments=1,
                matrix=visor)
    parts.append(lights.finish(smooth=45))

    flags = Part("arch_pennants")
    for sx in (-1, 1):
        grid = []
        for r in range(4):
            row = []
            for c in range(7):
                u, vv = c / 6, r / 3
                half_h = 0.32 * (1 - 0.85 * u)
                x = sx * 9.0 + 0.04 + u * 1.1
                z = 11.15 + (vv - 0.5) * 2 * half_h - 0.12 * u
                y = 0.08 * math.sin(u * 5.0 + sx) * u
                row.append(Vector((x if sx > 0 else sx * 9.0 - (x - sx * 9.0), y, z)))
            grid.append(row)
        sheet(flags, grid, 0.012, "paint_yellow")
    parts.append(flags.finish(smooth=60))
    return join_objects(parts, "start_arch")


SEAT_PROFILE = [(-0.20, 0.40), (-0.16, 0.45), (0.06, 0.43), (0.13, 0.47), (0.17, 0.86),
                (0.22, 0.88), (0.25, 0.84), (0.20, 0.44), (0.12, 0.37), (-0.17, 0.36)]


def build_grandstand():
    """20 m bleacher along X facing -Y: 7 seated rows, two aisles, cantilever roof."""
    rows, depth, rise = 7, 0.85, 0.42
    y0, z0 = -2.9, 0.70
    yb = y0 + rows * depth
    ztop = z0 + (rows - 1) * rise
    aisles = (-3.6, 3.6)
    half_len = 10.0
    sections = [(-9.75, -4.15), (-3.05, 3.05), (4.15, 9.75)]

    body = Part("stand_body", recalc_normals=True)
    prof = [(y0, 0.0)]
    for i in range(rows):
        z = z0 + i * rise
        prof += [(y0 + i * depth, z), (y0 + (i + 1) * depth, z)]
    prof += [(yb, 0.0)]
    extrude_x(body, prof, -half_len, half_len, "concrete")
    for sx in (-1, 1):
        x_in, x_out = sx * half_len, sx * (half_len + 0.3)
        wall = [(y0 - 0.06, 0.0), (y0 - 0.06, z0 + 1.1), (yb + 0.06, ztop + 1.25), (yb + 0.06, 0.0)]
        extrude_x(body, wall, min(x_in, x_out), max(x_in, x_out), "paint_white")
    for ax in aisles:
        for i in range(1, rows):
            zb = z0 + (i - 1) * rise
            yf = y0 + i * depth
            box(body, (ax, yf - depth * 0.25, zb + rise * 0.25), (1.0, depth * 0.5, rise * 0.5), "concrete")
            box(body, (ax, yf - depth * 0.5 + 0.03, zb + rise * 0.5 + 0.01), (1.0, 0.06, 0.02), "paint_yellow")
            box(body, (ax, yf + 0.03, zb + rise + 0.01), (1.0, 0.06, 0.02), "paint_yellow")
        for k in range(1, 3):
            zt = z0 - k * z0 / 3
            box(body, (ax, y0 - k * 0.17, zt * 0.5), (1.1, k * 0.34, zt), "concrete")
            box(body, (ax, y0 - k * 0.34 + 0.03, zt + 0.01), (1.1, 0.06, 0.02), "paint_yellow")
    box(body, (0, y0 - 0.03, z0 * 0.5), (19.8, 0.06, z0 * 0.72), "paint_red", bevel=0.02, segments=1)

    for i in range(rows):
        z = z0 + i * rise
        ys = y0 + i * depth + 0.43
        for si, (xa, xb) in enumerate(sections):
            n = int((xb - xa) / 0.56)
            pitch = (xb - xa) / n
            for c in range(n):
                x = xa + pitch * (c + 0.5)
                mat = "seat"
                if si == 1 and round(abs(c - (n - 1) / 2) - 0.5) == round(i * (n / 2 - 1) / (rows - 1)):
                    mat = "seat_alt"
                extrude_x(body, [(ys + y, z + zz) for y, zz in SEAT_PROFILE], x - 0.22, x + 0.22, mat)
                box(body, (x, ys + 0.07, z + 0.185), (0.09, 0.12, 0.37), "metal_dark")

    yr_b, yr_f = yb + 0.75, y0 - 0.85
    n = 12
    top, bot = [], []
    for k in range(n + 1):
        f = k / n
        y = lerp(yr_b, yr_f, f)
        zb = 7.25 + 0.55 * f + 0.18 * math.sin(math.pi * f)
        bot.append((y, zb))
        top.append((y, zb + lerp(0.26, 0.12, f)))
    extrude_x(body, top + list(reversed(bot)), -half_len - 0.8, half_len + 0.8, "paint_white")
    roof_bottom = bot
    fz = roof_bottom[-1][1] + 0.05
    box(body, (0, yr_f - 0.06, fz), (2 * half_len + 1.7, 0.14, 0.62), "paint_red", bevel=0.05, segments=2)
    box(body, (0, yr_f - 0.14, fz - 0.17), (2 * half_len + 1.6, 0.03, 0.07), "paint_white")
    for x in (-9.6, -4.8, 0.0, 4.8, 9.6):
        box(body, (x, yb + 0.35, 0.04), (0.6, 0.6, 0.08), "concrete", bevel=0.02, segments=1)
        beam = [(y, zb - 0.005) for y, zb in roof_bottom]
        beam += [(y, zb - lerp(0.75, 0.14, k / n)) for k, (y, zb) in reversed(list(enumerate(roof_bottom)))]
        extrude_x(body, beam, x - 0.11, x + 0.11, "metal")
    stand_obj = body.finish(smooth=35)

    steel = Part("stand_steel")
    for x in (-9.6, -4.8, 0.0, 4.8, 9.6):
        tube(steel, (x, yb + 0.35, 0.0), (x, yb + 0.35, 7.35), 0.17, 14, "metal")
        tube(steel, (x, yb + 0.35, 4.4), (x, -0.9, 7.25 + 0.55 * 0.6 + 0.18 * math.sin(math.pi * 0.6) - 0.4),
             0.06, 8, "metal", caps=True)
    for xa, xb in [(-10.0, -4.15), (-3.05, 3.05), (4.15, 10.0)]:
        yr = y0 + 0.06
        tube(steel, (xa, yr, z0 + 1.0), (xb, yr, z0 + 1.0), 0.035, 8, "metal", caps=True)
        tube(steel, (xa, yr, z0 + 0.52), (xb, yr, z0 + 0.52), 0.02, 6, "metal", caps=True)
        nposts = max(2, int((xb - xa) / 1.9) + 1)
        for k in range(nposts):
            x = lerp(xa + 0.05, xb - 0.05, k / (nposts - 1))
            tube(steel, (x, yr, z0), (x, yr, z0 + 1.0), 0.025, 6, "metal")
    yr = yb - 0.06
    tube(steel, (-10, yr, ztop + 1.05), (10, yr, ztop + 1.05), 0.035, 8, "metal", caps=True)
    tube(steel, (-10, yr, ztop + 0.55), (10, yr, ztop + 0.55), 0.02, 6, "metal", caps=True)
    for k in range(11):
        x = lerp(-9.95, 9.95, k / 10)
        tube(steel, (x, yr, ztop), (x, yr, ztop + 1.05), 0.025, 6, "metal")
    for ax in aisles:
        p_lo = Vector((ax, y0 + 0.15, z0 + 0.95))
        p_hi = Vector((ax, yb - 0.4, ztop + 0.95))
        tube(steel, p_lo, p_hi, 0.03, 8, "metal", caps=True)
        for i in range(0, rows, 2):
            y = y0 + i * depth + 0.15
            f = (y - p_lo.y) / (p_hi.y - p_lo.y)
            tube(steel, (ax, y, z0 + i * rise), (ax, y, lerp(p_lo.z, p_hi.z, f)), 0.025, 6, "metal")
    steel_obj = steel.finish(smooth=40)
    return join_objects([stand_obj, steel_obj], "grandstand")


def build_flag_pole():
    p = Part("flag_pole")
    lathe(p, [(0.30, 0.0), (0.30, 0.085), (0.285, 0.115), (0.25, 0.125), (0.0, 0.127)], 20, "concrete")
    lathe(p, [(0.075, 0.12), (0.075, 0.20), (0.062, 0.24), (0.05, 0.27), (0.047, 1.0),
              (0.034, 4.96), (0.0, 4.97)], 12, "metal")
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=14, v_segments=8, radius=0.075)
    bmesh.ops.translate(bm, vec=(0, 0, 5.03), verts=bm.verts)
    for f in bm.faces:
        f.material_index = p.mi("paint_yellow")
    p.merge(bm)
    cols, rows, length, height, ztop = 24, 9, 1.6, 1.0, 4.86
    grid = []
    for r in range(rows):
        row = []
        for c in range(cols):
            u, v = c / (cols - 1), r / (rows - 1)
            x = 0.045 + u * length * 0.97
            wave = math.sin(TAU * (1.45 * u) - 1.1 * v - 0.5) + 0.25 * math.sin(TAU * 2.9 * u + 0.7 * v)
            y = 0.17 * u ** 0.9 * wave + 0.04 * u
            z = ztop - (1 - v) * height - 0.10 * u ** 2 * (1.2 - v) + 0.03 * wave * u
            row.append(Vector((x, y, z)))
        grid.append(row)
    sheet(p, grid, 0.012, "flag")
    for z in (ztop - 0.02, ztop - height + 0.02):
        box(p, (0.042, 0, z), (0.05, 0.05, 0.05), "metal_dark", bevel=0.01, segments=1)
    tube(p, (0.05, 0.0, 0.9), (0.05, 0.0, 4.93), 0.007, 4, "paint_white")
    box(p, (0.065, 0, 0.9), (0.03, 0.04, 0.12), "metal_dark", bevel=0.006, segments=1)
    return p.finish(smooth=45)


def superellipse(p=5.0):
    """Radius multiplier turning a circle into a rounded square (bevelled timber look)."""
    def fn(th):
        c, s = abs(math.cos(th)), abs(math.sin(th))
        return 1.0 / (c ** p + s ** p) ** (1.0 / p)
    return fn


def build_fence_segment():
    """4 m ranch fence along X: square timber posts at x = -2, 0, +2 (end posts coincide with
    the neighbouring segment's, so segments tile every 4 m), two sagging plank rails on the
    -Y side held by metal brackets and bolts."""
    rng = random.Random(9)
    se = superellipse(5.0)
    posts = Part("fence_posts")
    prof = [(0.075, -0.12), (0.076, 0.40), (0.075, 1.00), (0.072, 1.035), (0.045, 1.085),
            (0.012, 1.105), (0.0, 1.107)]
    for x in (-2.0, 0.0, 2.0):
        lean = 0.0 if x else 0.025          # end posts must match the neighbours exactly
        M = Matrix.Translation((x, 0, 0)) @ Matrix.Rotation(lean, 4, "Y")
        lathe(posts, prof, 12, "wood_dark", matrix=M,
              radial_fn=lambda th, i, r, z: (r * se(th), z))
    posts_obj = posts.finish(smooth=35)

    rails = Part("fence_rails")
    for z, twist in ((0.43, 0.04), (0.84, -0.03)):
        path = [(lerp(-2.0, 2.0, k / 8), -0.112 + 0.006 * math.sin(math.pi * k / 4),
                 z - 0.022 * math.sin(math.pi * k / 8) + rng.uniform(-0.003, 0.003))
                for k in range(9)]
        sweep(rails, path, [0.085] * 9, 12, "wood", cap_start=True, cap_end=True,
              up_hint=Vector((0, twist, 1)), squash=(1.0, 0.36),
              radial_fn=lambda th, i, r: r * se(th))
    rails_obj = rails.finish(smooth=35)

    hw = Part("fence_hardware")
    for x in (-2.0, 0.0, 2.0):
        for z in (0.43, 0.84):
            zz = z - (0.022 if x == 0.0 else 0.0)
            box(hw, (x, -0.146, zz), (0.10, 0.008, 0.19), "metal_dark", bevel=0.003, segments=1)
            for dz in (-0.05, 0.05):
                sweep(hw, [(x, -0.150, zz + dz), (x, -0.162, zz + dz), (x, -0.166, zz + dz)],
                      [0.014, 0.014, 0.009], 6, "metal", cap_end=True, up_hint=Vector((0, 0, 1)))
    hw_obj = hw.finish(smooth=40)
    return join_objects([posts_obj, rails_obj, hw_obj], "fence_segment")


def mat_col(name):
    """Linear RGB of a material's authored colour (to paint flat-coloured parts of VC props)."""
    return hexcol(MATERIALS[name]["color"])


def shade(c, ao, k=0.55):
    """Darken a colour by baked AO (``k`` = how much a fully occluded corner darkens)."""
    return scale_col(c, (1.0 - k) + k * ao)


def bake_curvature(obj):
    """Per-vertex convexity in [-1, 1]: + on ridges / rims, - in creases (normalised)."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.normal_update()
    vals = []
    for v in bm.verts:
        acc, n = 0.0, 0
        for e in v.link_edges:
            d = e.other_vert(v).co - v.co
            ln = d.length
            if ln > 1e-9:
                acc -= v.normal.dot(d) / ln
                n += 1
        vals.append(acc / n if n else 0.0)
    bm.free()
    mags = sorted(abs(x) for x in vals)
    ref = (mags[int(len(mags) * 0.95)] if mags else 1.0) or 1.0
    return [max(-1.0, min(1.0, x / ref)) for x in vals]


def sphere(part, center, radius, mat, segs=16, rings=10, matrix=None):
    """UV sphere (``radius`` may be a 3-tuple -> ellipsoid), scaled, then ``matrix``, then moved.

    Built with lathe() rather than bmesh.ops.create_uvsphere, whose pole welding gives a
    run-to-run varying vertex order (the exported .glb would not be byte-reproducible)."""
    r = tuple(radius) if isinstance(radius, (tuple, list, Vector)) else (radius,) * 3
    M = (Matrix.Translation(Vector(center)) @ (matrix or Matrix.Identity(4)) @
         Matrix.Diagonal((r[0], r[1], r[2], 1.0)))
    prof = [(math.sin(math.pi * k / rings), -math.cos(math.pi * k / rings)) for k in range(rings + 1)]
    prof[0], prof[-1] = (0.0, -1.0), (0.0, 1.0)
    lathe(part, prof, segs, mat, matrix=M)


def loft(part, section, rings, mat, cap_start=True, cap_end=True, matrix=None):
    """Loft a CCW 2D ``section`` through ``rings`` = [(scale_x, scale_y, z, off_x, off_y)].

    A ring with zero scale becomes a single apex vertex.  Faces point outwards."""
    bm = part.bm
    M = matrix or Matrix.Identity(4)
    idx = part.mi(mat)
    vr = []
    for sx, sy, z, ox, oy in rings:
        if sx < 1e-6 and sy < 1e-6:
            vr.append([bm.verts.new(M @ Vector((ox, oy, z)))])
        else:
            vr.append([bm.verts.new(M @ Vector((x * sx + ox, y * sy + oy, z))) for x, y in section])
    n = len(section)
    for a, b in zip(vr, vr[1:]):
        for j in range(n):
            j2 = (j + 1) % n
            if len(a) == 1:
                vs = (a[0], b[j2], b[j])
            elif len(b) == 1:
                vs = (a[j], a[j2], b[0])
            else:
                vs = (a[j], a[j2], b[j2], b[j])
            bm.faces.new(vs).material_index = idx
    if cap_start and len(vr[0]) > 1:
        bm.faces.new(list(reversed(vr[0]))).material_index = idx
    if cap_end and len(vr[-1]) > 1:
        bm.faces.new(vr[-1]).material_index = idx
    return vr


def rounded_box(part, center, size, radius, mat, cuts=3, segments=2, matrix=None):
    """Box whose faces are subdivided (``cuts``) so it can be displaced, with rounded edges."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=Vector(size), verts=bm.verts)
    if cuts:
        bmesh.ops.subdivide_edges(bm, edges=list(bm.edges), cuts=cuts, use_grid_fill=True)
    sharp = [e for e in bm.edges if e.is_manifold and e.calc_face_angle(0.0) > 1.0]
    bmesh.ops.bevel(bm, geom=sharp, offset=radius, offset_type="OFFSET", profile_type="SUPERELLIPSE",
                    segments=segments, profile=0.5, affect="EDGES", clamp_overlap=True)
    M = Matrix.Translation(Vector(center)) @ (matrix or Matrix.Identity(4))
    bmesh.ops.transform(bm, matrix=M, verts=bm.verts)
    idx = part.mi(mat)
    for f in bm.faces:
        f.material_index = idx
    part.merge(bm)


def densify(profile, max_len):
    """Insert points so no profile edge is longer than ``max_len`` (for vertex-colour bands)."""
    out = [profile[0]]
    for (r0, z0), (r1, z1) in zip(profile, profile[1:]):
        n = max(1, int(math.ceil(math.hypot(r1 - r0, z1 - z0) / max_len)))
        for k in range(1, n + 1):
            out.append((lerp(r0, r1, k / n), lerp(z0, z1, k / n)))
    return out


def bezier(p0, p1, p2, p3, n):
    """``n`` points on a cubic Bezier (endpoints included)."""
    p0, p1, p2, p3 = (Vector(p) for p in (p0, p1, p2, p3))
    pts = []
    for k in range(n):
        t = k / (n - 1)
        u = 1.0 - t
        pts.append(p0 * u ** 3 + p1 * (3 * u * u * t) + p2 * (3 * u * t * t) + p3 * t ** 3)
    return pts


def fillet(points, radius, n=3):
    """Round the inner corners of a polyline with small arcs (neon tube bends)."""
    pts = [Vector(p) for p in points]
    out = [pts[0]]
    for a, b, c in zip(pts, pts[1:], pts[2:]):
        da, dc = (a - b), (c - b)
        r = min(radius, da.length * 0.45, dc.length * 0.45)
        p0, p1 = b + da.normalized() * r, b + dc.normalized() * r
        for k in range(n + 1):
            t = k / n
            out.append(p0 * (1 - t) ** 2 + b * (2 * t * (1 - t)) + p1 * t * t)
    out.append(pts[-1])
    return out


def blossom(part, center, normal, radius, mat, rng, petals=5, segs=15):
    """Small five-petal flower (same construction as the bush blossoms)."""
    M = (Matrix.Translation(Vector(center)) @
         Vector(normal).normalized().to_track_quat("Z", "Y").to_matrix().to_4x4() @
         Matrix.Rotation(rng.uniform(0, TAU), 4, "Z"))

    def fn(th, i, r, z):
        return r * (0.45 + 0.55 * abs(math.cos(petals * 0.5 * th))), z
    lathe(part, [(0.0, -0.16 * radius), (radius, 0.0), (0.0, 0.3 * radius)], segs, mat,
          radial_fn=fn, matrix=M)


def frond(part, spine, width_fn, cols, mat, rows_u=(-1.0, -0.3, 0.0, 0.3, 1.0), fold=0.5,
          zig=0.6, notch=0.45, thickness=0.01, min_width=0.006, twist=0.0):
    """Leaf blade along ``spine(s)`` (s in 0..1).

    Rows run across the blade (edge ... midrib ... edge); the edge rows zig-zag (even columns
    are leaflet tips pushed forward, odd columns are notches), and the blade is folded so the
    leaflets hang below the midrib by ``fold`` x width.  Built as a closed thin ``sheet``."""
    eps = 1e-3
    frames = []
    for c in range(cols):
        s = c / (cols - 1)
        p = spine(s)
        t = (spine(min(1.0, s + eps)) - spine(max(0.0, s - eps))).normalized()
        side = t.cross(Vector((0.0, 0.0, 1.0)))
        side = side.normalized() if side.length > 1e-4 else Vector((1.0, 0.0, 0.0))
        up = side.cross(t).normalized()
        if twist:
            q = Matrix.Rotation(twist * s, 3, t)
            side, up = q @ side, q @ up
        frames.append((s, p, t, side, up))
    seg_len = [(frames[min(c + 1, cols - 1)][1] - frames[max(c - 1, 0)][1]).length * 0.5
               for c in range(cols)]
    grid = []
    for u in rows_u:
        row = []
        edge = abs(abs(u) - 1.0) < 1e-6
        for c, (s, p, t, side, up) in enumerate(frames):
            w = max(width_fn(s), min_width)
            wf, fwd = 1.0, 0.0
            if edge and 0 < c < cols - 1:
                if c % 2 == 0:
                    fwd = zig * seg_len[c] * (1.0 - s)
                else:
                    wf = notch
            row.append(p + side * (u * wf * w) - up * (abs(u) ** 1.3 * fold * w * wf) + t * fwd)
        grid.append(row)
    sheet(part, grid, thickness, mat)


CACTUS = [(0.0, hexcol("#173d26")), (0.35, hexcol("#2a6234")), (0.70, hexcol("#4a8c3f")),
          (1.0, hexcol("#9cc86a"))]
PAD = [(0.0, hexcol("#26502c")), (0.45, hexcol("#4f8c45")), (0.8, hexcol("#7fb35a")),
       (1.0, hexcol("#bcd889"))]


def rib_profile(n, depth):
    """Cross-section multiplier for ribbed cacti: rounded ridges, narrow V grooves.
    Use 4 x n segments (phase 0) so ridges and grooves both get a vertex."""
    def fn(th):
        return 1.0 - depth + depth * math.sqrt(abs(math.cos(n * th * 0.5)))
    return fn


def cactus_arm(part, base_z, azimuth, reach, rise, r0, ribs, sides, mat="cactus"):
    """Saguaro arm: leaves the trunk with a slight droop, elbows up, rises, ends in a dome."""
    d = Vector((math.cos(azimuth), math.sin(azimuth), 0.0))
    up = Vector((0.0, 0.0, 1.0))
    k = reach / 0.735
    pts, radii = [], []
    for o, u, rr in [(0.0, 0.0, 0.95), (0.28, -0.05, 1.0), (0.48, -0.03, 1.0), (0.63, 0.07, 1.02),
                     (0.715, 0.23, 1.03), (0.74, 0.45, 1.02)]:
        pts.append(d * (o * k) + up * (base_z + u))
        radii.append(r0 * rr)
    x_end = 0.74 * k
    n_up = max(2, round((rise - 0.45) / 0.33))
    for j in range(1, n_up + 1):
        z = 0.45 + (rise - 0.45) * j / n_up
        pts.append(d * x_end + up * (base_z + z))
        radii.append(r0 * lerp(1.02, 0.96, j / n_up))
    rt = radii[-1]
    for f, rf in [(0.35, 0.94), (0.70, 0.71), (0.92, 0.39), (1.0, 0.08)]:
        pts.append(d * x_end + up * (base_z + rise + rt * f))
        radii.append(rt * rf)
    sweep(part, pts, radii, sides, mat, cap_end=True, up_hint=up,
          radial_fn=lambda th, i, r: r * ribs(th))
    return d * x_end + up * (base_z + rise + rt)


def cactus_color(s, curv, palette=CACTUS, seed=0.0):
    t = 0.10 + 0.50 * s.ao ** 1.3 + 0.14 * s.normal.z + 0.26 * curv + 0.06 * nz(s.co, 2.0, seed)
    c = ramp(palette, t)
    c = mix(c, hexcol("#e9dfae"), 0.38 * smoothstep(0.25, 0.9, curv))
    return c


def flower_color(s, centres, petal=("#fff6e3", "#ffe08a"), heart="#ffb21c", r_heart=0.022):
    k = min(range(len(centres)), key=lambda j: (s.co - centres[j]).length_squared)
    if (s.co - centres[k]).length < r_heart:
        return hexcol(heart)
    return hexcol(petal[k % len(petal)])


def build_cactus_a():
    """Saguaro (~4.7 m): ribbed column, two elbowed arms, blossoms on the crowns."""
    rng = random.Random(41)
    body = Part("saguaro")
    ribs = rib_profile(10, 0.15)
    prof = [(0.30, -0.10), (0.315, 0.15), (0.335, 0.6), (0.345, 1.4), (0.345, 2.3), (0.335, 3.1),
            (0.32, 3.7), (0.30, 4.08), (0.265, 4.34), (0.205, 4.52), (0.125, 4.62), (0.0, 4.66)]

    def trunk_fn(th, i, r, z):
        k = 1.0 + (ribs(th) - 1.0) * (1.0 - 0.6 * smoothstep(4.3, 4.66, z))
        wob = 1.0 + 0.025 * nz((math.cos(th), math.sin(th), z * 0.6), 1.0, 2.0)
        return r * k * wob, z
    lathe(body, prof, 40, "cactus", radial_fn=trunk_fn)
    arm_ribs = rib_profile(8, 0.15)
    tips = [Vector((0, 0, 4.66))]
    tips.append(cactus_arm(body, 1.75, 0.15, 0.80, 1.55, 0.205, arm_ribs, 32))
    tips.append(cactus_arm(body, 2.55, 3.45, 0.64, 1.02, 0.18, arm_ribs, 32))
    body_obj = body.finish()

    flowers = Part("saguaro_flowers")
    centres = []
    for (dx, dy), tip, dome in [((0.07, 0.03), 0, 0.30), ((-0.07, 0.06), 0, 0.30),
                                ((0.01, -0.09), 0, 0.30), ((0.04, 0.02), 1, 0.19),
                                ((-0.03, -0.04), 2, 0.17)]:
        c = tips[tip] + Vector((dx, dy, -(dx * dx + dy * dy) / (2 * dome) - 0.005))
        n = Vector((dx / dome, dy / dome, 1.0))
        blossom(flowers, c, n, 0.065, "flowers", rng)
        centres.append(c)
    flowers_obj = flowers.finish(smooth=70)

    obj = join_objects([body_obj, flowers_obj], "cactus_a")
    ao = bake_ao(obj, samples=24, max_dist=1.0)
    curv = bake_curvature(obj)

    def color(s):
        if s.mat == "flowers":
            return flower_color(s, centres)
        c = cactus_color(s, curv[s.index], seed=3.0)
        return mix(c, hexcol("#8c7c52"), 0.65 * (1.0 - smoothstep(0.0, 0.5, s.co.z)))

    paint(obj, color, ao)
    return obj


def build_cactus_b():
    """~1.2 m desert cluster: golden barrel cactus, a small barrel and a prickly-pear clump."""
    rng = random.Random(52)
    p = Part("cactus_b")
    bprof = [(0.20, -0.06), (0.27, 0.04), (0.31, 0.16), (0.315, 0.30), (0.285, 0.43), (0.21, 0.52),
             (0.11, 0.565), (0.0, 0.575)]
    barrels = [((-0.32, 0.06), 1.0, 12, 0.0), ((-0.66, -0.30), 0.6, 10, 1.0)]
    for (bx, by), sc, n_ribs, seed in barrels:
        ribs = rib_profile(n_ribs, 0.13)

        def barrel_fn(th, i, r, z, ribs=ribs, seed=seed):
            return r * ribs(th) * (1.0 + 0.03 * nz((math.cos(th), math.sin(th), z), 1.3, seed)), z
        M = Matrix.Translation((bx, by, 0.0)) @ Matrix.Scale(sc, 4)
        lathe(p, bprof, 4 * n_ribs, "cactus", radial_fn=barrel_fn, matrix=M)

    pad_info = []

    def pad(top, tilt, yaw, size):
        R = Matrix.Rotation(yaw, 4, "Z") @ Matrix.Rotation(tilt, 4, "Y")
        centre = top + (R @ Vector((0.0, 0.0, size[2] * 0.84)))
        sphere(p, centre, size, "cactus", 12, 7, matrix=R)
        pad_info.append((centre, R, size))
        return centre + (R @ Vector((0.0, 0.0, size[2] * 0.93)))

    a = pad(Vector((0.36, 0.08, -0.06)), 0.10, 0.45, (0.25, 0.065, 0.31))
    b = pad(a, -0.38, 0.62, (0.21, 0.06, 0.27))
    c = pad(a, 0.55, 0.30, (0.19, 0.055, 0.25))
    pad(b, -0.12, 0.95, (0.16, 0.05, 0.20))
    pad(c, 0.80, 0.10, (0.13, 0.045, 0.17))
    f = pad(Vector((0.66, -0.30, -0.06)), -0.62, -0.55, (0.20, 0.06, 0.25))
    pad(f, -1.05, -0.35, (0.15, 0.05, 0.19))
    fruits = []
    for k, xs in [(3, (-0.08, 0.06)), (4, (0.03,)), (1, (0.12,)), (6, (-0.05, 0.07))]:
        centre, R, size = pad_info[k]
        for x in xs:
            lz = size[2] * math.sqrt(max(0.0, 1.0 - (x / size[0]) ** 2)) * 0.97
            pos = centre + (R @ Vector((x, 0.0, lz)))
            sphere(p, pos, (0.042, 0.042, 0.058), "flowers", 8, 5, matrix=R)
            fruits.append(pos)
    flower_c = []
    for (bx, by), sc, _, _ in barrels:
        for dx, dy in ((0.05, 0.02), (-0.04, -0.05)) if sc > 0.8 else ((0.0, 0.02),):
            ctr = Vector((bx + dx, by + dy, 0.57 * sc))
            blossom(p, ctr, Vector((dx, dy, 0.25)), 0.06 * sc + 0.02, "flowers", rng)
            flower_c.append(ctr)
    obj = p.finish(smooth=70)
    obj.name = "cactus_b"
    ao = bake_ao(obj, samples=24, max_dist=0.6)
    curv = bake_curvature(obj)

    def color(s):
        if s.mat == "flowers":
            if fruits and min((s.co - q).length for q in fruits) < 0.07:
                return ramp([(0, hexcol("#6d0f3a")), (0.6, hexcol("#c2185b")), (1, hexcol("#ff6f9c"))],
                            0.25 + 0.6 * s.ao + 0.15 * s.normal.z)
            return flower_color(s, flower_c, petal=("#ffd23a", "#ffb81c"), heart="#ff7a1c", r_heart=0.02)
        in_barrel = any(math.hypot(s.co.x - bx, s.co.y - by) < 0.36 * sc + 0.02
                        for (bx, by), sc, _, _ in barrels)
        if in_barrel:
            col = cactus_color(s, curv[s.index], seed=5.0)
            return mix(col, hexcol("#f0cf6a"), 0.45 * smoothstep(0.15, 0.8, curv[s.index]))
        t = 0.12 + 0.55 * s.ao ** 1.2 + 0.18 * s.normal.z + 0.08 * nz(s.co, 3.0, 9.0)
        col = ramp(PAD, t)
        return mix(col, hexcol("#c9b25a"), 0.35 * smoothstep(0.3, 1.0, curv[s.index]))

    paint(obj, color, ao)
    return obj


PALM = [(0.0, hexcol("#173f22")), (0.35, hexcol("#2a6a2c")), (0.65, hexcol("#4a9a36")),
        (0.85, hexcol("#86c44a")), (1.0, hexcol("#cbe27c"))]
PALM_BARK = [(0.0, hexcol("#3f3124")), (0.45, hexcol("#7a6448")), (0.8, hexcol("#a88f6b")),
             (1.0, hexcol("#cdb894"))]


def build_palm_tree():
    """~8.6 m coconut palm: leaning, ring-segmented trunk, arched fronds, coconut bunch."""
    rng = random.Random(61)
    H, lean = 7.6, 1.75

    def axis(z):
        u = clamp01(z / H)
        return Vector((lean * (1.0 - (1.0 - u) ** 2.2), 0.22 * math.sin(u * 2.4), z))

    pts, radii = [], []
    for z, r in [(-0.15, 0.42), (0.04, 0.37), (0.20, 0.30)]:
        pts.append(axis(z))
        radii.append(r)
    z0, nseg = 0.30, 17
    seg_h = (H - z0) / nseg
    for k in range(nseg):
        zz = z0 + k * seg_h
        rbase = lerp(0.235, 0.165, (zz / H) ** 0.8)
        for f, m in ((0.0, 0.93), (0.72, 1.0), (0.93, 1.085)):
            pts.append(axis(zz + f * seg_h))
            radii.append(rbase * m)
    top = axis(H)
    for dz, r in [(0.0, 0.18), (0.25, 0.215), (0.45, 0.20), (0.58, 0.12), (0.62, 0.02)]:
        pts.append(top + Vector((0, 0, dz)))
        radii.append(r)

    def trunk_fn(th, i, r):
        if i < 3:
            return r * (1.0 + 0.16 * (0.5 + 0.5 * math.cos(5 * th + 0.7)) ** 2)
        return r * (1.0 + 0.02 * math.cos(3 * th + i))
    trunk = Part("palm_trunk")
    sweep(trunk, pts, radii, 12, "bark", cap_end=True, radial_fn=trunk_fn)
    crown = top + Vector((0, 0, 0.42))
    nuts = []
    for k in range(4):
        a = 0.6 + k * TAU / 4 + rng.uniform(-0.3, 0.3)
        c = top + Vector((math.cos(a) * 0.24, math.sin(a) * 0.24, 0.12 + rng.uniform(-0.08, 0.06)))
        R = Matrix.Rotation(rng.uniform(-0.4, 0.4), 4, "X") @ Matrix.Rotation(rng.uniform(-0.4, 0.4), 4, "Y")
        sphere(trunk, c, (0.13, 0.13, 0.15), "bark", 10, 7, matrix=R)
        nuts.append(c)
    trunk_obj = trunk.finish()

    leaves = Part("palm_fronds")
    old = []
    fronds = []
    n_main = 11
    for k in range(n_main):
        az = k * TAU / n_main + rng.uniform(-0.15, 0.15)
        is_old = k in (2, 7)
        elev = rng.uniform(0.02, 0.12) if is_old else rng.uniform(0.2, 0.75)
        fronds.append((az, elev, rng.uniform(3.6, 4.3), rng.uniform(0.68, 0.8),
                       0.9 if is_old else rng.uniform(0.5, 0.8), 19, is_old))
    for k in range(2):
        az = k * TAU / 2 + rng.uniform(0, 1)
        fronds.append((az, rng.uniform(1.1, 1.3), rng.uniform(1.8, 2.2), 0.42, 0.45, 13, False))
    for az, elev, length, width, droop, cols, is_old in fronds:
        d = Vector((math.cos(az), math.sin(az), 0.0))
        base = crown + d * 0.10

        def spine(s, d=d, base=base, elev=elev, length=length, droop=droop):
            h = length * s * math.cos(elev) * (1.0 - 0.12 * s)
            v = length * (s * math.sin(elev) - droop * s * s)
            return base + d * h + Vector((0, 0, v))

        def wfn(s, width=width):
            return width * smoothstep(0.05, 0.34, s) * (1.0 - s ** 1.8) ** 0.7
        frond(leaves, spine, wfn, cols, "leaves", fold=0.55, zig=0.7, notch=0.42, thickness=0.012,
              min_width=0.016, twist=rng.uniform(-0.3, 0.3))
        if is_old:
            old.append(d)
    leaves_obj = leaves.finish(smooth=70)

    obj = join_objects([trunk_obj, leaves_obj], "palm_tree")
    ao = bake_ao(obj, samples=24, max_dist=1.4)
    curv = bake_curvature(obj)

    def color(s):
        if s.mat == "bark":
            if min((s.co - c).length for c in nuts) < 0.17:
                t = 0.2 + 0.6 * s.ao + 0.2 * s.normal.z
                return ramp([(0, hexcol("#2f2a12")), (0.5, hexcol("#6b6a22")), (1, hexcol("#a8a440"))], t)
            if s.co.z > H - 0.05:
                return shade(mix(hexcol("#6f6a36"), hexcol("#9a8c52"), s.normal.z * 0.5 + 0.5), s.ao)
            t = 0.28 + 0.42 * s.ao + 0.30 * curv[s.index] + 0.08 * nz(s.co, 4.0, 2.0)
            return ramp(PALM_BARK, t)
        rel = s.co - crown
        tip = clamp01(rel.length / 4.0)
        t = 0.08 + 0.5 * s.ao ** 1.3 + 0.14 * (s.normal.z * 0.5 + 0.5) + 0.22 * tip + 0.10 * curv[s.index]
        c = ramp(PALM, t)
        h = Vector((rel.x, rel.y, 0.0))
        if old and h.length > 0.2 and rel.z < 0.3:
            h.normalize()
            if max(h.dot(d) for d in old) > 0.97:
                c = mix(c, hexcol("#a89a4a"), 0.3 + 0.35 * tip)
        return c

    paint(obj, color, ao)
    return obj


PINE_COLD = [(0.0, hexcol("#0e2a26")), (0.35, hexcol("#173f34")), (0.62, hexcol("#245a44")),
             (0.85, hexcol("#3a7652")), (1.0, hexcol("#6c9a6a"))]
SNOW = [(0.0, hexcol("#7f97c2")), (0.45, hexcol("#c3d4ec")), (0.8, hexcol("#eaf2fb")),
        (1.0, hexcol("#ffffff"))]
# simplified tier (its top is hidden under the snow cap) and the snow cap itself, both in
# (radial fraction, height fraction) like PINE_TIER, walked from the inner underside outwards
PINE_TIER_SNOW = [(0.00, 0.30), (0.30, 0.17), (0.62, 0.07), (0.86, 0.015), (0.98, 0.045),
                  (1.00, 0.12), (0.93, 0.21), (0.75, 0.37), (0.00, 0.95)]
SNOW_CAP = [(0.55, 0.50), (0.80, 0.28), (0.895, 0.215), (0.935, 0.255), (0.87, 0.335),
            (0.72, 0.45), (0.50, 0.64), (0.25, 0.86), (0.00, 1.04)]


def snow_color(s, seed=0.0):
    t = 0.18 + 0.55 * s.ao ** 1.2 + 0.25 * s.normal.z + 0.05 * nz(s.co, 1.5, seed)
    return ramp(SNOW, t)


def build_tree_pine_snow():
    """~8.5 m pine (same silhouette family as tree_pine) with a snow cap on every tier."""
    rng = random.Random(17)
    trunk = Part("snowpine_trunk")
    lathe(trunk, [(0.34, -0.08), (0.30, 0.10), (0.235, 0.35), (0.20, 0.9), (0.17, 2.0),
                  (0.13, 3.6), (0.09, 5.2), (0.05, 6.8), (0.0, 7.3)],
          12, "bark", radial_fn=root_flare(5, 0.75, 0.65, 0.4))
    displace(trunk.bm, 0.015, 5.0, seed=1)
    def drift(th, i, r, z):
        return r * (1.0 + 0.12 * nz((math.cos(th), math.sin(th), 0.0), 1.6, 4.0)), z
    lathe(trunk, [(0.0, -0.06), (1.35, -0.06), (1.25, 0.03), (0.95, 0.10), (0.6, 0.15),
                  (0.32, 0.17), (0.0, 0.17)], 28, "snow", radial_fn=drift)
    trunk_obj = trunk.finish()

    foliage = Part("snowpine_foliage")
    snow = Part("snowpine_snow")
    tiers = [(1.65, 4.20, 2.50, 9, 44), (2.80, 5.30, 2.08, 8, 40), (3.92, 6.35, 1.67, 8, 36),
             (5.00, 7.38, 1.25, 7, 30), (6.05, 8.45, 0.83, 6, 24)]
    for ti, (z0, z1, radius, lobes, segs) in enumerate(tiers):
        phase = rng.uniform(0, TAU)
        h = z1 - z0
        amp = [rng.uniform(0.75, 1.25) for _ in range(lobes)]
        deform = _pine_deform(radius, lobes, phase, amp, h)
        tilt = Matrix.Rotation(rng.uniform(-0.05, 0.05), 4, "X") @ Matrix.Rotation(rng.uniform(-0.05, 0.05), 4, "Y")
        M = Matrix.Translation((0, 0, z0)) @ tilt @ Matrix.Translation((0, 0, -z0))
        lathe(foliage, [(s * radius, z0 + t * h) for s, t in PINE_TIER_SNOW], segs, "leaves_dark",
              radial_fn=deform, matrix=M)

        def snow_fn(th, i, r, z, deform=deform, h=h, ti=ti):
            r2, z2 = deform(th, i, r, z)
            if 1 <= i <= 3:
                drip = clamp01(0.5 + 1.3 * nz((math.cos(th) * 2.2, math.sin(th) * 2.2, ti * 3.7), 1.0, 6.0)) ** 2
                z2 -= h * 0.05 * drip * (1.0 if i > 1 else 0.6)
                r2 *= 1.0 + 0.015 * drip
            return r2, z2
        lathe(snow, [(s * radius, z0 + t * h) for s, t in SNOW_CAP], segs, "snow",
              radial_fn=snow_fn, matrix=M)
    displace(foliage.bm, 0.05, 1.1, seed=2)
    displace(snow.bm, 0.03, 1.6, seed=3)
    foliage_obj = foliage.finish()
    snow_obj = snow.finish()

    obj = join_objects([trunk_obj, foliage_obj, snow_obj], "tree_pine_snow")
    ao = bake_ao(obj, samples=28, max_dist=2.4)

    def color(s):
        if s.mat == "bark":
            return bark_color(s)
        if s.mat == "snow":
            return snow_color(s, 5.0)
        return foliage_color(PINE_COLD, s, warm=0.0, seed=4.0)

    paint(obj, color, ao)
    return obj


def build_snowman():
    """~1.85 m snowman: three lumpy snowballs, coal face, carrot nose, twig arms, striped
    scarf and a little top hat.  Faces -Y."""
    rng = random.Random(23)
    body = Part("snowman_body")
    zs = 0.9
    prof = [(0.0, -0.03), (0.30, -0.02), (0.43, 0.08), (0.50, 0.25), (0.52, 0.42), (0.49, 0.60),
            (0.40, 0.76), (0.27, 0.86), (0.30, 0.93), (0.37, 1.04), (0.38, 1.14), (0.34, 1.26),
            (0.24, 1.35), (0.20, 1.39), (0.24, 1.46), (0.26, 1.55), (0.24, 1.65), (0.17, 1.73),
            (0.08, 1.775), (0.0, 1.785)]
    lathe(body, [(r, z * zs) for r, z in prof], 28, "snow")
    displace(body.bm, 0.016, 2.6, seed=1)
    lathe(body, [(0.0, -0.06), (0.85, -0.06), (0.78, 0.02), (0.6, 0.09), (0.45, 0.12), (0.0, 0.12)],
          24, "snow", radial_fn=lambda th, i, r, z: (r * (1 + 0.1 * nz((math.cos(th), math.sin(th), 0), 1.5, 2)), z))
    body_obj = body.finish()

    acc = Part("snowman_acc")
    head_c = Vector((0.0, 0.0, 1.395))
    coal = []

    def on_head(x, z, out=0.255):
        d = Vector((x, -1.0, z)).normalized()
        return head_c + d * out, d

    for sx in (-1, 1):
        pos, d = on_head(sx * 0.36, 0.30)
        sphere(acc, pos, (0.03, 0.03, 0.033), "paint_black", 8, 5)
        coal.append(pos)
    for k in range(5):
        a = (k - 2) * 0.24
        pos, d = on_head(math.sin(a) * 0.9, -0.33 - 0.05 * math.cos(a * 2.2))
        sphere(acc, pos, 0.018, "paint_black", 6, 4)
        coal.append(pos)
    mid_c, mid_r = Vector((0.0, 0.0, 1.03 * zs + 0.02)), 0.375
    for z in (0.16, -0.06, -0.27):
        d = Vector((0.0, -1.0, z)).normalized()
        sphere(acc, mid_c + d * (mid_r * (1.0 - 0.06 * abs(z))), 0.036, "paint_black", 8, 5)
    nose_base, _ = on_head(0.0, 0.05, 0.24)
    M = Matrix.Translation(nose_base) @ Matrix.Rotation(math.pi / 2 + 0.12, 4, "X")
    lathe(acc, [(0.0, -0.02), (0.042, 0.0), (0.040, 0.05), (0.030, 0.12), (0.016, 0.19),
                (0.0, 0.235)], 10, "paint_orange",
          radial_fn=lambda th, i, r, z: (r * (1 + 0.08 * math.cos(3 * th + z * 30)), z), matrix=M)
    hat = [(0.0, 0.0), (0.24, 0.0), (0.275, 0.008), (0.285, 0.022), (0.27, 0.034), (0.19, 0.036),
           (0.165, 0.05), (0.165, 0.075), (0.168, 0.135), (0.172, 0.27), (0.165, 0.29), (0.0, 0.295)]
    mats = ["paint_black"] * (len(hat) - 1)
    mats[7] = "fabric_a"
    M = (Matrix.Translation((0.02, 0.01, 1.53)) @ Matrix.Rotation(0.13, 4, "Y") @
         Matrix.Rotation(0.07, 4, "X"))
    lathe(acc, hat, 22, mats=mats, matrix=M)
    for sx in (-1, 1):
        start = Vector((sx * 0.25, 0.02, 1.0))
        pts = [start, start + Vector((sx * 0.20, 0.0, 0.08)), start + Vector((sx * 0.40, 0.03, 0.20)),
               start + Vector((sx * 0.55, 0.02, 0.33))]
        sweep(acc, pts, [0.026, 0.022, 0.016, 0.008], 6, "bark", cap_end=True)
        f0 = pts[2]
        sweep(acc, [f0, f0 + Vector((sx * 0.08, -0.03, 0.12)), f0 + Vector((sx * 0.10, -0.04, 0.2))],
              [0.012, 0.009, 0.004], 5, "bark", cap_end=True)
        f1 = pts[1]
        sweep(acc, [f1, f1 + Vector((sx * 0.10, 0.03, -0.06)), f1 + Vector((sx * 0.16, 0.04, -0.07))],
              [0.011, 0.008, 0.004], 5, "bark", cap_end=True)
    acc_obj = acc.finish(smooth=50)

    scarf = Part("snowman_scarf")
    zc = 1.245
    ring = [Vector((math.cos(a) * 0.212, math.sin(a) * 0.212, zc + 0.012 * math.sin(2 * a)))
            for a in (-math.pi / 2 + TAU * k / 24 for k in range(25))]
    sweep(scarf, ring, [0.06] * 25, 8, "fabric_a", squash=(1.0, 0.62))
    sphere(scarf, (0.09, -0.225, zc - 0.01), (0.065, 0.05, 0.06), "fabric_a", 10, 6)
    for off, length in ((0.0, 0.36), (0.08, 0.30)):
        grid = []
        pts = [Vector((0.09 + off, -0.24, zc - 0.03)), Vector((0.11 + off, -0.32, zc - 0.11)),
               Vector((0.125 + off, -0.385, zc - 0.21)), Vector((0.14 + off, -0.405, zc - 0.30)),
               Vector((0.15 + off, -0.40, zc - 0.30 - (length - 0.30) * 1.0 - 0.06))]
        for side in (-1, 1):
            row = []
            for q in pts:
                radial = Vector((q.x, q.y, 0.0)).normalized()
                across = Vector((-radial.y, radial.x, 0.0))
                row.append(q + across * (0.055 * side))
            grid.append(row)
        sheet(scarf, grid, 0.022, "fabric_a")
    scarf_obj = scarf.finish(smooth=60)

    obj = join_objects([body_obj, acc_obj, scarf_obj], "snowman")
    ao = bake_ao(obj, samples=28, max_dist=0.6)

    def color(s):
        if s.mat == "snow":
            return snow_color(s, 2.0)
        if s.mat == "fabric_a":
            fc = s.face_center
            stripe = math.sin(math.atan2(fc.y, fc.x) * 9.0) if fc.z > zc - 0.075 else math.sin(fc.z * 55.0)
            base = hexcol("#d8262b") if stripe > -0.35 else hexcol("#f6efe0")
            if (fc - Vector((0.02, 0.01, 1.53))).length < 0.35 and fc.z > 1.55:
                base = hexcol("#c81f2a")
            return shade(base, s.ao, 0.6)
        if s.mat == "paint_black":
            return shade(hexcol("#1c1c22") if s.co.z > 1.5 and s.co.z < 1.83 and abs(s.co.y) < 0.2
                         else hexcol("#18181c"), s.ao, 0.4)
        if s.mat == "paint_orange":
            return shade(mix(hexcol("#ff7a1c"), hexcol("#e8501a"), 0.5 + 0.5 * nz(s.co, 40.0, 1.0)), s.ao, 0.4)
        return shade(bark_color(s), 1.0, 0.0)

    paint(obj, color, ao)
    return obj


CRYSTAL = [(0.0, hexcol("#0b2f6e")), (0.35, hexcol("#1a6fc0")), (0.7, hexcol("#46cdf0")),
           (0.9, hexcol("#a9f1ff")), (1.0, hexcol("#f2feff"))]
SLATE = [(0.0, hexcol("#1d2230")), (0.5, hexcol("#3a4256")), (0.85, hexcol("#5f6b84")),
         (1.0, hexcol("#8793aa"))]


def crystal_section(chamfer):
    """Hexagon with chamfered corners (12 points, CCW, unit radius)."""
    pts = []
    for k in range(6):
        a = k * TAU / 6
        for s in (-1, 1):
            pts.append((math.cos(a + s * chamfer), math.sin(a + s * chamfer)))
    return pts


def build_crystal_cluster():
    """~2.8 m cluster of chamfered hexagonal ice/crystal shards growing out of a slate rock."""
    rng = random.Random(31)
    shards = Part("crystal_shards")
    specs = [(2.75, 0.30, 0.0, 0.0, 0.10, 0.4)]
    for k in range(5):
        a = k * TAU / 5 + rng.uniform(-0.3, 0.3)
        specs.append((rng.uniform(1.3, 2.0), rng.uniform(0.17, 0.24), a, rng.uniform(0.22, 0.38),
                      rng.uniform(0.32, 0.55), a))
    for k in range(8):
        a = k * TAU / 8 + rng.uniform(-0.25, 0.25) + 0.3
        specs.append((rng.uniform(0.5, 1.0), rng.uniform(0.08, 0.14), a, rng.uniform(0.45, 0.72),
                      rng.uniform(0.6, 1.0), a))
    for k in range(4):
        a = k * TAU / 4 + rng.uniform(-0.4, 0.4) + 0.7
        specs.append((rng.uniform(0.25, 0.45), rng.uniform(0.05, 0.08), a, rng.uniform(0.85, 1.05),
                      rng.uniform(1.0, 1.25), a))
    tips = []
    for length, radius, az, dist, tilt, lean_az in specs:
        base = Vector((math.cos(az) * dist, math.sin(az) * dist, 0.12 - 0.2 * dist))
        direction = Vector((math.cos(lean_az) * math.sin(tilt), math.sin(lean_az) * math.sin(tilt),
                            math.cos(tilt)))
        M = (Matrix.Translation(base) @ direction.to_track_quat("Z", "Y").to_matrix().to_4x4() @
             Matrix.Rotation(rng.uniform(0, TAU), 4, "Z"))
        ox, oy = rng.uniform(-0.2, 0.2) * radius, rng.uniform(-0.2, 0.2) * radius
        sec = crystal_section(rng.uniform(0.09, 0.15))
        loft(shards, [(x * radius, y * radius) for x, y in sec],
             [(0.92, 0.92, -0.35, 0, 0), (0.98, 0.98, length * 0.36, 0, 0),
              (1.0, 1.0, length * 0.70, 0, 0), (0.0, 0.0, length, ox, oy)],
             "crystal", cap_start=True, matrix=M)
        tips.append((base, direction, length))
    shards_obj = shards.finish(smooth=25)

    rock = Part("crystal_rock")
    rock_chunk(rock, rng, (0.05, 0.0, 0.0), (1.9, 1.6, 0.55), n_planes=9, embed=0.1,
               mats=("rock", "rock"))
    rock_chunk(rock, rng, (-0.75, 0.55, 0.0), (0.8, 0.7, 0.35), n_planes=7, embed=0.08,
               mats=("rock", "rock"))
    rock_obj = rock.finish()
    decimate_to(rock_obj, 900)
    set_smooth(rock_obj, 40)

    obj = join_objects([shards_obj, rock_obj], "crystal_cluster")
    ao = bake_ao(obj, samples=24, max_dist=0.8)
    curv = bake_curvature(obj)

    def color(s):
        if s.mat == "crystal":
            best = None
            for base, d, length in tips:
                rel = s.co - base
                along = rel.dot(d)
                perp = (rel - d * along).length
                if best is None or perp < best[0]:
                    best = (perp, clamp01(along / length))
            t = 0.08 + 0.62 * best[1] ** 0.9 + 0.22 * max(0.0, curv[s.index]) + 0.12 * s.ao
            return ramp(CRYSTAL, t)
        t = 0.1 + 0.55 * s.ao ** 1.3 + 0.2 * s.normal.z + 0.15 * curv[s.index] + 0.08 * nz(s.co, 3.0, 4.0)
        c = ramp(SLATE, t)
        return mix(c, hexcol("#dbe8f6"), 0.75 * smoothstep(0.55, 0.85, s.normal.z + 0.15 * nz(s.co, 2.5, 7.0)) * s.ao)

    paint(obj, color, ao)
    return obj


DEADWOOD = [(0.0, hexcol("#2a2420")), (0.4, hexcol("#4f463f")), (0.7, hexcol("#7c7268")),
            (0.9, hexcol("#a69c8f")), (1.0, hexcol("#c9c0b2"))]


def build_tree_dead():
    """~6 m bare, twisted dead tree: fluted spiralling trunk, exposed roots, gnarled limbs."""
    rng = random.Random(77)
    wood = Part("dead_wood")

    def wander(start, d, length, n, bend, up_bias, seed):
        pts = [Vector(start)]
        d = Vector(d).normalized()
        p = Vector(start)
        step = length / (n - 1)
        for k in range(1, n):
            q = p * 0.9
            jit = Vector((nz(q, 1.0, seed), nz(q, 1.0, seed + 1.3), nz(q, 1.0, seed + 2.6)))
            d = (d + jit * bend + Vector((0.0, 0.0, up_bias))).normalized()
            p = p + d * step
            pts.append(p.copy())
        return pts

    def perpendicular(t, angle):
        a = t.orthogonal().normalized()
        b = t.cross(a).normalized()
        return a * math.cos(angle) + b * math.sin(angle)

    SIDES = [16, 10, 7, 5]
    LEN = [3.9, 2.3, 1.25, 0.6]
    BEND = [0.13, 0.36, 0.5, 0.6]
    UP = [0.06, 0.16, 0.10, 0.03]

    def branch(start, d, length, r0, level, n_children):
        n = max(3, int(length / 0.3) + 2)
        pts = wander(start, d, length, n, BEND[level], UP[level], rng.uniform(0, 100))
        radii = [max(r0 * (1.0 - 0.72 * (k / (n - 1)) ** 0.9), 0.008) for k in range(n)]
        if level == 0:
            def rf(th, i, r):
                z = pts[i].z
                flare = 0.75 * clamp01(1.0 - z / 0.9) ** 2 * (0.5 + 0.5 * math.cos(4 * th + 0.8)) ** 2
                return r * (1.0 + 0.11 * math.cos(5 * th + i * 0.55) + flare)
        else:
            def rf(th, i, r, level=level):
                return r * (1.0 + 0.08 * math.cos(3 * th + i * 0.8))
        sweep(wood, pts, radii, SIDES[level], "bark", cap_end=True, radial_fn=rf)
        if level >= 3:
            return
        frames = _frames(pts)
        for c in range(n_children):
            if level == 0:
                f = [0.97, 0.9, 0.66, 0.48][c]
            else:
                f = rng.uniform(0.35, 0.95)
            i = min(n - 1, max(1, int(round(f * (n - 1)))))
            t = frames[i][0]
            ang = rng.uniform(0.55, 0.95) if level < 2 else rng.uniform(0.5, 1.1)
            cd = (t * math.cos(ang) + perpendicular(t, c * TAU / n_children + rng.uniform(-0.6, 0.6)) * math.sin(ang))
            cr = radii[i] * (0.8 if level == 0 else 0.78)
            branch(pts[i], cd, LEN[level + 1] * rng.uniform(0.8, 1.15), cr, level + 1,
                   [3, 3, 3][level])

    branch(Vector((0.0, 0.0, -0.12)), Vector((0.05, 0.03, 1.0)), LEN[0], 0.32, 0, 4)
    for k in range(5):
        a = k * TAU / 5 + rng.uniform(-0.3, 0.3)
        d = Vector((math.cos(a), math.sin(a), 0.0))
        s = Vector((0.0, 0.0, 0.35))
        pts = [s + d * 0.05, s + d * 0.45 + Vector((0, 0, -0.18)), s + d * 0.85 + Vector((0, 0, -0.33)),
               s + d * 1.2 + Vector((0, 0, -0.5))]
        sweep(wood, pts, [0.13, 0.09, 0.055, 0.03], 7, "bark", cap_end=True)
    displace(wood.bm, 0.01, 6.0, seed=3)
    obj = wood.finish()
    obj.name = "tree_dead"
    ao = bake_ao(obj, samples=24, max_dist=1.2)
    curv = bake_curvature(obj)

    def color(s):
        streak = nz((s.co.x * 7.0, s.co.y * 7.0, s.co.z * 1.2), 1.0, 5.0)
        t = 0.18 + 0.5 * s.ao ** 1.2 + 0.18 * s.normal.z + 0.12 * streak + 0.18 * curv[s.index]
        t += 0.12 * smoothstep(0.5, 2.5, s.co.z)
        return ramp(DEADWOOD, t)

    paint(obj, color, ao)
    return obj


def cap_cut(bm, plane_no):
    """Close the open boundary loop(s) left by bisect_plane with n-gons facing -plane_no.

    Walks each loop from its lowest-coordinate vertex so the result is deterministic."""
    bm.verts.index_update()
    boundary = [e for e in bm.edges if e.is_boundary]
    nbr = {}
    for e in boundary:
        a, b = e.verts
        nbr.setdefault(a, []).append(b)
        nbr.setdefault(b, []).append(a)
    faces, used = [], set()
    for start in sorted(nbr, key=lambda v: (round(v.co.x, 6), round(v.co.y, 6), round(v.co.z, 6), v.index)):
        if start in used or len(nbr[start]) != 2:
            continue
        loop, prev, cur = [start], None, start
        while True:
            used.add(cur)
            options = [v for v in nbr[cur] if v is not prev]
            nxt = min(options, key=lambda v: v.index) if prev is None else options[0]
            if nxt is start or nxt in used:
                break
            loop.append(nxt)
            prev, cur = cur, nxt
        if len(loop) < 3:
            continue
        nrm = Vector()
        for a, b in zip(loop, loop[1:] + loop[:1]):
            nrm += a.co.cross(b.co)
        if nrm.dot(plane_no) > 0:
            loop.reverse()
        faces.append(bm.faces.new(loop))
    return faces


BASALT = [(0.0, hexcol("#100f12")), (0.4, hexcol("#242124")), (0.75, hexcol("#3f3a39")),
          (1.0, hexcol("#6e6560"))]


def build_rock_lava():
    """~2.6 m basalt boulder split open by glowing fissures (emissive ``lava`` faces + core)."""
    rng = random.Random(404)
    src = Part("lava_src")
    rock_chunk(src, rng, (0.0, 0.0, 0.0), (2.6, 2.2, 1.85), n_planes=13, embed=0.15, yaw=0.4)
    src_obj = src.finish()
    decimate_to(src_obj, 1900)
    bm_src = bmesh.new()
    bm_src.from_mesh(src_obj.data)
    planes = [(Vector((0.12, 0.05, 0.0)), Vector((0.82, 0.52, 0.10)).normalized()),
              (Vector((0.0, 0.0, 1.0)), Vector((0.18, -0.30, 1.0)).normalized()),
              (Vector((-0.5, -0.1, 0.0)), Vector((-0.45, 0.88, 0.0)).normalized())]
    gap = 0.075
    part = Part("rock_lava")
    rock_i, lava_i = part.mi("rock"), part.mi("lava")
    combos = [(1, 1, 0), (1, -1, 0), (-1, 1, 1), (-1, 1, -1), (-1, -1, 1), (-1, -1, -1)]
    for signs in combos:
        bm = bm_src.copy()
        for (co, no), sg in zip(planes, signs):
            if sg == 0:
                continue
            bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], dist=1e-5,
                                   plane_co=co, plane_no=no * sg, clear_inner=True)
            new = cap_cut(bm, no * sg)
            for f in new:
                f.material_index = lava_i
            if new:
                bmesh.ops.triangulate(bm, faces=new, quad_method="BEAUTY", ngon_method="BEAUTY")
        if not bm.verts:
            bm.free()
            continue
        for f in bm.faces:
            if f.material_index != lava_i:
                f.material_index = rock_i
        move = Vector((0.0, 0.0, 0.0))
        for (co, no), sg in zip(planes, signs):
            move += no * (sg * gap * 0.5)
        if move.z < 0:
            move.z *= 0.3
        centre = sum((v.co for v in bm.verts), Vector()) / len(bm.verts)
        R = (Matrix.Rotation(rng.uniform(-0.04, 0.04), 4, "X") @ Matrix.Rotation(rng.uniform(-0.04, 0.04), 4, "Y"))
        M = Matrix.Translation(centre + move) @ R @ Matrix.Translation(-centre)
        bmesh.ops.transform(bm, matrix=M, verts=bm.verts)
        part.merge(bm)
    bm_src.free()
    bpy.data.objects.remove(src_obj, do_unlink=True)
    # bend the straight fracture lines: one smooth warp field moves both sides of every crack
    # (three scalar samples: mathutils.noise.noise_vector is not reproducible between runs)
    for v in part.bm.verts:
        q = v.co * 1.4
        v.co += Vector((nz(q, 1.0, 21.0), nz(q, 1.0, 22.0), nz(q, 1.0, 23.0))) * 0.11
    pieces = part.finish(smooth=40)
    me = pieces.data
    lava_slot = [m.name for m in me.materials].index("lava")
    crack = [tuple(p.vertices) for p in me.polygons if p.material_index == lava_slot]
    crack_bvh = BVHTree.FromPolygons([v.co.copy() for v in me.vertices], crack)
    core = Part("lava_core")
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=2, radius=1.0)
    bmesh.ops.scale(bm, vec=(0.85, 0.7, 0.62), verts=bm.verts)
    bmesh.ops.translate(bm, vec=(0.0, 0.0, 0.62), verts=bm.verts)
    for f in bm.faces:
        f.material_index = core.mi("lava")
    core.merge(bm)
    obj = join_objects([pieces, core.finish()], "rock_lava")
    ao = bake_ao(obj, samples=24, max_dist=1.0)
    curv = bake_curvature(obj)

    def color(s):
        if s.mat == "lava":
            t = clamp01(0.5 + 0.5 * nz(s.co, 3.0, 2.0))
            return mix(hexcol("#ffcf3a"), hexcol("#ff4a0c"), t)
        hit = crack_bvh.find_nearest(s.co, 0.5)
        d = hit[3] if hit[0] is not None else 1.0
        heat = (1.0 - smoothstep(0.0, 0.32, d)) ** 2
        t = 0.12 + 0.5 * s.ao ** 1.2 + 0.25 * max(0.0, curv[s.index]) + 0.12 * s.normal.z
        t += 0.08 * nz(s.co, 4.0, 3.0)
        c = ramp(BASALT, t)
        c = mix(c, hexcol("#a8240a"), 0.85 * heat)
        return mix(c, hexcol("#ff6a1a"), 0.6 * heat ** 3)

    paint(obj, color, ao)
    return obj


STRATA = [(-9.0, "#c46b3c"), (3.0, "#b8582f"), (4.6, "#a84a29"), (5.6, "#d58a52"), (6.8, "#b2552f"),
          (7.7, "#9a4127"), (8.6, "#f0c08a"), (9.5, "#c0623a"), (10.6, "#dc9259"), (11.8, "#b35a33"),
          (12.8, "#c87040"), (13.7, "#f2cb98"), (14.55, "#9c4327"), (15.5, "#c56d3f"),
          (16.5, "#e0a068"), (17.3, "#f3d0a0"), (18.0, "#b85f35"), (19.3, "#efc795"),
          (19.8, "#c46a3b"), (21.0, "#dc9a62")]
STRATA_LIN = [(z, hexcol(h)) for z, h in STRATA]


def strata_color(z):
    for k in range(len(STRATA_LIN) - 1, -1, -1):
        z0, c = STRATA_LIN[k]
        if z >= z0:
            if k > 0:
                return mix(STRATA_LIN[k - 1][1], c, smoothstep(z0 - 0.12, z0 + 0.12, z))
            return c
    return STRATA_LIN[0][1]


def build_rock_mesa():
    """Canyon backdrop (~33 x 24 m, 21 m tall): stepped sandstone butte with hard ledge bands,
    fluted cliffs and a talus apron, plus a slender capped spire.  Strata are vertex colours."""
    rng = random.Random(909)
    part = Part("rock_mesa")

    LEDGES = [(8.6, 9.5), (13.7, 14.55), (17.3, 18.0), (19.3, 19.85), (21.35, 22.1)]

    def mesa_fn(seed, top_z, ledge_amp):
        def fn(th, i, r, z):
            c, s_ = math.cos(th), math.sin(th)
            o = 1.0 + 0.16 * nz((c * 1.2, s_ * 1.2, 0.0), 1.0, seed) + 0.07 * nz((c * 2.6, s_ * 2.6, 0.0), 1.0, seed + 1)
            layer = sum(1 for za, _ in LEDGES if z > za)
            o += 0.045 * nz((c * 2.0, s_ * 2.0, layer * 2.3), 1.0, seed + 2)
            g = 1.0 - abs(nz((c * 4.5, s_ * 4.5, z * 0.02), 1.0, seed + 3))
            o -= 0.18 * g ** 4 * smoothstep(3.0, 6.0, z)
            o += 0.045 * nz((c * 9.0, s_ * 9.0, z * 0.05), 1.0, seed + 6)
            for k, (za, zb) in enumerate(LEDGES):
                if za + 0.1 <= z <= zb - 0.05:
                    mask = smoothstep(-0.12, 0.3, nz((c * 2.0, s_ * 2.0, k * 1.7), 1.0, seed + 7))
                    o += ledge_amp * mask
                elif za - 1.4 <= z < za - 0.05:
                    o -= 0.025
            if z < 5.0:
                o += 0.12 * nz((c * 3.2, s_ * 3.2, z * 0.6), 1.0, seed + 4) * (1.0 - z / 5.0)
                o += 0.05 * nz((c * 8.0, s_ * 8.0, z * 1.5), 1.0, seed + 8) * (1.0 - z / 5.0)
            if z > top_z - 0.3 and r < 4.9:
                z += 0.35 * nz((c * r * 0.35, s_ * r * 0.35, 0.0), 1.0, seed + 5) * min(1.0, r / 1.5)
            return r * o, z
        return fn

    butte = [(12.5, -0.6), (11.2, 0.3), (9.4, 1.5), (7.6, 3.0), (6.4, 4.4), (5.8, 5.3), (5.7, 7.4),
             (5.62, 8.62), (5.6, 8.8), (5.58, 9.3), (5.55, 9.5), (5.5, 11.5), (5.4, 13.72),
             (5.38, 13.9), (5.36, 14.4), (5.34, 14.55), (5.25, 16.0), (5.15, 17.32), (5.14, 17.5),
             (5.12, 17.9), (5.05, 18.0), (4.6, 18.2), (2.4, 18.3), (0.0, 18.34)]
    M = Matrix.Diagonal((1.45, 1.0, 1.0, 1.0))
    lathe(part, densify(butte, 1.15), 64, "sandstone", radial_fn=mesa_fn(1.0, 18.1, 0.075), matrix=M)
    spire = [(4.4, -0.6), (3.7, 0.5), (2.8, 2.0), (2.1, 3.5), (1.85, 4.6), (1.75, 8.62), (1.75, 8.8),
             (1.74, 9.3), (1.72, 9.5), (1.62, 13.72), (1.62, 13.9), (1.6, 14.4), (1.55, 14.55),
             (1.4, 19.32), (1.4, 19.45), (1.4, 19.7), (1.42, 19.85), (1.48, 21.37), (1.48, 21.5),
             (1.47, 21.95), (1.4, 22.1), (0.9, 22.4), (0.0, 22.5)]
    M = Matrix.Translation((13.2, 3.4, 0.0)) @ Matrix.Diagonal((1.0, 1.25, 1.0, 1.0))
    lathe(part, densify(spire, 1.2), 32, "sandstone", radial_fn=mesa_fn(7.0, 22.45, 0.16), matrix=M)
    body = part.finish(smooth=42)

    rocks = Part("mesa_boulders")
    for pos, size in [((-9.0, -8.9, 0), (4.6, 3.6, 3.2)), ((5.5, -10.6, 0), (3.2, 2.6, 2.2)),
                      ((-15.2, 3.6, 0), (3.8, 3.2, 2.6)), ((8.4, 8.4, 0), (2.8, 2.4, 1.8)),
                      ((-3.0, -11.2, 0), (2.0, 1.7, 1.3))]:
        rock_chunk(rocks, rng, pos, size, n_planes=10, embed=0.25, mats=("sandstone", "sandstone"))
    rocks_obj = rocks.finish()
    decimate_to(rocks_obj, 1000)
    set_smooth(rocks_obj, 40)

    obj = join_objects([body, rocks_obj], "rock_mesa")
    (x0, y0, _), (x1, y1, _) = bbox(obj)
    off = Vector((-(x0 + x1) * 0.5, -(y0 + y1) * 0.5, 0.0))
    for v in obj.data.vertices:
        v.co += off
    obj.data.update()
    ao = bake_ao(obj, samples=24, max_dist=4.0)
    curv = bake_curvature(obj)

    def color(s):
        p = s.co
        zz = p.z + 0.35 * nz((p.x * 0.12, p.y * 0.12, p.z * 0.05), 1.0, 3.0)
        c = strata_color(zz)
        steep = 1.0 - abs(s.normal.z)
        v = nz((p.x * 0.8, p.y * 0.8, p.z * 0.06), 1.0, 8.0)
        c = mix(c, hexcol("#4e2416"), 0.55 * smoothstep(0.1, 0.5, v) * steep * smoothstep(5.0, 7.0, p.z))
        c = mix(c, hexcol("#e3a96c"), 0.45 * smoothstep(0.6, 0.9, s.normal.z))
        c = mix(c, hexcol("#d2955e"), 0.35 * (1.0 - smoothstep(2.0, 5.0, p.z)))
        c = scale_col(c, 1.0 + 0.18 * max(0.0, curv[s.index]) + 0.06 * nz(p, 0.9, 4.0))
        return shade(c, s.ao, 0.6)

    paint(obj, color, ao)
    return obj


def build_street_lamp():
    """~6.3 m modern street lamp: tapered graphite pole on a concrete foot, swan-neck arm
    reaching +X (over the road), slim pod head with an emissive LED panel underneath."""
    p = Part("street_lamp")
    prof = [(0.0, 0.0), (0.24, 0.0), (0.24, 0.05), (0.225, 0.075), (0.16, 0.11), (0.125, 0.16),
            (0.118, 0.50), (0.105, 0.56), (0.085, 0.62), (0.077, 2.60), (0.082, 2.62), (0.082, 2.74),
            (0.077, 2.76), (0.066, 4.60), (0.0, 4.62)]
    mats = ["concrete"] * 4 + ["metal_dark"] * 5 + ["metal"] * 3 + ["metal_dark"] * 2
    lathe(p, prof, 18, mats=mats)
    lathe(p, [(0.0, 4.50), (0.086, 4.50), (0.09, 4.53), (0.09, 4.64), (0.075, 4.67), (0.0, 4.67)],
          18, "metal")
    arm = bezier((0, 0, 4.35), (0, 0, 5.55), (0.05, 0, 6.2), (0.75, 0, 6.22), 13)
    arm += [Vector((1.0, 0, 6.205)), Vector((1.25, 0, 6.19)), Vector((1.42, 0, 6.18))]
    radii = [lerp(0.066, 0.045, k / (len(arm) - 1)) for k in range(len(arm))]
    sweep(p, arm, radii, 14, "metal_dark", cap_end=True)
    body = p.finish(smooth=40)

    head = Part("lamp_head")
    hprof = [(0.0, -0.04), (0.07, -0.02), (0.13, 0.06), (0.16, 0.22), (0.155, 0.50), (0.12, 0.70),
             (0.06, 0.80), (0.0, 0.83)]

    def flat_bottom(th, i, r, z):
        c = math.cos(th)            # local +x is world down after the rotation below
        return r * (1.0 - 0.30 * max(0.0, c) ** 3), z
    M = (Matrix.Translation((1.24, 0.0, 6.17)) @ Matrix.Rotation(math.pi / 2 + 0.06, 4, "Y") @
         Matrix.Diagonal((0.42, 1.0, 1.0, 1.0)))
    lathe(head, hprof, 24, "metal_dark", radial_fn=flat_bottom, matrix=M)
    head.bm.normal_update()
    li = head.mi("lamp_light")
    for f in head.bm.faces:
        c = f.calc_center_median()
        if f.normal.z < -0.85 and 1.36 < c.x < 1.98:
            f.material_index = li
    sphere(head, (1.62, 0.0, 6.215), (0.05, 0.05, 0.03), "metal", 10, 6)
    head_obj = head.finish(smooth=40)
    return join_objects([body, head_obj], "street_lamp")


def rrect_path(x0, x1, z0, z1, r, y, n=6):
    """Closed rounded rectangle in the XZ plane (starts / ends at the bottom middle)."""
    pts = [Vector(((x0 + x1) * 0.5, y, z0))]
    for cx, cz, a0 in [(x1 - r, z0 + r, -90), (x1 - r, z1 - r, 0), (x0 + r, z1 - r, 90),
                       (x0 + r, z0 + r, 180)]:
        for k in range(n + 1):
            a = math.radians(a0 + 90 * k / n)
            pts.append(Vector((cx + r * math.cos(a), y, cz + r * math.sin(a))))
    pts.append(pts[0].copy())
    return pts


def build_neon_sign():
    """~6 m wide roadside billboard facing -Y on two posts: dark panel, magenta neon frame, cyan
    chevrons + speed lines (original, brand-free), catwalk and three flood lamps."""
    p = Part("neon_sign_struct")
    se = superellipse(4.0)
    for x in (-2.0, 2.0):
        box(p, (x, 0.22, 0.1), (0.7, 0.7, 0.2), "concrete", bevel=0.05, segments=2)
        lathe(p, [(0.0, 0.18), (0.16, 0.18), (0.16, 0.30), (0.13, 0.36), (0.13, 5.62), (0.10, 5.67),
                  (0.0, 5.68)], 16, "metal_dark", radial_fn=lambda th, i, r, z: (r * se(th), z),
              matrix=Matrix.Translation((x, 0.22, 0.0)))
        tube(p, (x, 0.08, 2.62), (x, -0.62, 2.95), 0.03, 6, "metal_dark", caps=True)
    box(p, (0.0, 0.0, 4.5), (6.0, 0.30, 2.9), "metal_dark", bevel=0.08, segments=2)
    box(p, (0.0, -0.15, 4.5), (5.72, 0.03, 2.62), "paint_black", bevel=0.02, segments=1)
    for z in (3.4, 5.5):
        box(p, (0.0, 0.22, z), (4.6, 0.14, 0.14), "metal", bevel=0.02, segments=1)
    box(p, (0.0, -0.40, 2.98), (5.6, 0.55, 0.05), "metal_dark", bevel=0.01, segments=1)
    tube(p, (-2.8, -0.66, 3.32), (2.8, -0.66, 3.32), 0.018, 6, "metal", caps=True)
    for k in range(5):
        x = lerp(-2.75, 2.75, k / 4)
        tube(p, (x, -0.66, 3.0), (x, -0.66, 3.32), 0.014, 5, "metal")
    for x in (-1.9, 0.0, 1.9):
        sweep(p, [Vector((x, -0.02, 5.9)), Vector((x, -0.25, 6.22)), Vector((x, -0.55, 6.32))],
              [0.025, 0.025, 0.022], 6, "metal_dark")
        R = Matrix.Rotation(0.25, 4, "X")
        hc = Vector((x, -0.62, 6.27))
        box(p, hc, (0.34, 0.18, 0.14), "metal_dark", bevel=0.025, segments=2, matrix=R)
        box(p, hc + R.to_3x3() @ Vector((0.0, 0.0, -0.07)), (0.28, 0.13, 0.02), "lamp_light",
            bevel=0.006, segments=1, matrix=R)
    struct = p.finish(smooth=40)

    neon = Part("neon_tubes")
    y = -0.235
    sweep(neon, rrect_path(-2.66, 2.66, 3.40, 5.60, 0.30, y, 6), [0.045] * 30, 8, "neon")
    zc = 4.5
    for x, h in [(0.62, 0.40), (1.32, 0.54), (2.08, 0.68)]:
        pts = fillet([(x - 0.55 * h, y, zc + h), (x, y, zc), (x - 0.55 * h, y, zc - h)], 0.12, 4)
        sweep(neon, pts, [0.05] * len(pts), 8, "neon_alt", cap_start=True, cap_end=True)
    for z, xa, xb in [(zc + 0.36, -1.70, -0.10), (zc, -2.20, 0.16), (zc - 0.36, -1.70, -0.10),
                      (zc + 0.36, -2.25, -1.95), (zc - 0.36, -2.25, -1.95)]:
        tube(neon, (xa, y, z), (xb, y, z), 0.04, 8, "neon_alt", caps=True)
    for x, z in [(-2.66, 4.5), (2.66, 4.5), (0.0, 3.40), (0.0, 5.60), (-1.5, 3.40), (1.5, 5.60),
                 (-1.0, zc), (0.62, zc)]:
        box(neon, (x, -0.195, z), (0.05, 0.06, 0.05), "metal", bevel=0.008, segments=1)
    tubes = neon.finish(smooth=50)
    return join_objects([struct, tubes], "neon_sign")


CITY_WALL = [(0.0, hexcol("#1b1f31")), (0.5, hexcol("#323954")), (1.0, hexcol("#545e80"))]


def build_building_block():
    """Stylised city block tower (12 x 12 m, ~30 m to the antenna): podium with lit shop
    fronts, awnings and neon signs, six floors of window bays between pilasters and ledges,
    louvred crown with a cyan light band, water tank, AC units and an aviation-light mast."""
    rng = random.Random(1717)
    p = Part("building_block")
    H0, H1, FL = 5.0, 23.0, 3.0
    Z = Vector((0.0, 0.0, 1.0))
    sides = [(Vector((0, -1, 0)), Vector((1, 0, 0))), (Vector((1, 0, 0)), Vector((0, 1, 0))),
             (Vector((0, 1, 0)), Vector((-1, 0, 0))), (Vector((-1, 0, 0)), Vector((0, -1, 0)))]

    def fbox(n, t, s, out, z, along, depth, h, mat, bevel=0.0):
        centre = n * out + t * s + Z * z
        size = (abs(t.x) * along + abs(n.x) * depth, abs(t.y) * along + abs(n.y) * depth, h)
        box(p, centre, size, mat, bevel=bevel, segments=1)

    def pane(n, t, out, s0, s1, z0, z1, mat):
        b = n * out
        quad(p, [b + t * s0 + Z * z0, b + t * s1 + Z * z0, b + t * s1 + Z * z1, b + t * s0 + Z * z1],
             mat, facing=n)

    box(p, (0, 0, H0 * 0.5), (12.0, 12.0, H0), "concrete")
    box(p, (0, 0, (H0 + H1) * 0.5), (11.0, 11.0, H1 - H0), "concrete")
    for k in range(6):
        box(p, (0, 0, H0 + FL * k), (11.62, 11.62, 0.24), "paint_white", bevel=0.04, segments=1)
    box(p, (0, 0, H1 + 0.1), (11.9, 11.9, 0.45), "paint_white", bevel=0.06, segments=1)
    for sx in (-1, 1):
        for sy in (-1, 1):
            box(p, (sx * 5.55, sy * 5.55, (H0 + H1) * 0.5), (0.72, 0.72, H1 - H0), "paint_white",
                bevel=0.04, segments=1)
            box(p, (sx * 5.75, sy * 5.75, 2.2), (0.8, 0.8, 4.4), "paint_white", bevel=0.04, segments=1)
    for fi, (n, t) in enumerate(sides):
        for s in (-2.75, 0.0, 2.75):
            fbox(n, t, s, 5.6, (H0 + H1) * 0.5, 0.42, 0.3, H1 - H0, "paint_white")
        for f in range(6):
            zf = H0 + FL * f
            z0, z1 = zf + 0.55, zf + 2.55
            for b in range(4):
                sb = -4.125 + 2.75 * b
                lit = rng.random() < 0.40 + 0.05 * f
                for s0, s1 in ((sb - 0.95, sb - 0.05), (sb + 0.05, sb + 0.95)):
                    on = lit if rng.random() > 0.12 else not lit
                    pane(n, t, 5.505, s0, s1, z0, z1, "window_light" if on else "glass")
                fbox(n, t, sb, 5.56, z0 - 0.07, 2.05, 0.14, 0.1, "paint_white")
        for s in (-2.0, 2.0):
            fbox(n, t, s, 6.1, 2.05, 0.6, 0.25, 4.1, "paint_white", bevel=0.03)
        for b, sb in enumerate((-4.0, 0.0, 4.0)):
            door = fi == 0 and b == 1
            lit = (not door) and rng.random() < 0.8
            pane(n, t, 6.005, sb - 1.55, sb + 1.55, 0.45, 3.55, "window_light" if lit else "glass")
            if door:
                pane(n, t, 6.01, sb - 1.55, sb + 1.55, 2.85, 3.55, "window_light")
        fbox(n, t, 0.0, 6.45, 4.05, 12.6, 0.9, 0.2, "metal_dark", bevel=0.03)
    fbox(sides[0][0], sides[0][1], 0.0, 6.06, 4.6, 5.0, 0.1, 0.36, "neon")
    fbox(sides[1][0], sides[1][1], 1.0, 6.06, 4.6, 3.6, 0.1, 0.36, "neon_alt")
    fbox(sides[3][0], sides[3][1], -1.0, 6.06, 4.6, 3.6, 0.1, 0.36, "neon")

    cx, cy = -1.0, 0.6
    box(p, (cx, cy, 24.5), (8.4, 8.4, 2.6), "concrete")
    for z in (23.75, 24.1, 24.45, 24.8):
        box(p, (cx, cy, z), (8.56, 8.56, 0.08), "metal_dark")
    box(p, (cx, cy, 25.3), (8.6, 8.6, 0.16), "neon_alt")
    box(p, (cx, cy, 25.85), (8.8, 8.8, 0.3), "paint_white", bevel=0.05, segments=1)
    for n, t in sides:
        fbox(n, t, 0.0, 5.82, 23.6, 11.9, 0.26, 0.7, "paint_white", bevel=0.03)
    for y in (-2.0, 1.2):
        box(p, (4.35, y, 23.7), (1.3, 1.0, 0.75), "metal_dark", bevel=0.06, segments=2)
        lathe(p, [(0.0, 0.0), (0.36, 0.0), (0.36, 0.05), (0.31, 0.065), (0.0, 0.035)], 16, "metal",
              matrix=Matrix.Translation((4.35, y, 24.07)))
    for x, y in ((2.6, -4.8), (-4.6, -4.9)):
        tube(p, (x, y, 23.3), (x, y, 24.5), 0.12, 10, "metal", caps=True)
    tx, ty = -3.0, 2.8
    for dx in (-0.75, 0.75):
        for dy in (-0.75, 0.75):
            tube(p, (tx + dx, ty + dy, 26.0), (tx + dx, ty + dy, 27.22), 0.07, 8, "metal_dark")
    box(p, (tx, ty, 27.26), (2.3, 2.3, 0.12), "metal_dark", bevel=0.02, segments=1)
    tank = [(0.0, 0.0), (1.0, 0.0), (1.05, 0.08), (1.05, 0.40), (1.08, 0.42), (1.08, 0.50), (1.05, 0.52),
            (1.05, 1.20), (1.08, 1.22), (1.08, 1.30), (1.05, 1.32), (1.05, 1.85), (1.0, 1.90),
            (0.3, 2.45), (0.0, 2.50)]
    tmats = ["wood"] * 3 + ["metal_dark"] * 3 + ["wood"] + ["metal_dark"] * 3 + ["wood"] * 2 + ["metal_dark"] * 2
    lathe(p, tank, 16, mats=tmats, matrix=Matrix.Translation((tx, ty, 27.32)))
    ax, ay = 1.6, -1.8
    tube(p, (ax, ay, 26.0), (ax, ay, 29.3), 0.06, 8, "metal", caps=True)
    for z, w in ((28.0, 0.5), (28.8, 0.35)):
        tube(p, (ax - w, ay, z), (ax + w, ay, z), 0.025, 6, "metal", caps=True)
    sphere(p, (ax, ay, 29.4), 0.1, "start_light", 10, 6)
    obj = p.finish(smooth=30)
    obj.name = "building_block"
    ao = bake_ao(obj, samples=20, max_dist=2.0)

    def color(s):
        fc = s.face_center
        if s.mat == "concrete":
            t = 0.2 + 0.3 * clamp01(s.co.z / 26.0) + 0.45 * s.ao
            return ramp(CITY_WALL, t)
        if s.mat == "paint_white":
            return shade(mix(hexcol("#59617f"), hexcol("#9aa3c0"), 0.5 + 0.5 * s.normal.z * 0.6 + 0.2 * clamp01(s.co.z / 26)), s.ao, 0.6)
        if s.mat == "glass":
            k = clamp01((s.co.z - fc.z) / 1.0 + 0.5)
            c = mix(hexcol("#0c1222"), hexcol("#2c416c"), k)
            return mix(c, hexcol("#3a2f5c"), 0.3 * (0.5 + 0.5 * nz(fc, 0.35, 1.0)))
        if s.mat == "window_light":
            v = nz(fc, 0.6, 2.0)
            return mix(hexcol("#ffd28a"), hexcol("#fff3dc") if v > 0 else hexcol("#ffb35a"), abs(v) * 1.4)
        if s.mat == "wood":
            return shade(mix(hexcol("#5e3b26"), hexcol("#8a5a38"), 0.5 + 0.5 * nz((s.co.x * 6, s.co.y * 6, s.co.z * 0.5), 1.0, 3.0)), s.ao)
        if s.mat in ("neon", "neon_alt", "start_light", "lamp_light", "window_light"):
            return mat_col(s.mat)
        return shade(mat_col(s.mat), s.ao)

    paint(obj, color, ao)
    return obj


def _interp(profile, r):
    """z of a monotonic (r, z) polyline at radius r."""
    for (r0, z0), (r1, z1) in zip(profile, profile[1:]):
        if r0 <= r <= r1:
            return lerp(z0, z1, (r - r0) / max(r1 - r0, 1e-6))
    return profile[-1][1]


def build_beach_umbrella():
    """~2.5 m leaning beach umbrella with scalloped striped canopy, a wooden deck chair with a
    striped sling, a towel and a beach ball."""
    rng = random.Random(88)
    tilt = Matrix.Rotation(0.13, 4, "X") @ Matrix.Rotation(-0.06, 4, "Y")

    def P(z):
        return tilt @ Vector((0.0, 0.0, z))

    pole = Part("umbrella_pole")
    tube(pole, P(-0.3), P(2.40), 0.022, 10, "wood", caps=True)
    tube(pole, P(1.15), P(1.27), 0.03, 10, "metal", caps=True)
    tube(pole, P(1.92), P(2.0), 0.034, 10, "metal", caps=True)
    sphere(pole, P(2.43), 0.04, "wood", 10, 6)
    Mc = Matrix.Translation(P(2.40 - 0.36)) @ tilt
    under = [(0.0, 0.33), (0.3, 0.27), (0.6, 0.16), (0.9, 0.03), (1.10, -0.05)]
    for k in range(8):
        th = k * TAU / 8
        d = Vector((math.cos(th), math.sin(th), 0.0))
        rib = [Mc @ (d * r + Vector((0, 0, _interp(under, r) - 0.016))) for r in (0.06, 0.4, 0.75, 1.07)]
        sweep(pole, rib, [0.009, 0.009, 0.008, 0.007], 4, "metal", cap_end=True)
        sweep(pole, [P(1.97), Mc @ (d * 0.55 + Vector((0, 0, _interp(under, 0.55) - 0.02)))],
              [0.007, 0.007], 4, "metal")
    pole_obj = pole.finish(smooth=45)

    canopy = Part("umbrella_canopy")
    prof = [(0.0, 0.33), (0.3, 0.27), (0.6, 0.16), (0.9, 0.03), (1.10, -0.05), (1.11, -0.13),
            (1.135, -0.13), (1.13, -0.04), (0.9, 0.065), (0.6, 0.195), (0.3, 0.305), (0.0, 0.36)]

    def sag_fn(th, i, r, z):
        sag = abs(math.sin(4 * th))
        rr = r / 1.13
        z2 = z - 0.07 * sag * rr ** 1.5
        if i in (5, 6):
            z2 -= 0.04 * sag
        return r * (1.0 - 0.035 * sag * rr), z2
    lathe(canopy, prof, 48, "fabric_a", radial_fn=sag_fn, matrix=Mc)
    inv = Mc.inverted()
    ia, ib = canopy.mi("fabric_a"), canopy.mi("fabric_b")
    for f in canopy.bm.faces:
        c = inv @ f.calc_center_median()
        a = math.atan2(c.y, c.x) % TAU
        f.material_index = ia if int(a / (TAU / 8)) % 2 == 0 else ib
    canopy_obj = canopy.finish(smooth=60)

    chair = Part("deck_chair")
    se = superellipse(4.0)
    for x in (-0.29, 0.29):
        for a, b in (((x, -0.55, 0.0), (x, 0.30, 1.0)), ((x, -0.72, 0.42), (x, 0.46, 0.0))):
            sweep(chair, [Vector(a), Vector(b)], [0.032, 0.032], 8, "wood", True, True,
                  up_hint=Vector((1, 0, 0)), squash=(0.55, 1.0), radial_fn=lambda th, i, r: r * se(th))
    for y, z in ((-0.70, 0.42), (0.29, 0.99), (0.43, 0.03), (-0.535, 0.02)):
        tube(chair, (-0.33, y, z), (0.33, y, z), 0.02, 8, "wood", caps=True)
    curve = bezier((0, 0.27, 0.965), (0, 0.12, 0.40), (0, -0.30, 0.10), (0, -0.68, 0.40), 10)
    grid = [[q + Vector((x, 0, 0)) for q in curve] for x in (-0.26, -0.13, 0.0, 0.13, 0.26)]
    sheet(chair, grid, 0.012, "fabric_a")
    Mch = Matrix.Translation((0.30, -1.05, 0.0)) @ Matrix.Rotation(0.35, 4, "Z")
    bmesh.ops.transform(chair.bm, matrix=Mch, verts=chair.bm.verts)
    Mt = Matrix.Translation((-0.95, -0.55, 0.0)) @ Matrix.Rotation(-0.45, 4, "Z")
    for k in range(5):
        box(chair, Mt @ Vector((-0.32 + 0.16 * k, 0.0, 0.012)), (0.16, 1.6, 0.02), "fabric_b",
            bevel=0.005, segments=1, matrix=Matrix.Rotation(-0.45, 4, "Z"))
    ball_c = Vector((0.85, 0.45, 0.17))
    sphere(chair, ball_c, 0.17, "paint_white", 18, 10, matrix=Matrix.Rotation(0.4, 4, "X"))
    chair_obj = chair.finish(smooth=40)

    obj = join_objects([pole_obj, canopy_obj, chair_obj], "beach_umbrella")
    ao = bake_ao(obj, samples=24, max_dist=1.2)
    inv_ch, inv_t = Mch.inverted(), Mt.inverted()
    towel_cols = [hexcol(h) for h in ("#17a7a8", "#fff2dc", "#ffc22e", "#fff2dc", "#17a7a8")]
    ball_cols = [hexcol(h) for h in ("#e8322a", "#ffffff", "#1f6fd1", "#ffd21f", "#ffffff", "#2bb24c")]
    rb = Matrix.Rotation(0.4, 4, "X").inverted()

    def color(s):
        fc = s.face_center
        if s.mat == "fabric_a" and fc.z > 1.4:
            return shade(hexcol("#ee4136"), s.ao, 0.5)
        if s.mat == "fabric_b" and fc.z > 1.4:
            return shade(hexcol("#fbf1dc"), s.ao, 0.5)
        if s.mat == "fabric_a":
            lx = (inv_ch @ fc).x
            return shade(hexcol("#1d9fb0") if int(math.floor((lx + 0.26) / 0.13)) % 2 == 0 else hexcol("#f4f1e6"), s.ao)
        if s.mat == "fabric_b":
            k = int(math.floor(((inv_t @ fc).x + 0.40) / 0.16))
            return shade(towel_cols[max(0, min(4, k))], s.ao)
        if s.mat == "paint_white":
            q = rb @ (fc - ball_c)
            if abs(q.z) > 0.15:
                return shade(hexcol("#ffffff"), s.ao, 0.4)
            return shade(ball_cols[int((math.atan2(q.y, q.x) % TAU) / (TAU / 6)) % 6], s.ao, 0.4)
        if s.mat == "wood":
            return shade(mix(hexcol("#b98652"), hexcol("#d8a86e"), 0.5 + 0.5 * nz(s.co, 6.0, 2.0)), s.ao)
        return shade(mat_col(s.mat), s.ao)

    paint(obj, color, ao)
    return obj


PUMPKIN_PROFILE = [(0.0, 0.08), (0.45, 0.0), (0.85, 0.14), (1.0, 0.45), (0.9, 0.78), (0.55, 0.97),
                   (0.18, 0.95), (0.0, 0.88)]


def pumpkin(part, center, radius, height, lobes, yaw=0.0, tilt=(0.0, 0.0), depth=0.11):
    """Lobed pumpkin (4 segments per lobe) with a curly stem.  Returns its transform."""
    def fn(th, i, r, z):
        g = (1.0 - abs(math.cos(lobes * th * 0.5))) ** 1.5
        zf = clamp01(z / height)
        fade = smoothstep(0.0, 0.25, zf) * (1.0 - smoothstep(0.8, 1.0, zf))
        return r * (1.0 - depth * g * (0.4 + 0.6 * fade)), z
    M = (Matrix.Translation(Vector(center)) @ Matrix.Rotation(yaw, 4, "Z") @
         Matrix.Rotation(tilt[0], 4, "X") @ Matrix.Rotation(tilt[1], 4, "Y"))
    lathe(part, [(r * radius, z * height) for r, z in PUMPKIN_PROFILE], lobes * 4, "pumpkin",
          radial_fn=fn, matrix=M)
    sc = radius / 0.25
    stem = [Vector((0, 0, 0.86 * height)), Vector((0.005, 0, 0.97 * height + 0.02 * sc)),
            Vector((0.02 * sc, 0.0, height + 0.055 * sc)), Vector((0.05 * sc, 0.012, height + 0.08 * sc))]
    sweep(part, [M @ q for q in stem], [0.032 * sc, 0.027 * sc, 0.023 * sc, 0.019 * sc], 6, "bark",
          cap_end=True, radial_fn=lambda th, i, r: r * (1.0 + 0.15 * math.cos(5 * th)))
    return M


def build_pumpkin_pile():
    """Autumn display (~1.4 m tall, ~2 m wide): two stacked hay bales with twine, five pumpkins
    (orange, cream, green) and a scatter of fallen leaves."""
    rng = random.Random(1031)
    bales = Part("hay_bales")
    bale_pose = [((0.0, 0.05, 0.21), 0.0), ((0.12, 0.0, 0.63), 0.38)]
    for c, yaw in bale_pose:
        R = Matrix.Rotation(yaw, 4, "Z")
        rounded_box(bales, c, (1.05, 0.5, 0.42), 0.075, "hay", cuts=3, segments=2, matrix=R)
    displace(bales.bm, 0.014, 9.0, seed=2)
    for c, yaw in bale_pose:
        R = Matrix.Rotation(yaw, 4, "Z")
        for x in (-0.27, 0.27):
            hy, hz, rr = 0.262, 0.222, 0.085
            loop = []
            for cy_, cz_, a0 in [(hy - rr, -hz + rr, -90), (hy - rr, hz - rr, 0), (-hy + rr, hz - rr, 90),
                                 (-hy + rr, -hz + rr, 180)]:
                for k in range(3):
                    a = math.radians(a0 + 45 * k)
                    loop.append(Vector(c) + R @ Vector((x, cy_ + rr * math.cos(a), cz_ + rr * math.sin(a))))
            loop.append(loop[0].copy())
            sweep(bales, loop, [0.012] * len(loop), 3, "wood_dark")
    bales_obj = bales.finish(smooth=50)

    pk = Part("pumpkins")
    pumpkins = [((0.16, -0.02, 0.83), 0.27, 0.34, 7, 0.3, (0.0, 0.05), "orange"),
                ((-0.78, -0.40, 0.0), 0.31, 0.38, 7, 1.2, (0.0, 0.0), "orange"),
                ((0.74, -0.45, 0.0), 0.22, 0.27, 6, 2.0, (0.05, 0.0), "deep"),
                ((-0.30, -0.58, 0.0), 0.18, 0.20, 6, 0.7, (0.0, 0.0), "cream"),
                ((0.28, -0.66, 0.0), 0.12, 0.15, 5, 2.6, (0.12, 0.0), "green")]
    centres = []
    for c, r, h, lobes, yaw, tl, kind in pumpkins:
        M = pumpkin(pk, c, r, h, lobes, yaw=yaw, tilt=tl)
        centres.append((M @ Vector((0, 0, h * 0.5)), r, kind))
    pk_obj = pk.finish(smooth=60)

    lv = Part("fallen_leaves")
    leaves = []
    for k in range(8):
        a = k * TAU / 8 + rng.uniform(-0.3, 0.3)
        d = rng.uniform(0.75, 1.15)
        pos = Vector((math.cos(a) * d * 1.05, math.sin(a) * d * 0.75, 0.0))
        yaw = rng.uniform(0, TAU)
        R = Matrix.Rotation(yaw, 4, "Z")
        sz = rng.uniform(1.2, 1.6)
        grid = []
        for side in (-1, 1):
            row = []
            for x, w in ((0.0, 0.004), (0.06, 0.045), (0.13, 0.003)):
                q = Vector((x * sz, side * w * sz, 0.008 + 0.025 * (x / 0.13) ** 2 + 0.012 * abs(side * w) / 0.045))
                row.append(pos + R @ q)
            grid.append(row)
        sheet(lv, grid, 0.004, "leaf_litter")
        leaves.append((pos, rng.choice(["#c2361b", "#e0651c", "#f0a21e", "#9a4a1c", "#d84a1a"])))
    lv_obj = lv.finish(smooth=60)

    obj = join_objects([bales_obj, pk_obj, lv_obj], "pumpkin_pile")
    ao = bake_ao(obj, samples=24, max_dist=0.6)
    curv = bake_curvature(obj)
    PUMPKIN_RAMPS = {
        "orange": [(0, hexcol("#7a2a08")), (0.45, hexcol("#d4580e")), (0.8, hexcol("#f58a22")), (1, hexcol("#ffbf5a"))],
        "deep":   [(0, hexcol("#5e1a06")), (0.45, hexcol("#b8400c")), (0.8, hexcol("#e06418")), (1, hexcol("#f8a050"))],
        "cream":  [(0, hexcol("#7d7260")), (0.45, hexcol("#cfc3a6")), (0.8, hexcol("#efe6cf")), (1, hexcol("#fffaf0"))],
        "green":  [(0, hexcol("#1f3317")), (0.45, hexcol("#3f6a2a")), (0.8, hexcol("#6f9a40")), (1, hexcol("#b5c873"))],
    }

    def color(s):
        if s.mat == "hay":
            streak = nz((s.co.x * 2.0, s.co.y * 18.0, s.co.z * 18.0), 1.0, 4.0)
            t = 0.2 + 0.55 * s.ao + 0.15 * streak + 0.15 * s.normal.z
            return ramp([(0, hexcol("#6e5422")), (0.45, hexcol("#b8913e")), (0.8, hexcol("#dcbc62")),
                         (1, hexcol("#f2db8e"))], t)
        if s.mat == "wood_dark":
            return shade(hexcol("#7a5a34"), s.ao)
        if s.mat == "bark":
            return shade(mix(hexcol("#4f5a26"), hexcol("#8c7a44"), clamp01(0.5 + s.normal.z)), s.ao, 0.4)
        if s.mat == "leaf_litter":
            k = min(range(len(leaves)), key=lambda j: (s.co - leaves[j][0]).length_squared)
            return shade(hexcol(leaves[k][1]), s.ao, 0.4)
        k = min(range(len(centres)), key=lambda j: (s.co - centres[j][0]).length - centres[j][1])
        t = 0.1 + 0.5 * s.ao ** 1.2 + 0.2 * curv[s.index] + 0.15 * s.normal.z + 0.05 * nz(s.co, 6.0, 1.0)
        c = ramp(PUMPKIN_RAMPS[centres[k][2]], t)
        return mix(c, hexcol("#8f8a2a"), 0.35 * smoothstep(-0.6, -0.95, s.normal.z))

    paint(obj, color, ao)
    return obj


FERN = [(0.0, hexcol("#143a1e")), (0.4, hexcol("#2a6a2a")), (0.75, hexcol("#56a03a")),
        (1.0, hexcol("#a8d266"))]
GRASS = [(0.0, hexcol("#1d4a1c")), (0.4, hexcol("#3b7a2a")), (0.75, hexcol("#6aa83c")),
         (1.0, hexcol("#bfdc74"))]


def build_fern():
    """~1.1 m wide fern rosette: seven arching pinnate fronds and an unfurling fiddlehead."""
    rng = random.Random(64)
    p = Part("fern")
    specs = []
    for k in range(6):
        az = k * TAU / 6 + rng.uniform(-0.25, 0.25)
        specs.append((az, rng.uniform(0.62, 0.78) if k else 0.52, rng.uniform(2.3, 3.0), 21 if k else 17))
    for az, length, a, cols in specs:
        d = Vector((math.cos(az), math.sin(az), 0.0))
        base = d * 0.03 + Vector((0, 0, 0.02))
        tip_z = rng.uniform(0.04, 0.16)
        g = a - (tip_z - 0.02) / length

        def spine(s, d=d, base=base, a=a, g=g, length=length):
            return base + d * (length * s * 0.78) + Vector((0, 0, length * (a * s - g * s * s) * 0.7))

        def wfn(s):
            return 0.12 * smoothstep(0.02, 0.3, s) * (1.0 - s ** 1.6) ** 0.75
        frond(p, spine, wfn, cols, "leaves", rows_u=(-1.0, 1.0), fold=0.35, zig=1.3, notch=0.16,
              thickness=0.008, min_width=0.005, twist=rng.uniform(-0.25, 0.25))
    pts = [Vector((0.02, -0.02, 0.0)), Vector((0.03, -0.02, 0.15)), Vector((0.04, -0.025, 0.28))]
    top = pts[-1]
    for k in range(1, 9):
        phi = k / 8 * 1.7 * math.pi
        rad = 0.07 * (1.0 - 0.6 * k / 8)
        pts.append(top + Vector((rad * math.sin(phi), 0.0, rad * (1.0 - math.cos(phi)) * 0.9)) * 1.0
                   + Vector((0, -0.01 * k, 0)))
    radii = [lerp(0.014, 0.008, k / (len(pts) - 1)) for k in range(len(pts))]
    sweep(p, pts, radii, 5, "leaves", cap_end=True)
    obj = p.finish(smooth=70)
    obj.name = "fern"
    ao = bake_ao(obj, samples=24, max_dist=0.3)
    curv = bake_curvature(obj)

    def color(s):
        tip = clamp01(Vector((s.co.x, s.co.y, 0.0)).length / 0.6)
        t = 0.1 + 0.45 * s.ao ** 1.3 + 0.25 * tip + 0.12 * (s.normal.z * 0.5 + 0.5) + 0.08 * curv[s.index]
        return ramp(FERN, t + 0.05 * nz(s.co, 6.0, 3.0))

    paint(obj, color, ao)
    return obj


def build_grass_tuft():
    """~0.5 m clump of 21 curved, ridged grass blades (closed 3-sided sweeps)."""
    rng = random.Random(12)
    p = Part("grass_tuft")
    for k in range(21):
        a = k * 2.39996 + rng.uniform(-0.2, 0.2)
        rr = 0.07 * math.sqrt((k + 0.5) / 21)
        base = Vector((math.cos(a) * rr, math.sin(a) * rr, -0.03))
        out = Vector((math.cos(a), math.sin(a), 0.0))
        h = rng.uniform(0.36, 0.62) * (1.0 - 0.3 * rr / 0.07)
        lean = rng.uniform(0.15, 0.45) + 0.6 * rr / 0.07
        droop = rng.uniform(0.1, 0.35)
        pts = []
        for j, f in enumerate((0.0, 0.38, 0.72, 1.0)):
            horiz = h * lean * (f ** 1.6 + droop * f ** 3)
            pts.append(base + out * horiz + Vector((0, 0, h * f * (1.0 - 0.25 * droop * f * f))))
        w = rng.uniform(0.013, 0.02)
        sweep(p, pts, [w, w * 0.85, w * 0.5, 0.0012], 3, "grass", up_hint=out, squash=(0.28, 1.0))
    obj = p.finish(smooth=80)
    obj.name = "grass_tuft"
    ao = bake_ao(obj, samples=16, max_dist=0.15)

    def color(s):
        hgt = clamp01((s.co.z + 0.03) / 0.5)
        t = 0.08 + 0.55 * hgt ** 0.8 + 0.25 * s.ao + 0.1 * nz(s.co, 14.0, 2.0)
        return ramp(GRASS, t)

    paint(obj, color, ao)
    return obj


# name: (builder, triangle budget, uses vertex colours)
PROPS = {
    "tree_pine":      (build_tree_pine, 6000, True),
    "tree_round":     (build_tree_round, 8000, True),
    "bush":           (build_bush, 2000, True),
    "rock_a":         (build_rock_a, 3000, True),
    "rock_b":         (build_rock_b, 3000, True),
    "rock_c":         (build_rock_c, 3000, True),
    "tire_stack":     (build_tire_stack, 4000, False),
    "traffic_cone":   (build_traffic_cone, 1000, False),
    "start_arch":     (build_start_arch, 25000, False),
    "grandstand":     (build_grandstand, 25000, False),
    "flag_pole":      (build_flag_pole, 2000, False),
    "fence_segment":  (build_fence_segment, 1500, False),
    "cactus_a":        (build_cactus_a, 3000, True),
    "cactus_b":        (build_cactus_b, 3000, True),
    "palm_tree":       (build_palm_tree, 7000, True),
    "tree_pine_snow":  (build_tree_pine_snow, 7000, True),
    "tree_dead":       (build_tree_dead, 7000, True),
    "rock_mesa":       (build_rock_mesa, 8000, True),
    "rock_lava":       (build_rock_lava, 3000, True),
    "crystal_cluster": (build_crystal_cluster, 2500, True),
    "street_lamp":     (build_street_lamp, 2000, False),
    "neon_sign":       (build_neon_sign, 4000, False),
    "building_block":  (build_building_block, 6000, True),
    "beach_umbrella":  (build_beach_umbrella, 2500, True),
    "snowman":         (build_snowman, 3000, True),
    "pumpkin_pile":    (build_pumpkin_pile, 3000, True),
    "fern":            (build_fern, 1200, True),
    "grass_tuft":      (build_grass_tuft, 400, True),
}


def export_glb(obj, path):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.export_scene.gltf(
        filepath=path,
        export_format="GLB",
        use_selection=True,
        export_apply=True,
        export_yup=True,
        export_cameras=False,
        export_lights=False,
        export_normals=True,
        export_texcoords=True,
        export_materials="EXPORT",
        export_vertex_color="MATERIAL",
        export_animations=False,
    )


def main():
    names, out_dir = parse_args()
    unknown = [n for n in names if n not in PROPS]
    if unknown:
        raise SystemExit(f"Unknown prop(s): {unknown}. Available: {list(PROPS)}")
    os.makedirs(out_dir, exist_ok=True)
    rows = []
    for name, (builder, budget, use_vc) in PROPS.items():
        if names and name not in names:
            continue
        reset_scene()
        BuildState.vertex_colors = use_vc
        obj = builder()
        obj.name = name
        obj.location = (0, 0, 0)
        tris = tri_count(obj)
        (x0, y0, z0), (x1, y1, z1) = bbox(obj)
        export_glb(obj, os.path.join(out_dir, name + ".glb"))
        flag = "OK" if tris <= budget else "OVER BUDGET"
        rows.append(f"{name:<15} {tris:>6} / {budget:<6} {flag:<11} "
                    f"size {x1 - x0:5.2f} x {y1 - y0:5.2f} x {z1 - z0:5.2f} m  "
                    f"z [{z0:+.2f}, {z1:+.2f}]  vc={'yes' if use_vc else 'no'}  "
                    f"mats={[m.name for m in obj.data.materials]}")
    print("\n=== Codeplay in Kart props ->", out_dir)
    for r in rows:
        print(r)


if __name__ == "__main__":
    main()
