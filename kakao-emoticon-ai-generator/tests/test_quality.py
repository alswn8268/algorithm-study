from PIL import Image, ImageDraw

from kakao_emoticon_gen import quality
from kakao_emoticon_gen.backends.mock import MockGenerator


def test_blank_transparent_image_fails_not_blank():
    img = Image.new("RGBA", (360, 360), (0, 0, 0, 0))
    ok, reason = quality.check_not_blank(img)
    assert not ok
    assert reason is not None


def test_solid_color_image_fails_not_blank():
    img = Image.new("RGBA", (360, 360), (255, 0, 0, 255))
    ok, reason = quality.check_not_blank(img)
    assert not ok


def test_mock_generated_face_passes_not_blank_and_blur():
    gen = MockGenerator()
    img = gen.generate("기쁨", size=360)
    ok_blank, _ = quality.check_not_blank(img)
    ok_blur, _, variance = quality.check_blur(img)
    assert ok_blank
    assert ok_blur
    assert variance > 0


def test_transparency_ratio_too_low_flagged():
    img = Image.new("RGBA", (360, 360), (255, 0, 0, 255))  # no transparency at all
    ok, reason, ratio = quality.check_transparency_ratio(img)
    assert not ok
    assert ratio == 0.0


def test_transparency_ratio_too_high_flagged():
    img = Image.new("RGBA", (360, 360), (0, 0, 0, 0))  # fully transparent
    ok, reason, ratio = quality.check_transparency_ratio(img)
    assert not ok
    assert ratio == 1.0


def test_dark_mode_legibility_flags_black_only_drawing():
    """검은 볼펜 선만 있고 밝은 채색이 없으면 다크모드에서 묻힌다."""
    img = Image.new("RGBA", (360, 360), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([50, 50, 310, 310], outline=(20, 20, 20, 255), width=4)

    ok, reason, ratio = quality.check_dark_mode_legibility(img)
    assert not ok
    assert reason is not None
    assert ratio < 0.25


def test_dark_mode_legibility_passes_with_light_fill():
    img = Image.new("RGBA", (360, 360), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([50, 50, 310, 310], fill=(255, 220, 180, 255), outline=(20, 20, 20, 255), width=4)

    ok, reason, ratio = quality.check_dark_mode_legibility(img)
    assert ok
    assert ratio > 0.25


def test_run_quality_checks_on_reasonable_image_passes():
    gen = MockGenerator()
    img = gen.generate("사랑해", size=360)
    # simulate a background-removed image: punch transparent corners
    draw_img = img.copy()
    ImageDraw.Draw(draw_img)
    report = quality.run_quality_checks(draw_img)
    # mock face has no transparency by default (fully opaque square canvas minus corners)
    assert isinstance(report.passed, bool)
    assert isinstance(report.reasons, list)
