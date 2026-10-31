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
        "calculation": "A = 20000\nO = 100\nC = 4\nanswer = sqrt(2 * A * O / C)",
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
        self.cfg.reels["enabled"] = True          # most tests cover the MCQ reel too (switched off in config.yaml)

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

    def test_answer_lands_on_target_letter(self):
        for target in C.LETTERS:
            out = G.shuffle_options(fake_mcq(), random.Random(3), target)
            self.assertEqual(out["correct"], target)
            self.assertEqual(out["options"][C.LETTERS.index(target)], "1,000 units")
            self.assertEqual(sorted(out["options"]), sorted(fake_mcq()["options"]))

    def test_daily_keys_are_spread_out(self):
        ids = C.Config().course_ids()
        for d in range(60):
            keys = list(G.answer_letters(ids, dt.date(2026, 10, 1) + dt.timedelta(days=d)).values())
            self.assertEqual(set(keys), set(C.LETTERS))                       # all four letters every day
            self.assertLessEqual(max(keys.count(l) for l in C.LETTERS), 2)   # none more than twice

    def test_cross_referencing_options_are_not_shuffled(self):
        m = fake_mcq(options=["Only (a)", "Both (a) and (b)", "X", "Y"])
        self.assertEqual(G.shuffle_options(m, random.Random(1))["options"], m["options"])

    def test_validation_catches_crammed_working(self):
        bad = fake_mcq(working=[{"label": "Less: deposited", "value": "₹39,500+₹12,900=₹52,400"}])
        self.assertTrue(any("one short figure" in p for p in G.validate(bad)))

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
        with mock.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test", "CLAUDE_CODE_OAUTH_TOKEN": ""}), \
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
        with mock.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test", "CLAUDE_CODE_OAUTH_TOKEN": ""}), \
             mock.patch.object(G.requests, "post", side_effect=fake_post), mock.patch.object(G.time, "sleep"):
            mcq = G.write_mcq(self.cfg, course, course["papers"][0], dt.date(2026, 10, 20), [])
        self.assertTrue(mcq["needs_check"])
        self.assertIn("Not confirmed", mcq["check_notes"][0])


FAKE_CLAUDE = r'''#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
schema = json.loads(args[args.index("--json-schema") + 1])
prompt = sys.stdin.read()
assert "-p" in args and "--system-prompt-file" in args
assert args[args.index("--tools") + 1] == "", "built-in tools must be switched off"
assert "ANTHROPIC_API_KEY" not in os.environ, "API key must not reach Claude Code"
if "answer" in schema["properties"]:
    letter = next(l[0] for l in prompt.splitlines() if "1,000 units" in l)
    out = {"answer": letter, "reasoning": "", "issues": [], "severity": "none"}
else:
    out = json.loads(os.environ["FAKE_MCQ"])
print(json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": "", "structured_output": out}))
'''


class SubscriptionTests(TempQueue):
    def test_writes_mcq_through_claude_code_with_subscription_token(self):
        import os, stat
        bindir = Path(tempfile.mkdtemp())
        exe = bindir / "claude"
        exe.write_text(FAKE_CLAUDE)
        exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
        env = {"CLAUDE_CODE_OAUTH_TOKEN": "sub-token", "ANTHROPIC_API_KEY": "should-not-be-used",
               "FAKE_MCQ": json.dumps(fake_mcq()), "PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}"}
        course = self.cfg.course("ca_inter")
        with mock.patch.dict("os.environ", env), mock.patch.object(G.requests, "post") as api:
            self.assertEqual(G.auth_mode(), "subscription")
            mcq = G.write_mcq(self.cfg, course, course["papers"][1], dt.date(2026, 10, 20), [])
            api.assert_not_called()                      # never touched the paid API
        self.assertEqual(mcq["options"][C.LETTERS.index(mcq["correct"])], "1,000 units")
        self.assertFalse(mcq["needs_check"])
        shutil.rmtree(bindir, ignore_errors=True)

    def test_falls_back_to_api_key_when_subscription_fails(self):
        with mock.patch.dict("os.environ", {"CLAUDE_CODE_OAUTH_TOKEN": "t", "ANTHROPIC_API_KEY": "k"}), \
             mock.patch.object(G, "_call_claude_code", side_effect=G.GenerationError("token refused")), \
             mock.patch.object(G, "_call_api", return_value={"ok": True}) as api:
            self.assertEqual(G._call_claude("m", "s", "u", {"name": "x", "input_schema": {}}), {"ok": True})
            api.assert_called_once()


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


class SecretTests(unittest.TestCase):
    def test_instagram_errors_never_show_the_token(self):
        from mcq_agent.instagram import Instagram, InstagramError
        import requests as rq
        ig = Instagram("graph.instagram.com", "v26.0", "SECRET123", "1")
        boom = rq.ConnectionError("failed for url /me?access_token=SECRET123")
        with mock.patch("mcq_agent.instagram.requests.get", side_effect=boom), mock.patch("mcq_agent.instagram.time.sleep"):
            with self.assertRaises(InstagramError) as ctx:
                ig.account()
        self.assertNotIn("SECRET123", str(ctx.exception))


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


class RecentTopicTests(TempQueue):
    def test_writer_sees_other_days_including_later_ones(self):
        for d, topic in (("2026-10-18", "Old"), ("2026-10-19", "Same day"), ("2026-10-20", "Next day")):
            B.save_batch(dt.date.fromisoformat(d), {"items": [{"course_id": "ca_inter", "topic": topic, "question": "q"}]})
        topics = [r["topic"] for r in B.recent_items("ca_inter", dt.date(2026, 10, 19))]
        self.assertEqual(sorted(topics), ["Next day", "Old"])


def make_batch(tmp: Path, date: dt.date) -> dict:
    """Sample batch with blank images, saved under the temporary queue."""
    from PIL import Image
    items = json.loads(json.dumps(SAMPLE["items"]))
    out = tmp / date.isoformat()
    out.mkdir(parents=True, exist_ok=True)
    for it in items:
        it["images"] = {"question": f"{it['course_id']}_q.jpg", "answer": f"{it['course_id']}_a.jpg"}
        for name in it["images"].values():
            Image.new("RGB", (1080, 1350), "white").save(out / name, "JPEG")
    batch = {"date": date.isoformat(), "items": items}
    B.save_batch(date, batch)
    return batch


class AutoModeTests(TempQueue):
    DATE = dt.date(2026, 10, 21)

    def _publish(self, at):
        with mock.patch.dict("os.environ", {"IG_ACCESS_TOKEN": "t", "IG_USER_ID": "1"}), \
             mock.patch("mcq_agent.instagram.Instagram.find_by_ref", return_value=None), \
             mock.patch("mcq_agent.instagram.Instagram.post_carousel",
                        return_value={"media_id": "m", "permalink": "p"}), \
             mock.patch("mcq_agent.hosting.urls_for", return_value=(["u1", "u2"], "test")):
            P.publish_due(self.cfg, self.DATE, at)
        return B.load_posted(self.DATE)

    def test_unconfirmed_answer_key_is_held_until_approved(self):
        batch = make_batch(self.tmp, self.DATE)
        it = B.find_item(batch, "cma_cat")
        it.update(serious=True, serious_reason="The checker could not confirm the answer key")
        P.set_hold(it)
        B.save_batch(self.DATE, batch)
        posted = self._publish(dt.time(21, 0))
        self.assertEqual(len(posted), 5)
        self.assertNotIn("cma_cat", posted)
        P.release(self.DATE, "cma_cat")
        self.assertIn("cma_cat", self._publish(dt.time(21, 30)))

    def test_cut_off_text_is_held(self):
        it = {"fit_notes": ["answer slide text is too long and is cut off; shorten it"]}
        P.set_hold(it)
        self.assertTrue(it["hold"])
        self.assertIn("cut off", it["hold_reason"])
        it = {"fit_notes": ["answer slide text shrunk to 78%; consider shortening"]}
        P.set_hold(it)
        self.assertFalse(it["hold"])                       # shrunk but readable: posts normally

    def test_hold_command_and_posted_mcqs_cannot_change(self):
        make_batch(self.tmp, self.DATE)
        P.hold(self.DATE, "ca_inter")
        self.assertTrue(B.find_item(B.load_batch(self.DATE), "ca_inter")["hold"])
        B.save_posted(self.DATE, {"ca_foundation": {"media_id": "x"}})
        with self.assertRaises(SystemExit):
            P.hold(self.DATE, "ca_foundation")
        with self.assertRaises(SystemExit):
            P.regenerate(self.cfg, self.DATE, "ca_foundation")

    def test_regenerated_mcq_that_passes_is_released(self):
        batch = make_batch(self.tmp, self.DATE)
        it = B.find_item(batch, "ca_final")
        it.update(serious=True)
        P.set_hold(it)
        B.save_batch(self.DATE, batch)
        good = json.loads(json.dumps(it)); good.update(serious=False, topic="New topic")

        class FakeRenderer:
            def __init__(self, cfg): pass
            def __enter__(self): return self
            def __exit__(self, *a): pass
            def render_item(self, item, date, out):
                return {"images": {"question": "ca_final_q.jpg", "answer": "ca_final_a.jpg"}, "fit_notes": []}

        with mock.patch.object(P, "_fill_item", return_value=good), mock.patch.object(P, "Renderer", FakeRenderer), \
             mock.patch.object(P, "_preview"):
            item = P.regenerate(self.cfg, self.DATE, "ca_final")
        self.assertFalse(item["hold"])
        self.assertEqual(B.find_item(B.load_batch(self.DATE), "ca_final")["topic"], "New topic")

    def test_comment_commands(self):
        from mcq_agent.__main__ import parse_command
        self.assertEqual(parse_command("/approve CA_INTER", self.cfg), ("approve", "ca_inter", ""))
        self.assertEqual(parse_command("/regen cma_final make it on WACC", self.cfg),
                         ("regen", "cma_final", "make it on WACC"))
        self.assertEqual(parse_command("thanks!\n/hold ca_final", self.cfg), ("hold", "ca_final", ""))
        for bad in ("/hold nonsense", "/approve", "looks good"):
            with self.assertRaises(SystemExit):
                parse_command(bad, self.cfg)

    def test_command_cli_writes_summary_for_the_reply(self):
        from mcq_agent.__main__ import main
        make_batch(self.tmp, self.DATE)
        out = self.tmp / "gh_out.txt"
        main(["command", "--date", self.DATE.isoformat(), "--comment", "/hold cma_inter", "--github-output", str(out)])
        text = out.read_text()
        self.assertIn("action=hold", text)
        self.assertIn("course=cma_inter", text)
        self.assertIn("summary=", text)

    def test_report_mentions_you_only_when_something_is_held(self):
        from mcq_agent.review import report, report_title
        batch = make_batch(self.tmp, self.DATE)
        body = report(self.cfg, self.DATE, "cacmagyan/daily-mcq", owner="cacmagyan")
        self.assertNotIn("@cacmagyan", body)
        self.assertIn("All six post automatically", body)
        self.assertFalse(report_title(self.cfg, self.DATE).startswith("⛔"))
        it = B.find_item(batch, "ca_inter")
        it.update(serious=True, serious_reason="The checker could not confirm the answer key")
        P.set_hold(it)
        B.save_batch(self.DATE, batch)
        body = report(self.cfg, self.DATE, "cacmagyan/daily-mcq", owner="cacmagyan")
        self.assertIn("@cacmagyan", body)
        self.assertIn("On hold", body)
        self.assertIn("/approve ca_inter", body)
        self.assertTrue(report_title(self.cfg, self.DATE).startswith("⛔ Action needed: MCQs for 2026-10-21"))

    def test_old_batches_without_hold_fields_still_post(self):
        make_batch(self.tmp, self.DATE)                    # like the 19th and 20th: no hold fields at all
        self.assertEqual(len(self._publish(dt.time(21, 0))), 6)


CONCEPTS = json.loads((ROOT / "samples" / "sample_concept.json").read_text(encoding="utf-8"))["items"]


def make_concept(tmp: Path, date: dt.date, course_id: str = "cma_cat", **over) -> dict:
    """A concept note with four blank slides, saved under the temporary queue."""
    from PIL import Image
    item = json.loads(json.dumps(next(c for c in CONCEPTS if c["course_id"] == course_id)))
    item.update(kind="concept", author="Ranjith Shivahari" if course_id == "cma_cat" else "Rahul kp",
                images=[f"concept_{i}.jpg" for i in range(1, 5)], fit_notes=[])
    item.update(over)
    out = tmp / date.isoformat()
    out.mkdir(parents=True, exist_ok=True)
    for name in item["images"]:
        Image.new("RGB", (1080, 1350), "white").save(out / name, "JPEG")
    B.save_concept(date, item)
    return item


