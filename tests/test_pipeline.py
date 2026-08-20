import json

from kakao_emoticon_gen import pipeline
from kakao_emoticon_gen.backends.mock import MockGenerator


def test_generate_one_produces_approved_or_review_result(tmp_path):
    backend = MockGenerator()
    result = pipeline.generate_one("기쁨", backend, tmp_path, seed=1)

    assert result.status in ("approved", "needs_review")
    assert result.output_path is not None
    assert (tmp_path / result.status / "기쁨.png").exists()


def test_generate_one_blocks_copyrighted_keyword(tmp_path):
    backend = MockGenerator()
    result = pipeline.generate_one("피카츄", backend, tmp_path, seed=1)

    assert result.status == "blocked"
    assert result.output_path is None


def test_generate_set_writes_manifest(tmp_path):
    backend = MockGenerator()
    results = pipeline.generate_set(
        ["기쁨", "슬픔", "화남"],
        backend,
        tmp_path,
        base_seed=42,
    )

    assert len(results) == 3
    manifest_path = tmp_path / "manifest.json"
    assert manifest_path.exists()

    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert len(data) == 3
    assert {d["keyword"] for d in data} == {"기쁨", "슬픔", "화남"}


def test_generate_set_deterministic_with_seed(tmp_path):
    backend = MockGenerator()
    r1 = pipeline.generate_set(["기쁨"], backend, tmp_path / "run1", base_seed=7)
    r2 = pipeline.generate_set(["기쁨"], backend, tmp_path / "run2", base_seed=7)

    assert r1[0].status == r2[0].status
