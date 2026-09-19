"""Local/HTTP reader for the participant inbox; attachment contents stay outside SQLite."""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path


class Inbox:
    def __init__(self, source: str | Path):
        self.source = str(source).rstrip("/")
        self.is_http = self.source.startswith(("http://", "https://"))

    def emails(self) -> list[dict]:
        if self.is_http:
            return self._get_json("/emails")
        inbox_dir = Path(self.source) / "inbox"
        return [
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(inbox_dir.glob("email_*.json"))
        ]

    def __iter__(self):
        return iter(self.emails())

    def get(self, email_id: str) -> dict:
        if self.is_http:
            return self._get_json(f"/emails/{email_id}")
        path = Path(self.source) / "inbox" / f"{email_id}.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def read_bytes(self, attachment_path: str) -> bytes:
        if self.is_http:
            return self._get_bytes("/" + attachment_path.lstrip("/"))
        return (Path(self.source) / attachment_path).read_bytes()

    def read_text(self, attachment_path: str, encoding: str = "utf-8") -> str:
        return self.read_bytes(attachment_path).decode(encoding, errors="replace")

    def sample_submission(self) -> dict:
        if self.is_http:
            return self._get_json("/sample_submission")
        path = Path(self.source) / "sample_submission.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def _get_json(self, path: str):
        with urllib.request.urlopen(self.source + path) as response:
            return json.loads(response.read())

    def _get_bytes(self, path: str) -> bytes:
        with urllib.request.urlopen(self.source + path) as response:
            return response.read()
