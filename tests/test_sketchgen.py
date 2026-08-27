from dataclasses import replace

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
        assert archetype["ear"] in sketchgen.EAR_KINDS, animal
        assert archetype["nose"] in sketchgen.NOSE_KINDS, animal


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


# --------------------------------------------------------------------------
# 형태 — 머리/몸통 구조, 부품 명암, 가려짐
# --------------------------------------------------------------------------

def _tone_count(img: Image.Image) -> int:
    """보이는 픽셀의 색 종류 수 (알파 있는 부분만)."""
    arr = np.array(img.convert("RGBA"))
    body = arr[arr[:, :, 3] > 200][:, :3]
    return len(np.unique(body, axis=0))


def test_parts_get_their_own_shade():
    """귀·팔다리가 몸통과 구분되려면 몸 색 말고 다른 톤이 있어야 한다."""
    char = sketchgen.make_character(3, animal="bear")
    img = sketchgen.render_character("안녕", size=300, seed=1, character=char)

    arr = np.array(img.convert("RGBA"))
    visible = arr[arr[:, :, 3] > 200][:, :3]
    values, counts = np.unique(visible, axis=0, return_counts=True)

    body_tone = values[counts.argmax()]
    body_lum = float(body_tone @ np.array([0.2126, 0.7152, 0.0722]))
    lums = values @ np.array([0.2126, 0.7152, 0.0722])

    # 몸통보다 어둡되 잉크(거의 검정)는 아닌 중간 톤이 실제로 존재해야 한다
    mid = counts[(lums < body_lum - 5) & (lums > 90)].sum()
    assert mid > visible.shape[0] * 0.02, "부품 명암이 보이지 않는다"


