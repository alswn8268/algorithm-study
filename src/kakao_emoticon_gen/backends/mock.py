"""GPU/API 없이 파이프라인을 테스트하기 위한 플레이스홀더 생성기.

실제 AI 이미지 대신, 키워드를 해시해 색상/표정을 결정론적으로 바꿔가며
간단한 '얼굴' 도형을 그린다. 배경 제거/리사이즈/규격 검증/CLI 등 나머지
파이프라인을 GPU나 API 키 없이 검증할 때 사용한다.
"""
from __future__ import annotations

import hashlib

from PIL import Image, ImageDraw

from .base import ImageGenerator

_PALETTE = [
    (255, 214, 165), (255, 179, 186), (186, 225, 255),
    (186, 255, 201), (255, 255, 186), (223, 186, 255),
]


def _seed_from(prompt: str, seed: int | None) -> int:
    if seed is not None:
        return seed
    digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


class MockGenerator(ImageGenerator):
    def generate(
        self,
        prompt: str,
        negative_prompt: str | None = None,
        seed: int | None = None,
        size: int = 512,
    ) -> Image.Image:
        s = _seed_from(prompt, seed)
        face_color = _PALETTE[s % len(_PALETTE)]
        mood_up = (s // len(_PALETTE)) % 2 == 0  # 웃는 표정 vs 놀란 표정 토글

        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        margin = int(size * 0.12)
        draw.ellipse(
            [margin, margin, size - margin, size - margin],
            fill=(*face_color, 255),
            outline=(40, 40, 40, 255),
            width=max(2, size // 60),
        )

        eye_r = size // 22
        eye_y = size // 2 - size // 10
        for cx in (size // 2 - size // 6, size // 2 + size // 6):
            draw.ellipse(
                [cx - eye_r, eye_y - eye_r, cx + eye_r, eye_y + eye_r],
                fill=(40, 40, 40, 255),
            )

        mouth_y = size // 2 + size // 8
        mouth_w = size // 6
        if mood_up:
            draw.arc(
                [size // 2 - mouth_w, mouth_y - mouth_w // 2, size // 2 + mouth_w, mouth_y + mouth_w // 2],
                start=20, end=160, fill=(40, 40, 40, 255), width=max(2, size // 80),
            )
        else:
            draw.ellipse(
                [size // 2 - mouth_w // 3, mouth_y, size // 2 + mouth_w // 3, mouth_y + mouth_w // 2],
                fill=(40, 40, 40, 255),
            )

        return img
