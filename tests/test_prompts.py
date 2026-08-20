import pytest

from kakao_emoticon_gen import prompts


def test_build_prompt_includes_style_and_keyword():
    result = prompts.build_prompt("기쁨")
    assert "기쁨" in result.prompt
    assert "shaky ballpoint pen line" in result.prompt
    assert "original character design" in result.prompt
    assert prompts.NEGATIVE_PROMPT_BASE in result.negative_prompt


def test_default_style_is_pen_doodle():
    assert prompts.DEFAULT_STYLE == "pen_doodle"


def test_pen_doodle_encodes_the_fixed_rules():
    """STYLE_GUIDE의 고정 규칙이 프롬프트에 실제로 들어있는지 잠근다."""
    prompt = prompts.STYLE_PRESETS["pen_doodle"]
    # 눈: 아주 작게, 위쪽에 좁게
    assert "tiny solid black dot eyes" in prompt
    assert "high on the face" in prompt
    # 중안부: 눈과 입 사이를 멀리
    assert "long midface" in prompt
    # 선: 하나로 이어진 실루엣
    assert "single continuous contour" in prompt
    # 비율: 좌우 비대칭
    assert "asymmetric" in prompt
    # 채색: 깔끔한 평면
    assert "clean flat" in prompt


def test_sloppy_styles_suppress_polished_output():
    negative = prompts.build_prompt("기쁨", style="pen_doodle").negative_prompt
    for banned in ("big eyes", "eye highlights", "eyelashes", "gradient", "shading",
                   "symmetrical", "short midface", "separate outlines around each body part"):
        assert banned in negative


@pytest.mark.parametrize("style", list(prompts.STYLE_PRESETS))
def test_no_style_asks_the_ai_to_render_korean_text(style):
    result = prompts.build_prompt("기쁨", style=style)
    for banned in ("korean text", "hangul", "letters"):
        assert banned in result.negative_prompt
    # 프리셋 서술 자체도 한글을 그리라고 요구하면 안 된다.
    assert "korean text caption" not in result.prompt


def test_build_prompt_unknown_style_raises():
    with pytest.raises(ValueError):
        prompts.build_prompt("기쁨", style="not_a_real_style")


def test_build_prompt_empty_keyword_raises():
    with pytest.raises(ValueError):
        prompts.build_prompt("   ")


def test_recommended_emotion_set_has_32_unique_cuts():
    emotions = prompts.RECOMMENDED_EMOTION_SET
    assert len(emotions) == 32
    assert len(set(emotions)) == 32
    assert all(isinstance(k, str) and k for k in emotions)
