"""OpenAI Images API(DALL·E) 백엔드.

사용하려면 `pip install openai` 및 `OPENAI_API_KEY` 환경변수가 필요하다.
"""
from __future__ import annotations

import base64
import io

from PIL import Image

from .base import ImageGenerator

_ALLOWED_SIZES = {256, 512, 1024}


class DalleGenerator(ImageGenerator):
    def __init__(self, api_key: str | None = None, model: str = "dall-e-3"):
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ImportError(
                "backend 'dalle' requires the 'openai' package. install it with:\n"
                "    pip install openai"
            ) from exc

        if not api_key:
            import os

            api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY is not set (env var or --api-key)")

        self._client = OpenAI(api_key=api_key)
        self._model = model

    def generate(
        self,
        prompt: str,
        negative_prompt: str | None = None,
        seed: int | None = None,
        size: int = 1024,
    ) -> Image.Image:
        # DALL·E API는 네거티브 프롬프트/시드를 지원하지 않으므로 프롬프트에 병합한다.
        full_prompt = prompt
        if negative_prompt:
            full_prompt += f". Avoid: {negative_prompt}"

        api_size = min(_ALLOWED_SIZES, key=lambda s: abs(s - size))
        response = self._client.images.generate(
            model=self._model,
            prompt=full_prompt,
            size=f"{api_size}x{api_size}",
            n=1,
            response_format="b64_json",
        )
        image_b64 = response.data[0].b64_json
        raw = base64.b64decode(image_b64)
        return Image.open(io.BytesIO(raw)).convert("RGBA")
