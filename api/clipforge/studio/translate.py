"""Textübersetzung für die Videoübersetzung (zunächst Deutsch ↔ Englisch).

Engines (erweiterbar über ENGINES):
  argos     – lokal, kostenlos: OPUS-MT-Modelle im Argos-Format, ausgeführt mit
              CTranslate2 + SentencePiece (CTranslate2 kommt mit faster-whisper).
              Modell-Download über Studio → Einrichtung (nach Zustimmung).
  anthropic – Claude (kostenpflichtig, ANTHROPIC_API_KEY, Projektbudget).
  manual    – keine Maschine: Originaltext wird übernommen und im Editor übersetzt.
  mock      – nur Tests (Feature-Flag studio_mock_providers).
"""

from __future__ import annotations

import glob
import json
import os
import re
import zipfile

from .errors import ProviderError, StudioError

LANG_NAMES = {"de": "Deutsch", "en": "English"}
PAIRS = {("de", "en"), ("en", "de")}
# Richtwert Claude: ~1,3 Tokens je Wort, Ein- und Ausgabe; konservativ gerundet
ANTHROPIC_USD_PER_1K_CHARS = 0.006

# Test-Hook für die LLM-Antwort: (system, prompt) -> str
LLM_CALL = None


def model_id(src: str, dst: str) -> str:
    return f"translate_{src}_{dst}"


# ------------------------------------------------------------------ Argos (lokal)
def _argos_dir(src: str, dst: str) -> str | None:
    from .models import model_path
    path = model_path(model_id(src, dst))
    if not path:
        return None
    target = path[: -len(".argosmodel")]
    if not os.path.isdir(target):
        with zipfile.ZipFile(path) as zf:
            for member in zf.namelist():  # Zip-Slip verhindern
                if member.startswith("/") or ".." in member.split("/"):
                    raise StudioError("model_invalid", "Ungültiges Modellpaket.", 502)
            zf.extractall(target + ".tmp")
        os.replace(target + ".tmp", target)
    models = glob.glob(os.path.join(target, "**", "model.bin"), recursive=True)
    return os.path.dirname(models[0]) if models else None


_argos_cache: dict = {}


def _argos(texts: list[str], src: str, dst: str) -> list[str]:
    model_dir = _argos_dir(src, dst)
    if not model_dir:
        raise StudioError("model_missing",
                          f"Übersetzungsmodell {src}→{dst} fehlt. Studio → Einrichtung → "
                          "Lokale KI-Modelle.", 409, details={"model": model_id(src, dst)})
    try:
        import ctranslate2
        import sentencepiece
    except ImportError as exc:
        raise StudioError("dependency_missing",
                          "Für lokale Übersetzung: pip install faster-whisper sentencepiece", 503) from exc
    if model_dir not in _argos_cache:
        root = os.path.dirname(model_dir)
        sp_files = glob.glob(os.path.join(root, "**", "sentencepiece.model"), recursive=True)
        if not sp_files:
            raise StudioError("model_invalid", "SentencePiece-Datei fehlt im Modellpaket.", 502)
        _argos_cache[model_dir] = (ctranslate2.Translator(model_dir, device="cpu"),
                                   sentencepiece.SentencePieceProcessor(model_file=sp_files[0]))
    translator, sp = _argos_cache[model_dir]
    out = []
    for text in texts:
        sentences = [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s]
        if not sentences:
            out.append("")
            continue
        batch = [sp.encode(s, out_type=str) for s in sentences]
        res = translator.translate_batch(batch, beam_size=4, max_decoding_length=256)
        out.append(" ".join(sp.decode(r.hypotheses[0]).replace("▁", " ").strip() for r in res))
    return out


# ------------------------------------------------------------- Claude (bezahlt)
_SYSTEM = ("Du übersetzt Untertitel-Segmente eines Videos. Gib NUR ein JSON-Array mit genau "
           "so vielen Strings zurück, wie Segmente kommen, gleiche Reihenfolge. Natürlich, knapp, "
           "sprechbar; keine Erklärungen.")


def _anthropic(texts: list[str], src: str, dst: str) -> list[str]:
    prompt = (f"Von {LANG_NAMES[src]} nach {LANG_NAMES[dst]}. Segmente:\n"
              + json.dumps(texts, ensure_ascii=False))
    if LLM_CALL is not None:
        raw = LLM_CALL(_SYSTEM, prompt)
    else:
        from ..config import get_settings
        settings = get_settings()
        if not settings.anthropic_api_key:
            raise StudioError("credential_not_set", "Kein Anthropic-Schlüssel hinterlegt.", 409)
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=settings.anthropic_api_key,
                                         timeout=settings.llm_timeout_seconds)
            resp = client.messages.create(model=settings.llm_model, max_tokens=4096,
                                          system=_SYSTEM,
                                          messages=[{"role": "user", "content": prompt}])
            raw = "".join(getattr(b, "text", "") for b in resp.content)
        except Exception as exc:  # noqa: BLE001 — nie Schlüssel/Antwort loggen
            raise ProviderError("anthropic", f"Übersetzung fehlgeschlagen ({type(exc).__name__})") from exc
    match = re.search(r"\[.*\]", raw, re.S)
    try:
        data = json.loads(match.group(0) if match else raw)
    except (ValueError, AttributeError):
        raise ProviderError("anthropic", "Antwort war kein JSON-Array") from None
    if not isinstance(data, list) or len(data) != len(texts):
        raise ProviderError("anthropic", "Anzahl der Segmente stimmt nicht")
    return [str(x).strip() for x in data]


def _mock(texts: list[str], src: str, dst: str) -> list[str]:
    return [f"[{dst}] {t}" for t in texts]


def _manual(texts: list[str], src: str, dst: str) -> list[str]:
    return list(texts)


ENGINES = {"argos": _argos, "anthropic": _anthropic, "manual": _manual, "mock": _mock}
PAID = {"anthropic"}


def engines_status() -> list[dict]:
    from ..config import get_settings
    from .flags import is_enabled
    from .models import model_path
    out = [{"id": "argos", "label": "Lokal (Argos/OPUS-MT)", "paid": False, "live_verified": False,
            "ready": {f"{a}-{b}": bool(model_path(model_id(a, b))) for a, b in sorted(PAIRS)}},
           {"id": "anthropic", "label": "Claude (kostenpflichtig)", "paid": True,
            "live_verified": False, "ready": bool(get_settings().anthropic_api_key)},
           {"id": "manual", "label": "Manuell im Editor", "paid": False, "live_verified": True,
            "ready": True}]
    if is_enabled("studio_mock_providers"):
        out.append({"id": "mock", "label": "Mock (Test)", "paid": False, "live_verified": True,
                    "ready": True})
    return out


def estimate_cost(engine: str, texts: list[str]) -> float:
    if engine not in PAID:
        return 0.0
    chars = sum(len(t) for t in texts)
    return round(chars / 1000 * ANTHROPIC_USD_PER_1K_CHARS * 2, 4)  # Ein- + Ausgabe


def translate(texts: list[str], src: str, dst: str, engine: str) -> list[str]:
    if (src, dst) not in PAIRS:
        raise StudioError("language_unsupported",
                          f"Übersetzung {src}→{dst} wird noch nicht unterstützt (de↔en).", 422)
    if engine not in ENGINES:
        raise StudioError("validation_error", "Unbekannte Übersetzungs-Engine.")
    if engine == "mock":
        from .flags import is_enabled
        if not is_enabled("studio_mock_providers"):
            raise StudioError("validation_error", "Mock-Engine nur im Testmodus.")
    if not texts:
        return []
    return ENGINES[engine](texts, src, dst)
