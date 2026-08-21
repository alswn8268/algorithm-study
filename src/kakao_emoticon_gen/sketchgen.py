"""볼펜 발그림 캐릭터를 절차적으로 그리는 렌더러 (AI 모델 불필요).

docs/STYLE_GUIDE.md의 고정 규칙을 그대로 코드로 옮긴 것이다. 규칙은
2025 트렌드("낙서형 흰둥이", 중안부가 길어지는 현상)에 맞춰 갱신됐다.

- 형태  : 큰 머리 + 작은 몸통이 겹친 구조. 통짜 원 하나면 감자에 혹이
          붙은 모양이 되고 동물로 안 읽힌다
- 눈    : 초롱초롱(sparkle)과 광기(manic) 두 계열. 하이라이트가 크고
          많을수록 귀엽고 흥분해 보인다 — 그게 이 표정의 작동 원리다
- 중안부: 눈과 입 사이를 일부러 멀리 벌린다 (현재 트렌드의 핵심 매력 포인트)
- 선    : 바깥 윤곽은 실루엣 하나로 이어 긋고, 귀·팔다리는 **안쪽 구분선과
          한 톤 낮춘 평면 명암**으로 나눈다. 몸에 가려지는 부분은 그리지
          않는다 (안 그러면 팔다리가 몸을 투과해 보인다)
- 비율  : 좌우를 살짝 다르게. 다만 과하게 일그러뜨리지 않는다
- 채색  : 깔끔한 평면 채색. 흰/크림색 몸이 주류다
- 색    : 이목구비는 새까맣게 찍지 않고 갈색 계열로 풀어준다. 하트·물방울
          같은 표현은 색을 넣어야 눈에 들어온다
- 팔다리: 직선 캡슐이 아니라 휜 뼈대(_ribbon)에 살을 붙인다. 직선이면
          막대기처럼 뻣뻣하다

**캐릭터 정체성(CharacterSpec)과 손떨림(seed)은 분리돼 있다.** 32컷 한 세트는
같은 CharacterSpec을 공유해야 "같은 캐릭터"가 되고, 컷마다 seed만 달라져서
"같은 사람이 그때그때 대충 그린" 흔들림이 생긴다.

용도는 두 가지다.
1) GPU/API 없이 파이프라인 전체를 실제 그림으로 검증
2) STYLE_GUIDE가 권하는 "트레이싱용 러프" — 이 출력을 밑그림 삼아
   아이패드에서 30초 안에 따라 그리면 가장 빠르고 확실하다
"""
from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass, field

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

# 완전한 검정보다 살짝 따뜻한 볼펜 잉크 색
INK = (38, 34, 30, 255)

# 이목구비는 윤곽선보다 살짝 풀어준 색을 쓴다. 전부 새까맣게 찍으면
# 얼굴만 무겁게 도드라진다.
EYE_INK = (46, 38, 36, 255)
MOUTH_INK = (98, 68, 62, 255)
BROW_INK = (86, 60, 55, 255)
NOSE_DARK = (84, 56, 50, 255)
NOSE_PINK = (232, 138, 148, 255)

# 하트·물방울 같은 표현은 색이 있어야 눈에 들어온다.
HEART_FILL = (255, 116, 140, 255)
HEART_LINE = (214, 62, 92, 255)
DROP_FILL = (162, 210, 244, 255)
DROP_LINE = (86, 152, 204, 255)
SPARKLE_COLOR = (255, 196, 84, 255)
BLUSH_COLOR = (245, 150, 158, 255)
ANGER_COLOR = (226, 84, 84, 255)

# 2025 트렌드는 "낙서형 흰둥이" — 흰/크림색 몸이 주류라 맨 앞에 둔다.
# 흰 몸은 다크모드에서도 형체가 또렷하다.
PALETTE: list[tuple[int, int, int, int]] = [
    (252, 249, 242, 255),   # 흰둥이 (기본)
    (247, 237, 222, 255),   # 크림
    (255, 208, 150, 255), (255, 176, 186, 255), (168, 216, 255, 255),
    (176, 234, 194, 255), (255, 238, 156, 255), (212, 190, 255, 255),
]

_SUPERSAMPLE = 2


# --------------------------------------------------------------------------
# 캐릭터 정체성 — 한 세트 안에서는 절대 바뀌면 안 되는 값들
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class CharacterSpec:
    """32컷 내내 고정되는 캐릭터의 생김새."""
    color: tuple[int, int, int, int]
    animal: str = "bear"
    rx_ratio: float = 0.27       # 몸통 가로 반지름
    ry_ratio: float = 0.27       # 몸통 세로 반지름
    bulge: float = 0.0           # 아래쪽이 불룩한 정도 (서양배 모양)
    eye_scale: float = 1.0
    eye_spread: float = 0.39     # 두 눈 사이 거리
    # --- 이목구비 ---
    ear: str = "round"           # round | tiny | long | pointy | floppy | none
    nose: str = "dot"            # dot | big | triangle | beak | none
    muzzle: bool = True          # 입 주변 밝은 영역 (주둥이)
    cheeks: bool = False         # 햄스터 볼주머니
    whiskers: bool = False
    teeth: bool = False          # 앞니
    tail: str = "none"           # stub | curl | none
    name: str = "character"


# 인기 이모티콘은 대부분 동물형이고, 종을 알아보게 하는 건 결국
# 귀 모양 · 코 · 주둥이 · 볼 · 수염 몇 가지의 조합이다.
# 특정 캐릭터를 베끼는 게 아니라 이 "구조 문법"만 가져온다.
ANIMAL_ARCHETYPES: dict[str, dict] = {
    "bear":    {"ear": "round",  "nose": "dot",      "muzzle": True,  "tail": "stub"},
    "hamster": {"ear": "tiny",   "nose": "dot",      "muzzle": True,  "cheeks": True,
                "whiskers": True, "teeth": True},
    "rabbit":  {"ear": "long",   "nose": "triangle", "muzzle": True,  "teeth": True, "tail": "stub"},
    "cat":     {"ear": "pointy", "nose": "triangle", "muzzle": False, "whiskers": True, "tail": "curl"},
    "dog":     {"ear": "floppy", "nose": "big",      "muzzle": True,  "tail": "curl"},
    "duck":    {"ear": "none",   "nose": "beak",     "muzzle": False},
    "seal":    {"ear": "none",   "nose": "dot",      "muzzle": True,  "whiskers": True},
}

ANIMALS = list(ANIMAL_ARCHETYPES)

# 종별로 어울리는 체형. 토끼는 갸름하고 물범은 옆으로 퍼진다.
_BODY_HINTS: dict[str, tuple[float, float]] = {
    "rabbit": (0.245, 0.290),
    "seal": (0.300, 0.240),
    "duck": (0.265, 0.275),
}


