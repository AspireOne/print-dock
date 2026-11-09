import io

import pytest
from PIL import Image

from printdock.crop import Crop
from printdock.imaging import encode_crop, render_crop


def test_portrait_crop_has_exact_protocol_ratio_in_source_coordinates():
    crop = Crop((2000, 1000))
    assert crop.box == (687.5, 0, 1312.5, 1000)
    assert crop.zoomed(2).box == (843.75, 250, 1156.25, 750)


def test_pan_clamps_at_image_edges_without_introducing_blank_pixels():
    crop = Crop((2000, 1000)).zoomed(2)
    assert crop.moved(-10000, -10000).box == (0, 0, 312.5, 500)
    assert crop.moved(10000, 10000).box == (1687.5, 500, 2000, 1000)


def test_wheel_zoom_preserves_source_point_under_pointer():
    crop = Crop((2000, 2000)).zoomed(2, anchor=(0.25, 0.75))
    assert crop.box == (531.25, 750, 1156.25, 1750)


def test_render_uses_selected_source_region_instead_of_recentering():
    image = Image.new("RGB", (1280, 1024), "blue")
    image.paste("red", (640, 0, 1280, 1024))
    left = Crop(image.size, center=(0.25, 0.5))
    right = left.moved(640, 0)
    assert render_crop(image, left).getpixel((320, 512)) == (0, 0, 255)
    assert render_crop(image, right).getpixel((320, 512)) == (255, 0, 0)


def test_one_output_pixel_nudge_moves_sampling_by_exactly_one_source_pixel_at_unity_scale():
    image = Image.new("RGB", (1280, 1024))
    for x in range(1280):
        image.paste((x % 256, 0, 0), (x, 0, x + 1, 1024))
    selected = Crop(image.size).moved(1, 0)
    assert selected.box == (321, 0, 961, 1024)
    assert render_crop(image, selected).getpixel((0, 512)) == (65, 0, 0)


def test_fit_photo_keeps_white_margins_and_all_of_the_image():
    image = Image.new("RGB", (1600, 1000), "blue")
    crop = Crop(image.size)
    crop = crop.zoomed(crop.fit_zoom)
    rendered = render_crop(image, crop)
    assert rendered.size == (640, 1024)
    assert rendered.getpixel((320, 0)) == (255, 255, 255)
    assert rendered.getpixel((320, 512)) == (0, 0, 255)
    assert crop.box == pytest.approx((0, -780, 1600, 1780))


def test_landscape_jpeg_rotation_preserves_the_selected_crop():
    image = Image.new("RGB", (2048, 1280), "red")
    image.paste("blue", (1024, 0, 2048, 1280))
    selected = Crop(image.size, landscape=True).zoomed(2).moved(-512, 0)
    with Image.open(io.BytesIO(encode_crop(image, selected))) as jpeg:
        assert jpeg.size == (640, 1024)
        assert jpeg.getpixel((320, 512))[0] > 240
        assert jpeg.getpixel((320, 512))[2] < 10


def test_crop_from_another_source_is_rejected():
    with pytest.raises(ValueError, match="different source"):
        render_crop(Image.new("RGB", (800, 800)), Crop((1000, 1000)))