class AuthorTests(unittest.TestCase):
    def setUp(self):
        self.cfg = C.Config()

    def paper(self, course_id, code, part=None):
        return next(p for p in self.cfg.course(course_id)["papers"]
                    if p["code"] == code and p.get("part") == part)

    def test_law_sm_and_audit_papers_are_ranjith(self):
        ranjith = [("ca_foundation", "Paper 2"), ("cma_cat", "Paper 1B"), ("ca_inter", "Paper 2"),
                   ("ca_inter", "Paper 5"), ("ca_inter", "Paper 6B"), ("cma_inter", "Paper 5"),
                   ("ca_final", "Paper 3"), ("cma_final", "Paper 13"), ("cma_final", "Paper 17")]
        for cid, code in ranjith:
            self.assertEqual(self.cfg.author_for(self.paper(cid, code)), "Ranjith Shivahari", (cid, code))
        for cid, code in [("ca_foundation", "Paper 1"), ("ca_inter", "Paper 4"), ("ca_inter", "Paper 3A"),
                          ("cma_final", "Paper 16"), ("ca_final", "Paper 1")]:
            self.assertEqual(self.cfg.author_for(self.paper(cid, code)), "Rahul kp", (cid, code))

    def test_mixed_cma_inter_papers_split_by_half(self):
        self.assertEqual(self.cfg.author_for(self.paper("cma_inter", "Paper 10", "Auditing")), "Ranjith Shivahari")
        self.assertEqual(self.cfg.author_for(self.paper("cma_inter", "Paper 10", "Corporate Accounting")), "Rahul kp")
        self.assertEqual(self.cfg.author_for(self.paper("cma_inter", "Paper 9", "Strategic Management")), "Ranjith Shivahari")
        self.assertEqual(self.cfg.author_for(self.paper("cma_inter", "Paper 9", "Operations Management")), "Rahul kp")
        p = self.paper("cma_inter", "Paper 10", "Auditing")
        self.assertEqual(self.cfg.paper_title(p), "Corporate Accounting and Auditing (Auditing)")
        self.assertIn("only the Auditing part", self.cfg.paper_prompt(p))

    def test_already_prepared_days_keep_their_papers(self):
        # the 19th and 20th were written before the paper list changed
        cma = self.cfg.course("cma_inter")
        self.assertEqual(self.cfg.paper_for(cma, dt.date(2026, 10, 19))["name"], "Cost Accounting")
        self.assertEqual(self.cfg.paper_for(cma, dt.date(2026, 10, 20))["name"], "Financial Accounting")

    def test_mcqs_are_signed_by_the_papers_author(self):
        # an MCQ written before the switch (no author field), like the 20th's law MCQ, gets it on a redraw
        item = {"course_id": "ca_foundation", "paper_code": "Paper 2", "paper_name": "Business Laws"}
        P._sign(self.cfg, item)
        self.assertEqual(item["author"], "Ranjith Shivahari")
        item = {"course_id": "cma_inter", "paper_code": "Paper 10", "paper_name": "Corporate Accounting and Auditing (Corporate Accounting)"}
        P._sign(self.cfg, item)
        self.assertEqual(item["author"], "Rahul kp")
        self.assertIn("Prepared by Rahul kp", build_caption(self.cfg, dict(fake_mcq(), **item), dt.date(2026, 10, 21)))
        with mock.patch.dict(self.cfg.authors, {"show_on_mcqs": False}):
            P._sign(self.cfg, item)
        self.assertNotIn("author", item)


class ConceptScheduleTests(unittest.TestCase):
    def setUp(self):
        self.cfg = C.Config()
        self.start = dt.date.fromisoformat(self.cfg.concepts["start_date"])

    def test_one_course_a_day_in_order(self):
        ids = [self.cfg.concept_course(self.start + dt.timedelta(days=i))["id"] for i in range(7)]
        self.assertEqual(ids, self.cfg.concepts["courses"] + [self.cfg.concepts["courses"][0]])

    def test_paper_is_tomorrows_mcq_paper(self):
        for i in range(10):
            d = self.start + dt.timedelta(days=i)
            course = self.cfg.concept_course(d)
            self.assertEqual(self.cfg.concept_paper(d), self.cfg.paper_for(course, d + dt.timedelta(days=1)))

    def test_nothing_before_the_start_date(self):
        self.assertFalse(self.cfg.concept_due(self.start - dt.timedelta(days=1)))
        self.assertTrue(self.cfg.concept_due(self.start))

    def test_publish_schedule_has_the_concept_run(self):
        wf = (ROOT / ".github" / "workflows" / "publish.yml").read_text()
        h, m = map(int, self.cfg.concept_time().split(":"))
        utc = (h * 60 + m - 330) % 1440
        self.assertIn(f'cron: "{(utc + 2) % 60} {(utc + 2) // 60} * * *"', wf)


class ConceptWriterTests(TempQueue):
    def _run(self, severities):
        calls = []
        note = {k: v for k, v in CONCEPTS[0].items() if k not in ("course_id", "paper_code", "paper_name")}

        def fake_post(url, headers=None, json=None, timeout=None):
            tool = json["tools"][0]["name"]
            calls.append((tool, json["system"]))
            if tool == "submit_concept":
                return FakeResponse({"content": [{"type": "tool_use", "name": tool, "input": note}]})
            sev = severities[min(sum(1 for t, _ in calls if t == "submit_check") - 1, len(severities) - 1)]
            issues = ["formula 1: the 2 is missing"] if sev == "major" else []
            return FakeResponse({"content": [{"type": "tool_use", "name": tool, "input": {"issues": issues, "severity": sev}}]})

        from mcq_agent import concept as K
        course = self.cfg.course("cma_inter")
        paper = course["papers"][0]
        with mock.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test", "CLAUDE_CODE_OAUTH_TOKEN": ""}), \
             mock.patch.object(G.requests, "post", side_effect=fake_post):
            out = K.write_concept(self.cfg, course, paper, dt.date(2026, 10, 26), [])
        return out, calls

    def test_rewrites_after_a_major_error_then_accepts(self):
        out, calls = self._run(["major", "none"])
        # two independent checks per draft; the first draft fails the first check, so it is rewritten
        self.assertEqual([t for t, _ in calls], ["submit_concept", "submit_check", "submit_check",
                                                 "submit_concept", "submit_check", "submit_check"])
        self.assertFalse(out["serious"])
        self.assertEqual(out["attempts"], 2)
        self.assertIn("signed by Rahul kp", calls[0][1])

    def test_held_when_errors_are_never_fixed(self):
        out, _ = self._run(["major"])
        self.assertTrue(out["serious"])
        item = dict(out, fit_notes=[])
        P.set_hold(item)
        self.assertTrue(item["hold"])

    def test_next_days_mcq_is_asked_to_test_the_concept(self):
        d = dt.date(2026, 10, 26)
        make_concept(self.tmp, d, "cma_inter")
        self.assertEqual(P.concept_link("cma_inter", d + dt.timedelta(days=1))["topic"], "Economic Order Quantity (EOQ)")
        self.assertIsNone(P.concept_link("ca_inter", d + dt.timedelta(days=1)))
        seen = {}

        def fake_post(url, headers=None, json=None, timeout=None):
            tool = json["tools"][0]["name"]
            if tool == "submit_mcq":
                seen["prompt"] = json["messages"][0]["content"]
                return FakeResponse({"content": [{"type": "tool_use", "name": tool, "input": fake_mcq()}]})
            user = json["messages"][0]["content"]
            right = next(l for l in user.splitlines() if "1,000 units" in l)[0]
            return FakeResponse({"content": [{"type": "tool_use", "name": tool, "input": {
                "answer": right, "reasoning": "", "issues": [], "severity": "none"}}]})

        with mock.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test", "CLAUDE_CODE_OAUTH_TOKEN": ""}), \
             mock.patch.object(G.requests, "post", side_effect=fake_post):
            item = P._fill_item(self.cfg, self.cfg.course("cma_inter"), d + dt.timedelta(days=1))
        self.assertIn("Yesterday's concept note for this course was on: Economic Order Quantity", seen["prompt"])
        self.assertEqual(item["linked_concept"], "Economic Order Quantity (EOQ)")


class MergePostedTests(TempQueue):
    def test_records_from_two_runs_are_both_kept(self):
        d = dt.date(2026, 10, 19)
        B.save_posted(d, {"ca_foundation": {"media_id": "1"}, "ca_inter": {"media_id": "2"}})   # already on main
        saved = Path(tempfile.mkdtemp())
        (saved / "queue" / d.isoformat()).mkdir(parents=True)
        (saved / "queue" / d.isoformat() / "posted.json").write_text(json.dumps(
            {"ca_foundation": {"media_id": "1"}, "ca_inter": {"media_id": "2", "note": "found existing post"},
             "cma_inter": {"media_id": "3"}}))
        self.assertEqual(B.merge_posted(saved), ["2026-10-19: cma_inter"])
        merged = B.load_posted(d)
        self.assertEqual(sorted(merged), ["ca_foundation", "ca_inter", "cma_inter"])
        self.assertNotIn("note", merged["ca_inter"])          # the first record stays as it was
        self.assertEqual(B.merge_posted(saved), [])             # nothing new the second time
        shutil.rmtree(saved, ignore_errors=True)


class CatchUpTests(TempQueue):
    """Starting concept notes on a day whose MCQs (and tomorrow's) were already written."""
    TODAY = dt.date(2026, 10, 19)

    def test_todo_tells_the_evening_run_what_is_missing(self):
        from mcq_agent.__main__ import main
        import io, contextlib
        def todo(d):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                main(["todo", "--date", d.isoformat()])
            return buf.getvalue().strip()
        self.assertEqual(todo(self.TODAY), "all")
        make_batch(self.tmp, self.TODAY)
        with mock.patch.dict(self.cfg.concepts, {"start_date": "2026-10-19"}), \
             mock.patch("mcq_agent.__main__.Config", return_value=self.cfg):
            self.assertEqual(todo(self.TODAY), "concept")
            make_concept(self.tmp, self.TODAY, "ca_foundation")
            self.assertEqual(todo(self.TODAY), "none")

    def test_note_teaches_tomorrows_existing_mcq_from_its_paper(self):
        make_batch(self.tmp, self.TODAY)
        nxt = make_batch(self.tmp, self.TODAY + dt.timedelta(days=1))
        fnd = B.find_item(nxt, "ca_foundation")
        fnd.update(paper_code="Paper 1", paper_name="Accounting", topic="Bank Reconciliation Statement")
        B.save_batch(self.TODAY + dt.timedelta(days=1), nxt)
        with mock.patch.dict(self.cfg.concepts, {"start_date": "2026-10-19"}):
            base = P._concept_base(self.cfg, self.TODAY)
        self.assertEqual(base["course_id"], "ca_foundation")
        self.assertEqual((base["paper_code"], base["paper_name"]), ("Paper 1", "Accounting"))   # not the rotation's Business Laws
        self.assertEqual(base["linked_mcq"], "Bank Reconciliation Statement")
        self.assertEqual(base["author"], "Rahul kp")
        seen = {}

        def fake_write(cfg, course, paper, date, recent, instruction="", topic="", fit_check=None):
            seen.update(paper=paper["name"], topic=topic)
            return {k: v for k, v in CONCEPTS[1].items() if k not in ("course_id", "paper_code", "paper_name")}

        class FakeRenderer:
            def render_concept(self, item, date, out):
                return {"images": [f"concept_{i}.jpg" for i in range(1, 5)], "fit_notes": [], "fit": []}

        with mock.patch.dict(self.cfg.concepts, {"start_date": "2026-10-19"}), \
             mock.patch("mcq_agent.concept.write_concept", fake_write):
            item = P._make_concept(self.cfg, FakeRenderer(), self.TODAY)
        self.assertEqual(seen, {"paper": "Accounting", "topic": "Bank Reconciliation Statement"})
        self.assertIn("Tomorrow's CA Foundation MCQ (7:55 AM) tests this concept.", item["caption"])

    def test_concept_only_leaves_the_mcqs_alone(self):
        batch = make_batch(self.tmp, self.TODAY)
        before = json.dumps(batch["items"], sort_keys=True)
        with mock.patch.dict(self.cfg.concepts, {"start_date": "2026-10-26"}):
            with self.assertRaises(SystemExit):              # not due yet: says so instead of doing nothing
                P.prepare(self.cfg, self.TODAY, ["concept"])
        with mock.patch.dict(self.cfg.concepts, {"start_date": "2026-10-19"}), \
             mock.patch.object(P, "Renderer") as R, \
             mock.patch.object(P, "_make_concept", return_value={"kind": "concept", "course_id": "ca_foundation", "topic": "BRS"}):
            P.prepare(self.cfg, self.TODAY, ["concept"])
        self.assertEqual(json.dumps(B.load_batch(self.TODAY)["items"], sort_keys=True), before)
        self.assertEqual(B.load_concept(self.TODAY)["topic"], "BRS")


