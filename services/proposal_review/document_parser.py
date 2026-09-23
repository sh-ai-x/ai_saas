"""Bounded local HTML/PDF parsing for proposal review."""

from __future__ import annotations

import hashlib
import ipaddress
import re
import socket
from dataclasses import dataclass
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlsplit
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class DocumentSection:
    title: str
    text: str
    source: str


@dataclass(frozen=True)
class ProposalDocument:
    name: str
    media_type: str
    sha256: str
    sections: tuple[DocumentSection, ...]
    extraction_confidence: float

    def public(self) -> dict[str, object]:
        return {"name": self.name, "media_type": self.media_type, "sha256": self.sha256, "sections": [section.__dict__ for section in self.sections], "extraction_confidence": self.extraction_confidence}


MAX_REMOTE_DOCUMENT_BYTES = 12 * 1024 * 1024
REMOTE_DOCUMENT_TIMEOUT_SECONDS = 10
_PUBLIC_DOCUMENT_TYPES = {"text/html", "application/xhtml+xml", "text/markdown", "text/plain"}


class _HtmlText(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.heading = "Document"
        self.current: list[str] = []
        self.sections: list[DocumentSection] = []
        self.in_heading = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"h1", "h2", "h3"}:
            self._flush()
            self.in_heading = True
            self.current = []

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"h1", "h2", "h3"}:
            title = " ".join("".join(self.current).split()) or "Untitled section"
            self.heading = title[:180]
            self.current = []
            self.in_heading = False
        elif tag.lower() in {"p", "li", "div", "br"}:
            self.current.append("\n")

    def handle_data(self, data: str) -> None:
        self.current.append(data)

    def _flush(self) -> None:
        text = " ".join("".join(self.current).split())
        if text:
            self.sections.append(DocumentSection(self.heading, text[:12_000], "html"))
        self.current = []

    def finish(self) -> tuple[DocumentSection, ...]:
        self._flush()
        return tuple(self.sections)


def _parse_html(data: bytes) -> tuple[DocumentSection, ...]:
    parser = _HtmlText()
    parser.feed(data.decode("utf-8", errors="replace"))
    return parser.finish()


def _parse_text(data: bytes, source: str = "text") -> tuple[DocumentSection, ...]:
    text = data.decode("utf-8", errors="replace")
    sections: list[DocumentSection] = []
    heading = "Document"
    current: list[str] = []
    for line in text.splitlines():
        match = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*$", line)
        if match:
            content = " ".join(" ".join(current).split())
            if content:
                sections.append(DocumentSection(heading[:180], content[:12_000], source))
            heading = match.group(1).strip() or "Untitled section"
            current = []
        else:
            current.append(line)
    content = " ".join(" ".join(current).split())
    if content:
        sections.append(DocumentSection(heading[:180], content[:12_000], source))
    return tuple(sections)


def _parse_pdf(data: bytes) -> tuple[DocumentSection, ...]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise ValueError("PDF parsing requires the pypdf dependency") from exc
    reader = PdfReader(BytesIO(data))
    sections: list[DocumentSection] = []
    for number, page in enumerate(reader.pages, start=1):
        text = " ".join((page.extract_text() or "").split())
        if text:
            sections.append(DocumentSection(f"Page {number}", text[:12_000], f"pdf:p{number}"))
    return tuple(sections)


def parse_document(name: str, data: bytes, *, max_bytes: int = 12 * 1024 * 1024) -> ProposalDocument:
    if not isinstance(name, str) or not name or len(data) <= 0 or len(data) > max_bytes:
        raise ValueError("proposal file is empty or too large")
    suffix = Path(name).suffix.lower()
    if suffix in {".html", ".htm"}:
        sections = _parse_html(data)
        media_type, confidence = "text/html", 1.0
    elif suffix in {".md", ".markdown"}:
        sections = _parse_text(data, "markdown")
        media_type, confidence = "text/markdown", 1.0
    elif suffix in {".txt", ".text"}:
        sections = _parse_text(data)
        media_type, confidence = "text/plain", 1.0
    elif suffix == ".pdf":
        sections = _parse_pdf(data)
        media_type, confidence = "application/pdf", 0.85 if sections else 0.0
    else:
        raise ValueError("proposal must be an HTML, Markdown, PDF, or text file")
    if not sections:
        raise ValueError("proposal contains no extractable text")
    return ProposalDocument(name, media_type, hashlib.sha256(data).hexdigest(), sections, confidence)


def _validate_remote_url(value: str) -> str:
    if not isinstance(value, str) or len(value.strip()) > 2_048:
        raise ValueError("proposal URL is invalid")
    url = value.strip()
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("proposal URL must use http or https")
    if parsed.username or parsed.password:
        raise ValueError("proposal URL must not contain credentials")
    return url


