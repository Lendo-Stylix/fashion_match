from outfitmatch.preference.structuring import PromptStructurer


def test_structurer_parses_user_hard_and_caches(tmp_path):
    calls: list[str] = []

    def fake(prompt: str) -> str:
        calls.append(prompt)
        return ('{"hard":{"colors_avoid":["bright"],"categories_exclude":[],'
                '"materials_require":[]},'
                '"soft":{"style":"minimalist","color":"","fit":"oversized"}}')

    s = PromptStructurer(fake, cache_dir=str(tmp_path / "c"))
    p1 = s.structure("minimalist, no bright colors, oversized", "pear")
    p2 = s.structure("minimalist, no bright colors, oversized", "pear")

    assert p1.hard.colors_avoid == ["bright"]
    assert p1.hard.source == "user"          # user gave hard -> no fallback
    assert p1.soft.fit == "oversized"
    assert p2.soft.style == "minimalist"
    assert len(calls) == 1                    # second call served from cache


def test_structurer_body_fallback_when_no_hard(tmp_path):
    def fake(prompt: str) -> str:
        return ('{"hard":{"colors_avoid":[],"categories_exclude":[],'
                '"materials_require":[]},'
                '"soft":{"style":"casual","color":"","fit":""}}')

    s = PromptStructurer(fake, cache_dir=str(tmp_path / "c"))
    p = s.structure("just casual everyday", "apple")
    assert p.hard.source == "body_fallback"
    assert p.hard.fit_bias == "defined_waist"


def test_structurer_strips_json_fence(tmp_path):
    def fake(prompt: str) -> str:
        return ('```json\n{"hard":{"colors_avoid":[],"categories_exclude":[],'
                '"materials_require":[]},"soft":{"style":"sporty",'
                '"color":"","fit":""}}\n```')

    s = PromptStructurer(fake, cache_dir=str(tmp_path / "c"))
    p = s.structure("sporty", "rectangle")
    assert p.soft.style == "sporty"
