"""Renders each MCQ into two 1080x1350 JPEGs (question + answer) with headless Chromium."""

from __future__ import annotations

import datetime as dt
import tempfile
from pathlib import Path

import re

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup, escape
from PIL import Image

from .config import LETTERS, ROOT, Config, date_label

WIDTH, HEIGHT = 1080, 1350


def image_names(course_id: str) -> dict:
    return {"question": f"{course_id}_q.jpg", "answer": f"{course_id}_a.jpg"}


def concept_names() -> list[str]:
    from .concept import SLIDES
    return [f"concept_{i}.jpg" for i in range(1, SLIDES + 1)]


def mark(text: str) -> Markup:
    """==term== -> yellow highlighter, !!text!! -> red ink (escapes everything else)."""
    out = str(escape(text or ""))
    out = re.sub(r"==(.+?)==", r'<span class="hl">\1</span>', out)
    out = re.sub(r"!!(.+?)!!", r'<span class="redink">\1</span>', out)
    return Markup(out.replace("==", "").replace("!!", ""))


class Renderer:
    """Use as a context manager so one browser serves the whole batch."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.env = Environment(
            loader=FileSystemLoader(ROOT / "templates"),
            autoescape=select_autoescape(["html", "j2"]),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self.env.filters["mark"] = mark
        self.template = self.env.get_template("slide.html.j2")
        self.fonts_uri = (ROOT / "assets" / "fonts").as_uri()
        logo = (cfg.brand.get("logo") or "").strip()
        self.logo_uri = (ROOT / logo).as_uri() if logo and (ROOT / logo).exists() else ""
        self._pw = self._browser = None

    def __enter__(self):
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch()
        return self

    def __exit__(self, *exc):
        if self._browser:
            self._browser.close()
        if self._pw:
            self._pw.stop()

    def html(self, item: dict, date: dt.date, slide: str) -> str:
        course = self.cfg.course(item["course_id"])
        return self.template.render(
            item=item,
            course=course,
            courses=self.cfg.courses,
            brand=self.cfg.brand,
            slide=slide,
            day=self.cfg.day_number(date),
            date_label=date_label(date),
            letters=LETTERS,
            fonts=self.fonts_uri,
            logo=self.logo_uri,
        )

    def _shoot(self, html: str, out: Path | None, fit_fn: str = "fitSheet") -> dict:
        """Draws one slide; with out=None it only measures how well the text fits."""
        page = self._browser.new_page(viewport={"width": WIDTH, "height": HEIGHT}, device_scale_factor=1)
        with tempfile.NamedTemporaryFile("w", suffix=".html", dir=ROOT / "templates",
                                         delete=False, encoding="utf-8") as fh:
            fh.write(html)
            tmp = Path(fh.name)
        try:
            page.goto(tmp.as_uri(), wait_until="load")
            page.evaluate("document.fonts.ready")
            fit = page.evaluate(f"window.{fit_fn}()")
            if out is None:
                return fit
            png = out.with_suffix(".png")
            page.screenshot(path=str(png), clip={"x": 0, "y": 0, "width": WIDTH, "height": HEIGHT})
        finally:
            page.close()
            tmp.unlink(missing_ok=True)
        # Instagram's API accepts JPEG only. Baseline, sRGB, no EXIF.
        with Image.open(png) as im:
            im.convert("RGB").save(out, "JPEG", quality=90, subsampling=2, optimize=True)
        png.unlink(missing_ok=True)
        return fit

    def render_item(self, item: dict, date: dt.date, out_dir: Path) -> dict:
        """Writes both images; returns file names plus how much the text had to shrink."""
        out_dir.mkdir(parents=True, exist_ok=True)
        names = image_names(item["course_id"])
        fits = {}
        for slide, name in names.items():
            fits[slide] = self._shoot(self.html(item, date, slide), out_dir / name)
        notes = []
        for slide, fit in fits.items():
            if fit["overflow"]:
                notes.append(f"{slide} slide text is too long and is cut off; shorten it")
            elif fit["scale"] < 0.8:
                notes.append(f"{slide} slide text shrunk to {int(fit['scale'] * 100)}%; consider shortening")
        return {"images": names, "fit_notes": notes}


    # ── concept of the day ─────────────────────────────────
    def concept_html(self, item: dict, date: dt.date, slide: int) -> str:
        from .concept import SLIDES, doodle
        from .fonts import FAMILIES, ensure_fonts, font_face_css

        if not hasattr(self, "_concept_tpl"):
            self._concept_tpl = self.env.get_template("concept.html.j2")
            self._real_fonts = ensure_fonts()
        course = self.cfg.course(item["course_id"])
        headings = {2: item.get("formula_heading") or "The Formula", 3: "Study Trick", 4: "Common Mistakes"}
        hooks = {2: item.get("formula_hook") or "learn it once, use it always",
                 3: item.get("trick_hook") or "remember it like this",
                 4: item.get("mistakes_hook") or "where marks are lost!"}
        swipes = {1: "Swipe for the formula" if item.get("formulas") else "Swipe for the summary",
                  2: "Swipe for a memory trick", 3: "Swipe for common mistakes"}
        return self._concept_tpl.render(
            c=item, course=course, brand=self.cfg.brand, slide=slide, total=SLIDES,
            heading=headings.get(slide, ""), hook=hooks.get(slide, ""), swipe=swipes.get(slide, ""),
            doodle_svg=doodle(item.get("paper_name", "")), logo=self.logo_uri,
            font_css=font_face_css(self._real_fonts), families=FAMILIES,
        )

    def _concept_fit(self, item: dict, date: dt.date, slide: int, out: Path | None) -> dict:
        from .fonts import FontError, fallback_allowed

        fit = self._shoot(self.concept_html(item, date, slide), out, "fitSlide")
        bad = [f for f, ok in fit.get("fonts", {}).items() if not ok]
        if bad and not (fallback_allowed() and not self._real_fonts):
            raise FontError(f"The handwriting fonts didn't load ({', '.join(bad)}); not drawing the concept note.")
        return fit

    def measure_concept(self, item: dict, date: dt.date) -> list[str]:
        """Problems for slides whose text doesn't fit even at the smallest allowed size."""
        from .concept import SLIDE_FIELDS, SLIDE_NAMES, SLIDES

        problems = []
        for slide in range(1, SLIDES + 1):
            fit = self._concept_fit(item, date, slide, None)
            if fit["overflow"]:
                over = round(100 * fit["need"] / max(1, fit["room"]))   # height at full size
                problems.append(f"slide {slide} ({SLIDE_NAMES[slide]}) needs about {over}% of the space available; "
                                f"shorten {SLIDE_FIELDS[slide]} by about {max(10, over - 85)}%")
        return problems

    def render_concept(self, item: dict, date: dt.date, out_dir: Path) -> dict:
        from .concept import SLIDE_NAMES

        out_dir.mkdir(parents=True, exist_ok=True)
        names, notes, fits = concept_names(), [], []
        for slide, name in enumerate(names, 1):
            fit = self._concept_fit(item, date, slide, out_dir / name)
            fits.append({"slide": slide, "zoom": fit["zoom"], "overflow": fit["overflow"]})
            if fit["overflow"]:
                notes.append(f"slide {slide} ({SLIDE_NAMES[slide]}) text is too long and is cut off; shorten it")
            elif fit["zoom"] < 0.9:
                notes.append(f"slide {slide} ({SLIDE_NAMES[slide]}) text shrunk to {int(fit['zoom'] * 100)}%")
        return {"images": names, "fit_notes": notes, "fit": fits}


def contact_sheet(out_dir: Path, items: list[dict], dest: Path) -> Path:
    """One overview image of the whole batch: question + answer per course, three courses a row."""
    tw, th, gap, pair_gap = 300, 375, 10, 34
    per_row = 3
    rows = (len(items) + per_row - 1) // per_row
    width = per_row * (2 * tw + gap) + (per_row - 1) * pair_gap + 2 * pair_gap
    height = rows * th + (rows - 1) * pair_gap + 2 * pair_gap
    sheet = Image.new("RGB", (width, height), (236, 237, 240))
    for i, item in enumerate(items):
        r, c = divmod(i, per_row)
        x = pair_gap + c * (2 * tw + gap + pair_gap)
        y = pair_gap + r * (th + pair_gap)
        for j, key in enumerate(("question", "answer")):
            with Image.open(out_dir / item["images"][key]) as im:
                sheet.paste(im.resize((tw, th), Image.LANCZOS), (x + j * (tw + gap), y))
    sheet.save(dest, "JPEG", quality=88)
    return dest