def _assert_public_hostname(hostname: str) -> None:
    normalized = hostname.rstrip(".").lower()
    if normalized in {"localhost", "localhost.localdomain"} or normalized.endswith(".localhost") or normalized.endswith(".local"):
        raise ValueError("proposal URL host must be public")
    try:
        addresses = {ipaddress.ip_address(item[4][0]) for item in socket.getaddrinfo(normalized, None, type=socket.SOCK_STREAM)}
    except socket.gaierror as exc:
        raise ValueError("proposal URL host could not be resolved") from exc
    if not addresses or any(not address.is_global for address in addresses):
        raise ValueError("proposal URL host must resolve to a public address")


def fetch_html_document(
    url: str,
    *,
    max_bytes: int = MAX_REMOTE_DOCUMENT_BYTES,
    timeout: float = REMOTE_DOCUMENT_TIMEOUT_SECONDS,
    opener: object = urlopen,
) -> ProposalDocument:
    """Fetch one public document URL without retaining its source bytes."""

    request_url = _validate_remote_url(url)
    parsed = urlsplit(request_url)
    _assert_public_hostname(parsed.hostname or "")
    request = Request(request_url, headers={"Accept": "text/html,application/xhtml+xml", "User-Agent": "AI-Change-Impact-Workbench/1.0"})
    try:
        response = opener(request, timeout=timeout)  # type: ignore[operator]
        with response:
            final_url = _validate_remote_url(str(response.geturl()))
            final_host = urlsplit(final_url).hostname or ""
            _assert_public_hostname(final_host)
            content_type = str(response.headers.get("Content-Type", "")).split(";", 1)[0].strip().lower()
            if content_type and content_type not in _PUBLIC_DOCUMENT_TYPES:
                raise ValueError("proposal URL must return HTML, Markdown, or plain text")
            data = response.read(max_bytes + 1)
    except ValueError:
        raise
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise ValueError("proposal URL could not be fetched") from exc
    if len(data) > max_bytes:
        raise ValueError("remote proposal is empty or too large")
    final_name = Path(urlsplit(final_url).path).name or "remote-proposal"
    if Path(final_name).suffix.lower() not in {".html", ".htm", ".md", ".markdown", ".txt", ".text"}:
        extension = ".md" if content_type == "text/markdown" else ".txt" if content_type == "text/plain" else ".html"
        final_name = f"{final_name}{extension}"
    return parse_document(final_name, data, max_bytes=max_bytes)


def fetch_local_html_document(
    url: str,
    *,
    host_root: str | Path | None = None,
    mounted_root: str | Path | None = None,
    max_bytes: int = MAX_REMOTE_DOCUMENT_BYTES,
) -> ProposalDocument:
    """Read a file URL from the configured local document mount.

    The browser sends the host's absolute ``file://`` path, while the
    foundation container sees the same directory at ``mounted_root``.  Only
    paths below the configured document host root are translated; arbitrary
    filesystem reads are rejected. The document root is separate from the
    repository selected for code analysis.
    """

    if not isinstance(url, str) or len(url.strip()) > 2_048:
        raise ValueError("proposal file URL is invalid")
    parsed = urlsplit(url.strip())
    if parsed.scheme != "file" or parsed.netloc not in {"", "localhost"}:
        raise ValueError("proposal file URL must use an absolute local path")
    raw_path = unquote(parsed.path)
    if not raw_path.startswith("/"):
        raise ValueError("proposal file URL must use an absolute local path")

    requested = Path(raw_path).expanduser().resolve(strict=False)
    configured_host_root = Path(host_root).expanduser().resolve(strict=False) if host_root else None
    if configured_host_root is None:
        candidate = requested
    else:
        try:
            relative = requested.relative_to(configured_host_root)
        except ValueError as exc:
            raise ValueError("proposal file must be inside the configured local document mount") from exc
        candidate = requested
        if not candidate.is_file() and mounted_root:
            configured_mount = Path(mounted_root).expanduser().resolve(strict=False)
            candidate = (configured_mount / relative).resolve(strict=False)
            try:
                candidate.relative_to(configured_mount)
            except ValueError as exc:
                raise ValueError("proposal file must be inside the configured local document mount") from exc

    if not candidate.is_file():
        raise ValueError("proposal file could not be found in the local document mount")
    if candidate.suffix.lower() not in {".html", ".htm", ".md", ".markdown", ".txt", ".text"}:
        raise ValueError("proposal file URL must point to an HTML, Markdown, or text file")
    if candidate.stat().st_size > max_bytes:
        raise ValueError("local proposal is empty or too large")
    data = candidate.read_bytes()
    return parse_document(candidate.name, data, max_bytes=max_bytes)
