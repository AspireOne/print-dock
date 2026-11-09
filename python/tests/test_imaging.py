import io

from PIL import Image

from printdock.imaging import printable_jpeg


def test_cover_fills_fixed_portrait_dimensions_and_contain_preserves_full_image(tmp_path):
    path = tmp_path / "landscape.png"
    Image.new("RGB", (400, 200), "red").save(path)
    with Image.open(io.BytesIO(printable_jpeg(path, orientation="portrait"))) as cover:
        assert cover.size == (640, 1024)
        assert cover.format == "JPEG"
        assert cover.getpixel((0, 0))[0] > 240
        assert cover.getpixel((0, 0))[1] < 10
    with Image.open(io.BytesIO(printable_jpeg(path, fit="contain", orientation="portrait"))) as contain:
        assert contain.size == (640, 1024)
        assert min(contain.getpixel((0, 0))) > 245
        assert contain.getpixel((320, 512))[0] > 240
        assert contain.getpixel((320, 512))[1] < 10


def test_exif_orientation_is_applied_before_resizing(tmp_path):
    image = Image.new("RGB", (100, 200), "red")
    image.paste("blue", (0, 0, 100, 100))
    exif = Image.Exif()
    exif[274] = 6
    path = tmp_path / "rotated.jpg"
    image.save(path, exif=exif)
    with Image.open(io.BytesIO(printable_jpeg(path, orientation="portrait"))) as prepared:
        assert prepared.getpixel((20, 512))[0] > 240
        assert prepared.getpixel((620, 512))[2] > 240


def test_landscape_photos_use_long_edge_without_cropping_as_portrait(tmp_path):
    path = tmp_path / "landscape.png"
    image = Image.new("RGB", (1024, 640), "red")
    image.paste("blue", (512, 0, 1024, 640))
    image.save(path)
    with Image.open(io.BytesIO(printable_jpeg(path))) as prepared:
        assert prepared.size == (640, 1024)
        assert prepared.getpixel((320, 20))[2] > 240
        assert prepared.getpixel((320, 1000))[0] > 240


def test_transparent_pixels_print_white(tmp_path):
    path = tmp_path / "transparent.png"
    Image.new("RGBA", (640, 1024), (0, 0, 0, 0)).save(path)
    with Image.open(io.BytesIO(printable_jpeg(path))) as prepared:
        assert prepared.getpixel((320, 512)) == (255, 255, 255)
