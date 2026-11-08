"""
Codeplay in Kart -- procedural kart model builder
=================================================

Builds every kart part (bodies, wheels, spoilers, driver) from scratch with bpy/bmesh
and exports each one as a .glb into ``assets/models/karts/``.

Usage (from the project root)::

    blender --background --factory-startup --python tools/blender/build_karts.py
    blender --background --factory-startup --python tools/blender/build_karts.py -- wheel_classic body_vortex
    blender --background --factory-startup --python tools/blender/build_karts.py -- --out C:/tmp/karts

Positional args after ``--`` restrict the build to those part names.

Conventions (see docs/ASSET_CONTRACT.md):
  * metres, Blender Z-up, kart front = +Y
  * wheels: axle along X, nominal radius 0.28, outer face toward +X
  * every body carries socket_* empties + a separate ``steering_wheel`` object
  * materials are named exactly as the contract says, so the game can recolour them

How the script is organised
---------------------------
1. Materials                 -> MATERIAL_DEFS / make_materials()
2. Geometry library          -> rings, lofts, sweeps (tubes), lathes, rounded boxes, slabs...
   Every primitive bakes its geometry directly in world space (objects keep an identity
   transform) and registers itself in the current *group*; a part is then joined into
   a single multi-material mesh.
3. Shared kart sub-assemblies -> seat, steering wheel, axles, pedals...
4. One ``build_<part>()`` function per exported file, listed in PARTS at the bottom.

To add a new part: write ``def build_mything():`` that creates geometry with the helpers,
returns ``finish(...)`` and register it in PARTS.
"""

import bpy
import bmesh
import math
import os
import sys
from math import sin, cos, pi, radians, sqrt, copysign
from mathutils import Vector, Matrix

V = Vector

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.normpath(os.path.join(SCRIPT_DIR, "..", ".."))
DEFAULT_OUT_DIR = os.path.join(PROJECT_ROOT, "assets", "models", "karts")

WHEEL_NOMINAL_RADIUS = 0.28
WHEEL_NOMINAL_WIDTH = 0.24
STEER_OFFSET = V((0.0, 0.42, 0.24))      # socket_driver -> steering wheel hub
STEER_TILT = radians(-40.0)              # rotation about X: local +Y = column (forward/down)
STEER_GRIP_X = 0.17                      # hands grip the rim at +-X
HAND_TARGET = V((STEER_GRIP_X, 0.42, 0.24))  # relative to the driver hip origin


MATERIAL_DEFS = {
    "paint_primary":   dict(color=(0.78, 0.035, 0.03), metallic=0.25, roughness=0.32, coat=0.8),
    "paint_secondary": dict(color=(0.90, 0.90, 0.88), metallic=0.05, roughness=0.34, coat=0.6),
    "paint_accent":    dict(color=(1.00, 0.62, 0.02), metallic=0.20, roughness=0.32, coat=0.6),
    "rim":             dict(color=(0.78, 0.79, 0.82), metallic=1.00, roughness=0.22),
    "suit":            dict(color=(0.05, 0.08, 0.22), metallic=0.00, roughness=0.62),
    "helmet":          dict(color=(0.92, 0.92, 0.92), metallic=0.10, roughness=0.25, coat=0.9),
    "chrome":          dict(color=(0.95, 0.95, 0.96), metallic=1.00, roughness=0.08),
    "carbon":          dict(color=(0.025, 0.025, 0.03), metallic=0.30, roughness=0.35, coat=0.8),
    "metal_dark":      dict(color=(0.07, 0.07, 0.08), metallic=0.85, roughness=0.40),
    "rubber":          dict(color=(0.022, 0.022, 0.024), metallic=0.00, roughness=0.85),
    "seat_fabric":     dict(color=(0.045, 0.045, 0.055), metallic=0.00, roughness=0.90),
    "glass":           dict(color=(0.60, 0.75, 0.85), metallic=0.00, roughness=0.05, alpha=0.35),
    "visor":           dict(color=(0.02, 0.025, 0.04), metallic=0.90, roughness=0.06, coat=1.0),
    "glove":           dict(color=(0.04, 0.04, 0.045), metallic=0.00, roughness=0.65),
    "emissive_light":  dict(color=(0.90, 0.95, 1.00), roughness=0.3, emission=(0.80, 0.92, 1.0), strength=6.0),
    "emissive_tail":   dict(color=(0.80, 0.02, 0.02), roughness=0.3, emission=(1.00, 0.015, 0.005), strength=4.0),
    "whitewall":       dict(color=(0.86, 0.85, 0.82), metallic=0.00, roughness=0.62),
}
MAT = {}


def make_materials():
    """Create (or reuse) every contract material with exact names."""
    for name, d in MATERIAL_DEFS.items():
        m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
        m.use_fake_user = True
        if not m.node_tree:
            m.use_nodes = True
        bsdf = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
        bsdf.inputs["Base Color"].default_value = (*d["color"], 1.0)
        bsdf.inputs["Metallic"].default_value = d.get("metallic", 0.0)
        bsdf.inputs["Roughness"].default_value = d.get("roughness", 0.5)
        bsdf.inputs["Coat Weight"].default_value = d.get("coat", 0.0)
        bsdf.inputs["Coat Roughness"].default_value = 0.05
        if "emission" in d:
            bsdf.inputs["Emission Color"].default_value = (*d["emission"], 1.0)
            bsdf.inputs["Emission Strength"].default_value = d["strength"]
        if "alpha" in d:
            bsdf.inputs["Alpha"].default_value = d["alpha"]
            try:
                m.surface_render_method = "BLENDED"
            except (TypeError, AttributeError):
                pass
        m.diffuse_color = (*d["color"], d.get("alpha", 1.0))
        MAT[name] = m


_groups = [[]]


class Group:
    """Collects the objects created inside a ``with Group() as g:`` block (g.objs)."""

    def __enter__(self):
        _groups.append([])
        return self

    def __exit__(self, *exc):
        self.objs = _groups.pop()


def _register(obj):
    _groups[-1].append(obj)


class MatList:
    """Maps material names to slot indices for one mesh."""

    def __init__(self):
        self.names = []

    def idx(self, name):
        if name not in self.names:
            self.names.append(name)
        return self.names.index(name)


def mtx_of(loc=(0, 0, 0), rot=(0, 0, 0), scale=None):
    """Build a 4x4 matrix from location, XYZ euler (degrees) and optional scale."""
    m = Matrix.Translation(V(loc))
    if isinstance(rot, Matrix):
        m = m @ rot.to_4x4()
    else:
        m = m @ (Matrix.Rotation(radians(rot[2]), 4, "Z") @ Matrix.Rotation(radians(rot[1]), 4, "Y")
                 @ Matrix.Rotation(radians(rot[0]), 4, "X"))
    if scale is not None:
        s = scale if hasattr(scale, "__len__") else (scale, scale, scale)
        m = m @ Matrix.Diagonal((*s, 1.0))
    return m


def mirror_x():
    return Matrix.Diagonal((-1.0, 1.0, 1.0, 1.0))


def axis_matrix(direction):
    """Rotation (4x4) that maps local +Z onto ``direction``."""
    return V((0, 0, 1)).rotation_difference(V(direction).normalized()).to_matrix().to_4x4()


def _shade(bm, sharp_angle=None):
    for f in bm.faces:
        f.smooth = True
    if sharp_angle is not None:
        lim = radians(sharp_angle)
        for e in bm.edges:
            if len(e.link_faces) == 2:
                try:
                    if e.calc_face_angle() > lim:
                        e.smooth = False
                except ValueError:
                    pass


def mesh_object(name, bm, ml, mtx=None, sharp_angle=None, recalc=True):
    """Turn a bmesh into a registered object (geometry baked in world space)."""
    if mtx is not None:
        bmesh.ops.transform(bm, matrix=mtx, verts=bm.verts)
    if recalc:
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    _shade(bm, sharp_angle)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for n in ml.names:
        me.materials.append(MAT[n])
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    _register(obj)
    return obj


def add_bevel(obj, width, segments=3, angle=30.0, profile=0.5):
    m = obj.modifiers.new("Bevel", "BEVEL")
    m.width = width
    m.segments = segments
    m.limit_method = "ANGLE"
    m.angle_limit = radians(angle)
    m.profile = profile
    m.use_clamp_overlap = True
    return m


def add_wn(obj):
    m = obj.modifiers.new("WeightedNormal", "WEIGHTED_NORMAL")
    m.keep_sharp = True
    m.weight = 50
    return m


def add_subsurf(obj, levels=1):
    m = obj.modifiers.new("Subsurf", "SUBSURF")
    m.levels = levels
    m.render_levels = levels
    return m


def add_solidify(obj, thickness, offset=0.0):
    m = obj.modifiers.new("Solidify", "SOLIDIFY")
    m.thickness = thickness
    m.offset = offset
    m.use_even_offset = True
    return m


def catmull(p0, p1, p2, p3, t):
    t2, t3 = t * t, t * t * t
    return 0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t3)


def smooth_path(pts, sub=4, closed=False):
    """Catmull-Rom resample of a point list (sub samples per segment)."""
    pts = [V(p) for p in pts]
    n = len(pts)
    out = []
    segs = n if closed else n - 1
    for i in range(segs):
        p0 = pts[(i - 1) % n] if closed else pts[max(i - 1, 0)]
        p1 = pts[i]
        p2 = pts[(i + 1) % n]
        p3 = pts[(i + 2) % n] if closed else pts[min(i + 2, n - 1)]
        for k in range(sub):
            out.append(catmull(p0, p1, p2, p3, k / sub))
    if not closed:
        out.append(pts[-1])
    return out


def fillet_path(pts, radius, steps=5, closed=False):
    """Round the corners of a polyline with quadratic-bezier fillets."""
    pts = [V(p) for p in pts]
    n = len(pts)
    out = []
    for i in range(n):
        p = pts[i]
        if not closed and (i == 0 or i == n - 1):
            out.append(p)
            continue
        a, b = pts[i - 1], pts[(i + 1) % n]
        d1, d2 = a - p, b - p
        d = min(radius, d1.length * 0.45, d2.length * 0.45)
        if d < 1e-5 or abs(d1.normalized().dot(d2.normalized())) > 0.9999:
            out.append(p)
            continue
        A, B = p + d1.normalized() * d, p + d2.normalized() * d
        for k in range(steps + 1):
            t = k / steps
            out.append((1 - t) ** 2 * A + 2 * (1 - t) * t * p + t * t * B)
    return out


def interp_keys(keys, sub=4):
    """Catmull-Rom interpolation of a list of parameter dicts (missing keys inherit)."""
    full = []
    last = {}
    for k in keys:
        d = dict(last)
        d.update(k)
        full.append(d)
        last = d
    names = set().union(*[k.keys() for k in full])
    n = len(full)
    out = []
    for i in range(n - 1):
        k0, k1, k2, k3 = full[max(i - 1, 0)], full[i], full[i + 1], full[min(i + 2, n - 1)]
        for s in range(sub):
            t = s / sub
            d = {}
            for nm in names:
                if all(isinstance(k.get(nm), (int, float)) for k in (k0, k1, k2, k3)):
                    d[nm] = catmull(k0[nm], k1[nm], k2[nm], k3[nm], t)
                else:
                    d[nm] = k1.get(nm)
            out.append(d)
    out.append(dict(full[-1]))
    return out


def se_pts(n, w, h, e=2.0, ts=1.0, bs=1.0, t0=0.0, t1=2 * pi, closed=True):
    """Superellipse points (x, z).  e=2 ellipse, e>2 boxier.  ts/bs scale top/bottom width."""
    pts = []
    count = n if closed else n + 1
    for j in range(count):
        t = t0 + (t1 - t0) * j / n
        c, s = cos(t), sin(t)
        x = w * copysign(abs(c) ** (2.0 / e), c)
        z = h * copysign(abs(s) ** (2.0 / e), s)
        k = (z / h + 1) * 0.5 if h > 1e-9 else 0.5
        x *= bs + (ts - bs) * k
        pts.append((x, z))
    return pts


def circle_pts(n, r=1.0):
    return [(r * cos(2 * pi * j / n), r * sin(2 * pi * j / n)) for j in range(n)]


def round_poly(pts, radius, steps=4):
    """Fillet a closed 2D polygon (list of (a,b))."""
    p3 = fillet_path([(a, b, 0) for a, b in pts], radius, steps, closed=True)
    return [(p.x, p.y) for p in p3]


def airfoil_pts(n, chord, thick=0.12, camber=0.0, camber_pos=0.4):
    """NACA-4-like closed airfoil (x along chord 0..chord, y thickness).  Returns list (x, y)."""
    upper, lower = [], []
    for i in range(n + 1):
        b = pi * i / n
        x = (1 - cos(b)) / 2
        yt = 5 * thick * (0.2969 * sqrt(x) - 0.1260 * x - 0.3516 * x ** 2 + 0.2843 * x ** 3 - 0.1036 * x ** 4)
        if x < camber_pos:
            yc = camber / camber_pos ** 2 * (2 * camber_pos * x - x * x) if camber_pos else 0
        else:
            yc = camber / (1 - camber_pos) ** 2 * ((1 - 2 * camber_pos) + 2 * camber_pos * x - x * x)
        upper.append((x * chord, (yc + yt) * chord))
        lower.append((x * chord, (yc - yt) * chord))
    # closed loop: trailing edge -> upper -> leading edge -> lower -> trailing edge
    loop = list(reversed(upper)) + lower[1:-1]
    return loop


def grid_object(name, rings, closed_u=True, closed_v=False, cap0=False, cap1=False,
                mat_fn=None, mat="paint_primary", cap_mat=None, sharp_angle=None, merge=1e-5,
                recalc=True):
    """Quad grid from rings[i][j] (i along the path, j around the section).

    mat_fn(s, u) -> material name, with s/u the face-centre fractions (0..1) along/around.
    """
    ml = MatList()
    bm = bmesh.new()
    nv, nu = len(rings), len(rings[0])
    vs = [[bm.verts.new(V(p)) for p in ring] for ring in rings]
    ju = nu if closed_u else nu - 1
    iv = nv if closed_v else nv - 1
    for i in range(iv):
        i2 = (i + 1) % nv
        for j in range(ju):
            j2 = (j + 1) % nu
            quad = [vs[i][j], vs[i][j2], vs[i2][j2], vs[i2][j]]
            try:
                f = bm.faces.new(quad)
            except ValueError:
                continue
            name_m = mat_fn((i + 0.5) / iv, (j + 0.5) / ju) if mat_fn else mat
            f.material_index = ml.idx(name_m)
    if closed_u:
        for flag, ring, s in ((cap0, vs[0], 0.0), (cap1, vs[-1], 1.0)):
            if not flag:
                continue
            try:
                f = bm.faces.new(ring)
            except ValueError:
                continue
            f.material_index = ml.idx(cap_mat or (mat_fn(s, 0.5) if mat_fn else mat))
    if merge:
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=merge)
    return mesh_object(name, bm, ml, sharp_angle=sharp_angle, recalc=recalc)


def face_towards(obj, target):
    """Flip all faces of an open shell so that, on average, normals point to ``target``."""
    me = obj.data
    score = sum(p.normal.dot(V(target) - p.center) * p.area for p in me.polygons)
    if score < 0:
        bm = bmesh.new()
        bm.from_mesh(me)
        bmesh.ops.reverse_faces(bm, faces=bm.faces)
        bm.to_mesh(me)
        bm.free()


def set_origin(obj, point):
    """Move the object origin to ``point`` without moving its geometry."""
    p = V(point)
    obj.data.transform(Matrix.Translation(-p))
    obj.matrix_world = Matrix.Translation(p) @ obj.matrix_world


def _place(axis, pos, c1, c2, a, b):
    if axis == "y":
        return V((c1 + a, pos, c2 + b))
    if axis == "x":
        return V((pos, c1 + a, c2 + b))
    return V((c1 + a, c2 + b, pos))  # axis z: a->x, b->y


def loft(name, keys, axis="y", n=32, sub=4, t0=0.0, t1=2 * pi, closed=True, cap0=True, cap1=True,
         mat="paint_primary", mat_fn=None, cap_mat=None, sharp_angle=None, mtx=None):
    """Loft of superellipse sections.

    Each key: pos (coordinate along ``axis``), c1/c2 (section centre in the other two axes,
    for axis 'y' that is x/z), w, h, e (exponent), ts/bs (top/bottom width scale),
    zmin/zmax (clamp on the second section axis, absolute).
    """
    ks = interp_keys(keys, sub)
    rings = []
    for k in ks:
        pts = se_pts(n, max(k["w"], 1e-4), max(k["h"], 1e-4), k.get("e", 2.0), k.get("ts", 1.0),
                     k.get("bs", 1.0), t0, t1, closed)
        ring = []
        for a, b in pts:
            bb = k.get("c2", 0.0) + b
            if k.get("zmin") is not None:
                bb = max(bb, k["zmin"])
            if k.get("zmax") is not None:
                bb = min(bb, k["zmax"])
            ring.append(_place(axis, k["pos"], k.get("c1", 0.0), 0.0, a, bb))
        rings.append(ring)
    if mtx is not None:
        rings = [[mtx @ p for p in r] for r in rings]
    return grid_object(name, rings, closed_u=closed, cap0=cap0 and closed, cap1=cap1 and closed,
                       mat_fn=mat_fn, mat=mat, cap_mat=cap_mat, sharp_angle=sharp_angle)


def loft_profile(name, sections, mat="paint_primary", mat_fn=None, closed=True, cap0=True, cap1=True,
                 sharp_angle=None, cap_mat=None):
    """Loft through explicit 3D rings (all with the same point count)."""
    return grid_object(name, sections, closed_u=closed, cap0=cap0 and closed, cap1=cap1 and closed,
                       mat_fn=mat_fn, mat=mat, sharp_angle=sharp_angle, cap_mat=cap_mat)


def path_frames(path, closed=False, up=None):
    """Tangent / normal / binormal per path point.  ``up`` fixes the normal direction,
    otherwise parallel transport is used."""
    n = len(path)
    T = []
    for i in range(n):
        if closed:
            a, b = path[i - 1], path[(i + 1) % n]
        else:
            a, b = path[max(i - 1, 0)], path[min(i + 1, n - 1)]
        d = b - a
        T.append(d.normalized() if d.length > 1e-9 else V((0, 1, 0)))
    N = []
    for i in range(n):
        if up is not None:
            u = V(up[i]) if isinstance(up, list) else V(up)
            nn = u - T[i] * u.dot(T[i])
            if nn.length < 1e-6:
                nn = V((1, 0, 0)) - T[i] * T[i].x
            N.append(nn.normalized())
        elif i == 0:
            u = V((0, 0, 1)) if abs(T[0].z) < 0.9 else V((1, 0, 0))
            N.append((u - T[0] * u.dot(T[0])).normalized())
        else:
            q = T[i - 1].rotation_difference(T[i])
            nn = q @ N[-1]
            N.append((nn - T[i] * nn.dot(T[i])).normalized())
    B = [T[i].cross(N[i]) for i in range(n)]
    return T, N, B


def sweep(name, path, profile, radii=None, closed=False, up=None, caps=True, mat="chrome",
          mat_fn=None, cap_mat=None, sharp_angle=50.0, closed_profile=True):
    """Sweep a 2D profile [(n, b), ...] along a 3D path (profile scaled by radii[i])."""
    path = [V(p) for p in path]
    T, N, B = path_frames(path, closed, up)
    rings = []
    for i, p in enumerate(path):
        r = radii[i] if radii is not None else 1.0
        rings.append([p + N[i] * (a * r) + B[i] * (b * r) for a, b in profile])
    return grid_object(name, rings, closed_u=closed_profile, closed_v=closed,
                       cap0=caps and not closed, cap1=caps and not closed,
                       mat_fn=mat_fn, mat=mat, cap_mat=cap_mat, sharp_angle=sharp_angle)


def tube(name, pts, r, mat="chrome", fillet=0.06, n=12, closed=False, caps=True, radii=None,
         steps=5, mat_fn=None, cap_mat=None, smooth=0):
    """Round tube along a polyline with filleted corners (or Catmull-Rom if smooth>0)."""
    if smooth:
        path = smooth_path(pts, smooth, closed)
    else:
        path = fillet_path(pts, fillet, steps, closed) if fillet else [V(p) for p in pts]
    if radii is None:
        scale = [1.0] * len(path)
    elif smooth:
        scale = [p.x for p in smooth_path([(x, 0, 0) for x in radii], smooth, closed)]
    else:
        # map radii (given per input point) onto the filleted path by arc length
        src = [V(p) for p in pts]
        cum = [0.0]
        for a, b in zip(src, src[1:]):
            cum.append(cum[-1] + (b - a).length)
        cum2 = [0.0]
        for a, b in zip(path, path[1:]):
            cum2.append(cum2[-1] + (b - a).length)
        scale = []
        for c in cum2:
            t = c / (cum2[-1] or 1.0) * cum[-1]
            k = 0
            while k < len(cum) - 2 and t > cum[k + 1]:
                k += 1
            f = (t - cum[k]) / max(cum[k + 1] - cum[k], 1e-9)
            scale.append(radii[k] * (1 - f) + radii[k + 1] * f)
    return sweep(name, path, circle_pts(n, r), radii=scale, closed=closed, caps=caps, mat=mat,
                 mat_fn=mat_fn, cap_mat=cap_mat)


def torus(name, R, r, mtx, mat="chrome", n_major=48, n_minor=12, mat_fn=None, rx=None):
    """Torus in the local XY plane (axis local Z) -- rx optionally makes the ring elliptic."""
    rx = R if rx is None else rx
    path = [mtx @ V((rx * cos(2 * pi * i / n_major), R * sin(2 * pi * i / n_major), 0)) for i in range(n_major)]
    axis = (mtx.to_3x3() @ V((0, 0, 1))).normalized()
    return sweep(name, path, circle_pts(n_minor, r), closed=True, up=axis, mat=mat, mat_fn=mat_fn)


