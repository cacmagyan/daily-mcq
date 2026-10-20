"""Instagram Graph API: carousel publishing, status checks, token refresh."""

from __future__ import annotations

import json
import os
import time

import requests


class InstagramError(RuntimeError):
    def __init__(self, message: str, code: int | None = None, subcode: int | None = None):
        super().__init__(message)
        self.code, self.subcode = code, subcode


TRANSIENT_CODES = {1, 2, 4, 17, 32, 341, 368, 613, 9004, 9007}


class Instagram:
    def __init__(self, host: str, version: str, token: str, user_id: str | None = None):
        if not token:
            raise InstagramError("IG_ACCESS_TOKEN is not set. Add it as a GitHub secret or in your .env file.")
        self.host = host
        self.base = f"https://{host}/{version}"
        self.token = token
        self._user_id = user_id or None
        self._alt_text_ok = True

    @classmethod
    def from_env(cls, ig_cfg: dict) -> "Instagram":
        return cls(
            host=ig_cfg.get("graph_host", "graph.instagram.com"),
            version=ig_cfg.get("api_version", "v26.0"),
            token="".join(os.environ.get("IG_ACCESS_TOKEN", "").split()),
            user_id=os.environ.get("IG_USER_ID", ""),
        )

    # ── low level ──────────────────────────────────────────
    def _redact(self, text) -> str:
        """Never let the token appear in logs (the repo is public)."""
        out = str(text)
        if self.token:
            out = out.replace(self.token, "***")
        return out

    def _call(self, method: str, path: str, **params) -> dict:
        params["access_token"] = self.token
        url = f"{self.base}/{path.lstrip('/')}"
        last = None
        for attempt in range(4):
            try:
                if method == "GET":
                    r = requests.get(url, params=params, timeout=60)
                else:
                    r = requests.post(url, data=params, timeout=60)
                data = r.json() if r.content else {}
            except (requests.RequestException, ValueError) as exc:
                last = InstagramError(f"Network problem talking to Instagram: {self._redact(exc)}")
                time.sleep(5 * 2 ** attempt)
                continue
            if r.ok and "error" not in data:
                return data
            err = data.get("error", {}) if isinstance(data, dict) else {}
            msg = self._redact(err.get("error_user_msg") or err.get("message") or r.text[:300])
            last = InstagramError(f"Instagram API error {err.get('code')}/{err.get('error_subcode')}: {msg}",
                                  err.get("code"), err.get("error_subcode"))
            if r.status_code >= 500 or err.get("is_transient") or err.get("code") in TRANSIENT_CODES:
                time.sleep(5 * 2 ** attempt)
                continue
            raise last
        raise last

    # ── account ───────────────────────────────────────────
    @property
    def user_id(self) -> str:
        if not self._user_id:
            if "instagram" not in self.host:
                raise InstagramError("Set IG_USER_ID (your Instagram professional account ID) when using graph.facebook.com.")
            me = self._call("GET", "me", fields="user_id,username")
            self._user_id = str(me.get("user_id") or me["id"])
        return self._user_id

    def account(self) -> dict:
        if "instagram" in self.host:
            return self._call("GET", "me", fields="user_id,username,account_type")
        return self._call("GET", self.user_id, fields="username")

    def publishing_limit(self) -> dict:
        return self._call("GET", f"{self.user_id}/content_publishing_limit", fields="quota_usage,config")

    def recent_media(self, limit: int = 15) -> list[dict]:
        return self._call("GET", f"{self.user_id}/media", fields="id,caption,permalink,timestamp",
                          limit=limit).get("data", [])

    def find_by_ref(self, ref: str) -> dict | None:
        for m in self.recent_media():
            if ref in (m.get("caption") or ""):
                return m
        return None

    # ── publishing ────────────────────────────────────────
    def image_container(self, image_url: str, alt_text: str = "") -> str:
        params = {"image_url": image_url, "is_carousel_item": "true"}
        if alt_text and self._alt_text_ok:
            try:
                return self._call("POST", f"{self.user_id}/media", alt_text=alt_text, **params)["id"]
            except InstagramError as exc:
                if exc.code != 100:          # 100 = invalid parameter; retry without alt text
                    raise
                self._alt_text_ok = False
        return self._call("POST", f"{self.user_id}/media", **params)["id"]

    def carousel_container(self, children: list[str], caption: str) -> str:
        return self._call("POST", f"{self.user_id}/media", media_type="CAROUSEL",
                          children=",".join(children), caption=caption)["id"]

    def wait_until_ready(self, container_id: str, timeout: int = 240, every: int = 5) -> None:
        start = time.time()
        while True:
            status = self._call("GET", container_id, fields="status_code,status")
            code = status.get("status_code")
            if code in ("FINISHED", "PUBLISHED"):
                return
            if code in ("ERROR", "EXPIRED"):
                raise InstagramError(f"Instagram could not process media {container_id}: {status.get('status')}")
            if time.time() - start > timeout:
                raise InstagramError(f"Media {container_id} still not ready after {timeout}s (status {code})")
            time.sleep(every)

    def publish(self, creation_id: str) -> str:
        return self._call("POST", f"{self.user_id}/media_publish", creation_id=creation_id)["id"]

    def permalink(self, media_id: str) -> str:
        return self._call("GET", media_id, fields="permalink").get("permalink", "")

    def post_carousel(self, image_urls: list[str], caption: str, alt_texts: list[str]) -> dict:
        children = []
        for url, alt in zip(image_urls, alt_texts):
            children.append(self.image_container(url, alt))
        for cid in children:
            self.wait_until_ready(cid)
        carousel = self.carousel_container(children, caption)
        self.wait_until_ready(carousel)
        media_id = self.publish(carousel)
        return {"media_id": media_id, "permalink": self.permalink(media_id)}

    def reel_container(self, video_url: str, caption: str, share_to_feed: bool = True,
                       trial: str | None = None, audio_name: str = "") -> str:
        """A REELS container. `trial` (MANUAL or SS_PERFORMANCE) makes it a Trial Reel, shown first
        only to people who don't follow you. Optional extras are dropped if Instagram rejects them."""
        params = {"media_type": "REELS", "video_url": video_url, "caption": caption}
        extras = {}
        if trial:
            params["trial_params"] = json.dumps({"graduation_strategy": trial})
        else:
            params["share_to_feed"] = "true" if share_to_feed else "false"
        if audio_name:
            extras["audio_name"] = audio_name[:100]
        try:
            return self._call("POST", f"{self.user_id}/media", **params, **extras)["id"]
        except InstagramError as exc:
            if exc.code != 100 or not extras:     # 100 = invalid parameter; try once without the extras
                raise
        return self._call("POST", f"{self.user_id}/media", **params)["id"]

    def post_reel(self, video_urls: list[str], caption: str, **options) -> dict:
        """Posts a reel. Instagram downloads the video itself; each URL is tried until one is
        processed. Video processing takes a minute or two."""
        if not video_urls:
            raise InstagramError("No public address for the reel video")
        problems = []
        for url in video_urls:
            try:
                container = self.reel_container(url, caption, **options)
                self.wait_until_ready(container, timeout=600, every=10)
            except InstagramError as exc:
                problems.append(f"{url.split('/')[2]}: {exc}")
                continue
            media_id = self.publish(container)
            return {"media_id": media_id, "permalink": self.permalink(media_id), "video_url": url}
        raise InstagramError("Instagram could not take the reel video. " + " | ".join(problems))

    # ── token ─────────────────────────────────────────────
    def refresh_token(self) -> dict:
        """Instagram Login tokens last 60 days; this extends one that is at least a day old."""
        try:
            r = requests.get("https://graph.instagram.com/refresh_access_token",
                             params={"grant_type": "ig_refresh_token", "access_token": self.token}, timeout=60)
            data = r.json()
        except (requests.RequestException, ValueError) as exc:
            raise InstagramError(f"Token refresh failed: {self._redact(exc)}") from None
        if not r.ok or "access_token" not in data:
            raise InstagramError(f"Token refresh failed: {self._redact(data.get('error', data))}")
        return data
