"""절차적 발그림 렌더러를 파이프라인 백엔드로 연결한다 (GPU/API 불필요).

`mock` 백엔드가 파이프라인 배관 확인용 플레이스홀더라면, 이 백엔드는 실제로
STYLE_GUIDE의 화풍 규칙을 따르는 그림을 낸다. 32컷 세트 전체가 같은
`CharacterSpec`을 공유하므로 캐릭터 일관성도 유지된다.
"""
from __future__ import annotations

import re

from PIL import Image

from .. import sketchgen
from ..sketchgen import CharacterSpec
from .base import ImageGenerator

# pipeline이 만드는 프롬프트에서 원래 키워드를 되찾기 위한 패턴.
# prompts.build_prompt()가 항상 이 형태로 시작한다.
_KEYWORD_RE = re.compile(r'expressing "(.+?)" emotion')


class SketchGenerator(ImageGenerator):
    def __init__(
        self,
        character: CharacterSpec | None = None,
        character_seed: int | None = None,
        animal: str | None = None,
        draw_style: str = "doodle",
    ):
        self.draw_style = draw_style
        if character is not None:
            self.character = character
        elif character_seed is not None:
            self.character = sketchgen.make_character(character_seed, animal=animal)
        elif animal is not None:
            self.character = sketchgen.make_character(0, animal=animal)
        else:
            self.character = sketchgen.DEFAULT_CHARACTER

    def generate(
        self,
        prompt: str,
        negative_prompt: str | None = None,
        seed: int | None = None,
        size: int = 512,
    ) -> Image.Image:
        match = _KEYWORD_RE.search(prompt)
        # 프롬프트 형식이 바뀌어도 죽지 않도록 전체 프롬프트로 폴백한다.
        keyword = match.group(1) if match else prompt
        return sketchgen.render_character(keyword, size=size, seed=seed,
                                          character=self.character,
                                          draw_style=self.draw_style)