def lathe(name, prof, segs=64, mat="rim", mat_fn=None, closed=False, mtx=None, sharp_angle=40.0,
          a0=0.0, a1=2 * pi):
    """Revolve profile [(x, r), ...] around the X axis.  mat_fn(i_segment) -> material."""
    full = abs(a1 - a0 - 2 * pi) < 1e-6
    count = segs if full else segs + 1
    angles = [a0 + (a1 - a0) * j / segs for j in range(count)]
    rings = [[V((x, r * cos(a), r * sin(a))) for a in angles] for x, r in prof]
    if mtx is not None:
        rings = [[mtx @ p for p in ring] for ring in rings]
    nseg = len(prof) if closed else len(prof) - 1
    fn = (lambda s, u: mat_fn(min(int(s * nseg), nseg - 1))) if mat_fn else None
    return grid_object(name, rings, closed_u=full, closed_v=closed, mat_fn=fn, mat=mat,
                       sharp_angle=sharp_angle)


def rbox(name, size, loc=(0, 0, 0), mat="paint_primary", bevel=0.01, segs=3, rot=(0, 0, 0),
         taper=(1.0, 1.0), mtx=None, shear_y=0.0):
    """Rounded box. taper scales the top (+Z) face in x/y; shear_y slides the top along Y."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        x, y, z = v.co
        if z > 0:
            x *= taper[0]
            y *= taper[1]
            y += shear_y / max(size[1], 1e-6)
        v.co = V((x * size[0], y * size[1], z * size[2]))
    m = mtx_of(loc, rot)
    if mtx is not None:
        m = mtx @ m
    ml = MatList()
    ml.idx(mat)
    obj = mesh_object(name, bm, ml, mtx=m)
    if bevel > 0:
        add_bevel(obj, bevel, segs)
        add_wn(obj)
    return obj


def cyl(name, r, depth, loc=(0, 0, 0), direction=(0, 0, 1), mat="metal_dark", segs=32, r2=None,
        bevel=0.0, bsegs=2, cap_mat=None, mtx=None):
    """Cylinder/cone centred at loc along ``direction``."""
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=segs, radius1=r,
                          radius2=r if r2 is None else r2, depth=depth)
    ml = MatList()
    ml.idx(mat)
    if cap_mat:
        ci = ml.idx(cap_mat)
        for f in bm.faces:
            if abs(f.normal.z) > 0.99 and len(f.verts) > 4:
                f.material_index = ci
    m = Matrix.Translation(V(loc)) @ axis_matrix(direction)
    if mtx is not None:
        m = mtx @ m
    if bevel > 0:
        obj = mesh_object(name, bm, ml, mtx=m)
        add_bevel(obj, bevel, bsegs)
        add_wn(obj)
    else:
        obj = mesh_object(name, bm, ml, mtx=m, sharp_angle=40.0)
    return obj


def hexnut(name, r, depth, loc, direction, mat="chrome", mtx=None):
    return cyl(name, r, depth, loc, direction, mat=mat, segs=6, bevel=r * 0.18, bsegs=1, mtx=mtx)


def sphere(name, r, loc=(0, 0, 0), scale=(1, 1, 1), mat="chrome", segs=24, rings=12, mtx=None,
           rot=(0, 0, 0)):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=segs, v_segments=rings, radius=r)
    for v in bm.verts:
        v.co = V((v.co.x * scale[0], v.co.y * scale[1], v.co.z * scale[2]))
    m = mtx_of(loc, rot)
    if mtx is not None:
        m = mtx @ m
    ml = MatList()
    ml.idx(mat)
    return mesh_object(name, bm, ml, mtx=m)


def slab(name, pts2d, thickness, origin, u_axis, v_axis, mat="paint_secondary", edge_mat=None,
         bevel=0.004, segs=2, mtx=None):
    """Extrude a 2D polygon (in the plane spanned by u_axis/v_axis) by ``thickness``
    (centred on the plane).  edge_mat colours the side walls."""
    O, U, Vv = V(origin), V(u_axis).normalized(), V(v_axis).normalized()
    W = U.cross(Vv).normalized()
    bm = bmesh.new()
    ml = MatList()
    mi = ml.idx(mat)
    ei = ml.idx(edge_mat) if edge_mat else mi
    bot = [bm.verts.new(O + U * a + Vv * b - W * thickness / 2) for a, b in pts2d]
    top = [bm.verts.new(O + U * a + Vv * b + W * thickness / 2) for a, b in pts2d]
    f0 = bm.faces.new(list(reversed(bot)))
    f0.material_index = mi
    f1 = bm.faces.new(top)
    f1.material_index = mi
    n = len(pts2d)
    for i in range(n):
        j = (i + 1) % n
        f = bm.faces.new((bot[i], bot[j], top[j], top[i]))
        f.material_index = ei
    obj = mesh_object(name, bm, ml, mtx=mtx)
    if bevel > 0:
        add_bevel(obj, bevel, segs, angle=40)
        add_wn(obj)
    return obj


def empty(name, loc, scale=1.0):
    e = bpy.data.objects.new(name, None)
    e.empty_display_type = "ARROWS"
    e.empty_display_size = 0.12
    e.location = V(loc)
    e.scale = (scale, scale, scale)
    bpy.context.scene.collection.objects.link(e)
    return e


def bake(obj):
    """Apply all modifiers (and convert to a plain mesh)."""
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    me = bpy.data.meshes.new_from_object(ev, preserve_all_data_layers=True, depsgraph=dg)
    obj.modifiers.clear()
    old = obj.data
    obj.data = me
    if old.users == 0:
        bpy.data.meshes.remove(old)


def join(objs, name):
    """Bake + join a list of objects into a single mesh object called ``name``."""
    objs = [o for o in objs if o.type == "MESH"]
    for o in objs:
        bake(o)
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    target = objs[0]
    bpy.context.view_layer.objects.active = target
    if len(objs) > 1:
        bpy.ops.object.join()
    target.name = name
    target.data.name = name
    return target


def tri_count(obj):
    me = obj.data
    me.calc_loop_triangles()
    return len(me.loop_triangles)


def clear_scene():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    for me in list(bpy.data.meshes):
        if me.users == 0:
            bpy.data.meshes.remove(me)
    _groups[:] = [[]]


def export_glb(name, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, name + ".glb")
    bpy.ops.object.select_all(action="DESELECT")
    for o in bpy.context.scene.objects:
        o.select_set(True)
    bpy.ops.export_scene.gltf(
        filepath=path, export_format="GLB", use_selection=True, export_apply=True,
        export_cameras=False, export_lights=False, export_extras=True, export_yup=True,
        export_normals=True, export_materials="EXPORT",
    )
    return path


REPORT = {}


def finish(part_name, main_objs, extra=None):
    """Join the main geometry into one mesh named after the part. ``extra`` = dict of
    name -> list of objects that must stay separate objects (steering wheel, head)."""
    out = {part_name: join(main_objs, part_name)}
    for nm, objs in (extra or {}).items():
        out[nm] = join(objs, nm)
    REPORT[part_name] = {k: tri_count(o) for k, o in out.items()}
    return out


# 3. WHEELS  (origin = axle centre, axle along X, outer face toward +X, radius 0.28)
def X_AXIS_MTX(x=0.0):
    """Matrix that maps the local XY plane onto the wheel plane (YZ) at offset x."""
    return Matrix.Translation((x, 0, 0)) @ Matrix.Rotation(radians(90), 4, "Y")


def mirror_profile(half):
    """half profile [(x, r)] from tread centre (x=0) toward +X -> full profile -X..+X."""
    left = [(-x, r) for x, r in reversed(half) if x > 0]
    return left + half


def tire(name, half_profile, accent_band=None, segs=64):
    """Lathe a tire; faces whose mid radius lies in accent_band on the +X side get paint_accent."""
    prof = mirror_profile(half_profile)

    def mf(i):
        (x0, r0), (x1, r1) = prof[i], prof[i + 1]
        if accent_band and x0 > 0 and x1 > 0 and accent_band[0] <= (r0 + r1) / 2 <= accent_band[1]:
            return "paint_accent"
        return "rubber"
    return lathe(name, prof, segs, mat_fn=mf, sharp_angle=60.0)


def wheel_ring(name, x, R, r, mat, n_major=64, n_minor=10):
    return torus(name, R, r, X_AXIS_MTX(x), mat=mat, n_major=n_major, n_minor=n_minor)


def radial_copies(count, builder, phase=0.0):
    """Call builder(mtx, k) for count rotations about the wheel axle (X)."""
    for k in range(count):
        builder(Matrix.Rotation(phase + 2 * pi * k / count, 4, "X"), k)


def spoke_loft(name, keys, mtx, mat="rim", n=12):
    """Spoke built along local +Z (radial). keys: pos(radius), c1(x dish), c2(tangential), w, h."""
    return loft(name, keys, axis="z", n=n, sub=3, mat=mat, sharp_angle=55.0, mtx=mtx)


def build_wheel_classic():
    """Slick racing tire + 10-spoke (5 twin spokes) dished rim."""
    half = [(0.000, 0.2800), (0.040, 0.2797), (0.070, 0.2786), (0.090, 0.2766), (0.104, 0.2732),
            (0.114, 0.2672), (0.120, 0.2585), (0.1225, 0.2475), (0.1222, 0.2370), (0.1232, 0.2340),
            (0.1232, 0.2240), (0.1205, 0.2205), (0.1170, 0.2120), (0.1120, 0.2030), (0.1060, 0.1960),
            (0.1000, 0.1915)]
    with Group() as g:
        tire("tire", half, accent_band=(0.2235, 0.2345))
        lathe("barrel", [(-0.100, 0.180), (0.100, 0.180), (0.100, 0.190), (-0.100, 0.190)], 64,
              mat="rim", closed=True)
        wheel_ring("lip_out", 0.101, 0.191, 0.0075, "chrome")
        wheel_ring("lip_in", -0.101, 0.191, 0.0065, "rim")
        cyl("backplate", 0.181, 0.006, (-0.035, 0, 0), (1, 0, 0), mat="metal_dark", segs=48)
        cyl("brake_disc", 0.135, 0.010, (-0.055, 0, 0), (1, 0, 0), mat="chrome", segs=48, bevel=0.002)

        def twin(mtx, k):
            for side in (-1, 1):
                keys = [dict(pos=0.040, c1=0.074, c2=side * 0.010, w=0.013, h=0.014, e=3.0),
                        dict(pos=0.090, c1=0.083, c2=side * 0.020, w=0.0115, h=0.0125),
                        dict(pos=0.150, c1=0.091, c2=side * 0.029, w=0.0105, h=0.0110),
                        dict(pos=0.186, c1=0.095, c2=side * 0.033, w=0.0100, h=0.0120)]
                spoke_loft("spoke", keys, mtx)
        radial_copies(5, twin)
        cyl("hub", 0.056, 0.045, (0.075, 0, 0), (1, 0, 0), mat="rim", segs=40, bevel=0.006)
        cyl("hub_ring", 0.044, 0.012, (0.100, 0, 0), (1, 0, 0), mat="paint_accent", segs=40, bevel=0.003)
        sphere("cap", 0.028, (0.104, 0, 0), scale=(0.7, 1, 1), mat="chrome", segs=24, rings=12)
        radial_copies(5, lambda m, k: hexnut("lug", 0.0085, 0.014, m @ V((0.104, 0, 0.040)),
                                            (1, 0, 0), mat="chrome"), phase=pi / 5)
    return finish("wheel_classic", g.objs)


def build_wheel_offroad():
    """Knobby deep-tread tire + 6-spoke beadlock rim."""
    half = [(0.000, 0.2520), (0.060, 0.2515), (0.090, 0.2500), (0.108, 0.2460), (0.119, 0.2380),
            (0.125, 0.2260), (0.127, 0.2100), (0.126, 0.1950), (0.122, 0.1800), (0.116, 0.1680),
            (0.108, 0.1600), (0.100, 0.1550)]
    with Group() as g:
        tire("carcass", half, segs=48)
        steps = 14
        half_step = pi / steps
        for k in range(steps):
            a = 2 * pi * k / steps
            for side in (-1, 1):
                ang = a + (half_step if side > 0 else 0.0)
                rbox("knob_c", (0.060, 0.056, 0.032), (side * 0.040, 0, 0.264), mat="rubber",
                     bevel=0.006, segs=2, rot=(0, 0, side * 14), taper=(0.92, 0.9),
                     mtx=Matrix.Rotation(ang, 4, "X"))
                ang2 = a + (0 if side > 0 else half_step) + half_step * 0.5
                rbox("knob_s", (0.050, 0.052, 0.030), (side * 0.099, 0, 0.250), mat="rubber",
                     bevel=0.007, segs=1, rot=(0, side * 38, 0), taper=(0.9, 0.9),
                     mtx=Matrix.Rotation(ang2, 4, "X"))
        lathe("barrel", [(-0.104, 0.140), (0.104, 0.140), (0.104, 0.152), (-0.104, 0.152)], 48,
              mat="rim", closed=True)
        lathe("beadlock", [(0.094, 0.126), (0.121, 0.126), (0.127, 0.132), (0.127, 0.168),
                           (0.121, 0.174), (0.094, 0.174)], 48, mat="metal_dark", closed=True)
        radial_copies(12, lambda m, k: hexnut("bolt", 0.0062, 0.010, m @ V((0.129, 0, 0.150)),
                                             (1, 0, 0), mat="chrome"))
        cyl("backplate", 0.142, 0.006, (-0.03, 0, 0), (1, 0, 0), mat="metal_dark", segs=48)

        def spoke(mtx, k):
            keys = [dict(pos=0.045, c1=0.070, c2=0.0, w=0.016, h=0.026, e=4.0),
                    dict(pos=0.090, c1=0.080, w=0.014, h=0.021),
                    dict(pos=0.128, c1=0.090, w=0.013, h=0.019),
                    dict(pos=0.142, c1=0.092, w=0.012, h=0.022)]
            spoke_loft("spoke", keys, mtx, n=16)
        radial_copies(6, spoke)
        cyl("hub", 0.060, 0.050, (0.075, 0, 0), (1, 0, 0), mat="rim", segs=40, bevel=0.007)
        sphere("cap", 0.036, (0.100, 0, 0), scale=(0.75, 1, 1), mat="chrome", segs=24, rings=12)
        radial_copies(6, lambda m, k: hexnut("lug", 0.0090, 0.016, m @ V((0.102, 0, 0.046)),
                                            (1, 0, 0), mat="metal_dark"), phase=pi / 6)
    return finish("wheel_offroad", g.objs)


def build_wheel_turbine():
    """Low-profile tire + turbine-fan disc rim with chrome spinner and glow ring."""
    half = [(0.000, 0.2800), (0.026, 0.2799), (0.029, 0.2752), (0.036, 0.2752), (0.039, 0.2798),
            (0.070, 0.2792), (0.090, 0.2780), (0.104, 0.2758), (0.114, 0.2715), (0.120, 0.2640),
            (0.1225, 0.2545), (0.1235, 0.2470), (0.1235, 0.2400), (0.121, 0.2340), (0.116, 0.2275),
            (0.110, 0.2230), (0.104, 0.2205)]
    with Group() as g:
        tire("tire", half, accent_band=(0.239, 0.248), segs=64)
        lathe("barrel", [(-0.100, 0.206), (0.100, 0.206), (0.100, 0.219), (-0.100, 0.219)], 64,
              mat="rim", closed=True)
        wheel_ring("lip_out", 0.102, 0.218, 0.0065, "chrome")
        lathe("shroud", [(0.035, 0.192), (0.098, 0.192), (0.106, 0.197), (0.106, 0.206),
                         (0.035, 0.206)], 64, mat="rim", closed=True)
        cyl("backplate", 0.200, 0.008, (0.030, 0, 0), (1, 0, 0), mat="metal_dark", segs=56)
        nblades = 18
        for k in range(nblades):
            base = 2 * pi * k / nblades
            rings = []
            nr = 7
            for i in range(nr):
                t = i / (nr - 1)
                rad = 0.066 + t * (0.194 - 0.066)
                pitch = radians(55 - 25 * t)
                chord = 0.050 + 0.012 * t
                rot = Matrix.Rotation(base + 0.35 * t * t, 3, "X")
                ring = []
                for a, b in se_pts(10, chord / 2, 0.0035, 2.4):
                    lx = a * cos(pitch) - b * sin(pitch)
                    lt = a * sin(pitch) + b * cos(pitch)
                    ring.append(rot @ V((0.068 + lx, lt, rad)))
                rings.append(ring)
            loft_profile("blade", rings, mat="rim", sharp_angle=60.0)
        lathe("spinner", [(0.030, 0.0705), (0.070, 0.0690), (0.098, 0.0580), (0.120, 0.0400),
                          (0.134, 0.0200), (0.140, 0.0060), (0.141, 0.0)], 48, mat="chrome",
              sharp_angle=50.0)
        wheel_ring("glow", 0.074, 0.072, 0.0045, "emissive_light", n_major=48, n_minor=8)
    return finish("wheel_turbine", g.objs)


class KartSpec:
    """Layout of one body.  front/rear = (x, y, wheel scale); points are Blender coords."""

    def __init__(self, front, rear, hip, spoiler, exhaust_l, exhaust_r):
        self.front, self.rear = front, rear
        self.hip = V(hip)
        self.spoiler = V(spoiler)
        self.exhaust_l, self.exhaust_r = V(exhaust_l), V(exhaust_r)

    @property
    def hub(self):
        return self.hip + STEER_OFFSET

    @property
    def column_dir(self):
        return V((0.0, cos(STEER_TILT), sin(STEER_TILT)))

    def wheel(self, axle, side):
        x, y, s = self.front if axle == "front" else self.rear
        return V((side * x, y, WHEEL_NOMINAL_RADIUS * s)), s

    def inner_face_x(self, axle):
        x, y, s = self.front if axle == "front" else self.rear
        return x - WHEEL_NOMINAL_WIDTH * s / 2


def add_sockets(spec):
    """Create the contract empties (unparented, identity rotation)."""
    for nm, axle, side in (("fl", "front", -1), ("fr", "front", 1), ("rl", "rear", -1), ("rr", "rear", 1)):
        c, s = spec.wheel(axle, side)
        empty("socket_wheel_" + nm, c, s)
    empty("socket_spoiler", spec.spoiler)
    empty("socket_driver", spec.hip)
    empty("socket_exhaust_l", spec.exhaust_l)
    empty("socket_exhaust_r", spec.exhaust_r)


def build_steering_wheel(rim_mat="carbon", grip_mat="rubber", centre_mat="paint_primary", display=True):
    """Steering wheel in LOCAL coords: hub at origin, rim in XZ plane, column toward +Y.
    ``display=False`` drops the digital display/paddles (retro wheels)."""
    with Group() as g:
        n = 64
        pts = se_pts(n, STEER_GRIP_X, 0.128, 2.7)
        path = [V((x, 0.0, z)) for x, z in pts]
        radii = []
        for j in range(n):
            c = cos(2 * pi * j / n)
            radii.append(1.22 if abs(c) > 0.62 else 1.0)

        def rim_mf(s, u):
            a = 2 * pi * s
            if abs(cos(a)) > 0.62:
                return grip_mat
            if abs(s - 0.25) < 0.02:
                return "paint_accent"
            return rim_mat
        sweep("sw_rim", path, se_pts(12, 0.016, 0.0125, 2.2), radii=radii, closed=True,
              up=(0, 1, 0), mat_fn=rim_mf, sharp_angle=None)
        prof = se_pts(10, 0.0075, 0.021, 3.0)
        for side in (-1, 1):
            sp = smooth_path([(side * 0.035, 0.034, 0.0), (side * 0.09, 0.018, -0.004),
                              (side * 0.158, 0.002, 0.0)], 4)
            sweep("sw_spoke", sp, prof, radii=[1.15 - 0.3 * i / (len(sp) - 1) for i in range(len(sp))],
                  up=(0, 1, 0), mat=rim_mat, sharp_angle=None)
        sp = smooth_path([(0, 0.034, -0.03), (0, 0.016, -0.08), (0, 0.002, -0.118)], 4)
        sweep("sw_spoke_b", sp, prof, up=(0, 1, 0), mat=rim_mat, sharp_angle=None)
        cyl("sw_hub", 0.047, 0.05, (0, 0.04, 0), (0, 1, 0), mat=rim_mat, segs=32, bevel=0.008)
        cyl("sw_ring", 0.037, 0.012, (0, 0.012, 0), (0, 1, 0), mat="paint_accent", segs=32, bevel=0.003)
        cyl("sw_badge", 0.027, 0.012, (0, 0.006, 0), (0, 1, 0), mat=centre_mat, segs=32, bevel=0.003)
        if display:
            rbox("sw_display", (0.090, 0.024, 0.036), (0, 0.022, 0.056), mat="carbon", bevel=0.008)
            rbox("sw_screen", (0.068, 0.004, 0.022), (0, 0.009, 0.057), mat="emissive_light", bevel=0.002,
                 segs=1)
            for side in (-1, 1):
                rbox("sw_paddle", (0.032, 0.008, 0.055), (side * 0.085, 0.05, 0.03), mat="metal_dark",
                     bevel=0.003, rot=(0, side * -20, 0))
        else:
            torus("sw_horn_ring", 0.06, 0.004, mtx_of((0, 0.004, 0), (90, 0, 0)), mat="chrome",
                  n_major=32, n_minor=6)
    return g.objs


def place_steering(obj, spec):
    obj.matrix_world = Matrix.Translation(spec.hub) @ Matrix.Rotation(STEER_TILT, 4, "X")


def build_column(spec, mat="chrome"):
    d = spec.column_dir
    h = spec.hub
    tube("column", [h + d * 0.05, h + d * 0.46], 0.0145, mat=mat, fillet=0)
    cyl("column_collar", 0.024, 0.04, h + d * 0.085, d, mat="metal_dark", bevel=0.004)
    cyl("column_clamp", 0.022, 0.03, h + d * 0.30, d, mat="metal_dark", bevel=0.004)


def build_seat(spec, outer_mat="carbon", width=1.0, thickness=0.022):
    """Bucket seat swept along the driver's back; fabric inside, ``outer_mat`` shell."""
    hip = spec.hip
    key_pts = [(0.17, -0.095), (0.07, -0.125), (-0.06, -0.132), (-0.145, -0.09), (-0.180, 0.03),
               (-0.210, 0.18), (-0.240, 0.34)]
    widths = [0.17, 0.19, 0.20, 0.205, 0.21, 0.21, 0.19]
    depths = [0.035, 0.06, 0.075, 0.10, 0.12, 0.12, 0.085]
    path = smooth_path([hip + V((0, y, z)) for y, z in key_pts], 4)
    wv = [p.x for p in smooth_path([(w, 0, 0) for w in widths], 4)]
    dv = [p.x for p in smooth_path([(d, 0, 0) for d in depths], 4)]
    T, N, B = path_frames(path, up=(1, 0, 0))
    rings = []
    m = 16
    for i, p in enumerate(path):
        ring = []
        for k in range(m + 1):
            a = pi * k / m
            c, s = cos(a), sin(a)
            x = wv[i] * width * copysign(abs(c) ** (2 / 3.0), c)
            b = dv[i] * (1 - abs(s) ** (2 / 3.0))
            ring.append(p + N[i] * x + B[i] * b)
        rings.append(ring)
    obj = grid_object("seat", rings, closed_u=False, mat="seat_fabric")
    face_towards(obj, hip + V((0, 0.05, 0.25)))
    obj.data.materials.append(MAT[outer_mat])
    sol = add_solidify(obj, thickness, offset=-1)
    sol.material_offset = 1
    sol.material_offset_rim = 1
    add_subsurf(obj, 1)
    return obj