class StrongerCheckTests(TempQueue):
    """Code-checked arithmetic, two solvers for tax/law, checker fallback, and the topic switch."""

    def setUp(self):
        super().setUp()
        G._checker_unavailable.clear()
        self.models_patch = mock.patch.dict(self.cfg.models, {"strong_checks": "all"})   # these tests use the strong checker
        self.models_patch.start()
        self.addCleanup(self.models_patch.stop)

    def run_writer(self, course_id, paper_code, drafts, solver, fail_model=None):
        """drafts: MCQs the writer returns in turn; solver(n, user, model) -> the letter the n-th check picks."""
        log = []

        def fake_call(model, system, user, tool, max_tokens=2000):
            if fail_model and model == fail_model:
                log.append(("unavailable", model))
                raise G.GenerationError("model not available on this plan")
            if tool["name"] == "submit_mcq":
                log.append(("write", model))
                return json.loads(json.dumps(drafts[min(sum(1 for k, _ in log if k == "write") - 1, len(drafts) - 1)]))
            log.append(("check", model))
            n = sum(1 for k, _ in log if k == "check")
            letter = solver(n, user, model)
            return {"answer": letter, "reasoning": "", "issues": [], "severity": "none"}

        course = self.cfg.course(course_id)
        paper = next(x for x in course["papers"] if x["code"] == paper_code)
        with mock.patch.object(G, "_call_claude", side_effect=fake_call):
            mcq = G.write_mcq(self.cfg, course, paper, dt.date(2026, 10, 21), [])
        return mcq, log

    @staticmethod
    def right(user):
        return next(l for l in user.splitlines() if "1,000 units" in l)[0]

    def test_wrong_arithmetic_is_rewritten_before_any_check(self):
        bad = fake_mcq(calculation="A = 20000\nO = 100\nC = 4\nanswer = sqrt(A * O / C)")   # forgot the 2
        mcq, log = self.run_writer("ca_inter", "Paper 4", [bad, fake_mcq()], lambda n, u, m: self.right(u))
        self.assertEqual([k for k, _ in log], ["write", "write", "check"])
        self.assertFalse(mcq["serious"])

    def test_tax_and_law_need_two_solvers_to_agree(self):
        def solver(n, user, model):
            right = self.right(user)
            return C.LETTERS[(C.LETTERS.index(right) + 1) % 4] if n == 2 else right   # 2nd solver disagrees once
        mcq, log = self.run_writer("ca_inter", "Paper 3A", [fake_mcq()], solver)
        self.assertEqual([k for k, _ in log], ["write", "check", "check", "write", "check", "check"])
        self.assertEqual({m for k, m in log if k == "check"}, {"claude-opus-5-5", "claude-sonnet-5-5"})
        self.assertFalse(mcq["serious"])
        self.assertTrue(mcq["law_sensitive"])

    def test_checker_falls_back_to_writer_model_once(self):
        mcq, log = self.run_writer("ca_inter", "Paper 4", [fake_mcq()], lambda n, u, m: self.right(u),
                                   fail_model="claude-opus-5-5")
        self.assertEqual(log, [("write", "claude-sonnet-5-5"), ("unavailable", "claude-opus-5-5"),
                               ("check", "claude-sonnet-5-5")])
        self.assertFalse(mcq["serious"])
        mcq, log = self.run_writer("ca_inter", "Paper 4", [fake_mcq()], lambda n, u, m: self.right(u),
                                   fail_model="claude-opus-5-5")
        self.assertNotIn("unavailable", [k for k, _ in log])            # not tried again in the same run

    def test_switches_topic_before_holding(self):
        def solver(n, user, model):
            right = self.right(user)
            return C.LETTERS[(C.LETTERS.index(right) + 1) % 4] if n <= 3 else right   # first topic never confirmed
        mcq, log = self.run_writer("ca_inter", "Paper 4", [fake_mcq()], solver)
        self.assertEqual(sum(1 for k, _ in log if k == "write"), 4)
        self.assertFalse(mcq["serious"])
        self.assertIn("Switched to a new topic", mcq["check_notes"][0])

    def test_held_only_when_the_new_topic_fails_too(self):
        def solver(n, user, model):
            return C.LETTERS[(C.LETTERS.index(self.right(user)) + 1) % 4]
        mcq, log = self.run_writer("ca_inter", "Paper 4", [fake_mcq()], solver)
        self.assertEqual(sum(1 for k, _ in log if k == "write"), 5)     # 3 tries + 2 on a new topic
        self.assertTrue(mcq["serious"])

    def test_a_failing_switch_still_holds_the_first_draft(self):
        calls = {"write": 0}

        def fake_call(model, system, user, tool, max_tokens=2000):
            if tool["name"] == "submit_mcq":
                calls["write"] += 1
                if calls["write"] > 3:
                    raise G.GenerationError("usage limit reached")
                return fake_mcq()
            return {"answer": C.LETTERS[(C.LETTERS.index(self.right(user)) + 1) % 4],
                    "reasoning": "", "issues": [], "severity": "none"}

        course = self.cfg.course("ca_inter")
        with mock.patch.object(G, "_call_claude", side_effect=fake_call):
            mcq = G.write_mcq(self.cfg, course, course["papers"][1], dt.date(2026, 10, 21), [])
        self.assertTrue(mcq["serious"])                                  # held, not crashed
        self.assertEqual(mcq["topic"], "Inventory: EOQ")

    def test_traps_reach_the_writer_and_checker(self):
        seen = {}

        def fake_call(model, system, user, tool, max_tokens=2000):
            seen[tool["name"]] = system
            if tool["name"] == "submit_mcq":
                return fake_mcq()
            return {"answer": self.right(user), "reasoning": "", "issues": [], "severity": "none"}

        course = self.cfg.course("ca_foundation")
        paper = course["papers"][0]                                       # Accounting
        with mock.patch.object(G, "_call_claude", side_effect=fake_call):
            G.write_mcq(self.cfg, course, paper, dt.date(2026, 10, 21), [])
        for name in ("submit_mcq", "submit_check"):
            self.assertIn("Known traps", seen[name])
            self.assertIn("starting from the Pass Book balance", seen[name])


class SafeCalcTests(unittest.TestCase):
    def test_blocks_anything_but_arithmetic(self):
        from mcq_agent.safecalc import CalcError, evaluate
        self.assertEqual(evaluate("cost = 500000\nrate = 0.2\nanswer = cost * (1 - rate) * rate"), 80000)
        for bad in ("import os", "answer = __import__('os')", "answer = (1).real", "answer = open('f')",
                    "answer = [1]", "x = 2\nanswer = x ** 1000", "answer = y", "y = 1"):
            with self.assertRaises(CalcError, msg=bad):
                evaluate(bad)

    def test_losses_and_lookalike_options(self):
        from mcq_agent.safecalc import check_answer
        opts = ["Loss ₹5,000", "Profit ₹5,000", "Loss ₹2,500", "Profit ₹7,500"]
        self.assertEqual(check_answer("answer = 20000 - 25000", opts, 0), [])            # -5000 shown as a loss
        self.assertTrue(check_answer("answer = 20000 - 25000", opts, 1))                 # a profit key is caught
        self.assertTrue(check_answer("answer = 1000", ["₹1,000", "₹1000", "₹2,000", "₹500"], 0))   # same answer twice

    def test_reads_indian_numbers(self):
        from mcq_agent.safecalc import numbers_in
        self.assertEqual(numbers_in("₹1,45,800"), [(145800.0, 0)])
        self.assertEqual(numbers_in("₹2.5 lakh"), [(250000.0, 0)])
        self.assertEqual(numbers_in("12.5%"), [(12.5, 1)])
        self.assertEqual(numbers_in("₹3 crore"), [(30000000.0, 0)])


class ConceptPostingTests(TempQueue):
    DATE = dt.date(2026, 10, 26)

    def _publish(self, at):
        calls = []

        def post(self_ig, urls, caption, alts):
            calls.append((len(urls), caption, alts))
            return {"media_id": "m", "permalink": "p"}

        with mock.patch.dict("os.environ", {"IG_ACCESS_TOKEN": "t", "IG_USER_ID": "1"}), \
             mock.patch("mcq_agent.instagram.Instagram.find_by_ref", return_value=None), \
             mock.patch("mcq_agent.instagram.Instagram.post_carousel", post), \
             mock.patch("mcq_agent.hosting.urls_for", side_effect=lambda paths, cfg: ([str(p) for p in paths], "test")):
            P.publish_due(self.cfg, self.DATE, at, limit=10)
        return calls

    def test_concept_posts_at_its_time_as_four_slides(self):
        make_batch(self.tmp, self.DATE)
        make_concept(self.tmp, self.DATE)
        self._publish(dt.time(19, 0))
        self.assertNotIn("concept", B.load_posted(self.DATE))
        calls = self._publish(dt.time(19, 42))
        self.assertIn("concept", B.load_posted(self.DATE))
        n, caption, alts = calls[-1]
        self.assertEqual((n, len(alts)), (4, 4))
        self.assertIn("Notes by Ranjith Shivahari", caption)
        self.assertIn("ref concept-261026", caption)
        self.assertLessEqual(caption.count("#"), 5)

    def test_held_concept_waits_for_approve(self):
        make_batch(self.tmp, self.DATE)
        make_concept(self.tmp, self.DATE, serious=True, serious_reason="The checker found errors that weren't fixed")
        c = B.load_concept(self.DATE); P.set_hold(c); B.save_concept(self.DATE, c)
        self._publish(dt.time(21, 0))
        posted = B.load_posted(self.DATE)
        self.assertEqual(len(posted), 6)                      # all MCQs still post
        self.assertNotIn("concept", posted)
        from mcq_agent.review import report, report_title
        self.assertTrue(report_title(self.cfg, self.DATE).startswith("⛔ Action needed"))
        body = report(self.cfg, self.DATE, "cacmagyan/daily-mcq", owner="cacmagyan")
        self.assertIn("@cacmagyan", body)
        self.assertIn("/approve concept", body)
        P.release(self.DATE, "concept")
        self._publish(dt.time(21, 5))
        self.assertIn("concept", B.load_posted(self.DATE))

    def test_days_without_a_concept_note_post_normally(self):
        make_batch(self.tmp, self.DATE)
        self._publish(dt.time(21, 0))
        self.assertEqual(len(B.load_posted(self.DATE)), 6)

    def test_concept_commands_and_report_row(self):
        from mcq_agent.__main__ import parse_command
        from mcq_agent.review import report
        self.assertEqual(parse_command("/regen concept make it on JIT", self.cfg), ("regen", "concept", "make it on JIT"))
        self.assertEqual(parse_command("/hold concept", self.cfg), ("hold", "concept", ""))
        make_batch(self.tmp, self.DATE)
        make_concept(self.tmp, self.DATE)
        P.hold(self.DATE, "concept")
        self.assertTrue(B.load_concept(self.DATE)["hold"])
        body = report(self.cfg, self.DATE, "cacmagyan/daily-mcq", owner="cacmagyan")
        self.assertIn("19:40 | 📒 Concept (CMA CAT)", body)
        self.assertIn("concept_4.jpg", body)


class ConceptRenderTests(unittest.TestCase):
    def test_samples_fit_and_are_signed_by_the_papers_author(self):
        import os
        if os.environ.get("GITHUB_ACTIONS"):
            self.skipTest("local drawing test")
        from mcq_agent.render import Renderer
        cfg = C.Config()
        tmp = Path(tempfile.mkdtemp())
        try:
            with mock.patch.dict("os.environ", {"MCQ_FONT_FALLBACK": "1"}), Renderer(cfg) as r:
                for c in CONCEPTS:
                    item = dict(c, kind="concept")
                    paper = next(p for p in cfg.course(c["course_id"])["papers"] if p["code"] == c["paper_code"])
                    item["author"] = cfg.author_for(paper)
                    res = r.render_concept(item, dt.date(2026, 10, 26), tmp)
                    self.assertEqual(res["fit_notes"], [], c["course_id"])
                    html = r.concept_html(item, dt.date(2026, 10, 26), 4)
                    self.assertIn(item["author"], html)
        finally:
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


class FakeReelRenderer:
    """Draws a few plain frames instead of the real page, so encoding can be tested quickly."""

    def __init__(self, scale=1.0, overflow=False, scale_with_presenter=None):
        self.fit = {"scale": scale, "overflow": overflow}
        self.guy_scale = scale if scale_with_presenter is None else scale_with_presenter
        self.calls = []

    def reel_frames(self, item, date, why, think, answer, fps, frames_dir, with_presenter=True, outro=2.5, share=""):
        from PIL import Image
        self.calls.append((item["course_id"], why, with_presenter))
        self.timing = (think, answer, outro, share)
        fit = dict(self.fit, scale=self.guy_scale) if with_presenter else self.fit
        if frames_dir is None:
            return {"fit": fit, "frames": []}
        frames_dir.mkdir(parents=True, exist_ok=True)
        frames = []
        for i, (colour, secs) in enumerate((("white", think), ("#E4F4EA", answer), ("#FFFFFF", outro))):
            path = frames_dir / f"f{i}.png"
            Image.new("RGB", (1080, 1920), colour).save(path)
            frames.append((path, secs))
        return {"fit": fit, "frames": frames}


