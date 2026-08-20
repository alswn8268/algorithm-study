import pytest

from kakao_emoticon_gen import prompts


def test_build_prompt_includes_style_and_keyword():
    result = prompts.build_prompt("기쁨")
    assert "기쁨" in result.prompt
    assert "shaky ballpoint pen lines" in result.prompt
    assert "original character design" in result.prompt
    assert prompts.NEGATIVE_PROMPT_BASE in result.negative_prompt


def test_default_style_is_pen_doodle():
    assert prompts.DEFAULT_STYLE == "pen_doodle"


def test_pen_doodle_encodes_the_four_fixed_rules():
    prompt = prompts.STYLE_PRESETS["pen_doodle"]
    # 눈: 검정 점눈 + 짝눈
    assert "black dot eyes" in prompt
    assert "mismatched in size" in prompt
    # 선: 얇고 떨리는 볼펜 선 + 겹쳐 그은 흔적
    assert "thin shaky ballpoint pen lines" in prompt
    assert "overlapping strokes" in prompt
    # 비율: 좌우 비대칭
    assert "asymmetric" in prompt
    # 채색: 선 밖으로 삐져나감
    assert "spills messily outside the outlines" in prompt


def test_sloppy_styles_suppress_polished_output():
    negative = prompts.build_prompt("기쁨", style="pen_doodle").negative_prompt
    for banned in ("eye highlights", "eyelashes", "gradient", "shading",
                   "symmetrical", "clean lineart", "uniform line weight"):
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
