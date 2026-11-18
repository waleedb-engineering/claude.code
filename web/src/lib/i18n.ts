"use client";

// Minimale Zweisprachigkeit (DE/EN) für die zentralen Studio-Oberflächen.
// Kein Framework: ein kleiner Store über localStorage + useSyncExternalStore.
// Backend-Fehlermeldungen kommen weiterhin auf Deutsch (siehe docs).

import { useSyncExternalStore } from "react";

export type Locale = "de" | "en";
const KEY = "clipforge.locale";
const listeners = new Set<() => void>();

function read(): Locale {
  try {
    return window.localStorage.getItem(KEY) === "en" ? "en" : "de";
  } catch {
    return "de";
  }
}

export function setLocale(locale: Locale): void {
  try {
    window.localStorage.setItem(KEY, locale);
  } catch {
    /* privater Modus: nur für diese Sitzung */
  }
  document.documentElement.lang = locale;
  listeners.forEach((fn) => fn());
}

function subscribe(fn: () => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function useLocale(): Locale {
  return useSyncExternalStore(subscribe, read, () => "de" as Locale);
}

const DICT = {
  // Navigation
  "nav.dashboard": ["Übersicht", "Dashboard"],
  "nav.create": ["Erstellen", "Create"],
  "nav.automations": ["Automationen", "Automations"],
  "nav.analytics": ["Analytics", "Analytics"],
  "nav.ideas": ["Ideen", "Ideas"],
  "nav.setup": ["Einrichtung", "Setup"],
  // Allgemein
  "common.loading": ["Lädt …", "Loading …"],
  "common.save": ["Speichern", "Save"],
  "common.cancel": ["Abbrechen", "Cancel"],
  "common.delete": ["Löschen", "Delete"],
  "common.retry": ["Erneut versuchen", "Retry"],
  "common.open": ["Öffnen", "Open"],
  "common.reload": ["Neu laden", "Reload"],
  "common.none": ["Keine", "None"],
  "common.language": ["Sprache", "Language"],
  "common.local": ["lokal", "local"],
  "common.paid": ["kostenpflichtig", "paid"],
  "common.estimate": ["Schätzung", "Estimate"],
  // Status
  "status.draft": ["Entwurf", "Draft"],
  "status.ingesting": ["Wird verarbeitet", "Processing"],
  "status.ready": ["Bereit", "Ready"],
  "status.failed": ["Fehlgeschlagen", "Failed"],
  "status.queued": ["In Warteschlange", "Queued"],
  "status.running": ["Läuft", "Running"],
  "status.succeeded": ["Fertig", "Done"],
  "status.canceled": ["Abgebrochen", "Canceled"],
  "status.interrupted": ["Unterbrochen", "Interrupted"],
  "status.not_connected": ["Nicht verbunden", "Not connected"],
  "status.scheduled": ["Geplant", "Scheduled"],
  "status.due": ["Fällig – manuell posten", "Due – post manually"],
  "status.published": ["Veröffentlicht", "Published"],
  "status.not_configured": ["Nicht konfiguriert", "Not configured"],
  "status.unavailable": ["Nicht verfügbar", "Not available"],
  "status.disabled": ["Deaktiviert", "Disabled"],
  // Dashboard
  "dash.title": ["Creator Studio", "Creator Studio"],
  "dash.subtitle": [
    "Von der Quelle bis zum fertigen Video — lokal auf deinem Rechner.",
    "From source to finished video — locally on your machine.",
  ],
  "dash.new": ["Neues Video", "New video"],
  "dash.projects": ["Projekte", "Projects"],
  "dash.empty": [
    "Noch keine Projekte. Starte mit „Neues Video“.",
    "No projects yet. Start with “New video”.",
  ],
  "dash.scenes": ["Szenen", "scenes"],
  "dash.exports": ["Exporte", "exports"],
  "dash.worker_on": ["Automation-Worker läuft", "Automation worker running"],
  "dash.worker_off": ["Automation-Worker läuft nicht", "Automation worker not running"],
  "dash.llm_on": ["Skript-KI aktiv (API-Key gesetzt)", "Script AI active (API key set)"],
  "dash.llm_off": [
    "Ohne API-Key: Skripte entstehen lokal (Zusammenfassung/Gerüst)",
    "No API key: scripts are built locally (summary/outline)",
  ],
  "dash.shorts_job": ["Shorts-Job öffnen", "Open shorts job"],
  "dash.confirm_delete": ["Projekt wirklich löschen?", "Really delete this project?"],
  // Create
  "create.title": ["Neues Video erstellen", "Create a new video"],
  "create.pick": ["1. Workflow wählen", "1. Choose a workflow"],
  "create.details": ["2. Angaben", "2. Details"],
  "create.settings": ["3. Format", "3. Format"],
  "create.submit": ["Projekt anlegen", "Create project"],
  "create.creating": ["Wird angelegt …", "Creating …"],
  "create.uploading": ["Upload", "Upload"],
  "create.processing": ["Quelle wird verarbeitet …", "Processing source …"],
  "create.projectTitle": ["Titel (optional)", "Title (optional)"],
  "create.prompt": ["Thema / Prompt", "Topic / prompt"],
  "create.script": ["Skript", "Script"],
  "create.url": ["URL (öffentlich erreichbar)", "URL (publicly reachable)"],
  "create.file": ["Datei auswählen", "Choose file"],
  "create.files": ["Bilder/Videos auswählen", "Choose images/videos"],
  "create.transcript": [
    "Transkript oder Untertitel (.json/.srt/.vtt, optional, überspringt Whisper)",
    "Transcript or subtitles (.json/.srt/.vtt, optional, skips Whisper)",
  ],
  "create.job": ["Bestehender Job", "Existing job"],
  "create.youtubeUrl": ["YouTube-Link", "YouTube link"],
  "create.youtubeHint": [
    "ClipForge lädt nichts von YouTube herunter. Lade das Video selbst hoch (bei eigenen Videos: YouTube Studio → Herunterladen). Untertitel aus YouTube Studio (.srt/.vtt) sparen die Transkription.",
    "ClipForge never downloads from YouTube. Upload the video yourself (own videos: YouTube Studio → Download). Subtitles from YouTube Studio (.srt/.vtt) skip transcription.",
  ],
  "create.youtubeRights": [
    "Ich bin Rechteinhaber dieses Videos oder habe die Erlaubnis, es zu bearbeiten.",
    "I own this video or have permission to edit it.",
  ],
  "create.noJobs": ["Keine fertigen Jobs vorhanden.", "No completed jobs available."],
  "create.seconds": ["Ziel-Länge (Sekunden)", "Target length (seconds)"],
  "create.aspect": ["Seitenverhältnis", "Aspect ratio"],
  "create.resolution": ["Auflösung", "Resolution"],
  "create.captions": ["Caption-Stil", "Caption style"],
  "create.product.name": ["Produktname", "Product name"],
  "create.product.problem": ["Problem der Zielgruppe", "Audience problem"],
  "create.product.benefits": ["Vorteile (je Zeile einer)", "Benefits (one per line)"],
  "create.product.price": ["Preis (optional)", "Price (optional)"],
  "create.product.cta": ["Handlungsaufforderung", "Call to action"],
  "create.unavailable": ["Nicht verfügbar", "Not available"],
  "create.mediaLines": [
    "Texte je Bild/Video (optional, je Zeile einer)",
    "Text per image/video (optional, one per line)",
  ],
  "wf.prompt": ["Prompt → Video", "Prompt → video"],
  "wf.script": ["Skript → Video", "Script → video"],
  "wf.article_url": ["Artikel/Blog → Video", "Article/blog → video"],
  "wf.website_review": ["Website → Review", "Website → review"],
  "wf.social_url": ["Social-Post → Video", "Social post → video"],
  "wf.pdf": ["PDF → Video", "PDF → video"],
  "wf.audio": ["Audio → Video", "Audio → video"],
  "wf.music": ["Musik → Beat-Video", "Music → beat video"],
  "wf.podcast": ["Podcast → Shorts", "Podcast → shorts"],
  "wf.longform": ["Longform → Shorts", "Long-form → shorts"],
  "wf.media": ["Eigene Medien → Video", "Own media → video"],
  "wf.job": ["Job als Quelle", "Job as source"],
  "wf.product_ad": ["Produkt-Ad", "Product ad"],
  "wf.cinematic": ["Cinematic", "Cinematic"],
  "wf.youtube": ["YouTube → Shorts", "YouTube → shorts"],
  "wf.avatar": ["Talking Avatar", "Talking avatar"],
  "wf.idea": ["Aus Idee", "From idea"],
  // Editor
  "ed.back": ["← Alle Projekte", "← All projects"],
  "ed.saved": ["Gespeichert", "Saved"],
  "ed.saving": ["Speichert …", "Saving …"],
  "ed.unsaved": ["Ungespeicherte Änderungen", "Unsaved changes"],
  "ed.conflict": [
    "Das Projekt wurde an anderer Stelle geändert. Deine letzten Änderungen wurden nicht gespeichert.",
    "The project was changed elsewhere. Your latest changes were not saved.",
  ],
  "ed.undo": ["Rückgängig", "Undo"],
  "ed.redo": ["Wiederholen", "Redo"],
  "ed.scenes": ["Szenen", "Scenes"],
  "ed.scriptMode": ["Als Text bearbeiten", "Edit as text"],
  "ed.sceneMode": ["Szenenansicht", "Scene view"],
  "ed.scriptHint": [
    "Eine Leerzeile trennt Szenen. „Übernehmen“ schreibt den Text zurück in die Szenen.",
    "A blank line separates scenes. “Apply” writes the text back into the scenes.",
  ],
  "ed.apply": ["Übernehmen", "Apply"],
  "ed.addScene": ["Szene hinzufügen", "Add scene"],
  "ed.scene": ["Szene", "Scene"],
  "ed.text": ["Text (Caption)", "Text (caption)"],
  "ed.voiceText": ["Abweichender Sprechtext (optional)", "Different spoken text (optional)"],
  "ed.visualPrompt": ["Visual-Prompt", "Visual prompt"],
  "ed.headline": ["Einblendung (optional)", "Headline overlay (optional)"],
  "ed.visual": ["Visual", "Visual"],
  "ed.media": ["Medium", "Media"],
  "ed.duration": ["Dauer (s, leer = automatisch)", "Duration (s, empty = auto)"],
  "ed.pause": ["Pause danach (s)", "Pause after (s)"],
  "ed.up": ["Nach oben", "Move up"],
  "ed.down": ["Nach unten", "Move down"],
  "ed.duplicate": ["Duplizieren", "Duplicate"],
  "ed.regenerate": ["Szene neu generieren", "Regenerate scene"],
  "ed.originalAudio": ["Original-Audio", "Original audio"],
  "ed.mode.motion": ["Motion-Hintergrund", "Motion background"],
  "ed.mode.static": ["Farbfläche", "Solid colour"],
  "ed.mode.media": ["Eigenes Medium", "Own media"],
  "ed.mode.ai_image": ["KI-Bild (animiert)", "AI image (animated)"],
  "ed.mode.split": ["Split-Screen", "Split screen"],
  "ed.mode.ai_video": ["KI-Video (kostenpflichtig)", "AI video (paid)"],
  "ed.mode.avatar": ["Sprechender Avatar (kostenpflichtig)", "Talking avatar (paid)"],
  "ed.avatarImage": ["Avatar-Bild (Gesicht, frontal)", "Avatar image (face, frontal)"],
  "su.untested": ["ungetestet", "untested"],
  "ac.title": ["Plattform-Konten", "Platform accounts"],
  "ac.connect": ["Verbinden", "Connect"],
  "ac.disconnect": ["Trennen", "Disconnect"],
  "ac.connectedAs": ["verbunden als", "connected as"],
  "ac.notSupported": ["Kein direkter Upload", "No direct upload"],
  "ac.opened": ["Anmeldefenster geöffnet. Nach der Freigabe kommst du hierher zurück.", "Sign-in window opened. You will return here after approving."],
  "status.connected": ["Verbunden", "Connected"],
  "status.expired": ["Abgelaufen", "Expired"],
  "status.uploading": ["Wird hochgeladen", "Uploading"],
  "status.in_platform_drafts": ["In TikTok-Entwürfen – dort veröffentlichen", "In TikTok drafts – publish there"],
  "an.tiktokUpload": ["In TikTok-Entwürfe hochladen", "Upload to TikTok drafts"],
  "an.tiktokConfirm": [
    "Das Video wird in die Entwürfe deines TikTok-Kontos hochgeladen. Veröffentlichen musst du es selbst in der TikTok-App. Fortfahren?",
    "The video will be uploaded to your TikTok drafts. You publish it yourself in the TikTok app. Continue?",
  ],
  "an.refresh": ["Status abfragen", "Check status"],
  "su.untestedHint": [
    "Nur gegen nachgebildete Antworten getestet, noch nie gegen den echten Dienst.",
    "Only tested against simulated responses, never against the real service.",
  ],
  "vc.title": ["Eigene Stimme klonen (ElevenLabs)", "Clone your own voice (ElevenLabs)"],
  "vc.hint": [
    "Nur mit Einwilligung. Die Erklärung wird mit Zeitpunkt gespeichert. Braucht einen ElevenLabs-Schlüssel und einen Tarif mit Stimmklon.",
    "Consent required. The declaration is stored with a timestamp. Needs an ElevenLabs key and a plan that includes cloning.",
  ],
  "vc.name": ["Name der Stimme", "Voice name"],
  "vc.samples": ["Sprachproben (1–5 Audiodateien, je ≤ 10 MB)", "Voice samples (1–5 audio files, ≤ 10 MB each)"],
  "vc.own": ["Es ist meine eigene Stimme.", "It is my own voice."],
  "vc.permission": ["Es ist die Stimme einer anderen Person, die mir schriftlich erlaubt hat, sie zu klonen.", "It is another person's voice who gave me written permission to clone it."],
  "vc.speaker": ["Name dieser Person", "Name of that person"],
  "vc.noDeception": ["Ich werde die Stimme nicht zur Täuschung über die Identität einer Person einsetzen.", "I will not use the voice to deceive anyone about a person's identity."],
  "vc.create": ["Stimme klonen", "Clone voice"],
  "vc.none": ["Noch keine geklonte Stimme.", "No cloned voice yet."],
  "ed.kind.hook": ["Hook", "Hook"],
  "ed.kind.body": ["Inhalt", "Body"],
  "ed.kind.cta": ["CTA", "CTA"],
  "ed.settings": ["Einstellungen", "Settings"],
  "ed.style": ["Look", "Look"],
  "ed.voice": ["Stimme", "Voice"],
  "ed.voiceAuto": ["Automatisch", "Automatic"],
  "ed.voicePreview": ["Hörprobe", "Preview voice"],
  "ed.speed": ["Sprechtempo", "Speaking rate"],
  "ed.noSpeech": [
    "Kein lokaler Sprach-Provider gefunden — das Video wird ohne Stimme gerendert.",
    "No local speech provider found — the video renders without a voice.",
  ],
  "ed.music": ["Musik", "Music"],
  "ed.volume": ["Lautstärke", "Volume"],
  "ed.ducking": ["Unter der Stimme absenken", "Duck under voice"],
  "ed.beatSync": ["Schnitte auf den Beat legen", "Cut on the beat"],
  "ed.useBrand": ["Brand-Kit-Farben und Schrift verwenden", "Use brand kit colours and font"],
  "ed.gameplay": ["Gameplay-Video (für Split-Screen)", "Gameplay video (for split screen)"],
  "ed.budget": ["Budgetlimit (USD)", "Budget limit (USD)"],
  "ed.budgetHint": [
    "0 = es werden nie kostenpflichtige Provider aufgerufen.",
    "0 = paid providers are never called.",
  ],
  "ed.cost": ["Geschätzte Kosten", "Estimated cost"],
  "ed.uploadMedia": ["Medien hochladen", "Upload media"],
  "ed.mediaEmpty": ["Noch keine Medien in diesem Projekt.", "No media in this project yet."],
  "ed.preview": ["Vorschau rendern", "Render preview"],
  "ed.final": ["Final rendern", "Render final"],
  "ed.quality": ["Qualitätsprüfung", "Quality check"],
  "ed.renders": ["Renders", "Renders"],
  "ed.noRenders": ["Noch nichts gerendert.", "Nothing rendered yet."],
  "ed.download": ["Herunterladen", "Download"],
  "ed.export": ["An Publishing übergeben", "Send to publishing"],
  "ed.exported": ["Im Publishing-Planner öffnen", "Open in publishing planner"],
  "ed.versions": ["Versionen", "Versions"],
  "ed.restore": ["Wiederherstellen", "Restore"],
  "ed.reingest": ["Quelle erneut verarbeiten", "Process source again"],
  "ed.empty": [
    "Dieses Projekt hat noch keine Szenen.",
    "This project has no scenes yet.",
  ],
  "ed.linkedJob": [
    "Dieses Projekt läuft über die Shorts-Pipeline. Clips und Publishing findest du im Job.",
    "This project runs through the shorts pipeline. Clips and publishing live in the job.",
  ],
  "ed.blocked": ["Der Render ist blockiert:", "Rendering is blocked:"],
  "ed.remix": ["Remix erstellen", "Create remix"],
  // Automation
  "au.title": ["Automationen", "Automations"],
  "au.safety": [
    "Automationen erstellen Videos und höchstens Entwürfe. Sie veröffentlichen nie.",
    "Automations create videos and at most drafts. They never publish.",
  ],
  "au.new": ["Neue Automation", "New automation"],
  "au.name": ["Name", "Name"],
  "au.frequency": ["Rhythmus", "Frequency"],
  "au.daily": ["Täglich", "Daily"],
  "au.weekly": ["Wöchentlich", "Weekly"],
  "au.monthly": ["Monatlich", "Monthly"],
  "au.time": ["Uhrzeit", "Time"],
  "au.weekday": ["Wochentag", "Weekday"],
  "au.day": ["Tag im Monat", "Day of month"],
  "au.items": [
    "Themen/Skripte/URLs — je Zeile eines, werden der Reihe nach verwendet",
    "Topics/scripts/URLs — one per line, used in rotation",
  ],
  "au.drafts": ["Publishing-Entwürfe anlegen für", "Create publishing drafts for"],
  "au.budgetRun": ["Budget pro Lauf (USD)", "Budget per run (USD)"],
  "au.budgetMonth": ["Monatsbudget (USD, 0 = aus)", "Monthly budget (USD, 0 = off)"],
  "au.next": ["Nächster Lauf", "Next run"],
  "au.paused": ["Pausiert", "Paused"],
  "au.pause": ["Pausieren", "Pause"],
  "au.resume": ["Fortsetzen", "Resume"],
  "au.runNow": ["Jetzt ausführen", "Run now"],
  "au.history": ["Verlauf", "History"],
  "au.noRuns": ["Noch keine Läufe.", "No runs yet."],
  "au.empty": ["Noch keine Automationen.", "No automations yet."],
  "au.create": ["Automation anlegen", "Create automation"],
  "au.project": ["Projekt", "Project"],
  // Analytics
  "an.title": ["Analytics", "Analytics"],
  "an.subtitle": [
    "Echte Ergebnisse veröffentlichter Entwürfe. Es werden keine Zahlen erfunden.",
    "Real results of published drafts. No numbers are made up.",
  ],
  "an.empty": [
    "Noch keine veröffentlichten Entwürfe. Markiere unten einen Entwurf als veröffentlicht, sobald du ihn gepostet hast.",
    "No published drafts yet. Mark a draft as published below once you have posted it.",
  ],
  "an.potential": ["Performance-Potenzial", "Performance potential"],
  "an.views": ["Views", "Views"],
  "an.likes": ["Likes", "Likes"],
  "an.comments": ["Kommentare", "Comments"],
  "an.noData": ["keine Daten", "no data"],
  "an.enter": ["Werte eintragen", "Enter values"],
  "an.sync": ["Von Plattform abrufen", "Sync from platform"],
  "an.manual": ["manuell", "manual"],
  "an.synced": ["synchronisiert", "synced"],
  "an.estimated": ["geschätzt", "estimated"],
  "an.hooks": ["Hook-Varianten im Vergleich", "Hook variants compared"],
  "an.best": ["beste Variante", "best variant"],
  "an.drafts": ["Entwürfe & Planung", "Drafts & scheduling"],
  "an.markPublished": ["Als veröffentlicht markieren", "Mark as published"],
  "an.confirmPublished": [
    "Hast du diesen Beitrag selbst veröffentlicht? ClipForge postet nichts automatisch.",
    "Did you publish this post yourself? ClipForge never posts automatically.",
  ],
  "an.postUrl": ["Link zum Beitrag (optional)", "Link to the post (optional)"],
  "an.noDrafts": ["Noch keine Publishing-Entwürfe.", "No publishing drafts yet."],
  "an.agreement": ["Übereinstimmung Potenzial ↔ Views", "Agreement potential ↔ views"],
  // Ideas
  "id.title": ["Ideen-Bibliothek", "Idea library"],
  "id.subtitle": [
    "Deine eigenen gespeicherten Referenzen. ClipForge liefert keine fremden Daten mit.",
    "Your own saved references. ClipForge ships no third-party data.",
  ],
  "id.add": ["Idee speichern", "Save idea"],
  "id.search": ["Suchen …", "Search …"],
  "id.niche": ["Nische", "Niche"],
  "id.tags": ["Tags (Komma-getrennt)", "Tags (comma-separated)"],
  "id.hook": ["Hook-Typ", "Hook type"],
  "id.format": ["Format", "Format"],
  "id.platform": ["Plattform", "Platform"],
  "id.notes": ["Notizen", "Notes"],
  "id.titleField": ["Titel", "Title"],
  "id.use": ["Als Inspiration verwenden", "Use as inspiration"],
  "id.topic": ["Dein eigenes Thema", "Your own topic"],
  "id.empty": ["Noch keine Ideen gespeichert.", "No ideas saved yet."],
  "id.all": ["Alle", "All"],
  // Produktionsoptionen
  "opt.title": ["Vorgaben (optional)", "Brief (optional)"],
  "opt.platform": ["Ziel-Plattform", "Target platform"],
  "opt.goal": ["Ziel des Videos", "Goal of the video"],
  "opt.audience": ["Zielgruppe", "Audience"],
  "opt.cta": ["Handlungsaufforderung (letzte Szene)", "Call to action (last scene)"],
  "opt.instructions": ["Kreative Hinweise", "Creative instructions"],
  "opt.forbidden": ["Ausgeschlossene Themen (Komma-getrennt)", "Forbidden topics (comma-separated)"],
  "opt.visualStyle": ["Bildstil", "Visual style"],
  "opt.mediaType": ["Standard-Visual", "Default visual"],
  "opt.imageAnimation": ["Bilder animieren (Ken-Burns)", "Animate images (Ken Burns)"],
  "opt.musicNone": ["Ohne Musik rendern", "Render without music"],
  "opt.voiceModel": ["Stimm-Modell (Cloud, optional)", "Voice model (cloud, optional)"],
  "opt.llmHint": [
    "Ziel, Zielgruppe und kreative Hinweise wirken nur mit Skript-KI (API-Key). CTA, ausgeschlossene Themen, Bildstil und Visual wirken immer.",
    "Goal, audience and creative instructions only apply with script AI (API key). CTA, forbidden topics, visual style and visual always apply.",
  ],
  // Credentials
  "cr.title": ["API-Schlüssel", "API keys"],
  "cr.hint": [
    "Schlüssel werden lokal in deiner .env gespeichert (nur für dich lesbar) und wirken sofort, ohne Neustart.",
    "Keys are stored locally in your .env (readable only by you) and take effect immediately, without a restart.",
  ],
  "cr.set": ["Hinterlegt", "Set"],
  "cr.unset": ["Nicht hinterlegt", "Not set"],
  "cr.key": ["Schlüssel", "Key"],
  "cr.save": ["Speichern", "Save"],
  "cr.remove": ["Entfernen", "Remove"],
  "cr.test": ["Schlüssel prüfen", "Test key"],
  // Setup
  "su.title": ["Einrichtung & Bereitschaft", "Setup & readiness"],
  "su.providers": ["Provider", "Providers"],
  "su.platforms": ["Plattformen", "Platforms"],
  "su.needs": ["Benötigt", "Requires"],
  "su.fallback": ["Fallback: Export-Pack", "Fallback: export pack"],
  "su.secrets": [
    "Schlüssel stehen nur in deiner .env. Die Oberfläche zeigt nie Werte an.",
    "Keys live only in your .env. The UI never shows values.",
  ],
} as const;

export type TKey = keyof typeof DICT;

export function translate(locale: Locale, key: TKey): string {
  return DICT[key][locale === "en" ? 1 : 0];
}

export function useT(): (key: TKey) => string {
  const locale = useLocale();
  return (key) => translate(locale, key);
}

/** Übersetzt dynamische Schlüssel (z. B. Status) mit Fallback auf den Rohwert. */
export function tDyn(t: (key: TKey) => string, prefix: string, value: string): string {
  const key = `${prefix}.${value}` as TKey;
  return key in DICT ? t(key) : value;
}