class ReelTests(TempQueue):
    DATE = dt.date(2026, 10, 21)

    def test_one_course_a_day_never_the_concept_course(self):
        start = dt.date.fromisoformat(self.cfg.reels["start_date"])
        days = [start + dt.timedelta(days=i) for i in range(12)]
        ids = [self.cfg.reel_courses()[self.cfg.reel_course_index(d)] for d in days]
        self.assertEqual(sorted(ids[:6]), sorted(self.cfg.course_ids()))
        self.assertEqual(ids[:6], ids[6:])
        for d, cid in zip(days, ids):
            self.assertNotEqual(cid, self.cfg.concept_course(d)["id"])

    def test_held_or_failed_mcqs_are_skipped(self):
        from mcq_agent import reel as R
        batch = make_batch(self.tmp, self.DATE)
        first = self.cfg.reel_courses()[self.cfg.reel_course_index(self.DATE)]
        self.assertEqual(R.candidates(self.cfg, batch, self.DATE)[0]["course_id"], first)
        B.find_item(batch, first)["hold"] = True
        nxt = R.candidates(self.cfg, batch, self.DATE)
        self.assertEqual(len(nxt), 5)
        self.assertNotIn(first, [it["course_id"] for it in nxt])

    def test_short_reason_keeps_whole_sentences(self):
        from mcq_agent.reel import short_reason
        text = "First sentence is here. Second one adds detail. " + "Third goes on and on " * 10 + "."
        self.assertEqual(short_reason(text, 60), "First sentence is here. Second one adds detail.")
        self.assertEqual(short_reason("One only"), "One only")

    @unittest.skipUnless(shutil.which("ffmpeg"), "needs ffmpeg")
    def test_makes_an_instagram_ready_video(self):
        from mcq_agent import reel as R
        from mcq_agent.video import probe
        batch = make_batch(self.tmp, self.DATE)
        item = R.make_reel(self.cfg, FakeReelRenderer(), batch, self.DATE)
        video = self.tmp / self.DATE.isoformat() / "reel.mp4"
        data = video.read_bytes()
        self.assertLess(data.find(b"moov"), data.find(b"mdat"))         # plays while it downloads
        self.assertNotIn(b"elst", data[:data.find(b"mdat")])            # no edit lists
        info = probe(video)
        if info:
            v = next(s for s in info["streams"] if s["codec_name"] == "h264")
            a = next(s for s in info["streams"] if s["codec_name"] == "aac")
            self.assertEqual((v["width"], v["height"], v["r_frame_rate"]), (1080, 1920, "30/1"))
            self.assertEqual(a["sample_rate"], "48000")
            self.assertAlmostEqual(float(info["format"]["duration"]), 15, delta=0.2)
        self.assertTrue((self.tmp / self.DATE.isoformat() / "reel_cover.jpg").exists())
        src = B.find_item(batch, item["course_id"])
        self.assertEqual(item["source"], R.source_hash(src))
        self.assertIn(post_ref("reel", self.DATE), item["caption"])
        self.assertIn(src["question"], item["caption"])

    def test_text_too_long_uses_a_shorter_reason_then_another_course(self):
        from mcq_agent import reel as R
        batch = make_batch(self.tmp, self.DATE)
        first = self.cfg.reel_courses()[self.cfg.reel_course_index(self.DATE)]
        B.find_item(batch, first)["explanation"] = "A short first reason. " + "Then a long second sentence " * 9 + "."
        tiny = FakeReelRenderer(scale=0.6)
        with mock.patch("mcq_agent.video.encode"), mock.patch("mcq_agent.reel._cover"):
            with self.assertRaises(R.ReelError):
                R.make_reel(self.cfg, tiny, batch, self.DATE)
        whys = [w for c, w, g in tiny.calls if c == first and not g]
        self.assertEqual(len(whys), 2)                                  # full reason, then a shorter one
        self.assertLess(len(whys[1]), len(whys[0]))

    def test_the_papers_author_presents_it_when_the_text_fits(self):
        from mcq_agent import reel as R
        rahul = R.presenter(self.cfg, "Rahul kp")
        self.assertTrue(rahul["think"].endswith(".png") and rahul["answer"] != rahul["think"] and rahul["thumbs"])
        self.assertTrue(R.presenter(self.cfg, "Ranjith Shivahari")["thumbs"])
        self.assertIsNone(R.presenter(self.cfg, "A New Author"))       # no pictures: drawn without a presenter
        batch = make_batch(self.tmp, self.DATE)
        with mock.patch("mcq_agent.video.encode"), mock.patch("mcq_agent.reel._cover"):
            item = R.make_reel(self.cfg, FakeReelRenderer(scale=0.9), batch, self.DATE)
            self.assertTrue(item["presenter"])
            crowded = FakeReelRenderer(scale=0.9, scale_with_presenter=0.65)
            item = R.make_reel(self.cfg, crowded, batch, self.DATE)
            self.assertFalse(item["presenter"])                         # too tight beside him: without him
            tried = [g for c, w, g in crowded.calls if c == item["course_id"]]
            self.assertEqual(tried[:2], [True, "compact"])              # full size, then a smaller presenter first

    def test_share_line_names_a_wrong_option_and_caption_gives_nothing_away(self):
        from mcq_agent import reel as R
        batch = make_batch(self.tmp, self.DATE)
        for src in batch["items"]:
            seen = {R.share_option(src, self.DATE + dt.timedelta(days=i)) for i in range(6)}
            self.assertNotIn(src["correct"], seen)
            self.assertEqual(len(seen), 3)                              # changes from day to day
        with mock.patch("mcq_agent.video.encode"), mock.patch("mcq_agent.reel._cover"):
            r = FakeReelRenderer()
            item = R.make_reel(self.cfg, r, batch, self.DATE)
        self.assertEqual(r.timing[3], item["share_option"])
        self.assertIn("Send this to a friend who'd get it wrong", item["caption"])
        self.assertNotIn("pick option", item["caption"])

    def _fake_voice(self, seconds):
        import math, struct, wave

        def synth(cfg, text, author, dest):
            secs = seconds.get(next(k for k in seconds if k in text), 1.0)
            with wave.open(str(dest), "wb") as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(48000)
                w.writeframes(b"".join(struct.pack("<h", int(6000 * math.sin(i / 20))) for i in range(int(secs * 48000))))
            return dest, "en-IN-AaravNeural (Azure)"
        return synth

    @unittest.skipUnless(shutil.which("ffmpeg"), "needs ffmpeg")
    def test_voice_makes_the_answer_stay_until_it_is_read(self):
        from mcq_agent import reel as R
        from mcq_agent import tts
        from mcq_agent.video import probe
        batch = make_batch(self.tmp, self.DATE)
        voice = self._fake_voice({"question.": 2.0, "The answer is": 12.0, "Send this": 2.2})
        with mock.patch.object(tts, "provider", return_value="azure"), mock.patch.object(tts, "synthesize", side_effect=voice):
            r = FakeReelRenderer()
            item = R.make_reel(self.cfg, r, batch, self.DATE)
        think, hold, outro, _ = r.timing
        self.assertAlmostEqual(hold, 0.7 + 12.0 + 0.6, places=2)        # answer stays until the voice ends
        self.assertAlmostEqual(outro, 0.3 + 2.2 + 0.6, places=2)
        self.assertEqual(item["voice"], "en-IN-AaravNeural (Azure)")
        info = probe(self.tmp / self.DATE.isoformat() / "reel.mp4")
        if info:
            self.assertAlmostEqual(float(info["format"]["duration"]), think + hold + outro, delta=0.2)

    def test_voice_failure_still_makes_the_reel(self):
        from mcq_agent import reel as R
        from mcq_agent import tts
        batch = make_batch(self.tmp, self.DATE)
        with mock.patch.object(tts, "provider", return_value="google"), \
             mock.patch.object(tts, "synthesize", side_effect=tts.TTSError("HTTP 403")), \
             mock.patch("mcq_agent.video.encode"), mock.patch("mcq_agent.reel._cover"):
            item = R.make_reel(self.cfg, FakeReelRenderer(), batch, self.DATE)
        self.assertEqual(item["voice"], "")
        self.assertIn("voice failed", item["voice_note"])
        self.assertEqual(item["seconds"]["answer"], 7.0)

    def test_voice_key_choice(self):
        from mcq_agent import tts
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertIsNone(tts.provider(self.cfg))
        with mock.patch.dict("os.environ", {"GOOGLE_TTS_API_KEY": "g"}, clear=True):
            self.assertEqual(tts.provider(self.cfg), "google")
        with mock.patch.dict("os.environ", {"GOOGLE_TTS_API_KEY": "g", "AZURE_SPEECH_KEY": "a",
                                            "AZURE_SPEECH_REGION": "centralindia"}, clear=True):
            self.assertEqual(tts.provider(self.cfg), "azure")
            self.assertEqual(tts.voice_for(self.cfg, "azure", "Ranjith Shivahari"), "en-IN-AaravNeural")
            with mock.patch.dict(self.cfg.reels["voice"], {"enabled": False}):
                self.assertIsNone(tts.provider(self.cfg))

    def test_voice_requests_never_leak_the_key(self):
        from mcq_agent import tts
        sent = []

        class R:
            def __init__(self, status, body):
                self.status_code, self.ok, self.text, self.content = status, status == 200, body, body.encode()
            def json(self):
                return json.loads(self.text)

        def fake_post(url, data=None, json=None, headers=None, timeout=None):
            sent.append((url, headers, data, json))
            return R(401, "bad key SECRET123")
        env = {"AZURE_SPEECH_KEY": "SECRET123", "AZURE_SPEECH_REGION": "centralindia", "GOOGLE_TTS_API_KEY": "SECRET123"}
        with mock.patch.dict("os.environ", env, clear=True), mock.patch("mcq_agent.tts.requests.post", side_effect=fake_post):
            with self.assertRaises(tts.TTSError) as err:
                tts.synthesize(self.cfg, "Answer: ₹27,000", "Ranjith Shivahari", self.tmp / "v.wav")
            self.assertNotIn("SECRET123", str(err.exception))
            self.assertEqual(sent[0][0], "https://centralindia.tts.speech.microsoft.com/cognitiveservices/v1")
            self.assertIn(b"en-IN-AaravNeural", sent[0][2])
            self.assertIn(b"twenty-seven thousand rupees", sent[0][2])
            self.assertIn(b"en-IN-PrabhatNeural", sent[1][2])                    # refused voice: default tried once
            with mock.patch.dict(self.cfg.reels["voice"], {"provider": "google"}):
                sent.clear()
                with self.assertRaises(tts.TTSError):
                    tts.synthesize(self.cfg, "x", "Rahul kp", self.tmp / "v.wav")
            self.assertNotIn("key=", sent[0][0])                                  # key in a header, not the address
            self.assertEqual(sent[0][1]["X-Goog-Api-Key"], "SECRET123")

    def test_numbers_and_symbols_are_spoken_naturally(self):
        from mcq_agent.tts import indian_words, speakable
        self.assertEqual(indian_words(145800), "one lakh forty-five thousand eight hundred")
        self.assertEqual(indian_words(12345678), "one crore twenty-three lakh forty-five thousand six hundred seventy-eight")
        self.assertEqual(speakable("EOQ = √10,00,000 = 1,000 units."),
                         "EOQ equals the square root of ten lakh equals one thousand units.")
        self.assertEqual(speakable("₹25,000 + ₹6,000 − ₹4,000 = ₹27,000"),
                         "twenty-five thousand rupees plus six thousand rupees minus four thousand rupees "
                         "equals twenty-seven thousand rupees")
        self.assertEqual(speakable("₹2.5 lakh p.a. under Ind AS 10 – not AS 4"),
                         "two point five lakh rupees per annum under Ind A S 10, not A S 4")

    def _reel(self, batch, course_id="ca_foundation"):
        from mcq_agent import reel as R
        src = B.find_item(batch, course_id)
        item = {"kind": "reel", "course_id": course_id, "paper_code": src["paper_code"],
                "paper_name": src["paper_name"], "topic": src["topic"], "correct": src["correct"],
                "source": R.source_hash(src), "video": "reel.mp4", "cover": "reel_cover.jpg",
                "seconds": {"think": 8, "answer": 7}, "caption": "c\n\n" + post_ref("reel", self.DATE)}
        (self.tmp / self.DATE.isoformat() / "reel.mp4").write_bytes(b"0" * 20000)
        B.save_reel(self.DATE, item)
        return item

    def _publish(self, at, dry=False):
        with mock.patch.dict("os.environ", {"IG_ACCESS_TOKEN": "t", "IG_USER_ID": "1"}), \
             mock.patch("mcq_agent.instagram.Instagram.find_by_ref", return_value=None), \
             mock.patch("mcq_agent.instagram.Instagram.post_carousel", return_value={"media_id": "m", "permalink": "p"}), \
             mock.patch("mcq_agent.instagram.Instagram.post_reel", return_value={"media_id": "r", "permalink": "pr"}) as post, \
             mock.patch("mcq_agent.instagram.Instagram.post_story", return_value={"media_id": "s"}) as story, \
             mock.patch("mcq_agent.hosting.urls_for", return_value=(["u1", "u2"], "test")), \
             mock.patch("mcq_agent.hosting.video_urls", return_value=["https://v/reel.mp4"]):
            P.publish_due(self.cfg, self.DATE, at, dry_run=dry, limit=10)
        self.story_calls = story.call_args_list
        return post

    def test_reel_posts_at_its_time_once(self):
        batch = make_batch(self.tmp, self.DATE)
        self._reel(batch)
        post = self._publish(dt.time(17, 30))
        self.assertEqual(post.call_count, 0)
        self.assertNotIn("reel", B.load_posted(self.DATE))
        post = self._publish(dt.time(17, 56))
        self.assertEqual(post.call_count, 1)
        self.assertEqual(post.call_args.args[0], ["https://v/reel.mp4"])
        self.assertEqual(post.call_args.kwargs, {"share_to_feed": True, "trial": None,
                                                 "audio_name": self.cfg.reels["audio_name"]})
        self.assertEqual(B.load_posted(self.DATE)["reel"]["permalink"], "pr")
        self.assertEqual(self._publish(dt.time(21, 0)).call_count, 0)    # never twice

    def test_reel_follows_its_mcq(self):
        batch = make_batch(self.tmp, self.DATE)
        self._reel(batch)
        src = B.find_item(batch, "ca_foundation")
        src["question"] += " (edited)"                                   # changed after the video was made
        B.save_batch(self.DATE, batch)
        self.assertEqual(self._publish(dt.time(18, 0)).call_count, 0)
        from mcq_agent.review import report, report_title
        self.assertIn("changed after the video was made", report(self.cfg, self.DATE, "me/r"))
        self.assertTrue(report_title(self.cfg, self.DATE).startswith("⛔"))
        batch = make_batch(self.tmp, self.DATE)
        self._reel(batch)
        B.find_item(batch, "ca_foundation")["hold"] = True               # on hold: the reel waits too
        B.save_batch(self.DATE, batch)
        self.assertEqual(self._publish(dt.time(18, 0)).call_count, 0)

    def test_trial_reel_option(self):
        with mock.patch.dict(self.cfg.reels, {"trial": True}):
            self.assertEqual(P.reel_options(self.cfg)["trial"], "SS_PERFORMANCE")
            self.assertFalse(P.reel_options(self.cfg)["share_to_feed"])

    def test_each_post_is_followed_by_its_story(self):
        batch = make_batch(self.tmp, self.DATE)
        for it in batch["items"]:
            it["story"] = f"{it['course_id']}_story.jpg"
            (self.tmp / self.DATE.isoformat() / it["story"]).write_bytes(b"jpg")
        B.save_batch(self.DATE, batch)
        self._reel(batch)
        with mock.patch.object(self.cfg, "now", return_value=dt.datetime(2026, 10, 21, 17, 56, tzinfo=self.cfg.tz)):
            self._publish(dt.time(17, 56))
        posted = B.load_posted(self.DATE)
        for cid in ("ca_foundation", "cma_cat", "ca_inter", "cma_inter", "reel"):
            self.assertIn(f"{cid}:story", posted)
        self.assertNotIn("ca_final:story", posted)                    # its post hasn't gone out yet
        videos = [c for c in self.story_calls if c.kwargs.get("video")]
        self.assertEqual(len(videos), 1)                               # the reel is shared as a video Story
        self.assertEqual(len(self.story_calls), 5)
        with mock.patch.object(self.cfg, "now", return_value=dt.datetime(2026, 10, 21, 18, 0, tzinfo=self.cfg.tz)):
            self._publish(dt.time(18, 0))
        self.assertEqual(len(self.story_calls), 0)                     # never twice

    def test_failed_story_tries_again_but_not_when_too_late(self):
        batch = make_batch(self.tmp, self.DATE)
        it = B.find_item(batch, "ca_foundation")
        it["story"] = "ca_foundation_story.jpg"
        (self.tmp / self.DATE.isoformat() / it["story"]).write_bytes(b"jpg")
        B.save_batch(self.DATE, batch)
        B.save_posted(self.DATE, {"ca_foundation": {"media_id": "1", "posted_at": "2026-10-21T07:56:00+05:30"}})
        with mock.patch.object(self.cfg, "now", return_value=dt.datetime(2026, 10, 21, 9, 0, tzinfo=self.cfg.tz)):
            self._publish(dt.time(9, 0))                                # nothing due, but the Story was waiting
        self.assertIn("ca_foundation:story", B.load_posted(self.DATE))
        B.save_posted(self.DATE, {"ca_foundation": {"media_id": "1", "posted_at": "2026-10-21T07:56:00+05:30"}})
        with mock.patch.object(self.cfg, "now", return_value=dt.datetime(2026, 10, 21, 15, 0, tzinfo=self.cfg.tz)):
            self._publish(dt.time(9, 0))
        self.assertNotIn("ca_foundation:story", B.load_posted(self.DATE))   # 7 hours late: skipped

    def test_story_is_drawn_with_each_mcq_and_concept(self):
        from PIL import Image

        class R:
            def render_item(self, item, date, out):
                return {"images": {"question": "q.jpg", "answer": "a.jpg"}, "fit_notes": []}

            def render_story(self, item, date, out):
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(b"jpg")
                return True

        item = dict(fake_mcq(), course_id="ca_inter", paper_code="Paper 4", paper_name="Cost and Management Accounting")
        P._finish(self.cfg, R(), item, self.DATE)
        self.assertEqual(item["story"], "ca_inter_story.jpg")
        broken = R()
        broken.render_story = mock.Mock(side_effect=RuntimeError("browser crashed"))
        P._finish(self.cfg, broken, item, self.DATE)
        self.assertNotIn("story", item)                                 # no Story, but the MCQ is fine
        self.assertFalse(item["hold"])
        out = self.tmp / self.DATE.isoformat()
        Image.new("RGB", (1080, 1350), "white").save(out / "concept_1.jpg")
        from mcq_agent.render import concept_story
        concept_story(out / "concept_1.jpg", out / "concept_story.jpg", self.cfg.course("cma_inter"))
        with Image.open(out / "concept_story.jpg") as im:
            self.assertEqual(im.size, (1080, 1920))

    def test_disabled_reels_never_post(self):
        batch = make_batch(self.tmp, self.DATE)
        self._reel(batch)
        with mock.patch.dict(self.cfg.reels, {"enabled": False}):
            self.assertEqual(self._publish(dt.time(21, 0)).call_count, 0)

    def test_hold_and_approve_the_reel(self):
        from mcq_agent.__main__ import parse_command
        batch = make_batch(self.tmp, self.DATE)
        self._reel(batch)
        self.assertEqual(parse_command("/hold reel", self.cfg), ("hold", "reel", ""))
        self.assertEqual(parse_command("/regen reel", self.cfg), ("regen", "reel", ""))
        P.hold(self.DATE, "reel")
        self.assertEqual(self._publish(dt.time(18, 0)).call_count, 0)
        P.release(self.DATE, "reel")
        self.assertEqual(self._publish(dt.time(18, 0)).call_count, 1)

    def test_todo_and_reel_only_prepare(self):
        from mcq_agent.__main__ import main
        import io, contextlib

        def todo(d):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf), mock.patch("mcq_agent.__main__.Config", return_value=self.cfg):
                main(["todo", "--date", d.isoformat()])
            return buf.getvalue().strip()

        batch = make_batch(self.tmp, self.DATE)
        make_concept(self.tmp, self.DATE, "cma_cat")
        self.assertEqual(todo(self.DATE), "reel")
        before = json.dumps(batch["items"], sort_keys=True)
        with mock.patch.object(P, "Renderer"), \
             mock.patch("mcq_agent.reel.make_reel", return_value={"kind": "reel", "course_id": "cma_final", "topic": "T"}):
            P.prepare(self.cfg, self.DATE, ["reel"])
        self.assertEqual(json.dumps(B.load_batch(self.DATE)["items"], sort_keys=True), before)
        self.assertEqual(B.load_reel(self.DATE)["course_id"], "cma_final")
        self.assertEqual(todo(self.DATE), "none")
        B.save_reel(self.DATE, {"kind": "reel", "course_id": "cma_final", "error": "x"})
        self.assertEqual(todo(self.DATE), "reel")                          # a failed reel is tried again
        # the Claude limit was reached part-way: the MCQs and concept note that failed are tried again
        B.find_item(batch, "ca_inter")["error"] = "usage limit reached"
        B.find_item(batch, "cma_final")["error"] = "usage limit reached"
        B.save_batch(self.DATE, batch)
        B.save_concept(self.DATE, {"kind": "concept", "course_id": "cma_cat", "error": "usage limit reached"})
        self.assertEqual(todo(self.DATE), "ca_inter,cma_final,concept,reel")

    def test_failed_reel_never_blocks_the_mcqs(self):
        batch = make_batch(self.tmp, self.DATE)
        with mock.patch("mcq_agent.reel.make_reel", side_effect=RuntimeError("ffmpeg is not installed")):
            P._prepare_reel(self.cfg, object(), self.DATE)
        r = B.load_reel(self.DATE)
        self.assertIn("ffmpeg", r["error"])
        from mcq_agent.review import report
        self.assertIn("/regen reel", report(self.cfg, self.DATE, "me/r"))
        post = self._publish(dt.time(21, 0))
        self.assertEqual(post.call_count, 0)
        self.assertEqual(len(B.load_posted(self.DATE)), 6)

    def test_posted_reel_is_never_remade(self):
        batch = make_batch(self.tmp, self.DATE)
        self._reel(batch)
        B.save_posted(self.DATE, {"reel": {"media_id": "r"}})
        with mock.patch("mcq_agent.reel.make_reel") as make:
            P._prepare_reel(self.cfg, object(), self.DATE)
        make.assert_not_called()
        with self.assertRaises(SystemExit):
            P.regenerate(self.cfg, self.DATE, "reel")

    def test_stops_calling_claude_once_the_limit_is_reached(self):
        calls = []

        class R:
            returncode, stdout = 1, ""
            stderr = "Claude AI usage limit reached|1761600000"

        def fake_run(*a, **k):
            calls.append(1)
            return R()
        G._strikes["n"] = 0
        G._stopped.clear()
        tool = {"name": "t", "input_schema": {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}}
        with mock.patch("mcq_agent.generator.shutil.which", return_value="/usr/bin/claude"), \
             mock.patch("mcq_agent.generator.subprocess.run", side_effect=fake_run), \
             mock.patch("mcq_agent.generator.time.sleep") as slept:
            for _ in range(G.STOP_AFTER):
                with self.assertRaises(G.GenerationError):
                    G._call_claude_code("m", "s", "u", tool)
            self.assertEqual(len(calls), G.STOP_AFTER)                  # one try each: no retrying a used-up limit
            slept.assert_not_called()
            with self.assertRaises(G.GenerationError) as err:
                G._call_claude_code("m", "s", "u", tool)
            self.assertEqual(len(calls), G.STOP_AFTER)                  # stopped: no more calls in this run
            self.assertIn("usage limit", str(err.exception))
        G._strikes["n"] = 0
        G._stopped.clear()

    def test_strong_checker_only_where_wording_traps_hide(self):
        writer = self.cfg.models["writer"]
        acc = self.cfg.find_paper("ca_foundation", "Paper 1", "Accounting")
        law = self.cfg.find_paper("ca_foundation", "Paper 2", "Business Laws")
        tax = self.cfg.find_paper("ca_inter", "Paper 3A", "Income-tax Law")
        with mock.patch.dict(self.cfg.models, {"strong_checks": "law_tax_audit"}):
            self.assertEqual(G.checker_for(self.cfg, acc, ""), writer)          # arithmetic is re-done by code
            self.assertIsNone(G.checker_for(self.cfg, law, ""))                 # Ranjith's papers keep the strong checker
            self.assertIsNone(G.checker_for(self.cfg, tax, "Income-tax Act"))
        with mock.patch.dict(self.cfg.models, {"strong_checks": "all"}):
            self.assertIsNone(G.checker_for(self.cfg, acc, ""))

    def test_prepare_ahead_saves_each_day_and_stops_at_the_limit(self):
        wf = (ROOT / ".github" / "workflows" / "prepare-ahead.yml").read_text()
        self.assertIn("group: prepare", wf)                                     # never alongside the evening job
        self.assertIn('git commit -q -m "MCQs for $D (prepared ahead)"', wf)
        self.assertIn("isn't complete", wf)
        self.assertLess(wf.index("git push"), wf.index('LEFT=$(python -m mcq_agent todo'))

    def test_paused_days_are_not_counted(self):
        with mock.patch.dict(self.cfg.brand, {"paused": [["2026-10-24", "2026-10-26"]]}):
            self.assertEqual(self.cfg.day_number(dt.date(2026, 10, 23)), 5)
            self.assertEqual(self.cfg.day_number(dt.date(2026, 10, 27)), 6)       # carries on after the pause
            self.assertEqual(self.cfg.day_number(dt.date(2026, 11, 1)), 11)
        with mock.patch.dict(self.cfg.brand, {"paused": []}):
            self.assertEqual(self.cfg.day_number(dt.date(2026, 10, 27)), 9)

    def test_day_drawn_with_an_old_number_is_redrawn(self):
        from mcq_agent.__main__ import main
        import io, contextlib
        batch = make_batch(self.tmp, self.DATE)
        batch["day"] = self.cfg.day_number(self.DATE) + 3
        B.save_batch(self.DATE, batch)
        make_concept(self.tmp, self.DATE, "cma_cat")
        B.save_reel(self.DATE, {"kind": "reel", "course_id": "cma_final", "topic": "T"})
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), mock.patch("mcq_agent.__main__.Config", return_value=self.cfg):
            main(["todo", "--date", self.DATE.isoformat()])
        self.assertEqual(buf.getvalue().strip(), "redraw")
        wf = (ROOT / ".github" / "workflows" / "prepare-ahead.yml").read_text()
        self.assertIn('python -m mcq_agent render --date "$D"', wf)

    def test_morning_runs_catch_up_today(self):
        wf = (ROOT / ".github" / "workflows" / "prepare.yml").read_text()
        for cron in ("17 0 * * *", "17 1 * * *"):                      # 05:47 and 06:47 IST, before the first post
            self.assertIn(f'cron: "{cron}"', wf)
            self.assertIn(f'"$SCHEDULE" = "{cron}"', wf)
        self.assertIn('ARGS=(--date "${INPUT_DATE:-$DAY}")', wf)

    def test_publish_schedule_has_the_reel_run(self):
        wf = (ROOT / ".github" / "workflows" / "publish.yml").read_text()
        h, m = map(int, self.cfg.reel_time().split(":"))
        utc = (h * 60 + m - 330) % 1440
        self.assertIn(f'cron: "{(utc + 2) % 60} {(utc + 2) // 60} * * *"', wf)

    def test_instagram_tries_the_next_address_and_drops_rejected_extras(self):
        from mcq_agent.instagram import Instagram, InstagramError
        ig = Instagram("graph.instagram.com", "v26.0", "tok", "1")
        calls = []

        def fake_call(method, path, **params):
            calls.append((path, dict(params)))
            if path == "1/media" and "audio_name" in params:
                raise InstagramError("bad param", 100)
            if path == "1/media":
                return {"id": f"c{len(calls)}"}
            if params.get("fields") == "status_code,status":
                return {"status_code": "ERROR" if path == "c2" else "FINISHED", "status": "bad video"}
            if path == "1/media_publish":
                return {"id": "m1"}
            return {"permalink": "https://instagram.com/reel/x"}

        with mock.patch.object(ig, "_call", side_effect=fake_call), mock.patch("time.sleep"):
            res = ig.post_reel(["https://a/r.mp4", "https://b/r.mp4"], "cap", audio_name="MCQ timer")
        self.assertEqual(res["video_url"], "https://b/r.mp4")
        made = [p for path, p in calls if path == "1/media"]
        self.assertEqual(made[0]["media_type"], "REELS")
        self.assertEqual(made[0]["share_to_feed"], "true")
        self.assertNotIn("audio_name", made[1])                            # dropped after Instagram refused it
        self.assertEqual(sum(1 for path, _ in calls if path == "1/media_publish"), 1)

    def test_sound_has_ticks_and_a_chime(self):
        import wave
        from mcq_agent.video import make_sound
        path = make_sound(self.tmp / "s.wav", 8, 15)
        with wave.open(str(path)) as w:
            self.assertEqual((w.getframerate(), w.getnchannels()), (48000, 2))
            self.assertAlmostEqual(w.getnframes() / 48000, 15, delta=0.01)


