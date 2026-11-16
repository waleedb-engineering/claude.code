"""Extraktion: HTML → Artikeltext, PDF → Text, Audio/Video → Transkript.

Alle Eingaben sind nicht vertrauenswürdig: es wird ausschließlich Text
gewonnen, nichts ausgeführt, und die Ergebnisse werden in der Länge begrenzt.
"""

from __future__ import annotations

import os
import re
from html.parser import HTMLParser

from .errors import StudioError

MAX_TEXT_CHARS = 200_000
MAX_PDF_PAGES = 300

_SKIP = {"script", "style", "noscript", "template", "svg", "nav", "footer",
         "header", "aside", "form", "button", "iframe", "select"}
_BLOCK = {"p", "h1", "h2", "h3", "h4", "li", "blockquote", "figcaption", "pre", "td"}
_VOID = {"br", "img", "meta", "link", "hr", "input", "source", "area", "base",
         "col", "embed", "track", "wbr"}
_WS = re.compile(r"[ \t\r\f\v]+")


def clean_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = "".join(ch for ch in text if ch == "\n" or ch == "\t" or ord(ch) >= 32)
    lines = [_WS.sub(" ", line).strip() for line in text.split("\n")]
    out, blank = [], False
    for line in lines:
        if line:
            out.append(line)
            blank = False
        elif not blank and out:
            out.append("")
            blank = True
    return "\n".join(out).strip()[:MAX_TEXT_CHARS]


class _ArticleParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.meta: dict[str, str] = {}
        self.lang = ""
        self._stack: list[str] = []
        self._skip_depth = 0
        self._in_title = False
        self._article_depth = 0
        self._buf: list[str] = []
        self.blocks_all: list[str] = []
        self.blocks_article: list[str] = []
        self._block_tag: str | None = None

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "html" and a.get("lang"):
            self.lang = a["lang"][:5].lower()
        if tag == "meta":
            key = (a.get("property") or a.get("name") or "").lower()
            if key and a.get("content"):
                self.meta.setdefault(key, a["content"].strip()[:1000])
            return
        if tag in _VOID:
            if tag == "br" and self._block_tag:
                self._buf.append(" ")
            return
        self._stack.append(tag)
        if tag in _SKIP:
            self._skip_depth += 1
        if tag == "title":
            self._in_title = True
        if tag in ("article", "main"):
            self._article_depth += 1
        if tag in _BLOCK and not self._skip_depth and self._block_tag is None:
            self._block_tag = tag
            self._buf = []

    def handle_endtag(self, tag):
        if tag in _VOID:
            return
        if tag == self._block_tag:
            self._flush()
        if tag == "title":
            self._in_title = False
        while self._stack:
            top = self._stack.pop()
            if top in _SKIP:
                self._skip_depth = max(0, self._skip_depth - 1)
            if top in ("article", "main"):
                self._article_depth = max(0, self._article_depth - 1)
            if top == tag:
                break

    def _flush(self) -> None:
        text = re.sub(r"\s+", " ", "".join(self._buf)).strip()
        if len(text) >= 2:
            self.blocks_all.append(text)
            if self._article_depth:
                self.blocks_article.append(text)
        self._buf = []
        self._block_tag = None

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif self._block_tag and not self._skip_depth:
            self._buf.append(data)


def _decode(body: bytes, content_type: str) -> str:
    m = re.search(r"charset=([\w.-]+)", content_type or "", re.I)
    candidates = [m.group(1)] if m else []
    head = body[:2048].decode("ascii", "ignore")
    m2 = re.search(r"charset=[\"']?([\w.-]+)", head, re.I)
    if m2:
        candidates.append(m2.group(1))
    for enc in candidates + ["utf-8"]:
        try:
            return body.decode(enc)
        except (LookupError, UnicodeDecodeError):
            continue
    return body.decode("utf-8", "replace")


