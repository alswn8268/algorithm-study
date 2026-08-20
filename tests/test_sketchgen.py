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
    sheet, characters = sketchgen.render_lineup(count=4, cell=100, cols=2, base_seed=0)
    assert sheet.size == (200, 200)
    assert len(characters) == 4
    # 후보끼리 종도 색도 겹치면 비교할 이유가 없다
    assert len({c.animal for c in characters}) == 4
    assert len({c.color for c in characters}) == 4


def test_lineup_covers_every_animal_when_it_fits():
    _, characters = sketchgen.render_lineup(
        count=len(sketchgen.ANIMALS), cell=60, cols=4, base_seed=0
    )
    assert [c.animal for c in characters] == sketchgen.ANIMALS


def test_every_archetype_declares_an_ear_and_nose():
    for animal, archetype in sketchgen.ANIMAL_ARCHETYPES.items():
        assert archetype["ear"] in ("round", "tiny", "long", "pointy", "floppy", "none"), animal
        assert archetype["nose"] in ("dot", "big", "triangle", "beak", "none"), animal


def test_make_character_follows_the_archetype():
    for animal in sketchgen.ANIMALS:
        char = sketchgen.make_character(1, animal=animal)
        archetype = sketchgen.ANIMAL_ARCHETYPES[animal]
        assert char.animal == animal
        assert char.ear == archetype["ear"]
        assert char.nose == archetype["nose"]


def test_make_character_honours_explicit_colour():
    forced = (1, 2, 3, 255)
    assert sketchgen.make_character(5, color=forced).color == forced


@pytest.mark.parametrize("animal", sketchgen.ANIMALS)
def test_every_animal_renders_for_every_expression(animal):
    """부리(입 대체)·앞니·볼주머니 조합에서 렌더가 깨지지 않아야 한다."""
    char = sketchgen.make_character(3, animal=animal)
    for keyword in ("기쁨", "슬픔", "놀람", "졸림"):
        img = sketchgen.render_character(keyword, size=140, seed=2, character=char)
        assert img.size == (140, 140)
        assert len(_visible(img)) > 0


def test_animal_features_stay_fixed_across_a_set():
    """세트 통일감 — 표정이 바뀌어도 종·귀·코는 그대로여야 한다."""
    char = sketchgen.make_character(4, animal="hamster")
    assert char.cheeks and char.teeth and char.whiskers
    for keyword in ("기쁨", "화남", "졸림"):
        # CharacterSpec은 frozen이라 렌더링이 정체성을 바꿀 수 없다
        sketchgen.render_character(keyword, size=120, seed=1, character=char)
    assert char == sketchgen.make_character(4, animal="hamster")


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


# --------------------------------------------------------------------------
# 움직이는 이모티콘 (움짤)
# --------------------------------------------------------------------------

def test_zero_motion_matches_a_static_render():
    """모션 0이면 정지 렌더와 완전히 같아야 한다.

    이게 깨지면 모션 코드가 난수 소비 순서를 건드리고 있다는 뜻이고,
    그러면 프레임마다 선이 새로 그려져 화면이 지글거린다.
    """
    char = sketchgen.make_character(4, animal="bear")
    static = sketchgen.render_character("기쁨", size=150, seed=5, character=char)
    zeroed = sketchgen.render_character("기쁨", size=150, seed=5, character=char,
                                        motion=sketchgen.Motion())
    assert np.array_equal(np.array(static), np.array(zeroed))


def test_render_animation_frame_count_and_size():
    frames = sketchgen.render_animation("기쁨", size=120, seed=1, frames=6)
    assert len(frames) == 6
    assert all(f.size == (120, 120) for f in frames)
    assert all(f.mode == "RGBA" for f in frames)


def test_animation_frames_actually_move():
    frames = sketchgen.render_animation("기쁨", size=120, seed=1, frames=6, kind="bounce")
    first = np.array(frames[0])
    assert any(not np.array_equal(first, np.array(f)) for f in frames[1:])


@pytest.mark.parametrize("kind", list(sketchgen.MOTION_PRESETS))
def test_every_motion_preset_renders(kind):
    frames = sketchgen.render_animation("기쁨", size=100, seed=2, frames=4, kind=kind)
    assert len(frames) == 4


def test_render_animation_rejects_bad_input():
    with pytest.raises(ValueError):
        sketchgen.render_animation("기쁨", kind="does_not_exist")
    with pytest.raises(ValueError):
        sketchgen.render_animation("기쁨", frames=1)


def test_animation_gif_keeps_transparent_background(tmp_path):
    """이모티콘은 투명 배경이 필수라 GIF 저장에서 알파가 날아가면 안 된다."""
    from kakao_emoticon_gen import postprocess
    from PIL import Image

    frames = sketchgen.render_animation("기쁨", size=120, seed=3, frames=4)
    out = postprocess.frames_to_gif(frames, tmp_path / "a.gif")

    with Image.open(out) as gif:
        assert gif.n_frames == 4
        assert "transparency" in gif.info
        assert gif.convert("RGBA").getpixel((2, 2))[3] == 0
