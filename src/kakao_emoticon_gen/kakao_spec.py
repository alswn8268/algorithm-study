"""카카오 이모티콘 스튜디오 제출 규격 검증.

카카오의 정식 규격은 이모티콘 유형(정지/움직이는/큰 이모티콘)과 제출
단계(제안 시안 vs 정식 등록)에 따라 다르고, 공지에 따라 바뀔 수 있다.
여기서는 가장 핵심적이고 공통적인 규격(PNG, 360x360, 투명 배경)을
`proposal_static` 기본 프로필로 강제한다. 제출 직전에는 반드시
카카오 이모티콘 스튜디오의 최신 공식 가이드를 재확인해야 한다.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image


@dataclass(frozen=True)
class SubmissionProfile:
    name: str
    width: int
    height: int
    format: str  # PIL format string, e.g. "PNG"
    require_alpha: bool
    max_bytes: int
    description: str
    expected_count: int | None = None  # 세트 단위 제출 장수 (없으면 검사 안 함)


SUBMISSION_PROFILES: dict[str, SubmissionProfile] = {
    "proposal_static": SubmissionProfile(
        name="proposal_static",
        width=360,
        height=360,
        format="PNG",
        require_alpha=True,
        max_bytes=150 * 1024,
        description="멈춰있는 이모티콘 제안(시안) 단계 기준",
        expected_count=32,
    ),
    # 필요 시 아래처럼 프로필을 추가해 다른 규격(정식 등록, 큰 이모티콘 등)을
    # 지원할 수 있다. 실제 값은 반드시 공식 가이드로 재확인할 것.
    "proposal_animated_frame": SubmissionProfile(
        name="proposal_animated_frame",
        width=360,
        height=360,
        format="PNG",
        require_alpha=True,
        max_bytes=2 * 1024 * 1024,
        description="움직이는 이모티콘 개별 프레임 기준 (GIF 합성 전)",
        # 프레임은 제출 단위가 아니라 GIF 합성용 중간 산출물이라 장수를 세지 않는다.
        expected_count=None,
    ),
}


@dataclass
class SpecViolation:
    field: str
    message: str


@dataclass
class ValidationResult:
    profile: str
    violations: list[SpecViolation] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return len(self.violations) == 0


def _has_real_transparency(image: Image.Image) -> bool:
    if image.mode != "RGBA":
        return False
    alpha = image.getchannel("A")
    return alpha.getextrema()[0] < 255  # 알파 채널에 실제 투명 픽셀이 있는지


def validate_image(
    image_path: str | Path,
    profile: str | SubmissionProfile = "proposal_static",
) -> ValidationResult:
    """저장된 PNG 파일이 카카오 제출 규격을 만족하는지 검증한다."""
    spec = SUBMISSION_PROFILES[profile] if isinstance(profile, str) else profile
    path = Path(image_path)
    violations: list[SpecViolation] = []

    if not path.exists():
        return ValidationResult(profile=spec.name, violations=[SpecViolation("file", f"file not found: {path}")])

    file_bytes = path.stat().st_size
    if file_bytes > spec.max_bytes:
        violations.append(
            SpecViolation(
                "file_size",
                f"{file_bytes} bytes exceeds max {spec.max_bytes} bytes ({spec.max_bytes // 1024}KB)",
            )
        )

    with Image.open(path) as img:
        img.load()
        actual_format = img.format
        if actual_format != spec.format:
            violations.append(SpecViolation("format", f"expected {spec.format}, got {actual_format}"))

        if img.size != (spec.width, spec.height):
            violations.append(
                SpecViolation("dimensions", f"expected {spec.width}x{spec.height}, got {img.size[0]}x{img.size[1]}")
            )

        if spec.require_alpha and not _has_real_transparency(img):
            violations.append(SpecViolation("transparency", "image has no transparent background (alpha channel missing or fully opaque)"))

    return ValidationResult(profile=spec.name, violations=violations)


@dataclass
class SetValidationResult:
    profile: str
    file_results: dict[str, ValidationResult] = field(default_factory=dict)
    count_violation: SpecViolation | None = None

    @property
    def is_valid(self) -> bool:
        return self.count_violation is None and all(r.is_valid for r in self.file_results.values())


def validate_set(
    directory: str | Path,
    profile: str | SubmissionProfile = "proposal_static",
) -> SetValidationResult:
    """디렉터리 전체를 제출 세트로 보고 각 파일 규격 + 총 장수를 검증한다."""
    spec = SUBMISSION_PROFILES[profile] if isinstance(profile, str) else profile
    directory = Path(directory)

    files = sorted(directory.glob("*.png"))
    result = SetValidationResult(profile=spec.name)
    for f in files:
        result.file_results[str(f)] = validate_image(f, profile=spec)

    if spec.expected_count is not None and len(files) != spec.expected_count:
        result.count_violation = SpecViolation(
            "count",
            f"expected {spec.expected_count} PNG files for a full submission set, found {len(files)}",
        )
    return result


def validate_in_memory(
    image: Image.Image,
    profile: str | SubmissionProfile = "proposal_static",
) -> ValidationResult:
    """디스크에 저장하지 않고 메모리 상의 이미지를 검증한다 (파일 용량은
    PNG로 인코딩했을 때의 크기를 기준으로 추정한다)."""
    spec = SUBMISSION_PROFILES[profile] if isinstance(profile, str) else profile
    violations: list[SpecViolation] = []

    buf = io.BytesIO()
    image.convert("RGBA").save(buf, format="PNG", optimize=True)
    encoded_bytes = buf.tell()

    if encoded_bytes > spec.max_bytes:
        violations.append(
            SpecViolation(
                "file_size",
                f"{encoded_bytes} bytes exceeds max {spec.max_bytes} bytes ({spec.max_bytes // 1024}KB)",
            )
        )

    if image.size != (spec.width, spec.height):
        violations.append(
            SpecViolation("dimensions", f"expected {spec.width}x{spec.height}, got {image.size[0]}x{image.size[1]}")
        )

    if spec.require_alpha and not _has_real_transparency(image.convert("RGBA")):
        violations.append(SpecViolation("transparency", "image has no transparent background (alpha channel missing or fully opaque)"))

    return ValidationResult(profile=spec.name, violations=violations)
