"""저작권/브랜드 침해 위험을 줄이기 위한 프롬프트 필터.

이 모듈은 "완벽한 저작권 검사기"가 아니다. 생성 전 프롬프트에 명백히
위험한 고유명사가 들어있는지 차단하는 최소한의 안전장치이며, 생성된
이미지가 실제로 기존 캐릭터와 유사한지는 사람이 검수해야 한다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

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