class ExplainerTests(TempQueue):
    """The cartoon explainer: script checks, word timing helpers, scene pictures and the 6 PM slot."""
    DATE = dt.date(2026, 11, 3)

    def setUp(self):
        super().setUp()
        self.cfg.explainer["style"] = "classic"      # these cover the classic style; StoryTests the story

    def script(self):
        from mcq_agent import explainer as X
        return X.tidy(json.loads(json.dumps(X.sample_script(self.cfg))))

    def test_spoken_words_for_amounts_formulas_and_acronyms(self):
        from mcq_agent.cartoon_video import shown, tokens
        toks = tokens("Invest ₹1,000 at 10%, so {(1+r)^n|one plus r, to the power n} grows. NPV rises.")
        self.assertEqual(toks[1], ("₹1,000", ["one", "thousand", "rupees"]))
        self.assertEqual(toks[3], ("10%,", ["10", "percent,"]))
        self.assertIn(("(1+r)^n", ["one", "plus", "r,", "to", "the", "power", "n"]), toks)
        self.assertTrue(dict(toks)["NPV"][0].startswith("[[") )        # spelt out by letter names
        self.assertEqual(shown("percent,"), "percent")

    def test_sample_script_is_valid(self):
        from mcq_agent import explainer as X
        self.assertEqual(X.validate(self.script()), [])
        self.assertTrue(85 <= X.word_count(self.script()) <= 115)

    def test_validation_catches_bad_scripts(self):
        from mcq_agent import explainer as X
        s = self.script()
        s["scenes"][0]["template"] = "talk"                              # no hook first
        s["scenes"][1]["speech"] = "x" * 40                              # too long for the bubble
        s["scenes"][2]["say"] = "This is the trap examiners love, a classic exam mistake."
        s["scenes"][3]["pose"] = "dancing"
        problems = " | ".join(X.validate(s))
        self.assertIn("first scene must be the hook", problems)
        self.assertIn("speech is 40 characters", problems)
        self.assertIn("only explains", problems)
        self.assertIn("is not a pose", problems)
        s = self.script()
        s["scenes"].insert(3, {"template": "mistake", "say": "x", "wrong": "a", "fix": "b"})
        self.assertIn("don't use these templates", " ".join(X.validate(s)))

    def test_every_template_draws(self):
        from mcq_agent import cartoon_scenes as S
        extra = [
            {"template": "talk", "say": "Hmm?", "bubble": "?"},
            {"template": "stacks", "say": "It grows.", "labels": ["Q1", "Q2", "Q3"], "values": ["₹1,025", "₹1,051", "₹1,077"], "note": "2.5% a quarter"},
            {"template": "paper", "say": "A question.", "title": "EXAM", "lines": ["Find the", "target cost?"]},
            {"template": "hold", "say": "Today!", "item": "cash", "label": "₹1,000", "face": "excited", "confetti": True},
            {"template": "flow", "say": "It becomes more.", "from": "Sales", "to": "Profit", "label": "−cost"},
            {"template": "board", "say": "Remember these.", "title": "KEY", "lines": ["One", "Two"], "pose": "present"},
        ]
        for sc in self.script()["scenes"] + extra:
            self.assertEqual(S.check_scene(sc, 1), [], sc)
            layers = S.layers(sc, lambda w: 1.0, 4.0, "@me", None)
            self.assertTrue(layers and all("<" in l["svg"] for l in layers), sc["template"])
            self.assertTrue(all(0 <= l["delay"] <= 2.4 for l in layers))   # pictures appear in the first 60%

    def test_caption_points_to_the_note_without_traps(self):
        from mcq_agent import explainer as X
        item = {"course_id": "cma_final", "paper_code": "Paper 16", "paper_name": "Strategic Cost Management",
                "topic": "Target Costing", "script": self.script()}
        cap = X.caption(self.cfg, item, self.DATE)
        self.assertIn("Full concept note today at 7:40 PM", cap)
        self.assertTrue(cap.endswith(post_ref("explainer", self.DATE)))
        self.assertNotIn("mistake", cap.lower())

    def _items(self, error=None, posted=None):
        from mcq_agent import explainer as X
        batch = make_batch(self.tmp, self.DATE)
        concept = make_concept(self.tmp, self.DATE, "cma_cat")
        out = self.tmp / self.DATE.isoformat()
        (out / "reel.mp4").write_bytes(b"0" * 20000)
        (out / "explainer.mp4").write_bytes(b"0" * 20000)
        from mcq_agent import reel as R
        src = B.find_item(batch, "ca_foundation")
        B.save_reel(self.DATE, {"kind": "reel", "course_id": "ca_foundation", "paper_code": src["paper_code"],
                                "paper_name": src["paper_name"], "topic": src["topic"], "correct": src["correct"],
                                "source": R.source_hash(src), "video": "reel.mp4", "seconds": {"think": 8, "answer": 7},
                                "caption": "reel caption"})
        ex = {"kind": "explainer", "course_id": "cma_cat", "paper_code": concept["paper_code"],
              "paper_name": concept["paper_name"], "topic": concept["topic"], "concept_topic": concept["topic"],
              "video": "explainer.mp4", "cover": "explainer_cover.jpg", "seconds": 41.0, "thumb_ms": 1200,
              "script": self.script(), "caption": "explainer caption", "hold": False}
        if error:
            ex["error"] = error
        X.save(self.DATE, ex)
        if posted:
            B.save_posted(self.DATE, posted)

    def _publish(self, at):
        with mock.patch.dict("os.environ", {"IG_ACCESS_TOKEN": "t", "IG_USER_ID": "1"}), \
             mock.patch("mcq_agent.instagram.Instagram.find_by_ref", return_value=None), \
             mock.patch("mcq_agent.instagram.Instagram.post_carousel", return_value={"media_id": "m", "permalink": "p"}), \
             mock.patch("mcq_agent.instagram.Instagram.post_reel", return_value={"media_id": "r", "permalink": "pr"}) as post, \
             mock.patch("mcq_agent.instagram.Instagram.post_story", return_value={"media_id": "s"}), \
             mock.patch("mcq_agent.hosting.urls_for", return_value=(["u1", "u2"], "test")), \
             mock.patch("mcq_agent.hosting.video_urls", side_effect=lambda p, c: [f"https://v/{p.name}"]):
            P.publish_due(self.cfg, self.DATE, at, limit=10)
        return post

    def test_explainer_takes_the_reel_slot(self):
        self._items()
        post = self._publish(dt.time(17, 56))
        self.assertEqual(post.call_count, 1)
        self.assertEqual(post.call_args.args[0], ["https://v/explainer.mp4"])
        self.assertEqual(post.call_args.args[1], "explainer caption")
        self.assertEqual(post.call_args.kwargs["thumb_offset"], 1200)
        posted = B.load_posted(self.DATE)
        self.assertIn("explainer", posted)
        self.assertNotIn("reel", posted)
        self.assertEqual(self._publish(dt.time(21, 0)).call_count, 0)    # one reel a day, never twice
        from mcq_agent.review import report
        text = report(self.cfg, self.DATE, "me/r")
        self.assertIn("🎬 Explainer", text)
        self.assertIn("backup", text.lower())

    def test_with_reels_off_only_the_explainer_posts(self):
        self.cfg.reels["enabled"] = False
        self._items()
        post = self._publish(dt.time(17, 56))
        self.assertEqual(post.call_count, 1)
        self.assertEqual(post.call_args.args[0], ["https://v/explainer.mp4"])
        self.assertNotIn("reel", B.load_posted(self.DATE))

    def test_mcq_reel_posts_when_the_explainer_failed(self):
        self._items(error="usage limit reached")
        from mcq_agent.review import report, report_title
        self.assertIn("the MCQ reel posts instead", report(self.cfg, self.DATE, "me/r"))
        self.assertFalse(report_title(self.cfg, self.DATE).startswith("⛔"))   # the backup covers it
        post = self._publish(dt.time(17, 56))
        self.assertEqual(post.call_args.args[0], ["https://v/reel.mp4"])
        self.assertIn("reel", B.load_posted(self.DATE))
        self.assertIn("the MCQ reel took the slot", report(self.cfg, self.DATE, "me/r"))

    def test_changed_concept_holds_the_explainer(self):
        self._items()
        c = B.load_concept(self.DATE)
        c["topic"] = "Another topic"
        B.save_concept(self.DATE, c)
        post = self._publish(dt.time(17, 56))
        self.assertEqual(post.call_args.args[0], ["https://v/reel.mp4"])

    def test_todo_asks_for_a_missing_explainer(self):
        from mcq_agent.__main__ import main
        import io, contextlib
        make_batch(self.tmp, self.DATE)
        make_concept(self.tmp, self.DATE, "cma_cat")
        B.save_reel(self.DATE, {"kind": "reel", "course_id": "cma_final", "topic": "T"})
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), mock.patch("mcq_agent.__main__.Config", return_value=self.cfg):
            main(["todo", "--date", self.DATE.isoformat()])
        self.assertEqual(buf.getvalue().strip(), "concept2,explainer,explainer2")   # 3 Nov: two notes and videos a day

    def test_a_failed_drawing_keeps_the_script(self):
        from mcq_agent import explainer as X
        make_batch(self.tmp, self.DATE)
        concept = make_concept(self.tmp, self.DATE, "cma_cat")
        script = {**self.script(), "checked": True}
        with mock.patch.object(X, "write_script", return_value=script) as write, \
             mock.patch("mcq_agent.cartoon_video.render", side_effect=RuntimeError("espeak-ng is not installed")):
            P._prepare_explainer(self.cfg, self.DATE)
        saved = X.load(self.DATE)
        self.assertIn("espeak", saved["error"])
        self.assertEqual(saved["script"]["scenes"], script["scenes"])
        self.assertEqual(write.call_count, 1)
        fake = {"seconds": 40.0, "scene_start": [], "words": [], "thumb_ms": 1100}
        with mock.patch.object(X, "write_script") as write, \
             mock.patch("mcq_agent.cartoon_video.render", return_value=fake):
            P._prepare_explainer(self.cfg, self.DATE)                      # drawn again without Claude
        self.assertEqual(write.call_count, 0)
        saved = X.load(self.DATE)
        self.assertNotIn("error", saved)
        self.assertEqual(saved["concept_topic"], concept["topic"])
        self.assertEqual(saved["seconds"], 40.0)

    def test_unconfirmed_script_is_held(self):
        from mcq_agent import explainer as X
        make_batch(self.tmp, self.DATE)
        make_concept(self.tmp, self.DATE, "cma_cat")
        script = {**self.script(), "serious": True, "serious_reason": "The checker found errors that weren't fixed"}
        fake = {"seconds": 40.0, "scene_start": [], "words": [], "thumb_ms": 1100}
        with mock.patch.object(X, "write_script", return_value=script), \
             mock.patch("mcq_agent.cartoon_video.render", return_value=fake):
            item = P._prepare_explainer(self.cfg, self.DATE)
        self.assertTrue(item["hold"])
        self.assertIn("checker", item["hold_reason"])

    def test_writer_retries_then_checks(self):
        from mcq_agent import explainer as X
        good = self.script()
        bad = {**good, "scenes": good["scenes"][1:]}                      # no hook
        replies = iter([bad, good])
        with mock.patch("mcq_agent.generator._call_claude", side_effect=lambda *a, **k: json.loads(json.dumps(next(replies)))), \
             mock.patch("mcq_agent.generator.call_checker", return_value={"issues": [], "severity": "none"}) as check:
            course = self.cfg.course("cma_final")
            out = X.write_script(self.cfg, {"topic": "Target Costing", "simple_words": "x"}, course, course["papers"][1], self.DATE)
        self.assertTrue(out["checked"])
        self.assertEqual(out["attempts"], 2)
        self.assertEqual(check.call_count, 1)

    def test_reel_container_sends_the_cover_frame(self):
        from mcq_agent.instagram import Instagram
        ig = Instagram("graph.instagram.com", "v26.0", "t", "1")
        with mock.patch.object(ig, "_call", return_value={"id": "c"}) as call:
            ig.reel_container("https://v/e.mp4", "cap", thumb_offset=1200)
        self.assertEqual(call.call_args.kwargs["thumb_offset"], "1200")