def make_character(
    seed: int, name: str | None = None, animal: str | None = None,
    color: tuple[int, int, int, int] | None = None,
) -> CharacterSpec:
    """seed 하나로 캐릭터 디자인을 결정론적으로 뽑는다.

    `animal`/`color`를 주면 그 부분만 고정하고 나머지는 seed로 정해진다.
    """
    rng = random.Random(seed)
    kind = animal or rng.choice(ANIMALS)
    archetype = ANIMAL_ARCHETYPES[kind]

    base_rx, base_ry = _BODY_HINTS.get(kind, (0.270, 0.270))
    picked_color = rng.choice(PALETTE)
    return CharacterSpec(
        color=color or picked_color,
        animal=kind,
        rx_ratio=base_rx * rng.uniform(0.94, 1.08),
        ry_ratio=base_ry * rng.uniform(0.94, 1.08),
        bulge=rng.choice([0.0, 0.12, 0.22]),
        eye_scale=rng.uniform(0.95, 1.35),
        eye_spread=rng.uniform(0.33, 0.44),
        ear=archetype["ear"],
        nose=archetype["nose"],
        muzzle=archetype.get("muzzle", False),
        cheeks=archetype.get("cheeks", False),
        whiskers=archetype.get("whiskers", False),
        teeth=archetype.get("teeth", False),
        tail=archetype.get("tail", "none"),
        name=name or f"{kind}{seed}",
    )


# --------------------------------------------------------------------------
# 저수준 펜 프리미티브
# --------------------------------------------------------------------------

def _periodic_noise(rng: random.Random, octaves: int = 3):
    """주기가 1인 부드러운 노이즈 함수 (닫힌 곡선용)."""
    waves = []
    for k in range(octaves):
        freq = rng.choice([2, 3, 4, 5]) * (k + 1)
        phase = rng.uniform(0, math.tau)
        waves.append((freq, phase, 1.0 / (k + 1)))
    total = sum(w[2] for w in waves)

    def noise(t: float) -> float:
        return sum(a * math.sin(f * math.tau * t + p) for f, p, a in waves) / total

    return noise


def wobbly_ellipse(
    cx: float, cy: float, rx: float, ry: float, rng: random.Random,
    steps: int = 96, wobble: float = 0.07, gap: float = 0.0,
    tilt: float = 0.0, bulge: float = 0.0,
) -> list[tuple[float, float]]:
    """찌그러진 타원 경로. `gap`만큼 끝을 안 닫아 선이 벌어지게 둔다."""
    radial = _periodic_noise(rng)
    angular = _periodic_noise(rng)
    start = rng.uniform(0.0, 1.0)
    span = 1.0 - gap

    cos_t, sin_t = math.cos(tilt), math.sin(tilt)
    points = []
    for i in range(steps + 1):
        t = (start + span * i / steps) % 1.0
        angle = t * math.tau + 0.04 * angular(t)
        r = 1.0 + wobble * radial(t)
        # 아래쪽만 불룩하게 (y축이 아래로 증가하므로 sin>0이 하반신)
        r *= 1.0 + bulge * max(0.0, math.sin(angle))
        x, y = rx * r * math.cos(angle), ry * r * math.sin(angle)
        points.append((cx + x * cos_t - y * sin_t, cy + x * sin_t + y * cos_t))
    return points


def _point_on(points: list[tuple[float, float]], cx: float, cy: float,
              angle_deg: float) -> tuple[float, float]:
    """경로 위에서 주어진 방향에 가장 가까운 점을 찾는다 (팔다리 부착점)."""
    target = math.radians(angle_deg)
    tx, ty = math.cos(target), math.sin(target)
    best, best_dot = points[0], -2.0
    for p in points:
        dx, dy = p[0] - cx, p[1] - cy
        n = math.hypot(dx, dy) or 1.0
        dot = (dx / n) * tx + (dy / n) * ty
        if dot > best_dot:
            best, best_dot = p, dot
    return best


def pen_stroke(
    draw: ImageDraw.ImageDraw, points: list[tuple[float, float]], rng: random.Random,
    width: int = 4, passes: int = 2, color=INK, drift: float = 2.0,
) -> None:
    """한 획을 두세 번 겹쳐 그어 손떨림 흔적을 남긴다."""
    if len(points) < 2:
        return
    for _ in range(passes):
        ox, oy = rng.uniform(-drift, drift), rng.uniform(-drift, drift)
        shaky = [
            (x + ox + rng.uniform(-1.0, 1.0), y + oy + rng.uniform(-1.0, 1.0))
            for x, y in points
        ]
        draw.line(shaky, fill=color, width=width, joint="curve")


def _polygon_mask(size: tuple[int, int], polygon: list[tuple[float, float]]) -> Image.Image:
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).polygon(polygon, fill=255)
    return mask


def wobble_mask(mask: Image.Image, rng: random.Random, amount: float,
                cell: int = 40) -> Image.Image:
    """실루엣 마스크 전체를 부드럽게 일렁이게 만든다.

    도형을 하나씩 흔드는 대신 합쳐진 실루엣을 통째로 흔들어야, 부품을
    붙여놓은 티가 안 나고 한 번에 그린 윤곽처럼 보인다.
    """
    if amount <= 0:
        return mask

    arr = np.array(mask)
    h, w = arr.shape
    coarse_h, coarse_w = max(2, h // cell), max(2, w // cell)

    def field() -> np.ndarray:
        coarse = rng_normal(rng, coarse_h, coarse_w, amount)
        return np.array(Image.fromarray(coarse, mode="F").resize((w, h), Image.BICUBIC),
                        dtype=np.float32)

    dx, dy = field(), field()
    yy, xx = np.meshgrid(np.arange(h), np.arange(w), indexing="ij")
    sx = np.clip(np.rint(xx + dx).astype(np.int64), 0, w - 1)
    sy = np.clip(np.rint(yy + dy).astype(np.int64), 0, h - 1)
    return Image.fromarray(arr[sy, sx], mode="L")


def rng_normal(rng: random.Random, h: int, w: int, scale: float) -> np.ndarray:
    """random.Random만으로 정규분포 배열을 만든다 (numpy 시드와 분리하기 위해)."""
    return np.array([[rng.gauss(0.0, scale) for _ in range(w)] for _ in range(h)],
                    dtype=np.float32)


def silhouette_outline(mask: Image.Image, width: int) -> Image.Image:
    """실루엣 경계를 따라가는 선 마스크.

    부품별 윤곽을 각각 긋지 않고 합쳐진 경계만 한 줄로 그으면, 귀·팔이
    '몸에 붙인 도형'이 아니라 몸에서 자라난 것처럼 보인다.
    """
    size = max(3, width if width % 2 else width + 1)
    grown = mask.filter(ImageFilter.MaxFilter(size))
    shrunk = mask.filter(ImageFilter.MinFilter(size))
    return ImageChops.difference(grown, shrunk)


def _dot(draw: ImageDraw.ImageDraw, cx: float, cy: float, r: float, color=INK) -> None:
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)


def _roughen(points: list[tuple[float, float]], rng: random.Random,
             amount: float) -> list[tuple[float, float]]:
    """매끈한 수식 곡선(하트·물방울)에 손떨림을 입힌다.

    이걸 안 하면 부속물만 반듯해서 몸통의 떨리는 선과 따로 논다 — 화풍이 깨진다.
    """
    nx, ny = _periodic_noise(rng), _periodic_noise(rng)
    last = max(1, len(points) - 1)
    return [
        (x + amount * nx(i / last), y + amount * ny(i / last))
        for i, (x, y) in enumerate(points)
    ]


