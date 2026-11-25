"""Lädt die kleinen, frei lizenzierten Testmodelle und Testbilder für die
echten (nicht nachgebildeten) Tests: Hintergrundentfernung und Gesichtsprüfung.

    python scripts/fetch_test_models.py <zielordner>

Danach: CLIPFORGE_TEST_MODELS_DIR=<zielordner> pytest api/tests
"""

import hashlib
import os
import sys
import time
import urllib.error
import urllib.request

FILES = {
    "u2netp.onnx": ("https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2netp.onnx",
                    "md5", "8e83ca70e441ab06c318d82300c84806"),
    "face_detection_yunet_2023mar.onnx": (
        "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/"
        "face_detection_yunet/face_detection_yunet_2023mar.onnx", "sha256",
        "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"),
    "face_recognition_sface_2021dec.onnx": (
        "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/"
        "face_recognition_sface/face_recognition_sface_2021dec.onnx", "sha256",
        "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79"),
    # OpenCV-Beispielbilder (nur für Tests, nicht Teil von ClipForge)
    # fester Tag statt wanderndem Branch, mit Prüfsumme
    "lena.jpg": ("https://raw.githubusercontent.com/opencv/opencv/4.10.0/samples/data/lena.jpg", "sha256",
                 "7de7ed51a1594fff247f4cae2301eceacf5313d6011e37b4a4c8733f7bb72c07"),
    "messi5.jpg": ("https://raw.githubusercontent.com/opencv/opencv/4.10.0/samples/data/messi5.jpg", "sha256",
                   "1d570e49654e84c7a943918537bd9e5e1ef82920152e147c834006e235be97c9"),
}


def main(target: str) -> int:
    os.makedirs(target, exist_ok=True)
    for name, (url, algo, digest) in FILES.items():
        dest = os.path.join(target, name)
        if not os.path.exists(dest):
            print("lade", name)
            for attempt in range(4):  # GitHub-Downloads scheitern gelegentlich kurzzeitig (404/5xx)
                try:
                    urllib.request.urlretrieve(url, dest)  # noqa: S310 — feste URLs
                    break
                except (urllib.error.URLError, OSError) as exc:
                    if attempt == 3:
                        raise
                    print(f"  Versuch {attempt + 1} fehlgeschlagen ({exc}), neuer Versuch …")
                    time.sleep(5 * (attempt + 1))
        if algo:
            h = hashlib.new(algo)
            with open(dest, "rb") as fh:
                h.update(fh.read())
            if h.hexdigest() != digest:
                os.remove(dest)
                print("Prüfsumme falsch:", name)
                return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "test_models"))
