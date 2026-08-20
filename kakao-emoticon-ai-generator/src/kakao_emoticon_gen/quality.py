"""자동 생성 결과의 품질 편차를 걸러내기 위한 최소한의 휴리스틱 필터.

완벽한 품질 보증이 목표가 아니다. 애매한 경우 최대한 통과시키지 않고
"사람 검수(needs_review)"로 넘기는 것을 기본 전략으로 한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from PIL import Image, ImageFilter


@dataclass
class QualityReport:
    passed: bool
    reasons: list[str] = field(default_factory=list)
    transparency_ratio: float = 0.0
    edge_variance: float = 0.0


def check_not_blank(image: Image.Image, std_threshold: float = 3.0) -> tuple[bool, str | None]:
    """알파 채널이 있는 부분(피사체)이 단색/거의 무변화인지 확인한다."""
    rgba = image.convert("RGBA")
    arr = np.array(rgba)
    alpha = arr[:, :, 3]
    visible = arr[alpha > 0][:, :3]

    if visible.size == 0:
        return False, "generated image is fully transparent (no visible content)"

    # per-channel std across pixels (spatial variation), not across R/G/B
    # within a pixel -- a solid red image has zero spatial variance even
    # though its R and B channel values differ from each other.
    std = float(np.std(visible, axis=0).mean())
    if std < std_threshold:
        return False, f"visible content has almost no color variation (std={std:.2f})"
    return True, None


def check_blur(image: Image.Image, min_edge_variance: float = 15.0) -> tuple[bool, str | None, float]:
    """에지 검출 기반 블러 추정. 값이 낮을수록 흐릿한 이미지일 가능성이 높다."""
    gray = image.convert("L")
    edges = gray.filter(ImageFilter.FIND_EDGES)
    variance = float(np.var(np.array(edges, dtype=np.float32)))

    if variance < min_edge_variance:
        return False, f"image looks too blurry/flat (edge_variance={variance:.2f})", variance
    return True, None, variance


def check_transparency_ratio(
    image: Image.Image,
    min_ratio: float = 0.05,
    max_ratio: float = 0.97,
) -> tuple[bool, str | None, float]:
    """배경 제거가 전혀 안 됐거나(과소) 캐릭터까지 날아갔는지(과다) 확인한다."""
    rgba = image.convert("RGBA")
    alpha = np.array(rgba)[:, :, 3]
    ratio = float(np.mean(alpha == 0))

    if ratio < min_ratio:
        return False, f"background may not have been removed (transparent ratio={ratio:.2%})", ratio
    if ratio > max_ratio:
        return False, f"too much of the image is transparent (ratio={ratio:.2%}); subject may be missing", ratio
    return True, None, ratio


def run_quality_checks(image: Image.Image) -> QualityReport:
    reasons: list[str] = []

    ok, reason = check_not_blank(image)
    if not ok and reason:
        reasons.append(reason)

    ok, reason, edge_variance = check_blur(image)
    if not ok and reason:
        reasons.append(reason)

    ok, reason, transparency_ratio = check_transparency_ratio(image)
    if not ok and reason:
        reasons.append(reason)

    return QualityReport(
        passed=len(reasons) == 0,
        reasons=reasons,
        transparency_ratio=transparency_ratio,
        edge_variance=edge_variance,
    )
