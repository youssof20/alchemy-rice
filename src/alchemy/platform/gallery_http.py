from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol
from urllib.error import HTTPError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


@dataclass(frozen=True, slots=True)
class HttpDocument:
    status: int
    body: bytes
    etag: str | None
    final_url: str


class GalleryHttpClient(Protocol):
    def fetch(self, url: str, *, maximum: int, etag: str | None = None) -> HttpDocument: ...


class UrllibGalleryHttpClient:
    def fetch(self, url: str, *, maximum: int, etag: str | None = None) -> HttpDocument:
        headers = {"Accept": "application/json, image/*;q=0.8", "User-Agent": "Alchemy/0.1"}
        if etag:
            headers["If-None-Match"] = etag
        opener = build_opener(_NoRedirectHandler())
        current_url = url
        for _ in range(6):
            request = Request(current_url, headers=headers)
            try:
                with opener.open(request, timeout=20) as response:
                    final_url = response.geturl()
                    _validate_final_url(url, final_url)
                    length = response.headers.get("Content-Length")
                    if length is not None and int(length) > maximum:
                        raise ValueError("Remote gallery document exceeds its byte limit")
                    body = response.read(maximum + 1)
                    if len(body) > maximum:
                        raise ValueError("Remote gallery document exceeds its byte limit")
                    response_etag = response.headers.get("ETag")
                    if response_etag is not None and (
                        len(response_etag) > 512
                        or any(ord(character) < 32 for character in response_etag)
                    ):
                        response_etag = None
                    return HttpDocument(response.status, body, response_etag, final_url)
            except HTTPError as exc:
                if exc.code == 304:
                    return HttpDocument(304, b"", etag, current_url)
                if exc.code in {301, 302, 303, 307, 308}:
                    location = exc.headers.get("Location")
                    if not location:
                        raise RuntimeError("Gallery redirect omitted its destination") from exc
                    destination = urljoin(current_url, location)
                    _validate_final_url(url, destination)
                    current_url = destination
                    continue
                raise RuntimeError(f"Gallery request failed with HTTP {exc.code}") from exc
        raise RuntimeError("Gallery request exceeded the redirect limit")


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(
        self,
        req: Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        return None


def _validate_final_url(initial: str, final: str) -> None:
    initial_url = urlsplit(initial)
    final_url = urlsplit(final)
    if (
        final_url.scheme != "https"
        or final_url.username is not None
        or final_url.password is not None
        or final_url.fragment
    ):
        raise ValueError("Gallery request redirected to an unsafe URL")
    initial_host = initial_url.hostname
    final_host = final_url.hostname
    allowed: set[str | None]
    if initial_host == "github.com":
        allowed = {
            "github.com",
            "objects.githubusercontent.com",
            "release-assets.githubusercontent.com",
        }
    elif initial_host == "raw.githubusercontent.com":
        allowed = {"raw.githubusercontent.com"}
    elif initial_host == "codeberg.org":
        allowed = {"codeberg.org"}
    else:
        allowed = {initial_host}
    if final_host not in allowed:
        raise ValueError("Gallery request redirected to an unexpected host")
