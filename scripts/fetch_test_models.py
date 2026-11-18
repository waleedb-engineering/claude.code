"""Lädt die kleinen, frei lizenzierten Testmodelle und Testbilder für die
echten (nicht nachgebildeten) Tests: Hintergrundentfernung und Gesichtsprüfung.

    python scripts/fetch_test_models.py <zielordner>

Danach: CLIPFORGE_TEST_MODELS_DIR=<zielordner> pytest api/tests
"""

import hashlib
import os
import sys
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
    "lena.jpg": ("https://raw.githubusercontent.com/opencv/opencv/4.x/samples/data/lena.jpg", None, None),
    "messi5.jpg": ("https://raw.githubusercontent.com/opencv/opencv/4.x/samples/data/messi5.jpg", None, None),
}


def main(target: str) -> int:
    os.makedirs(target, exist_ok=True)
    for name, (url, algo, digest) in FILES.items():
        dest = os.path.join(target, name)
        if not os.path.exists(dest):
            print("lade", name)
            urllib.request.urlretrieve(url, dest)  # noqa: S310 — feste URLs
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