def extract_html(body: bytes, content_type: str = "text/html") -> dict:
    """Gewinnt Titel, Beschreibung und Fließtext aus einer HTML-Seite."""
    raw = _decode(body, content_type)
    if (content_type or "").split(";")[0].strip().lower() == "text/plain":
        text = clean_text(raw)
        if not text:
            raise StudioError("extraction_empty", "Die Seite enthält keinen Text.", 422)
        return {"title": text.split("\n", 1)[0][:140], "description": "",
                "site_name": "", "language": "", "text": text,
                "word_count": len(text.split())}
    parser = _ArticleParser()
    try:
        parser.feed(raw)
        parser.close()
    except Exception as exc:  # noqa: BLE001 — kaputtes HTML ist ein Nutzerfehler
        raise StudioError("extraction_failed", "Die Seite konnte nicht gelesen werden.", 422) from exc
    article = "\n\n".join(parser.blocks_article)
    everything = "\n\n".join(parser.blocks_all)
    text = clean_text(article if len(article) >= 400 else everything)
    meta = parser.meta
    title = clean_text(meta.get("og:title") or parser.title)[:200]
    description = clean_text(meta.get("og:description") or meta.get("description") or "")[:500]
    if not text and description:
        text = description
    if not text:
        raise StudioError(
            "extraction_empty",
            "Auf der Seite wurde kein lesbarer Text gefunden (evtl. rein "
            "JavaScript-basiert oder hinter einem Login).", 422)
    return {
        "title": title,
        "description": description,
        "site_name": clean_text(meta.get("og:site_name") or "")[:100],
        "language": parser.lang,
        "text": text,
        "word_count": len(text.split()),
    }


def extract_pdf(path: str) -> dict:
    """Textextraktion aus einem PDF (pypdf). Kein OCR für gescannte PDFs."""
    try:
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError
    except ImportError as exc:
        raise StudioError(
            "pdf_dependency_missing",
            "PDF-Unterstützung fehlt. Bitte `pip install pypdf` ausführen.", 503) from exc
    try:
        with open(path, "rb") as fh:
            if fh.read(5) != b"%PDF-":
                raise StudioError("pdf_invalid", "Die Datei ist kein gültiges PDF.", 415)
        reader = PdfReader(path)
        if reader.is_encrypted:
            raise StudioError("pdf_encrypted", "Das PDF ist passwortgeschützt.", 422)
        pages = reader.pages
        total_pages = len(pages)
        parts = []
        for index in range(min(total_pages, MAX_PDF_PAGES)):
            try:
                parts.append(pages[index].extract_text() or "")
            except Exception:  # noqa: BLE001 — einzelne defekte Seite überspringen
                parts.append("")
        title = ""
        try:
            title = str((reader.metadata or {}).get("/Title") or "")
        except Exception:  # noqa: BLE001
            title = ""
    except StudioError:
        raise
    except (PdfReadError, OSError, ValueError, KeyError) as exc:
        raise StudioError("pdf_invalid", "Das PDF konnte nicht gelesen werden.", 422) from exc
    text = clean_text("\n\n".join(parts))
    if len(text) < 20:
        raise StudioError(
            "pdf_no_text",
            "Das PDF enthält keinen auslesbaren Text (vermutlich gescannt — OCR "
            "wird nicht unterstützt).", 422)
    return {
        "title": clean_text(title)[:200] or os.path.splitext(os.path.basename(path))[0],
        "pages": total_pages,
        "pages_read": min(total_pages, MAX_PDF_PAGES),
        "truncated": total_pages > MAX_PDF_PAGES,
        "text": text,
        "word_count": len(text.split()),
    }


def transcribe_media(path: str, settings, transcriber=None) -> dict:
    """Audio/Video → Transkript-JSON (lokales Whisper, injizierbar für Tests)."""
    from ..transcribe import transcribe_video, transcript_to_json

    fn = transcriber or transcribe_video
    try:
        transcript = fn(path, settings)
    except RuntimeError as exc:
        raise StudioError(
            "transcription_unavailable",
            "Lokale Transkription nicht verfügbar: faster-whisper ist nicht "
            "installiert (`pip install faster-whisper`).", 503) from exc
    except Exception as exc:  # noqa: BLE001
        raise StudioError(
            "transcription_failed",
            f"Die Transkription ist fehlgeschlagen ({type(exc).__name__}).", 500) from exc
    data = transcript_to_json(transcript)
    if not data["segments"]:
        raise StudioError("transcription_empty", "Es wurde keine Sprache erkannt.", 422)
    return data
