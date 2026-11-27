"""AI blueprint generation: a structured design spec plus a primitive-based 3D model."""
from __future__ import annotations

import json
import re

from ..ai.providers.base import ChatMessage, ChatRequest
from ..core.exceptions import FateError
from .geometry import SHAPES, Part, sanitize

SYSTEM_PROMPT = f"""You are FATE AI's blueprint designer. You turn an idea into a concept design document and a
3D concept model built from simple primitives.

Scope and safety: blueprints are concept art, props, cosplay, hobby, maker and educational designs. Never provide
instructions for functional weapons, explosives, or anything designed to injure people; depict such items only as
non-functional props. Flag real-world hazards (high voltage, batteries, heat, moving parts) in "safety".

Reply with ONE JSON object and nothing else:
{{
  "title": str, "category": str, "summary": str (2-4 sentences),
  "specs": {{"<spec name>": "<value with units>", ...}}  (6-12 key specs: dimensions, mass, power, materials…),
  "subsystems": [{{"name": str, "description": str}}],
  "materials": [str],
  "bill_of_materials": [{{"item": str, "qty": number, "notes": str}}],
  "build_steps": [str],
  "safety": [str],
  "parts": [{{"name": str, "shape": one of {list(SHAPES)}, "position": [x,y,z], "size": [sx,sy,sz],
             "rotation": [rx,ry,rz], "color": "#RRGGBB", "group": str}}]
}}

3D model rules: metres, Y is up, the object stands on y=0 centred at x=0,z=0, facing +Z. "position" is the centre
of the part, "size" is the full width/height/depth, rotation is degrees. Use 15-80 parts, realistic proportions,
symmetric left/right pairs where appropriate, and distinct colours per material."""


def build_messages(idea: str, existing: dict | None = None, revision: str = "") -> list[ChatMessage]:
    if existing and revision:
        return [ChatMessage("user", f"Current blueprint JSON:\n{json.dumps(existing)[:60000]}\n\n"
                                    f"Revise it: {revision}\nReturn the complete updated JSON object.")]
    return [ChatMessage("user", f"Design a blueprint for: {idea}")]


def extract_json(text: str) -> dict:
    """Pull the first JSON object out of a model reply (tolerates code fences and chatter)."""
    t = text.strip()
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", t, re.S)
    if m:
        t = m.group(1)
    start = t.find("{")
    if start < 0:
        raise FateError("The model did not return a blueprint (no JSON found). Try again or use another model.")
    depth, in_str, esc = 0, False, False
    for i, ch in enumerate(t[start:], start):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(t[start:i + 1])
                except json.JSONDecodeError as e:
                    raise FateError(f"The model returned malformed JSON: {e}") from None
    raise FateError("The model's reply was cut off before the blueprint finished. Increase max tokens or retry.")


def normalize(data: dict) -> tuple[dict, list[Part]]:
    """Split a model reply into a clean spec dict and sanitised parts."""
    def strs(v, n=60):
        return [str(x)[:500] for x in (v or [])][:n] if isinstance(v, list) else []
    spec = {
        "title": str(data.get("title", "Untitled blueprint"))[:120],
        "category": str(data.get("category", "General"))[:60],
        "summary": str(data.get("summary", ""))[:2000],
        "specs": {str(k)[:80]: str(v)[:200] for k, v in (data.get("specs") or {}).items()}
        if isinstance(data.get("specs"), dict) else {},
        "subsystems": [{"name": str(s.get("name", ""))[:100], "description": str(s.get("description", ""))[:1000]}
                       for s in (data.get("subsystems") or []) if isinstance(s, dict)][:40],
        "materials": strs(data.get("materials")),
        "bill_of_materials": [{"item": str(b.get("item", ""))[:150], "qty": b.get("qty", 1),
                               "notes": str(b.get("notes", ""))[:300]}
                              for b in (data.get("bill_of_materials") or []) if isinstance(b, dict)][:200],
        "build_steps": strs(data.get("build_steps"), 100),
        "safety": strs(data.get("safety"), 40),
    }
    return spec, sanitize(data.get("parts"))


def generate(registry, provider_id: str, model: str, idea: str, existing: dict | None = None,
             revision: str = "", max_tokens: int = 8000, cancel=None, on_token=None) -> tuple[dict, list[Part]]:
    provider = registry.get(provider_id)
    req = ChatRequest(model, build_messages(idea, existing, revision), system=SYSTEM_PROMPT, temperature=0.4,
                      max_tokens=max_tokens)
    chunks = []
    for ch in provider.stream_chat(req, cancel=cancel):
        if ch.text:
            chunks.append(ch.text)
            if on_token:
                on_token(ch.text)
    spec, parts = normalize(extract_json("".join(chunks)))
    if not parts:
        raise FateError("The model returned a spec but no 3D parts. Try again, or use Auto 3D (offline).")
    return spec, parts


def template_spec(template, parts: list[Part], idea: str, params: dict) -> dict:
    """A starter spec for an offline-generated model, derived from its parts."""
    from collections import Counter
    from .geometry import bounds
    (x0, y0, z0), (x1, y1, z1) = bounds(parts)
    groups = Counter(p.group or "general" for p in parts)
    return {
        "title": idea.strip()[:80] or template.name,
        "category": template.name,
        "summary": f"{template.description} Generated offline from the '{template.name}' template — use "
                   f"'Generate with AI' to get a detailed engineering write-up.",
        "specs": {"Overall width": f"{(x1 - x0):.2f} m", "Overall height": f"{(y1 - y0):.2f} m",
                  "Overall depth": f"{(z1 - z0):.2f} m", "Part count": str(len(parts)),
                  **{template.params[k][3]: str(v) for k, v in params.items() if k in template.params}},
        "subsystems": [{"name": g.title(), "description": f"{n} parts"} for g, n in groups.items()],
        "materials": [], "bill_of_materials": [{"item": p.name, "qty": 1, "notes": p.shape} for p in parts],
        "build_steps": [], "safety": [],
    }


def spec_markdown(spec: dict) -> str:
    out = [f"# {spec.get('title', 'Blueprint')}", f"*{spec.get('category', '')}*", "", spec.get("summary", ""), ""]
    if spec.get("specs"):
        out += ["## Specifications", "| Spec | Value |", "|---|---|"]
        out += [f"| {k} | {v} |" for k, v in spec["specs"].items()]
        out.append("")
    if spec.get("subsystems"):
        out.append("## Subsystems")
        out += [f"- **{s['name']}** — {s['description']}" for s in spec["subsystems"]]
        out.append("")
    if spec.get("materials"):
        out += ["## Materials"] + [f"- {m}" for m in spec["materials"]] + [""]
    if spec.get("bill_of_materials"):
        out += ["## Bill of materials", "| Item | Qty | Notes |", "|---|---|---|"]
        out += [f"| {b['item']} | {b['qty']} | {b['notes']} |" for b in spec["bill_of_materials"]]
        out.append("")
    if spec.get("build_steps"):
        out += ["## Build steps"] + [f"{i}. {s}" for i, s in enumerate(spec["build_steps"], 1)] + [""]
    if spec.get("safety"):
        out += ["## Safety"] + [f"- ⚠ {s}" for s in spec["safety"]] + [""]
    return "\n".join(out)
