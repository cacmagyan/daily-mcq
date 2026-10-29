"""The two students of the story explainers, from the page's own character sheets (a boy in a blue hoodie
and a girl in a pink hoodie). The chosen poses were cut out, sharpened to 4x and packed into
assets/brand/students.webp; POSES below says where each one is, where its eyes and mouth are, and how
big its head is, so any pose can be placed at the same head size, blink, and move its mouth with the
voice (the mouth and closed eyes are painted over the picture).
"""

from __future__ import annotations

from functools import lru_cache

from .config import ROOT

ATLAS = ROOT / "assets" / "brand" / "students.webp"
OUTLINE = (58, 36, 26)
MOUTH_DARK = (110, 38, 40)
TONGUE = (232, 120, 122)

# pose -> "rect" (x, y, w, h) in the atlas; "ed" = distance between the eyes (head size) and "anchor" =
# the point between the eyes, in the pose's own pixels; "mouth" = (x, y, width) where a talking mouth
# goes; "mouth_patch" / "blink_patch" = (x, y, w, h) in the atlas + where to paste it on the pose: the
# face with its drawn mouth smoothed away / with its eyes closed.
POSES: dict[str, dict] = {
    "boy_back": {"rect": [0, 0, 498, 679], "ed": 160.0, "anchor": [242.0, 199.4]},
    "boy_ask": {"rect": [502, 0, 555, 757], "ed": 123.5, "anchor": [285.2, 271.5], "eyes": [[223.5, 287.0, 25.2, 29.4], [347.0, 256.0, 21.3, 27.3]], "mouth": [294.5, 381.5, 61.8], "mouth_patch": [1061, 0, 142, 72, 224, 346], "blink_patch": [1207, 0, 214, 122, 176, 211]},
    "boy_shocked": {"rect": [1425, 0, 540, 800], "ed": 139.5, "anchor": [277.2, 289.8], "eyes": [[207.5, 291.5, 28.6, 34.1], [347.0, 288.0, 26.9, 33.6]], "mouth": [278.0, 415.5, 76.7], "mouth_patch": [1969, 0, 169, 93, 194, 363], "blink_patch": [2142, 0, 243, 108, 155, 235]},
    "boy_think": {"rect": [2389, 0, 558, 797], "ed": 131.0, "anchor": [299.0, 290.8], "eyes": [[233.5, 305.5, 27.4, 32.0], [364.5, 276.0, 24.1, 31.5]], "mouth": [309.5, 398.0, 65.5], "mouth_patch": [2951, 0, 150, 73, 235, 362], "blink_patch": [3105, 0, 228, 129, 183, 226]},
    "boy_point": {"rect": [0, 804, 805, 759], "ed": 124.5, "anchor": [328.8, 284.5], "eyes": [[266.5, 295.0, 26.3, 31.5], [391.0, 274.0, 22.4, 30.5]], "mouth": [332.0, 398.5, 68.5], "mouth_patch": [809, 804, 155, 84, 255, 357], "blink_patch": [968, 804, 218, 119, 217, 225]},
    "boy_happy": {"rect": [1190, 804, 576, 749], "ed": 145.0, "anchor": [312.0, 292.0], "mouth": [315, 385, 110], "mouth_patch": [1770, 804, 227, 145, 202, 313]},
    "boy_worried": {"rect": [2001, 804, 527, 789], "ed": 137.5, "anchor": [286.2, 294.5], "eyes": [[217.5, 297.0, 27.4, 32.6], [355.0, 292.0, 24.6, 31.5]], "mouth": [271.0, 399.5, 68.8], "mouth_patch": [2532, 804, 155, 76, 194, 362], "blink_patch": [2691, 804, 236, 105, 167, 242]},
    "boy_listen": {"rect": [2931, 804, 520, 766], "ed": 129.5, "anchor": [299.2, 282.5], "eyes": [[234.5, 288.5, 26.3, 32.0], [364.0, 276.5, 22.4, 31.0]], "mouth": [293.5, 385.5, 72], "mouth_patch": [3455, 804, 160, 84, 214, 344], "blink_patch": [3619, 804, 223, 111, 185, 227]},
    "boy_cheer": {"rect": [0, 1597, 850, 795], "ed": 150.0, "anchor": [339.0, 283.0], "mouth": [357, 370, 115], "mouth_patch": [854, 1597, 237, 149, 239, 296]},
    "boy_nervous": {"rect": [1095, 1597, 445, 535], "ed": 110.5, "anchor": [258.8, 256.0], "eyes": [[203.5, 255.5, 21.8, 25.7], [314.0, 256.5, 20.2, 24.7]], "mouth": [234.5, 357.5, 60.8], "mouth_patch": [1544, 1597, 142, 74, 164, 321], "blink_patch": [1690, 1597, 194, 84, 161, 213]},
    "boy_wave": {"rect": [1888, 1597, 631, 795], "ed": 134.0, "anchor": [343.0, 280.5], "eyes": [[276.0, 295.0, 28.0, 31.5], [410.0, 266.0, 24.6, 31.5]], "mouth": [358.0, 400.5, 73.7], "mouth_patch": [2523, 1597, 163, 88, 277, 357], "blink_patch": [2690, 1597, 234, 128, 224, 216]},
    "boy_think2": {"rect": [2928, 1597, 522, 671], "ed": 125.5, "anchor": [271.8, 242.5], "eyes": [[209.0, 258.0, 37.0, 30.5], [334.5, 227.0, 18.5, 23.1]], "mouth": [265.5, 384.5, 62.8], "mouth_patch": [3454, 1597, 144, 72, 194, 349], "blink_patch": [3602, 1597, 230, 117, 143, 188]},
    "girl_back": {"rect": [0, 2396, 507, 651], "ed": 164.1, "anchor": [249.0, 314.6]},
    "girl_ask": {"rect": [511, 2396, 539, 725], "ed": 118.5, "anchor": [279.2, 245.2], "eyes": [[220.0, 261.0, 24.6, 29.4], [338.5, 229.5, 21.8, 28.9]], "mouth": [295.0, 334.5, 65.2], "mouth_patch": [1054, 2396, 149, 84, 221, 293], "blink_patch": [1207, 2396, 209, 124, 173, 183]},
    "girl_shocked": {"rect": [1420, 2396, 562, 760], "ed": 128.0, "anchor": [275.0, 254.0], "eyes": [[211.0, 263.0, 25.8, 31.5], [339.0, 245.0, 24.6, 30.5]], "mouth": [285.5, 360.5, 70.4], "mouth_patch": [1986, 2396, 158, 118, 207, 302], "blink_patch": [2148, 2396, 224, 116, 163, 196]},
    "girl_think": {"rect": [2376, 2396, 580, 753], "ed": 145.0, "anchor": [292.0, 252.0], "eyes": [[220, 275, 33.6, 35.7], [365, 230, 32.5, 34.6]], "mouth": [320, 344, 72.5], "mouth_patch": [2960, 2396, 161, 77, 240, 306], "blink_patch": [3125, 2396, 266, 153, 159, 176]},
    "girl_point": {"rect": [3395, 2396, 579, 714], "ed": 113.0, "anchor": [296.0, 240.0], "eyes": [[239.5, 252.0, 24.1, 28.4], [352.5, 228.0, 19.6, 27.3]], "mouth": [300.5, 330.0, 78], "mouth_patch": [0, 3160, 172, 105, 215, 278], "blink_patch": [176, 3160, 198, 114, 194, 183]},
    "girl_excited": {"rect": [378, 3160, 608, 727], "ed": 146.0, "anchor": [319.0, 240.0], "mouth": [320, 325, 100], "mouth_patch": [990, 3160, 209, 137, 216, 257]},
    "girl_worried": {"rect": [1203, 3160, 533, 755], "ed": 128.5, "anchor": [275.8, 265.2], "eyes": [[211.5, 271.0, 25.2, 30.5], [340.0, 259.5, 24.6, 29.9]], "mouth": [280.5, 365.5, 64.2], "mouth_patch": [1740, 3160, 148, 72, 207, 330], "blink_patch": [1892, 3160, 224, 106, 164, 212]},
    "girl_neutral": {"rect": [2120, 3160, 517, 639], "ed": 106.5, "anchor": [310.8, 226.5], "eyes": [[257.5, 242.5, 21.8, 27.8], [364.0, 210.5, 15.7, 26.8]], "mouth": [341.0, 300.5, 58.6], "mouth_patch": [2641, 3160, 137, 70, 273, 266], "blink_patch": [2782, 3160, 183, 119, 215, 167]},
    "girl_listen": {"rect": [2969, 3160, 559, 720], "ed": 119.0, "anchor": [323.0, 241.8], "eyes": [[263.5, 255.0, 25.2, 29.4], [382.5, 228.5, 20.7, 28.9]], "mouth": [333.0, 335.0, 71], "mouth_patch": [3532, 3160, 159, 95, 254, 288], "blink_patch": [3695, 3160, 208, 119, 216, 182]},
    "girl_happy": {"rect": [0, 3919, 588, 759], "ed": 146.0, "anchor": [298.0, 252.0], "mouth": [291, 330, 98], "mouth_patch": [592, 3919, 207, 137, 188, 262]},
    "girl_nervous": {"rect": [803, 3919, 521, 638], "ed": 135.0, "anchor": [280.0, 237.0], "eyes": [[212, 247, 31.4, 33.6], [347, 227, 29.1, 31.5]], "mouth": [286, 315, 74.2], "mouth_patch": [1328, 3919, 165, 98, 204, 262], "blink_patch": [1497, 3919, 247, 121, 155, 177]},
    "girl_wave": {"rect": [1748, 3919, 625, 760], "ed": 131.5, "anchor": [357.2, 256.2], "eyes": [[291.5, 268.0, 27.4, 32.6], [423.0, 244.5, 23.5, 31.0]], "mouth": [367.0, 358.0, 95], "mouth_patch": [2377, 3919, 201, 133, 267, 292], "blink_patch": [2582, 3919, 228, 123, 241, 195]},
    "girl_think2": {"rect": [2814, 3919, 548, 657], "ed": 112.5, "anchor": [315.2, 217.0], "eyes": [[259.0, 239.0, 23.5, 28.4], [371.5, 195.0, 16.2, 26.2]], "mouth": [326.0, 307.0, 61.9], "mouth_patch": [3366, 3919, 143, 71, 255, 272], "blink_patch": [3513, 3919, 192, 132, 214, 152]},
}


