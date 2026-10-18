"""Offline tests: no API keys, no network. Run with:  python -m unittest discover tests"""

import datetime as dt
import json
import random
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mcq_agent import batch as B
from mcq_agent import config as C
from mcq_agent import generator as G
from mcq_agent import pipeline as P
from mcq_agent.__main__ import parse_regen_comment
from mcq_agent.caption import build_caption, post_ref

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = json.loads((ROOT / "samples" / "sample_batch.json").read_text(encoding="utf-8"))


def fake_mcq(**over):
    m = {
        "topic": "Inventory: EOQ",
        "question": "Annual demand 20,000 units, ordering cost ₹100, carrying cost ₹4. EOQ?",
        "options": ["1,000 units", "707 units", "1,414 units", "500 units"],
        "correct": "A",
        "explanation": "EOQ = √(2AO ÷ C) = √10,00,000 = 1,000 units.",
        "working": [{"label": "2AO ÷ C", "value": "10,00,000"}, {"label": "Square root", "value": "1,000"}],
        "why_not": {"B": "Missed the 2.", "C": "Divided by 2.", "D": "Average stock."},
        "exam_tip": "At EOQ, ordering cost = carrying cost.",
        "applicability": "", "confidence": "high", "reviewer_note": "",
    }
    m.update(over)
    return m


class FakeResponse:
    def __init__(self, payload, status=200):
        self._p, self.status_code = payload, status
        self.ok = status < 400
        self.content = json.dumps(payload).encode()
        self.text = json.dumps(payload)
        self.headers = {"content-type": "image/jpeg"}

    def json(self):
        return self._p

    def close(self):
        pass


class TempQueue(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.patches = [mock.patch.object(C, "QUEUE", self.tmp), mock.patch.object(B, "QUEUE", self.tmp)]
        for p in self.patches:
            p.start()
        self.cfg = C.Config()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)


class ShuffleTests(unittest.TestCase):
    def test_answer_text_and_reasons_follow_the_shuffle(self):
        for seed in range(20):
            m = fake_mcq()
            out = G.shuffle_options(m, random.Random(seed))
            self.assertEqual(out["options"][C.LETTERS.index(out["correct"])], "1,000 units")
            self.assertNotIn(out["correct"], out["why_not"])
            for letter, reason in out["why_not"].items():
                old = C.LETTERS[m["options"].index(out["options"][C.LETTERS.index(letter)])]
                self.assertEqual(m["why_not"][old], reason)

    def test_cross_referencing_options_are_not_shuffled(self):
        m = fake_mcq(options=["Only (a)", "Both (a) and (b)", "X", "Y"])
        self.assertEqual(G.shuffle_options(m, random.Random(1))["options"], m["options"])

    def test_validation_catches_letters_in_explanation(self):
        self.assertTrue(G.validate(fake_mcq(explanation="Option B is right because…")))
        self.assertFalse(G.validate(fake_mcq()))


class GeneratorTests(TempQueue):
    def test_rewrites_when_checker_disagrees_then_accepts(self):
        calls = []

        def fake_post(url, headers=None, json=None, timeout=None):
            tool = json["tools"][0]["name"]
            calls.append(tool)
            if tool == "submit_mcq":
                return FakeResponse({"content": [{"type": "tool_use", "name": tool, "input": fake_mcq()}]})
            # first check picks a wrong letter, second picks the real key
            user = json["messages"][0]["content"]
            right = next(l for l in user.splitlines() if "1,000 units" in l)[0]
            wrong = C.LETTERS[(C.LETTERS.index(right) + 1) % 4]
            answer = wrong if calls.count("submit_check") == 1 else right
            return FakeResponse({"content": [{"type": "tool_use", "name": tool, "input": {
                "answer": answer, "reasoning": "...", "issues": [], "severity": "none"}}]})

        course = self.cfg.course("ca_inter")
        paper = course["papers"][1]
        with mock.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test"}), \
             mock.patch.object(G.requests, "post", side_effect=fake_post):
            mcq = G.write_mcq(self.cfg, course, paper, dt.date(2026, 10, 20), [])
        self.assertEqual(mcq["attempts"], 2)
        self.assertEqual(calls, ["submit_mcq", "submit_check", "submit_mcq", "submit_check"])
        self.assertFalse(mcq["needs_check"])
        self.assertEqual(mcq["options"][C.LETTERS.index(mcq["correct"])], "1,000 units")

    def test_flags_for_review_when_never_confirmed(self):
        def fake_post(url, headers=None, json=None, timeout=None):
            tool = json["tools"][0]["name"]
            if tool == "submit_mcq":
                return FakeResponse({"content": [{"type": "tool_use", "name": tool, "input": fake_mcq()}]})
            return FakeResponse({"content": [{"type": "tool_use", "name": tool, "input": {
                "answer": "A", "reasoning": "", "issues": ["Two options defensible"], "severity": "major"}}]})

        course = self.cfg.course("ca_inter")
        with mock.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test"}), \
             mock.patch.object(G.requests, "post", side_effect=fake_post), mock.patch.object(G.time, "sleep"):
            mcq = G.write_mcq(self.cfg, course, course["papers"][0], dt.date(2026, 10, 20), [])
        self.assertTrue(mcq["needs_check"])
        self.assertIn("Not confirmed", mcq["check_notes"][0])


