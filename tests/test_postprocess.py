import numpy as np
import pytest
from PIL import Image, ImageDraw

from kakao_emoticon_gen import postprocess


def _sample_image_with_white_bg(size=400):
    img = Image.new("RGBA", (size, size), (255, 255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.ellipse([50, 50, size - 50, size - 50], fill=(255, 0, 0, 255))
    return img


def test_colorkey_remove_background_makes_corners_transparent():
    img = _sample_image_with_white_bg()
    result = postprocess._colorkey_remove_background(img)
    assert result.getpixel((0, 0))[3] == 0
    # center of the red circle should remain opaque
    cx = cy = img.size[0] // 2
    assert result.getpixel((cx, cy))[3] == 255


def test_resize_canvas_produces_exact_target_size():
    img = _sample_image_with_white_bg(size=200)
    no_bg = postprocess.remove_background(img)
    resized = postprocess.resize_canvas(no_bg, target=360)
    assert resized.size == (360, 360)
    assert resized.mode == "RGBA"


def test_resize_canvas_handles_fully_transparent_image():
    img = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
    resized = postprocess.resize_canvas(img, target=360)
    assert resized.size == (360, 360)


def test_add_hand_jitter_preserves_size_and_mode():
    img = _sample_image_with_white_bg(size=200)
    jittered = postprocess.add_hand_jitter(img, strength=2.0, seed=1)
    assert jittered.size == img.size
    assert jittered.mode == "RGBA"


def test_add_hand_jitter_actually_changes_pixels():
    img = _sample_image_with_white_bg(size=200)
    jittered = postprocess.add_hand_jitter(img, strength=3.0, seed=1)
    assert not np.array_equal(np.array(jittered), np.array(img.convert("RGBA")))


def test_add_hand_jitter_is_deterministic_with_seed():
    img = _sample_image_with_white_bg(size=200)
    a = postprocess.add_hand_jitter(img, strength=2.0, seed=7)
    b = postprocess.add_hand_jitter(img, strength=2.0, seed=7)
    assert np.array_equal(np.array(a), np.array(b))


def test_add_hand_jitter_zero_strength_is_a_noop():
    img = _sample_image_with_white_bg(size=100)
    result = postprocess.add_hand_jitter(img, strength=0)
    assert np.array_equal(np.array(result), np.array(img.convert("RGBA")))


def test_resize_canvas_fit_canvas_keeps_scale_consistent():
    """세트 통일감의 핵심 — fit='canvas'는 내용물 크기와 무관하게 같은 배율을 쓴다."""
    def framed(radius):
        img = Image.new("RGBA", (400, 400), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.ellipse([200 - radius, 200 - radius, 200 + radius, 200 + radius], fill=(255, 0, 0, 255))
        return img

    small = postprocess.resize_canvas(framed(40), target=360, fit="canvas")
    large = postprocess.resize_canvas(framed(90), target=360, fit="canvas")

    def opaque_width(img):
        alpha = np.array(img)[:, :, 3]
        cols = np.where(alpha.max(axis=0) > 0)[0]
        return cols.max() - cols.min()

    # 원본에서 크기가 다르면 결과에서도 그대로 달라야 한다
    assert opaque_width(large) > opaque_width(small) * 1.8

    # 반면 fit="content"는 둘 다 캔버스에 꽉 채워 크기 차이를 지워버린다
    c_small = postprocess.resize_canvas(framed(40), target=360, fit="content")
    c_large = postprocess.resize_canvas(framed(90), target=360, fit="content")
    assert abs(opaque_width(c_small) - opaque_width(c_large)) < 10


def test_resize_canvas_rejects_unknown_fit():
    img = _sample_image_with_white_bg(size=100)
    with pytest.raises(ValueError):
        postprocess.resize_canvas(img, target=360, fit="stretch")


def test_save_png_creates_file(tmp_path):
    img = Image.new("RGBA", (360, 360), (0, 0, 0, 0))
    out = postprocess.save_png(img, tmp_path / "nested" / "out.png")
    assert out.exists()
    with Image.open(out) as reloaded:
        assert reloaded.format == "PNG"
        assert reloaded.size == (360, 360)


def test_frames_to_gif(tmp_path):
    frames = [Image.new("RGBA", (50, 50), (i * 30, 0, 0, 255)) for i in range(3)]
    out = postprocess.frames_to_gif(frames, tmp_path / "anim.gif")
    assert out.exists()
    with Image.open(out) as gif:
        assert gif.n_frames == 3