def available() -> bool:
    return ATLAS.exists() and bool(POSES)


@lru_cache(maxsize=1)
def _atlas():
    from PIL import Image

    return Image.open(ATLAS).convert("RGBA")


def poses(who: str) -> list[str]:
    return [k.split("_", 1)[1] for k in POSES if k.startswith(who + "_")]


def _mouth_layer(size, mx, my, mw, kind, ss=3):
    """A talking mouth (half or fully open) in the sheet's style, drawn large and shrunk for smooth edges."""
    from PIL import Image, ImageDraw

    W, H = size
    big = Image.new("RGBA", (W * ss, H * ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    w = mw * (0.62 if kind == 1 else 0.86)
    h = mw * (0.30 if kind == 1 else 0.56)
    x0, y0, x1, y1 = (mx - w / 2) * ss, (my - h / 2) * ss, (mx + w / 2) * ss, (my + h / 2) * ss
    lw = max(2, int(mw * 0.05 * ss))
    # a rounded "D" shape: flatter top, round bottom
    d.chord([x0, y0 - (y1 - y0) * 0.7, x1, y1], 0, 180, fill=MOUTH_DARK + (255,), outline=OUTLINE + (255,), width=lw)
    tw, th = (x1 - x0) * 0.55, (y1 - y0) * 0.42
    cx = (x0 + x1) / 2
    d.ellipse([cx - tw / 2, y1 - th - lw, cx + tw / 2, y1 + th * 0.5 - lw], fill=TONGUE + (255,))
    if kind == 2:                                   # top teeth
        d.rectangle([x0 + (x1 - x0) * 0.16, y0 + lw * 0.6, x1 - (x1 - x0) * 0.16, y0 + (y1 - y0) * 0.24],
                    fill=(255, 255, 255, 255))
    d.chord([x0, y0 - (y1 - y0) * 0.7, x1, y1], 0, 180, outline=OUTLINE + (255,), width=lw)
    return big.resize(size, Image.LANCZOS)


def _patch(spec):
    x, y, w, h = spec[:4]
    return _atlas().crop((x, y, x + w, y + h))


@lru_cache(maxsize=256)
def picture(who: str, pose: str, talk: int = 0, blink: bool = False):
    """The pose at sheet size (RGBA), with an open mouth (talk 1 or 2) and/or closed eyes painted on."""
    meta = POSES[f"{who}_{pose}"]
    x, y, w, h = meta["rect"]
    im = _atlas().crop((x, y, x + w, y + h)).copy()
    if talk and meta.get("mouth_patch"):
        im.alpha_composite(_patch(meta["mouth_patch"]), tuple(meta["mouth_patch"][4:6]))
        mx, my, mw = meta["mouth"]
        im.alpha_composite(_mouth_layer(im.size, mx, my + mw * 0.04, mw, talk))
    if blink and meta.get("blink_patch"):
        im.alpha_composite(_patch(meta["blink_patch"]), tuple(meta["blink_patch"][4:6]))
    return im


def placed(who: str, pose: str, head_x: float, eye_y: float, eye_dist: float, talk: int = 0, blink: bool = False):
    """(image, (left, top)) of the pose scaled so its eyes are `eye_dist` apart, centred on head_x, eye_y."""
    from PIL import Image

    meta = POSES[f"{who}_{pose}"]
    s = eye_dist / meta["ed"]
    im = picture(who, pose, talk, blink)
    im = im.resize((max(1, round(im.width * s)), max(1, round(im.height * s))), Image.LANCZOS)
    ax, ay = meta["anchor"]
    return im, (round(head_x - ax * s), round(eye_y - ay * s))