@pytest.mark.parametrize("animal", ["bear", "cat", "dog", "rabbit"])
def test_head_and_body_are_separated_by_a_waist(animal):
    """머리와 몸통이 나뉘어야 동물로 읽힌다.

    통짜 원 하나면 폭이 위에서 아래로 단조롭게 줄어든다. 머리와 몸통이
    겹친 구조라면 그 사이에 잘록한 지점(목)이 생긴다.
    """
    char = sketchgen.make_character(3, animal=animal)
    img = sketchgen.render_character("안녕", size=300, seed=1, character=char)
    alpha = np.array(img.convert("RGBA"))[:, :, 3] > 128

    rows = np.where(alpha.any(axis=1))[0]
    top, height = rows.min(), rows.max() - rows.min()
    widths = np.array([alpha[top + height * pct // 100].sum() for pct in range(10, 90)])

    head_max = widths[:35].max()      # 머리
    waist = widths[30:55].min()       # 목 언저리
    body_max = widths[45:].max()      # 몸통(+팔)

    assert waist < head_max * 0.95, f"{animal}: 머리와 몸통이 안 나뉜다"
    assert waist < body_max * 0.95, f"{animal}: 머리와 몸통이 안 나뉜다"


def test_shape_is_not_wildly_distorted():
    """왜곡을 줄였으므로 실루엣이 대체로 둥글어야 한다 (가로세로비가 극단이 아님)."""
    for animal in ("bear", "cat", "dog"):
        char = sketchgen.make_character(3, animal=animal)
        img = sketchgen.render_character("안녕", size=300, seed=2, character=char)
        alpha = np.array(img.convert("RGBA"))[:, :, 3] > 128
        rows = np.where(alpha.any(axis=1))[0]
        cols = np.where(alpha.any(axis=0))[0]
        h = rows.max() - rows.min()
        w = cols.max() - cols.min()
        assert 0.45 < w / h < 2.2, f"{animal}: 실루엣이 지나치게 일그러졌다 ({w}x{h})"


# --------------------------------------------------------------------------
# 그림체 (DrawStyle) — 캐릭터와 직교하는 축
# --------------------------------------------------------------------------

def _dominant_body_tone(img: Image.Image):
    arr = np.array(img.convert("RGBA"))
    body = arr[arr[:, :, 3] > 200][:, :3]
    values, counts = np.unique(body, axis=0, return_counts=True)
    return tuple(values[counts.argmax()])


@pytest.mark.parametrize("style", sketchgen.DRAW_STYLE_NAMES)
def test_every_draw_style_renders(style):
    char = sketchgen.make_character(2, animal="guineapig")
    img = sketchgen.render_character("안녕", size=160, seed=3, character=char, draw_style=style)
    assert img.size == (160, 160)
    assert len(_visible(img)) > 0


def test_draw_styles_actually_look_different():
    """그림체를 바꿨는데 결과가 같다면 축이 연결되지 않은 것이다."""
    char = sketchgen.make_character(2, animal="guineapig")
    renders = {
        style: np.array(sketchgen.render_character(
            "안녕", size=160, seed=3, character=char, draw_style=style))
        for style in sketchgen.DRAW_STYLE_NAMES
    }
    for a, b in zip(sketchgen.DRAW_STYLE_NAMES, sketchgen.DRAW_STYLE_NAMES[1:]):
        assert not np.array_equal(renders[a], renders[b]), f"{a} == {b}"


def test_chunky_draws_a_heavier_outline_than_doodle():
    char = sketchgen.make_character(2, animal="bear")

    def ink_pixels(style):
        arr = np.array(sketchgen.render_character(
            "안녕", size=200, seed=4, character=char, draw_style=style).convert("RGBA"))
        visible = arr[arr[:, :, 3] > 200][:, :3]
        lum = visible @ np.array([0.2126, 0.7152, 0.0722])
        return int((lum < 90).sum())

    assert ink_pixels("chunky") > ink_pixels("doodle") * 1.3


def test_mono_style_drains_the_body_colour():
    char = sketchgen.make_character(2, animal="guineapig", color=(255, 176, 186, 255))
    coloured = _dominant_body_tone(
        sketchgen.render_character("안녕", size=180, seed=4, character=char, draw_style="doodle"))
    mono = _dominant_body_tone(
        sketchgen.render_character("안녕", size=180, seed=4, character=char, draw_style="mono"))
    # 원본은 분홍, mono는 거의 무채색이어야 한다
    assert max(coloured) - min(coloured) > 30
    assert max(mono) - min(mono) < 20


def test_sticker_style_adds_a_white_border():
    char = sketchgen.make_character(2, animal="guineapig", color=(168, 216, 255, 255))
    plain = sketchgen.render_character("안녕", size=200, seed=4, character=char, draw_style="doodle")
    sticker = sketchgen.render_character("안녕", size=200, seed=4, character=char, draw_style="sticker")

    def near_white(img):
        arr = np.array(img.convert("RGBA"))
        vis = arr[arr[:, :, 3] > 200][:, :3]
        return int((vis.min(axis=1) > 245).sum())

    # 실루엣을 부풀린 흰 테두리가 붙으므로 흰 픽셀이 확실히 늘어난다
    assert near_white(sticker) > near_white(plain) + 500


def test_unknown_draw_style_is_rejected():
    with pytest.raises(KeyError):
        sketchgen.render_character("안녕", size=100, draw_style="does_not_exist")


def test_style_sheet_grid_shape():
    char = sketchgen.make_character(2, animal="guineapig")
    sheet, used = sketchgen.render_style_sheet(char, ["안녕", "기쁨"], cell=80, seed=1)
    assert used == sketchgen.DRAW_STYLE_NAMES
    assert sheet.size == (80 * 2, 80 * len(used))


def test_style_sheet_rejects_bad_input():
    char = sketchgen.make_character(2, animal="guineapig")
    with pytest.raises(ValueError):
        sketchgen.render_style_sheet(char, [], cell=80)
    with pytest.raises(ValueError):
        sketchgen.render_style_sheet(char, ["안녕"], cell=80, styles=["nope"])


# --------------------------------------------------------------------------
# 기니피그
# --------------------------------------------------------------------------

def test_guineapig_archetype_features():
    char = sketchgen.make_character(2, animal="guineapig")
    assert char.ear == "petal"          # 머리 옆에 낮게 붙은 꽃잎 귀
    assert char.tail == "none"          # 꼬리가 없다
    assert char.neckless and char.patch # 목이 없는 체형 + 털 얼룩
    assert char.teeth and char.whiskers


def test_guineapig_is_wider_than_tall():
    """기니피그는 낮고 넓은 체형이라 가로가 세로보다 길어야 한다."""
    char = sketchgen.make_character(2, animal="guineapig")
    img = sketchgen.render_character("안녕", size=300, seed=4, character=char)
    alpha = np.array(img.convert("RGBA"))[:, :, 3] > 128
    rows = np.where(alpha.any(axis=1))[0]
    cols = np.where(alpha.any(axis=0))[0]
    assert (cols.max() - cols.min()) > (rows.max() - rows.min())


# --------------------------------------------------------------------------
# 떡냥이 — 얼굴 고정, 몸이 연기하는 캐릭터
# --------------------------------------------------------------------------

def _silhouette_box(img):
    alpha = np.array(img.convert("RGBA"))[:, :, 3] > 128
    rows = np.where(alpha.any(axis=1))[0]
    cols = np.where(alpha.any(axis=0))[0]
    return cols.max() - cols.min(), rows.max() - rows.min()


def test_body_is_solid_not_hollow():
    """업로드된 시안의 실제 버그: 흰 몸이 흰 배경과 같은 색이라 배경 제거 시
    몸통까지 지워져 다크모드에서 속이 뚫려 보였다.

    이 렌더러는 투명 캔버스에 직접 그리므로 배경 제거 단계 자체가 없다.
    몸 한가운데가 불투명한지 못박아 회귀를 막는다.
    """
    img = sketchgen.render_character("안녕", size=300, seed=5,
                                     character=sketchgen.TTEOKNYANGI, draw_style="mochi")
    arr = np.array(img.convert("RGBA"))
    assert arr[2, 2, 3] == 0, "배경은 투명해야 한다"

    alpha = arr[:, :, 3] > 128
    rows = np.where(alpha.any(axis=1))[0]
    cols = np.where(alpha.any(axis=0))[0]
    cy = (rows.min() + rows.max()) // 2
    cx = (cols.min() + cols.max()) // 2
    assert arr[cy, cx, 3] > 250, "몸 한가운데가 비어 있다 (속 빈 윤곽)"

    # 실루엣 내부가 대부분 채워져 있어야 한다
    inner = alpha[rows.min():rows.max(), cols.min():cols.max()]
    assert inner.mean() > 0.55


def test_every_emotion_has_a_body_state():
    for keyword in prompts.RECOMMENDED_EMOTION_SET:
        assert keyword in sketchgen.EMOTION_BODY, keyword
        assert sketchgen.EMOTION_BODY[keyword] in sketchgen.BODY_STATES, keyword


def test_body_states_change_the_silhouette():
    """얼굴이 고정이므로 실루엣이 감정을 전달해야 한다."""
    def box(keyword):
        return _silhouette_box(sketchgen.render_character(
            keyword, size=300, seed=7, character=sketchgen.TTEOKNYANGI, draw_style="mochi"))

    melt_w, melt_h = box("졸림")     # 녹아내림 — 넓고 납작
    stretch_w, stretch_h = box("놀람")  # 늘어남 — 좁고 길쭉
    assert melt_w / melt_h > stretch_w / stretch_h * 1.3


def test_fixed_face_ignores_the_emotion_face():
    """놀람은 원래 광기 눈인데, 표정 고정 캐릭터는 점눈을 유지해야 한다."""
    fixed = sketchgen.TTEOKNYANGI
    loose = replace(fixed, fixed_face=False)
    a = sketchgen.render_character("놀람", size=220, seed=3, character=fixed, draw_style="mochi")
    b = sketchgen.render_character("놀람", size=220, seed=3, character=loose, draw_style="mochi")
    assert not np.array_equal(np.array(a), np.array(b))

    # 광기 눈은 큰 흰자를 만든다 — 고정 얼굴에는 그 흰 덩어리가 없어야 한다
    def sclera_pixels(img):
        arr = np.array(img.convert("RGBA"))
        top = arr[: arr.shape[0] // 2]
        vis = top[top[:, :, 3] > 200][:, :3]
        return int((vis.min(axis=1) > 250).sum())

    assert sclera_pixels(a) < sclera_pixels(b)


def test_cracks_only_appear_in_the_hardened_state():
    def ink(keyword):
        arr = np.array(sketchgen.render_character(
            keyword, size=260, seed=4, character=sketchgen.TTEOKNYANGI,
            draw_style="mochi").convert("RGBA"))
        vis = arr[arr[:, :, 3] > 200][:, :3]
        return int((vis @ np.array([0.2126, 0.7152, 0.0722]) < 110).sum())

    assert sketchgen.BODY_STATES[sketchgen.EMOTION_BODY["삐짐"]].cracks > 0
    assert sketchgen.BODY_STATES[sketchgen.EMOTION_BODY["안녕"]].cracks == 0
    assert ink("삐짐") > ink("안녕")


def test_paw_pads_are_drawn_in_pink():
    img = sketchgen.render_character("안녕", size=300, seed=5,
                                     character=sketchgen.TTEOKNYANGI, draw_style="mochi")
    arr = np.array(img.convert("RGBA"))
    vis = arr[arr[:, :, 3] > 200][:, :3].astype(int)
    pink = (vis[:, 0] > 230) & (vis[:, 1] < 215) & (vis[:, 2] < 220) & (vis[:, 1] > 150)
    assert pink.sum() > 100, "볼터치·젤리 발바닥의 분홍이 보이지 않는다"


def test_one_piece_body_has_no_waist():
    """떡냥이는 1등신 한 덩어리라 머리/몸통 사이 잘록함이 없어야 한다."""
    img = sketchgen.render_character("안녕", size=300, seed=5,
                                     character=sketchgen.TTEOKNYANGI, draw_style="mochi")
    alpha = np.array(img.convert("RGBA"))[:, :, 3] > 128
    rows = np.where(alpha.any(axis=1))[0]
    top, height = rows.min(), rows.max() - rows.min()
    widths = np.array([alpha[top + height * pct // 100].sum() for pct in range(15, 70)])
    # 가운데가 위아래보다 확 좁아지는 지점이 없어야 한다
    assert widths[15:40].min() > max(widths[:15].max(), widths[40:].max()) * 0.72


def test_named_character_pairs_spec_with_style():
    spec, style = sketchgen.NAMED_CHARACTERS["tteoknyangi"]
    assert spec is sketchgen.TTEOKNYANGI
    assert style == "mochi"
    assert spec.fixed_face and spec.one_piece and spec.paw_pads