def build_pedals(spec):
    for side in (-1, 1):
        p = spec.hip + V((side * 0.10, 0.95, -0.10))
        rbox("pedal", (0.055, 0.014, 0.11), p, mat="metal_dark", bevel=0.004, rot=(-30, 0, 0))


def build_front_uprights(spec, bracket_mat="metal_dark", beam_mat="chrome", tie_z=None):
    """King-pins, stub axles, hubs, front axle beam and tie rods."""
    x, y, s = spec.front
    r = WHEEL_NOMINAL_RADIUS * s
    inner = spec.inner_face_x("front")
    kx = inner - 0.04
    for side in (-1, 1):
        cyl("kingpin", 0.019, 0.13, (side * kx, y, r), (0, 0, 1), mat=bracket_mat, bevel=0.004)
        for dz in (-0.075, 0.075):
            rbox("c_bracket", (0.05, 0.05, 0.022), (side * (kx - 0.02), y, r + dz), mat=bracket_mat,
                 bevel=0.006)
        cyl("stub_axle", 0.017, inner + 0.05 - kx, (side * (kx + inner + 0.05) / 2, y, r), (1, 0, 0),
            mat="chrome")
        cyl("hub_flange", 0.05, 0.018, (side * (inner - 0.006), y, r), (1, 0, 0), mat=bracket_mat,
            bevel=0.004)
        cyl("hub_nut", 0.018, 0.02, (side * (inner + 0.003), y, r), (1, 0, 0), mat="chrome", segs=6)
        rbox("steer_arm", (0.02, 0.075, 0.016), (side * (kx - 0.005), y - 0.045, r - 0.06),
             mat=bracket_mat, bevel=0.005)
        tz = tie_z if tie_z is not None else r - 0.06
        tube("tie_rod", [(side * (kx - 0.01), y - 0.08, tz), (side * 0.05, spec.hub.y + 0.36, tz)],
             0.0075, mat="chrome", fillet=0)
    tube("front_beam", [(-(kx - 0.02), y, r - 0.075), (-0.18, y, r - 0.14), (0.18, y, r - 0.14),
                        ((kx - 0.02), y, r - 0.075)], 0.019, mat=beam_mat, fillet=0.06)


def gear_pts(teeth, r_out, r_in):
    pts = []
    for k in range(teeth * 4):
        a = 2 * pi * k / (teeth * 4)
        rr = r_out if (k % 4) in (1, 2) else r_in
        pts.append((rr * cos(a), rr * sin(a)))
    return pts


def build_rear_axle(spec, axle_mat="chrome", hanger_mat="metal_dark", sprocket=True, brake=True,
                    hanger_x=0.30):
    x, y, s = spec.rear
    r = WHEEL_NOMINAL_RADIUS * s
    inner = spec.inner_face_x("rear")
    cyl("rear_axle", 0.024, 2 * (inner + 0.03), (0, y, r), (1, 0, 0), mat=axle_mat, segs=24)
    for side in (-1, 1):
        cyl("rear_hub", 0.056, 0.05, (side * (inner - 0.02), y, r), (1, 0, 0), mat=hanger_mat,
            bevel=0.006)
        cyl("rear_hub_nut", 0.02, 0.02, (side * (inner + 0.005), y, r), (1, 0, 0), mat="chrome", segs=6)
        rbox("bearing_hanger", (0.034, 0.10, r - 0.03), (side * hanger_x, y, (r - 0.03) / 2 + 0.04),
             mat=hanger_mat, bevel=0.008, taper=(1.0, 0.7))
        cyl("bearing", 0.046, 0.05, (side * hanger_x, y, r), (1, 0, 0), mat=hanger_mat, bevel=0.006)
        cyl("bearing_ring", 0.032, 0.056, (side * hanger_x, y, r), (1, 0, 0), mat="chrome", bevel=0.002)
    if brake:
        cyl("brake_disc", 0.092, 0.010, (-0.17, y, r), (1, 0, 0), mat="chrome", segs=48, bevel=0.002)
        cyl("brake_hub", 0.04, 0.03, (-0.17, y, r), (1, 0, 0), mat="metal_dark", bevel=0.004)
        rbox("caliper", (0.04, 0.07, 0.05), (-0.17, y + 0.055, r + 0.055), mat="paint_accent",
             bevel=0.012, rot=(-35, 0, 0))
    if sprocket:
        slab("sprocket", gear_pts(30, 0.08, 0.073), 0.008, (0.17, y, r), (0, 1, 0), (0, 0, 1),
             mat="metal_dark", bevel=0.002, segs=1)
        cyl("sprocket_hub", 0.035, 0.03, (0.17, y, r), (1, 0, 0), mat="chrome", bevel=0.003)


def exhaust_pipe(points, r, tip_len=0.08, tip_r=None, mat="chrome", inner_mat="metal_dark"):
    """Smooth exhaust header ending in a flared tip.  Returns the tip end point."""
    path = smooth_path(points, 5)
    tube("exhaust", points, r, mat=mat, smooth=5, n=14)
    end = path[-1]
    d = (path[-1] - path[-2]).normalized()
    tr = tip_r or r * 1.45
    lathe_m = Matrix.Translation(end) @ V((1, 0, 0)).rotation_difference(d).to_matrix().to_4x4()
    lathe("exhaust_tip", [(-0.01, r * 0.98), (0.0, tr * 0.92), (tip_len * 0.9, tr), (tip_len, tr * 1.04),
                          (tip_len + 0.004, tr * 0.86), (tip_len - 0.01, tr * 0.80)], 24, mat=mat,
          mtx=lathe_m, sharp_angle=45)
    cyl("exhaust_core", tr * 0.80, 0.01, end + d * (tip_len - 0.02), d, mat=inner_mat, segs=24)
    return end + d * tip_len


def stripe_fn(base, bands, s_range=(0.0, 1.0)):
    """Material function for lofts: bands = [(u0, u1, material), ...] applied when s in s_range."""
    def fn(s, u):
        if s_range[0] <= s <= s_range[1]:
            for u0, u1, m in bands:
                if u0 <= u <= u1:
                    return m
        return base
    return fn


VORTEX = KartSpec(front=(0.58, 0.63, 0.90), rear=(0.58, -0.63, 1.05), hip=(0.0, -0.22, 0.27),
                  spoiler=(0.0, -0.80, 0.50), exhaust_l=(-0.2, -1.0, 0.37), exhaust_r=(0.2, -1.0, 0.37))


def build_body_vortex():
    """Sleek classic racing kart: chrome tube chassis, nose cone, side pods, bucket seat,
    exposed finned engine with twin exhausts, wide rear bumper."""
    sp = VORTEX
    with Group() as body:
        for s in (-1, 1):
            tube("rail", [(s * 0.15, 0.90, 0.115), (s * 0.24, 0.74, 0.085), (s * 0.29, 0.40, 0.07),
                          (s * 0.30, -0.30, 0.07), (s * 0.33, -0.55, 0.09), (s * 0.30, -0.82, 0.13),
                          (s * 0.16, -0.90, 0.15)], 0.016, fillet=0.09)
            tube("pod_stay", [(s * 0.29, 0.25, 0.07), (s * 0.40, 0.25, 0.10)], 0.012, fillet=0)
            tube("pod_stay", [(s * 0.30, -0.15, 0.07), (s * 0.40, -0.15, 0.10)], 0.012, fillet=0)
            tube("bumper_stay", [(s * 0.31, -0.80, 0.13), (s * 0.40, -0.93, 0.16)], 0.013, fillet=0)
        for yy, zz in ((0.25, 0.07), (-0.20, 0.07)):
            tube("cross", [(-0.29, yy, zz), (0.29, yy, zz)], 0.015, fillet=0)
        tube("cross_rear", [(-0.30, -0.82, 0.13), (0.30, -0.82, 0.13)], 0.015, fillet=0)
        tube("nose_hoop", [(-0.15, 0.90, 0.115), (-0.10, 1.0, 0.14), (0.10, 1.0, 0.14), (0.15, 0.90, 0.115)],
             0.014, fillet=0.05)
        rbox("floor_tray", (0.54, 0.84, 0.012), (0, 0.10, 0.058), mat="carbon", bevel=0.004, segs=2)
        build_front_uprights(sp)
        build_rear_axle(sp)
        build_pedals(sp)

        loft("front_fairing", [
            dict(pos=1.045, c2=0.13, w=0.30, h=0.030, e=3.0, ts=0.85),
            dict(pos=1.035, w=0.52, h=0.060),
            dict(pos=1.000, w=0.61, h=0.080),
            dict(pos=0.950, w=0.63, h=0.085),
            dict(pos=0.905, w=0.61, h=0.075),
            dict(pos=0.890, w=0.52, h=0.050),
        ], n=40, sub=3, mat_fn=stripe_fn("paint_primary", [(0.52, 0.98, "carbon"),
                                                          (0.232, 0.268, "paint_secondary"),
                                                          (0.222, 0.232, "paint_accent"),
                                                          (0.268, 0.278, "paint_accent")]))
        nose = loft("nose_panel", [
            dict(pos=1.010, c2=0.105, w=0.17, h=0.06, e=2.6),
            dict(pos=0.950, w=0.215, h=0.13),
            dict(pos=0.850, w=0.255, h=0.22),
            dict(pos=0.720, w=0.272, h=0.30),
            dict(pos=0.580, w=0.270, h=0.345),
            dict(pos=0.470, w=0.255, h=0.360),
            dict(pos=0.425, w=0.235, h=0.350),
        ], n=32, sub=3, t0=0.0, t1=pi, closed=False,
            mat_fn=stripe_fn("paint_primary", [(0.44, 0.56, "paint_secondary"),
                                               (0.405, 0.44, "paint_accent"), (0.56, 0.595, "paint_accent")]))
        add_solidify(nose, 0.014, offset=0.0)
        add_subsurf(nose, 1)
        for s in (-1, 1):
            sphere("headlight", 0.032, (s * 0.115, 0.952, 0.215), scale=(1.3, 0.55, 0.7),
                   mat="emissive_light", rot=(-35, 0, s * -12))
            torus("headlight_bezel", 0.031, 0.006,
                  mtx_of((s * 0.115, 0.955, 0.215), (55, 0, s * -12), scale=(1.3, 0.72, 1.0)),
                  mat="chrome", n_major=32, n_minor=8)

        for s in (-1, 1):
            m = None if s > 0 else mirror_x()
            loft("side_pod", [
                dict(pos=0.37, c1=0.47, c2=0.13, w=0.07, h=0.04, e=3.4, ts=0.72, zmin=0.05),
                dict(pos=0.34, w=0.12, h=0.075, c2=0.135),
                dict(pos=0.24, w=0.14, h=0.095, c2=0.145),
                dict(pos=0.00, w=0.148, h=0.118, c2=0.16),
                dict(pos=-0.18, w=0.142, h=0.13, c2=0.17),
                dict(pos=-0.27, w=0.12, h=0.115),
                dict(pos=-0.305, w=0.06, h=0.06),
            ], n=32, sub=3, mtx=m,
                mat_fn=stripe_fn("paint_primary", [(0.06, 0.17, "paint_secondary"), (0.17, 0.20, "paint_accent"),
                                                   (0.62, 0.88, "carbon")], (0.12, 0.92)))
            sphere("pod_intake", 0.06, (s * 0.47, 0.352, 0.16), scale=(1.4, 0.35, 0.9), mat="metal_dark")
            for k in range(3):
                rbox("pod_vent", (0.10, 0.012, 0.008), (s * 0.47, 0.357, 0.13 + k * 0.025), mat="chrome",
                     bevel=0.003, segs=1)

        loft("rear_bumper", [
            dict(pos=-0.930, c2=0.165, w=0.52, h=0.045, e=3.5, ts=0.9),
            dict(pos=-0.945, w=0.63, h=0.075),
            dict(pos=-0.990, w=0.665, h=0.085),
            dict(pos=-1.030, w=0.64, h=0.07),
            dict(pos=-1.045, w=0.52, h=0.035),
        ], n=40, sub=3, mat_fn=stripe_fn("paint_secondary", [(0.55, 0.95, "carbon"), (0.20, 0.30, "paint_primary")]))
        for s in (-1, 1):
            rbox("tail_light", (0.13, 0.02, 0.032), (s * 0.43, -1.04, 0.17), mat="emissive_tail", bevel=0.008)
            rbox("tail_bezel", (0.15, 0.016, 0.046), (s * 0.43, -1.034, 0.17), mat="metal_dark", bevel=0.01)
        rbox("tail_center", (0.08, 0.02, 0.022), (0, -1.045, 0.175), mat="emissive_tail", bevel=0.006)

        build_seat(sp, outer_mat="carbon")
        for s in (-1, 1):
            tube("seat_strut", [(s * 0.29, -0.05, 0.07), (s * 0.20, -0.40, 0.42)], 0.011, fillet=0)
        build_column(sp)

        ex, ey = 0.0, -0.52
        rbox("crankcase", (0.22, 0.17, 0.15), (ex, ey, 0.175), mat="metal_dark", bevel=0.03, segs=3)
        rbox("case_cover", (0.03, 0.12, 0.10), (ex + 0.12, ey, 0.17), mat="chrome", bevel=0.012)
        axis = V((0, -0.35, 1)).normalized()
        base = V((ex, ey - 0.02, 0.25))
        cyl("barrel", 0.05, 0.22, base + axis * 0.10, axis, mat="metal_dark", segs=24)
        for k in range(7):
            c = base + axis * (0.02 + k * 0.026)
            rbox("fin", (0.17, 0.15, 0.008), c, mat="chrome" if k % 2 == 0 else "metal_dark", bevel=0.012,
                 segs=2, rot=(-math.degrees(math.atan2(0.35, 1)), 0, 0))
        head_c = base + axis * 0.205
        rbox("cyl_head", (0.13, 0.12, 0.05), head_c, mat="paint_accent", bevel=0.018,
             rot=(-math.degrees(math.atan2(0.35, 1)), 0, 0))
        cyl("spark_plug", 0.012, 0.05, head_c + axis * 0.04, axis, mat="chrome", segs=12)
        cyl("plug_cap", 0.016, 0.035, head_c + axis * 0.07, axis, mat="rubber", segs=12, bevel=0.004)
        cyl("carb", 0.026, 0.09, (0.13, ey + 0.02, 0.30), (1, 0, 0), mat="chrome", bevel=0.003)
        cyl("airbox", 0.065, 0.13, (0.24, ey + 0.02, 0.30), (1, 0, 0), mat="paint_secondary", segs=32,
            bevel=0.015, cap_mat="carbon")
        cyl("airbox_band", 0.067, 0.02, (0.24, ey + 0.02, 0.30), (1, 0, 0), mat="chrome", segs=32, bevel=0.003)
        slab("chain_guard", round_poly([(-0.10, -0.06), (0.06, -0.10), (0.20, 0.03), (0.17, 0.12),
                                        (-0.06, 0.09)], 0.03), 0.01, (0.20, -0.53, 0.20), (0, -1, 0),
             (0, 0, 1), mat="paint_secondary", edge_mat="paint_accent", bevel=0.003)
        tips = []
        for s in (-1, 1):
            tips.append(exhaust_pipe([(s * 0.03, -0.60, 0.33), (s * 0.11, -0.66, 0.34),
                                      (s * 0.15, -0.78, 0.39), (s * 0.155, -0.90, 0.42)], 0.021,
                                     tip_len=0.075))
        for s in (-1, 1):
            tube("wing_pylon", [(s * 0.07, -0.82, 0.13), (s * 0.06, -0.81, 0.30), (s * 0.05, -0.80, 0.485)],
                 0.014, fillet=0.05, mat="metal_dark")
        tube("wing_brace", [(-0.06, -0.81, 0.30), (0.06, -0.81, 0.30)], 0.01, fillet=0, mat="metal_dark")
        rbox("wing_mount", (0.26, 0.07, 0.022), (0, -0.80, 0.489), mat="metal_dark", bevel=0.006)

    sp.exhaust_l, sp.exhaust_r = tips[0], tips[1]
    out = finish("body_vortex", body.objs, {"steering_wheel": build_steering_wheel()})
    place_steering(out["steering_wheel"], sp)
    add_sockets(sp)
    return out


def fender(name, center, radius, a0, a1, width, thick, mat="paint_primary", n=28, e=4.0,
           trim_mat=None):
    """Arc-shaped fender around a wheel (angles in degrees from +Y, counter-clockwise toward +Z)."""
    c = V(center)
    path = [c + V((0, radius * cos(radians(a)), radius * sin(radians(a))))
            for a in (a0 + (a1 - a0) * i / n for i in range(n + 1))]
    prof = se_pts(16, width / 2, thick / 2, e)
    fn = None
    if trim_mat:
        fn = lambda s, u: trim_mat if (u < 0.07 or u > 0.93 or 0.43 < u < 0.57) else mat
    return sweep(name, path, prof, up=(1, 0, 0), mat=mat, mat_fn=fn, sharp_angle=None)


def vent_slats(center, count, size, pitch, axis=(0, 1, 0), mat="metal_dark", rot=(0, 0, 0)):
    d = V(axis).normalized()
    for k in range(count):
        p = V(center) + d * (pitch * (k - (count - 1) / 2))
        rbox("slat", size, p, mat=mat, bevel=min(size) * 0.35, segs=2, rot=rot)


def bolt_row(p0, p1, count, normal, r=0.007, mat="chrome"):
    for k in range(count):
        p = V(p0).lerp(V(p1), k / max(count - 1, 1))
        hexnut("bolt", r, 0.008, p, normal, mat=mat)


BRUTUS = KartSpec(front=(0.58, 0.64, 1.00), rear=(0.58, -0.62, 1.10), hip=(0.0, -0.20, 0.34),
                  spoiler=(0.0, -0.82, 0.555), exhaust_l=(-0.3, -1.0, 0.45), exhaust_r=(0.3, -1.0, 0.45))


