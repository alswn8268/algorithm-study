from PIL import Image

from kakao_emoticon_gen import kakao_spec


def _rgba_with_transparency(size=360):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    for x in range(size // 4, 3 * size // 4):
        for y in range(size // 4, 3 * size // 4):
            img.putpixel((x, y), (255, 0, 0, 255))
    return img


def test_validate_in_memory_passes_for_correct_image():
    img = _rgba_with_transparency(360)
    result = kakao_spec.validate_in_memory(img, profile="proposal_static")
    assert result.is_valid, result.violations


def test_validate_in_memory_fails_wrong_size():
    img = _rgba_with_transparency(512)
    result = kakao_spec.validate_in_memory(img, profile="proposal_static")
    assert not result.is_valid
    assert any(v.field == "dimensions" for v in result.violations)


def test_validate_in_memory_fails_no_transparency():
    img = Image.new("RGBA", (360, 360), (255, 0, 0, 255))  # fully opaque
    result = kakao_spec.validate_in_memory(img, profile="proposal_static")
    assert not result.is_valid
    assert any(v.field == "transparency" for v in result.violations)


def test_validate_image_file_roundtrip(tmp_path):
    img = _rgba_with_transparency(360)
    path = tmp_path / "sample.png"
    img.save(path, format="PNG")

    result = kakao_spec.validate_image(path, profile="proposal_static")
    assert result.is_valid, result.violations


def test_validate_set_flags_incomplete_cut_count(tmp_path):
    for i in range(5):
        _rgba_with_transparency(360).save(tmp_path / f"cut{i}.png", format="PNG")

    result = kakao_spec.validate_set(tmp_path, profile="proposal_static")
    assert not result.is_valid
    assert result.count_violation is not None
    assert "32" in result.count_violation.message
    # 개별 파일은 모두 규격을 만족한다.
    assert all(r.is_valid for r in result.file_results.values())


def test_validate_set_passes_with_full_32_cuts(tmp_path):
    for i in range(32):
        _rgba_with_transparency(360).save(tmp_path / f"cut{i:02d}.png", format="PNG")

    result = kakao_spec.validate_set(tmp_path, profile="proposal_static")
    assert result.is_valid, result.count_violation
    assert len(result.file_results) == 32


def test_validate_set_skips_count_check_when_profile_has_none(tmp_path):
    _rgba_with_transparency(360).save(tmp_path / "frame0.png", format="PNG")

    result = kakao_spec.validate_set(tmp_path, profile="proposal_animated_frame")
    assert result.count_violation is None
    assert result.is_valid


def test_validate_image_missing_file(tmp_path):
    result = kakao_spec.validate_image(tmp_path / "missing.png")
    assert not result.is_valid
    assert result.violations[0].field == "file"


def test_validate_image_wrong_format(tmp_path):
    img = _rgba_with_transparency(360)
    path = tmp_path / "sample.jpg"
    img.convert("RGB").save(path, format="JPEG")

    result = kakao_spec.validate_image(path, profile="proposal_static")
    assert not result.is_valid
    assert any(v.field == "format" for v in result.violations)
