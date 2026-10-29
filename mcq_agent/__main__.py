"""Command line: python -m mcq_agent <command> --help"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
from pathlib import Path

from .config import ROOT, Config


def _load_dotenv() -> None:
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _write_output(path: str | None, **pairs: str) -> None:
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            for k, v in pairs.items():
                fh.write(f"{k}={v}\n")


def _courses(value: str | None) -> list[str] | None:
    return [c.strip() for c in value.split(",") if c.strip()] if value else None


def parse_regen_comment(text: str, cfg: Config) -> tuple[str, str]:
    for line in text.strip().splitlines():
        line = line.strip()
        if line.lower().startswith("/regen"):
            parts = line.split(maxsplit=2)
            if len(parts) < 2:
                break
            course_id = parts[1].strip().lower()
            if course_id not in ("concept", "reel", "explainer"):
                try:
                    cfg.course(course_id)
                except KeyError as exc:
                    raise SystemExit(str(exc).strip('"') + ", concept, reel, explainer") from None
            return course_id, (parts[2].strip() if len(parts) > 2 else "")
    raise SystemExit("Write it as: /regen <course_id> [instruction]. Course ids: " + ", ".join(cfg.course_ids()))


COMMANDS = ("/regen", "/approve", "/hold")


def parse_command(text: str, cfg: Config) -> tuple[str, str, str]:
    """Returns (command, course_id, instruction) from a comment like '/regen ca_inter make it on CVP'."""
    for line in text.strip().splitlines():
        line = line.strip()
        word = line.split(maxsplit=1)[0].lower() if line else ""
        if word in COMMANDS:
            parts = line.split(maxsplit=2)
            if len(parts) < 2:
                break
            course_id = parts[1].strip().lower()
            if course_id not in ("concept", "reel", "explainer"):
                try:
                    cfg.course(course_id)
                except KeyError as exc:
                    raise SystemExit(str(exc).strip('"') + ", concept, reel, explainer") from None
            return word[1:], course_id, (parts[2].strip() if len(parts) > 2 else "")
    raise SystemExit("Write one of: /regen <course> [instruction], /approve <course>, /hold <course>. "
                     "Course ids: " + ", ".join(cfg.course_ids()) + ", concept, reel, explainer")


def main(argv: list[str] | None = None) -> int:
    _load_dotenv()
    p = argparse.ArgumentParser(prog="mcq_agent", description="Daily CA/CMA MCQ images for Instagram")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("prepare", help="write and render a day's MCQs")
    s.add_argument("--date", default="tomorrow", help="YYYY-MM-DD, today or tomorrow (default)")
    s.add_argument("--courses", help="comma-separated course ids (default: all)")
    s.add_argument("--sample", action="store_true", help="use the built-in sample MCQs, no API key needed")
    s.add_argument("--github-output", help=argparse.SUPPRESS)

    s = sub.add_parser("render", help="redraw images after editing mcqs.json")
    s.add_argument("--date", required=True, help="YYYY-MM-DD, today or tomorrow")
    s.add_argument("--courses")
    s.add_argument("--github-output", help=argparse.SUPPRESS)

    s = sub.add_parser("regen", help="rewrite one course's MCQ")
    s.add_argument("--date", required=True)
    s.add_argument("--course")
    s.add_argument("--instruction", default="")
    s.add_argument("--comment", help="a '/regen <course> [instruction]' comment")
    s.add_argument("--github-output", help=argparse.SUPPRESS)

    s = sub.add_parser("pr-body", help="print the review text for a batch")
    s.add_argument("--date", required=True)
    s.add_argument("--branch", required=True)
    s.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", "owner/repo"))

    s = sub.add_parser("report", help="print the daily report (auto mode)")
    s.add_argument("--date", required=True)
    s.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", "owner/repo"))
    s.add_argument("--branch", default="main")
    s.add_argument("--owner", default=os.environ.get("GITHUB_REPOSITORY_OWNER", ""))

    s = sub.add_parser("report-title", help="print the daily issue title")
    s.add_argument("--date", required=True)

    s = sub.add_parser("command", help="run a /regen, /approve or /hold comment")
    s.add_argument("--date", required=True)
    s.add_argument("--comment", required=True)
    s.add_argument("--github-output", help=argparse.SUPPRESS)

    sub.add_parser("mode", help="print the review mode (auto, github_pr or local)")

    s = sub.add_parser("merge-posted", help="add saved posted.json records into the current queue")
    s.add_argument("saved", help="folder holding copies of queue/<date>/posted.json")

    s = sub.add_parser("todo", help="print what a day still needs: all, none, or a list like ca_inter,concept,reel,explainer")
    s.add_argument("--date", default="tomorrow")

    s = sub.add_parser("approve", help="approve a batch (review mode: local)")
    s.add_argument("--date", required=True)

    s = sub.add_parser("publish", help="post every approved MCQ whose time has come")
    s.add_argument("--date", default="today")
    s.add_argument("--at", help="pretend the time is HH:MM (testing)")
    s.add_argument("--limit", type=int)
    s.add_argument("--dry-run", action="store_true")
    s.add_argument("--strict", action="store_true", help="fail if today's batch isn't approved")

    s = sub.add_parser("set-logo", help="use a new logo image (removes a fake checkerboard background)")
    s.add_argument("image", help="path to the logo (PNG with transparency, or JPEG)")

    s = sub.add_parser("reel-demo", help="make demo reels from the sample MCQs (tries the voice); posts nothing")
    s.add_argument("--out", default="demo", help="folder for the videos (default: demo)")

    s = sub.add_parser("explainer-demo", help="draw the sample explainer (samples/sample_story.json, or sample_explainer.json for the classic style); no Claude, posts nothing")
    s.add_argument("--out", default="demo", help="folder for the video (default: demo)")

    s = sub.add_parser("replies", help="DM the concept note PDF to everyone who commented NOTES")
    s.add_argument("--dry-run", action="store_true")

    s = sub.add_parser("make-pdfs", help="make PDFs of recent concept notes (for the comment DMs)")
    s.add_argument("--days", type=int, default=8)

    s = sub.add_parser("weekly-report", help="last week's Instagram numbers, as the text of an issue")
    s.add_argument("--out", help="write the report here (default: print it)")
    s.add_argument("--no-summary", action="store_true", help="skip Claude's notes")

    sub.add_parser("check", help="test the Instagram and Claude connections")
    sub.add_parser("refresh-token", help="print a refreshed Instagram token (stdout only)")

    args = p.parse_args(argv)
    cfg = Config()

    if args.cmd == "prepare":
        from .pipeline import prepare
        date = cfg.resolve_date(args.date)
        print(f"Preparing {date} (Day {cfg.day_number(date)})")
        batch = prepare(cfg, date, _courses(args.courses), sample=args.sample)
        failed = [it["course_id"] for it in batch["items"] if it.get("error")]
        _write_output(args.github_output, batch_date=date.isoformat(), failed=",".join(failed))
        return 0 if len(failed) < len(batch["items"]) else 1

    if args.cmd == "render":
        from .pipeline import rerender
        date = cfg.resolve_date(args.date)
        rerender(cfg, date, _courses(args.courses))
        _write_output(args.github_output, batch_date=date.isoformat())
        return 0

    if args.cmd == "regen":
        from .pipeline import regenerate
        if args.comment:
            course_id, instruction = parse_regen_comment(args.comment, cfg)
        elif args.course:
            course_id, instruction = args.course, args.instruction
        else:
            p.error("give --course or --comment")
        regenerate(cfg, dt.date.fromisoformat(args.date), course_id, instruction)
        _write_output(args.github_output, course=course_id)
        return 0

    if args.cmd == "pr-body":
        from .review import pr_body
        print(pr_body(cfg, dt.date.fromisoformat(args.date), args.repo, args.branch))
        return 0

    if args.cmd == "report":
        from .review import report
        print(report(cfg, dt.date.fromisoformat(args.date), args.repo, args.branch, args.owner))
        return 0

    if args.cmd == "report-title":
        from .review import report_title
        print(report_title(cfg, dt.date.fromisoformat(args.date)))
        return 0

    if args.cmd == "mode":
        print(cfg.review_mode)
        return 0

    if args.cmd == "merge-posted":
        from .batch import merge_posted
        for line in merge_posted(Path(args.saved)):
            print(f"  recorded {line}")
        return 0

    if args.cmd == "todo":
        from .batch import load_batch, load_concept, load_reel
        date = cfg.resolve_date(args.date)
        if not load_batch(date):
            print("all")
            return 0
        batch = load_batch(date)
        # MCQs that failed to be written (e.g. the Claude limit was reached part-way) are tried again
        need = [it["course_id"] for it in batch.get("items", []) if it.get("error")]
        concept = load_concept(date)
        if cfg.concept_due(date) and (not concept or concept.get("error")):
            need.append("concept")
        reel = load_reel(date)
        if cfg.reel_due(date) and (not reel or reel.get("error")):     # a failed reel is cheap to retry
            need.append("reel")
        from .explainer import load as load_explainer
        ex = load_explainer(date)
        if cfg.explainer_due(date) and (not ex or ex.get("error") or "concept" in need
                                        or (concept and ex.get("concept_topic") != concept.get("topic"))):
            need.append("explainer")
        if not need and batch.get("day") and batch["day"] != cfg.day_number(date):
            print("redraw")              # drawn with an older Day number (e.g. after a pause): redraw it
            return 0
        print(",".join(need) or "none")
        return 0

    if args.cmd == "command":
        from .pipeline import hold, regenerate, release
        date = dt.date.fromisoformat(args.date)
        action, course_id, instruction = parse_command(args.comment, cfg)
        name = {"concept": "concept note", "reel": "reel", "explainer": "explainer"}.get(course_id) or cfg.course(course_id)["name"]
        if action == "regen":
            item = regenerate(cfg, date, course_id, instruction)
            if course_id == "concept":
                summary = f"New concept note for {date}: {item.get('topic', '')}"
            elif course_id == "explainer":
                summary = (f"Explainer for {date} could not be made: {item.get('error', '')[:200]}" if item.get("error")
                           else f"New explainer for {date}: {item.get('topic', '')} ({item.get('seconds', 0):g} s)")
            elif course_id == "reel":
                summary = (f"Reel for {date} could not be made: {item.get('error', '')[:200]}" if item.get("error")
                           else f"New reel for {date}: {cfg.course(item['course_id'])['name']}, {item.get('topic', '')}")
            else:
                summary = f"New {name} MCQ for {date}: {item.get('topic', '')} (answer {item.get('correct', '?')})"
            if item.get("hold"):
                summary += f". It is on hold: {item.get('hold_reason')}"
        elif action == "approve":
            summary = release(date, course_id)
        else:
            summary = hold(date, course_id)
        print(summary)
        _write_output(args.github_output, course=course_id, action=action, summary=summary.replace("\n", " "))
        return 0

    if args.cmd == "approve":
        from .pipeline import approve
        approve(dt.date.fromisoformat(args.date))
        return 0

    if args.cmd == "publish":
        from .pipeline import publish_due
        at = dt.time.fromisoformat(args.at) if args.at else None
        return publish_due(cfg, cfg.resolve_date(args.date), at, args.dry_run, args.strict, args.limit)

    if args.cmd == "set-logo":
        try:
            from .logo import prepare_logo
            dest = ROOT / (cfg.brand.get("logo") or "assets/brand/logo.png")
            prepare_logo(Path(args.image), dest)
        except ImportError:
            raise SystemExit("set-logo needs two extra packages: pip install numpy scipy")
        print(f"Saved {dest.relative_to(ROOT)}. Run: python -m mcq_agent prepare --date today --sample  to see it.")
        return 0

    if args.cmd == "reel-demo":
        from .pipeline import reel_demo
        made = reel_demo(cfg, ROOT / args.out)
        return 0 if made else 1

    if args.cmd == "explainer-demo":
        from . import explainer as X
        out = ROOT / args.out
        out.mkdir(parents=True, exist_ok=True)
        script = X.sample_script(cfg)
        item = X.make(cfg, cfg.today(), script["concept"], out, script=script)
        print(f"  ✓ {out / item['video']} ({item['seconds']:g} s)\n---\n{item['caption']}")
        return 0

    if args.cmd == "replies":
        from .replies import run
        counts = run(cfg, dry_run=args.dry_run)
        return 1 if counts["failed"] and not counts["sent"] else 0

    if args.cmd == "make-pdfs":
        from .replies import make_pdfs
        for p in make_pdfs(cfg, args.days):
            print(f"  ✓ {p.relative_to(ROOT)}")
        return 0

    if args.cmd == "weekly-report":
        from .insights import weekly
        text = weekly(cfg, with_summary=not args.no_summary)
        if args.out:
            Path(args.out).write_text(text, encoding="utf-8")
        else:
            print(text)
        return 0

    if args.cmd == "check":
        return _check(cfg)

    if args.cmd == "refresh-token":
        from .instagram import Instagram
        data = Instagram.from_env(cfg.instagram).refresh_token()
        sys.stdout.write(data["access_token"])
        days = int(data.get("expires_in", 0)) // 86400
        print(f"\nRefreshed; valid for {days} more days.", file=sys.stderr)
        return 0
    return 2


def _check(cfg: Config) -> int:
    import requests

    from .instagram import Instagram, InstagramError

    from .generator import GenerationError, _call_claude_code, auth_mode

    ok = True
    mode = auth_mode()
    if mode == "none":
        print("✗ No Claude login: add CLAUDE_CODE_OAUTH_TOKEN (subscription) or ANTHROPIC_API_KEY (paid API)")
        ok = False
    elif mode == "subscription":
        try:
            _call_claude_code(cfg.models.get("writer", "claude-sonnet-5-5"), "Reply as asked.", "Set ok to true.",
                              {"name": "check", "input_schema": {"type": "object",
                               "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}})
            print("✓ Claude subscription token works (MCQs will use your Claude plan)")
            checker = cfg.models.get("checker")
            if checker and checker != cfg.models.get("writer"):
                try:
                    _call_claude_code(checker, "Reply as asked.", "Set ok to true.",
                                      {"name": "check", "input_schema": {"type": "object",
                                       "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}})
                    print(f"✓ Checker model {checker} works")
                except GenerationError as exc:
                    print(f"• Checker model {checker} isn't available on your plan ({str(exc)[:80]}); "
                          "the writer model will do the checks instead")
        except GenerationError as exc:
            print(f"✗ Claude subscription token: {exc}"); ok = False
    else:
        key = os.environ["ANTHROPIC_API_KEY"]
        r = requests.get("https://api.anthropic.com/v1/models",
                         headers={"x-api-key": key, "anthropic-version": "2023-06-01"}, timeout=30)
        if r.ok:
            names = {m.get("id") for m in r.json().get("data", [])}
            for role, model in cfg.models.items():
                if role in ("writer", "checker"):
                    mark = "✓" if model in names else "?"
                    print(f"{mark} Claude {role} model {model}" + ("" if model in names else " (not in your model list; check the name)"))
        else:
            print(f"✗ Claude API key rejected: HTTP {r.status_code}"); ok = False
    try:
        ig = Instagram.from_env(cfg.instagram)
        acc = ig.account()
        print(f"✓ Instagram account @{acc.get('username')} ({acc.get('account_type', 'professional')}), id {ig.user_id}")
        lim = ig.publishing_limit().get("data", [{}])[0]
        print(f"✓ Posts published by API in the last 24 h: {lim.get('quota_usage', '?')}")
    except InstagramError as exc:
        print(f"✗ Instagram: {exc}"); ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
