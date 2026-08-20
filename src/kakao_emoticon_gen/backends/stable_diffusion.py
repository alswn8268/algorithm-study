"""로컬 Stable Diffusion (huggingface diffusers) 백엔드.

사용하려면 `pip install torch diffusers accelerate`가 필요하고,
GPU(CUDA/MPS)가 있으면 훨씬 빠르다. CPU에서도 동작은 하지만 느리다.
모델은 최초 호출 시 huggingface hub에서 다운로드되어 캐시된다.
"""
from __future__ import annotations

from PIL import Image

from .base import ImageGenerator


class StableDiffusionGenerator(ImageGenerator):
    def __init__(
        self,
        model_id: str = "runwayml/stable-diffusion-v1-5",
        device: str = "cpu",
        num_inference_steps: int = 30,
        guidance_scale: float = 7.5,
    ):
        try:
            import torch
            from diffusers import StableDiffusionPipeline
        except ImportError as exc:
            raise ImportError(
                "backend 'stable_diffusion' requires torch + diffusers. install with:\n"
                "    pip install torch diffusers accelerate"
            ) from exc

        dtype = torch.float16 if device in ("cuda", "mps") else torch.float32
        self._pipe = StableDiffusionPipeline.from_pretrained(model_id, torch_dtype=dtype)
        self._pipe = self._pipe.to(device)
        self._torch = torch
        self._device = device
        self._num_inference_steps = num_inference_steps
        self._guidance_scale = guidance_scale

    def generate(
        self,
        prompt: str,
        negative_prompt: str | None = None,
        seed: int | None = None,
        size: int = 512,
    ) -> Image.Image:
        generator = None
        if seed is not None:
            generator = self._torch.Generator(device=self._device).manual_seed(seed)

        # SD 1.x는 8의 배수 해상도를 요구한다.
        rounded_size = max(64, (size // 8) * 8)

        result = self._pipe(
            prompt=prompt,
            negative_prompt=negative_prompt,
            height=rounded_size,
            width=rounded_size,
            num_inference_steps=self._num_inference_steps,
            guidance_scale=self._guidance_scale,
            generator=generator,
        )
        return result.images[0].convert("RGBA")
