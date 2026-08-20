"""감정/키워드 텍스트 → 카카오 이모티콘 스타일 이미지 생성 프롬프트.

카카오는 제출 필수 감정 목록을 공개적으로 고정해두지 않는다. 아래
`RECOMMENDED_EMOTION_SET`은 멈춰있는 이모티콘 제안 기준인 32컷에 맞춰
정리한 예시 세트일 뿐, 공식 요구사항이 아니다. 실제 제출 전에는
카카오 이모티콘 스튜디오의 최신 안내를 확인해야 한다.

한글 텍스트는 어떤 프리셋에서도 AI에게 그리게 하지 않는다. 이미지 생성
모델은 한글 자소를 거의 항상 깨뜨리므로, 문구는 그림을 뽑은 뒤 별도
편집 도구에서 손글씨로 얹는 것을 전제로 한다 (docs/STYLE_GUIDE.md 참고).
"""
from __future__ import annotations

from dataclasses import dataclass

# --- 스타일 프리셋 ---------------------------------------------------------

STYLE_PRESETS: dict[str, str] = {
    # 볼펜 발그림 (기본값) — "대충 그린 정제되지 않은 낙서" 화풍.
    # 눈은 검정 점눈만, 선은 얇고 떨리는 볼펜 선, 좌우 비대칭, 채색은
    # 선 밖으로 삐져나가게. 자세한 고정 규칙은 docs/STYLE_GUIDE.md 참고.
    "pen_doodle": (
        "a crude careless doodle scribbled in about thirty seconds, "
        "thin shaky ballpoint pen lines, wobbly trembling strokes drawn with an unsteady hand, "
        "each line gone over two or three times with the stray overlapping strokes left in, "
        "line ends that do not quite meet and leave small gaps at the corners, "
        "plain round solid black dot eyes deliberately mismatched in size and set at "
        "slightly different heights, "
        "lopsided asymmetric wonky proportions, squashed uneven head, limbs of unequal length, "
        "flat crayon-scribble coloring that spills messily outside the outlines "
        "and leaves patchy white gaps unfilled inside, "
        "single character, centered, plain white paper background, "
        "amateur sketchbook doodle, intentionally unpolished and badly drawn"
    ),
    # 텍스트형 — 문구 자리만 비워두고 그림만 생성한다. 한글은 후처리에서 얹는다.
    "text_based": (
        "a crude careless doodle scribbled in about thirty seconds, "
        "thin shaky ballpoint pen lines, wobbly trembling strokes, "
        "plain round solid black dot eyes mismatched in size, "
        "lopsided asymmetric proportions, "
        "flat scribbled coloring spilling outside the outlines, "
        "character placed in the upper portion with generous empty blank space left "
        "at the bottom of the frame, completely wordless with no writing anywhere, "
        "single character, plain white paper background, amateur sketchbook doodle"
    ),
    # 움직이는 GIF형 (단일 프레임 생성용 — 여러 프레임을 seed만 바꿔 생성 후
    # postprocess.frames_to_gif로 조합)
    "animated_frame": (
        "a crude careless doodle scribbled in about thirty seconds, "
        "character caught mid-motion in an exaggerated flailing pose, "
        "thin shaky ballpoint pen lines, wobbly trembling strokes, "
        "plain round solid black dot eyes mismatched in size, "
        "lopsided asymmetric wonky proportions, "
        "flat scribbled coloring spilling outside the outlines, "
        "single animation frame, single character, plain white paper background, "
        "amateur sketchbook doodle, intentionally unpolished"
    ),
    # 깔끔한 캐릭터형 — 발그림 화풍을 쓰지 않을 때를 위한 대안 프리셋.
    "cute_character": (
        "cute chibi character, kakao emoticon sticker style, thick bold black outline, "
        "flat pastel colors, minimal simple shading, big expressive eyes, "
        "centered composition, single character, plain white background, "
        "digital illustration, sticker art"
    ),
}

DEFAULT_STYLE = "pen_doodle"

# 모든 스타일에 공통으로 붙는 네거티브 프롬프트.
# 한글/문자 관련 항목은 "텍스트는 AI에 맡기지 않는다"는 원칙을 강제한다.
NEGATIVE_PROMPT_BASE = (
    "photorealistic, realistic, 3d render, watermark, signature, "
    "text, letters, words, korean text, hangul, caption, speech bubble text, "
    "extra limbs, extra fingers, deformed hands, low quality, blurry, jpeg artifacts, "
    "logo, brand mark, existing copyrighted character, complex background, cluttered background"
)

# 스타일별 추가 네거티브. 발그림 계열은 AI가 기본적으로 "잘 그리려는" 경향을
# 억누르는 것이 핵심이라, 정제된 결과물을 유도하는 단어를 광범위하게 배제한다.
_SLOPPY_NEGATIVE = (
    "eye highlights, sparkling eyes, eyelashes, crescent eyes, glossy eyes, "
    "gradient, shading, soft shading, cel shading, ambient occlusion, "
    "symmetrical, perfectly symmetrical, clean lineart, smooth lines, uniform line weight, "
    "vector art, crisp edges, anti-aliased, polished, refined, highly detailed, "
    "professional illustration, masterpiece, well drawn, neat coloring, "
    "coloring that stays inside the lines"
)

STYLE_NEGATIVES: dict[str, str] = {
    "pen_doodle": _SLOPPY_NEGATIVE,
    "text_based": _SLOPPY_NEGATIVE,
    "animated_frame": _SLOPPY_NEGATIVE,
}

ORIGINALITY_CLAUSE = (
    "original character design, not based on any existing copyrighted character, "
    "mascot, or brand"
)

# --- 감정/문구 예시 세트 (참고용, 공식 요구사항 아님) -----------------------
#
# 멈춰있는 이모티콘 제안 기준인 32컷에 맞춘 세트. 모두 "텍스트 없이 봐도
# 뜻이 통하는지"(논버벌 테스트)를 통과하도록 몸짓으로 표현 가능한 것만 골랐다.
RECOMMENDED_EMOTION_SET: list[str] = [
    "안녕", "반가워", "기쁨", "슬픔", "화남", "놀람", "사랑해", "고마워",
    "미안해", "축하해", "화이팅", "웃김", "심심함", "졸림", "배고픔", "당황",
    "부끄러움", "자신감", "실망", "긴장", "감동", "궁금함", "지침", "설렘",
    "만족", "거절", "수긍", "눈치보기", "신남", "멍때림", "삐짐", "잘자",
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

    negative_parts = [NEGATIVE_PROMPT_BASE]
    style_negative = STYLE_NEGATIVES.get(style)
    if style_negative:
        negative_parts.append(style_negative)

    return PromptResult(
        keyword=keyword.strip(),
        style=style,
        prompt=", ".join(parts),
        negative_prompt=", ".join(negative_parts),
    )
