"""전체 오케스트레이션: 프롬프트 생성 → 저작권 검사 → AI 생성 → 후처리
→ 품질 필터 → 카카오 규격 검증 → approved/needs_review로 분류 저장.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import copyright_guard, kakao_spec, postprocess, prompts, quality
from .backends.base import ImageGenerator


@dataclass
class EmoticonResult:
    keyword: str
    style: str
    prompt: str
    output_path: str | None
    status: str  # "approved" | "needs_review" | "blocked"
    reasons: list[str] = field(default_factory=list)


def generate_one(
    keyword: str,
    backend: ImageGenerator,
    output_dir: Path,
    style: str = prompts.DEFAULT_STYLE,
    profile: str = "proposal_static",
    seed: int | None = None,
    raw_size: int = 512,
    target_size: int = 360,
) -> EmoticonResult:
    prompt_result = prompts.build_prompt(keyword, style=style)

    guard = copyright_guard.check_prompt(prompt_result.prompt)
    if guard.is_blocked:
        return EmoticonResult(
            keyword=keyword,
            style=style,
            prompt=prompt_result.prompt,
            output_path=None,
            status="blocked",
            reasons=[f"blocked term(s) in prompt: {', '.join(guard.blocked_terms)}"],
        )

    raw_image = backend.generate(
        prompt=prompt_result.prompt,
        negative_prompt=prompt_result.negative_prompt,
        seed=seed,
        size=raw_size,
    )

    no_bg = postprocess.remove_background(raw_image)
    final_image = postprocess.resize_canvas(no_bg, target=target_size)

    quality_report = quality.run_quality_checks(final_image)
    spec_result = kakao_spec.validate_in_memory(final_image, profile=profile)

    reasons = list(quality_report.reasons) + [v.message for v in spec_result.violations]
    status = "approved" if (quality_report.passed and spec_result.is_valid) else "needs_review"

    safe_name = "".join(c if c.isalnum() else "_" for c in keyword)
    subdir = output_dir / ("approved" if status == "approved" else "needs_review")
    out_path = postprocess.save_png(final_image, subdir / f"{safe_name}.png")

    return EmoticonResult(
        keyword=keyword,
        style=style,
        prompt=prompt_result.prompt,
        output_path=str(out_path),
        status=status,
        reasons=reasons,
    )


def generate_set(
    keywords: list[str],
    backend: ImageGenerator,
    output_dir: str | Path,
    style: str = prompts.DEFAULT_STYLE,
    profile: str = "proposal_static",
    base_seed: int | None = None,
) -> list[EmoticonResult]:
    output_dir = Path(output_dir)
    results = []
    for i, keyword in enumerate(keywords):
        seed = None if base_seed is None else base_seed + i
        result = generate_one(keyword, backend, output_dir, style=style, profile=profile, seed=seed)
        results.append(result)

    manifest_path = output_dir / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps([asdict(r) for r in results], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return results
