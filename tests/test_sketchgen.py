import numpy as np
import pytest
from PIL import Image

from kakao_emoticon_gen import prompts, sketchgen
from kakao_emoticon_gen.backends import get_backend
from kakao_emoticon_gen.backends.sketch import SketchGenerator


def _visible(img: Image.Image) -> np.ndarray:
    arr = np.array(img.convert("RGBA"))
    return arr[arr[:, :, 3] > 0]


def test_render_character_size_mode_and_transparency():
    img = sketchgen.render_character("기쁨", size=360, seed=1)
    assert img.size == (360, 360)
    assert img.mode == "RGBA"
    # 배경은 투명하게 남아야 카카오 규격을 통과한다
    assert img.getpixel((2, 2))[3] == 0
    assert len(_visible(img)) > 0


def test_render_character_is_deterministic():
    a = sketchgen.render_character("슬픔", size=200, seed=42)
    b = sketchgen.render_character("슬픔", size=200, seed=42)
    assert np.array_equal(np.array(a), np.array(b))


def test_different_seeds_change_the_drawing():
    a = sketchgen.render_character("슬픔", size=200, seed=1)
    b = sketchgen.render_character("슬픔", size=200, seed=2)
    assert not np.array_equal(np.array(a), np.array(b))


def test_unregistered_keyword_still_renders():
    """EXPRESSIONS에 없는 키워드도 해시 기반 폴백으로 그려져야 한다."""
    img = sketchgen.render_character("존재하지않는감정", size=200, seed=3)
    assert len(_visible(img)) > 0


def test_every_recommended_emotion_has_an_expression():
    for keyword in prompts.RECOMMENDED_EMOTION_SET:
        assert keyword in sketchgen.EXPRESSIONS, keyword


def test_expression_parts_reference_known_kinds():
    for keyword, spec in sketchgen.EXPRESSIONS.items():
        assert spec["eyes"] in sketchgen._EYE_KINDS, keyword
        assert spec["mouth"] in sketchgen._MOUTH_KINDS, keyword
        assert spec["pose"] in sketchgen._POSE_ANGLES, keyword


def test_make_character_is_deterministic():
    assert sketchgen.make_character(7) == sketchgen.make_character(7)
    assert sketchgen.make_character(7) != sketchgen.make_character(8)


def test_same_character_keeps_identity_across_expressions():
    """세트 통일감의 핵심 — 표정이 달라도 몸 색은 같아야 한다."""
    char = sketchgen.make_character(5)
    colors = set()
    for keyword in ("기쁨", "슬픔", "화남", "졸림"):
        img = sketchgen.render_character(keyword, size=200, seed=1, character=char)
        arr = np.array(img.convert("RGBA"))
        body = arr[arr[:, :, 3] > 200][:, :3]
        # 가장 많이 쓰인 색 = 몸통 채색
        values, counts = np.unique(body, axis=0, return_counts=True)
        colors.add(tuple(values[counts.argmax()]))
    assert len(colors) == 1


def test_contact_sheet_dimensions():
    sheet = sketchgen.render_contact_sheet(["기쁨", "슬픔", "화남"], cell=100, cols=2, seed=1)
    assert sheet.size == (200, 200)  # 3컷 → 2열 2행


def test_contact_sheet_rejects_empty():
    with pytest.raises(ValueError):
        sketchgen.render_contact_sheet([], cell=100)


def test_render_lineup_returns_distinct_characters():
    sheet, characters = render = sketchgen.render_lineup(count=4, cell=100, cols=2, base_seed=0)
    assert sheet.size == (200, 200)
    assert len(characters) == 4
    assert len({(c.color, c.tuft, round(c.rx_ratio, 4)) for c in characters}) > 1


def test_sketch_backend_extracts_keyword_from_prompt():
    """파이프라인 프롬프트에서 원래 감정 키워드를 되찾아야 표정이 맞는다."""
    backend = SketchGenerator(character=sketchgen.make_character(5))
    prompt = prompts.build_prompt("슬픔").prompt
    from_prompt = backend.generate(prompt, seed=9, size=200)
    direct = sketchgen.render_character("슬픔", size=200, seed=9,
                                        character=sketchgen.make_character(5))
    assert np.array_equal(np.array(from_prompt), np.array(direct))


def test_sketch_backend_survives_unexpected_prompt_format():
    backend = SketchGenerator()
    img = backend.generate("완전히 다른 형식의 프롬프트", seed=1, size=150)
    assert img.size == (150, 150)


def test_sketch_backend_registered_in_factory():
    assert isinstance(get_backend("sketch", character_seed=5), SketchGenerator)
