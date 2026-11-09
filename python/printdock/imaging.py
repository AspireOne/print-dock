import io
from pathlib import Path

from PIL import Image, ImageCms, ImageOps

from .protocol import IMAGE_SIZE


def printable_jpeg(
    path: Path, *, fit: str = "cover", quality: int = 98, orientation: str = "auto",
) -> bytes:
    if fit not in {"cover", "contain"}:
        raise ValueError("Fit must be cover or contain")
    if not 1 <= quality <= 100:
        raise ValueError("JPEG quality must be 1..100")
    if orientation not in {"auto", "portrait", "landscape"}:
        raise ValueError("Orientation must be auto, portrait, or landscape")
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
        image = background.convert("RGB")
        landscape = orientation == "landscape" or (orientation == "auto" and image.width > image.height)
        target = IMAGE_SIZE[::-1] if landscape else IMAGE_SIZE
        if fit == "cover":
            image = ImageOps.fit(image, target, method=Image.Resampling.LANCZOS)
        else:
            image = ImageOps.pad(image, target, method=Image.Resampling.LANCZOS, color="white")
        if landscape:
            image = image.transpose(Image.Transpose.ROTATE_90)
        output = io.BytesIO()
        image.save(output, "JPEG", quality=quality, subsampling=0, progressive=False)
        return output.getvalue()
