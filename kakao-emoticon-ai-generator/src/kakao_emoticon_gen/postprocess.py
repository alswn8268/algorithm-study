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


def resize_canvas(image: Image.Image, target: int = 360, padding_ratio: float = 0.06) -> Image.Image:
    """이미지를 비율을 유지한 채 정사각형 `target x target` 캔버스에 맞춘다.

    카카오 심사 시 캐릭터가 캔버스 가장자리에 딱 붙어있으면 감점 요인이
    될 수 있어, 기본적으로 여백(`padding_ratio`)을 둔다.
    """
    rgba = image.convert("RGBA")
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
