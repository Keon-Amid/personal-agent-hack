import pytest

from agent import quiz
from data.sie import STYLES


def test_quiz_shape_matches_system():
    assert quiz.QUIZ["styles"] == STYLES
    qs = quiz.QUIZ["questions"]
    assert len(qs) == 5
    for q in qs:
        assert q["references"]
        for o in q["options"]:
            assert set(o.get("weights", {})) <= set(STYLES)
            if q["kind"] == "image_choice":
                assert o["image_url"].startswith("https://") and o["ref_url"].startswith("https://")


def test_scandi_dog_owner():
    r = quiz.score({"q1_mood": "light", "q2_touch": "linen_oak", "q3_never": "loft",
                    "q4_life": "kids_pets", "q5_budget": "mid"})
    assert r["style"] == "scandinavian"  # 3+2 beats warm minimal 1+2
    assert r["style_text"] == ("scandinavian living room, linen, light oak, beige, "
                               "durable, easy to clean, washable cover")
    assert r["budget_usd"] == 500
    assert r["style_scores"]["industrial"] == -3


def test_rejection_lowers_a_style():
    base = {"q1_mood": "light", "q2_touch": "linen_oak", "q4_life": "solo", "q5_budget": "unsure"}
    assert quiz.score({**base, "q3_never": "loft"})["style"] == "scandinavian"
    r = quiz.score({**base, "q3_never": "stark"})
    assert r["style"] == "scandinavian" and r["style_scores"]["warm minimal"] == 1
    assert r["budget_usd"] is None


def test_negative_never_reaches_style_text():
    r = quiz.score({"q1_mood": "moody", "q2_touch": "leather_metal", "q3_never": "formal",
                    "q4_life": "hosting", "q5_budget": "comfortable"})
    assert r["style"] == "dark modern"  # 3+2 beats industrial 1+3
    assert "traditional" not in r["style_text"]


def test_missing_answer_raises():
    with pytest.raises(ValueError):
        quiz.score({"q1_mood": "light"})


def test_every_style_is_reachable():
    import itertools
    qs = quiz.QUIZ["questions"]
    won = {quiz.score(dict(zip([q["id"] for q in qs], combo)))["style"]
           for combo in itertools.product(*[[o["id"] for o in q["options"]] for q in qs])}
    assert won == set(STYLES)


def test_catalog_support_reads_superlinked_labels(tmp_path):
    import json
    (tmp_path / "p.json").write_text(json.dumps({"products": [
        {"id": "a", "name": "A sofa", "category": "sofa"}, {"id": "b", "name": "B rug", "category": "rug"}]}))
    (tmp_path / "e.json").write_text(json.dumps({"product_styles": {
        "a": [{"style": "scandinavian", "score": 0.09}], "b": [{"style": "scandinavian", "score": 0.03}]}}))
    r = quiz.catalog_support("scandinavian", tmp_path / "p.json", tmp_path / "e.json")
    assert r["covered"] == ["sofa"]  # the rug's 0.03 label is under the 0.05 mute line
    assert r["slots"]["sofa"][0]["name"] == "A sofa"


def test_catalog_support_on_real_catalog():
    for style in STYLES:
        r = quiz.catalog_support(style)
        assert set(r["slots"]) == {"sofa", "armchair", "coffee_table", "rug", "floor_lamp"}
