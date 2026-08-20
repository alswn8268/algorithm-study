"""환경 설정 로딩.

python-dotenv가 설치되어 있으면 사용하고, 없으면 `.env` 파일을 직접 파싱한다.
실제 값은 항상 `os.environ`을 우선한다 (셸에서 export한 값이 .env보다 우선).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv_file(path: Path) -> dict:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _load_env() -> None:
    try:
        from dotenv import load_dotenv  # type: ignore

        load_dotenv(PROJECT_ROOT / ".env")
        return
    except ImportError:
        pass

    for key, value in _load_dotenv_file(PROJECT_ROOT / ".env").items():
        os.environ.setdefault(key, value)


_load_env()


@dataclass
class Settings:
    backend: str = field(default_factory=lambda: os.environ.get("KAKAO_EMOTICON_BACKEND", "mock"))
    output_dir: Path = field(
        default_factory=lambda: Path(os.environ.get("KAKAO_EMOTICON_OUTPUT_DIR", "output"))
    )
    profile: str = field(default_factory=lambda: os.environ.get("KAKAO_EMOTICON_PROFILE", "proposal_static"))
    openai_api_key: str | None = field(default_factory=lambda: os.environ.get("OPENAI_API_KEY") or None)
    sd_model_id: str = field(
        default_factory=lambda: os.environ.get("SD_MODEL_ID", "runwayml/stable-diffusion-v1-5")
    )
    sd_device: str = field(default_factory=lambda: os.environ.get("SD_DEVICE", "cpu"))


def get_settings() -> Settings:
    return Settings()