class ConfigTests(unittest.TestCase):
    def test_income_tax_basis_switches_for_may_2027(self):
        cfg = C.Config()
        paper = {"code": "Paper 3A", "name": "Income-tax Law", "law": "ca_income_tax"}
        self.assertIn("1961", cfg.law_text(paper, dt.date(2026, 12, 1)))
        self.assertIn("2025", cfg.law_text(paper, dt.date(2027, 3, 1)))

    def test_every_course_has_distinct_colour_and_time(self):
        cfg = C.Config()
        self.assertEqual(len({c["color"]["ink"] for c in cfg.courses}), 6)
        self.assertEqual(len({c["post_time"] for c in cfg.courses}), 6)

    def test_papers_rotate_daily(self):
        cfg = C.Config()
        c = cfg.course("ca_final")
        names = [cfg.paper_for(c, cfg.start_date + dt.timedelta(days=i))["name"] for i in range(5)]
        self.assertEqual(len(set(names)), 5)

    def test_regen_comment(self):
        cfg = C.Config()
        self.assertEqual(parse_regen_comment("/regen cma_final make it on WACC", cfg), ("cma_final", "make it on WACC"))
        for bad in ("/regen", "/regen nonsense", "looks good"):
            with self.assertRaises(SystemExit):
                parse_regen_comment(bad, cfg)


