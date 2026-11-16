"""Studio: HTML-/PDF-Extraktion, Transkription (Mock), Skripterzeugung."""

from __future__ import annotations

import os
import shutil
import tempfile

from studio_helpers import make_pdf, run_all

from clipforge.config import get_settings
from clipforge.models import Transcript, TranscriptSegment, Word
from clipforge.studio import extract, scriptgen
from clipforge.studio.errors import StudioError

HTML = b"""<!doctype html><html lang="de"><head><title>Seitentitel</title>
<meta property="og:title" content="Lokale Videotools im Test">
<meta name="description" content="Kurzbeschreibung des Artikels.">
<script>var secret = "IGNORE_ME_SCRIPT";</script><style>.x{color:red}</style></head>
<body><nav><p>Navigation Startseite Impressum</p></nav>
<article><h1>Lokale Videotools im Test</h1>
<p>Lokale Videotools verarbeiten Material direkt auf dem eigenen Rechner. Das spart Kosten
und schuetzt private Daten zuverlaessig.</p>
<p>Warum lohnt sich das? Weil keine Minutenpreise anfallen und jede Szene bearbeitbar bleibt.
Viele Teams berichten von deutlich kuerzeren Wartezeiten bei lokalen Videotools.</p>
<p>Ein weiterer Vorteil lokaler Videotools ist die volle Kontrolle ueber Schriften, Farben und
Musik im gesamten Projekt.</p></article>
<footer><p>Footer Copyright Hinweis</p></footer></body></html>"""


def _code(fn) -> str:
    try:
        fn()
    except StudioError as exc:
        return exc.code
    return "no_error"


def test_html_extraction_keeps_article_drops_scripts_and_chrome():
    data = extract.extract_html(HTML, "text/html; charset=utf-8")
    assert data["title"] == "Lokale Videotools im Test"
    assert data["description"] == "Kurzbeschreibung des Artikels."
    assert data["language"] == "de"
    assert "eigenen Rechner" in data["text"]
    for junk in ("IGNORE_ME_SCRIPT", "Navigation", "Footer", "color:red"):
        assert junk not in data["text"], junk
    assert data["word_count"] > 40


def test_html_without_text_is_a_clear_error():
    assert _code(lambda: extract.extract_html(b"<html><body><script>x()</script></body></html>")) == "extraction_empty"
    # og:description als Fallback (Social-Post-Seiten)
    social = b'<html><head><meta property="og:description" content="Mein Post Text hier"></head><body></body></html>'
    assert extract.extract_html(social)["text"] == "Mein Post Text hier"


def test_html_charset_and_plain_text():
    latin = "<html><body><p>Größe und Maße zählen hier wirklich</p></body></html>".encode("latin-1")
    assert "Größe" in extract.extract_html(latin, "text/html; charset=iso-8859-1")["text"]
    assert extract.extract_html(b"Erste Zeile\nZweite Zeile", "text/plain")["title"] == "Erste Zeile"


def test_pdf_text_extraction():
    tmp = tempfile.mkdtemp(prefix="pdf_")
    try:
        path = os.path.join(tmp, "doc.pdf")
        with open(path, "wb") as fh:
            fh.write(make_pdf(["Quarterly report for the local video team.",
                               "Rendering got twice as fast this quarter."]))
        data = extract.extract_pdf(path)
        assert data["pages"] == 1 and "twice as fast" in data["text"]
        assert data["word_count"] >= 10
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_pdf_invalid_and_textless():
    tmp = tempfile.mkdtemp(prefix="pdf_")
    try:
        bad = os.path.join(tmp, "bad.pdf")
        with open(bad, "wb") as fh:
            fh.write(b"MZ this is not a pdf")
        assert _code(lambda: extract.extract_pdf(bad)) == "pdf_invalid"
        broken = os.path.join(tmp, "broken.pdf")
        with open(broken, "wb") as fh:
            fh.write(b"%PDF-1.4\ngarbage garbage")
        assert _code(lambda: extract.extract_pdf(broken)) == "pdf_invalid"
        from pypdf import PdfWriter
        blank = os.path.join(tmp, "blank.pdf")
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        with open(blank, "wb") as fh:
            writer.write(fh)
        assert _code(lambda: extract.extract_pdf(blank)) == "pdf_no_text"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_transcription_with_mock_and_failure_modes():
    def fake(path, settings):
        return Transcript(language="de", duration=2.0, segments=[TranscriptSegment(
            text="Hallo Welt", start=0.0, end=1.0,
            words=[Word("Hallo", 0.0, 0.5), Word("Welt", 0.5, 1.0)])])
    data = extract.transcribe_media("x.wav", get_settings(), fake)
    assert data["language"] == "de" and data["segments"][0]["words"][1]["text"] == "Welt"

    def missing(path, settings):
        raise RuntimeError("faster-whisper ist nicht installiert")
    assert _code(lambda: extract.transcribe_media("x.wav", get_settings(), missing)) == "transcription_unavailable"

    def empty(path, settings):
        return Transcript(language="de", duration=1.0, segments=[])
    assert _code(lambda: extract.transcribe_media("x.wav", get_settings(), empty)) == "transcription_empty"

    def crash(path, settings):
        raise ValueError("boom")
    assert _code(lambda: extract.transcribe_media("x.wav", get_settings(), crash)) == "transcription_failed"