class FakeIG:
    """Records DMs and replies; serves media, comments and insights from dicts."""
    def __init__(self, media, comments, insights=None, fail_dm=None):
        self.media, self._comments, self._insights, self.fail_dm = media, comments, insights or {}, fail_dm
        self.dms, self.replies = [], []

    def account(self):
        return {"username": "cacmagyan"}

    def media_list(self, limit=30):
        return self.media

    def comments(self, media_id):
        return self._comments.get(media_id, [])

    def private_reply(self, cid, text):
        from mcq_agent.instagram import InstagramError
        if self.fail_dm:
            raise InstagramError(self.fail_dm, 10)
        self.dms.append((cid, text))
        return {"message_id": "m"}

    def reply_to_comment(self, cid, text):
        self.replies.append((cid, text))
        return {"id": "r"}

    def media_insights(self, media_id, metrics):
        return dict(self._insights.get(media_id, {}))

    def followers(self):
        return 1234



class StoryTests(TempQueue):
    """The story explainer: the classroom scene with the two students and the elephant teacher."""
    DATE = dt.date(2026, 11, 4)

    def script(self):
        from mcq_agent import explainer as X
        return X.story_tidy(self.cfg, json.loads(json.dumps(X.sample_script(self.cfg))))

    def test_story_is_the_default_and_the_sample_is_valid(self):
        from mcq_agent import explainer as X
        self.assertEqual(X.style(self.cfg), "story")
        s = self.script()
        self.assertEqual(X.story_validate(s), [])
        self.assertEqual(s["lines"][-1]["who"], "teacher")
        self.assertIn("Comment NOTES", s["lines"][-1]["say"])          # the DM keyword is asked for at the end
        self.assertIn("Line 1 (boy, desk):", X.story_plain(s))

    def test_story_validation_catches_problems(self):
        from mcq_agent import explainer as X
        s = self.script()
        s["lines"][0]["who"] = "teacher"                                  # the hook must be a student's
        s["lines"][2]["say"] = "Hmm, but why would any company ever do all of this extra work for nothing at all, Ma'am, tell me?"
        s["lines"][3]["board"]["says"] = "Customers will pay at most ₹10,000"     # too long for the bubble
        s["lines"][4]["say"] = "Remember this trap that examiners love."
        s["lines"][5]["pose"] = "dancing"
        s["hook_label"] = ""
        problems = " | ".join(X.story_validate(s))
        for part in ("line 1 must be a student's hook", "a student's line is too long", "board says is",
                     "only explains", "pose 'dancing'", "hook_label is required"):
            self.assertIn(part, problems)

    def test_caption_phrases_break_well(self):
        from mcq_agent.story_video import WEAK, chunks
        say = "Comment NOTES for the full note, and follow for one concept every day!"
        out = chunks([(w, i, i + 0.3) for i, w in enumerate(say.split())])
        self.assertEqual(" ".join(c[0] for c in out), say)
        for text, a, b in out:
            self.assertLessEqual(len(text), 28)
            self.assertNotIn(text.split()[-1].lower().strip(",.!?"), WEAK - {"it"}, text)
            self.assertLess(a, b)

    def test_every_board_picture_draws_and_fits(self):
        from mcq_agent import story_sets as Z
        from mcq_agent.cartoon_scenes import _words
        boards = [ln["board"] for ln in self.script()["lines"] if ln.get("board")]
        boards.append({"kind": "list", "title": "VALUE ENGINEERING", "lines": ["Same features", "Lower cost"]})
        for b in boards:
            self.assertEqual(Z.check_board(b, _words("price gap"), "x"), [], b)
            pieces = Z.board_layers(b)
            self.assertTrue(pieces and all("<" in svg for svg, _ in pieces), b["kind"])
        self.assertIn("at most 14", " ".join(Z.check_board(
            {"kind": "versus", "left": {"title": "A", "lines": ["x" * 20]}, "right": {"title": "B"}}, set(), "x")))

    def test_mouth_moves_with_the_voice(self):
        import numpy as np
        from mcq_agent.story_video import SR, _mouths
        t = np.arange(int(1.2 * SR)) / SR
        voice = np.sin(2 * np.pi * 180 * t) * (0.2 + 0.2 * np.sin(2 * np.pi * 4 * t))
        audio = np.concatenate([np.zeros(int(0.4 * SR)), voice, np.zeros(int(0.4 * SR))]).astype(np.float32)
        m = _mouths(audio)
        self.assertEqual(set(m[:5]), {0})                                 # silent: mouth shut
        self.assertTrue({1, 2} <= set(m))                                 # talking: it opens and closes
        self.assertTrue(all(not (m[i] == m[i + 1] == m[i + 2] != 0) for i in range(len(m) - 2)))

    def test_the_students_from_the_sheets(self):
        from mcq_agent import students_art as SA
        from mcq_agent.story_video import ART_POSE
        self.assertTrue(SA.available())
        for who in ("girl", "boy"):
            for name in set(ART_POSE[who].values()) | {"back"}:
                self.assertIn(f"{who}_{name}", SA.POSES)
        im = SA.picture("girl", "neutral")
        talking = SA.picture("girl", "neutral", talk=2, blink=True)
        self.assertEqual(im.size, talking.size)
        self.assertNotEqual(im.tobytes(), talking.tobytes())
        small, (x, y) = SA.placed("boy", "ask", 300, 1000, 120)
        meta = SA.POSES["boy_ask"]
        self.assertAlmostEqual(small.width, meta["rect"][2] * 120 / meta["ed"], delta=1)

    def test_writer_and_make_use_the_story(self):
        from mcq_agent import explainer as X
        good = self.script()
        bad = {**good, "lines": good["lines"][1:]}                       # starts with the teacher
        replies = iter([bad, good])
        with mock.patch("mcq_agent.generator._call_claude",
                        side_effect=lambda m, sys_, u, tool, **k: (self.assertEqual(tool["name"], "submit_story"),
                                                                   json.loads(json.dumps(next(replies))))[1]), \
             mock.patch("mcq_agent.generator.call_checker", return_value={"issues": [], "severity": "none"}):
            course = self.cfg.course("cma_final")
            out = X.write_script(self.cfg, {"topic": "Target Costing", "simple_words": "x"}, course, course["papers"][1], self.DATE)
        self.assertTrue(out["checked"])
        self.assertEqual(out["attempts"], 2)
        fake = {"seconds": 57.0, "line_start": [], "captions": [], "thumb_ms": 1300}
        with mock.patch("mcq_agent.story_video.render", return_value=fake) as render:
            item = X.make(self.cfg, self.DATE, good["concept"], self.tmp, script=out)
        self.assertEqual(render.call_count, 1)
        self.assertEqual(item["style"], "story")
        self.assertEqual(len(item["script"]["lines"]), len(good["lines"]))
        self.assertIn("girl: af_sarah", item["voice"])
        self.assertIn("Comment NOTES", item["caption"])

    def test_report_shows_who_says_what(self):
        from mcq_agent.review import _explainer_block
        e = {"course_id": "cma_final", "topic": "Target Costing", "seconds": 57.0, "script": self.script()}
        text = "\n".join(_explainer_block(self.cfg, e, "me/r", "main", self.DATE))
        self.assertIn("**👦 Boy:** Wait...", text)
        self.assertIn("**🐘 Teacher:**", text)


