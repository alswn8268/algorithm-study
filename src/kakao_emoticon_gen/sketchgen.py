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
    rx_ratio: float = 0.27       # 몸통 가로 반지름
    ry_ratio: float = 0.27       # 몸통 세로 반지름
    bulge: float = 0.0           # 아래쪽이 불룩한 정도 (서양배 모양)
    eye_scale: float = 1.0
    eye_spread: float = 0.39     # 두 눈 사이 거리
    tuft: str = "none"           # none | sprout | ears | cowlick
    name: str = "character"


TUFTS = ["none", "sprout", "ears", "cowlick"]


def make_character(seed: int, name: str | None = None) -> CharacterSpec:
    """seed 하나로 캐릭터 디자인을 결정론적으로 뽑는다."""
    rng = random.Random(seed)
    return CharacterSpec(
        color=rng.choice(PALETTE),
        rx_ratio=rng.uniform(0.230, 0.300),
        ry_ratio=rng.uniform(0.230, 0.305),
        bulge=rng.choice([0.0, 0.12, 0.22, 0.30]),
        eye_scale=rng.uniform(0.9, 1.35),
        eye_spread=rng.uniform(0.33, 0.46),
        tuft=rng.choice(TUFTS),
        name=name or f"char{seed}",
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

    region = Image.new("L", size, 0)
    ImageDraw.Draw(region).polygon(shifted, fill=255)

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


def _draw_limbs(draw, rng, body, cx, cy, rx, ry, pose: str, lw: int) -> None:
    """팔다리는 몸통 윤곽선에서 출발해 바깥으로만 뻗는다 (몸을 뚫지 않게)."""
    left_deg, right_deg = _POSE_ANGLES.get(pose, _POSE_ANGLES["down"])

    for angle_deg, length in (
        (left_deg, rx * rng.uniform(0.52, 0.78)),
        (right_deg, rx * rng.uniform(0.52, 0.78)),
    ):
        # 부착점은 몸통 옆구리, 뻗는 방향은 포즈가 정한다
        side = 180 if math.cos(math.radians(angle_deg)) < 0 else 0
        x0, y0 = _point_on(body, cx, cy, side + rng.uniform(-14, 14))
        a = math.radians(angle_deg)
        mid = (x0 + math.cos(a) * length * 0.55 + rng.uniform(-6, 6),
               y0 + math.sin(a) * length * 0.55 + rng.uniform(-6, 6))
        end = (x0 + math.cos(a) * length, y0 + math.sin(a) * length)
        pen_stroke(draw, [(x0, y0), mid, end], rng, lw, 2)

    # 다리 — 길이를 확실히 다르게
    for sx in (-1, 1):
        x0, y0 = _point_on(body, cx, cy, 90 + sx * rng.uniform(14, 30))
        leg = ry * rng.uniform(0.30, 0.48)
        knee = (x0 + rng.uniform(-6, 6), y0 + leg * 0.55)
        foot = (x0 + sx * rng.uniform(4, 18), y0 + leg)
        pen_stroke(draw, [(x0, y0), knee, foot], rng, lw, 2)


def _draw_tuft(draw, rng, body, cx, cy, rx, ry, kind: str, lw: int) -> None:
    """머리 위 장식 — 캐릭터 정체성이라 세트 내내 같아야 한다."""
    if kind == "none":
        return
    top = _point_on(body, cx, cy, -90 + rng.uniform(-8, 8))

    if kind == "sprout":
        tip = (top[0] + rng.uniform(-6, 6), top[1] - ry * 0.30)
        pen_stroke(draw, [top, tip], rng, lw, 2)
        pen_stroke(draw, wobbly_ellipse(tip[0] + rx * 0.10, tip[1] - ry * 0.03,
                                        rx * 0.13, rx * 0.09, rng, 32, 0.16), rng, lw, 2)
    elif kind == "ears":
        for sx in (-1, 1):
            ex = top[0] + sx * rx * rng.uniform(0.40, 0.52)
            ey = top[1] + ry * rng.uniform(0.06, 0.16)
            pen_stroke(draw, _arc_points(ex, ey, rx * 0.19, ry * 0.21, 165, 375), rng, lw, 2)
    elif kind == "cowlick":
        for i in range(3):
            bx = top[0] + (i - 1) * rx * 0.16 + rng.uniform(-4, 4)
            pen_stroke(draw, [(bx, top[1] + 4),
                              (bx + rng.uniform(-8, 8), top[1] - ry * rng.uniform(0.12, 0.20))],
                       rng, lw, 2)


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

DEFAULT_CHARACTER = CharacterSpec(
    color=(255, 208, 150, 255), rx_ratio=0.27, ry_ratio=0.27,
    bulge=0.10, eye_scale=1.1, eye_spread=0.39, tuft="sprout", name="default",
)


def render_character(
    keyword: str, size: int = 360, seed: int | None = None,
    character: CharacterSpec | None = None,
) -> Image.Image:
    """감정 키워드 하나를 발그림 캐릭터 한 컷으로 그린다.

    `character`가 같으면 같은 캐릭터, `seed`가 다르면 손떨림만 달라진다.
    """
    spec_char = character or DEFAULT_CHARACTER
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

    body = wobbly_ellipse(cx, cy, rx, ry, rng, 96, rng.uniform(0.05, 0.09),
                          gap=rng.uniform(0.015, 0.05), tilt=tilt, bulge=spec_char.bulge)

    # 채색을 먼저, 그 위에 잉크 선 — 그래야 선이 살아있으면서 색은 삐져나간다
    scribble_fill(canvas, body, spec_char.color, rng, spill=S * 0.022)
    _draw_limbs(draw, rng, body, cx, cy, rx, ry, face.get("pose", "down"), lw)
    _draw_tuft(draw, rng, body, cx, cy, rx, ry, spec_char.tuft, lw)
    pen_stroke(draw, body, rng, lw, passes=rng.choice([2, 3]), drift=S * 0.004)

    # 얼굴
    eye_y = cy - ry * rng.uniform(0.14, 0.24)
    eye_dx = rx * spec_char.eye_spread
    _draw_eyes(draw, rng,
               cx - eye_dx * rng.uniform(0.92, 1.08),
               cx + eye_dx * rng.uniform(0.92, 1.08),
               eye_y, S * 0.021 * spec_char.eye_scale, face.get("eyes", "dots"), lw)
    _draw_mouth(draw, rng, cx + rng.uniform(-rx * 0.07, rx * 0.07),
                cy + ry * rng.uniform(0.18, 0.30), rx * 0.44,
                face.get("mouth", "smile"), lw)

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


def render_lineup(
    count: int = 8, keyword: str = "안녕", cell: int = 300, cols: int = 4,
    base_seed: int = 0, background: tuple[int, int, int, int] = (255, 255, 255, 255),
) -> tuple[Image.Image, list[CharacterSpec]]:
    """서로 다른 캐릭터 후보를 같은 표정으로 나란히 그려 디자인을 비교한다."""
    characters = [make_character(base_seed + i, name=f"후보{i + 1}") for i in range(count)]
    rows = math.ceil(count / cols)
    sheet = Image.new("RGBA", (cols * cell, rows * cell), background)
    for i, char in enumerate(characters):
        cut = render_character(keyword, cell, base_seed + i, char)
        sheet.alpha_composite(cut, ((i % cols) * cell, (i // cols) * cell))
    return sheet, characters
