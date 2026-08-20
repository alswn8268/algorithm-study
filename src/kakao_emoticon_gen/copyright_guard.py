"""저작권/브랜드 침해 위험을 줄이기 위한 프롬프트 필터.

이 모듈은 "완벽한 저작권 검사기"가 아니다. 생성 전 프롬프트에 명백히
위험한 고유명사가 들어있는지 차단하는 최소한의 안전장치이며, 생성된
이미지가 실제로 기존 캐릭터와 유사한지는 사람이 검수해야 한다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# 화풍 참고 대상으로만 언급하고 프롬프트에는 절대 넣으면 안 되는 이름들.
# 특정 작가/캐릭터의 이름을 프롬프트에 넣으면 결과물이 그 실루엣을 그대로
# 따라가 심사 탈락 사유가 된다. 화풍의 문법(선·눈·비율·채색)은 STYLE_PRESETS의
# 서술로만 재현하고, 고유명사는 여기서 차단한다.
STYLE_REFERENCE_BLOCKLIST: list[str] = [
    # 화풍 참고
    "내쓰만",
    "가나디", "듀 가나디", "듀가나디",
    "이걸누가사",
    "어쩔꽁쥐", "꽁쥐",
    # 동물형 캐릭터 참고 — 구조 문법(귀·코·볼)만 가져오고 이름은 막는다
    "망곰이", "햄깅이",
    "망그러진곰", "망그러진 곰",
    "오버액션토끼", "토심이", "토뭉이",
    "곰돌찡", "단답쿼카", "어쩔티콘",
]
# 참고: "그모", "곰", "토끼"처럼 짧거나 일반적인 단어는 여기에 넣지 않는다.
# 비ASCII 항목은 단어 경계 없이 부분 문자열로 매칭하므로 "그모습"이나
# "곰 캐릭터" 같은 정상적인 표현까지 오탐으로 걸러내기 때문이다.
# 동물 종류(곰/햄스터/토끼)는 누구나 쓸 수 있는 소재이며, 보호 대상은
# 특정 캐릭터의 이름과 실루엣이다.

# 예시 블록리스트. 실제 운영 시 회사/프로젝트 정책에 맞게 확장하세요.
BLOCKLIST: list[str] = [
    "mickey mouse", "미키마우스",
    "pikachu", "피카츄",
    "hello kitty", "헬로키티",
    "pokemon", "포켓몬",
    "disney", "디즈니",
    "marvel", "마블",
    "kakao friends", "카카오프렌즈",
    "line friends", "라인프렌즈",
    "pooh", "곰돌이 푸",
    "doraemon", "도라에몽",
    "sanrio", "산리오",
    "짱구",
    "뽀로로", "pororo",
    *STYLE_REFERENCE_BLOCKLIST,
]


@dataclass
class GuardResult:
    original_prompt: str
    sanitized_prompt: str
    blocked_terms: list[str] = field(default_factory=list)

    @property
    def is_blocked(self) -> bool:
        return len(self.blocked_terms) > 0


def _find_blocked_terms(text: str) -> list[str]:
    lowered = text.lower()
    found = []
    for term in BLOCKLIST:
        pattern = r"\b" + re.escape(term.lower()) + r"\b" if term.isascii() else re.escape(term.lower())
        if re.search(pattern, lowered):
            found.append(term)
    return found


def check_prompt(prompt: str) -> GuardResult:
    """프롬프트에 금칙어(기존 캐릭터/브랜드명)가 있는지 검사한다.

    금칙어가 발견되면 `is_blocked=True`로 표시하고, 호출자는 생성을
    진행하지 말아야 한다 (pipeline.py가 이 규칙을 강제한다).
    """
    blocked = _find_blocked_terms(prompt)
    return GuardResult(original_prompt=prompt, sanitized_prompt=prompt, blocked_terms=blocked)


def enforce(prompt: str) -> str:
    """금칙어가 없으면 그대로 반환하고, 있으면 예외를 발생시킨다."""
    result = check_prompt(prompt)
    if result.is_blocked:
        raise ValueError(
            "prompt contains blocked term(s) that risk copyright infringement: "
            + ", ".join(result.blocked_terms)
        )
    return result.sanitized_prompt