class CommentDMTests(TempQueue):
    DATE = dt.date(2026, 11, 3)

    @staticmethod
    def _url(host, path, ig_cfg):
        return f"https://cdn.jsdelivr.net/gh/me/repo@abc/queue/{path.parent.name}/{path.name}"

    def _setup(self, comments):
        make_concept(self.tmp, self.DATE, "cma_cat")
        now = dt.datetime.now(dt.timezone.utc)
        ts = now.strftime("%Y-%m-%dT%H:%M:%S+0000")
        media = [{"id": "e1", "caption": "x\n\n" + post_ref("explainer", self.DATE), "timestamp": ts, "comments_count": len(comments)},
                 {"id": "q1", "caption": "x\n\n" + post_ref("ca_inter", self.DATE), "timestamp": ts, "comments_count": 3}]
        for c in comments:
            c.setdefault("timestamp", ts)
        return FakeIG(media, {"e1": comments, "q1": [{"id": "x", "text": "notes", "username": "a", "timestamp": ts}]})

    def test_notes_comment_gets_one_dm_and_a_public_reply(self):
        from mcq_agent import replies as Rp
        ig = self._setup([
            {"id": "c1", "text": "NOTES please 🙏", "username": "student1"},
            {"id": "c2", "text": "Nice video", "username": "student2"},
            {"id": "c3", "text": "notes", "username": "student3", "replies": {"data": [{"username": "cacmagyan"}]}},
            {"id": "c4", "text": "notes", "username": "cacmagyan"},
        ])
        with mock.patch("mcq_agent.hosting.public_url", side_effect=self._url):
            counts = Rp.run(self.cfg, ig)
        self.assertEqual(counts["sent"], 1)
        self.assertEqual([c for c, _ in ig.dms], ["c1"])                   # not the MCQ post, not done ones, not us
        self.assertIn("https://cdn.jsdelivr.net/gh/me/repo@abc/queue/2026-11-03/concept.pdf", ig.dms[0][1])
        self.assertEqual(ig.replies[0][0], "c1")
        self.assertTrue((self.tmp / self.DATE.isoformat() / "concept.pdf").exists())

    def test_missing_permission_stops_quietly(self):
        from mcq_agent import replies as Rp
        ig = self._setup([{"id": "c1", "text": "notes", "username": "s1"}, {"id": "c2", "text": "pdf", "username": "s2"}])
        ig.fail_dm = "Application does not have permission for this action"
        with mock.patch("mcq_agent.hosting.public_url", side_effect=self._url):
            counts = Rp.run(self.cfg, ig)
        self.assertEqual((counts["sent"], counts["failed"]), (0, 1))
        self.assertEqual(ig.replies, [])

    def test_keywords_and_cta(self):
        from mcq_agent import replies as Rp
        self.assertTrue(Rp.wants_notes("Notes!!", ["notes"]))
        self.assertFalse(Rp.wants_notes("footnotes", ["notes"]))
        self.assertIn("Comment NOTES", Rp.cta(self.cfg))
        from mcq_agent.caption import build_concept_caption
        c = make_concept(self.tmp, self.DATE, "cma_cat")
        self.assertIn("Comment NOTES", build_concept_caption(self.cfg, c, self.DATE))