class LogoTests(unittest.TestCase):
    def test_checkerboard_removed_but_white_inside_logo_kept(self):
        try:
            import numpy  # noqa: F401
            import scipy  # noqa: F401
        except ImportError:
            self.skipTest("numpy/scipy not installed")
        from PIL import Image, ImageDraw
        from mcq_agent.logo import prepare_logo
        im = Image.new("RGB", (400, 400))
        d = ImageDraw.Draw(im)
        for y in range(0, 400, 10):                         # fake "transparent" background
            for x in range(0, 400, 10):
                d.rectangle([x, y, x + 9, y + 9], fill=(254, 254, 254) if (x // 10 + y // 10) % 2 == 0 else (214, 214, 214))
        d.ellipse([100, 100, 300, 300], fill=(20, 40, 90))     # logo: navy disc
        d.rectangle([170, 170, 230, 230], fill=(250, 250, 250))  # white patch inside the logo
        tmp = Path(tempfile.mkdtemp())
        im.save(tmp / "src.jpg", quality=92)
        out = prepare_logo(tmp / "src.jpg", tmp / "logo.png")
        logo = Image.open(out)
        self.assertEqual(logo.mode, "RGBA")
        self.assertLessEqual(abs(logo.width - 200), 6)          # trimmed to the disc
        cx, cy = logo.width // 2, logo.height // 2
        self.assertGreater(logo.getpixel((cx, cy))[3], 240)     # white patch kept
        self.assertEqual(logo.getpixel((2, 2))[3], 0)            # corner background gone
        shutil.rmtree(tmp, ignore_errors=True)


class CaptionTests(unittest.TestCase):
    def test_caption_limits(self):
        cfg = C.Config()
        for it in SAMPLE["items"]:
            cap = build_caption(cfg, it, dt.date(2026, 10, 19))
            self.assertLessEqual(len(cap), 2200)
            self.assertLessEqual(cap.count("#"), 5)
            self.assertIn(post_ref(it["course_id"], dt.date(2026, 10, 19)), cap)


class PublishTests(TempQueue):
    def _batch(self, date):
        from PIL import Image
        items = json.loads(json.dumps(SAMPLE["items"]))
        out = self.tmp / date.isoformat()
        out.mkdir(parents=True)
        for it in items:
            it["images"] = {"question": f"{it['course_id']}_q.jpg", "answer": f"{it['course_id']}_a.jpg"}
            for name in it["images"].values():
                Image.new("RGB", (1080, 1350), "white").save(out / name, "JPEG")
        B.save_batch(date, {"date": date.isoformat(), "items": items})

    def test_posts_due_items_once(self):
        date = dt.date(2026, 10, 19)
        self._batch(date)
        log = []

        def fake_get(url, params=None, timeout=None, **kw):
            if url.endswith("/media"):
                return FakeResponse({"data": []})
            if params and params.get("fields") == "status_code,status":
                return FakeResponse({"status_code": "FINISHED"})
            if params and params.get("fields") == "permalink":
                return FakeResponse({"permalink": "https://instagram.com/p/x"})
            return FakeResponse({})

        def fake_post(url, data=None, timeout=None, **kw):
            log.append((url.rsplit("/", 1)[-1], data.get("media_type") or data.get("is_carousel_item")))
            if url.endswith("media_publish"):
                return FakeResponse({"id": f"media{len(log)}"})
            return FakeResponse({"id": f"c{len(log)}"})

        env = {"IG_ACCESS_TOKEN": "t", "IG_USER_ID": "123"}
        with mock.patch.dict("os.environ", env), \
             mock.patch("mcq_agent.instagram.requests.get", side_effect=fake_get), \
             mock.patch("mcq_agent.instagram.requests.post", side_effect=fake_post), \
             mock.patch("mcq_agent.hosting.urls_for", return_value=(["https://x/q.jpg", "https://x/a.jpg"], "test")):
            code = P.publish_due(self.cfg, date, dt.time(10, 30), limit=5)
            self.assertEqual(code, 0)
            posted = B.load_posted(date)
            self.assertEqual(sorted(posted), ["ca_foundation", "cma_cat"])   # 07:55 and 09:55 slots
            # 2 image containers + 1 carousel + 1 publish per post
            self.assertEqual([k for k, _ in log].count("media_publish"), 2)
            self.assertEqual(log[2], ("media", "CAROUSEL"))
            log.clear()
            P.publish_due(self.cfg, date, dt.time(10, 30), limit=5)
            self.assertEqual(log, [])                                         # nothing posted twice

    def test_last_run_of_the_day_posts_everything_waiting(self):
        date = dt.date(2026, 10, 19)
        self._batch(date)
        with mock.patch.dict("os.environ", {"IG_ACCESS_TOKEN": "t", "IG_USER_ID": "1"}), \
             mock.patch("mcq_agent.instagram.Instagram.find_by_ref", return_value=None), \
             mock.patch("mcq_agent.instagram.Instagram.post_carousel",
                        return_value={"media_id": "m", "permalink": "p"}) as post, \
             mock.patch("mcq_agent.hosting.urls_for", return_value=(["u1", "u2"], "test")):
            P.publish_due(self.cfg, date, dt.time(15, 30))      # 4 due, limit 2
            self.assertEqual(post.call_count, 2)
            P.publish_due(self.cfg, date, dt.time(21, 0))       # final run: the other 4
            self.assertEqual(post.call_count, 6)
        self.assertEqual(len(B.load_posted(date)), 6)

    def test_review_text_lists_every_course(self):
        from mcq_agent.review import pr_body
        date = dt.date(2026, 10, 19)
        self._batch(date)
        body = pr_body(self.cfg, date, "me/mcq", "batch/2026-10-19")
        for c in self.cfg.courses:
            self.assertIn(c["name"], body)
        self.assertIn("Merge this pull request to approve", body)

    def test_unmerged_batch_posts_nothing(self):
        self.assertEqual(P.publish_due(self.cfg, dt.date(2030, 1, 1), dt.time(23, 0)), 0)
        self.assertEqual(P.publish_due(self.cfg, dt.date(2030, 1, 1), dt.time(23, 0), strict=True), 1)


if __name__ == "__main__":
    unittest.main()