def _heart_points(cx: float, cy: float, s: float, steps: int = 48) -> list[tuple[float, float]]:
    """고전적인 하트 곡선. 원 두 개를 겹치는 방식보다 훨씬 하트로 잘 읽힌다."""
    points = []
    for i in range(steps + 1):
        t = math.tau * i / steps
        x = 16 * math.sin(t) ** 3
        y = -(13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t))
        points.append((cx + x * s / 16.0, cy + y * s / 16.0))
    return points


def _drop_points(cx: float, cy: float, w: float, h: float) -> list[tuple[float, float]]:
    """물방울 — 아래는 둥글고 위는 뾰족하게."""
    points = _arc_points(cx, cy + h * 0.18, w * 0.5, w * 0.5, -30, 210, 22)
    points.append((cx, cy - h * 0.5))
    points.append(points[0])
    return points


def _arc_points(
    cx: float, cy: float, rx: float, ry: float,
    start_deg: float, end_deg: float, steps: int = 24,
) -> list[tuple[float, float]]:
    return [
        (cx + rx * math.cos(a), cy + ry * math.sin(a))
        for a in (
            math.radians(start_deg + (end_deg - start_deg) * i / steps)
            for i in range(steps + 1)
        )
    ]


# --------------------------------------------------------------------------
# 표정 파츠
# --------------------------------------------------------------------------

def _eye_highlight(draw, cx, cy, r, rng) -> None:
    """하이라이트가 크고 많을수록 귀엽고 흥분해 보인다 — 초롱초롱의 핵심."""
    hr = r * rng.uniform(0.38, 0.48)
    hx, hy = cx - r * 0.32, cy - r * 0.36
    draw.ellipse([hx - hr, hy - hr, hx + hr, hy + hr], fill=(255, 255, 255, 255))
    sr = r * rng.uniform(0.15, 0.22)
    sx, sy = cx + r * 0.30, cy + r * 0.34
    draw.ellipse([sx - sr, sy - sr, sx + sr, sy + sr], fill=(255, 255, 255, 225))


def _draw_eyes(draw, rng, lx, rx_, ey, base_r, kind: str, lw: int) -> None:
    """짝눈이 매력 포인트라 좌우를 반드시 다르게 그린다."""
    l_r = base_r * rng.uniform(0.86, 1.0)
    r_r = base_r * rng.uniform(1.0, 1.18)
    l_y = ey + rng.uniform(-base_r * 0.16, base_r * 0.10)
    r_y = ey + rng.uniform(-base_r * 0.10, base_r * 0.16)

    def sparkle(cx, cy, r):
        """초롱초롱 — 큰 눈망울 + 큼직한 하이라이트."""
        ball = wobbly_ellipse(cx, cy, r, r * rng.uniform(1.02, 1.16), rng, 36, 0.05)
        draw.polygon(ball, fill=EYE_INK)
        _eye_highlight(draw, cx, cy, r, rng)

    def manic(cx, cy, r):
        """광기 — 흰자를 크게 벌리고 동공을 작게, 위치도 제멋대로."""
        white = wobbly_ellipse(cx, cy, r * 1.28, r * 1.42, rng, 40, 0.07)
        draw.polygon(white, fill=(255, 255, 255, 255))
        pen_stroke(draw, white, rng, max(2, lw - 1), 1, color=EYE_INK, drift=1.0)
        px = cx + rng.uniform(-r * 0.40, r * 0.40)
        py = cy + rng.uniform(-r * 0.40, r * 0.40)
        pr = r * rng.uniform(0.34, 0.52)
        draw.ellipse([px - pr, py - pr, px + pr, py + pr], fill=EYE_INK)
        hr = pr * 0.42
        draw.ellipse([px - hr - pr * 0.25, py - hr - pr * 0.25,
                      px + hr - pr * 0.25, py + hr - pr * 0.25], fill=(255, 255, 255, 245))

    if kind == "sparkle":
        sparkle(lx, l_y, l_r)
        sparkle(rx_, r_y, r_r)
    elif kind == "manic":
        manic(lx, l_y, l_r)
        manic(rx_, r_y, r_r)
    elif kind == "closed_happy":                     # ^ ^
        pen_stroke(draw, _arc_points(lx, l_y + l_r * 0.6, l_r * 1.15, l_r * 1.0, 200, 340),
                   rng, lw, 2, color=EYE_INK, drift=1.2)
        pen_stroke(draw, _arc_points(rx_, r_y + r_r * 0.6, r_r * 1.15, r_r * 1.0, 200, 340),
                   rng, lw, 2, color=EYE_INK, drift=1.2)
    elif kind == "closed_flat":                      # - -
        pen_stroke(draw, [(lx - l_r * 1.1, l_y), (lx + l_r * 1.1, l_y)],
                   rng, lw, 2, color=EYE_INK, drift=1.2)
        pen_stroke(draw, [(rx_ - r_r * 1.1, r_y), (rx_ + r_r * 1.1, r_y)],
                   rng, lw, 2, color=EYE_INK, drift=1.2)
    elif kind == "wide":
        manic(lx, l_y, l_r * 1.12)
        manic(rx_, r_y, r_r * 1.12)
    elif kind == "half":
        sparkle(lx, l_y, l_r * 0.9)
        sparkle(rx_, r_y, r_r * 0.9)
        for cx, cy, r in ((lx, l_y, l_r), (rx_, r_y, r_r)):
            pen_stroke(draw, [(cx - r * 1.2, cy - r * 0.45), (cx + r * 1.2, cy - r * 0.55)],
                       rng, max(2, lw), 2, color=EYE_INK, drift=1.0)
    elif kind == "side":
        sparkle(lx + l_r * 0.5, l_y, l_r * 0.92)
        sparkle(rx_ + r_r * 0.5, r_y, r_r * 0.92)
    else:                                            # dots — 아주 작은 점눈
        _dot(draw, lx, l_y, l_r * 0.55, color=EYE_INK)
        _dot(draw, rx_, r_y, r_r * 0.55, color=EYE_INK)


def _draw_mouth(draw, rng, cx, cy, w, kind: str, lw: int) -> None:
    if kind == "big_smile":
        pen_stroke(draw, _arc_points(cx, cy - w * 0.3, w * 0.75, w * 0.8, 15, 165), rng, lw, 2, color=MOUTH_INK, drift=1.2)
    elif kind == "smile":
        pen_stroke(draw, _arc_points(cx, cy - w * 0.12, w * 0.5, w * 0.42, 25, 155), rng, lw, 2, color=MOUTH_INK, drift=1.2)
    elif kind == "frown":
        pen_stroke(draw, _arc_points(cx, cy + w * 0.45, w * 0.5, w * 0.42, 205, 335), rng, lw, 2, color=MOUTH_INK, drift=1.2)
    elif kind == "flat":
        pen_stroke(draw, [(cx - w * 0.35, cy), (cx + w * 0.35, cy + rng.uniform(-3, 3))], rng, lw, 2, color=MOUTH_INK, drift=1.2)
    elif kind == "o":
        # 크고 진하게 채우면 얼굴에 구멍이 뚫린 것처럼 보인다
        mouth_o = wobbly_ellipse(cx, cy, w * 0.20, w * 0.28, rng, 36, 0.12)
        draw.polygon(mouth_o, fill=(196, 132, 130, 255))
        pen_stroke(draw, mouth_o, rng, max(2, lw - 1), 1, color=MOUTH_INK, drift=0.8)
    elif kind == "wavy":
        pts = [
            (cx - w * 0.42 + w * 0.84 * (i / 24), cy + math.sin((i / 24) * math.tau * 1.6) * w * 0.22)
            for i in range(25)
        ]
        pen_stroke(draw, pts, rng, lw, 2, color=MOUTH_INK, drift=1.2)
    elif kind == "cat":  # ω
        pen_stroke(draw, _arc_points(cx - w * 0.22, cy, w * 0.24, w * 0.28, 0, 175), rng, lw, 2, color=MOUTH_INK, drift=1.2)
        pen_stroke(draw, _arc_points(cx + w * 0.22, cy, w * 0.24, w * 0.28, 5, 180), rng, lw, 2, color=MOUTH_INK, drift=1.2)