class WeeklyReportTests(TempQueue):
    def test_report_compares_kinds_and_ranks_posts(self):
        from mcq_agent import insights as I
        start = dt.date(2026, 11, 2)
        for k in range(3):
            d = start + dt.timedelta(days=k)
            make_batch(self.tmp, d)
            make_concept(self.tmp, d, "cma_cat")
            B.save_posted(d, {"ca_inter": {"media_id": f"q{k}", "permalink": "p"},
                              "explainer": {"media_id": f"e{k}", "permalink": "pe"},
                              "explainer:story": {"media_id": "s"}})
        ins = {f"q{k}": {"views": 100, "reach": 80, "saved": 2, "shares": 1, "likes": 5} for k in range(3)}
        ins.update({f"e{k}": {"views": 900 + k, "reach": 700, "saved": 20, "shares": 9, "likes": 40,
                              "ig_reels_avg_watch_time": 14500} for k in range(3)})
        ig = FakeIG([], {}, ins)
        with mock.patch.object(I, "STATS", self.tmp / "stats"):
            data = I.collect(self.cfg, ig, start, start + dt.timedelta(days=6))
            text = I.report(self.cfg, data, with_summary=False)
            I.save(data)
        self.assertEqual(len(data["posts"]), 6)                               # Stories left out
        self.assertIn("🎬 Cartoon explainer | 3 | 901", text)
        self.assertIn("14.5 s", text)
        self.assertIn("1,234", text)
        best = text.split("**Best posts**")[1]
        self.assertLess(best.index("Cartoon explainer"), best.index("MCQ post"))
        self.assertTrue((self.tmp / "stats" / "week-2026-11-08.json").exists())

    def test_no_permission_explains_itself(self):
        from mcq_agent import insights as I
        d = dt.date(2026, 11, 2)
        make_batch(self.tmp, d)
        B.save_posted(d, {"ca_inter": {"media_id": "q", "permalink": "p"}})

        class NoInsights(FakeIG):
            def media_insights(self, media_id, metrics):
                raise RuntimeError("(#10) Application does not have permission")
        with mock.patch.object(I, "STATS", self.tmp / "stats"):
            data = I.collect(self.cfg, NoInsights([], {}), d, d)
            self.assertIn("instagram_business_manage_insights", I.report(self.cfg, data, with_summary=False))

    def test_media_insights_drops_metrics_instagram_refuses(self):
        from mcq_agent.instagram import Instagram, InstagramError
        ig = Instagram("graph.instagram.com", "v26.0", "t", "1")
        calls = []

        def fake(method, path, **params):
            calls.append(params["metric"])
            if "follows" in params["metric"]:
                raise InstagramError("Invalid metric follows", 100)
            return {"data": [{"name": "reach", "values": [{"value": 50}]}, {"name": "views", "total_value": {"value": 70}}]}
        with mock.patch.object(ig, "_call", side_effect=fake):
            self.assertEqual(ig.media_insights("m", ["reach", "views", "follows"]), {"reach": 50, "views": 70})
        self.assertEqual(calls[-1], "reach,views")


if __name__ == "__main__":
    unittest.main()


class ConceptRepeatTests(TempQueue):
    def test_a_concept_used_by_another_course_is_not_repeated(self):
        for i, (course, topic) in enumerate([("cma_inter", "Offer vs Invitation to Offer"), ("ca_final", "POEM")]):
            d = dt.date(2026, 11, 3 + i)
            B.save_concept(d, {"course_id": course, "topic": topic})
        near = B.concepts_near(dt.date(2026, 11, 8))
        self.assertIn("Offer vs Invitation to Offer", near)
        self.assertTrue(B.same_topic("Offer vs. invitation to offer", near[0]))
        self.assertEqual(B.concepts_near(dt.date(2026, 12, 30)), [])
        captured = {}
        def fake_write(cfg, course, paper, date, recent, instruction, topic, **k):
            captured.update(recent=recent, topic=topic)
            raise RuntimeError("stop")
        with mock.patch.object(P, "_concept_base", return_value={"course_id": "ca_inter", "linked_mcq": "Offer vs Invitation to Offer"}), \
             mock.patch.object(P, "_concept_paper", return_value={"code": "P2", "name": "Corporate and Other Laws"}), \
             mock.patch("mcq_agent.concept.write_concept", side_effect=fake_write):
            with self.assertRaises(RuntimeError):
                P._make_concept(self.cfg, None, dt.date(2026, 11, 8))
        self.assertEqual(captured["topic"], "")                     # not the repeated MCQ topic
        self.assertIn("Offer vs Invitation to Offer", captured["recent"])


class ExplainerMinorFixTests(TempQueue):
    def test_minor_wording_issues_get_one_more_pass(self):
        from mcq_agent import explainer as X
        good = X.story_tidy(self.cfg, json.loads(json.dumps(X.sample_script(self.cfg))))
        checks = iter([{"issues": ["say 'how much', not 'how fast'"], "severity": "minor"}, {"issues": [], "severity": "none"}])
        with mock.patch("mcq_agent.generator._call_claude", side_effect=lambda *a, **k: json.loads(json.dumps(good))) as write, \
             mock.patch("mcq_agent.generator.call_checker", side_effect=lambda *a, **k: next(checks)):
            course = self.cfg.course("cma_final")
            out = X.write_script(self.cfg, {"topic": "Target Costing", "simple_words": "x"}, course, course["papers"][1], self.DATE)
        self.assertEqual(write.call_count, 2)
        self.assertIn("wording fixes", write.call_args_list[1].args[2])
        self.assertTrue(out["checked"])

    DATE = dt.date(2026, 11, 5)


class TwoPerDayTests(TempQueue):
    """From 1 Nov 2026: three MCQs a day (CA one day, CMA the next), two concept notes and two videos."""
    CA_DAY, CMA_DAY = dt.date(2026, 11, 1), dt.date(2026, 11, 2)

    def test_mcq_families_alternate(self):
        self.assertEqual(self.cfg.mcq_course_ids(self.CA_DAY), ["ca_foundation", "ca_inter", "ca_final"])
        self.assertEqual(self.cfg.mcq_course_ids(self.CMA_DAY), ["cma_cat", "cma_inter", "cma_final"])
        self.assertEqual(len(self.cfg.mcq_course_ids(dt.date(2026, 10, 31))), 6)     # before the change
        for k in range(12):                         # both notes every day: one CA course and one CMA course
            d = self.CA_DAY + dt.timedelta(days=k)
            a, b = self.cfg.concept_course(d)["id"], self.cfg.concept_course(d, "2")["id"]
            self.assertNotEqual(a.split("_")[0], b.split("_")[0], d)
        self.assertEqual(self.cfg.concept_time("2"), "13:40")
        self.assertEqual(self.cfg.explainer_time("2"), "11:25")

    def _day(self, date):
        from mcq_agent import explainer as X
        make_batch(self.tmp, date)                             # an old 6-MCQ batch (prepared ahead)
        make_concept(self.tmp, date, "cma_cat")
        c2 = make_concept(self.tmp, date, "ca_foundation", kind="concept2",
                          images=[f"concept2_{i}.jpg" for i in range(1, 5)])
        B.save_concept(date, c2, "2")
        (self.tmp / date.isoformat() / "concept.json").write_text(
            json.dumps({**B.load_concept(date, "2"), "kind": "concept", "course_id": "cma_cat",
                        "images": [f"concept_{i}.jpg" for i in range(1, 5)], "topic": "Evening topic"}))
        for slot, concept in (("", B.load_concept(date)), ("2", B.load_concept(date, "2"))):
            (self.tmp / date.isoformat() / f"explainer{slot}.mp4").write_bytes(b"0" * 20000)
            X.save(date, {"kind": "explainer" + slot, "course_id": concept["course_id"], "paper_code": "P",
                          "paper_name": "N", "topic": concept["topic"], "concept_topic": concept["topic"],
                          "video": f"explainer{slot}.mp4", "cover": "c.jpg", "seconds": 50, "thumb_ms": 1000,
                          "caption": f"video {slot or 1}", "hold": False}, slot)

    def _publish(self, date, at):
        with mock.patch.dict("os.environ", {"IG_ACCESS_TOKEN": "t", "IG_USER_ID": "1"}), \
             mock.patch("mcq_agent.instagram.Instagram.find_by_ref", return_value=None), \
             mock.patch("mcq_agent.instagram.Instagram.post_carousel", return_value={"media_id": "m", "permalink": "p"}) as car, \
             mock.patch("mcq_agent.instagram.Instagram.post_reel", return_value={"media_id": "r", "permalink": "pr"}) as reel, \
             mock.patch("mcq_agent.instagram.Instagram.post_story", return_value={"media_id": "s"}), \
             mock.patch("mcq_agent.hosting.urls_for", return_value=(["u1", "u2"], "test")), \
             mock.patch("mcq_agent.hosting.video_urls", side_effect=lambda p, c: [f"https://v/{p.name}"]):
            P.publish_due(self.cfg, date, at, limit=20)
        return car, reel

    def test_a_ca_day_posts_three_ca_mcqs_two_notes_and_two_videos(self):
        self._day(self.CA_DAY)
        car, reel = self._publish(self.CA_DAY, dt.time(11, 30))
        posted = B.load_posted(self.CA_DAY)
        self.assertIn("ca_foundation", posted)
        self.assertNotIn("cma_cat", posted)                    # 09:55 is a CMA time: not today
        self.assertIn("explainer2", posted)                    # 11:25 video
        self.assertEqual(reel.call_args.args[0], ["https://v/explainer2.mp4"])
        self._publish(self.CA_DAY, dt.time(23, 0))
        posted = B.load_posted(self.CA_DAY)
        self.assertEqual(sorted(k for k in posted if ":" not in k),
                         sorted(["ca_foundation", "ca_inter", "ca_final", "concept", "concept2", "explainer", "explainer2"]))
        from mcq_agent.review import report
        text = report(self.cfg, self.CA_DAY, "me/r")
        self.assertNotIn("CMA CAT |", text.split("## All MCQs")[0].replace("Concept (CMA CAT)", "").replace("Explainer (CMA CAT)", ""))
        self.assertIn("13:40", text)
        self.assertIn("11:25", text)

    def test_second_note_has_its_own_ref_pdf_and_dm(self):
        from mcq_agent import replies as R
        from mcq_agent.caption import build_concept_caption
        self._day(self.CA_DAY)
        c2 = B.load_concept(self.CA_DAY, "2")
        self.assertIn("ref concept2-261101", build_concept_caption(self.cfg, c2, self.CA_DAY))
        self.assertTrue(str(R.concept_pdf(self.CA_DAY, "2")).endswith("concept2.pdf"))
        self.assertEqual(R._post_date("x\nref explainer2-261101"), ("explainer2", self.CA_DAY))

    def test_todo_and_commands_know_the_second_slot(self):
        from mcq_agent.__main__ import parse_command
        self.assertEqual(parse_command("/regen concept2 another topic", self.cfg), ("regen", "concept2", "another topic"))
        self.assertEqual(parse_command("/hold explainer2", self.cfg)[1], "explainer2")
