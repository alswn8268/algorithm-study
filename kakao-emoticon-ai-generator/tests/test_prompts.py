import pytest

from kakao_emoticon_gen import prompts


def test_build_prompt_includes_style_and_keyword():
    result = prompts.build_prompt("기쁨")
    assert "기쁨" in result.prompt
    assert "kakao emoticon sticker style" in result.prompt
    assert "original character design" in result.prompt
    assert result.negative_prompt == prompts.NEGATIVE_PROMPT_BASE


def test_build_prompt_unknown_style_raises():
    with pytest.raises(ValueError):
        prompts.build_prompt("기쁨", style="not_a_real_style")


def test_build_prompt_empty_keyword_raises():
    with pytest.raises(ValueError):
        prompts.build_prompt("   ")


def test_recommended_emotion_set_nonempty():
    assert len(prompts.RECOMMENDED_EMOTION_SET) > 0
    assert all(isinstance(k, str) and k for k in prompts.RECOMMENDED_EMOTION_SET)