_POSE_ANGLES = {
    "up": (-128, -52), "down": (152, 28), "out": (178, 2),
    "hug": (128, 52), "cross": (118, 62), "hip": (146, 34),
    "wave": (-118, 22), "fist": (-104, 30), "belly": (112, 68),
}


def _luminance(color: tuple[int, int, int, int]) -> float:
    r, g, b = color[:3]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _lighten(color: tuple[int, int, int, int], amount: float) -> tuple[int, int, int, int]:
    r, g, b, a = color
    return (
        int(r + (255 - r) * amount),
        int(g + (255 - g) * amount),
        int(b + (255 - b) * amount),
        a,
    )


def _ear_shapes(rng, cx, cy, rx, ry, kind: str) -> list[list[tuple[float, float]]]:
    """귀 윤곽 경로를 좌우 한 쌍으로 만든다. 좌우를 미세하게 다르게 뽑는다."""
    if kind == "none":
        return []

    shapes = []
    for sx in (-1, 1):
        wiggle = rng.uniform(0.92, 1.10)
        if kind == "round":       # 곰 — 머리 위에 큼직한 반원
            ex = cx + sx * rx * rng.uniform(0.52, 0.64)
            ey = cy - ry * rng.uniform(0.80, 0.92)
            shapes.append(wobbly_ellipse(ex, ey, rx * 0.28 * wiggle, rx * 0.27 * wiggle, rng, 40, 0.13))
        elif kind == "tiny":      # 햄스터 — 작고 동그란 귀
            ex = cx + sx * rx * rng.uniform(0.52, 0.62)
            ey = cy - ry * rng.uniform(0.86, 0.96)
            shapes.append(wobbly_ellipse(ex, ey, rx * 0.17 * wiggle, rx * 0.17 * wiggle, rng, 36, 0.14))
        elif kind == "long":      # 토끼 — 길쭉한 귀, 살짝 벌어지게
            ex = cx + sx * rx * rng.uniform(0.26, 0.38)
            ey = cy - ry * rng.uniform(1.02, 1.18)
            tilt = sx * rng.uniform(0.12, 0.30)
            shapes.append(wobbly_ellipse(ex, ey, rx * 0.16 * wiggle, ry * 0.42 * wiggle,
                                         rng, 48, 0.10, tilt=tilt))
        elif kind == "pointy":    # 고양이 — 삼각 귀
            ex = cx + sx * rx * rng.uniform(0.46, 0.56)
            ey = cy - ry * rng.uniform(0.86, 0.98)
            w, h = rx * 0.24 * wiggle, ry * 0.34 * wiggle
            shapes.append(_roughen([
                (ex - w, ey + h * 0.55), (ex + sx * w * 0.25, ey - h * 0.75),
                (ex + w, ey + h * 0.55), (ex - w, ey + h * 0.55),
            ], rng, rx * 0.03))
        elif kind == "floppy":    # 강아지 — 옆으로 축 늘어진 귀
            ex = cx + sx * rx * rng.uniform(0.72, 0.84)
            ey = cy - ry * rng.uniform(0.18, 0.32)
            shapes.append(wobbly_ellipse(ex, ey, rx * 0.20 * wiggle, ry * 0.36 * wiggle,
                                         rng, 44, 0.12, tilt=sx * 0.28))
    return shapes


def _draw_nose(draw, rng, cx, cy, rx, kind: str, lw: int) -> None:
    if kind == "none":
        return
    if kind in ("dot", "big"):
        s = rx * (0.075 if kind == "dot" else 0.11)
        # 외곽선 + 점을 겹쳐 그리면 뭉개진다. 통째로 칠한 뒤 한 획만 덧그린다.
        blob = wobbly_ellipse(cx, cy, s, s * 0.82, rng, 28, 0.16)
        draw.polygon(blob, fill=NOSE_DARK)
    elif kind == "triangle":
        s = rx * 0.085
        tri = _roughen([
            (cx - s, cy - s * 0.55), (cx + s, cy - s * 0.55), (cx, cy + s * 0.8),
            (cx - s, cy - s * 0.55),
        ], rng, rx * 0.014)
        draw.polygon(tri, fill=NOSE_PINK)
        pen_stroke(draw, tri, rng, max(2, lw - 2), 1, color=_darken(NOSE_PINK, 0.30), drift=0.8)


def _draw_beak(draw, rng, cx, cy, rx, lw: int) -> None:
    """오리 — 코와 입을 겸하는 부리. 이 경우 별도 입을 그리지 않는다."""
    w, h = rx * 0.30, rx * 0.17
    beak = _roughen([
        (cx - w, cy - h * 0.2), (cx, cy - h), (cx + w, cy - h * 0.2),
        (cx + w * 0.55, cy + h), (cx - w * 0.55, cy + h), (cx - w, cy - h * 0.2),
    ], rng, rx * 0.018)
    draw.polygon(beak, fill=(255, 190, 92, 255))
    pen_stroke(draw, beak, rng, lw, 2)
    # 부리 가운데 선
    pen_stroke(draw, [(cx - w * 0.75, cy - h * 0.1), (cx + w * 0.75, cy - h * 0.1)], rng, max(2, lw - 1), 1)


def _draw_whiskers(draw, rng, cx, cy, rx, lw: int) -> None:
    for sx in (-1, 1):
        for i in range(rng.randint(2, 3)):
            y = cy + (i - 1) * rx * 0.10 + rng.uniform(-3, 3)
            x0 = cx + sx * rx * rng.uniform(0.34, 0.44)
            x1 = cx + sx * rx * rng.uniform(0.66, 0.80)
            pen_stroke(draw, [(x0, y), (x1, y + rng.uniform(-8, 8))], rng, max(2, lw - 1), 1, color=BROW_INK, drift=1.0)


def _draw_teeth(draw, rng, cx, cy, rx, lw: int) -> None:
    """앞니 — 햄스터/토끼를 단번에 알아보게 하는 요소."""
    w, h = rx * 0.062, rx * 0.10
    gap = w * 1.15
    for sx in (-1, 1):
        x = cx + sx * gap * 0.55
        rect = _roughen([
            (x - w, cy), (x + w, cy), (x + w, cy + h), (x - w, cy + h), (x - w, cy),
        ], rng, rx * 0.010)
        draw.polygon(rect, fill=(255, 255, 255, 255))
        pen_stroke(draw, rect, rng, max(2, lw - 1), 1, color=MOUTH_INK, drift=0.8)