def build_body_brutus():
    """Chunky off-road / rally kart: skid tub, boxy hood, fender flares, roll cage with
    roof light bar, bull bar, skid plates, snorkel and mud flaps."""
    sp = BRUTUS
    with Group() as body:
        for s in (-1, 1):
            tube("rail", [(s * 0.18, 0.92, 0.17), (s * 0.28, 0.70, 0.14), (s * 0.31, 0.35, 0.13),
                          (s * 0.31, -0.35, 0.13), (s * 0.33, -0.60, 0.15), (s * 0.28, -0.88, 0.18)],
                 0.02, fillet=0.09, mat="metal_dark")
        loft("skid_tub", [
            dict(pos=0.90, c2=0.17, w=0.24, h=0.03, e=5.0, zmin=0.09),
            dict(pos=0.84, c2=0.155, w=0.30, h=0.055),
            dict(pos=0.0, c2=0.150, w=0.32, h=0.058),
            dict(pos=-0.84, c2=0.155, w=0.30, h=0.055),
            dict(pos=-0.90, c2=0.17, w=0.24, h=0.03),
        ], n=32, sub=3, mat_fn=stripe_fn("metal_dark", [(0.08, 0.42, "paint_secondary")], (0.05, 0.95)))
        for s in (-1, 1):
            bolt_row((s * 0.322, 0.70, 0.15), (s * 0.322, -0.70, 0.15), 9, (s, 0, 0), r=0.0075)
        build_front_uprights(sp, beam_mat="metal_dark")
        build_rear_axle(sp, axle_mat="metal_dark", sprocket=False)
        build_pedals(sp)

        hood_keys = [
            dict(pos=0.975, c2=0.17, w=0.30, h=0.14, e=4.5),
            dict(pos=0.920, w=0.335, h=0.19),
            dict(pos=0.800, w=0.350, h=0.25),
            dict(pos=0.640, w=0.350, h=0.30),
            dict(pos=0.500, w=0.330, h=0.33),
            dict(pos=0.440, w=0.300, h=0.325),
        ]
        hood = loft("hood", hood_keys, n=36, sub=3, t0=0.0, t1=pi, closed=False,
                    mat_fn=stripe_fn("paint_primary", [(0.40, 0.46, "paint_secondary"), (0.54, 0.60, "paint_secondary"),
                                                       (0.46, 0.54, "paint_accent")]))
        add_solidify(hood, 0.018, offset=-1)
        add_subsurf(hood, 1)
        k0 = hood_keys[0]
        gp = [(x, k0["c2"] + z) for x, z in se_pts(36, k0["w"] - 0.01, k0["h"] - 0.01, k0["e"], t0=0, t1=pi,
                                                   closed=False)]
        slab("grille", gp, 0.012, (0, 0.968, 0), (1, 0, 0), (0, 0, 1), mat="metal_dark", bevel=0.003)
        for k in range(4):
            rbox("grille_bar", (0.36, 0.014, 0.012), (0, 0.976, 0.195 + k * 0.03), mat="chrome", bevel=0.004)
        for s in (-1, 1):
            cyl("headlight", 0.045, 0.02, (s * 0.205, 0.978, 0.235), (0, 1, 0), mat="emissive_light", segs=32,
                bevel=0.008)
            torus("headlight_bezel", 0.048, 0.008, mtx_of((s * 0.205, 0.988, 0.235), (90, 0, 0)), mat="chrome",
                  n_major=32, n_minor=8)
        rbox("scoop", (0.20, 0.20, 0.06), (0, 0.66, 0.475), mat="paint_primary", bevel=0.02, taper=(0.85, 0.8),
             rot=(-6, 0, 0))
        rbox("scoop_mouth", (0.17, 0.02, 0.035), (0, 0.765, 0.48), mat="metal_dark", bevel=0.008)
        rbox("bumper_block", (0.78, 0.09, 0.10), (0, 1.02, 0.18), mat="rubber", bevel=0.03)
        tube("bull_bar", [(-0.26, 1.00, 0.20), (-0.26, 1.06, 0.40), (0.26, 1.06, 0.40), (0.26, 1.00, 0.20)],
             0.022, fillet=0.08, mat="metal_dark")
        for s in (-1, 1):
            tube("bull_bar_v", [(s * 0.09, 1.05, 0.23), (s * 0.09, 1.06, 0.40)], 0.016, fillet=0, mat="metal_dark")
            rbox("tow_hook", (0.03, 0.06, 0.05), (s * 0.30, 1.07, 0.15), mat="paint_accent", bevel=0.01)
        rbox("skid_plate", (0.62, 0.26, 0.014), (0, 0.93, 0.105), mat="chrome", bevel=0.006, rot=(-18, 0, 0))
        bolt_row((-0.26, 0.92, 0.115), (0.26, 0.92, 0.115), 6, (0, 0.3, 1), r=0.008, mat="metal_dark")

        for s in (-1, 1):
            c, sc = sp.wheel("front", s)
            fender("fender_f", c, WHEEL_NOMINAL_RADIUS * sc + 0.05, 25, 160, 0.32, 0.03, trim_mat="rubber")
            rbox("fender_f_arm", (0.20, 0.06, 0.03), (s * 0.40, 0.64, 0.50), mat="metal_dark", bevel=0.01,
                 rot=(0, s * -12, 0))
            c, sc = sp.wheel("rear", s)
            fender("fender_r", c, WHEEL_NOMINAL_RADIUS * sc + 0.05, 20, 165, 0.34, 0.03, trim_mat="rubber")
            rbox("fender_r_arm", (0.20, 0.07, 0.03), (s * 0.38, -0.62, 0.545), mat="metal_dark", bevel=0.01,
                 rot=(0, s * -10, 0))
            slab("mud_flap", round_poly([(-0.13, 0.0), (0.13, 0.0), (0.13, 0.24), (-0.13, 0.24)], 0.02),
                 0.012, (s * 0.58, -0.985, 0.06), (1, 0, 0), (0, 0, 1), mat="rubber", bevel=0.003)
            rbox("mud_flap_strip", (0.24, 0.016, 0.03), (s * 0.58, -0.988, 0.27), mat="paint_accent", bevel=0.006)
            for k in (-1, 0, 1):
                hexnut("bolt", 0.006, 0.008, (s * 0.58 + k * 0.08, -0.995, 0.27), (0, -1, 0))

        for s in (-1, 1):
            rbox("side_box", (0.20, 0.58, 0.20), (s * 0.43, -0.01, 0.255), mat="paint_primary", bevel=0.045,
                 segs=4, taper=(0.92, 0.95))
            rbox("side_stripe", (0.206, 0.54, 0.045), (s * 0.432, -0.01, 0.275), mat="paint_secondary", bevel=0.015)
            rbox("side_pin", (0.208, 0.54, 0.012), (s * 0.433, -0.01, 0.305), mat="paint_accent", bevel=0.004)
            rbox("side_skid", (0.012, 0.46, 0.07), (s * 0.533, -0.01, 0.20), mat="chrome", bevel=0.004)
            bolt_row((s * 0.54, 0.19, 0.20), (s * 0.54, -0.21, 0.20), 5, (s, 0, 0), r=0.007, mat="metal_dark")
            tube("nerf_step", [(s * 0.38, 0.34, 0.13), (s * 0.57, 0.31, 0.13), (s * 0.57, -0.28, 0.13),
                               (s * 0.38, -0.30, 0.13)], 0.018, fillet=0.06, mat="metal_dark")

        cage = "paint_secondary"
        tube("cage_main", [(-0.31, -0.53, 0.21), (-0.27, -0.56, 1.12), (0.27, -0.56, 1.12), (0.31, -0.53, 0.21)],
             0.022, fillet=0.13, mat=cage)
        tube("cage_front", [(-0.37, 0.34, 0.30), (-0.29, -0.02, 1.16), (0.29, -0.02, 1.16), (0.37, 0.34, 0.30)],
             0.022, fillet=0.13, mat=cage)
        for s in (-1, 1):
            tube("cage_roof", [(s * 0.282, -0.06, 1.155), (s * 0.262, -0.53, 1.12)], 0.02, fillet=0, mat=cage)
            tube("cage_brace", [(s * 0.25, -0.56, 1.05), (s * 0.24, -0.72, 0.52)], 0.018, fillet=0, mat=cage)
            for z in (0.30, 0.95):
                cyl("cage_clamp", 0.03, 0.035, (s * (0.37 - (z - 0.3) * 0.08), 0.34 - (z - 0.3) * 0.42, z),
                    (s * 0.07, -0.42, 0.86), mat="metal_dark", bevel=0.005)
        tube("cage_diag", [(-0.27, -0.555, 1.0), (0.30, -0.535, 0.32)], 0.018, fillet=0, mat=cage)
        rbox("lightbar", (0.58, 0.085, 0.08), (0, -0.01, 1.225), mat="metal_dark", bevel=0.02)
        for k in range(4):
            x = -0.21 + k * 0.14
            cyl("roof_light", 0.03, 0.02, (x, 0.03, 1.225), (0, 1, 0), mat="emissive_light", segs=24, bevel=0.005)
            torus("roof_bezel", 0.033, 0.006, mtx_of((x, 0.04, 1.225), (90, 0, 0)), mat="chrome", n_major=24,
                  n_minor=6)
        for s in (-1, 1):
            rbox("lightbar_tab", (0.025, 0.05, 0.06), (s * 0.24, -0.02, 1.18), mat="metal_dark", bevel=0.006)
        tube("antenna", [(0.27, -0.56, 1.13), (0.30, -0.62, 1.48)], 0.004, fillet=0, mat="metal_dark")
        sphere("antenna_ball", 0.022, (0.30, -0.62, 1.49), mat="paint_accent", segs=16, rings=8)

        rbox("engine_block", (0.30, 0.24, 0.18), (0, -0.70, 0.27), mat="metal_dark", bevel=0.03)
        for k in range(5):
            rbox("engine_fin", (0.34, 0.012, 0.15), (0, -0.62 - k * 0.04, 0.29), mat="chrome", bevel=0.005, segs=1)
        rbox("rear_deck", (0.58, 0.40, 0.17), (0, -0.80, 0.465), mat="paint_primary", bevel=0.05, segs=4,
             taper=(0.9, 0.92))
        rbox("deck_stripe", (0.14, 0.405, 0.172), (0, -0.80, 0.466), mat="paint_secondary", bevel=0.045, segs=4,
             taper=(0.9, 0.92))
        vent_slats((0.17, -0.80, 0.553), 5, (0.12, 0.022, 0.012), 0.05)
        vent_slats((-0.17, -0.80, 0.553), 5, (0.12, 0.022, 0.012), 0.05)
        for s in (-1, 1):
            rbox("tail_light", (0.07, 0.02, 0.06), (s * 0.20, -1.003, 0.45), mat="emissive_tail", bevel=0.01)
            rbox("tail_bezel", (0.09, 0.016, 0.08), (s * 0.20, -0.996, 0.45), mat="chrome", bevel=0.01)
        rbox("rear_bumper", (0.80, 0.09, 0.10), (0, -1.0, 0.20), mat="rubber", bevel=0.03)
        tube("rear_bar", [(-0.36, -0.96, 0.24), (-0.34, -1.02, 0.32), (0.34, -1.02, 0.32), (0.36, -0.96, 0.24)],
             0.02, fillet=0.05, mat="metal_dark")
        tube("snorkel", [(0.12, -0.66, 0.38), (0.22, -0.62, 0.62), (0.31, -0.60, 0.80), (0.33, -0.60, 1.02)],
             0.028, smooth=4, mat="carbon", n=16)
        for zz in (0.62, 0.90):
            cyl("snorkel_clamp", 0.034, 0.025, (0.25 + (zz - 0.62) * 0.3, -0.61, zz), (0.3, 0, 1), mat="chrome", bevel=0.003)
        rbox("snorkel_head", (0.07, 0.11, 0.06), (0.33, -0.57, 1.05), mat="metal_dark", bevel=0.02)
        tips = []
        for s in (-1, 1):
            tips.append(exhaust_pipe([(s * 0.12, -0.72, 0.28), (s * 0.24, -0.78, 0.33), (s * 0.29, -0.90, 0.38),
                                      (s * 0.30, -0.97, 0.42)], 0.026, tip_len=0.07))
        build_seat(sp, outer_mat="metal_dark")
        build_column(sp, mat="metal_dark")
        rbox("wing_mount", (0.24, 0.07, 0.02), (0, sp.spoiler.y, sp.spoiler.z - 0.008), mat="metal_dark",
             bevel=0.005)

    sp.exhaust_l, sp.exhaust_r = tips[0], tips[1]
    out = finish("body_brutus", body.objs,
                 {"steering_wheel": build_steering_wheel(rim_mat="metal_dark", centre_mat="paint_accent")})
    place_steering(out["steering_wheel"], sp)
    add_sockets(sp)
    return out


FALCON = KartSpec(front=(0.58, 0.66, 0.85), rear=(0.58, -0.62, 1.00), hip=(0.0, -0.25, 0.24),
                  spoiler=(0.0, -0.84, 0.405), exhaust_l=(-0.12, -1.09, 0.28), exhaust_r=(0.12, -1.09, 0.28))


def build_body_falcon():
    """Futuristic low racer: sculpted nose and sponsons, blade fenders, glowing strips,
    tail fins and twin jet nozzles."""
    sp = FALCON
    glow = "emissive_light"
    with Group() as body:
        rbox("floor", (0.52, 1.30, 0.014), (0, -0.05, 0.075), mat="carbon", bevel=0.005)
        build_front_uprights(sp, beam_mat="carbon", tie_z=0.17)
        build_rear_axle(sp, sprocket=False, brake=False, hanger_x=0.20)
        build_pedals(sp)
        loft("nose", [
            dict(pos=1.10, c2=0.13, w=0.035, h=0.02, e=2.4, ts=0.7, zmin=0.07),
            dict(pos=1.05, c2=0.135, w=0.10, h=0.045),
            dict(pos=0.95, c2=0.15, w=0.17, h=0.075),
            dict(pos=0.80, c2=0.17, w=0.23, h=0.11),
            dict(pos=0.64, c2=0.19, w=0.262, h=0.14),
            dict(pos=0.50, c2=0.21, w=0.272, h=0.165),
            dict(pos=0.40, c2=0.22, w=0.268, h=0.175),
            dict(pos=0.345, c2=0.215, w=0.25, h=0.16),
        ], n=40, sub=4, cap_mat="carbon",
            mat_fn=stripe_fn("paint_primary", [(0.21, 0.29, "paint_secondary"), (0.195, 0.21, glow),
                                               (0.29, 0.305, glow), (0.58, 0.92, "carbon")], (0.0, 0.97)))
        slab("splitter", round_poly([(-0.50, 0.93), (0.50, 0.93), (0.44, 1.10), (-0.44, 1.10)], 0.04), 0.014,
             (0, 0, 0.07), (1, 0, 0), (0, 1, 0), mat="carbon", edge_mat="paint_accent", bevel=0.004)
        for s in (-1, 1):
            slab("splitter_fin", round_poly([(0.93, 0.0), (1.08, 0.0), (1.05, 0.07), (0.95, 0.07)], 0.015), 0.01,
                 (s * 0.49, 0, 0.075), (0, 1, 0), (0, 0, 1), mat="paint_secondary", edge_mat="paint_accent")
            rbox("headlight", (0.10, 0.012, 0.016), (s * 0.135, 0.985, 0.185), mat=glow, bevel=0.005,
                 rot=(-20, 0, s * -38))
            slab("canard", round_poly([(0.0, 0.0), (0.12, 0.0), (0.10, 0.05)], 0.01), 0.008,
                 (s * 0.18, 0.80, 0.20), (s, 0, 0), (0, 1, 0.35), mat="carbon", bevel=0.002)
        for s in (-1, 1):
            c, sc = sp.wheel("front", s)
            R = WHEEL_NOMINAL_RADIUS * sc
            fender("blade_fender", c, R + 0.045, 20, 150, 0.27, 0.016, e=2.5, mat="paint_primary")
            fender("blade_fender_glow", c, R + 0.054, 40, 135, 0.05, 0.006, e=2.0, mat=glow)
            tube("fender_arm", [(s * 0.24, 0.64, 0.30), (s * 0.40, 0.66, 0.42), (s * 0.46, 0.67, 0.49)], 0.013,
                 smooth=3, mat="carbon")
            tube("wishbone", [(s * 0.22, 0.74, 0.16), (s * (sp.inner_face_x("front") - 0.04), 0.66, R - 0.06),
                              (s * 0.22, 0.58, 0.16)], 0.011, fillet=0.03, mat="carbon")
        for s in (-1, 1):
            m = None if s > 0 else mirror_x()
            loft("sponson", [
                dict(pos=0.41, c1=0.40, c2=0.16, w=0.04, h=0.04, e=2.6, ts=0.55, zmin=0.075),
                dict(pos=0.37, w=0.11, h=0.085),
                dict(pos=0.25, w=0.145, h=0.115),
                dict(pos=0.00, w=0.158, h=0.13, c2=0.175),
                dict(pos=-0.20, w=0.152, h=0.14, c2=0.19),
                dict(pos=-0.30, w=0.12, h=0.12, c2=0.19),
                dict(pos=-0.335, w=0.05, h=0.05),
            ], n=40, sub=4, mtx=m,
                mat_fn=stripe_fn("paint_primary", [(0.0, 0.02, glow), (0.6, 0.9, "carbon"),
                                                   (0.02, 0.06, "paint_secondary"), (0.94, 1.0, "paint_secondary")],
                                 (0.1, 0.92)))
            sphere("sponson_intake", 0.06, (s * 0.40, 0.385, 0.165), scale=(1.5, 0.3, 0.9), mat="metal_dark")
            slab("intake_vane", round_poly([(-0.07, -0.03), (0.07, -0.03), (0.07, 0.03), (-0.07, 0.03)], 0.01),
                 0.006, (s * 0.40, 0.392, 0.165), (1, 0, 0), (0, 0, 1), mat="paint_accent", bevel=0.002)
        loft("rear_fairing", [
            dict(pos=-0.34, c2=0.30, w=0.10, h=0.06, e=2.5, ts=0.65, zmin=0.075),
            dict(pos=-0.40, w=0.20, h=0.14),
            dict(pos=-0.52, c2=0.30, w=0.235, h=0.18),
            dict(pos=-0.70, c2=0.285, w=0.235, h=0.165),
            dict(pos=-0.88, c2=0.275, w=0.215, h=0.135),
            dict(pos=-0.97, c2=0.275, w=0.20, h=0.115),
            dict(pos=-1.00, w=0.19, h=0.10),
        ], n=40, sub=4, cap_mat="metal_dark",
            mat_fn=stripe_fn("paint_primary", [(0.22, 0.28, "paint_secondary"), (0.205, 0.22, glow),
                                               (0.28, 0.295, glow), (0.6, 0.9, "carbon")], (0.05, 0.97)))
        tips = []
        for s in (-1, 1):
            c = V((s * 0.11, -0.975, 0.28))
            mtx = Matrix.Translation(c) @ Matrix.Rotation(radians(-90), 4, "Z")
            lathe("nozzle", [(0.0, 0.070), (0.04, 0.076), (0.085, 0.074), (0.11, 0.068), (0.112, 0.060),
                             (0.095, 0.056), (0.03, 0.054)], 40, mat="metal_dark", mtx=mtx, closed=True)
            lathe("nozzle_ring", [(0.06, 0.077), (0.075, 0.079), (0.08, 0.077)], 40, mat="chrome", mtx=mtx)
            cyl("nozzle_core", 0.054, 0.01, c + V((0, -0.06, 0)), (0, 1, 0), mat="emissive_tail", segs=32)
            cyl("nozzle_cone", 0.03, 0.05, c + V((0, -0.07, 0)), (0, -1, 0), r2=0.006, mat="chrome", segs=24)
            for k in range(6):
                a = 2 * pi * k / 6
                rbox("nozzle_vane", (0.004, 0.04, 0.05), c + V((0.03 * cos(a), -0.065, 0.03 * sin(a))),
                     mat="metal_dark", bevel=0.0015, segs=1, rot=(0, -math.degrees(a) + 90, 0))
            tips.append(c + V((0, -0.115, 0)))
        rbox("diffuser", (0.50, 0.16, 0.016), (0, -0.93, 0.10), mat="carbon", bevel=0.005, rot=(12, 0, 0))
        for k in range(5):
            slab("diffuser_fin", round_poly([(-0.86, 0.09), (-1.02, 0.09), (-1.02, 0.17), (-0.95, 0.15)], 0.01),
                 0.008, (-0.2 + k * 0.1, 0, 0), (0, 1, 0), (0, 0, 1), mat="carbon", bevel=0.002)
        rbox("tail_light", (0.20, 0.015, 0.018), (0, -1.002, 0.36), mat="emissive_tail", bevel=0.006)
        for s in (-1, 1):
            slab("tail_fin", round_poly([(-0.48, 0.0), (-0.86, 0.0), (-0.99, 0.13), (-0.94, 0.15), (-0.70, 0.05)],
                                        0.02), 0.016, (s * 0.19, 0, 0.37), (0, 1, 0), (s * 0.45, 0, 1),
                 mat="paint_secondary", edge_mat="paint_accent", bevel=0.004)
        ws = loft("windscreen", [
            dict(pos=0.42, c2=0.355, w=0.22, h=0.02, e=2.4),
            dict(pos=0.37, w=0.235, h=0.10),
            dict(pos=0.335, w=0.24, h=0.12),
        ], n=24, sub=3, t0=0.0, t1=pi, closed=False, mat="glass")
        add_solidify(ws, 0.006, offset=0)
        build_seat(sp, outer_mat="paint_secondary")
        build_column(sp, mat="metal_dark")
        rbox("wing_mount", (0.16, 0.07, 0.02), (0, sp.spoiler.y, sp.spoiler.z - 0.008), mat="metal_dark",
             bevel=0.005)

    sp.exhaust_l, sp.exhaust_r = tips[0], tips[1]
    out = finish("body_falcon", body.objs,
                 {"steering_wheel": build_steering_wheel(rim_mat="carbon", centre_mat="paint_secondary")})
    place_steering(out["steering_wheel"], sp)
    add_sockets(sp)
    return out


# 6. SPOILERS  (origin = mounting point at the bottom of the struts)
def wing_element(name, x0, x1, chord, thick, camber, aoa, le_y, le_z, nspan=12, n=18, mat_fn=None,
                 dihedral=0.0):
    """Downforce wing along X: leading edge at (le_y, le_z), chord toward -Y, trailing edge up by aoa."""
    sec = airfoil_pts(n, chord, thick, camber)
    rings = []
    th = radians(-aoa)
    for i in range(nspan + 1):
        x = x0 + (x1 - x0) * i / nspan
        lift = dihedral * abs(x) / max(abs(x0), abs(x1))
        ring = []
        for cx, cy in sec:
            y, z = -cx, -cy
            yr = y * cos(th) - z * sin(th)
            zr = y * sin(th) + z * cos(th)
            ring.append(V((x, le_y + yr, le_z + zr + lift)))
        rings.append(ring)
    return loft_profile(name, rings, mat_fn=mat_fn, sharp_angle=50.0)


def wing_mat(top="paint_primary", stripe="paint_secondary", bottom="carbon"):
    def fn(s, u):
        if u < 0.5:
            return bottom
        if u > 0.86:
            return stripe
        return top
    return fn


