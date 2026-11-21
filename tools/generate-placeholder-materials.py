#!/usr/bin/env python3
"""Generate procedural placeholder material textures.

The original photographic material scans were lost with the sonics007 account
(see RECOVERY.md). These seamless-ish procedural textures stand in for them so
the panel, Studio previews and website render and the browser tests run.
Replace them with real scans when available; file names must stay the same.

Usage: python3 tools/generate-placeholder-materials.py   (needs numpy, Pillow)
"""
from pathlib import Path
import numpy as np
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
TARGETS = [ROOT / 'custom_components/aurelvi/frontend/materials', ROOT / 'website/assets/materials']
SIZE = 768
rng = np.random.default_rng(2026)
y, x = np.mgrid[0:SIZE, 0:SIZE] / SIZE


def smooth_noise(scale, octaves=4):
    """Tileable value noise via FFT-filtered white noise."""
    out = np.zeros((SIZE, SIZE))
    for o in range(octaves):
        white = rng.standard_normal((SIZE, SIZE))
        f = np.fft.fft2(white)
        fy = np.fft.fftfreq(SIZE)[:, None]
        fx = np.fft.fftfreq(SIZE)[None, :]
        cutoff = scale * 2 ** o / SIZE
        f *= np.exp(-(fx ** 2 + fy ** 2) / (2 * cutoff ** 2))
        layer = np.real(np.fft.ifft2(f))
        layer = (layer - layer.mean()) / (layer.std() + 1e-9)
        out += layer / 2 ** o
    return (out - out.min()) / (out.max() - out.min())


def colorize(v, dark, light):
    dark, light = np.array(dark, float), np.array(light, float)
    return (dark + (light - dark) * v[..., None]).clip(0, 255).astype(np.uint8)


def brushed(base, spread):
    streaks = rng.standard_normal((SIZE, 1)) * np.ones((1, SIZE))
    streaks = np.real(np.fft.ifft2(np.fft.fft2(streaks) * np.exp(-(np.fft.fftfreq(SIZE)[:, None] * 40) ** 2)))
    fine = rng.standard_normal((SIZE, SIZE)) * .25
    fine = np.array(Image.fromarray(((fine - fine.min()) / np.ptp(fine) * 255).astype(np.uint8)).filter(ImageFilter.BoxBlur(0)), float) / 255
    v = .55 + .25 * (streaks - streaks.mean()) / (streaks.std() + 1e-9) * .4 + .2 * (fine - .5) + .15 * smooth_noise(3, 2)
    return colorize(v.clip(0, 1), [base - spread] * 3, [base + spread] * 3)


def wood(dark, light, rings):
    warp = smooth_noise(2, 2)
    grain = np.sin((x * rings + warp * .9 + .04 * np.sin(y * 6 * np.pi)) * 2 * np.pi)
    streak = rng.standard_normal((1, SIZE)) * np.ones((SIZE, 1))
    streak = np.array(Image.fromarray(((streak - streak.min()) / np.ptp(streak) * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.2)), float) / 255
    v = .5 + .22 * grain + .3 * (streak - .5) + .12 * (smooth_noise(6, 2) - .5)
    return colorize(v.clip(0, 1), dark, light)


def marble(dark, light, vein_dark):
    n = smooth_noise(5, 5)
    veins = np.abs(np.sin((x * 2 + y * 1.3 + n * 2.2) * np.pi))
    veins = veins ** .12
    base = .85 + .15 * smooth_noise(12, 3)
    v = (base * veins).clip(0, 1)
    if vein_dark:
        return colorize(v, dark, light)
    return colorize(1 - v * .0 - (1 - v), dark, light)


def carbon():
    cell = 24
    cx, cy = (np.arange(SIZE)[None, :] // cell), (np.arange(SIZE)[:, None] // cell)
    weave = ((cx + cy) % 2).astype(float)
    sheen = .5 + .5 * np.sin((np.arange(SIZE)[None, :] % cell) / cell * np.pi) * np.ones((SIZE, 1))
    sheen_v = .5 + .5 * np.sin((np.arange(SIZE)[:, None] % cell) / cell * np.pi) * np.ones((1, SIZE))
    v = np.where(weave > 0, sheen, sheen_v) * .7 + .1 * smooth_noise(40, 2)
    return colorize(v.clip(0, 1), [14, 16, 19], [92, 98, 106])


def leather(dark, light):
    pores = smooth_noise(120, 2)
    pebbles = smooth_noise(45, 2)
    v = .45 + .35 * (pebbles - .5) ** 2 * 4 + .2 * (pores - .5) + .2 * smooth_noise(4, 2)
    return colorize(v.clip(0, 1), dark, light)


textures = {
    'aluminium': brushed(196, 26),
    'titanium': brushed(118, 22),
    'carbon': carbon(),
    'oak': wood([176, 133, 88], [226, 194, 148], 9),
    'walnut': wood([58, 36, 24], [126, 86, 58], 11),
    'marble': marble([168, 168, 172], [246, 245, 242], True),
    'black-marble': colorize(1 - (smooth_noise(5, 5) * 0 + np.abs(np.sin((x * 2 + y * 1.3 + smooth_noise(5, 5) * 2.2) * np.pi)) ** .12), [16, 16, 18], [190, 186, 178]),
    'leather': leather([52, 30, 20], [124, 78, 52]),
}

for target in TARGETS:
    target.mkdir(parents=True, exist_ok=True)
    for name, data in textures.items():
        Image.fromarray(data, 'RGB').save(target / f'{name}.webp', quality=84, method=6)
print(f'Wrote {len(textures)} placeholder textures to', ', '.join(str(t.relative_to(ROOT)) for t in TARGETS))