def _quad_bezier(p0, p1, p2, steps: int = 16) -> list[tuple[float, float]]:
    """2차 베지에 곡선. 팔다리 뼈대를 휘게 만드는 데 쓴다."""
    points = []
    for i in range(steps + 1):
        t = i / steps
        u = 1.0 - t
        points.append((
            u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0],
            u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1],
        ))
    return points


def _ribbon(spine: list[tuple[float, float]], r0: float, r1: float,
            cap_steps: int = 8) -> list[tuple[float, float]]:
    """휜 뼈대를 따라 두께를 입혀 폴리곤으로 만든다.

    직선 캡슐로 만든 팔다리는 뻣뻣하다. 곡선 뼈대에 살을 붙여야 자연스럽게
    휘어진 팔다리·꼬리·귀가 나온다.
    """
    n = len(spine)
    left, right = [], []
    for i, (x, y) in enumerate(spine):
        r = r0 + (r1 - r0) * (i / (n - 1))
        if i == 0:
            dx, dy = spine[1][0] - x, spine[1][1] - y
        elif i == n - 1:
            dx, dy = x - spine[-2][0], y - spine[-2][1]
        else:
            dx, dy = spine[i + 1][0] - spine[i - 1][0], spine[i + 1][1] - spine[i - 1][1]
        length = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / length * r, dx / length * r
        left.append((x + nx, y + ny))
        right.append((x - nx, y - ny))

    def cap(centre, tangent: float, radius: float, start_off: float):
        """반원은 항상 진행 방향 *바깥쪽*으로 돌아야 한다.

        반대로 돌면 폴리곤이 자기 자신을 가로질러 톱니처럼 삐죽해진다.
        """
        return [
            (centre[0] + math.cos(tangent + start_off - math.pi * i / cap_steps) * radius,
             centre[1] + math.sin(tangent + start_off - math.pi * i / cap_steps) * radius)
            for i in range(cap_steps + 1)
        ]

    head_t = math.atan2(spine[-1][1] - spine[-2][1], spine[-1][0] - spine[-2][0])
    tail_t = math.atan2(spine[1][1] - spine[0][1], spine[1][0] - spine[0][0])

    return (left                                   # 한쪽 옆면 (시작 → 끝)
            + cap(spine[-1], head_t, r1, math.pi / 2)   # 끝단 반원
            + right[::-1]                          # 반대쪽 옆면 (끝 → 시작)
            + cap(spine[0], tail_t, r0, -math.pi / 2))  # 뿌리쪽 반원


def _capsule(p0, p1, r0: float, r1: float, steps: int = 12) -> list[tuple[float, float]]:
    """양 끝이 둥근 캡슐 폴리곤. 팔다리 한 짝을 하나의 덩어리로 만든다."""
    (x0, y0), (x1, y1) = p0, p1
    ang = math.atan2(y1 - y0, x1 - x0)
    points = []
    for i in range(steps + 1):          # 뿌리쪽 반원
        a = ang + math.pi / 2 + math.pi * i / steps
        points.append((x0 + math.cos(a) * r0, y0 + math.sin(a) * r0))
    for i in range(steps + 1):          # 끝쪽 반원
        a = ang - math.pi / 2 + math.pi * i / steps
        points.append((x1 + math.cos(a) * r1, y1 + math.sin(a) * r1))
    return points


def _darken(color: tuple[int, int, int, int], amount: float) -> tuple[int, int, int, int]:
    r, g, b, a = color
    return (int(r * (1 - amount)), int(g * (1 - amount)), int(b * (1 - amount)), a)


def _limb_shapes(rng, trunk, cx, cy, body_rx, body_ry, rx, ry,
                 pose: str, limb_delta: float = 0.0) -> list[list[tuple[float, float]]]:
    """팔 두 짝 + 다리 두 짝을 캡슐 폴리곤으로 만든다.

    팔은 머리가 아니라 **몸통**에서 나와야 동물로 보인다.
    """
    left_deg, right_deg = _POSE_ANGLES.get(pose, _POSE_ANGLES["down"])
    left_deg -= limb_delta
    right_deg += limb_delta

    shapes = []
    for angle_deg in (left_deg, right_deg):
        a = math.radians(angle_deg)
        left_side = math.cos(a) < 0
        lift = -1 if math.sin(a) < 0 else 1
        attach = (180 + lift * 22) if left_side else (0 - lift * 22)
        x0, y0 = _point_on(trunk, cx, cy, attach + rng.uniform(-8, 8))

        length = rx * rng.uniform(0.42, 0.58)
        end = (x0 + math.cos(a) * length, y0 + math.sin(a) * length)
        # 뼈대를 옆으로 휜다. 직선이면 막대기처럼 뻣뻣하다.
        bend = rx * rng.uniform(0.10, 0.26) * rng.choice([-1, 1])
        mid = (x0 + math.cos(a) * length * 0.5 - math.sin(a) * bend,
               y0 + math.sin(a) * length * 0.5 + math.cos(a) * bend)
        shapes.append(_ribbon(_quad_bezier((x0, y0), mid, end),
                              rx * rng.uniform(0.115, 0.135),
                              rx * rng.uniform(0.085, 0.105)))

    for sx in (-1, 1):
        x0, y0 = _point_on(trunk, cx, cy, 90 + sx * rng.uniform(24, 42))
        leg = ry * rng.uniform(0.16, 0.24)
        foot = (x0 + sx * rng.uniform(4, 14), y0 + leg)
        mid = (x0 + sx * rng.uniform(-4, 2), y0 + leg * 0.55)
        shapes.append(_ribbon(_quad_bezier((x0, y0), mid, foot),
                              rx * rng.uniform(0.115, 0.135),
                              rx * rng.uniform(0.105, 0.125)))
    return shapes


def _tail_shape(rng, trunk, cx, cy, body_rx, body_ry, rx,
                kind: str) -> list[list[tuple[float, float]]]:
    if kind == "none":
        return []
    base = _point_on(trunk, cx, cy, rng.uniform(15, 45))
    if kind == "stub":
        return [wobbly_ellipse(base[0] + rx * 0.07, base[1],
                               rx * 0.11, rx * 0.10, rng, 28, 0.08)]
    # 말린 꼬리 — 위로 휘어 올라가게
    tip = (base[0] + rx * rng.uniform(0.16, 0.26), base[1] - body_ry * rng.uniform(0.55, 0.85))
    mid = (base[0] + rx * rng.uniform(0.28, 0.40), base[1] - body_ry * rng.uniform(0.05, 0.25))
    return [_ribbon(_quad_bezier(base, mid, tip), rx * 0.085, rx * 0.05)]