def test_script_from_source_is_extractive_and_local():
    text = extract.extract_html(HTML)["text"]
    script = scriptgen.generate_script(workflow="article_url", source_text=text,
                                       title="Lokale Videotools im Test", language="de",
                                       target_seconds=30, settings=None)
    assert script["generator"] == "rule_based" and not script["needs_review"]
    assert script["scenes"][0]["kind"] == "hook" and script["scenes"][-1]["kind"] == "cta"
    body = [s for s in script["scenes"] if s["kind"] == "body"]
    assert body and all(s["text"] in text or s["text"][:25] in text for s in body)
    assert all(s["visual_prompt"] for s in script["scenes"])


def test_script_workflow_splits_verbatim_and_prompt_is_flagged_outline():
    src = "Erster Satz mit Inhalt. Zweiter Satz mit Inhalt. " * 8
    script = scriptgen.generate_script(workflow="script", source_text=src, language="de")
    assert " ".join(s["text"] for s in script["scenes"]).split() == src.split()
    assert all(len(s["text"].split()) <= 16 for s in script["scenes"])
    outline = scriptgen.generate_script(workflow="prompt", source_text="Kaffee richtig brühen",
                                        language="de")
    assert outline["needs_review"] and any("[" in s["text"] for s in outline["scenes"])


def test_product_ad_uses_only_user_facts():
    script = scriptgen.generate_script(
        workflow="product_ad", source_text="", language="en",
        product={"name": "AquaBottle", "problem": "Your water gets warm.",
                 "benefits": ["Keeps drinks cold for 24 hours", "Fits every cup holder"],
                 "price": "29 EUR", "cta": "Order today"})
    texts = [s["text"] for s in script["scenes"]]
    assert texts[0].startswith("Sound familiar?") and "AquaBottle" in texts[1]
    assert "Keeps drinks cold for 24 hours" in texts and texts[-1] == "Order today"


def test_llm_output_is_untrusted_and_falls_back():
    class Block:
        type = "text"

        def __init__(self, text):
            self.text = text

    class FakeClient:
        def __init__(self, raw):
            self.raw = raw
            self.messages = self

        def create(self, **kwargs):
            assert "untrusted" in kwargs["system"]
            return type("R", (), {"content": [Block(self.raw)]})()

    settings = get_settings()
    good = FakeClient('{"title": "T", "scenes": [{"kind": "hook", "text": "Garantiert viral wird das!"},'
                      '{"kind": "weird", "text": "' + "x " * 900 + '"}, {"text": ""}]}')
    script = scriptgen.generate_script(workflow="prompt", source_text="Thema", language="de",
                                       settings=settings, llm_client=good)
    assert script["generator"] == "llm" and len(script["scenes"]) == 2
    assert "garantiert viral" not in script["scenes"][0]["text"].lower()
    assert "Performance-Potenzial" in script["scenes"][0]["text"]
    assert script["scenes"][1]["kind"] == "body" and len(script["scenes"][1]["text"]) <= 600
    for raw in ("kein json", '{"scenes": "nope"}', '{"scenes": [{"text": "nur eine"}]}'):
        fb = scriptgen.generate_script(workflow="prompt", source_text="Thema", language="de",
                                       settings=settings, llm_client=FakeClient(raw))
        assert fb["generator"] == "rule_based"
        assert any("Fallback" in n for n in fb["notes"])


if __name__ == "__main__":
    run_all(globals())