def build_spoiler_wing():
    with Group() as g:
        rbox("mount", (0.24, 0.07, 0.02), (0, 0, 0.01), mat="metal_dark", bevel=0.005)
        for s in (-1, 1):
            slab("strut", round_poly([(0.03, 0.0), (-0.03, 0.0), (-0.12, 0.27), (-0.04, 0.27)], 0.012), 0.014,
                 (s * 0.10, 0, 0.0), (0, 1, 0), (0, 0, 1), mat="metal_dark", edge_mat="paint_accent", bevel=0.003)
            for z in (0.03, 0.23):
                hexnut("strut_bolt", 0.007, 0.022, (s * 0.10, -0.01 - 0.3 * z, z), (1, 0, 0))
        wing_element("wing", -0.50, 0.50, 0.30, 0.13, 0.05, 14, 0.06, 0.30, mat_fn=wing_mat())
        rbox("gurney", (1.0, 0.006, 0.022), (0, -0.232, 0.385), mat="paint_accent", bevel=0.002, segs=1)
        for s in (-1, 1):
            plate = round_poly([(0.12, 0.20), (0.10, 0.40), (-0.27, 0.46), (-0.31, 0.38), (-0.27, 0.18),
                                (-0.04, 0.15)], 0.035)
            slab("endplate", plate, 0.014, (s * 0.507, 0, 0), (0, 1, 0), (0, 0, 1), mat="paint_secondary",
                 edge_mat="paint_accent", bevel=0.004)
            rbox("endplate_skid", (0.02, 0.24, 0.012), (s * 0.507, -0.10, 0.165), mat="chrome", bevel=0.004)
    return finish("spoiler_wing", g.objs)


def build_spoiler_twin():
    with Group() as g:
        rbox("mount", (0.30, 0.08, 0.02), (0, 0, 0.01), mat="metal_dark", bevel=0.005)
        for s in (-1, 1):
            tube("swan_neck", [(s * 0.12, 0.0, 0.0), (s * 0.12, 0.0, 0.18), (s * 0.12, -0.03, 0.37),
                               (s * 0.12, -0.10, 0.38), (s * 0.12, -0.11, 0.32)], 0.014, smooth=4, mat="metal_dark")
            cyl("neck_foot", 0.024, 0.02, (s * 0.12, -0.11, 0.315), (0, 0, 1), mat="chrome", bevel=0.004)
        wing_element("main_plane", -0.52, 0.52, 0.26, 0.12, 0.06, 8, 0.04, 0.27,
                     mat_fn=wing_mat(stripe="paint_primary"))
        wing_element("flap", -0.52, 0.52, 0.15, 0.10, 0.05, 32, -0.18, 0.335,
                     mat_fn=wing_mat(top="paint_secondary", stripe="paint_accent"))
        for s in (-1, 1):
            plate = round_poly([(0.12, 0.17), (0.10, 0.38), (-0.10, 0.50), (-0.36, 0.50), (-0.38, 0.40),
                                (-0.30, 0.24), (-0.30, 0.13), (-0.02, 0.10)], 0.04)
            slab("endplate", plate, 0.016, (s * 0.53, 0, 0), (0, 1, 0), (0, 0, 1), mat="carbon",
                 edge_mat="paint_accent", bevel=0.004)
            slab("endplate_badge", round_poly([(-0.02, 0.20), (-0.24, 0.24), (-0.26, 0.32), (-0.06, 0.30)], 0.02),
                 0.004, (s * 0.54, 0, 0), (0, 1, 0), (0, 0, 1), mat="paint_primary", bevel=0.0015, segs=1)
            for k in range(3):
                rbox("louvre", (0.004, 0.06, 0.008), (s * 0.54, -0.25 + 0.0, 0.42 - k * 0.025), mat="metal_dark",
                     bevel=0.0015, segs=1)
    return finish("spoiler_twin", g.objs)


def build_spoiler_fin():
    with Group() as g:
        rbox("pedestal", (0.12, 0.20, 0.05), (0, -0.04, 0.025), mat="metal_dark", bevel=0.015, taper=(0.8, 0.9))
        rings = []
        levels = 9
        for i in range(levels + 1):
            t = i / levels
            z = 0.04 + 0.40 * t
            chord = 0.40 - 0.28 * t ** 1.2
            le_y = 0.10 - 0.30 * t ** 1.4
            th = 0.10 if i < levels else 0.05
            ring = [V((cy * 1.0, le_y - cx, z)) for cx, cy in airfoil_pts(14, chord, th, 0.0)]
            rings.append(ring)

        def fin_mf(s, u):
            if 0.47 < u < 0.53:
                return "paint_accent"
            if u < 0.06 or u > 0.94:
                return "emissive_tail" if s > 0.55 else "paint_secondary"
            if s > 0.82:
                return "paint_secondary"
            return "paint_primary"
        loft_profile("fin", rings, mat_fn=fin_mf, sharp_angle=60.0)
        for s in (-1, 1):
            path = []
            for i in range(10):
                t = 0.08 + 0.7 * i / 9
                z = 0.04 + 0.40 * t
                chord = 0.40 - 0.28 * t ** 1.2
                le_y = 0.10 - 0.30 * t ** 1.4
                path.append(V((s * 0.0185 * (1 - 0.4 * t), le_y - chord * 0.35, z)))
            tube("fin_glow", path, 0.0045, smooth=2, mat="emissive_light", n=8)
        wing_element("blade", -0.23, 0.23, 0.15, 0.10, 0.03, 8, -0.06, 0.20, nspan=10,
                     mat_fn=wing_mat(top="paint_primary", stripe="paint_accent"), dihedral=0.04)
        for s in (-1, 1):
            slab("blade_tip", round_poly([(-0.04, 0.17), (-0.22, 0.20), (-0.24, 0.27), (-0.07, 0.25)], 0.015),
                 0.01, (s * 0.235, 0, 0.0), (0, 1, 0), (0, 0, 1), mat="paint_secondary", edge_mat="paint_accent",
                 bevel=0.003)
    return finish("spoiler_fin", g.objs)


# 7. DRIVER  (origin = hips, facing +Y, hands on the wheel at (+-0.17, 0.42, 0.24))
def two_bone(a, c, l1, l2, pole):
    """Simple two-bone IK: returns the middle joint between a and c."""
    a, c = V(a), V(c)
    d = c - a
    dist = min(d.length, l1 + l2 - 1e-4)
    dn = d.normalized()
    x = (l1 * l1 - l2 * l2 + dist * dist) / (2 * dist)
    h = sqrt(max(l1 * l1 - x * x, 0.0))
    p = V(pole)
    p = (p - dn * p.dot(dn)).normalized()
    return a + dn * x + p * h


def frame_mtx(origin, x_axis, y_axis):
    x = V(x_axis).normalized()
    y = V(y_axis)
    y = (y - x * y.dot(x)).normalized()
    z = x.cross(y)
    m = Matrix((x, y, z)).transposed().to_4x4()
    return Matrix.Translation(V(origin)) @ m


NECK = V((0.0, -0.11, 0.47))
HELMET_C = NECK + V((0.0, 0.035, 0.15))
HELMET_R = V((0.158, 0.172, 0.162))


def helmet_point(lon, lat, off=0.0):
    """Point on the helmet ellipsoid. lon 0 = front (+Y), lat 90 = top (degrees)."""
    lo, la = radians(lon), radians(lat)
    n = V((cos(la) * sin(lo), cos(la) * cos(lo), sin(la)))
    p = V((HELMET_R.x * n.x, HELMET_R.y * n.y, HELMET_R.z * n.z))
    nn = V((p.x / HELMET_R.x ** 2, p.y / HELMET_R.y ** 2, p.z / HELMET_R.z ** 2)).normalized()
    return HELMET_C + p + nn * off, nn


def build_helmet():
    with Group() as g:
        cols, rows = 56, 30
        rings = []
        for i in range(rows + 1):
            t = i / rows
            ring = []
            for j in range(cols):
                lon = 360.0 * j / cols
                lat_min = -50.0 - 13.0 * cos(radians(lon))
                lat = lat_min + (87.0 - lat_min) * t
                p, _ = helmet_point(lon, lat)
                f = max(0.0, cos(radians(lon))) * max(0.0, -sin(radians(lat)))
                p += V((0, 0.018 * f, -0.006 * f))
                ring.append(p)
            rings.append(ring)
        grid_object("helmet_shell", rings, closed_u=True, cap0=True, cap1=True, mat="helmet",
                    cap_mat="rubber")
        trim = []
        for j in range(cols):
            lon = 360.0 * j / cols
            lat_min = -50.0 - 13.0 * cos(radians(lon))
            p, _ = helmet_point(lon, lat_min)
            f = max(0.0, cos(radians(lon))) * max(0.0, -sin(radians(lat_min)))
            trim.append(p + V((0, 0.018 * f, -0.006 * f)))
        sweep("helmet_trim", trim, circle_pts(8, 0.008), closed=True, mat="rubber", sharp_angle=None)
        for nm, lon_r, lat_r, off, mat, solid in (("gasket", 74, (-25, 25), 0.002, "rubber", 0.0),
                                                   ("visor", 68, (-19, 20), 0.007, "visor", 0.005)):
            rings = []
            for i in range(9):
                lat = lat_r[0] + (lat_r[1] - lat_r[0]) * i / 8
                rings.append([helmet_point(-lon_r + 2 * lon_r * j / 18, lat, off)[0] for j in range(19)])
            o = grid_object("helmet_" + nm, rings, closed_u=False, mat=mat)
            face_towards(o, HELMET_C + V((0, 1.0, 0)))
            add_solidify(o, solid or 0.003, offset=-1)
            add_subsurf(o, 1)
        for s in (-1, 1):
            p, n = helmet_point(s * 82, 0, 0.004)
            cyl("visor_pivot", 0.024, 0.012, p, n, mat="metal_dark", bevel=0.003)
            cyl("visor_pivot_cap", 0.012, 0.016, p + n * 0.004, n, mat="chrome", bevel=0.002)
        p, n = helmet_point(-40, -22, 0.009)
        rbox("visor_tab", (0.03, 0.012, 0.012), p, mat="metal_dark", bevel=0.004)
        for s in (-1, 1):
            path, ups = [], []
            for k in range(25):
                ang = -5 + 190 * k / 24
                a = radians(ang)
                x = s * 0.032
                # param on ellipsoid: fixed x, angle around X axis
                ky = sqrt(max(1 - (x / HELMET_R.x) ** 2, 0))
                p = HELMET_C + V((x, HELMET_R.y * ky * cos(a), HELMET_R.z * ky * sin(a)))
                nn = V(((p.x - HELMET_C.x) / HELMET_R.x ** 2, (p.y - HELMET_C.y) / HELMET_R.y ** 2,
                        (p.z - HELMET_C.z) / HELMET_R.z ** 2)).normalized()
                if ang < 24:
                    continue
                path.append(p + nn * 0.0015)
                ups.append(nn)
            sweep("helmet_stripe", path, se_pts(8, 0.0025, 0.012, 4.0), up=ups, mat="paint_accent",
                  sharp_angle=None)
        for k in (-1, 0, 1):
            p, n = helmet_point(k * 13, -40, 0.0)
            rbox("chin_vent", (0.022, 0.012, 0.008), p, mat="metal_dark", bevel=0.003, rot=(-40, 0, k * 13))
        p, n = helmet_point(180, 40, 0.0)
        rbox("helmet_wing", (0.12, 0.05, 0.022), p + V((0, -0.005, 0.006)), mat="helmet", bevel=0.009,
             rot=(-35, 0, 0), taper=(0.85, 0.7))
        rbox("helmet_wing_tip", (0.124, 0.012, 0.024), p + V((0, -0.03, -0.004)), mat="paint_accent",
             bevel=0.005, rot=(-35, 0, 0))
    return g.objs


def build_fist(grip, forearm_dir, rim_tangent, side):
    """Chunky glove gripping the rim at ``grip``."""
    t = V(rim_tangent).normalized()
    f = V(forearm_dir)
    f = (f - t * f.dot(t)).normalized()
    o = t.cross(f) * side
    m = frame_mtx(grip, f, t)
    sphere("palm", 1.0, (0, 0, 0), scale=(0.052, 0.048, 0.045), mat="glove",
           mtx=m @ Matrix.Translation((-0.008, 0.0, 0.0)), segs=20, rings=12)
    for k in range(4):
        sphere("knuckle", 1.0, (0, 0, 0), scale=(0.02, 0.016, 0.018), mat="glove",
               mtx=m @ Matrix.Translation((0.036, -0.03 + k * 0.02, 0.018 * (1 if side > 0 else 1))),
               segs=12, rings=8)
    sphere("thumb", 1.0, (0, 0, 0), scale=(0.035, 0.018, 0.017), mat="glove",
           mtx=m @ Matrix.Translation((0.004, 0.044, -0.012)) @ Matrix.Rotation(radians(25), 4, "Y"),
           segs=12, rings=8)
    rbox("glove_patch", (0.05, 0.05, 0.01), (0, 0, 0), mat="paint_accent", bevel=0.004,
         mtx=m @ Matrix.Translation((-0.012, 0.0, 0.042)))


def build_driver():
    hip = V((0, 0, 0))
    with Group() as body:
        torso_keys = [
            dict(pos=-0.115, c1=0.0, c2=-0.03, w=0.10, h=0.07, e=2.6),
            dict(pos=-0.090, c2=-0.035, w=0.155, h=0.115),
            dict(pos=-0.030, c2=-0.040, w=0.175, h=0.130),
            dict(pos=0.050, c2=-0.050, w=0.170, h=0.122),
            dict(pos=0.130, c2=-0.065, w=0.163, h=0.115),
            dict(pos=0.230, c2=-0.080, w=0.188, h=0.125),
            dict(pos=0.320, c2=-0.095, w=0.205, h=0.122),
            dict(pos=0.390, c2=-0.105, w=0.192, h=0.102),
            dict(pos=0.440, c2=-0.110, w=0.120, h=0.080),
            dict(pos=0.465, c2=-0.110, w=0.065, h=0.060),
        ]
        loft("torso", torso_keys, axis="z", n=40, sub=3,
             mat_fn=stripe_fn("suit", [(0.0, 0.05, "paint_primary"), (0.95, 1.0, "paint_primary"),
                                       (0.45, 0.55, "paint_primary"), (0.05, 0.07, "paint_secondary"),
                                       (0.93, 0.95, "paint_secondary"), (0.43, 0.45, "paint_secondary"),
                                       (0.55, 0.57, "paint_secondary")], (0.25, 0.85)))
        ks = interp_keys(torso_keys, 4)
        zp = [V((0.0, k["c2"] + k["h"] + 0.002, k["pos"])) for k in ks if 0.06 < k["pos"] < 0.43]
        tube("zip", zp, 0.0045, mat="metal_dark", smooth=2, n=8)
        kb = [k for k in ks if k["pos"] >= 0.04][0]
        belt_path = [V((x, kb["c2"] + z, 0.055)) for x, z in se_pts(48, kb["w"] + 0.006, kb["h"] + 0.006, 2.6)]
        sweep("belt", belt_path, se_pts(10, 0.007, 0.018, 4.0), closed=True, up=(0, 0, 1), mat="carbon",
              sharp_angle=None)
        rbox("buckle", (0.065, 0.014, 0.042), (0, kb["c2"] + kb["h"] + 0.012, 0.055), mat="chrome",
             bevel=0.008)
        cyl("neck", 0.052, 0.14, NECK + V((0, 0.0, 0.04)), (0, 0.15, 1), mat="suit", segs=24)
        collar = [NECK + V((x, z, -0.005)) for x, z in se_pts(32, 0.072, 0.066, 2.2)]
        sweep("collar", collar, circle_pts(10, 0.016), closed=True, up=(0, 0, 1), mat="paint_secondary",
              sharp_angle=None)
        for s in (-1, 1):
            sphere("shoulder", 1.0, (s * 0.19, -0.10, 0.37), scale=(0.075, 0.08, 0.07), mat="suit")
            sphere("shoulder_pad", 1.0, (s * 0.195, -0.10, 0.405), scale=(0.058, 0.07, 0.03),
                   mat="paint_primary")

        tangent = V((0, -sin(STEER_TILT), cos(STEER_TILT)))
        for s in (-1, 1):
            S = V((s * 0.205, -0.10, 0.365))
            G = V((s * HAND_TARGET.x, HAND_TARGET.y, HAND_TARGET.z))
            W = G + V((s * 0.012, -0.075, 0.012))
            E = two_bone(S, W, 0.27, 0.25, (s * 1.0, -0.1, -0.7))
            pts = [S, S.lerp(E, 0.5), E, E.lerp(W, 0.5), W]
            tube("arm", pts, 1.0, radii=[0.064, 0.056, 0.050, 0.047, 0.040], smooth=4, n=16,
                 mat_fn=lambda a, u: "paint_primary" if (u < 0.06 or u > 0.94) and a < 0.92 else "suit",
                 caps=True)
            fdir = (W - E).normalized()
            cyl("gauntlet", 0.047, 0.07, W - fdir * 0.01, fdir, mat="glove", r2=0.052, segs=20, bevel=0.006)
            cyl("gauntlet_strap", 0.050, 0.016, W - fdir * 0.03, fdir, mat="paint_accent", segs=20,
                bevel=0.004)
            build_fist(G, fdir, tangent, s)

        for s in (-1, 1):
            Hj = V((s * 0.095, 0.0, -0.04))
            A = V((s * 0.15, 0.82, -0.13))
            K = two_bone(Hj, A, 0.45, 0.44, (s * 0.35, 0.0, 1.0))
            tube("leg", [Hj, Hj.lerp(K, 0.5), K, K.lerp(A, 0.5), A], 1.0,
                 radii=[0.088, 0.076, 0.064, 0.058, 0.048], smooth=4, n=18,
                 mat_fn=lambda a, u: "paint_primary" if abs(u - 0.25) < 0.035 else "suit")
            for t, rr in ((-0.07, 0.069), (0.07, 0.062)):
                d = (K - Hj).normalized() if t < 0 else (A - K).normalized()
                torus("knee_seam", rr, 0.0055, Matrix.Translation(K + d * t) @ axis_matrix(d),
                      mat="paint_secondary", n_major=24, n_minor=6)
            foot = V((0, cos(radians(32)), sin(radians(32))))
            bm = frame_mtx(A, V((1, 0, 0)), foot)
            rbox("boot", (0.10, 0.25, 0.10), (0, 0.07, -0.01), mat="glove", bevel=0.035, segs=3,
                 taper=(0.9, 0.85), mtx=bm)
            rbox("boot_sole", (0.104, 0.26, 0.022), (0, 0.072, -0.058), mat="rubber", bevel=0.008, mtx=bm)
            rbox("boot_strap", (0.106, 0.035, 0.07), (0, 0.04, 0.0), mat="paint_accent", bevel=0.01, mtx=bm)
            cyl("boot_cuff", 0.055, 0.07, A - (A - K).normalized() * 0.01, (A - K), mat="glove", segs=20,
                bevel=0.008)
    out = finish("driver", body.objs, {"driver_head": build_helmet()})
    set_origin(out["driver_head"], NECK)
    return out


def x_to(direction, loc=(0, 0, 0)):
    """Matrix that places a lathe (axis +X) at ``loc`` pointing along ``direction``."""
    rot = V((1, 0, 0)).rotation_difference(V(direction).normalized()).to_matrix().to_4x4()
    return Matrix.Translation(V(loc)) @ rot


def key_at(keys, pos):
    """Loft key (Catmull-Rom, as used by loft()) evaluated at coordinate ``pos``."""
    dense = sorted(interp_keys(keys, 12), key=lambda k: k["pos"])
    if pos <= dense[0]["pos"]:
        return dict(dense[0], pos=pos)
    if pos >= dense[-1]["pos"]:
        return dict(dense[-1], pos=pos)
    for a, b in zip(dense, dense[1:]):
        if a["pos"] <= pos <= b["pos"]:
            f = (pos - a["pos"]) / max(b["pos"] - a["pos"], 1e-9)
            out = {}
            for nm in set(a) | set(b):
                va, vb = a.get(nm), b.get(nm)
                if isinstance(va, (int, float)) and isinstance(vb, (int, float)):
                    out[nm] = va + (vb - va) * f
                else:
                    out[nm] = va if va is not None else vb
            out["pos"] = pos
            return out


def section_pt(k, t, grow=0.0):
    """Point of a y-axis loft section ``k`` at angle ``t``; ``grow`` inflates w and h."""
    w, h = k["w"] + grow, k["h"] + grow
    e = k.get("e", 2.0)
    c, s = cos(t), sin(t)
    x = w * copysign(abs(c) ** (2.0 / e), c)
    z = h * copysign(abs(s) ** (2.0 / e), s)
    kk = (z / h + 1) * 0.5
    x *= k.get("bs", 1.0) + (k.get("ts", 1.0) - k.get("bs", 1.0)) * kk
    zz = k.get("c2", 0.0) + z
    if k.get("zmin") is not None:
        zz = max(zz, k["zmin"])
    if k.get("zmax") is not None:
        zz = min(zz, k["zmax"])
    return V((k.get("c1", 0.0) + x, k["pos"], zz))


def orient_outward(obj, centre):
    """Flip an open shell so its normals point away from ``centre``."""
    me = obj.data
    score = sum(p.normal.dot(p.center - V(centre)) * p.area for p in me.polygons)
    if score < 0:
        bm = bmesh.new()
        bm.from_mesh(me)
        bmesh.ops.reverse_faces(bm, faces=bm.faces)
        bm.to_mesh(me)
        bm.free()


