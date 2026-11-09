import io
from pathlib import Path

from PIL import Image, ImageCms, ImageOps

from .crop import Crop


def initial_crop(image: Image.Image, *, fit: str = "cover", orientation: str = "auto") -> Crop:
    if fit not in {"cover", "contain"}:
        raise ValueError("Fit must be cover or contain")
    if orientation not in {"auto", "portrait", "landscape"}:
        raise ValueError("Orientation must be auto, portrait, or landscape")
    landscape = orientation == "landscape" or (orientation == "auto" and image.width > image.height)
    crop = Crop(image.size, landscape=landscape)
    return crop.zoomed(crop.fit_zoom) if fit == "contain" else crop


def load_image(path: Path) -> Image.Image:
    with Image.open(path) as source:
        image = ImageOps.exif_transpose(source)
        if image.info.get("icc_profile"):
            # Convert tagged photos once; printers consume untagged sRGB JPEGs.
            profile = ImageCms.ImageCmsProfile(io.BytesIO(image.info["icc_profile"]))
            alpha = image.getchannel("A") if "A" in image.getbands() else None
            image = ImageCms.profileToProfile(
                image.convert("RGB") if alpha is not None else image,
                profile,
                ImageCms.createProfile("sRGB"),
                outputMode="RGB",
            )
            if alpha is not None:
                image.putalpha(alpha)
        rgba = image.convert("RGBA")
        background = Image.new("RGBA", rgba.size, "white")
        background.alpha_composite(rgba)
        return background.convert("RGB")


def render_crop(image: Image.Image, crop: Crop) -> Image.Image:
    if image.size != crop.source_size:
        raise ValueError("Crop belongs to a different source image size")
    left, top, right, bottom = crop.box
    tw, th = crop.target_size
    visible = (max(0, left), max(0, top), min(image.width, right), min(image.height, bottom))
    # Resize only the visible source region, so high zoom never allocates an
    # enormous intermediate image. White margins use the same geometry.
    x0 = round((visible[0] - left) * tw / (right - left))
    y0 = round((visible[1] - top) * th / (bottom - top))
    x1 = round((visible[2] - left) * tw / (right - left))
    y1 = round((visible[3] - top) * th / (bottom - top))
    output = Image.new("RGB", crop.target_size, "white")
    if x1 > x0 and y1 > y0:
        pixels = image.resize((x1 - x0, y1 - y0), Image.Resampling.LANCZOS, box=visible)
        output.paste(pixels, (x0, y0))
    return output


def encode_crop(image: Image.Image, crop: Crop, *, quality: int = 98) -> bytes:
    if not 1 <= quality <= 100:
        raise ValueError("JPEG quality must be 1..100")
    rendered = render_crop(image, crop)
    if crop.landscape:
        rendered = rendered.transpose(Image.Transpose.ROTATE_90)
    output = io.BytesIO()
    rendered.save(output, "JPEG", quality=quality, subsampling=0, progressive=False)
    return output.getvalue()


def printable_jpeg(
    path: Path, *, fit: str = "cover", quality: int = 98, orientation: str = "auto",
) -> bytes:
    image = load_image(path)
    return encode_crop(image, initial_crop(image, fit=fit, orientation=orientation), quality=quality)
