"""CLI 진입점.

사용 예:
    python -m kakao_emoticon_gen.cli generate --emotions "기쁨,슬픔" --backend mock
    python -m kakao_emoticon_gen.cli validate --path output/approved
    python -m kakao_emoticon_gen.cli list-emotions
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import kakao_spec, prompts
from .backends import get_backend
from .config import get_settings
from .pipeline import generate_set


def _cmd_generate(args: argparse.Namespace) -> int:
    settings = get_settings()
    keywords = [k.strip() for k in args.emotions.split(",") if k.strip()]
    if not keywords:
        print("error: --emotions must contain at least one keyword", file=sys.stderr)
        return 1

    backend_name = args.backend or settings.backend
    backend_kwargs = {}
    if backend_name == "dalle":
        backend_kwargs["api_key"] = args.api_key or settings.openai_api_key
    elif backend_name == "stable_diffusion":
        backend_kwargs["model_id"] = args.model or settings.sd_model_id
        backend_kwargs["device"] = args.device or settings.sd_device

    backend = get_backend(backend_name, **backend_kwargs)

    results = generate_set(
        keywords=keywords,
        backend=backend,
        output_dir=args.out or settings.output_dir,
        style=args.style,
        profile=args.profile or settings.profile,
        base_seed=args.seed,
        jitter=args.jitter,
    )

    approved = sum(1 for r in results if r.status == "approved")
    review = sum(1 for r in results if r.status == "needs_review")
    blocked = sum(1 for r in results if r.status == "blocked")

    print(f"\n생성 완료: 총 {len(results)}개 (승인 {approved} / 검토필요 {review} / 차단 {blocked})\n")
    for r in results:
        marker = {"approved": "✅", "needs_review": "🔎", "blocked": "🚫"}[r.status]
        print(f"  {marker} [{r.status:12s}] {r.keyword:10s} -> {r.output_path}")
        for reason in r.reasons:
            print(f"        - {reason}")
    return 0


def _print_file_result(path, result) -> None:
    if result.is_valid:
        print(f"✅ {path}")
    else:
        print(f"❌ {path}")
        for v in result.violations:
            print(f"    - [{v.field}] {v.message}")


def _cmd_validate(args: argparse.Namespace) -> int:
    path = Path(args.path)

    if not path.is_dir():
        result = kakao_spec.validate_image(path, profile=args.profile)
        _print_file_result(path, result)
        return 0 if result.is_valid else 1

    set_result = kakao_spec.validate_set(path, profile=args.profile)
    if not set_result.file_results:
        print(f"no PNG files found under {path}", file=sys.stderr)
        return 1

    for file_path, result in set_result.file_results.items():
        _print_file_result(file_path, result)

    if set_result.count_violation is not None:
        print(f"\n⚠️  [{set_result.count_violation.field}] {set_result.count_violation.message}")

    return 0 if set_result.is_valid else 1


def _cmd_list_emotions(_: argparse.Namespace) -> int:
    emotions = prompts.RECOMMENDED_EMOTION_SET
    print(f"참고용 감정/문구 예시 세트 {len(emotions)}컷 (공식 요구사항 아님):")
    for kw in emotions:
        print(f"  - {kw}")
    print("\n사용 가능한 스타일 프리셋:")
    for name in prompts.STYLE_PRESETS:
        marker = " (기본값)" if name == prompts.DEFAULT_STYLE else ""
        print(f"  - {name}{marker}")
    return 0


SUBMISSION_CHECKLIST: list[str] = [
    "논란이 없을 법한 최신 유행어나 오래가는 밈을 활용",
    "32컷 모두 같은 사람이 대충 그린 듯한 통일감 (선의 얇기·떨림 정도·낙서 텐션이 일정)",
    "선이 너무 깔끔한 컷이 없는지 (있다면 다시 빠르게 그려서 교체 — 오래 그릴수록 망함)",
    "채색이 선 안에 얌전히 들어간 컷이 없는지 (일부러 삐져나가게)",
    "참고 캐릭터와 실루엣이 겹치지 않는지",
    "텍스트 없이 봐도 뜻이 통하는지 (논버벌 테스트)",
    "손글씨 텍스트에 흰색 아웃라인 + 다크모드 가독성 확인",
]


def _cmd_checklist(_: argparse.Namespace) -> int:
    print("제출 전 수동 검토 체크리스트:\n")
    for item in SUBMISSION_CHECKLIST:
        print(f"  [ ] {item}")
    print(
        "\n자동 검사는 규격(해상도/포맷/투명배경)과 최소 품질만 걸러냅니다."
        "\n화풍 통일감과 실루엣 유사성은 반드시 사람이 눈으로 확인하세요."
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kakao-emoticon-gen", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_gen = sub.add_parser("generate", help="키워드로부터 이모티콘 이미지 생성")
    p_gen.add_argument("--emotions", required=True, help="쉼표로 구분한 감정/키워드 목록 (예: '기쁨,슬픔,화남')")
    p_gen.add_argument("--backend", choices=["mock", "dalle", "stable_diffusion"], default=None)
    p_gen.add_argument("--style", choices=list(prompts.STYLE_PRESETS), default=prompts.DEFAULT_STYLE)
    p_gen.add_argument("--profile", choices=list(kakao_spec.SUBMISSION_PROFILES), default=None)
    p_gen.add_argument("--out", type=Path, default=None)
    p_gen.add_argument("--seed", type=int, default=None)
    p_gen.add_argument(
        "--jitter",
        type=float,
        default=1.5,
        help="AI 티 제거용 손떨림 강도(픽셀). 0이면 끕니다. 트레이싱의 대체재는 아닙니다.",
    )
    p_gen.add_argument("--api-key", default=None, help="dalle 백엔드용 OpenAI API 키")
    p_gen.add_argument("--model", default=None, help="stable_diffusion 백엔드용 모델 ID")
    p_gen.add_argument("--device", default=None, help="stable_diffusion 백엔드용 device (cuda/cpu/mps)")
    p_gen.set_defaults(func=_cmd_generate)

    p_val = sub.add_parser("validate", help="기존 PNG가 카카오 규격에 맞는지 검증")
    p_val.add_argument("--path", required=True, help="파일 또는 디렉터리 경로")
    p_val.add_argument("--profile", choices=list(kakao_spec.SUBMISSION_PROFILES), default="proposal_static")
    p_val.set_defaults(func=_cmd_validate)

    p_list = sub.add_parser("list-emotions", help="참고용 감정 세트/스타일 프리셋 목록 출력")
    p_list.set_defaults(func=_cmd_list_emotions)

    p_check = sub.add_parser("checklist", help="제출 전 수동 검토 체크리스트 출력")
    p_check.set_defaults(func=_cmd_checklist)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
