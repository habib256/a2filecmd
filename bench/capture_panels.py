#!/usr/bin/env python3
"""The README and manual screenshot: the 80-column ProDOS panels, from the
published enhanced XL image, at the display's aspect ratio.

    make disk && python3 bench/capture_panels.py [--out docs/screenshots]

POM2 renders 80-column text as 560 x 192: one pixel per half column, one
per scan line, a 2.9:1 picture that looks squashed. A monitor shows those
192 lines twice as tall as a half column is wide, so each line is doubled:
560 x 384, the proportions of the real screen. The image boots from a
throwaway copy; the dist file is compared unchanged afterwards. A JSON
note records the image hash and preset next to the capture, and a text
dump of the screen goes with it for review.
"""

import argparse, hashlib, json, struct, sys, tempfile, urllib.request, zlib
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pom2 import VERSION, Pom2, Session, ROOT, labels


def ppm_pixels(data):
    """Width, height and RGB rows of a binary P6 file."""
    fields, i = [], 0
    while len(fields) < 4:
        while data[i:i + 1].isspace(): i += 1
        if data[i:i + 1] == b'#':
            while data[i:i + 1] != b'\n': i += 1
            continue
        j = i
        while not data[j:j + 1].isspace(): j += 1
        fields.append(data[i:j]); i = j
    if fields[0] != b'P6' or int(fields[3]) != 255:
        raise ValueError('not an 8-bit P6 picture')
    w, h = int(fields[1]), int(fields[2])
    i += 1
    return w, h, [data[i + y * w * 3:i + (y + 1) * w * 3] for y in range(h)]


def png(w, rows):
    def chunk(kind, body):
        return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body))
    raw = b''.join(b'\0' + r for r in rows)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, len(rows), 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b''))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=str(ROOT / 'docs/screenshots'))
    args = ap.parse_args()
    out = Path(args.out)
    image = ROOT / f'dist/A2FILECMD-XL-65C02-enhanced-{VERSION}.2mg'
    before = image.read_bytes()
    if before[:4] != b'2IMG':
        sys.exit(f'{image}: not a 2IMG file')
    with tempfile.TemporaryDirectory(prefix='a2fc-capture-') as tmp:
        hdv = Path(tmp) / 'A2FILECMD.hdv'
        hdv.write_bytes(before[64:])
        with Pom2(hdv, port=6999, mouse=True, preset='iie') as p:
            s = Session(p, labels(ROOT / 'build/a2fc.lbl'))
            s.boot()
            s.wait(lambda: '/DEMO' in s.rows()[0][40:], 'DEMO in the right panel', 60)
            p.stable()
            text = '\n'.join(s.rows()) + '\n'
            with urllib.request.urlopen(p.base + '/screen.ppm') as response:
                w, h, rows = ppm_pixels(response.read())
    if image.read_bytes() != before:
        sys.exit(f'{image} changed during the capture')
    if (w, h) == (560, 192):
        rows = [r for r in rows for _ in (0, 1)]          # one scan line, twice as tall
    elif (w, h) != (560, 384):
        sys.exit(f'unexpected POM2 picture {w}x{h}')
    name = f'prodos-panels-{VERSION}'
    (out / f'{name}.png').write_bytes(png(560, rows))
    (out / f'{name}.txt').write_text(text)
    (out / f'{name}.json').write_text(json.dumps({
        'version': VERSION,
        'date': date.today().isoformat(),
        'emulator': 'POM2 pom2_playtest, disposable copy; no file operation',
        'image': image.name,
        'sha256': hashlib.sha256(before).hexdigest(),
        'preset': 'iie',
        'size': '560x384, each 80-column scan line doubled',
    }, indent=2) + '\n')
    print(f'{out / name}.png: 560x{len(rows)}')


if __name__ == '__main__':
    main()