def _draw_extras(draw, rng, cx, cy, rx, ry, extras: list[str], lw: int) -> None:
    for extra in extras:
        if extra == "heart":
            hx, hy = cx + rx * rng.uniform(0.80, 1.05), cy - ry * rng.uniform(0.95, 1.20)
            heart = _roughen(_heart_points(hx, hy, rx * rng.uniform(0.34, 0.44)),
                             rng, rx * 0.030)
            draw.polygon(heart, fill=HEART_FILL)
            pen_stroke(draw, heart, rng, max(2, lw - 1), 1, color=HEART_LINE, drift=1.0)
        elif extra == "tear":
            tx = cx - rx * rng.uniform(0.48, 0.60)
            ty = cy + ry * rng.uniform(0.04, 0.18)
            drop = _roughen(_drop_points(tx, ty, rx * 0.19, rx * 0.34), rng, rx * 0.018)
            draw.polygon(drop, fill=DROP_FILL)
            pen_stroke(draw, drop, rng, max(2, lw - 1), 1, color=DROP_LINE, drift=1.0)
        elif extra == "sweat":
            sx_, sy_ = cx + rx * rng.uniform(0.72, 0.90), cy - ry * rng.uniform(0.42, 0.60)
            drop = _roughen(_drop_points(sx_, sy_, rx * 0.20, rx * 0.36), rng, rx * 0.018)
            draw.polygon(drop, fill=DROP_FILL)
            pen_stroke(draw, drop, rng, max(2, lw - 1), 1, color=DROP_LINE, drift=1.0)
        elif extra == "blush":
            for sx in (-1, 1):
                bx = cx + sx * rx * rng.uniform(0.50, 0.64)
                by = cy + ry * rng.uniform(0.04, 0.16)
                for i in range(3):
                    yy = by + (i - 1) * rx * 0.075
                    pen_stroke(draw, [(bx - rx * 0.105, yy), (bx + rx * 0.105, yy)], rng,
                               max(2, lw - 1), 1, color=BLUSH_COLOR, drift=1.2)
        elif extra == "sparkle":
            for _ in range(3):
                px = cx + rng.uniform(-rx * 1.3, rx * 1.3)
                py = cy - ry * rng.uniform(0.70, 1.25)
                s = rx * rng.uniform(0.09, 0.15)
                pen_stroke(draw, [(px - s, py), (px + s, py)], rng, lw, 1,
                           color=SPARKLE_COLOR, drift=1.0)
                pen_stroke(draw, [(px, py - s), (px, py + s)], rng, lw, 1,
                           color=SPARKLE_COLOR, drift=1.0)
        elif extra == "anger":
            ax_, ay_ = cx + rx * rng.uniform(0.55, 0.70), cy - ry * rng.uniform(0.55, 0.70)
            s = rx * 0.15
            pen_stroke(draw, [(ax_ - s, ay_ - s), (ax_ + s, ay_ + s)], rng, lw, 1,
                       color=ANGER_COLOR, drift=1.0)
            pen_stroke(draw, [(ax_ + s, ay_ - s), (ax_ - s, ay_ + s)], rng, lw, 1,
                       color=ANGER_COLOR, drift=1.0)
        elif extra == "brows":
            for sx, tilt in ((-1, 1), (1, -1)):
                bx = cx + sx * rx * 0.36
                by = cy - ry * rng.uniform(0.40, 0.48)
                pen_stroke(draw, [(bx - rx * 0.17, by - tilt * rx * 0.10),
                                  (bx + rx * 0.17, by + tilt * rx * 0.10)],
                           rng, lw + 1, 2, color=BROW_INK, drift=1.2)
        elif extra == "zzz":  # 글자 대신 동그란 숨소리 방울
            bx, by = cx + rx * 0.85, cy - ry * 0.80
            for i in range(3):
                r = rx * (0.045 + i * 0.035)
                pen_stroke(draw, wobbly_ellipse(bx + i * rx * 0.22, by - i * ry * 0.17,
                                                r, r, rng, 24, 0.16), rng,
                           max(2, lw - 1), 1, color=BROW_INK, drift=1.0)


# --------------------------------------------------------------------------
# 감정 → 표정 조합
# --------------------------------------------------------------------------

EXPRESSIONS: dict[str, dict] = {
    "안녕":     {"eyes": "sparkle", "mouth": "smile", "pose": "wave"},
    "반가워":   {"eyes": "closed_happy", "mouth": "big_smile", "pose": "wave"},
    "기쁨":     {"eyes": "closed_happy", "mouth": "big_smile", "pose": "up", "extras": ["sparkle"]},
    "슬픔":     {"eyes": "half", "mouth": "frown", "pose": "down", "extras": ["tear"]},
    "화남":     {"eyes": "manic", "mouth": "wavy", "pose": "hip", "extras": ["anger", "brows"]},
    "놀람":     {"eyes": "manic", "mouth": "o", "pose": "out"},
    "사랑해":   {"eyes": "closed_happy", "mouth": "cat", "pose": "hug", "extras": ["heart", "blush"]},
    "고마워":   {"eyes": "closed_happy", "mouth": "smile", "pose": "hug"},
    "미안해":   {"eyes": "half", "mouth": "frown", "pose": "down"},
    "축하해":   {"eyes": "closed_happy", "mouth": "big_smile", "pose": "up", "extras": ["sparkle"]},
    "화이팅":   {"eyes": "sparkle", "mouth": "big_smile", "pose": "fist"},
    "웃김":     {"eyes": "closed_happy", "mouth": "big_smile", "pose": "belly", "extras": ["tear"]},
    "심심함":   {"eyes": "half", "mouth": "flat", "pose": "down"},
    "졸림":     {"eyes": "closed_flat", "mouth": "o", "pose": "down", "extras": ["zzz"]},
    "배고픔":   {"eyes": "half", "mouth": "wavy", "pose": "belly"},
    "당황":     {"eyes": "manic", "mouth": "o", "pose": "out", "extras": ["sweat"]},
    "부끄러움": {"eyes": "closed_happy", "mouth": "smile", "pose": "hug", "extras": ["blush"]},
    "자신감":   {"eyes": "sparkle", "mouth": "smile", "pose": "hip", "extras": ["sparkle"]},
    "실망":     {"eyes": "half", "mouth": "frown", "pose": "down"},
    "긴장":     {"eyes": "manic", "mouth": "wavy", "pose": "cross", "extras": ["sweat"]},
    "감동":     {"eyes": "closed_happy", "mouth": "smile", "pose": "hug", "extras": ["tear"]},
    "궁금함":   {"eyes": "sparkle", "mouth": "flat", "pose": "hip"},
    "지침":     {"eyes": "closed_flat", "mouth": "frown", "pose": "down", "extras": ["sweat"]},
    "설렘":     {"eyes": "closed_happy", "mouth": "cat", "pose": "hug", "extras": ["heart", "blush"]},
    "만족":     {"eyes": "closed_happy", "mouth": "cat", "pose": "hip"},
    "거절":     {"eyes": "manic", "mouth": "flat", "pose": "cross"},
    "수긍":     {"eyes": "closed_flat", "mouth": "smile", "pose": "down"},
    "눈치보기": {"eyes": "side", "mouth": "flat", "pose": "cross"},
    "신남":     {"eyes": "closed_happy", "mouth": "big_smile", "pose": "up", "extras": ["sparkle"]},
    "멍때림":   {"eyes": "dots", "mouth": "o", "pose": "down"},
    "삐짐":     {"eyes": "closed_flat", "mouth": "frown", "pose": "cross", "extras": ["blush"]},
    "잘자":     {"eyes": "closed_flat", "mouth": "smile", "pose": "down", "extras": ["zzz"]},
}

