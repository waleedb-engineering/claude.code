"""Video lesen und schreiben ueber ffmpeg-Pipes.

Bewusst nicht ueber cv2.VideoCapture: Handyaufnahmen sind oft HEVC und tragen
eine Drehung in den Metadaten. ffmpeg dreht beim Dekodieren selbst mit,
OpenCV je nach Build nicht -- dann steht der Fahrer quer und jeder Winkel ist
Unsinn.
"""
from __future__ import annotations
import json, subprocess, numpy as np


def probe(path: str) -> dict:
    """Bildrate, Groesse und Drehung aus der Datei LESEN. Nicht raten.

    Eine geratene Bildrate von 30 laesst ein 60er-Handyvideo hinterher in
    halber Geschwindigkeit laufen und verschiebt jede Zeitangabe.
    """
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_streams",
         "-show_format", "-of", "json", path],
        capture_output=True, text=True, check=True).stdout
    d = json.loads(out)
    st = d["streams"][0]

    def frac(s):
        if not s or s == "0/0":
            return None
        n, _, den = s.partition("/")
        den = float(den or 1)
        return float(n) / den if den else None

    fps = frac(st.get("avg_frame_rate")) or frac(st.get("r_frame_rate"))
    rot = 0
    for sd in st.get("side_data_list", []) or []:
        if "rotation" in sd:
            rot = int(round(float(sd["rotation"])))
    if not rot:
        rot = int(st.get("tags", {}).get("rotate", 0) or 0)
    w, h = int(st["width"]), int(st["height"])
    if abs(rot) % 180 == 90:          # ffmpeg dreht beim Dekodieren mit
        w, h = h, w
    n = st.get("nb_frames")
    dur = float(st.get("duration") or d.get("format", {}).get("duration") or 0.0)
    return dict(path=path, fps=float(fps or 0.0), width=w, height=h,
                rotation=rot, codec=st.get("codec_name", "?"),
                duration=dur,
                n_frames=int(n) if n and str(n).isdigit() else int(round(dur * (fps or 0))),
                pix_fmt=st.get("pix_fmt", "?"))


def read_frames(path: str, width: int, height: int, start: int = 0, step: int = 1):
    """Bilder als RGB-Arrays. step>1 ueberspringt Bilder (fuer die Vorpruefung)."""
    cmd = ["ffmpeg", "-v", "error", "-i", path,
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    n = width * height * 3
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, bufsize=n * 4)
    i = 0
    try:
        while True:
            buf = p.stdout.read(n)
            if len(buf) < n:
                break
            if i >= start and (i - start) % step == 0:
                yield i, np.frombuffer(buf, np.uint8).reshape(height, width, 3)
            i += 1
    finally:
        p.stdout.close()
        p.wait()


class H264Writer:
    """Schreibt RGB-Bilder direkt als H.264 -- kein Zwischenfile, laeuft ueberall."""

    def __init__(self, path, width, height, fps):
        # gerade Kantenlaengen: libx264 mit yuv420p verlangt das
        self.w, self.h = width - width % 2, height - height % 2
        self.p = subprocess.Popen(
            ["ffmpeg", "-v", "error", "-y",
             "-f", "rawvideo", "-pix_fmt", "rgb24",
             "-s", f"{self.w}x{self.h}", "-r", f"{fps:.6f}", "-i", "-",
             "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
             "-pix_fmt", "yuv420p", "-movflags", "+faststart",
             "-r", f"{fps:.6f}", path],
            stdin=subprocess.PIPE)

    def write(self, rgb: np.ndarray):
        self.p.stdin.write(np.ascontiguousarray(rgb[:self.h, :self.w]).tobytes())

    def close(self):
        self.p.stdin.close()
        if self.p.wait() != 0:
            raise RuntimeError("ffmpeg konnte das Video nicht schreiben")