def shell_plate(name, keys, y0, y1, t0, t1, grow0, grow1, n=24, steps=8, thick=0.008, mat="paint_primary",
                mat_fn=None, mtx=None, sharp=35.0):
    """Armour plate that hugs a y-axis loft (``keys``) between y0 -> y1 over the arc t0..t1,
    floating ``grow`` above it (grow0 at y0, grow1 at y1) -> layered / stepped panels."""
    rings = []
    for i in range(steps + 1):
        f = i / steps
        k = key_at(keys, y0 + (y1 - y0) * f)
        g = grow0 + (grow1 - grow0) * f
        rings.append([section_pt(k, t0 + (t1 - t0) * j / n, g) for j in range(n + 1)])
    kc = key_at(keys, (y0 + y1) / 2)
    centre = V((kc.get("c1", 0.0), (y0 + y1) / 2, kc.get("c2", 0.0)))
    if mtx is not None:
        rings = [[mtx @ p for p in r] for r in rings]
        centre = mtx @ centre
    obj = grid_object(name, rings, closed_u=False, mat=mat, mat_fn=mat_fn, sharp_angle=sharp, recalc=False)
    orient_outward(obj, centre)
    add_solidify(obj, thick, offset=-1)
    return obj


def surface_frame(keys, pos, t, grow=0.0, mtx=None):
    """(point, u, v, normal) on a loft surface: u along +Y, v along the section, normal outward."""
    k = key_at(keys, pos)
    p = section_pt(k, t, grow)
    dy = section_pt(key_at(keys, pos + 0.01), t, grow) - section_pt(key_at(keys, pos - 0.01), t, grow)
    dt = section_pt(k, t + 0.03, grow) - section_pt(k, t - 0.03, grow)
    nrm = dy.cross(dt).normalized()
    c = V((k.get("c1", 0.0), pos, k.get("c2", 0.0)))
    if nrm.dot(p - c) < 0:
        nrm = -nrm
    u = dy.normalized()
    v = nrm.cross(u).normalized()
    if mtx is not None:
        m3 = mtx.to_3x3()
        p, u, v, nrm = mtx @ p, (m3 @ u).normalized(), (m3 @ v).normalized(), (m3 @ nrm).normalized()
    return p, u, v, nrm


def rivet(p, normal, r=0.008, mat="metal_dark"):
    return sphere("rivet", r, (0, 0, 0), scale=(1, 1, 0.6), mat=mat, segs=8, rings=4,
                  mtx=Matrix.Translation(V(p)) @ axis_matrix(normal))


def rivet_row(p0, p1, count, normal, r=0.008, mat="metal_dark"):
    for k in range(count):
        rivet(V(p0).lerp(V(p1), k / max(count - 1, 1)), normal, r, mat)


def coil_spring(name, a, b, radius, wire, turns, mat="paint_accent", per_turn=14):
    a, b = V(a), V(b)
    d = b - a
    z = d.normalized()
    x = z.orthogonal().normalized()
    y = z.cross(x)
    total = int(turns * per_turn)
    pts = []
    for i in range(total + 1):
        t = i / total
        ang = 2 * pi * turns * t
        pts.append(a + d * t + x * (radius * cos(ang)) + y * (radius * sin(ang)))
    return sweep(name, pts, circle_pts(6, wire), mat=mat, sharp_angle=None)


def coilover(a, b, spring_mat="paint_accent"):
    """Coil-over shock absorber between eyes a and b."""
    a, b = V(a), V(b)
    d = b - a
    L = d.length
    dn = d.normalized()
    cyl("shock_body", 0.017, L * 0.5, a + dn * (L * 0.25 + 0.02), dn, mat="metal_dark", segs=16, bevel=0.003)
    cyl("shock_shaft", 0.0075, L * 0.45, b - dn * (L * 0.225 + 0.01), dn, mat="chrome", segs=12)
    cyl("shock_seat", 0.033, 0.012, a + dn * 0.07, dn, mat="metal_dark", segs=20, bevel=0.002)
    cyl("shock_seat", 0.033, 0.012, b - dn * 0.05, dn, mat="metal_dark", segs=20, bevel=0.002)
    coil_spring("shock_spring", a + dn * 0.077, b - dn * 0.057, 0.026, 0.0045, 6.5, spring_mat)
    ex = V((1, 0, 0)) - dn * dn.x
    ex = ex.normalized() if ex.length > 1e-6 else V((0, 1, 0))
    for p in (a, b):
        cyl("shock_eye", 0.014, 0.03, p, ex, mat="chrome", segs=12)


def hull_2d(points):
    """Convex hull (monotone chain), CCW."""
    pts = sorted(set(points))
    if len(pts) < 3:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def chain_loop(x, c1, r1, c2, r2, mat="metal_dark"):
    """Drive chain wrapped around two sprockets (centres (y, z)) in the plane x = const."""
    pts = []
    for c, r in ((c1, r1), (c2, r2)):
        for i in range(40):
            a = 2 * pi * i / 40
            pts.append((round(c[0] + r * cos(a), 6), round(c[1] + r * sin(a), 6)))
    hull = hull_2d(pts)
    path = [V((x, y, z)) for y, z in hull]
    return sweep("chain", path, se_pts(6, 0.0065, 0.0045, 4.0), closed=True, up=(1, 0, 0), mat=mat,
                 sharp_angle=None)


BOLT = KartSpec(front=(0.56, 0.66, 0.86), rear=(0.58, -0.62, 1.10), hip=(0.0, -0.20, 0.28),
                spoiler=(0.0, -1.00, 0.43), exhaust_l=(-0.31, -1.11, 0.42), exhaust_r=(0.31, -1.11, 0.42))

BOLT_NOSE = [
    dict(pos=1.105, c2=0.245, w=0.035, h=0.035, e=2.0, zmin=0.13),
    dict(pos=1.095, w=0.115, h=0.11),
    dict(pos=1.065, c2=0.245, w=0.175, h=0.17),
    dict(pos=1.000, c2=0.240, w=0.225, h=0.225),
    dict(pos=0.900, c2=0.235, w=0.255, h=0.26),
    dict(pos=0.760, c2=0.230, w=0.268, h=0.28),
    dict(pos=0.600, c2=0.225, w=0.270, h=0.29),
    dict(pos=0.470, c2=0.220, w=0.265, h=0.295),
    dict(pos=0.380, c2=0.215, w=0.258, h=0.29),
]

BOLT_POD = [
    dict(pos=0.36, c1=0.355, c2=0.20, w=0.03, h=0.035, e=2.6, bs=0.8),
    dict(pos=0.33, w=0.085, h=0.105),
    dict(pos=0.24, w=0.10, h=0.128),
    dict(pos=0.00, w=0.105, h=0.135),
    dict(pos=-0.20, w=0.10, h=0.13),
    dict(pos=-0.27, w=0.075, h=0.10),
    dict(pos=-0.30, w=0.025, h=0.035),
]


def bolt_nose_mf(s, u):
    """Spear-tipped pinstriped scallop panel on each flank of the bubble nose."""
    if u > 0.5:
        return "paint_primary"
    uu = u if u <= 0.25 else 0.5 - u
    d = abs(uu - 0.10)
    if d > 0.041 or s < 0.22 + 2.0 * d - 0.035:
        return "paint_primary"
    if s < 0.22 + 2.0 * d or d > 0.025:
        return "paint_accent"
    return "paint_secondary"


def bolt_pod_mf(s, u):
    if not (0.10 <= s <= 0.90):
        return "paint_primary"
    if 0.042 <= u <= 0.104:
        return "paint_secondary"
    if 0.021 <= u < 0.042 or 0.104 < u <= 0.125:
        return "paint_accent"
    return "paint_primary"


def build_body_bolt():
    """Compact retro hot-rod: chrome-trimmed bubble nose with grille and bucket headlights,
    pinstriped scallop panels, lake pipes, exposed chrome V8 with velocity stacks and
    4-into-1 zoomie headers, transverse fuel tank with bullet tail lights."""
    sp = BOLT
    with Group() as body:
        for s in (-1, 1):
            tube("rail", [(s * 0.14, 1.02, 0.13), (s * 0.22, 0.84, 0.11), (s * 0.27, 0.45, 0.085),
                          (s * 0.28, -0.25, 0.085), (s * 0.30, -0.50, 0.15), (s * 0.28, -0.88, 0.17),
                          (s * 0.15, -0.98, 0.16)], 0.016, fillet=0.09)
            tube("seat_strut", [(s * 0.28, -0.05, 0.085), (s * 0.20, -0.40, 0.42)], 0.011, fillet=0)
        for yy in (0.30, -0.20):
            tube("cross", [(-0.275, yy, 0.085), (0.275, yy, 0.085)], 0.015, fillet=0)
        tube("cross_rear", [(-0.29, -0.80, 0.165), (0.29, -0.80, 0.165)], 0.015, fillet=0)
        rbox("floor_pan", (0.54, 0.86, 0.012), (0, 0.06, 0.072), mat="metal_dark", bevel=0.004, segs=2)
        build_front_uprights(sp, beam_mat="chrome")
        build_rear_axle(sp, axle_mat="chrome")
        build_pedals(sp)

        nose = loft("nose", BOLT_NOSE, n=64, sub=3, cap0=True, cap1=False, mat_fn=bolt_nose_mf)
        add_solidify(nose, 0.012, offset=-1)
        k = key_at(BOLT_NOSE, 0.381)
        lip = [section_pt(k, -0.4 + (pi + 0.8) * j / 40, -0.004) for j in range(41)]
        tube("cowl_lip", lip, 0.011, mat="chrome", fillet=0, n=8)
        strip = []
        for i in range(44):
            y = 1.078 - (1.078 - 0.392) * i / 43
            kk = key_at(BOLT_NOSE, y)
            strip.append(V((0, y, kk["c2"] + kk["h"] + 0.002)))
        sweep("nose_strip", strip, [(z, x) for x, z in se_pts(8, 0.016, 0.0045, 3.0)], up=(0, 0, 1),
              mat="chrome", sharp_angle=None)
        gc = V((0, 1.100, 0.232))
        sphere("grille_mouth", 1.0, gc, scale=(0.094, 0.012, 0.071), mat="metal_dark", segs=32, rings=12)
        torus("grille_ring", 0.073, 0.0085, mtx_of(gc + V((0, 0.006, 0)), (90, 0, 0)), mat="chrome", rx=0.096,
              n_major=40, n_minor=8)
        for k in range(-3, 4):
            x = k * 0.0235
            hz = 0.071 * sqrt(max(1 - (x / 0.094) ** 2, 0)) - 0.006
            rbox("grille_bar", (0.0075, 0.012, 2 * hz), gc + V((x, 0.010, 0)), mat="chrome", bevel=0.003, segs=1)
        for s in (-1, 1):
            c = V((s * 0.215, 0.95, 0.375))
            m = x_to((0, 1, 0), c)
            lathe("hl_bucket", [(-0.10, 0.0), (-0.095, 0.025), (-0.075, 0.048), (-0.04, 0.062), (0.0, 0.068),
                                (0.03, 0.068), (0.037, 0.064), (0.037, 0.0)], 32, mat="chrome", mtx=m,
                  sharp_angle=60)
            sphere("hl_lens", 0.057, c + V((0, 0.036, 0)), scale=(1, 0.32, 1), mat="emissive_light", segs=24,
                   rings=8)
            torus("hl_bezel", 0.060, 0.0065, mtx_of(c + V((0, 0.037, 0)), (90, 0, 0)), mat="chrome",
                  n_major=28, n_minor=6)
        tube("front_bumper", [(-0.30, 0.98, 0.13), (-0.24, 1.135, 0.125), (0.24, 1.135, 0.125), (0.30, 0.98, 0.13)],
             0.018, mat="chrome", fillet=0.07)
        for s in (-1, 1):
            sphere("bumperette", 0.024, (s * 0.15, 1.15, 0.14), scale=(1, 1.2, 1.5), mat="chrome", segs=12, rings=6)
        ws = round_poly([(-0.13, 0.0), (0.13, 0.0), (0.115, 0.12), (-0.115, 0.12)], 0.035)
        o, u, v = V((0, 0.42, 0.468)), V((1, 0, 0)), V((0, -0.28, 1)).normalized()
        slab("windscreen", ws, 0.006, o, u, v, mat="glass", bevel=0.0)
        tube("ws_frame", [o + u * a + v * b for a, b in ws], 0.0065, mat="chrome", fillet=0, closed=True, n=8)
        k = key_at(BOLT_NOSE, 0.395)
        dash = []
        for j in range(33):
            p = section_pt(k, pi * j / 32, -0.016)
            if p.z >= 0.405:
                dash.append((p.x, p.z))
        dash = [(dash[0][0], 0.405)] + dash + [(dash[-1][0], 0.405)]
        slab("dash", dash, 0.016, (0, 0.40, 0), (1, 0, 0), (0, 0, 1), mat="carbon", bevel=0.003)
        for gx in (-0.075, 0.075):
            cyl("gauge", 0.024, 0.006, (gx, 0.389, 0.448), (0, 1, 0), mat="emissive_light", segs=24)
            torus("gauge_bezel", 0.027, 0.0045, mtx_of((gx, 0.387, 0.448), (90, 0, 0)), mat="chrome",
                  n_major=24, n_minor=6)
            rbox("gauge_needle", (0.003, 0.003, 0.02), (gx, 0.385, 0.452), mat="metal_dark", bevel=0.0,
                 rot=(0, 30 if gx > 0 else -30, 0))

        for s in (-1, 1):
            m = None if s > 0 else mirror_x()
            loft("side_pod", BOLT_POD, n=48, sub=4, mtx=m, mat_fn=bolt_pod_mf)
            trim = []
            for i in range(30):
                y = 0.31 - 0.58 * i / 29
                kk = key_at(BOLT_POD, y)
                trim.append(V((s * kk["c1"], y, kk["c2"] + kk["h"] + 0.001)))
            tube("pod_trim", trim, 0.0075, mat="chrome", fillet=0, n=8)
            px = s * 0.455
            tube("lake_pipe", [(px, 0.27, 0.105), (px, -0.22, 0.105)], 0.028, mat="chrome", fillet=0, n=16)
            sphere("lake_bullet", 0.028, (px, 0.27, 0.105), scale=(1, 1.9, 1), mat="chrome", segs=16, rings=8)
            lathe("lake_cap", [(0.0, 0.0285), (0.012, 0.034), (0.03, 0.034), (0.034, 0.029), (0.034, 0.0)], 16,
                  mat="chrome", mtx=x_to((0, -1, 0), (px, -0.22, 0.105)))
            for yy in (0.15, -0.10):
                torus("lake_clamp", 0.031, 0.004, Matrix.Translation((px, yy, 0.105)) @ Matrix.Rotation(radians(90), 4, "X"),
                      mat="metal_dark", n_major=16, n_minor=5)
                rbox("lake_hanger", (0.012, 0.025, 0.05), (s * 0.44, yy, 0.145), mat="metal_dark", bevel=0.003)

        build_seat(sp, outer_mat="paint_primary")
        build_column(sp, mat="chrome")

        ey = -0.72
        rbox("eng_block", (0.20, 0.27, 0.12), (0, ey, 0.43), mat="metal_dark", bevel=0.018)
        rbox("oil_pan", (0.16, 0.23, 0.045), (0, ey, 0.36), mat="chrome", bevel=0.014)
        cyl("timing_cover", 0.05, 0.02, (0, ey + 0.143, 0.43), (0, 1, 0), mat="chrome", segs=32, bevel=0.004)
        cyl("pulley", 0.032, 0.02, (0, ey + 0.16, 0.43), (0, 1, 0), mat="metal_dark", segs=24, bevel=0.003)
        cyl("alternator", 0.03, 0.05, (0.085, ey + 0.13, 0.50), (0, 1, 0), mat="chrome", segs=24, bevel=0.004)
        rbox("intake_manifold", (0.08, 0.27, 0.05), (0, ey, 0.55), mat="paint_accent", bevel=0.012)
        stack_prof = [(0.0, 0.0165), (0.06, 0.0172), (0.088, 0.021), (0.102, 0.027), (0.109, 0.031),
                      (0.113, 0.0285), (0.106, 0.0235), (0.088, 0.0185), (0.02, 0.0150)]
        tips = []
        for s in (-1, 1):
            R = Matrix.Rotation(radians(s * 35), 3, "Y")
            bc = V((s * 0.075, ey, 0.505))
            rbox("eng_bank", (0.09, 0.26, 0.085), bc, mat="metal_dark", bevel=0.012, rot=(0, s * 35, 0))
            vc = bc + R @ V((0, 0, 0.055))
            rbox("valve_cover", (0.078, 0.27, 0.03), vc, mat="chrome", bevel=0.012, rot=(0, s * 35, 0))
            for k in range(5):
                rbox("vc_rib", (0.058, 0.008, 0.012), vc + R @ V((0, -0.10 + k * 0.05, 0.017)), mat="chrome",
                     bevel=0.003, segs=1, rot=(0, s * 35, 0))
            for k in range(4):
                cyl("stack_base", 0.019, 0.02, (s * 0.03, ey - 0.0975 + 0.065 * k, 0.578), (s * 0.18, 0, 1),
                    mat="metal_dark", segs=16)
                lathe("velocity_stack", stack_prof, 20, mat="chrome",
                      mtx=x_to((s * 0.18, 0, 1), (s * 0.03, ey - 0.0975 + 0.065 * k, 0.583)), sharp_angle=60)
            nrm = R @ V((s, 0, 0))
            offs = [(-1, -1), (1, -1), (-1, 1), (1, 1)]
            for i, yy in enumerate((-0.09, -0.03, 0.03, 0.09)):
                p0 = bc + nrm * 0.040 + V((0, yy, 0))
                ox, oz = offs[i]
                tube("header", [p0, p0 + nrm * 0.05, (s * 0.25, ey + yy - 0.05, 0.37),
                                (s * (0.29 + ox * 0.012), -0.855, 0.362 + oz * 0.012)], 0.0135,
                     mat="chrome", smooth=3, n=8)
            lathe("collector", [(0.0, 0.044), (0.03, 0.040), (0.065, 0.029)], 24, mat="chrome",
                  mtx=x_to((0.0, -1, 0.05), (s * 0.29, -0.845, 0.362)))
            tips.append(exhaust_pipe([(s * 0.29, -0.90, 0.364), (s * 0.30, -0.97, 0.375), (s * 0.31, -1.04, 0.40)],
                                     0.026, tip_len=0.06))
            tube("eng_mount", [(s * 0.09, -0.80, 0.40), (s * 0.285, -0.80, 0.17)], 0.013, mat="metal_dark", fillet=0)

        tc = V((0, -1.0, 0.30))
        tp = [(-0.205, 0.0), (-0.203, 0.04), (-0.196, 0.075), (-0.182, 0.098), (-0.163, 0.108), (-0.14, 0.112),
              (-0.05, 0.112), (-0.042, 0.112), (0.042, 0.112), (0.05, 0.112), (0.14, 0.112), (0.163, 0.108),
              (0.182, 0.098), (0.196, 0.075), (0.203, 0.04), (0.205, 0.0)]

        def tank_mf(i):
            xm = abs((tp[i][0] + tp[i + 1][0]) / 2)
            if xm < 0.042:
                return "paint_secondary"
            if xm < 0.05:
                return "paint_accent"
            return "paint_primary"
        lathe("fuel_tank", tp, 48, mat_fn=tank_mf, mtx=Matrix.Translation(tc), sharp_angle=50)
        for x in (-0.115, 0.115):
            torus("tank_strap", 0.1155, 0.0055, Matrix.Translation((x, -1.0, 0.30)) @ Matrix.Rotation(radians(90), 4, "Y"),
                  mat="chrome", n_major=32, n_minor=6)
            rbox("tank_cradle", (0.035, 0.17, 0.03), (x, -1.0, 0.176), mat="metal_dark", bevel=0.006)
        cyl("filler_neck", 0.024, 0.02, (0.10, -0.985, 0.414), (0, 0.15, 1), mat="chrome", segs=24, bevel=0.003)
        cyl("filler_cap", 0.028, 0.012, (0.10, -0.9865, 0.426), (0, 0.15, 1), mat="chrome", segs=12, bevel=0.003)
        for s in (-1, 1):
            c = V((s * 0.145, -1.112, 0.292))
            sphere("tail_light", 0.028, c + V((0, -0.004, 0)), scale=(1, 0.5, 1), mat="emissive_tail", segs=20,
                   rings=10)
            torus("tail_bezel", 0.030, 0.0055, mtx_of(c + V((0, -0.005, 0)), (90, 0, 0)), mat="chrome",
                  n_major=24, n_minor=6)
        rbox("wing_mount", (0.24, 0.07, 0.02), (0, sp.spoiler.y, sp.spoiler.z - 0.01), mat="metal_dark", bevel=0.005)
        tube("rear_nerf", [(-0.34, -0.86, 0.17), (-0.34, -1.16, 0.17), (0.34, -1.16, 0.17), (0.34, -0.86, 0.17)],
             0.019, mat="chrome", fillet=0.08)
        for s in (-1, 1):
            sphere("bumperette", 0.026, (s * 0.21, -1.175, 0.19), scale=(1, 1.2, 1.5), mat="chrome", segs=12,
                   rings=6)

    sp.exhaust_l, sp.exhaust_r = tips[0], tips[1]
    out = finish("body_bolt", body.objs,
                 {"steering_wheel": build_steering_wheel(rim_mat="chrome", centre_mat="paint_secondary",
                                                         display=False)})
    place_steering(out["steering_wheel"], sp)
    add_sockets(sp)
    return out


MANTIS = KartSpec(front=(0.58, 0.68, 0.86), rear=(0.58, -0.62, 1.04), hip=(0.0, -0.24, 0.25),
                  spoiler=(0.0, -0.95, 0.47), exhaust_l=(-0.27, -1.11, 0.60), exhaust_r=(0.27, -1.11, 0.60))

