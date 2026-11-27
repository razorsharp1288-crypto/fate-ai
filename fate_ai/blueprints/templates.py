"""Offline procedural generators ("Auto 3D" without AI).

Each generator returns parts for a recognisable concept model from a few
parameters. They are concept/prop models for visualisation, cosplay and
hobby builds — not engineering-validated designs.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .geometry import Part, mirror_x


@dataclass
class Template:
    id: str
    name: str
    description: str
    keywords: tuple[str, ...]
    build: Callable[..., list[Part]]
    params: dict = field(default_factory=dict)  # name -> (default, min, max, label)


def _p(name, shape, pos, size, color, rot=(0, 0, 0), group="", material=""):
    return Part(name, shape, list(pos), list(size), list(rot), color, material, group)


# ----------------------------------------------------------------------------- armor suit
def armor_suit(height: float = 1.85, bulk: float = 1.0, primary: str = "#B91C1C", secondary: str = "#D4A017",
               glow: str = "#7DD3FC") -> list[Part]:
    h = height / 1.85
    b = bulk
    P = lambda *a, **k: _p(*a, **k)  # noqa: E731
    L: list[Part] = []
    # left-side limbs (mirrored later)
    L += [
        P("Boot (L)", "box", (0.11 * b, 0.05 * h, 0.03), (0.13 * b, 0.10 * h, 0.30), primary, group="legs"),
        P("Boot toe (L)", "wedge", (0.11 * b, 0.05 * h, 0.17), (0.12 * b, 0.08 * h, 0.08), secondary, group="legs"),
        P("Shin (L)", "capsule", (0.11 * b, 0.32 * h, 0), (0.15 * b, 0.42 * h, 0.16 * b), primary, group="legs"),
        P("Shin plate (L)", "box", (0.11 * b, 0.32 * h, 0.07 * b), (0.10 * b, 0.30 * h, 0.04), secondary, group="legs"),
        P("Knee cap (L)", "sphere", (0.11 * b, 0.54 * h, 0.06 * b), (0.11 * b, 0.10 * h, 0.08 * b), secondary,
          group="legs"),
        P("Thigh (L)", "capsule", (0.11 * b, 0.76 * h, 0), (0.18 * b, 0.42 * h, 0.19 * b), primary, group="legs"),
        P("Hip plate (L)", "box", (0.17 * b, 0.95 * h, 0), (0.06 * b, 0.14 * h, 0.18 * b), secondary, group="torso"),
        P("Shoulder (L)", "sphere", (0.27 * b, 1.46 * h, 0), (0.20 * b, 0.17 * h, 0.20 * b), primary, group="arms"),
        P("Shoulder pauldron (L)", "capsule", (0.29 * b, 1.50 * h, 0), (0.17 * b, 0.10 * h, 0.22 * b), secondary,
          rot=(0, 0, 70), group="arms"),
        P("Upper arm (L)", "capsule", (0.30 * b, 1.26 * h, 0), (0.12 * b, 0.32 * h, 0.12 * b), primary, group="arms"),
        P("Elbow (L)", "sphere", (0.30 * b, 1.08 * h, 0), (0.10 * b, 0.09 * h, 0.10 * b), secondary, group="arms"),
        P("Forearm gauntlet (L)", "capsule", (0.31 * b, 0.92 * h, 0.01), (0.12 * b, 0.30 * h, 0.12 * b), primary,
          group="arms"),
        P("Gauntlet band (L)", "cylinder", (0.31 * b, 0.84 * h, 0.01), (0.13 * b, 0.04 * h, 0.13 * b), secondary,
          group="arms"),
        P("Hand (L)", "box", (0.31 * b, 0.72 * h, 0.01), (0.08 * b, 0.13 * h, 0.10 * b), secondary, group="arms"),
        P("Palm emitter (L)", "cylinder", (0.355 * b, 0.72 * h, 0.01), (0.04, 0.012, 0.04), glow, rot=(0, 0, 90),
          group="arms"),
        P("Back thruster (L)", "cylinder", (0.09 * b, 1.30 * h, -0.17 * b), (0.08 * b, 0.22 * h, 0.08 * b), secondary,
          group="back"),
        P("Thruster glow (L)", "cone", (0.09 * b, 1.16 * h, -0.17 * b), (0.06 * b, 0.07 * h, 0.06 * b), glow,
          rot=(180, 0, 0), group="back"),
        P("Eye (L)", "box", (0.035, 1.725 * h, 0.105), (0.045, 0.012, 0.01), glow, group="helmet"),
    ]
    parts = L + mirror_x(L)
    parts += [
        P("Pelvis", "box", (0, 0.98 * h, 0), (0.30 * b, 0.16 * h, 0.20 * b), primary, group="torso"),
        P("Codpiece", "wedge", (0, 0.93 * h, 0.09 * b), (0.12 * b, 0.12 * h, 0.05), secondary, rot=(180, 0, 0),
          group="torso"),
        P("Abdomen", "box", (0, 1.13 * h, 0), (0.28 * b, 0.18 * h, 0.19 * b), secondary, group="torso"),
        P("Abdomen plates", "box", (0, 1.13 * h, 0.09 * b), (0.20 * b, 0.15 * h, 0.03), primary, group="torso"),
        P("Chest", "capsule", (0, 1.36 * h, 0), (0.44 * b, 0.34 * h, 0.27 * b), primary, group="torso"),
        P("Chest plate", "box", (0, 1.38 * h, 0.12 * b), (0.32 * b, 0.20 * h, 0.05), secondary, group="torso"),
        P("Chest reactor ring", "torus", (0, 1.38 * h, 0.15 * b), (0.11, 0.03, 0.11), "#CBD5E1", rot=(90, 0, 0),
          group="torso"),
        P("Chest reactor core", "cylinder", (0, 1.38 * h, 0.15 * b), (0.075, 0.02, 0.075), glow, rot=(90, 0, 0),
          group="torso"),
        P("Back pack", "box", (0, 1.36 * h, -0.15 * b), (0.30 * b, 0.30 * h, 0.08 * b), secondary, group="back"),
        P("Neck", "cylinder", (0, 1.56 * h, 0), (0.10, 0.07 * h, 0.10), secondary, group="helmet"),
        P("Helmet", "capsule", (0, 1.70 * h, 0), (0.21, 0.27 * h, 0.23), primary, group="helmet"),
        P("Faceplate", "box", (0, 1.69 * h, 0.085), (0.15, 0.17 * h, 0.05), secondary, group="helmet"),
        P("Jaw", "wedge", (0, 1.615 * h, 0.09), (0.13, 0.05 * h, 0.05), secondary, rot=(180, 0, 0), group="helmet"),
    ]
    return parts


# ----------------------------------------------------------------------------- drone
def quad_drone(span: float = 0.45, arms: int = 4, body: str = "#1F2937", accent: str = "#8B5CF6") -> list[Part]:
    import math
    arms = max(3, min(8, int(arms)))
    r = span / 2
    parts = [_p("Body", "box", (0, 0.10, 0), (span * 0.28, 0.05, span * 0.36), body, group="frame"),
             _p("Canopy", "capsule", (0, 0.135, 0), (span * 0.22, 0.06, span * 0.30), accent, rot=(90, 0, 0),
                group="frame"),
             _p("Battery", "box", (0, 0.065, 0), (span * 0.16, 0.03, span * 0.26), "#374151", group="power"),
             _p("Camera", "sphere", (0, 0.075, span * 0.19), (0.04, 0.04, 0.04), "#0F172A", group="payload")]
    for i in range(arms):
        a = 2 * math.pi * (i + 0.5) / arms
        x, z = r * math.cos(a), r * math.sin(a)
        mx, mz = x / 2, z / 2
        parts += [
            _p(f"Arm {i + 1}", "box", (mx, 0.10, mz), (r, 0.02, 0.025), body, rot=(0, -math.degrees(a), 0), group="frame"),
            _p(f"Motor {i + 1}", "cylinder", (x, 0.12, z), (0.035, 0.04, 0.035), "#9CA3AF", group="propulsion"),
            _p(f"Propeller {i + 1}", "cylinder", (x, 0.145, z), (span * 0.42, 0.004, span * 0.42), accent,
               group="propulsion"),
            _p(f"Landing leg {i + 1}", "cylinder", (x * 0.6, 0.04, z * 0.6), (0.012, 0.08, 0.012), body, group="frame"),
        ]
    return parts


# ----------------------------------------------------------------------------- robot arm
def robot_arm(reach: float = 0.8, joints: int = 3, color: str = "#F59E0B", dark: str = "#1F2937") -> list[Part]:
    joints = max(2, min(6, int(joints)))
    seg = reach / joints
    parts = [_p("Base", "cylinder", (0, 0.04, 0), (0.30, 0.08, 0.30), dark, group="base"),
             _p("Turntable", "cylinder", (0, 0.11, 0), (0.22, 0.06, 0.22), color, group="base")]
    y, x = 0.14, 0.0
    import math
    angles = [70, -35, -40, -25, -20, -15][:joints]
    heading = 0.0
    for i, ang in enumerate(angles):
        heading += ang if i == 0 else ang
        rad = math.radians(heading)
        dx, dy = seg * math.cos(rad), seg * math.sin(rad)
        parts.append(_p(f"Joint {i + 1}", "sphere", (x, y, 0), (0.10, 0.10, 0.10), dark, group="joints"))
        parts.append(_p(f"Link {i + 1}", "capsule", (x + dx / 2, y + dy / 2, 0), (0.07, seg, 0.07), color,
                        rot=(0, 0, heading - 90), group="links"))
        x, y = x + dx, y + dy
    parts += [_p("Wrist", "cylinder", (x, y, 0), (0.07, 0.05, 0.07), dark, group="tool"),
              _p("Gripper finger A", "box", (x + 0.03, y - 0.05, 0.02), (0.015, 0.08, 0.02), "#9CA3AF", group="tool"),
              _p("Gripper finger B", "box", (x + 0.03, y - 0.05, -0.02), (0.015, 0.08, 0.02), "#9CA3AF", group="tool")]
    return parts


# ----------------------------------------------------------------------------- rover
def rover(length: float = 0.9, wheels: int = 6, body: str = "#E5E7EB", accent: str = "#2563EB") -> list[Part]:
    wheels = max(4, min(8, int(wheels) // 2 * 2))
    w = length * 0.6
    per = wheels // 2
    parts = [_p("Chassis", "box", (0, 0.26, 0), (w, 0.10, length), body, group="body"),
             _p("Electronics box", "box", (0, 0.36, -0.05), (w * 0.7, 0.10, length * 0.5), accent, group="body"),
             _p("Mast", "cylinder", (0, 0.55, length * 0.3), (0.03, 0.40, 0.03), "#6B7280", group="sensors"),
             _p("Camera head", "box", (0, 0.77, length * 0.3), (0.14, 0.06, 0.06), "#111827", group="sensors"),
             _p("Solar panel", "box", (0, 0.43, -0.05), (w * 1.1, 0.01, length * 0.7), "#1E3A8A", group="power"),
             _p("Antenna dish", "cone", (w * 0.3, 0.50, -length * 0.35), (0.14, 0.04, 0.14), "#D1D5DB",
                rot=(180, 0, 0), group="comms")]
    for side in (-1, 1):
        for i in range(per):
            z = -length / 2 + length * (i + 0.5) / per
            parts.append(_p(f"Wheel {'L' if side < 0 else 'R'}{i + 1}", "cylinder", (side * (w / 2 + 0.05), 0.12, z),
                            (0.24, 0.08, 0.24), "#374151", rot=(0, 0, 90), group="wheels"))
            parts.append(_p(f"Suspension {'L' if side < 0 else 'R'}{i + 1}", "box", (side * (w / 2 + 0.01), 0.19, z),
                            (0.02, 0.12, 0.03), "#6B7280", group="wheels"))
    return parts


# ----------------------------------------------------------------------------- mech
def mech(height: float = 4.0, color: str = "#4B5563", accent: str = "#F97316") -> list[Part]:
    s = height / 4.0
    L = [_p("Foot (L)", "box", (0.6 * s, 0.12 * s, 0.1 * s), (0.5 * s, 0.24 * s, 0.9 * s), color, group="legs"),
         _p("Lower leg (L)", "box", (0.6 * s, 0.75 * s, 0), (0.35 * s, 1.0 * s, 0.4 * s), color, group="legs"),
         _p("Knee (L)", "sphere", (0.6 * s, 1.3 * s, 0.1 * s), (0.4 * s, 0.4 * s, 0.4 * s), accent, group="legs"),
         _p("Upper leg (L)", "box", (0.55 * s, 1.75 * s, 0), (0.4 * s, 0.8 * s, 0.45 * s), color, group="legs"),
         _p("Shoulder (L)", "box", (1.0 * s, 3.25 * s, 0), (0.5 * s, 0.4 * s, 0.6 * s), accent, group="arms"),
         _p("Arm (L)", "box", (1.05 * s, 2.7 * s, 0), (0.3 * s, 0.9 * s, 0.35 * s), color, group="arms"),
         _p("Hand (L)", "box", (1.05 * s, 2.15 * s, 0.05 * s), (0.28 * s, 0.25 * s, 0.3 * s), accent, group="arms")]
    return L + mirror_x(L) + [
        _p("Hip", "box", (0, 2.25 * s, 0), (1.0 * s, 0.35 * s, 0.6 * s), accent, group="torso"),
        _p("Torso", "box", (0, 2.9 * s, 0), (1.5 * s, 1.0 * s, 0.9 * s), color, group="torso"),
        _p("Cockpit", "wedge", (0, 3.0 * s, 0.5 * s), (0.8 * s, 0.6 * s, 0.25 * s), "#7DD3FC", group="torso"),
        _p("Head", "box", (0, 3.6 * s, 0.05 * s), (0.45 * s, 0.35 * s, 0.5 * s), color, group="head"),
        _p("Visor", "box", (0, 3.62 * s, 0.31 * s), (0.36 * s, 0.08 * s, 0.02 * s), "#EF4444", group="head")]


# ----------------------------------------------------------------------------- small house / structure
def cabin(width: float = 6.0, depth: float = 8.0, wall: str = "#A16207", roof: str = "#7F1D1D") -> list[Part]:
    h = 2.6
    return [_p("Foundation", "box", (0, 0.1, 0), (width + 0.3, 0.2, depth + 0.3), "#9CA3AF", group="structure"),
            _p("Walls", "box", (0, 0.2 + h / 2, 0), (width, h, depth), wall, group="structure"),
            _p("Roof (L)", "box", (-width / 4, 0.2 + h + 0.7, 0), (width * 0.62, 0.15, depth + 0.6), roof,
               rot=(0, 0, 25), group="roof"),
            _p("Roof (R)", "box", (width / 4, 0.2 + h + 0.7, 0), (width * 0.62, 0.15, depth + 0.6), roof,
               rot=(0, 0, -25), group="roof"),
            _p("Door", "box", (0, 1.2, depth / 2 + 0.01), (1.0, 2.0, 0.05), "#451A03", group="openings"),
            _p("Window (L)", "box", (-width / 3, 1.6, depth / 2 + 0.01), (1.0, 0.9, 0.05), "#BAE6FD", group="openings"),
            _p("Window (R)", "box", (width / 3, 1.6, depth / 2 + 0.01), (1.0, 0.9, 0.05), "#BAE6FD", group="openings"),
            _p("Chimney", "box", (width / 4, 0.2 + h + 1.2, -depth / 4), (0.6, 1.4, 0.6), "#57534E", group="roof")]


def generic(size: float = 1.0, color: str = "#8B5CF6") -> list[Part]:
    return [_p("Base", "box", (0, 0.1 * size, 0), (size, 0.2 * size, size), "#374151"),
            _p("Body", "cylinder", (0, 0.6 * size, 0), (0.6 * size, 0.8 * size, 0.6 * size), color),
            _p("Top", "sphere", (0, 1.1 * size, 0), (0.5 * size, 0.4 * size, 0.5 * size), "#C4B5FD")]


TEMPLATES: list[Template] = [
    Template("armor", "Armor suit", "Full-body powered-armor / cosplay suit (helmet, chest reactor, gauntlets, "
             "thrusters).", ("armor", "armour", "suit", "iron", "exosuit", "exoskeleton", "cosplay", "power armor",
                             "helmet"),
             armor_suit, {"height": (1.85, 1.2, 2.4, "Wearer height (m)"), "bulk": (1.0, 0.7, 1.5, "Bulk")}),
    Template("drone", "Multirotor drone", "Quad/hex-copter with motors, props, battery and camera.",
             ("drone", "quadcopter", "copter", "uav", "multirotor", "hexacopter"), quad_drone,
             {"span": (0.45, 0.15, 2.0, "Span (m)"), "arms": (4, 3, 8, "Arms")}),
    Template("arm", "Robot arm", "Articulated arm with base, joints and gripper.",
             ("robot arm", "arm", "manipulator", "gripper", "cobot"), robot_arm,
             {"reach": (0.8, 0.2, 3.0, "Reach (m)"), "joints": (3, 2, 6, "Joints")}),
    Template("rover", "Rover", "Wheeled exploration rover with mast camera and solar panel.",
             ("rover", "car", "vehicle", "buggy", "robot car", "wheels"), rover,
             {"length": (0.9, 0.3, 4.0, "Length (m)"), "wheels": (6, 4, 8, "Wheels")}),
    Template("mech", "Mech / walker", "Bipedal mech with cockpit.", ("mech", "mecha", "walker", "gundam", "robot"),
             mech, {"height": (4.0, 1.0, 20.0, "Height (m)")}),
    Template("cabin", "Cabin / building", "Small building with roof, door and windows.",
             ("house", "cabin", "building", "shed", "home", "hut"), cabin,
             {"width": (6.0, 2.0, 30.0, "Width (m)"), "depth": (8.0, 2.0, 30.0, "Depth (m)")}),
    Template("generic", "Generic object", "Simple placeholder form to start from.", (), generic,
             {"size": (1.0, 0.1, 10.0, "Size (m)")}),
]
BY_ID = {t.id: t for t in TEMPLATES}


def match_template(text: str) -> Template:
    t = (text or "").lower()
    best, score = BY_ID["generic"], 0
    for tpl in TEMPLATES:
        s = sum(len(k) for k in tpl.keywords if k in t)
        if s > score:
            best, score = tpl, s
    return best


def build(template_id: str, **params) -> list[Part]:
    tpl = BY_ID[template_id]
    clean = {}
    for k, (default, lo, hi, _label) in tpl.params.items():
        v = params.get(k, default)
        try:
            v = type(default)(v)
        except (TypeError, ValueError):
            v = default
        clean[k] = max(lo, min(hi, v))
    for k in ("primary", "secondary", "glow", "color", "accent", "body"):
        if k in params and isinstance(params[k], str):
            clean[k] = params[k]
    import inspect
    allowed = set(inspect.signature(tpl.build).parameters)
    return tpl.build(**{k: v for k, v in clean.items() if k in allowed})
