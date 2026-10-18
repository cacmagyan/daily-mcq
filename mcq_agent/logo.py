"""Prepares the brand logo for the slides.

A logo saved as JPEG with a fake "transparent" checkerboard behind it has the squares baked
into its pixels. This removes them (keeping white areas inside the logo), trims the edges and
saves a transparent PNG. A logo that is already a transparent PNG is only trimmed and resized.

Needs numpy and scipy:  pip install numpy scipy
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

MAX_SIZE = 700  # px; the slides show the logo at about 230 px


def _grid(lum) -> tuple[float, float, bool] | None:
    """Square size, origin and whether the top-left square is white, measured along the top row."""
    import numpy as np

    tone = lum[2] > 234
    edges = np.flatnonzero(np.diff(tone.astype(int)) != 0) + 1
    if len(edges) < 8:
        return None
    size = (edges[-1] - edges[0]) / (len(edges) - 1)
    origin = edges[0] - size * round(edges[0] / size)
    return size, origin, bool(lum[2, 2] > 234)


def _remove_checkerboard(rgb: Image.Image) -> Image.Image:
    import numpy as np
    from scipy import ndimage

    a = np.asarray(rgb, dtype=np.int16)
    lo, hi = a.min(axis=2), a.max(axis=2)
    neutral_light = (hi - lo <= 16) & (lo >= 192)            # white and light-grey squares, JPEG noise included

    labels, n = ndimage.label(neutral_light)
    border = np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]]))
    is_bg = np.zeros(n + 1, dtype=bool)
    is_bg[border] = True

    # Enclosed patches (inside letters, between arms) are background only if their light and
    # grey pixels sit exactly where the checkerboard would put them. White shirts, paper and
    # shading inside the logo don't follow that grid, so they stay.
    grid = _grid(lo)
    if grid:
        size, origin, white_first = grid
        yy, xx = np.indices(lo.shape)
        even = ((np.floor((xx - origin) / size) + np.floor((yy - origin) / size)) % 2) == 0
        expect_white = even if white_first else ~even
        seen_white, seen_grey = lo >= 238, hi <= 228
        valid = seen_white | seen_grey
        match = valid & (seen_white == expect_white)
        idx = np.arange(n + 1)
        n_valid = ndimage.sum(valid, labels, index=idx)
        n_match = ndimage.sum(match, labels, index=idx)
        with np.errstate(invalid="ignore", divide="ignore"):
            is_bg |= (n_valid >= 12) & ((n_match / np.maximum(n_valid, 1)) >= 0.8)
    is_bg[0] = False
    bg = is_bg[labels]

    # eat the 1-2 px fringe where the logo outline was blended into the squares
    fringe = ndimage.binary_dilation(bg, iterations=2) & (hi - lo <= 34) & (lo >= 170)
    bg |= fringe
    alpha = np.where(bg, 0, 255).astype(np.uint8)
    alpha = np.asarray(Image.fromarray(alpha).filter(_soften()), dtype=np.uint8)
    out = np.dstack([a.astype(np.uint8), alpha])
    return Image.fromarray(out, "RGBA")


def _soften():
    from PIL import ImageFilter
    return ImageFilter.GaussianBlur(0.6)


def prepare_logo(src: Path, dest: Path) -> Path:
    im = Image.open(src)
    has_alpha = im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info)
    if has_alpha:
        im = im.convert("RGBA")
    else:
        im = _remove_checkerboard(im.convert("RGB"))
    box = im.getchannel("A").point(lambda v: 255 if v > 24 else 0).getbbox()
    if box:
        im = im.crop(box)
    im.thumbnail((MAX_SIZE, MAX_SIZE), Image.LANCZOS)
    dest.parent.mkdir(parents=True, exist_ok=True)
    im.save(dest, "PNG", optimize=True)
    return dest