MANTIS_NOSE = [
    dict(pos=1.17, c2=0.165, w=0.03, h=0.02, e=1.0, zmin=0.10),
    dict(pos=1.12, c2=0.175, w=0.09, h=0.055),
    dict(pos=1.00, c2=0.195, w=0.17, h=0.10, e=1.1),
    dict(pos=0.84, c2=0.21, w=0.235, h=0.165, e=1.2),
    dict(pos=0.66, c2=0.22, w=0.27, h=0.215, e=1.3),
    dict(pos=0.50, c2=0.225, w=0.28, h=0.245, e=1.35),
    dict(pos=0.37, c2=0.225, w=0.275, h=0.25),
]

MANTIS_POD = [
    dict(pos=0.42, c1=0.38, c2=0.17, w=0.03, h=0.03, e=1.0, zmin=0.07),
    dict(pos=0.38, w=0.10, h=0.09),
    dict(pos=0.26, w=0.13, h=0.12, c2=0.18),
    dict(pos=0.00, w=0.135, h=0.13, c2=0.19),
    dict(pos=-0.18, w=0.12, h=0.135, c2=0.20),
    dict(pos=-0.28, w=0.08, h=0.11),
    dict(pos=-0.33, w=0.02, h=0.04),
]


def mantis_nose_mf(s, u):
    if u > 0.5:
        return "carbon"
    if abs(u - 0.25) < 0.012:
        return "paint_secondary"
    if u < 0.03 or u > 0.47:
        return "paint_accent"
    return "paint_primary"


def build_body_mantis():
    """Aggressive angular insect racer: faceted nose with layered armour plates, serrated
    mandible splitter, glowing eye slits, faceted sponsons, high dorsal air intake and an
    exposed V-twin rear with chain drive and coil-overs."""
    sp = MANTIS
    glow = "emissive_light"
    with Group() as body:
        for s in (-1, 1):
            tube("rail", [(s * 0.13, 1.00, 0.105), (s * 0.22, 0.80, 0.09), (s * 0.27, 0.40, 0.075),
                          (s * 0.28, -0.30, 0.075), (s * 0.31, -0.55, 0.10), (s * 0.28, -0.95, 0.15),
                          (s * 0.16, -1.00, 0.15)], 0.016, fillet=0.04, mat="metal_dark")
            tube("seat_strut", [(s * 0.28, -0.08, 0.075), (s * 0.20, -0.44, 0.40)], 0.011, fillet=0, mat="carbon")
        for yy, zz in ((0.25, 0.075), (-0.25, 0.075), (-0.98, 0.15)):
            tube("cross", [(-0.28, yy, zz), (0.28, yy, zz)], 0.015, fillet=0, mat="metal_dark")
        rbox("floor", (0.50, 1.10, 0.012), (0, 0.10, 0.068), mat="carbon", bevel=0.004)
        build_front_uprights(sp, beam_mat="carbon")
        build_rear_axle(sp, axle_mat="chrome", hanger_x=0.32)
        build_pedals(sp)

        nose = loft("nose", MANTIS_NOSE, n=48, sub=4, cap0=True, cap1=False, mat_fn=mantis_nose_mf,
                    sharp_angle=28.0)
        add_solidify(nose, 0.012, offset=-1)

        def plate_mf(s, u):
            if s > 0.82:
                return "paint_accent"
            if abs(u - 0.5) < 0.03:
                return "paint_secondary"
            return "paint_primary"
        for y0, y1, g1 in ((0.98, 0.83, 0.020), (0.85, 0.69, 0.024), (0.71, 0.54, 0.026)):
            shell_plate("nose_plate", MANTIS_NOSE, y0, y1, 0.07 * pi, 0.93 * pi, 0.004, g1, n=26, steps=8,
                        thick=0.008, mat_fn=plate_mf)
        for s in (-1, 1):
            m = None if s > 0 else mirror_x()
            for yy, t, sc in ((1.035, 0.27 * pi, 1.0), (1.0, 0.13 * pi, 0.75)):
                p, u, v, nrm = surface_frame(MANTIS_NOSE, yy, t, mtx=m)
                eye = [(-0.065 * sc, -0.006), (0.05 * sc, -0.013), (0.07 * sc, 0.0), (-0.05 * sc, 0.012)]
                ring = [(a * 1.25, b * 1.9) for a, b in eye]
                slab("eye_socket", ring, 0.006, p + nrm * 0.002, u, v, mat="metal_dark", bevel=0.0015, segs=1)
                slab("eye_slit", eye, 0.006, p + nrm * 0.005, u, v, mat=glow, bevel=0.0012, segs=1)
        slab("splitter", round_poly([(-0.24, 0.78), (0.24, 0.78), (0.20, 1.0), (0.10, 1.22), (-0.10, 1.22),
                                     (-0.20, 1.0)], 0.03), 0.014, (0, 0, 0.085), (1, 0, 0), (0, 1, 0),
             mat="carbon", edge_mat="paint_accent", bevel=0.003)
        mand = [(0.20, 0.84), (0.30, 0.94), (0.345, 1.06), (0.32, 1.18), (0.24, 1.29), (0.12, 1.37),
                (0.14, 1.32), (0.20, 1.255), (0.195, 1.215), (0.245, 1.155), (0.235, 1.115), (0.272, 1.05),
                (0.255, 0.96), (0.17, 0.89)]
        for s in (-1, 1):
            pts = [(s * x, y) for x, y in mand]
            if s < 0:
                pts.reverse()
            slab("mandible", pts, 0.026, (0, 0, 0.105), (1, 0, 0), (0, 1, 0.10), mat="paint_secondary",
                 edge_mat="paint_accent", bevel=0.004)
            slab("mandible_glow", [(s * x, y) for x, y in ((0.30, 0.97), (0.322, 1.06), (0.30, 1.16), (0.29, 1.16),
                                                           (0.31, 1.06), (0.29, 0.975))][::s],
                 0.008, (0, 0, 0.12), (1, 0, 0), (0, 1, 0.10), mat=glow, bevel=0.0)
        slab("visor_screen", round_poly([(-0.16, 0.0), (0.16, 0.0), (0.07, 0.10), (-0.07, 0.10)], 0.02), 0.006,
             (0, 0.40, 0.445), (1, 0, 0), V((0, -0.5, 1)).normalized(), mat="glass", bevel=0.0)

        def pod_mf(s, u):
            if u < 0.025 or u > 0.975:
                return "paint_accent"
            if u > 0.5:
                return "carbon"
            return "paint_primary"

        def pod_plate_mf(s, u):
            if s > 0.80:
                return "paint_accent"
            if abs(u - 0.578) < 0.03:
                return "paint_secondary"
            return "paint_primary"
        for s in (-1, 1):
            m = None if s > 0 else mirror_x()
            loft("sponson", MANTIS_POD, n=40, sub=4, mtx=m, mat_fn=pod_mf, sharp_angle=28.0)
            for y0, y1 in ((0.33, 0.07), (0.09, -0.21)):
                shell_plate("pod_plate", MANTIS_POD, y0, y1, 0.02 * pi, 0.85 * pi, 0.004, 0.02, n=22, steps=8,
                            thick=0.008, mat_fn=pod_plate_mf, mtx=m)
            for yy in (0.17, 0.05, -0.07):
                p, u, v, nrm = surface_frame(MANTIS_POD, yy, -0.12 * pi, mtx=m)
                sl = [(-0.045, -0.006), (0.03, -0.006), (0.05, 0.007), (-0.025, 0.007)]
                slab("pod_slit_bg", [(a * 1.15, b * 2.2) for a, b in sl], 0.005, p + nrm * 0.002, u, v,
                     mat="metal_dark", bevel=0.0012, segs=1)
                slab("pod_slit", sl, 0.005, p + nrm * 0.0045, u, v, mat=glow, bevel=0.001, segs=1)

        build_seat(sp, outer_mat="carbon")
        build_column(sp, mat="metal_dark")

        ipath = smooth_path([(0, -0.585, 0.80), (0, -0.64, 0.765), (0, -0.69, 0.67), (0, -0.715, 0.57),
                             (0, -0.725, 0.50)], 4)
        T, N, B = path_frames(ipath, up=(1, 0, 0))
        iprof = se_pts(24, 0.11, 0.085, 1.15)
        iradii = [1.0 - 0.3 * i / (len(ipath) - 1) for i in range(len(ipath))]

        def intake_mf(s, u):
            if abs(u - 0.25) < 0.03:
                return "paint_secondary"
            if u > 0.5:
                return "carbon"
            return "paint_primary"
        sweep("air_intake", ipath, iprof, radii=iradii, up=(1, 0, 0), mat_fn=intake_mf, cap_mat="metal_dark",
              sharp_angle=30.0)
        mouth = [ipath[0] + N[0] * (a * 1.02) + B[0] * (b * 1.02) - T[0] * 0.004 for a, b in iprof]
        tube("intake_lip", mouth, 0.007, mat="paint_accent", fillet=0, closed=True, n=8)
        for a in (-0.05, 0.0, 0.05):
            rbox("intake_vane", (0.006, 0.01, 0.15), (0, 0, 0), mat="carbon", bevel=0.002, segs=1,
                 mtx=frame_mtx(ipath[0] + N[0] * a - T[0] * 0.006, N[0], -T[0]))
        for s in (-1, 1):
            for i in (4, 8):
                p = ipath[i] + N[i] * (s * 0.109 * iradii[i])
                slab("intake_slit", [(-0.03, -0.004), (0.03, -0.004), (0.035, 0.004), (-0.025, 0.004)], 0.004,
                     p, -T[i], B[i], mat=glow, bevel=0.0)

        rbox("crankcase", (0.20, 0.16, 0.14), (0, -0.80, 0.41), mat="metal_dark", bevel=0.012)
        cyl("clutch_cover", 0.06, 0.02, (-0.11, -0.80, 0.41), (1, 0, 0), mat="chrome", segs=32, bevel=0.004)
        slab("clutch_gear", gear_pts(18, 0.05, 0.045), 0.008, (-0.124, -0.80, 0.41), (0, 1, 0), (0, 0, 1),
             mat="metal_dark", bevel=0.0015, segs=1)
        rbox("plenum", (0.08, 0.12, 0.06), (0, -0.77, 0.52), mat="carbon", bevel=0.01)
        tips = []
        for s in (-1, 1):
            a = V((s * sin(radians(40)), 0, cos(radians(40))))
            base = V((s * 0.05, -0.80, 0.48))
            cyl("barrel", 0.042, 0.13, base + a * 0.07, a, mat="metal_dark", segs=20)
            for k in range(6):
                rbox("fin", (0.12, 0.11, 0.007), base + a * (0.02 + k * 0.021), mat="chrome" if k % 2 == 0 else "metal_dark",
                     bevel=0.01, segs=2, rot=(0, s * 40, 0))
            head = base + a * 0.16
            rbox("cyl_head", (0.10, 0.10, 0.045), head, mat="paint_accent", bevel=0.006, rot=(0, s * 40, 0))
            cyl("spark_plug", 0.011, 0.05, head + a * 0.035, a, mat="chrome", segs=12)
            p0 = head + V((s * 0.03, -0.04, -0.01))
            tips.append(exhaust_pipe([p0, (s * 0.235, -0.88, 0.57), (s * 0.25, -0.98, 0.565), (s * 0.26, -1.04, 0.58)],
                                     0.02, tip_len=0.07))
            coilover((s * 0.32, -0.70, 0.31), (s * 0.10, -0.90, 0.50))
            rbox("shock_mount", (0.03, 0.07, 0.03), (s * 0.32, -0.67, 0.30), mat="metal_dark", bevel=0.006)
            rbox("shock_bracket", (0.05, 0.05, 0.03), (s * 0.085, -0.905, 0.485), mat="metal_dark", bevel=0.006)
            slab("pylon", [(-0.88, 0.15), (-1.02, 0.15), (-0.99, 0.46), (-0.91, 0.46), (-0.895, 0.30)], 0.014,
                 (s * 0.06, 0, 0), (0, 1, 0), (0, 0, 1), mat="carbon", edge_mat="paint_accent", bevel=0.003)
        slab("drive_sprocket", gear_pts(12, 0.034, 0.029), 0.008, (0.17, -0.76, 0.43), (0, 1, 0), (0, 0, 1),
             mat="chrome", bevel=0.0015, segs=1)
        cyl("output_shaft", 0.014, 0.08, (0.135, -0.76, 0.43), (1, 0, 0), mat="chrome", segs=12)
        chain_loop(0.17, (-0.62, WHEEL_NOMINAL_RADIUS * sp.rear[2]), 0.082, (-0.76, 0.43), 0.036)
        rbox("wing_mount", (0.22, 0.08, 0.02), (0, sp.spoiler.y, sp.spoiler.z - 0.01), mat="metal_dark", bevel=0.005)
        slab("tail_plate", round_poly([(-0.50, -0.93), (0.50, -0.93), (0.42, -1.08), (0.12, -1.14), (-0.12, -1.14),
                                       (-0.42, -1.08)], 0.02), 0.04, (0, 0, 0.16), (1, 0, 0), (0, 1, 0),
             mat="carbon", edge_mat="paint_primary", bevel=0.006)
        for s in (-1, 1):
            rbox("tail_slit", (0.17, 0.012, 0.016), (s * 0.28, -1.112, 0.165), mat="emissive_tail", bevel=0.004,
                 rot=(0, 0, s * 20.5))
            slab("tail_fin", [(-0.93, 0.18), (-1.06, 0.18), (-1.10, 0.30), (-1.0, 0.27)], 0.012,
                 (s * 0.44, 0, 0), (0, 1, 0), (0, 0, 1), mat="paint_primary", edge_mat="paint_accent", bevel=0.003)

    sp.exhaust_l, sp.exhaust_r = tips[0], tips[1]
    out = finish("body_mantis", body.objs,
                 {"steering_wheel": build_steering_wheel(rim_mat="carbon", centre_mat="paint_accent")})
    place_steering(out["steering_wheel"], sp)
    add_sockets(sp)
    return out


TITAN = KartSpec(front=(0.60, 0.70, 1.00), rear=(0.62, -0.64, 1.18), hip=(0.0, -0.18, 0.37),
                 spoiler=(0.0, -0.98, 0.675), exhaust_l=(-0.31, -0.66, 1.18), exhaust_r=(0.31, -0.66, 1.18))

TITAN_HOOD = [
    dict(pos=1.02, c2=0.36, w=0.30, h=0.15, e=5.0, zmin=0.16),
    dict(pos=0.985, w=0.33, h=0.20),
    dict(pos=0.80, c2=0.37, w=0.345, h=0.25),
    dict(pos=0.60, c2=0.38, w=0.35, h=0.26),
    dict(pos=0.44, c2=0.385, w=0.345, h=0.26),
    dict(pos=0.38, c2=0.385, w=0.34, h=0.255),
]


def armor_fender(center, R, a0, a1, segs, width, thick=0.028, mat="paint_primary"):
    """Segmented riveted armour arch around a wheel (angles in degrees from +Y toward +Z)."""
    c = V(center)
    step = (a1 - a0) / segs
    for k in range(segs):
        a = a0 + step * (k + 0.5)
        chord = 2 * R * sin(radians(step / 2)) + 0.014
        nrm = V((0, cos(radians(a)), sin(radians(a))))
        p = c + nrm * R
        rbox("fender_plate", (width, chord, thick), p, mat=mat, bevel=0.008, segs=2, rot=(a - 90, 0, 0))
        for sx in (-1, 1):
            rivet(p + nrm * (thick / 2) + V((sx * (width / 2 - 0.028), 0, 0)), nrm, 0.0085)


