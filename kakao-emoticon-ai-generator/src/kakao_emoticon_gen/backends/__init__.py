"""이미지 생성 백엔드 (mock / dalle / stable_diffusion)."""
from __future__ import annotations

from .base import ImageGenerator


def get_backend(name: str, **kwargs) -> ImageGenerator:
    """이름으로 백엔드 인스턴스를 생성한다. 무거운 의존성은 각 백엔드
    내부에서 지연 임포트하므로, 실제로 사용하지 않는 백엔드의 패키지는
    설치할 필요가 없다."""
    if name == "mock":
        from .mock import MockGenerator

        return MockGenerator(**kwargs)
    if name == "dalle":
        from .dalle import DalleGenerator

        return DalleGenerator(**kwargs)
    if name == "stable_diffusion":
        from .stable_diffusion import StableDiffusionGenerator

        return StableDiffusionGenerator(**kwargs)
    raise ValueError(f"unknown backend '{name}'. choose from: mock, dalle, stable_diffusion")