_EYE_KINDS = ["sparkle", "manic", "dots", "closed_happy", "closed_flat",
              "wide", "half", "side"]
_MOUTH_KINDS = ["smile", "big_smile", "frown", "flat", "o", "wavy", "cat"]
_POSES = list(_POSE_ANGLES)


def _fallback_expression(keyword: str) -> dict:
    """등록되지 않은 키워드도 결정론적으로 표정을 배정받는다."""
    h = hashlib.sha256(keyword.encode("utf-8")).digest()
    return {
        "eyes": _EYE_KINDS[h[0] % len(_EYE_KINDS)],
        "mouth": _MOUTH_KINDS[h[1] % len(_MOUTH_KINDS)],
        "pose": _POSES[h[2] % len(_POSES)],
        "extras": [],
    }


def _seed_for(keyword: str, seed: int | None) -> int:
    if seed is not None:
        return seed
    return int(hashlib.sha256(keyword.encode("utf-8")).hexdigest()[:8], 16)


# --------------------------------------------------------------------------
# 메인 진입점
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Motion:
    """한 프레임의 움직임. 그림 자체는 건드리지 않고 자세만 바꾼다.

    움짤은 **같은 seed + 다른 Motion**으로 만든다. seed를 바꾸면 선이 매
    프레임 새로 그려져 화면이 지글거리기 때문이다 (boiling line 효과는
    의도했을 때만 써야 한다).
    """
    dy: float = 0.0       # 세로 이동 (세로 반지름 대비 비율)
    tilt: float = 0.0     # 몸통 기울기 (라디안)
    limb: float = 0.0     # 팔 각도 변화 (도)
    squash: float = 0.0   # 눌림 (양수면 납작해지고 옆으로 퍼짐)


def _bounce(t: float) -> Motion:
    phase = math.sin(t * math.tau)
    return Motion(
        dy=-0.16 * max(0.0, phase),
        squash=0.12 * max(0.0, -phase),
        limb=20.0 * phase,
    )


def _wiggle(t: float) -> Motion:
    phase = math.sin(t * math.tau)
    return Motion(tilt=0.11 * phase, limb=12.0 * phase, dy=-0.03 * abs(phase))


def _nod(t: float) -> Motion:
    phase = math.sin(t * math.tau)
    return Motion(dy=0.07 * phase, squash=0.05 * max(0.0, phase))


MOTION_PRESETS = {"bounce": _bounce, "wiggle": _wiggle, "nod": _nod}


DEFAULT_CHARACTER = CharacterSpec(
    color=(252, 249, 242, 255), animal="bear", rx_ratio=0.27, ry_ratio=0.27,
    bulge=0.10, eye_scale=1.1, eye_spread=0.39,
    ear="round", nose="dot", muzzle=True, tail="stub", name="default",
)


def render_character(
    keyword: str, size: int = 360, seed: int | None = None,
    character: CharacterSpec | None = None, motion: Motion | None = None,
) -> Image.Image:
    """감정 키워드 하나를 발그림 캐릭터 한 컷으로 그린다.

    `character`가 같으면 같은 캐릭터, `seed`가 다르면 손떨림만 달라진다.
    """
    spec_char = character or DEFAULT_CHARACTER
    move = motion or Motion()
    rng = random.Random(_seed_for(keyword, seed))
    face = EXPRESSIONS.get(keyword) or _fallback_expression(keyword)

    S = size * _SUPERSAMPLE
    canvas = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    lw = max(3, int(S * 0.0055))

    # 중심과 기울기만 흔들고, 크기 비율은 캐릭터 정체성이라 고정
    cx = S * 0.5 + rng.uniform(-S * 0.015, S * 0.015)
    cy = S * 0.50 + rng.uniform(-S * 0.010, S * 0.010)
    rx = S * spec_char.rx_ratio
    ry = S * spec_char.ry_ratio
    tilt = rng.uniform(-0.05, 0.05)

    # 모션은 난수를 뽑은 *뒤에* 더한다. 순서를 바꾸면 프레임마다 rng 소비가
    # 달라져 선이 통째로 다시 그려지고 화면이 지글거린다.
    cy += ry * move.dy
    tilt += move.tilt
    rx *= 1.0 + move.squash * 0.5
    ry *= 1.0 - move.squash

    # --- 1) 머리 + 몸통을 나눠 동물 형태를 만든다 --------------------
    # 통짜 원 하나면 감자에 혹이 붙은 모양이 된다. 큰 머리 + 작은 몸통이
    # 겹쳐야 비로소 '동물'로 읽힌다.
    head_cy = cy - ry * 0.26
    head_rx, head_ry = rx * 0.98, ry * 0.86
    body_cy = cy + ry * 0.62
    body_rx, body_ry = rx * 0.76, ry * 0.52

    # 왜곡은 약하게. 과하면 찌그러진 덩어리로 보인다.
    head = wobbly_ellipse(cx, head_cy, head_rx, head_ry, rng,
                          96, rng.uniform(0.018, 0.032), tilt=tilt)
    trunk = wobbly_ellipse(cx + rng.uniform(-rx * 0.03, rx * 0.03), body_cy,
                           body_rx, body_ry, rng, 72, rng.uniform(0.020, 0.035),
                           tilt=tilt * 0.5, bulge=spec_char.bulge * 0.5)
    ears = _ear_shapes(rng, cx, head_cy, head_rx, head_ry, spec_char.ear)

    limbs = _limb_shapes(rng, trunk, cx, body_cy, body_rx, body_ry, rx, ry,
                         face.get("pose", "down"), move.limb)
    tail = _tail_shape(rng, trunk, cx, body_cy, body_rx, body_ry, rx, spec_char.tail)

    cheeks: list[list[tuple[float, float]]] = []
    if spec_char.cheeks:
        for sx in (-1, 1):
            cheeks.append(wobbly_ellipse(
                cx + sx * head_rx * rng.uniform(0.54, 0.62),
                head_cy + head_ry * rng.uniform(0.26, 0.36),
                head_rx * rng.uniform(0.32, 0.37), head_rx * rng.uniform(0.27, 0.31),
                rng, 40, 0.06))

    # --- 2) 실루엣 하나로 합치기 ---------------------------------------
    parts = ears + limbs + tail + cheeks          # 몸에서 뻗어나온 부품들
    silhouette = Image.new("L", (S, S), 0)
    sdraw = ImageDraw.Draw(silhouette)
    for poly in [head, trunk, *parts]:
        sdraw.polygon(poly, fill=255)
    silhouette = wobble_mask(silhouette, rng, amount=S * 0.0015)

    # --- 3) 평면 채색 + 부품 명암 + 안쪽 구분선 ------------------------
    canvas.paste(spec_char.color, (0, 0), silhouette)

    # 몸통·머리에 가려지는 부분은 칠하지도 긋지도 않는다.
    # 안 그러면 팔다리가 몸을 투과해 보이는 X-ray 그림이 된다.
    core = Image.new("L", (S, S), 0)
    core_draw = ImageDraw.Draw(core)
    core_draw.polygon(head, fill=255)
    core_draw.polygon(trunk, fill=255)
    not_core = ImageChops.invert(core)

    # 귀·팔다리·꼬리에만 한 톤 낮춘 평면 명암. 볼은 얼굴의 일부라 제외한다
    # (칠하면 얼굴에 회색 원 두 개를 붙인 꼴이 된다).
    shade = _darken(spec_char.color, 0.075)
    appendages = ears + limbs + tail
    app_mask = Image.new("L", (S, S), 0)
    app_draw = ImageDraw.Draw(app_mask)
    for poly in appendages:
        app_draw.polygon(poly, fill=255)
    canvas.paste(shade, (0, 0),
                 ImageChops.multiply(ImageChops.multiply(app_mask, not_core), silhouette))

    # 안쪽 구분선. 바깥 윤곽은 하나로 이어진 채 두고 안쪽에만 선이 생겨야
    # "한 마리인데 팔다리가 구분되는" 그림이 된다.
    interior = silhouette.filter(ImageFilter.MinFilter(max(3, lw | 1)))
    inner_ink = _darken(spec_char.color, 0.45)
    inner_w = max(3, (lw - 1) | 1)

    for poly in appendages:
        band = silhouette_outline(_polygon_mask((S, S), poly), inner_w)
        band = ImageChops.multiply(ImageChops.multiply(band, interior), not_core)
        canvas.paste(inner_ink, (0, 0), band)

    # 머리와 몸통이 만나는 자리 — 가슴/배 선
    neck = silhouette_outline(_polygon_mask((S, S), trunk), inner_w)
    canvas.paste(inner_ink, (0, 0), ImageChops.multiply(neck, interior))

    canvas.paste(INK, (0, 0), silhouette_outline(silhouette, lw))

    # --- 3) 얼굴 -------------------------------------------------------
    # 트렌드: 중안부가 길다. 눈은 위쪽에 작고 좁게, 입은 한참 아래에.
    eye_y = head_cy - head_ry * rng.uniform(0.24, 0.32)
    mouth_y = head_cy + head_ry * rng.uniform(0.34, 0.46)
    nose_y = mouth_y - head_rx * rng.uniform(0.17, 0.23)

    # 흰둥이처럼 몸이 이미 밝으면 주둥이를 칠해도 보이지 않는다.
    # 대비가 안 나오는 칠은 그리지 않는 게 낫다 — 흰 얼룩만 남는다.
    if spec_char.muzzle and _luminance(spec_char.color) < 235:
        snout = wobbly_ellipse(cx + rng.uniform(-head_rx * 0.03, head_rx * 0.03),
                               (nose_y + mouth_y) * 0.5,
                               head_rx * 0.30, head_rx * 0.22, rng, 44, 0.06)
        canvas.paste(_lighten(spec_char.color, 0.6), (0, 0),
                     _polygon_mask((S, S), snout))

    eye_dx = head_rx * spec_char.eye_spread
    _draw_eyes(draw, rng,
               cx - eye_dx * rng.uniform(0.94, 1.06),
               cx + eye_dx * rng.uniform(0.94, 1.06),
               eye_y, S * 0.021 * spec_char.eye_scale, face.get("eyes", "sparkle"), lw)

    if spec_char.nose == "beak":
        _draw_beak(draw, rng, cx, (nose_y + mouth_y) * 0.5, head_rx, lw)
    else:
        _draw_nose(draw, rng, cx, nose_y, head_rx, spec_char.nose, lw)
        if spec_char.whiskers:
            _draw_whiskers(draw, rng, cx, nose_y, head_rx, lw)
        _draw_mouth(draw, rng, cx + rng.uniform(-head_rx * 0.04, head_rx * 0.04),
                    mouth_y, head_rx * 0.34, face.get("mouth", "smile"), lw)
        if spec_char.teeth:
            _draw_teeth(draw, rng, cx, mouth_y + head_rx * 0.05, head_rx, lw)

    _draw_extras(draw, rng, cx, head_cy, head_rx, head_ry, face.get("extras", []), lw)

    return canvas.resize((size, size), Image.LANCZOS)


