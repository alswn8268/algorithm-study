"""감정/키워드 텍스트 → 카카오 이모티콘 스타일 이미지 생성 프롬프트.

카카오는 제출 필수 감정 목록을 공개적으로 고정해두지 않는다. 아래
`RECOMMENDED_EMOTION_SET`은 국내 인기 이모티콘에서 흔히 쓰이는 감정/문구를
참고용으로 정리한 예시 세트일 뿐, 공식 요구사항이 아니다. 실제 제출 전에는
카카오 이모티콘 스튜디오의 최신 안내를 확인해야 한다.
"""
from __future__ import annotations

from dataclasses import dataclass

# --- 스타일 프리셋 ---------------------------------------------------------

STYLE_PRESETS: dict[str, str] = {
    # 귀여운 캐릭터형 (기본값)
    "cute_character": (
        "cute chibi character, kakao emoticon sticker style, thick bold black outline, "
        "flat pastel colors, minimal simple shading, big expressive eyes, "
        "centered composition, single character, plain white background, "
        "digital illustration, sticker art"
    ),
    # 텍스트형 (짧은 문구가 함께 들어가는 스타일 — 실제 한글 렌더링은 AI가
    # 부정확한 경우가 많아, 문구는 후처리 단계에서 별도로 합성하는 것을 권장)
    "text_based": (
        "simple flat character illustration with empty speech bubble space, "
        "kakao emoticon sticker style, bold outline, flat colors, "
        "leaves room at the bottom for korean text caption, plain white background"
    ),
    # 움직이는 GIF형 (단일 프레임 생성용 — 여러 프레임을 seed만 바꿔 생성 후
    # postprocess.frames_to_gif로 조합)
    "animated_frame": (
        "cute chibi character mid-motion pose, kakao emoticon sticker style, "
        "thick bold outline, flat pastel colors, dynamic pose, "
        "single animation frame, plain white background, digital illustration"
    ),
}

DEFAULT_STYLE = "cute_character"

NEGATIVE_PROMPT_BASE = (
    "photorealistic, realistic, 3d render, watermark, signature, text artifacts, "
    "extra limbs, extra fingers, deformed hands, low quality, blurry, jpeg artifacts, "
    "logo, brand mark, existing copyrighted character, complex background, cluttered background"
)

ORIGINALITY_CLAUSE = (
    "original character design, not based on any existing copyrighted character, "
    "mascot, or brand"
)

# --- 감정/문구 예시 세트 (참고용, 공식 요구사항 아님) -----------------------

RECOMMENDED_EMOTION_SET: list[str] = [
    "안녕", "기쁨", "슬픔", "화남", "놀람", "사랑해", "고마워", "미안해",
    "축하해", "화이팅", "웃김", "심심함", "졸림", "배고픔", "당황",
    "부끄러움", "자신감", "실망", "긴장", "감동", "궁금함", "지침",
    "설렘", "만족",
]


@dataclass
class PromptResult:
    keyword: str
    style: str
    prompt: str
    negative_prompt: str


def build_prompt(keyword: str, style: str = DEFAULT_STYLE, extra: str | None = None) -> PromptResult:
    """감정 키워드를 카카오 이모티콘 스타일 프롬프트로 변환한다."""
    if not keyword or not keyword.strip():
        raise ValueError("keyword must be a non-empty string")

    style_desc = STYLE_PRESETS.get(style)
    if style_desc is None:
        known = ", ".join(STYLE_PRESETS)
        raise ValueError(f"unknown style '{style}'. known styles: {known}")

    parts = [
        f'a character expressing "{keyword.strip()}" emotion',
        style_desc,
        ORIGINALITY_CLAUSE,
    ]
    if extra:
        parts.append(extra.strip())

    prompt = ", ".join(parts)
    return PromptResult(
        keyword=keyword.strip(),
        style=style,
        prompt=prompt,
        negative_prompt=NEGATIVE_PROMPT_BASE,
    )
