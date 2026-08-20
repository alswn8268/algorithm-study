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