def render_contact_sheet(
    keywords: list[str], cell: int = 300, cols: int = 4, seed: int | None = None,
    character: CharacterSpec | None = None,
    background: tuple[int, int, int, int] = (255, 255, 255, 255),
) -> Image.Image:
    """한 캐릭터의 여러 표정을 격자로 배치한다.

    32컷의 낙서 텐션이 일정한지 눈으로 확인할 때 쓴다 (STYLE_GUIDE 체크리스트).
    """
    if not keywords:
        raise ValueError("keywords must not be empty")

    rows = math.ceil(len(keywords) / cols)
    sheet = Image.new("RGBA", (cols * cell, rows * cell), background)
    for i, keyword in enumerate(keywords):
        cut = render_character(keyword, cell, None if seed is None else seed + i, character)
        sheet.alpha_composite(cut, ((i % cols) * cell, (i // cols) * cell))
    return sheet


def render_animation(
    keyword: str, size: int = 360, seed: int | None = None,
    character: CharacterSpec | None = None, frames: int = 8, kind: str = "bounce",
) -> list[Image.Image]:
    """움직이는 이모티콘용 루프 프레임을 만든다.

    모든 프레임이 **같은 seed**를 쓰므로 선은 그대로 있고 자세만 움직인다.
    프레임마다 seed를 바꾸면 선이 통째로 다시 그려져 화면이 지글거린다.

    반환한 프레임은 `postprocess.frames_to_gif()`로 GIF가 된다.

    ⚠️ 움직이는 이모티콘의 카카오 제출 규격(프레임 수·용량·재생 시간)은
    멈춰있는 이모티콘과 다르다. 제출 전 공식 가이드를 확인할 것.
    """
    motion_fn = MOTION_PRESETS.get(kind)
    if motion_fn is None:
        raise ValueError(f"unknown motion '{kind}'. choose from: {', '.join(MOTION_PRESETS)}")
    if frames < 2:
        raise ValueError("frames must be at least 2")

    return [
        render_character(keyword, size=size, seed=seed, character=character,
                         motion=motion_fn(i / frames))
        for i in range(frames)
    ]


def render_lineup(
    count: int = 8, keyword: str = "안녕", cell: int = 300, cols: int = 4,
    base_seed: int = 0, background: tuple[int, int, int, int] = (255, 255, 255, 255),
) -> tuple[Image.Image, list[CharacterSpec]]:
    """서로 다른 캐릭터 후보를 같은 표정으로 나란히 그려 디자인을 비교한다.

    후보 수가 종 수 이하이면 종이 겹치지 않게 하나씩 배정한다 — 같은 동물만
    여러 번 나오면 비교가 안 되기 때문이다.
    """
    if count <= len(ANIMALS):
        picks: list[str | None] = ANIMALS[:count]
    else:
        picks = [ANIMALS[i % len(ANIMALS)] for i in range(count)]
    characters = [
        make_character(base_seed + i, name=f"후보{i + 1}", animal=picks[i],
                       color=PALETTE[i % len(PALETTE)])
        for i in range(count)
    ]
    rows = math.ceil(count / cols)
    sheet = Image.new("RGBA", (cols * cell, rows * cell), background)
    for i, char in enumerate(characters):
        cut = render_character(keyword, cell, base_seed + i, char)
        sheet.alpha_composite(cut, ((i % cols) * cell, (i // cols) * cell))
    return sheet, characters
