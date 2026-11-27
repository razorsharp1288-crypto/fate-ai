"""Primitive-based 3D concept models: meshing, transforms and STL/OBJ export.

Coordinates are metres, Y is up, the model stands on the ground plane (y=0).
A model is a list of ``Part``s; each part is a primitive with position
(centre), size (full extents along x/y/z), rotation (degrees, XYZ order) and colour.
"""
from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

SHAPES = ("box", "cylinder", "sphere", "cone", "capsule", "torus", "wedge")
MAX_PARTS = 300
Vec = tuple[float, float, float]
Tri = tuple[Vec, Vec, Vec]


@dataclass
class Part:
    name: str
    shape: str = "box"
    position: list[float] = field(default_factory=lambda: [0.0, 0.5, 0.0])
    size: list[float] = field(default_factory=lambda: [1.0, 1.0, 1.0])
    rotation: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    color: str = "#8B5CF6"
    material: str = ""
    group: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def _vec(v, default, lo, hi) -> list[float]:
    try:
        out = [float(x) for x in list(v)[:3]]
        if len(out) != 3 or any(math.isnan(x) or math.isinf(x) for x in out):
            raise ValueError
    except (TypeError, ValueError):
        return list(default)
    return [max(lo, min(hi, x)) for x in out]


def sanitize(raw_parts) -> list[Part]:
    """Validate untrusted part dicts (e.g. from a model reply) into safe Parts."""
    parts: list[Part] = []
    for d in list(raw_parts or [])[:MAX_PARTS]:
        if not isinstance(d, dict):
            continue
        shape = str(d.get("shape", "box")).lower()
        if shape not in SHAPES:
            shape = "box"
        color = str(d.get("color", "#8B5CF6"))
        parts.append(Part(
            name=str(d.get("name", f"part {len(parts) + 1}"))[:80],
            shape=shape,
            position=_vec(d.get("position"), [0, 0.5, 0], -1000, 1000),
            size=_vec(d.get("size"), [0.2, 0.2, 0.2], 0.001, 1000),
            rotation=_vec(d.get("rotation"), [0, 0, 0], -360, 360),
            color=color if _HEX.match(color) else "#8B5CF6",
            material=str(d.get("material", ""))[:60],
            group=str(d.get("group", ""))[:40]))
    return parts


# --------------------------------------------------------------------------- unit meshes (size 1, centred)
def _unit_box() -> list[Tri]:
    p = [(-.5, -.5, -.5), (.5, -.5, -.5), (.5, .5, -.5), (-.5, .5, -.5),
         (-.5, -.5, .5), (.5, -.5, .5), (.5, .5, .5), (-.5, .5, .5)]
    faces = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (3, 7, 6, 2), (0, 4, 7, 3), (1, 2, 6, 5)]
    return [t for a, b, c, d in faces for t in ((p[a], p[b], p[c]), (p[a], p[c], p[d]))]


def _unit_wedge() -> list[Tri]:
    # ramp: full height at back (z=-.5), zero at front (z=.5)
    p = [(-.5, -.5, -.5), (.5, -.5, -.5), (.5, .5, -.5), (-.5, .5, -.5), (-.5, -.5, .5), (.5, -.5, .5)]
    return [(p[0], p[3], p[2]), (p[0], p[2], p[1]), (p[0], p[1], p[5]), (p[0], p[5], p[4]),
            (p[3], p[4], p[5]), (p[3], p[5], p[2]), (p[0], p[4], p[3]), (p[1], p[2], p[5])]


def _unit_lathe(profile: list[tuple[float, float]], seg: int) -> list[Tri]:
    """Revolve (radius, y) profile points around Y. Radius 0.5 == unit size."""
    tris: list[Tri] = []
    ring = [(math.cos(2 * math.pi * i / seg), math.sin(2 * math.pi * i / seg)) for i in range(seg)]
    for (r0, y0), (r1, y1) in zip(profile, profile[1:]):
        for i in range(seg):
            c0, s0 = ring[i]
            c1, s1 = ring[(i + 1) % seg]
            a, b = (r0 * c0, y0, r0 * s0), (r0 * c1, y0, r0 * s1)
            c, d = (r1 * c1, y1, r1 * s1), (r1 * c0, y1, r1 * s0)
            if r0 > 1e-9:
                tris.append((a, d, b))
            if r1 > 1e-9:
                tris.append((b, d, c))
    return tris


def _sphere_profile(n: int = 10, y0: float = -0.5, y1: float = 0.5, r: float = 0.5):
    pts = []
    for i in range(n + 1):
        t = math.pi * i / n
        pts.append((r * math.sin(t), (y0 + y1) / 2 - (y1 - y0) / 2 * math.cos(t)))
    return pts


_CACHE: dict[str, list[Tri]] = {}


