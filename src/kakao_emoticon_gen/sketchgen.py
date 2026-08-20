"""볼펜 발그림 캐릭터를 절차적으로 그리는 렌더러 (AI 모델 불필요).

이 화풍의 본질은 "정제되지 않음"이라, 오히려 난수 기반으로 재현하기 좋다.
docs/STYLE_GUIDE.md의 고정 규칙 4가지를 그대로 코드로 옮긴 것이다.

- 눈    : 검정 점눈만. 크기·높이를 일부러 다르게 (짝눈)
- 선    : 얇고 떨리는 볼펜 선. 한 획을 두세 번 겹쳐 긋고, 끝을 안 만나게 벌림
- 비율  : 좌우 대칭 금지. 머리가 찌그러지고 팔다리 길이가 제각각
- 채색  : 윤곽선에서 어긋난 문지르기. 밖으로 삐져나가고 안쪽은 듬성듬성

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

from PIL import Image, ImageChops, ImageDraw

# 완전한 검정보다 살짝 따뜻한 볼펜 잉크 색
INK = (38, 34, 30, 255)

PALETTE: list[tuple[int, int, int, int]] = [
    (255, 208, 150, 255), (255, 176, 186, 255), (168, 216, 255, 255),
    (176, 234, 194, 255), (255, 238, 156, 255), (212, 190, 255, 255),
    (255, 196, 168, 255), (176, 226, 218, 255),
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


def scribble_fill(
    canvas: Image.Image, outline: list[tuple[float, float]],
    color: tuple[int, int, int, int], rng: random.Random, spill: float = 7.0,
) -> None:
    """윤곽선에서 어긋난 문지르기로 채색한다.

    색칠 영역을 통째로 밀어두기 때문에 한쪽은 선 밖으로 삐져나가고 반대쪽은
    안쪽이 하얗게 빈다. 획마다 굵기와 각도를 바꿔 빗금 패턴처럼 규칙적으로
    보이지 않게 한다. 그라데이션은 쓰지 않는다.
    """
    if len(outline) < 3:
        return

    size = canvas.size
    ox, oy = rng.uniform(-spill, spill), rng.uniform(-spill, spill)
    shifted = [(x + ox, y + oy) for x, y in outline]

    region = _polygon_mask(size, shifted)

    strokes = Image.new("L", size, 0)
    sdraw = ImageDraw.Draw(strokes)

    xs = [p[0] for p in shifted]
    ys = [p[1] for p in shifted]
    x0, x1 = min(xs) - 30, max(xs) + 30
    y0, y1 = min(ys) - 30, max(ys) + 30
    height = y1 - y0

    # 기울기는 fill 하나당 한 번만 정한다. 획마다 바꾸면 선이 부채꼴로 벌어져
    # 커다란 흰 쐐기가 생기고, 문지른 게 아니라 빗금무늬처럼 보인다.
    skew = height * math.tan(rng.choice([-1, 1]) * rng.uniform(0.30, 0.65))

    x = x0 - abs(skew)
    while x < x1 + abs(skew):
        step = rng.uniform(10.0, 15.0)
        # 획을 간격보다 굵게 그어 대부분 겹치게 하고, 가끔만 틈이 벌어지게 한다
        stroke_w = int(step * rng.uniform(1.3, 2.1))
        if rng.random() > 0.08:
            sdraw.line(
                [(x + rng.uniform(-4, 4), y0), (x + skew + rng.uniform(-4, 4), y1)],
                fill=255, width=stroke_w,
            )
        x += step

    canvas.paste(color, (0, 0), ImageChops.multiply(strokes, region))

    # 경계 밖으로 튀어나간 몇 획 — 마스크를 거치지 않아 확실히 삐져나간다
    overshoot = Image.new("L", size, 0)
    odraw = ImageDraw.Draw(overshoot)
    for _ in range(rng.randint(2, 4)):
        px, py = rng.choice(outline)
        ang = rng.uniform(0, math.tau)
        length = spill * rng.uniform(1.4, 3.0)
        odraw.line(
            [(px, py), (px + math.cos(ang) * length, py + math.sin(ang) * length)],
            fill=255, width=int(spill * rng.uniform(1.0, 1.8)),
        )
    canvas.paste(color, (0, 0), overshoot)


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

def _draw_eyes(draw, rng, lx, rx_, ey, base_r, kind: str, lw: int) -> None:
    """짝눈이 이 화풍의 핵심 매력 포인트라 좌우를 반드시 다르게 그린다."""
    l_r = base_r * rng.uniform(0.75, 0.95)
    r_r = base_r * rng.uniform(1.05, 1.30)
    l_y = ey + rng.uniform(-base_r * 0.45, base_r * 0.25)
    r_y = ey + rng.uniform(-base_r * 0.25, base_r * 0.45)

    if kind == "closed_happy":  # ^ ^
        pen_stroke(draw, _arc_points(lx, l_y + l_r * 0.7, l_r * 1.25, l_r * 1.1, 200, 340), rng, lw, 2)
        pen_stroke(draw, _arc_points(rx_, r_y + r_r * 0.7, r_r * 1.25, r_r * 1.1, 200, 340), rng, lw, 2)
    elif kind == "closed_flat":  # - -
        pen_stroke(draw, [(lx - l_r * 1.2, l_y), (lx + l_r * 1.2, l_y)], rng, lw, 2)
        pen_stroke(draw, [(rx_ - r_r * 1.2, r_y), (rx_ + r_r * 1.2, r_y)], rng, lw, 2)
    elif kind == "wide":
        pen_stroke(draw, wobbly_ellipse(lx, l_y, l_r * 1.5, l_r * 1.7, rng, 48, 0.1), rng, lw, 2)
        pen_stroke(draw, wobbly_ellipse(rx_, r_y, r_r * 1.5, r_r * 1.7, rng, 48, 0.1), rng, lw, 2)
        _dot(draw, lx, l_y, l_r * 0.8)
        _dot(draw, rx_, r_y, r_r * 0.8)
    elif kind == "half":
        pen_stroke(draw, _arc_points(lx, l_y, l_r * 1.2, l_r, 180, 360), rng, lw, 2)
        pen_stroke(draw, _arc_points(rx_, r_y, r_r * 1.2, r_r, 180, 360), rng, lw, 2)
        _dot(draw, lx, l_y - l_r * 0.1, l_r * 0.65)
        _dot(draw, rx_, r_y - r_r * 0.1, r_r * 0.65)
    elif kind == "side":
        _dot(draw, lx + l_r * 0.8, l_y, l_r)
        _dot(draw, rx_ + r_r * 0.8, r_y, r_r)
    else:  # dots
        _dot(draw, lx, l_y, l_r)
        _dot(draw, rx_, r_y, r_r)


def _draw_mouth(draw, rng, cx, cy, w, kind: str, lw: int) -> None:
    if kind == "big_smile":
        pen_stroke(draw, _arc_points(cx, cy - w * 0.3, w * 0.75, w * 0.8, 15, 165), rng, lw, 2)
    elif kind == "smile":
        pen_stroke(draw, _arc_points(cx, cy - w * 0.12, w * 0.5, w * 0.42, 25, 155), rng, lw, 2)
    elif kind == "frown":
        pen_stroke(draw, _arc_points(cx, cy + w * 0.45, w * 0.5, w * 0.42, 205, 335), rng, lw, 2)
    elif kind == "flat":
        pen_stroke(draw, [(cx - w * 0.35, cy), (cx + w * 0.35, cy + rng.uniform(-3, 3))], rng, lw, 2)
    elif kind == "o":
        pen_stroke(draw, wobbly_ellipse(cx, cy, w * 0.28, w * 0.4, rng, 40, 0.14), rng, lw, 2)
    elif kind == "wavy":
        pts = [
            (cx - w * 0.42 + w * 0.84 * (i / 24), cy + math.sin((i / 24) * math.tau * 1.6) * w * 0.22)
            for i in range(25)
        ]
        pen_stroke(draw, pts, rng, lw, 2)
    elif kind == "cat":  # ω
        pen_stroke(draw, _arc_points(cx - w * 0.22, cy, w * 0.24, w * 0.28, 0, 175), rng, lw, 2)
        pen_stroke(draw, _arc_points(cx + w * 0.22, cy, w * 0.24, w * 0.28, 5, 180), rng, lw, 2)


_POSE_ANGLES = {
    "up": (-128, -52), "down": (152, 28), "out": (178, 2),
    "hug": (128, 52), "cross": (118, 62), "hip": (146, 34),
    "wave": (-118, 22), "fist": (-104, 30), "belly": (112, 68),
}


def _draw_limbs(canvas, draw, rng, body, cx, cy, rx, ry, pose: str, lw: int,
                fill_color, limb_delta: float = 0.0) -> None:
    """팔다리는 몸통 윤곽선에서 출발해 바깥으로만 뻗는다 (몸을 뚫지 않게)."""
    left_deg, right_deg = _POSE_ANGLES.get(pose, _POSE_ANGLES["down"])
    left_deg -= limb_delta
    right_deg += limb_delta

    def paw(px, py, r):
        """손/발 끝의 동그란 뭉치. 이게 없으면 팔다리가 그냥 뻗은 선으로 보인다."""
        blob = wobbly_ellipse(px, py, r, r * rng.uniform(0.85, 1.1), rng, 26, 0.16)
        canvas.paste(fill_color, (0, 0), _polygon_mask(canvas.size, blob))
        pen_stroke(draw, blob, rng, lw, 2, drift=1.5)

    for angle_deg, length in (
        (left_deg, rx * rng.uniform(0.48, 0.70)),
        (right_deg, rx * rng.uniform(0.48, 0.70)),
    ):
        a = math.radians(angle_deg)
        # 팔이 위로 갈 땐 어깨 쪽, 아래로 갈 땐 옆구리 아래쪽에서 나와야
        # 몸에서 뻗어나온 것처럼 보인다
        left_side = math.cos(a) < 0
        lift = -1 if math.sin(a) < 0 else 1
        attach = (180 + lift * 22) if left_side else (0 - lift * 22)
        x0, y0 = _point_on(body, cx, cy, attach + rng.uniform(-8, 8))

        mid = (x0 + math.cos(a) * length * 0.55 + rng.uniform(-6, 6),
               y0 + math.sin(a) * length * 0.55 + rng.uniform(-6, 6))
        end = (x0 + math.cos(a) * length, y0 + math.sin(a) * length)
        pen_stroke(draw, [(x0, y0), mid, end], rng, lw, 2)
        paw(end[0], end[1], rx * rng.uniform(0.085, 0.115))

    # 다리 — 길이를 확실히 다르게
    for sx in (-1, 1):
        x0, y0 = _point_on(body, cx, cy, 90 + sx * rng.uniform(14, 30))
        leg = ry * rng.uniform(0.26, 0.42)
        knee = (x0 + rng.uniform(-6, 6), y0 + leg * 0.55)
        foot = (x0 + sx * rng.uniform(4, 16), y0 + leg)
        pen_stroke(draw, [(x0, y0), knee, foot], rng, lw, 2)
        paw(foot[0], foot[1], rx * rng.uniform(0.085, 0.115))


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
            ey = cy - ry * rng.uniform(0.72, 0.84)
            shapes.append(wobbly_ellipse(ex, ey, rx * 0.28 * wiggle, rx * 0.27 * wiggle, rng, 40, 0.13))
        elif kind == "tiny":      # 햄스터 — 작고 동그란 귀
            ex = cx + sx * rx * rng.uniform(0.55, 0.66)
            ey = cy - ry * rng.uniform(0.66, 0.76)
            shapes.append(wobbly_ellipse(ex, ey, rx * 0.17 * wiggle, rx * 0.17 * wiggle, rng, 36, 0.14))
        elif kind == "long":      # 토끼 — 길쭉한 귀, 살짝 벌어지게
            ex = cx + sx * rx * rng.uniform(0.26, 0.38)
            ey = cy - ry * rng.uniform(1.02, 1.18)
            tilt = sx * rng.uniform(0.12, 0.30)
            shapes.append(wobbly_ellipse(ex, ey, rx * 0.16 * wiggle, ry * 0.42 * wiggle,
                                         rng, 48, 0.10, tilt=tilt))
        elif kind == "pointy":    # 고양이 — 삼각 귀. 밑동이 머리 안에 묻히게 낮춘다
            ex = cx + sx * rx * rng.uniform(0.44, 0.54)
            ey = cy - ry * rng.uniform(0.50, 0.60)
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
        draw.polygon(blob, fill=INK)
        pen_stroke(draw, blob, rng, max(2, lw - 1), 1)
    elif kind == "triangle":
        s = rx * 0.085
        tri = _roughen([
            (cx - s, cy - s * 0.55), (cx + s, cy - s * 0.55), (cx, cy + s * 0.8),
            (cx - s, cy - s * 0.55),
        ], rng, rx * 0.014)
        draw.polygon(tri, fill=INK)
        pen_stroke(draw, tri, rng, max(2, lw - 1), 1)


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
            pen_stroke(draw, [(x0, y), (x1, y + rng.uniform(-8, 8))], rng, max(2, lw - 1), 1)


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
        pen_stroke(draw, rect, rng, max(2, lw - 1), 1)


def _draw_tail(draw, rng, body, cx, cy, rx, ry, kind: str, lw: int) -> None:
    if kind == "none":
        return
    base = _point_on(body, cx, cy, rng.uniform(28, 48))
    if kind == "stub":
        pen_stroke(draw, wobbly_ellipse(base[0] + rx * 0.10, base[1] + ry * 0.04,
                                        rx * 0.13, rx * 0.12, rng, 28, 0.16), rng, lw, 2)
    elif kind == "curl":
        pts = _arc_points(base[0] + rx * 0.16, base[1] - ry * 0.02, rx * 0.18, ry * 0.20, 120, -80, 20)
        pen_stroke(draw, _roughen(pts, rng, rx * 0.02), rng, lw, 2)


def _draw_extras(draw, rng, cx, cy, rx, ry, extras: list[str], lw: int) -> None:
    for extra in extras:
        if extra == "heart":
            hx, hy = cx + rx * rng.uniform(0.80, 1.05), cy - ry * rng.uniform(0.95, 1.20)
            heart = _heart_points(hx, hy, rx * rng.uniform(0.34, 0.44))
            pen_stroke(draw, _roughen(heart, rng, rx * 0.035), rng, lw, 2)
        elif extra == "tear":
            tx = cx - rx * rng.uniform(0.48, 0.60)
            ty = cy + ry * rng.uniform(0.04, 0.18)
            drop = _drop_points(tx, ty, rx * 0.19, rx * 0.34)
            pen_stroke(draw, _roughen(drop, rng, rx * 0.022), rng, lw, 2)
        elif extra == "sweat":
            sx_, sy_ = cx + rx * rng.uniform(0.72, 0.90), cy - ry * rng.uniform(0.42, 0.60)
            drop = _drop_points(sx_, sy_, rx * 0.20, rx * 0.36)
            pen_stroke(draw, _roughen(drop, rng, rx * 0.022), rng, lw, 2)
        elif extra == "blush":
            for sx in (-1, 1):
                bx = cx + sx * rx * rng.uniform(0.50, 0.64)
                by = cy + ry * rng.uniform(0.04, 0.16)
                for i in range(3):
                    yy = by + (i - 1) * rx * 0.075
                    pen_stroke(draw, [(bx - rx * 0.105, yy), (bx + rx * 0.105, yy)], rng,
                               max(2, lw - 1), 1, color=(232, 132, 145, 255), drift=1.2)
        elif extra == "sparkle":
            for _ in range(3):
                px = cx + rng.uniform(-rx * 1.3, rx * 1.3)
                py = cy - ry * rng.uniform(0.70, 1.25)
                s = rx * rng.uniform(0.08, 0.13)
                pen_stroke(draw, [(px - s, py), (px + s, py)], rng, lw, 1)
                pen_stroke(draw, [(px, py - s), (px, py + s)], rng, lw, 1)
        elif extra == "anger":
            ax_, ay_ = cx + rx * rng.uniform(0.55, 0.70), cy - ry * rng.uniform(0.55, 0.70)
            s = rx * 0.15
            pen_stroke(draw, [(ax_ - s, ay_ - s), (ax_ + s, ay_ + s)], rng, lw, 1)
            pen_stroke(draw, [(ax_ + s, ay_ - s), (ax_ - s, ay_ + s)], rng, lw, 1)
        elif extra == "brows":
            for sx, tilt in ((-1, 1), (1, -1)):
                bx = cx + sx * rx * 0.36
                by = cy - ry * rng.uniform(0.40, 0.48)
                pen_stroke(draw, [(bx - rx * 0.15, by - tilt * rx * 0.08),
                                  (bx + rx * 0.15, by + tilt * rx * 0.08)], rng, lw, 2)
        elif extra == "zzz":  # 글자 대신 동그란 숨소리 방울
            bx, by = cx + rx * 0.85, cy - ry * 0.80
            for i in range(3):
                r = rx * (0.045 + i * 0.035)
                pen_stroke(draw, wobbly_ellipse(bx + i * rx * 0.22, by - i * ry * 0.17,
                                                r, r, rng, 24, 0.16), rng, lw, 1)


# --------------------------------------------------------------------------
# 감정 → 표정 조합
# --------------------------------------------------------------------------

EXPRESSIONS: dict[str, dict] = {
    "안녕":     {"eyes": "dots", "mouth": "smile", "pose": "wave"},
    "반가워":   {"eyes": "closed_happy", "mouth": "big_smile", "pose": "wave"},
    "기쁨":     {"eyes": "closed_happy", "mouth": "big_smile", "pose": "up", "extras": ["sparkle"]},
    "슬픔":     {"eyes": "half", "mouth": "frown", "pose": "down", "extras": ["tear"]},
    "화남":     {"eyes": "dots", "mouth": "wavy", "pose": "hip", "extras": ["anger", "brows"]},
    "놀람":     {"eyes": "wide", "mouth": "o", "pose": "out"},
    "사랑해":   {"eyes": "closed_happy", "mouth": "cat", "pose": "hug", "extras": ["heart", "blush"]},
    "고마워":   {"eyes": "closed_happy", "mouth": "smile", "pose": "hug"},
    "미안해":   {"eyes": "half", "mouth": "frown", "pose": "down"},
    "축하해":   {"eyes": "closed_happy", "mouth": "big_smile", "pose": "up", "extras": ["sparkle"]},
    "화이팅":   {"eyes": "dots", "mouth": "big_smile", "pose": "fist"},
    "웃김":     {"eyes": "closed_happy", "mouth": "big_smile", "pose": "belly", "extras": ["tear"]},
    "심심함":   {"eyes": "half", "mouth": "flat", "pose": "down"},
    "졸림":     {"eyes": "closed_flat", "mouth": "o", "pose": "down", "extras": ["zzz"]},
    "배고픔":   {"eyes": "half", "mouth": "wavy", "pose": "belly"},
    "당황":     {"eyes": "wide", "mouth": "o", "pose": "out", "extras": ["sweat"]},
    "부끄러움": {"eyes": "closed_happy", "mouth": "smile", "pose": "hug", "extras": ["blush"]},
    "자신감":   {"eyes": "dots", "mouth": "smile", "pose": "hip", "extras": ["sparkle"]},
    "실망":     {"eyes": "half", "mouth": "frown", "pose": "down"},
    "긴장":     {"eyes": "wide", "mouth": "wavy", "pose": "cross", "extras": ["sweat"]},
    "감동":     {"eyes": "closed_happy", "mouth": "smile", "pose": "hug", "extras": ["tear"]},
    "궁금함":   {"eyes": "dots", "mouth": "flat", "pose": "hip"},
    "지침":     {"eyes": "closed_flat", "mouth": "frown", "pose": "down", "extras": ["sweat"]},
    "설렘":     {"eyes": "closed_happy", "mouth": "cat", "pose": "hug", "extras": ["heart", "blush"]},
    "만족":     {"eyes": "closed_happy", "mouth": "cat", "pose": "hip"},
    "거절":     {"eyes": "dots", "mouth": "flat", "pose": "cross"},
    "수긍":     {"eyes": "closed_flat", "mouth": "smile", "pose": "down"},
    "눈치보기": {"eyes": "side", "mouth": "flat", "pose": "cross"},
    "신남":     {"eyes": "closed_happy", "mouth": "big_smile", "pose": "up", "extras": ["sparkle"]},
    "멍때림":   {"eyes": "dots", "mouth": "o", "pose": "down"},
    "삐짐":     {"eyes": "closed_flat", "mouth": "frown", "pose": "cross", "extras": ["blush"]},
    "잘자":     {"eyes": "closed_flat", "mouth": "smile", "pose": "down", "extras": ["zzz"]},
}

_EYE_KINDS = ["dots", "closed_happy", "closed_flat", "wide", "half", "side"]
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
    color=(255, 208, 150, 255), animal="bear", rx_ratio=0.27, ry_ratio=0.27,
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
    cy = S * 0.52 + rng.uniform(-S * 0.012, S * 0.012)
    rx = S * spec_char.rx_ratio
    ry = S * spec_char.ry_ratio
    tilt = rng.uniform(-0.12, 0.12)

    # 모션은 난수를 뽑은 *뒤에* 더한다. 순서를 바꾸면 프레임마다 rng 소비가
    # 달라져 선이 통째로 다시 그려지고 화면이 지글거린다.
    cy += ry * move.dy
    tilt += move.tilt
    rx *= 1.0 + move.squash * 0.5
    ry *= 1.0 - move.squash

    body = wobbly_ellipse(cx, cy, rx, ry, rng, 96, rng.uniform(0.05, 0.09),
                          gap=rng.uniform(0.015, 0.05), tilt=tilt, bulge=spec_char.bulge)
    ears = _ear_shapes(rng, cx, cy, rx, ry, spec_char.ear)

    # 귀 → 몸통 순서로 칠해야 몸통이 귀 밑동을 덮어 자연스럽게 이어진다
    for ear in ears:
        scribble_fill(canvas, ear, spec_char.color, rng, spill=S * 0.010)
    scribble_fill(canvas, body, spec_char.color, rng, spill=S * 0.022)

    for ear in ears:
        pen_stroke(draw, ear, rng, lw, 2, drift=S * 0.003)
    _draw_tail(draw, rng, body, cx, cy, rx, ry, spec_char.tail, lw)
    _draw_limbs(canvas, draw, rng, body, cx, cy, rx, ry,
                face.get("pose", "down"), lw, spec_char.color, move.limb)

    # 채색 위에 잉크 선 — 선이 살아있으면서 색은 삐져나간다
    pen_stroke(draw, body, rng, lw, passes=rng.choice([2, 3]), drift=S * 0.004)

    # 볼주머니 (햄스터) — 몸통 선 위에 얹어 실루엣이 옆으로 부풀게
    if spec_char.cheeks:
        for sx in (-1, 1):
            px = cx + sx * rx * rng.uniform(0.48, 0.58)
            py = cy + ry * rng.uniform(0.30, 0.40)
            prx, pry = rx * rng.uniform(0.34, 0.40), rx * rng.uniform(0.27, 0.32)

            scribble_fill(canvas, wobbly_ellipse(px, py, prx, pry, rng, 40, 0.12),
                          spec_char.color, rng, spill=S * 0.007)
            # 바깥쪽 호만 긋는다. 원을 통째로 그리면 얼굴에 원 두 개를 붙인
            # 꼴이 되고, 볼주머니는 실루엣이 부풀어 보여야 한다.
            start, end = (90, 270) if sx < 0 else (-90, 90)
            arc = _arc_points(px, py, prx, pry, start, end, 30)
            pen_stroke(draw, _roughen(arc, rng, rx * 0.022), rng, lw, 2, drift=S * 0.003)

    # 얼굴 배치 — 주둥이가 있으면 이목구비를 살짝 위로 올려 자리를 만든다
    eye_y = cy - ry * rng.uniform(0.14, 0.24)
    muzzle_y = cy + ry * rng.uniform(0.20, 0.30)
    mouth_y = muzzle_y + (rx * 0.06 if spec_char.muzzle else 0)

    if spec_char.muzzle:
        snout = wobbly_ellipse(cx + rng.uniform(-rx * 0.04, rx * 0.04), muzzle_y,
                               rx * 0.34, rx * 0.25, rng, 44, 0.12)
        scribble_fill(canvas, snout, _lighten(spec_char.color, 0.55), rng, spill=S * 0.006)

    eye_dx = rx * spec_char.eye_spread
    _draw_eyes(draw, rng,
               cx - eye_dx * rng.uniform(0.92, 1.08),
               cx + eye_dx * rng.uniform(0.92, 1.08),
               eye_y, S * 0.021 * spec_char.eye_scale, face.get("eyes", "dots"), lw)

    if spec_char.nose == "beak":
        # 부리가 입을 겸하므로 별도 입은 그리지 않는다
        _draw_beak(draw, rng, cx, muzzle_y, rx, lw)
    else:
        nose_y = muzzle_y - rx * 0.12
        _draw_nose(draw, rng, cx, nose_y, rx, spec_char.nose, lw)
        if spec_char.whiskers:
            _draw_whiskers(draw, rng, cx, nose_y, rx, lw)
        _draw_mouth(draw, rng, cx + rng.uniform(-rx * 0.05, rx * 0.05),
                    mouth_y, rx * 0.40, face.get("mouth", "smile"), lw)
        if spec_char.teeth:
            _draw_teeth(draw, rng, cx, mouth_y + rx * 0.06, rx, lw)

    _draw_extras(draw, rng, cx, cy, rx, ry, face.get("extras", []), lw)

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
