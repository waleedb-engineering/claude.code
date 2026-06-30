"""Deterministische Tests für die Reframe-Crop-Mathematik (ohne OpenCV/ffmpeg)."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from clipforge.reframe import (
    center_crop_filter,
    compute_scaled_and_crop,
    plan_reframe,
)


def test_scaled_dims_cover_landscape():
    sw, sh, x, y = compute_scaled_and_crop(1280, 720, 1080, 1920, 0.5)
    # Landscape 16:9 -> auf Höhe 1920 skaliert, Breite > 1080
    assert sh == 1920
    assert sw >= 1080
    assert sw % 2 == 0 and sh % 2 == 0
    # Center-Fokus -> x mittig
    assert abs(x - (sw - 1080) // 2) <= 1
    assert y == 0


def test_focus_left_moves_crop_left():
    _sw, _sh, x_center, _ = compute_scaled_and_crop(1280, 720, 1080, 1920, 0.5)
    _sw, _sh, x_left, _ = compute_scaled_and_crop(1280, 720, 1080, 1920, 0.2)
    assert x_left < x_center  # Fokus links -> Crop weiter links


def test_crop_x_clamped_in_range():
    sw, _sh, x0, _ = compute_scaled_and_crop(1280, 720, 1080, 1920, 0.0)
    sw, _sh, x1, _ = compute_scaled_and_crop(1280, 720, 1080, 1920, 1.0)
    assert x0 == 0
    assert x1 == sw - 1080


def test_portrait_source_no_horizontal_room():
    # Quelle bereits hochkant -> kein horizontaler Spielraum
    sw, _sh, x, _ = compute_scaled_and_crop(1080, 1920, 1080, 1920, 0.2)
    assert sw == 1080 and x == 0


def test_center_mode_uses_center_filter():
    crop, info = plan_reframe(
        "/nonexistent.mp4", 0.0, 10.0, 1280, 720, 1080, 1920, "center"
    )
    assert crop == center_crop_filter(1080, 1920)
    assert info["applied_mode"] == "center"
    assert info["fallback"] is False


def test_unknown_resolution_falls_back_center():
    crop, info = plan_reframe(
        "/nonexistent.mp4", 0.0, 10.0, 0, 0, 1080, 1920, "smart"
    )
    assert crop == center_crop_filter(1080, 1920)
    assert info["applied_mode"] == "center"
    assert info["fallback"] is True


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ✓ {fn.__name__}")
    print(f"\n{len(fns)} Tests bestanden.")


if __name__ == "__main__":
    _run_all()
