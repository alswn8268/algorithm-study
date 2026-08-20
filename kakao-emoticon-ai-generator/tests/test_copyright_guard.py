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


@pytest.mark.parametrize("name", ["내쓰만", "가나디", "이걸누가사", "어쩔꽁쥐", "꽁쥐"])
def test_style_reference_artist_names_are_blocked(name):
    """화풍 참고 대상의 이름이 프롬프트로 새어나가면 실루엣까지 따라가 탈락 사유가 된다."""
    result = copyright_guard.check_prompt(f"draw in the style of {name}")
    assert result.is_blocked


def test_short_korean_words_do_not_false_positive():
    """2글자 이하 이름을 블록리스트에 넣지 않기로 한 결정을 고정한다."""
    result = copyright_guard.check_prompt("그모습 그대로 귀여운 오리지널 캐릭터")
    assert not result.is_blocked


def test_enforce_raises_on_blocked_prompt():
    with pytest.raises(ValueError):
        copyright_guard.enforce("draw pikachu as a kakao emoticon")


def test_enforce_returns_prompt_when_clean():
    prompt = "a cute original fox character"
    assert copyright_guard.enforce(prompt) == prompt
