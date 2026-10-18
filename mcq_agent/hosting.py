"""Gives Instagram a public URL for each image (Instagram downloads images itself)."""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

from .config import ROOT


class HostingError(RuntimeError):
    pass


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()


def repo_and_commit() -> tuple[str, str]:
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    sha = os.environ.get("GITHUB_SHA", "")
    try:
        if not repo:
            m = re.search(r"github\.com[:/](.+?)(?:\.git)?$", _git("remote", "get-url", "origin"))
            repo = m.group(1) if m else ""
        if not sha:
            sha = _git("rev-parse", "HEAD")
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    if not repo or not sha:
        raise HostingError("Can't work out the GitHub repo/commit. Run inside the GitHub repo or set GITHUB_REPOSITORY.")
    return repo, sha


def _cloudinary_upload(path: Path) -> str:
    url = os.environ.get("CLOUDINARY_URL", "")
    p = urlparse(url)
    if p.scheme != "cloudinary" or not p.username or not p.password or not p.hostname:
        raise HostingError("CLOUDINARY_URL must look like cloudinary://API_KEY:API_SECRET@CLOUD_NAME")
    public_id = f"mcq/{path.parent.name}/{path.stem}"
    ts = str(int(time.time()))
    to_sign = f"overwrite=true&public_id={public_id}&timestamp={ts}{p.password}"
    with open(path, "rb") as fh:
        r = requests.post(
            f"https://api.cloudinary.com/v1_1/{p.hostname}/image/upload",
            data={"api_key": p.username, "timestamp": ts, "public_id": public_id, "overwrite": "true",
                  "signature": hashlib.sha1(to_sign.encode()).hexdigest()},
            files={"file": fh}, timeout=120,
        )
    if not r.ok:
        raise HostingError(f"Cloudinary upload failed: {r.text[:300]}")
    return r.json()["secure_url"]


def public_url(host: str, path: Path, ig_cfg: dict) -> str:
    rel = path.relative_to(ROOT).as_posix()
    if host == "github_raw":
        repo, sha = repo_and_commit()
        return f"https://raw.githubusercontent.com/{repo}/{sha}/{rel}"
    if host == "jsdelivr":
        repo, sha = repo_and_commit()
        return f"https://cdn.jsdelivr.net/gh/{repo}@{sha}/{rel}"
    if host == "base_url":
        base = (ig_cfg.get("public_base_url") or "").rstrip("/")
        if not base:
            raise HostingError("image_hosts has base_url but public_base_url is empty in config.yaml")
        return f"{base}/{rel}"
    if host == "cloudinary":
        return _cloudinary_upload(path)
    raise HostingError(f"Unknown image host '{host}'")


def reachable_jpeg(url: str) -> tuple[bool, str]:
    try:
        r = requests.get(url, timeout=45, stream=True)
        ctype = r.headers.get("content-type", "")
        r.close()
    except requests.RequestException as exc:
        return False, str(exc)
    if r.status_code != 200:
        return False, f"HTTP {r.status_code}"
    if "jpeg" not in ctype and "jpg" not in ctype:
        return False, f"content-type {ctype or 'missing'}"
    return True, "ok"


def urls_for(paths: list[Path], ig_cfg: dict) -> tuple[list[str], str]:
    """Tries each configured host until every image is publicly reachable as JPEG."""
    errors = []
    for host in ig_cfg.get("image_hosts", ["github_raw", "jsdelivr"]):
        try:
            urls = [public_url(host, p, ig_cfg) for p in paths]
        except HostingError as exc:
            errors.append(f"{host}: {exc}")
            continue
        checks = [reachable_jpeg(u) for u in urls]
        if all(ok for ok, _ in checks):
            return urls, host
        errors.append(f"{host}: " + "; ".join(f"{u} -> {why}" for u, (ok, why) in zip(urls, checks) if not ok))
    raise HostingError(
        "No image host worked. A private GitHub repo can't serve images to Instagram: make the repo public "
        "or switch image_hosts to cloudinary.\n" + "\n".join(errors))
