"""이미지 생성 백엔드 공통 인터페이스."""
from __future__ import annotations

from abc import ABC, abstractmethod

from PIL import Image


class ImageGenerator(ABC):
    """모든 백엔드(mock/dalle/stable_diffusion)가 구현해야 하는 인터페이스."""

    @abstractmethod
    def generate(
        self,
        prompt: str,
        negative_prompt: str | None = None,
        seed: int | None = None,
        size: int = 512,
    ) -> Image.Image:
        """프롬프트로부터 정사각형 RGBA(또는 RGB) PIL 이미지를 생성한다."""
        raise NotImplementedError
