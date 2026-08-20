import pytest

from kakao_emoticon_gen import copyright_guard


def test_clean_prompt_not_blocked():
    result = copyright_guard.check_prompt("a cute original bear character expressing joy")
    assert not result.is_blocked
    assert result.blocked_terms == []


@pytest.mark.parametrize("term", ["Pikachu", "피카츄", "hello kitty", "짱구"])
def test_blocked_terms_detected(term):
    result = copyright_guard.check_prompt(f"a character that looks like {term}")
    assert result.is_blocked
    assert term.lower() in [t.lower() for t in result.blocked_terms]


def test_enforce_raises_on_blocked_prompt():
    with pytest.raises(ValueError):
        copyright_guard.enforce("draw pikachu as a kakao emoticon")


def test_enforce_returns_prompt_when_clean():
    prompt = "a cute original fox character"
    assert copyright_guard.enforce(prompt) == prompt