def build_body_titan():
    """Heavy armoured monster kart: box-section frame, riveted armour hood and side boxes,
    segmented fender arches, big blocky bumpers with winch and hazard stripes, caged lights,
    big-block engine with vertical exhaust stacks."""
    sp = TITAN
    with Group() as body:
        for s in (-1, 1):
            rbox("frame_rail", (0.07, 1.95, 0.09), (s * 0.30, 0.0, 0.17), mat="metal_dark", bevel=0.012)
            rivet_row((s * 0.336, 0.88, 0.17), (s * 0.336, -0.88, 0.17), 14, (s, 0, 0), r=0.0075, mat="chrome")
        for yy in (0.90, 0.35, -0.30, -0.92):
            rbox("cross_member", (0.56, 0.06, 0.06), (0, yy, 0.17), mat="metal_dark", bevel=0.01)
        rbox("floor", (0.54, 0.95, 0.014), (0, 0.30, 0.135), mat="metal_dark", bevel=0.004)
        build_front_uprights(sp, beam_mat="metal_dark")
        build_rear_axle(sp, axle_mat="metal_dark", sprocket=False, brake=False)
        cyl("diff", 0.075, 0.12, (0, sp.rear[1], WHEEL_NOMINAL_RADIUS * sp.rear[2]), (1, 0, 0), mat="metal_dark",
            segs=32, bevel=0.02)
        build_pedals(sp)

        hood = loft("hood", TITAN_HOOD, n=48, sub=3, cap0=True, cap1=False, cap_mat="metal_dark",
                    mat_fn=lambda s, u: "metal_dark" if u > 0.5 else "paint_primary")
        add_solidify(hood, 0.016, offset=-1)
        shell_plate("hood_plate", TITAN_HOOD, 0.965, 0.42, 0.30 * pi, 0.70 * pi, 0.012, 0.012, n=16, steps=14,
                    thick=0.02, mat="paint_secondary", sharp=30.0)
        rivet_ys = [0.93 - 0.0675 * i for i in range(8)]
        for yy in rivet_ys:
            for t in (0.315 * pi, 0.685 * pi):
                p, u, v, nrm = surface_frame(TITAN_HOOD, yy, t, 0.012)
                rivet(p, nrm, 0.0085, "chrome")
        for s in (-1, 1):
            m = None if s > 0 else mirror_x()
            shell_plate("hood_cheek", TITAN_HOOD, 0.96, 0.42, -0.16 * pi, 0.20 * pi, 0.012, 0.012, n=14, steps=14,
                        thick=0.018, mat="metal_dark", sharp=30.0, mtx=m)
            for yy in rivet_ys:
                for t in (0.185 * pi, -0.145 * pi):
                    p, u, v, nrm = surface_frame(TITAN_HOOD, yy, t, 0.012, mtx=m)
                    rivet(p, nrm, 0.0085, "chrome")
            p, u, v, nrm = surface_frame(TITAN_HOOD, 0.62, 0.02 * pi, 0.016, mtx=m)
            for k in range(4):
                slab("hood_gill", [(-0.07, -0.006), (0.07, -0.006), (0.07, 0.006), (-0.07, 0.006)], 0.012,
                     p + v * (0.035 * (k - 1.5)), u, v, mat="chrome", bevel=0.003, segs=1)
        fy = 1.022
        for s in (-1, 1):
            c = V((s * 0.175, fy, 0.40))
            cyl("hl_bucket", 0.068, 0.03, c + V((0, 0.005, 0)), (0, 1, 0), mat="metal_dark", segs=32, bevel=0.006)
            cyl("hl_lens", 0.054, 0.02, c + V((0, 0.012, 0)), (0, 1, 0), mat="emissive_light", segs=32, bevel=0.004)
            torus("hl_bezel", 0.06, 0.009, mtx_of(c + V((0, 0.022, 0)), (90, 0, 0)), mat="chrome", n_major=32,
                  n_minor=8)
            for ang in (45, -45):
                rbox("hl_cage", (0.13, 0.012, 0.012), c + V((0, 0.035, 0)), mat="chrome", bevel=0.004, segs=1,
                     rot=(0, ang, 0))
            for ang in range(0, 360, 90):
                rivet(c + V((0.08 * cos(radians(ang + 45)), 0.022, 0.08 * sin(radians(ang + 45)))), (0, 1, 0), 0.008,
                      "chrome")
        for k in range(4):
            rbox("grille_tooth", (0.022, 0.025, 0.15), ((k - 1.5) * 0.04, fy + 0.012, 0.34), mat="chrome",
                 bevel=0.006)

        rbox("front_bumper", (1.00, 0.17, 0.20), (0, 1.12, 0.25), mat="metal_dark", bevel=0.025)
        rbox("bumper_cap", (1.02, 0.18, 0.035), (0, 1.12, 0.36), mat="paint_primary", bevel=0.012)
        for s in (-1, 1):
            rbox("bumper_pad", (0.15, 0.03, 0.12), (s * 0.37, 1.212, 0.25), mat="rubber", bevel=0.01)
            rbox("bumper_bracket", (0.06, 0.12, 0.08), (s * 0.30, 1.0, 0.20), mat="metal_dark", bevel=0.01)
            rbox("tow_hook", (0.03, 0.07, 0.05), (s * 0.20, 1.225, 0.18), mat="paint_accent", bevel=0.01)
            for k in range(3):
                x0 = s * (0.115 + 0.055 * k)
                stripe = [(x0 - 0.014, -0.05), (x0 + 0.014, -0.05), (x0 + 0.014 + s * 0.04, 0.05),
                          (x0 - 0.014 + s * 0.04, 0.05)]
                if s < 0:
                    stripe.reverse()
                slab("hazard", stripe, 0.006, (0, 1.207, 0.25), (1, 0, 0), (0, 0, 1), mat="paint_accent",
                     bevel=0.0)
        cyl("winch_drum", 0.042, 0.13, (0, 1.215, 0.25), (1, 0, 0), mat="chrome", segs=32, bevel=0.004)
        for s in (-1, 1):
            rbox("winch_plate", (0.012, 0.09, 0.12), (s * 0.075, 1.215, 0.25), mat="metal_dark", bevel=0.004)
        rbox("winch_hook", (0.025, 0.03, 0.05), (0, 1.27, 0.21), mat="paint_accent", bevel=0.008)
        rivet_row((-0.46, 1.207, 0.32), (0.46, 1.207, 0.32), 14, (0, 1, 0), r=0.0085, mat="chrome")
        rivet_row((-0.46, 1.207, 0.175), (0.46, 1.207, 0.175), 14, (0, 1, 0), r=0.0085, mat="chrome")

        for s in (-1, 1):
            rbox("side_armor", (0.13, 0.64, 0.26), (s * 0.415, 0.03, 0.27), mat="paint_primary", bevel=0.03, segs=3,
                 taper=(0.9, 0.95))
            plate = round_poly([(0.32, 0.17), (-0.26, 0.17), (-0.24, 0.37), (0.30, 0.37)], 0.025)
            slab("side_plate", plate, 0.016, (s * 0.484, 0, 0), (0, 1, 0), (0, 0, 1), mat="metal_dark",
                 edge_mat="paint_accent", bevel=0.004)
            rivet_row((s * 0.493, 0.28, 0.345), (s * 0.493, -0.22, 0.345), 7, (s, 0, 0), r=0.008, mat="chrome")
            rivet_row((s * 0.493, 0.28, 0.195), (s * 0.493, -0.22, 0.195), 7, (s, 0, 0), r=0.008, mat="chrome")
            rbox("side_step", (0.10, 0.36, 0.02), (s * 0.43, 0.03, 0.42), mat="chrome", bevel=0.005)
            for k in range(5):
                rbox("step_grip", (0.09, 0.012, 0.008), (s * 0.43, -0.11 + 0.07 * k, 0.433), mat="metal_dark",
                     bevel=0.002, segs=1)

        for s in (-1, 1):
            c, sc = sp.wheel("front", s)
            armor_fender(c, WHEEL_NOMINAL_RADIUS * sc + 0.07, 25, 160, 5, 0.30)
            rbox("fender_arm_f", (0.15, 0.05, 0.035), (s * 0.40, 0.70, 0.60), mat="metal_dark", bevel=0.008)
            c, sc = sp.wheel("rear", s)
            armor_fender(c, WHEEL_NOMINAL_RADIUS * sc + 0.06, 15, 165, 6, 0.33)
            tube("fender_strut", [(s * 0.45, -0.50, 0.69), (s * 0.34, -0.46, 0.215)], 0.018, fillet=0, mat="metal_dark")
            tube("fender_strut", [(s * 0.45, -0.86, 0.645), (s * 0.31, -0.92, 0.215)], 0.018, fillet=0, mat="metal_dark")

        build_seat(sp, outer_mat="metal_dark")
        build_column(sp, mat="metal_dark")

        ey = -0.78
        rbox("eng_block", (0.36, 0.26, 0.22), (0, ey, 0.50), mat="metal_dark", bevel=0.03)
        rbox("eng_top", (0.30, 0.22, 0.05), (0, ey, 0.635), mat="paint_accent", bevel=0.015)
        cyl("air_filter", 0.10, 0.09, (0, -0.74, 0.705), (0, 0, 1), mat="chrome", segs=40, bevel=0.012)
        cyl("air_filter_band", 0.103, 0.035, (0, -0.74, 0.705), (0, 0, 1), mat="paint_primary", segs=40, bevel=0.004)
        cyl("air_filter_nut", 0.02, 0.02, (0, -0.74, 0.757), (0, 0, 1), mat="chrome", segs=6)
        tips = []
        for s in (-1, 1):
            for k in range(6):
                rbox("eng_fin", (0.05, 0.24, 0.012), (s * 0.20, ey, 0.42 + k * 0.03),
                     mat="chrome" if k % 2 == 0 else "metal_dark", bevel=0.004, segs=1)
            tip = exhaust_pipe([(s * 0.17, -0.70, 0.50), (s * 0.27, -0.69, 0.50), (s * 0.31, -0.66, 0.58),
                                (s * 0.31, -0.66, 0.75), (s * 0.31, -0.66, 1.08)], 0.034, tip_len=0.08)
            tips.append(tip)
            sc = V((s * 0.31, -0.66, 0.0))
            lathe("heat_shield", [(0.66, 0.044), (0.97, 0.044), (0.97, 0.050), (0.66, 0.050)], 24, mat="chrome",
                  closed=True, mtx=Matrix.Translation(sc) @ Matrix.Rotation(radians(-90), 4, "Y"))
            for zz in (0.68, 0.95):
                torus("shield_clamp", 0.051, 0.005, Matrix.Translation(sc + V((0, 0, zz))), mat="metal_dark",
                      n_major=24, n_minor=6)
            for i in range(4):
                for j in range(5):
                    ang = radians(-60 + 40 * i) if s > 0 else radians(240 - 40 * i)
                    p = sc + V((0.051 * cos(ang), 0.051 * sin(ang), 0.72 + j * 0.05))
                    rbox("shield_slot", (0.004, 0.012, 0.032), p, mat="metal_dark", bevel=0.0,
                         rot=(0, 0, math.degrees(ang)))
            cyl("rain_cap", 0.05, 0.006, tip + V((0, -0.028, 0.03)), (0, -0.55, 0.83), mat="metal_dark", segs=24,
                bevel=0.002)
            cyl("rain_hinge", 0.007, 0.03, tip + V((0, -0.05, 0.0)), (1, 0, 0), mat="chrome", segs=8)

        rbox("rear_deck", (0.54, 0.22, 0.10), (0, -1.0, 0.615), mat="paint_primary", bevel=0.025)
        for s in (-1, 1):
            rbox("deck_post", (0.05, 0.06, 0.37), (s * 0.20, -1.0, 0.385), mat="metal_dark", bevel=0.008)
            rbox("tail_light", (0.10, 0.02, 0.05), (s * 0.17, -1.112, 0.61), mat="emissive_tail", bevel=0.008)
            for k in range(3):
                rbox("tail_cage", (0.008, 0.012, 0.07), (s * 0.17 + (k - 1) * 0.035, -1.125, 0.61), mat="chrome",
                     bevel=0.002, segs=1)
        rivet_row((-0.24, -0.918, 0.666), (0.24, -0.918, 0.666), 8, (0, 0, 1), r=0.0075, mat="chrome")
        rivet_row((-0.24, -1.082, 0.666), (0.24, -1.082, 0.666), 8, (0, 0, 1), r=0.0075, mat="chrome")
        rbox("wing_mount", (0.24, 0.07, 0.02), (0, sp.spoiler.y, sp.spoiler.z - 0.01), mat="metal_dark", bevel=0.005)
        rbox("rear_bumper", (1.04, 0.16, 0.20), (0, -1.17, 0.25), mat="metal_dark", bevel=0.025)
        rbox("rear_bumper_cap", (1.06, 0.17, 0.035), (0, -1.17, 0.36), mat="paint_primary", bevel=0.012)
        for s in (-1, 1):
            rbox("rear_pad", (0.15, 0.03, 0.12), (s * 0.37, -1.262, 0.25), mat="rubber", bevel=0.01)
            rbox("rear_bracket", (0.06, 0.14, 0.08), (s * 0.30, -1.04, 0.20), mat="metal_dark", bevel=0.01)
            cyl("rear_round_light", 0.03, 0.02, (s * 0.20, -1.255, 0.25), (0, -1, 0), mat="emissive_tail", segs=24,
                bevel=0.004)
            torus("rear_round_bezel", 0.033, 0.006, mtx_of((s * 0.20, -1.262, 0.25), (90, 0, 0)), mat="chrome",
                  n_major=24, n_minor=6)
        rbox("hitch", (0.06, 0.10, 0.04), (0, -1.28, 0.20), mat="metal_dark", bevel=0.008)
        sphere("hitch_ball", 0.028, (0, -1.31, 0.245), mat="chrome", segs=16, rings=8)
        rivet_row((-0.47, -1.251, 0.32), (0.47, -1.251, 0.32), 14, (0, -1, 0), r=0.0085, mat="chrome")
        rivet_row((-0.47, -1.251, 0.175), (0.47, -1.251, 0.175), 14, (0, -1, 0), r=0.0085, mat="chrome")

    sp.exhaust_l, sp.exhaust_r = tips[0], tips[1]
    out = finish("body_titan", body.objs,
                 {"steering_wheel": build_steering_wheel(rim_mat="metal_dark", centre_mat="paint_accent")})
    place_steering(out["steering_wheel"], sp)
    add_sockets(sp)
    return out


def build_wheel_retro():
    """Whitewall balloon tyre, painted hoop with chrome cross-laced wire spokes, finned drum
    and a three-eared chrome knock-off spinner."""
    half = [(0.000, 0.2800), (0.035, 0.2796), (0.062, 0.2780), (0.082, 0.2752), (0.097, 0.2712), (0.107, 0.2655),
            (0.1135, 0.2580), (0.1165, 0.2490), (0.1170, 0.2390), (0.1155, 0.2290), (0.1125, 0.2200),
            (0.1085, 0.2130), (0.1040, 0.2080), (0.0990, 0.2045)]
    prof = mirror_profile(half)

    def tmf(i):
        (x0, r0), (x1, r1) = prof[i], prof[i + 1]
        if x0 > 0 and x1 > 0 and 0.2095 <= (r0 + r1) / 2 <= 0.2525:
            return "whitewall"
        return "rubber"
    with Group() as g:
        lathe("tire", prof, 72, mat_fn=tmf, sharp_angle=60.0)
        lathe("hoop", [(-0.100, 0.198), (-0.097, 0.207), (-0.090, 0.204), (-0.082, 0.190), (-0.050, 0.181),
                       (0.050, 0.181), (0.082, 0.190), (0.090, 0.204), (0.097, 0.207), (0.100, 0.198),
                       (0.094, 0.174), (-0.094, 0.174)], 72, mat="rim", closed=True, sharp_angle=50.0)
        wheel_ring("hoop_lip", 0.098, 0.2055, 0.0045, "chrome", n_major=72, n_minor=8)
        lathe("drum", [(-0.112, 0.03), (-0.112, 0.150), (-0.104, 0.156), (-0.096, 0.150), (-0.088, 0.156),
                       (-0.080, 0.150), (-0.068, 0.150), (-0.062, 0.03)], 48, mat="metal_dark", closed=True)
        lathe("hub_shell", [(-0.075, 0.030), (-0.062, 0.036), (-0.056, 0.056), (-0.046, 0.056), (-0.042, 0.038),
                            (0.034, 0.034), (0.037, 0.052), (0.046, 0.052), (0.050, 0.036), (0.078, 0.034)], 40,
              mat="chrome", sharp_angle=50.0)
        nsp = 20
        for fx, rx, hr, phase in ((0.042, -0.012, 0.047, 0.0), (-0.051, 0.014, 0.052, pi / nsp)):
            for k in range(nsp):
                a = phase + 2 * pi * k / nsp
                b = a + (0.45 if k % 2 == 0 else -0.45)
                p0 = V((fx, hr * cos(a), hr * sin(a)))
                p1 = V((rx, 0.176 * cos(b), 0.176 * sin(b)))
                tube("spoke", [p0, p1], 0.0032, mat="chrome", fillet=0, n=6)
                cyl("nipple", 0.0055, 0.014, p1 - (p1 - p0).normalized() * 0.004, p1 - p0, mat="chrome", segs=6)
        lathe("spinner_nut", [(0.074, 0.042), (0.090, 0.042), (0.095, 0.036), (0.112, 0.031), (0.118, 0.023),
                              (0.122, 0.011), (0.1235, 0.0)], 32, mat="chrome", sharp_angle=50.0)

        def ear(mtx, k):
            keys = [dict(pos=0.025, c1=0.104, c2=0.0, w=0.011, h=0.013, e=2.6),
                    dict(pos=0.055, c1=0.103, w=0.009, h=0.011),
                    dict(pos=0.080, c1=0.099, w=0.010, h=0.019),
                    dict(pos=0.090, c1=0.095, w=0.011, h=0.022)]
            spoke_loft("spinner_ear", keys, mtx, mat="chrome", n=14)
        radial_copies(3, ear, phase=pi / 6)
        cyl("spinner_badge", 0.014, 0.004, (0.1225, 0, 0), (1, 0, 0), mat="paint_accent", segs=24)
    return finish("wheel_retro", g.objs)


def build_wheel_neon():
    """Low-profile tyre on a sharp split-spoke rim with a glowing ring in a recessed channel."""
    half = [(0.000, 0.2800), (0.050, 0.2797), (0.080, 0.2786), (0.100, 0.2766), (0.112, 0.2736), (0.119, 0.2690),
            (0.1225, 0.2625), (0.1235, 0.2550), (0.1225, 0.2480), (0.119, 0.2425), (0.113, 0.2385), (0.106, 0.2360)]
    with Group() as g:
        tire("tire", half, segs=72)
        lathe("barrel", [(-0.102, 0.222), (0.102, 0.222), (0.102, 0.236), (-0.102, 0.236)], 72, mat="rim", closed=True)
        lathe("rim_lip", [(0.098, 0.2365), (0.108, 0.2370), (0.111, 0.2320), (0.108, 0.2200), (0.098, 0.2160)], 72,
              mat="rim", sharp_angle=40.0)
        lathe("face_ring", [(0.080, 0.178), (0.102, 0.179), (0.104, 0.1835), (0.104, 0.189), (0.0965, 0.190),
                            (0.0965, 0.210), (0.104, 0.211), (0.104, 0.2155), (0.100, 0.2195), (0.080, 0.2200)],
              72, mat="rim", closed=True, sharp_angle=40.0,
              mat_fn=lambda i: "metal_dark" if i in (3, 4, 5) else "rim")
        wheel_ring("glow_ring", 0.0985, 0.200, 0.0082, "emissive_light", n_major=72, n_minor=8)
        cyl("backplate", 0.205, 0.008, (0.02, 0, 0), (1, 0, 0), mat="metal_dark", segs=56)
        cyl("brake_disc", 0.15, 0.012, (-0.03, 0, 0), (1, 0, 0), mat="chrome", segs=48, bevel=0.002)

        def spoke(mtx, k):
            for side in (-1, 1):
                keys = [dict(pos=0.050, c1=0.080, c2=side * 0.006, w=0.015, h=0.011, e=1.6),
                        dict(pos=0.095, c1=0.088, c2=side * 0.016, w=0.013, h=0.010),
                        dict(pos=0.145, c1=0.095, c2=side * 0.030, w=0.011, h=0.0085),
                        dict(pos=0.186, c1=0.098, c2=side * 0.040, w=0.010, h=0.010)]
                spoke_loft("spoke", keys, mtx, n=10)
        radial_copies(6, spoke)
        cyl("hub", 0.058, 0.05, (0.075, 0, 0), (1, 0, 0), mat="rim", segs=48, bevel=0.007)
        wheel_ring("hub_glow", 0.1005, 0.042, 0.0032, "emissive_light", n_major=40, n_minor=6)
        lathe("centre_cap", [(0.099, 0.034), (0.106, 0.032), (0.112, 0.024), (0.116, 0.012), (0.117, 0.0)], 32,
              mat="metal_dark", sharp_angle=50.0)
        radial_copies(6, lambda m, k: hexnut("lug", 0.0072, 0.012, m @ V((0.101, 0, 0.050)), (1, 0, 0),
                                            mat="chrome"), phase=pi / 6)
    return finish("wheel_neon", g.objs)


def build_spoiler_duck():
    """Retro ducktail: a sculpted deck lid that kicks up into a lip, on chrome posts."""
    with Group() as g:
        rbox("mount", (0.24, 0.07, 0.02), (0, 0, 0.01), mat="metal_dark", bevel=0.005)
        for s in (-1, 1):
            slab("duck_post", round_poly([(0.03, 0.0), (-0.03, 0.0), (-0.06, 0.075), (0.0, 0.075)], 0.01), 0.018,
                 (s * 0.09, 0, 0), (0, 1, 0), (0, 0, 1), mat="chrome", bevel=0.003)
        # section (y, z): long low deck that curls up into a sharp lip
        top = smooth_path([(0.105, 0.066), (0.02, 0.074), (-0.07, 0.083), (-0.15, 0.098), (-0.21, 0.122),
                           (-0.25, 0.150), (-0.272, 0.178)], 4)
        sec = []
        nt = len(top)
        for i, p in enumerate(top):
            f = i / (nt - 1)
            m = "paint_primary" if f < 0.62 else ("paint_accent" if f < 0.68 else "paint_secondary")
            sec.append((p.x, p.y, m))
        sec += [(-0.281, 0.186, "paint_secondary"), (-0.290, 0.183, "paint_secondary"),
                (-0.292, 0.174, "carbon"), (-0.278, 0.156, "carbon")]
        bot = smooth_path([(-0.262, 0.138), (-0.19, 0.098), (-0.08, 0.066), (0.03, 0.054), (0.10, 0.055)], 3)
        sec += [(p.x, p.y, "carbon") for p in bot]
        sec.append((0.113, 0.060, "paint_primary"))
        mats = [m for _, _, m in sec]
        lip_idx = len(top) + 1
        half_span, ns = 0.43, 32
        rings, lip = [], []
        for i in range(ns + 1):
            x = -half_span + 2 * half_span * i / ns
            f = max(1 - (abs(x) / (half_span + 0.004)) ** 5, 0.0) ** 0.2
            ring = []
            for y, z, _ in sec:
                ring.append(V((x, -0.09 + (y + 0.09) * (0.55 + 0.45 * f), 0.06 + (z - 0.06) * (0.25 + 0.75 * f))))
            rings.append(ring)
            lip.append(ring[lip_idx] + V((0, 0, 0.004)))
        nu = len(sec)
        loft_profile("duck", rings, mat_fn=lambda s, u: mats[min(int(u * nu), nu - 1)], cap_mat="paint_primary",
                     sharp_angle=55.0)
        tube("duck_trim", lip[2:-2], 0.0042, mat="chrome", smooth=2, n=8)
    return finish("spoiler_duck", g.objs)


def build_spoiler_halo():
    """Futuristic floating ring wing with a glowing inner edge on two thin chrome struts."""
    with Group() as g:
        rbox("mount", (0.24, 0.07, 0.02), (0, 0, 0.01), mat="metal_dark", bevel=0.005)
        rbox("mount_pod", (0.18, 0.09, 0.04), (0, -0.01, 0.035), mat="carbon", bevel=0.015, taper=(0.8, 0.8))
        c = V((0, -0.13, 0.34))
        rx, ry = 0.47, 0.21
        tilt = Matrix.Rotation(radians(-5), 4, "X")
        M = Matrix.Translation(c) @ tilt
        axis = (tilt.to_3x3() @ V((0, 0, 1))).normalized()
        n = 96
        path = [M @ V((rx * cos(2 * pi * i / n), ry * sin(2 * pi * i / n), 0)) for i in range(n)]
        prof = []
        m = 16
        for j in range(m):
            t = 2 * pi * j / m
            b = 0.048 * cos(t)
            prof.append((0.011 * sin(t) + 0.005 * (1 - (b / 0.048) ** 2), b))

        def halo_mf(s, u):
            t = 2 * pi * u
            if cos(t) > 0.80:
                return "paint_accent"
            if sin(t) < 0:
                return "carbon"
            if cos(t) < -0.55:
                return "paint_secondary"
            return "paint_primary"
        sweep("halo_ring", path, prof, closed=True, up=axis, mat_fn=halo_mf, sharp_angle=None)
        T, N, B = path_frames(path, closed=True, up=axis)
        glow = [path[i] - B[i] * 0.049 + N[i] * 0.003 for i in range(n)]
        tube("halo_glow", glow, 0.0055, mat="emissive_light", fillet=0, closed=True, n=6)
        rear = [path[i] + B[i] * 0.049 for i in range(int(n * 0.68), int(n * 0.82) + 1)]
        tube("halo_brake", rear, 0.0065, mat="emissive_tail", fillet=0, n=8)
        for s in (-1, 1):
            th = -40.0 if s > 0 else 220.0
            idx = int(round((th % 360.0) / 360.0 * n)) % n
            attach = path[idx] - N[idx] * 0.010
            tube("halo_strut", [V((s * 0.075, -0.01, 0.03)), V((s * 0.11, -0.05, 0.12)), V((s * 0.22, -0.15, 0.24)),
                                attach], 0.0085, mat="chrome", smooth=4, n=10)
            sphere("strut_pod", 0.019, attach, scale=(1.0, 1.7, 0.8), mat="metal_dark", segs=16, rings=8)
    return finish("spoiler_halo", g.objs)


PARTS = {
    "wheel_classic": build_wheel_classic,
    "wheel_offroad": build_wheel_offroad,
    "wheel_turbine": build_wheel_turbine,
    "body_vortex": build_body_vortex,
    "body_brutus": build_body_brutus,
    "body_falcon": build_body_falcon,
    "spoiler_wing": build_spoiler_wing,
    "spoiler_twin": build_spoiler_twin,
    "spoiler_fin": build_spoiler_fin,
    "driver": build_driver,
    "wheel_retro": build_wheel_retro,
    "wheel_neon": build_wheel_neon,
    "body_bolt": build_body_bolt,
    "body_mantis": build_body_mantis,
    "body_titan": build_body_titan,
    "spoiler_duck": build_spoiler_duck,
    "spoiler_halo": build_spoiler_halo,
}


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out_dir = DEFAULT_OUT_DIR
    names = []
    i = 0
    while i < len(argv):
        if argv[i] == "--out":
            out_dir = argv[i + 1]
            i += 2
            continue
        names.append(argv[i])
        i += 1
    return out_dir, names


def main():
    out_dir, names = parse_args()
    make_materials()
    todo = names or list(PARTS.keys())
    for name in todo:
        clear_scene()
        PARTS[name]()
        path = export_glb(name, out_dir)
        print("[build_karts] exported %-16s %s  tris=%s" % (name, path, REPORT[name]))
    print("[build_karts] DONE", REPORT)


if __name__ == "__main__":
    main()
