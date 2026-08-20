"""후처리: 배경 제거, 정사각 캔버스 패딩/리사이즈, 투명 PNG 저장, GIF 인코딩."""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image


def remove_background(image: Image.Image, tolerance: int = 24) -> Image.Image:
    """배경을 제거해 알파 채널이 있는 이미지를 반환한다.

    `rembg`가 설치되어 있으면 딥러닝 기반 세그멘테이션을 사용하고,
    없으면 모서리 색상을 배경으로 간주하는 간이 컬러 키(color-key)
    알고리즘으로 대체한다 (플랫한 단색 배경에서 잘 동작, 사진처럼
    복잡한 배경에는 부적합 — 그 경우 rembg 설치를 권장).
    """
    try:
        from rembg import remove as rembg_remove  # type: ignore

        return rembg_remove(image.convert("RGBA"))
    except ImportError:
        return _colorkey_remove_background(image, tolerance=tolerance)


def _colorkey_remove_background(image: Image.Image, tolerance: int = 24) -> Image.Image:
    rgba = image.convert("RGBA")
    arr = np.array(rgba).astype(np.int16)

    corners = [arr[0, 0], arr[0, -1], arr[-1, 0], arr[-1, -1]]
    bg_color = np.mean(corners, axis=0)[:3]

    diff = np.abs(arr[:, :, :3] - bg_color).sum(axis=2)
    mask = diff <= tolerance

    out = arr.copy()
    out[mask, 3] = 0
    return Image.fromarray(out.astype(np.uint8), mode="RGBA")


def add_hand_jitter(
    image: Image.Image,
    strength: float = 1.5,
    cell: int = 32,
    seed: int | None = None,
) -> Image.Image:
    """저주파 랜덤 변위장을 적용해 선을 미세하게 흔들고 좌우 대칭을 깬다.

    AI가 뽑은 그림은 선 굵기가 균일하고 좌우가 지나치게 대칭이라 "AI 티"가
    난다. 이 함수는 이미지 전체를 부드럽게 일렁이게 만들어 그 균일함을
    깨뜨린다.

    ⚠️ 이것은 보조 수단일 뿐 트레이싱(직접 따라 그리기)의 대체재가 아니다.
    발그림 화풍의 본질인 "겹쳐 그은 획", "끝에서 안 만나는 선"은 픽셀 변형으로
    만들어낼 수 없다. 자세한 내용은 docs/STYLE_GUIDE.md 참고.

    Args:
        strength: 변위 크기(픽셀 표준편차). 0이면 원본을 그대로 반환한다.
        cell: 변위장의 대략적인 셀 크기. 클수록 완만하게 일렁인다.
        seed: 재현 가능한 결과를 원할 때 지정한다.
    """
    if strength <= 0:
        return image.convert("RGBA")

    rgba = image.convert("RGBA")
    arr = np.array(rgba)
    h, w = arr.shape[:2]

    rng = np.random.default_rng(seed)
    coarse_h = max(2, h // max(1, cell))
    coarse_w = max(2, w // max(1, cell))

    def _displacement_field() -> np.ndarray:
        coarse = rng.normal(0.0, strength, (coarse_h, coarse_w)).astype(np.float32)
        smoothed = Image.fromarray(coarse, mode="F").resize((w, h), Image.BICUBIC)
        return np.array(smoothed, dtype=np.float32)

    dx = _displacement_field()
    dy = _displacement_field()

    yy, xx = np.meshgrid(np.arange(h), np.arange(w), indexing="ij")
    src_x = np.clip(np.rint(xx + dx).astype(np.int64), 0, w - 1)
    src_y = np.clip(np.rint(yy + dy).astype(np.int64), 0, h - 1)

    return Image.fromarray(arr[src_y, src_x], mode="RGBA")


def resize_canvas(
    image: Image.Image,
    target: int = 360,
    padding_ratio: float = 0.06,
    fit: str = "content",
) -> Image.Image:
    """이미지를 비율을 유지한 채 정사각형 `target x target` 캔버스에 맞춘다.

    카카오 심사 시 캐릭터가 캔버스 가장자리에 딱 붙어있으면 감점 요인이
    될 수 있어, 기본적으로 여백(`padding_ratio`)을 둔다.

    `fit`:
      - "content": 컷마다 내용물 경계에 맞춰 꽉 차게 확대한다. 여백이 제각각인
        AI 생성 이미지를 정렬할 때 쓴다.
      - "canvas" : 원본 프레이밍을 그대로 두고 전체를 축소만 한다.
        **세트 전체의 캐릭터 크기를 일정하게 유지해야 할 때 반드시 이쪽을 쓴다.**
        "content"는 팔을 벌린 컷의 몸통을 작게 만들어 32컷 통일감을 깨뜨린다.
    """
    if fit not in ("content", "canvas"):
        raise ValueError(f"unknown fit '{fit}'. use 'content' or 'canvas'")

    rgba = image.convert("RGBA")

    if fit == "canvas":
        side = max(rgba.size)
        square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        square.paste(rgba, ((side - rgba.width) // 2, (side - rgba.height) // 2), rgba)
        return square.resize((target, target), Image.LANCZOS)

    content_box = rgba.getbbox()
    cropped = rgba.crop(content_box) if content_box else rgba

    usable = int(target * (1 - 2 * padding_ratio))
    usable = max(1, usable)

    w, h = cropped.size
    scale = usable / max(w, h)
    new_w, new_h = max(1, round(w * scale)), max(1, round(h * scale))
    resized = cropped.resize((new_w, new_h), Image.LANCZOS)

    canvas = Image.new("RGBA", (target, target), (0, 0, 0, 0))
    offset = ((target - new_w) // 2, (target - new_h) // 2)
    canvas.paste(resized, offset, resized)
    return canvas


def save_png(image: Image.Image, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.convert("RGBA").save(path, format="PNG", optimize=True)
    return path


def frames_to_gif(
    frames: list[Image.Image],
    path: str | Path,
    duration_ms: int = 120,
    loop: int = 0,
) -> Path:
    """움직이는 이모티콘용: 여러 프레임을 하나의 GIF로 합친다."""
    if not frames:
        raise ValueError("frames must not be empty")

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    converted = [f.convert("RGBA") for f in frames]
    converted[0].save(
        path,
        format="GIF",
        save_all=True,
        append_images=converted[1:],
        duration=duration_ms,
        loop=loop,
        disposal=2,
    )
    return path
