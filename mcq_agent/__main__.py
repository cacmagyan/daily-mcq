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
            try:
                cfg.course(course_id)
            except KeyError as exc:
                raise SystemExit(str(exc).strip('"')) from None
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
            try:
                cfg.course(course_id)
            except KeyError as exc:
                raise SystemExit(str(exc).strip('"')) from None
            return word[1:], course_id, (parts[2].strip() if len(parts) > 2 else "")
    raise SystemExit("Write one of: /regen <course> [instruction], /approve <course>, /hold <course>. "
                     "Course ids: " + ", ".join(cfg.course_ids()))


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
    s.add_argument("--date", required=True)
    s.add_argument("--courses")

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
        rerender(cfg, dt.date.fromisoformat(args.date), _courses(args.courses))
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

    if args.cmd == "command":
        from .pipeline import hold, regenerate, release
        date = dt.date.fromisoformat(args.date)
        action, course_id, instruction = parse_command(args.comment, cfg)
        name = cfg.course(course_id)["name"]
        if action == "regen":
            item = regenerate(cfg, date, course_id, instruction)
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