def unit_mesh(shape: str) -> list[Tri]:
    if shape not in _CACHE:
        seg = 20
        if shape == "box":
            m = _unit_box()
        elif shape == "wedge":
            m = _unit_wedge()
        elif shape == "cylinder":
            m = _unit_lathe([(0, -.5), (.5, -.5), (.5, .5), (0, .5)], seg)
        elif shape == "cone":
            m = _unit_lathe([(0, -.5), (.5, -.5), (0, .5)], seg)
        elif shape == "sphere":
            m = _unit_lathe(_sphere_profile(10), seg)
        elif shape == "capsule":
            cap = 0.25
            prof = [(0.5 * math.sin(math.pi / 2 * i / 5), -0.5 + cap - cap * math.cos(math.pi / 2 * i / 5))
                    for i in range(6)]
            prof += [(0.5 * math.cos(math.pi / 2 * i / 5), 0.5 - cap + cap * math.sin(math.pi / 2 * i / 5))
                     for i in range(1, 6)]
            m = _unit_lathe(prof, seg)
        elif shape == "torus":
            # ring in the XZ plane: outer diameter 1, tube height 1 (scaled by size like other shapes)
            m = []
            R, r, n1, n2 = 0.35, 0.15, 28, 12

            def pt(a, b):
                u, v = 2 * math.pi * a / n1, 2 * math.pi * b / n2
                return ((R + r * math.cos(v)) * math.cos(u), 0.5 * math.sin(v),
                        (R + r * math.cos(v)) * math.sin(u))
            for i in range(n1):
                for j in range(n2):
                    p00, p10, p11, p01 = pt(i, j), pt(i + 1, j), pt(i + 1, j + 1), pt(i, j + 1)
                    m += [(p00, p11, p10), (p00, p01, p11)]
        else:
            m = _unit_box()
        _CACHE[shape] = m
    return _CACHE[shape]


def _rot(v: Vec, rx: float, ry: float, rz: float) -> Vec:
    x, y, z = v
    if rx:
        c, s = math.cos(rx), math.sin(rx)
        y, z = y * c - z * s, y * s + z * c
    if ry:
        c, s = math.cos(ry), math.sin(ry)
        x, z = x * c + z * s, -x * s + z * c
    if rz:
        c, s = math.cos(rz), math.sin(rz)
        x, y = x * c - y * s, x * s + y * c
    return (x, y, z)


def part_triangles(p: Part) -> list[Tri]:
    sx, sy, sz = p.size
    rx, ry, rz = (math.radians(a) for a in p.rotation)
    px, py, pz = p.position
    out = []
    for tri in unit_mesh(p.shape):
        out.append(tuple(
            (lambda r: (r[0] + px, r[1] + py, r[2] + pz))(_rot((v[0] * sx, v[1] * sy, v[2] * sz), rx, ry, rz))
            for v in tri))
    return out


def scene_triangles(parts: list[Part]) -> list[tuple[Tri, str, int]]:
    """All triangles as (tri, colour, part index)."""
    return [(t, p.color, i) for i, p in enumerate(parts) for t in part_triangles(p)]


def bounds(parts: list[Part]) -> tuple[Vec, Vec]:
    xs, ys, zs = [], [], []
    for p in parts:
        for t in part_triangles(p):
            for x, y, z in t:
                xs.append(x)
                ys.append(y)
                zs.append(z)
    if not xs:
        return (0, 0, 0), (0, 0, 0)
    return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


def _normal(t: Tri) -> Vec:
    (ax, ay, az), (bx, by, bz), (cx, cy, cz) = t
    ux, uy, uz = bx - ax, by - ay, bz - az
    vx, vy, vz = cx - ax, cy - ay, cz - az
    nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    ln = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
    return (nx / ln, ny / ln, nz / ln)


def export_stl(parts: list[Part], path: Path, name: str = "fate_blueprint", scale: float = 1000.0) -> int:
    """ASCII STL in millimetres (scale 1000) — ready for slicers. Returns triangle count."""
    tris = [t for p in parts for t in part_triangles(p)]
    safe = re.sub(r"[^A-Za-z0-9_]", "_", name)[:60] or "model"
    with open(path, "w", encoding="ascii") as fh:
        fh.write(f"solid {safe}\n")
        for t in tris:
            n = _normal(t)
            fh.write(f"  facet normal {n[0]:.6f} {n[1]:.6f} {n[2]:.6f}\n    outer loop\n")
            for x, y, z in t:
                # STL convention is Z-up: (x, y, z)_Yup -> (x, -z, y)
                fh.write(f"      vertex {x * scale:.4f} {-z * scale:.4f} {y * scale:.4f}\n")
            fh.write("    endloop\n  endfacet\n")
        fh.write(f"endsolid {safe}\n")
    return len(tris)


def export_obj(parts: list[Part], path: Path) -> Path:
    """Wavefront OBJ + MTL with one object and one colour material per part (metres, Y-up)."""
    path = Path(path)
    mtl = path.with_suffix(".mtl")
    colors: dict[str, str] = {}
    lines = [f"mtllib {mtl.name}"]
    vi = 1
    for i, p in enumerate(parts):
        mat = colors.setdefault(p.color, f"mat_{len(colors)}")
        lines.append(f"o {re.sub(r'[^A-Za-z0-9_]', '_', p.name) or 'part'}_{i}")
        lines.append(f"usemtl {mat}")
        for t in part_triangles(p):
            for x, y, z in t:
                lines.append(f"v {x:.5f} {y:.5f} {z:.5f}")
            lines.append(f"f {vi} {vi + 1} {vi + 2}")
            vi += 3
    path.write_text("\n".join(lines) + "\n", "utf-8")
    m = []
    for col, name in colors.items():
        r, g, b = (int(col[k:k + 2], 16) / 255 for k in (1, 3, 5))
        m += [f"newmtl {name}", f"Kd {r:.4f} {g:.4f} {b:.4f}", "Ka 0 0 0", "Ks 0.3 0.3 0.3", "Ns 40", ""]
    mtl.write_text("\n".join(m), "utf-8")
    return path


def mirror_x(parts: list[Part], suffix: str = " (R)") -> list[Part]:
    """Mirror parts across the YZ plane (for symmetric designs)."""
    out = []
    for p in parts:
        out.append(Part(p.name.replace("(L)", "").strip() + suffix if "(L)" in p.name else p.name + suffix,
                        p.shape, [-p.position[0], p.position[1], p.position[2]], list(p.size),
                        [p.rotation[0], -p.rotation[1], -p.rotation[2]], p.color, p.material, p.group))
    return out
