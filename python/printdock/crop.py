"""Crop geometry in EXIF-oriented source pixels, independent of the editor size."""

import math
from dataclasses import dataclass, replace

from .protocol import IMAGE_SIZE


@dataclass(frozen=True)
class Crop:
    source_size: tuple[int, int]
    landscape: bool = False
    zoom: float = 1.0
    center: tuple[float, float] = (0.5, 0.5)

    def __post_init__(self) -> None:
        if min(self.source_size) <= 0 or not math.isfinite(self.zoom) or self.zoom <= 0:
            raise ValueError("Crop dimensions and zoom must be positive and finite")
        if not all(math.isfinite(value) for value in self.center):
            raise ValueError("Crop center must be finite")

    @property
    def target_size(self) -> tuple[int, int]:
        return IMAGE_SIZE[::-1] if self.landscape else IMAGE_SIZE

    @property
    def fit_zoom(self) -> float:
        sw, sh = self.source_size
        tw, th = self.target_size
        return min(tw / sw, th / sh) / max(tw / sw, th / sh)

    @property
    def box(self) -> tuple[float, float, float, float]:
        sw, sh = self.source_size
        tw, th = self.target_size
        width = min(sw, sh * tw / th) / self.zoom
        height = width * th / tw
        cx, cy = self.center[0] * sw, self.center[1] * sh
        return cx - width / 2, cy - height / 2, cx + width / 2, cy + height / 2

    def clamped(self) -> "Crop":
        left, top, right, bottom = self.box
        sw, sh = self.source_size
        width, height = right - left, bottom - top
        left = min(max(left, min(0, sw - width)), max(0, sw - width))
        top = min(max(top, min(0, sh - height)), max(0, sh - height))
        return replace(self, center=((left + width / 2) / sw, (top + height / 2) / sh))

    def moved(self, dx: float, dy: float) -> "Crop":
        sw, sh = self.source_size
        return replace(self, center=(self.center[0] + dx / sw, self.center[1] + dy / sh)).clamped()

    def zoomed(self, zoom: float, anchor: tuple[float, float] = (0.5, 0.5)) -> "Crop":
        left, top, right, bottom = self.box
        point = (left + (right - left) * anchor[0], top + (bottom - top) * anchor[1])
        result = replace(self, zoom=zoom)
        nl, nt, nr, nb = result.box
        sw, sh = self.source_size
        return replace(result, center=(
            (point[0] + (0.5 - anchor[0]) * (nr - nl)) / sw,
            (point[1] + (0.5 - anchor[1]) * (nb - nt)) / sh,
        )).clamped()
