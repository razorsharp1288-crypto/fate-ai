import json
import math

import httpx
import pytest

from fate_ai.blueprints import geometry as g
from fate_ai.blueprints.generator import extract_json, generate, normalize, spec_markdown, template_spec
from fate_ai.blueprints.service import BlueprintService
from fate_ai.blueprints.templates import BY_ID, TEMPLATES, build, match_template
from fate_ai.core.exceptions import FateError, ValidationError


def test_every_shape_meshes_and_is_closed():
    for shape in g.SHAPES:
        tris = g.unit_mesh(shape)
        assert tris
        # closed manifold: every edge is shared by exactly two triangles
        from collections import Counter
        def k(v):
            return tuple(round(c, 5) for c in v)
        edges = Counter()
        for t in tris:
            for a, b in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
                edges[tuple(sorted((k(a), k(b))))] += 1
        assert all(n == 2 for n in edges.values()), shape


def test_transform_and_bounds():
    p = g.Part("b", "box", [1, 2, 3], [2, 4, 6], [0, 0, 0])
    (x0, y0, z0), (x1, y1, z1) = g.bounds([p])
    assert (x0, y0, z0, x1, y1, z1) == pytest.approx((0, 0, 0, 2, 4, 6))
    r = g.Part("r", "box", [0, 0, 0], [2, 1, 1], [0, 90, 0])
    (x0, _, z0), (x1, _, z1) = g.bounds([r])
    assert x1 - x0 == pytest.approx(1, abs=1e-6) and z1 - z0 == pytest.approx(2, abs=1e-6)


def test_sanitize_untrusted_parts():
    parts = g.sanitize([{"name": "x" * 500, "shape": "rm -rf", "position": [1, "a"], "size": [-5, 1e9, 1],
                         "color": "red"}, "junk", {"shape": "sphere", "position": [math.inf, 0, 0]}])
    assert len(parts) == 2
    assert parts[0].shape == "box" and len(parts[0].name) == 80 and parts[0].color == "#8B5CF6"
    assert parts[0].size[0] == 0.001 and parts[0].size[1] == 1000
    assert parts[1].position == [0, 0.5, 0]
    assert len(g.sanitize([{}] * 1000)) == g.MAX_PARTS


def test_stl_and_obj_export(tmp_path):
    parts = build("drone")
    n = g.export_stl(parts, tmp_path / "d.stl", "drone")
    txt = (tmp_path / "d.stl").read_text()
    assert txt.startswith("solid drone") and txt.count("facet normal") == n > 100
    g.export_obj(parts, tmp_path / "d.obj")
    obj = (tmp_path / "d.obj").read_text()
    assert obj.startswith("mtllib d.mtl") and obj.count("\nf ") == n
    assert "newmtl" in (tmp_path / "d.mtl").read_text()


@pytest.mark.parametrize("tpl", [t.id for t in TEMPLATES])
def test_templates_build_on_ground(tpl):
    parts = build(tpl)
    assert 3 <= len(parts) <= g.MAX_PARTS
    (_, y0, _), (_, y1, _) = g.bounds(parts)
    assert y0 >= -0.05 and y1 > 0.1


def test_template_params_clamped_and_matching():
    tall = build("armor", height=99)
    (_, _, _), (_, y1, _) = g.bounds(tall)
    assert y1 < 2.6  # clamped to 2.4 m wearer
    assert match_template("I want an Iron Man suit").id == "armor"
    assert match_template("hexacopter drone for filming").id == "drone"
    assert match_template("tiny house in the woods").id == "cabin"
    assert match_template("something weird").id == "generic"


def test_extract_json_variants():
    assert extract_json('Sure!\n```json\n{"a": {"b": "}"}}\n```\nEnjoy')["a"]["b"] == "}"
    assert extract_json('prefix {"x": 1} suffix') == {"x": 1}
    with pytest.raises(FateError):
        extract_json("no json here")
    with pytest.raises(FateError):
        extract_json('{"cut": "off')


def test_normalize_and_markdown():
    spec, parts = normalize({"title": "Suit", "specs": {"Height": "1.9 m"}, "bill_of_materials": [
        {"item": "EVA foam", "qty": 4}], "build_steps": ["Cut"], "safety": ["Heat gun"],
        "parts": [{"name": "Helmet", "shape": "sphere", "position": [0, 1.7, 0], "size": [0.25, 0.3, 0.25]}]})
    assert spec["title"] == "Suit" and parts[0].name == "Helmet"
    md = spec_markdown(spec)
    assert "| Height | 1.9 m |" in md and "⚠ Heat gun" in md and "1. Cut" in md


def test_generate_with_mock_provider(ctx):
    from fate_ai.ai.providers.registry import ProviderRegistry
    reply = {"title": "Drone X", "category": "Drone", "summary": "s",
             "parts": [{"name": "Body", "shape": "box", "position": [0, 0.1, 0], "size": [0.2, 0.05, 0.3]}]}
    text = "Here is your design:\n```json\n" + json.dumps(reply) + "\n```"
    captured = {}

    def handler(req):
        body = json.loads(req.content)
        captured["system"] = body["messages"][0]["content"]
        lines = [json.dumps({"message": {"content": text[i:i + 40]}, "done": False}) for i in range(0, len(text), 40)]
        lines.append(json.dumps({"done": True}))
        return httpx.Response(200, content="\n".join(lines).encode())
    reg = ProviderRegistry(ctx.provider_repo, ctx.credentials, transport=httpx.MockTransport(handler))
    spec, parts = generate(reg, "ollama", "m", "a drone")
    assert spec["title"] == "Drone X" and parts[0].name == "Body"
    assert "non-functional props" in captured["system"]


def test_service_roundtrip(ctx, tmp_path):
    svc = BlueprintService(ctx.db, ctx.audit)
    parts = build("armor")
    spec = template_spec(BY_ID["armor"], parts, "Iron suit", {"height": 1.85})
    bid = svc.create("Iron suit", "Armor", "an iron suit", spec, parts)
    b = svc.get(bid)
    assert len(b["parts"]) == len(parts) and b["spec"]["specs"]["Part count"] == str(len(parts))
    svc.save(bid, notes="paint it gold")
    assert svc.list("iron")[0]["id"] == bid
    f = svc.export_file(bid, tmp_path / "s.fateblueprint")
    bid2 = svc.import_file(f)
    assert svc.get(bid2)["notes"] == "paint it gold" or svc.get(bid2)["name"] == "Iron suit"
    assert svc.export_stl(bid, tmp_path / "s.stl") > 500
    svc.export_markdown(bid, tmp_path / "s.md")
    assert "Iron suit" in (tmp_path / "s.md").read_text()
    (tmp_path / "bad.json").write_text('{"format": "other"}')
    with pytest.raises(ValidationError):
        svc.import_file(tmp_path / "bad.json")
    svc.delete(bid)
    assert svc.get(bid) is None
