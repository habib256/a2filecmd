#!/usr/bin/env python3
"""Check the split-load contract between ld65, the game image and loader.c."""
import argparse
import re
from pathlib import Path


def check_layout(s, loader, length):
    errors = []
    def require(ok, message):
        if not ok:
            errors.append(message)
    stage, prefix, entry = (loader[k] for k in ('LC_STAGE', 'LC_BYTES', 'GAME_ADDR'))
    require(s['__LCIMAGE_FILEOFFS__'] == 0, 'LC must be the first bytes in the file')
    require(s['__LCIMAGE_START__'] == stage, 'LC staging address differs from loader')
    require(s['__LCIMAGE_SIZE__'] == prefix, 'LC prefix size differs from loader')
    require(s['__MAIN_FILEOFFS__'] == prefix, 'MAIN file offset differs from loader')
    require(s['__MAIN_START__'] == entry, 'MAIN entry address differs from loader')
    require(0x0C00 <= stage and stage + prefix <= 0x2000,
            'LC staging overlaps ProDOS buffers or the SYSTEM launcher')
    require(0xD400 <= s['__LC_START__'] <= s['__LC_LAST__'] <= 0xE000,
            'LC code crosses its bank-2 execution window')
    require(s['__LC_LAST__'] - s['__LC_START__'] <= prefix,
            'LC code exceeds the fixed prefix')
    require(s['__LCIMAGE_LAST__'] - stage == s['__LC_LAST__'] - s['__LC_START__'],
            'LC staging and execution lengths differ')
    require(entry < s['__MAIN_LAST__'] <= 0xBF00,
            'MAIN image is empty or overlaps the ProDOS system page')
    require(length == prefix + s['__MAIN_LAST__'] - entry,
            'game file length does not match split-load layout')
    return errors


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--src', type=Path, default=Path(__file__).resolve().parents[1]/'SCOSWAMP/SRC')
    # TOTAL partage le lanceur et la disposition du jeu : memes controles,
    # sur sa propre table de symboles et son propre fichier.
    ap.add_argument('--lbl', default='build.lbl', help='table de symboles ld65 (defaut : build.lbl)')
    ap.add_argument('--bin', default='../SCOSWAMP.BIN', help='image a charge separee (defaut : ../SCOSWAMP.BIN)')
    args = ap.parse_args()
    args.src = args.src.resolve()
    s = {name: int(value,16) for value,name in re.findall(
        r'^al ([0-9A-Fa-f]+) \.([\w]+)$', (args.src/args.lbl).read_text(), re.M)}
    loader = {name:int(value,0) for name,value in re.findall(
        r'^#define (LC_STAGE|LC_BYTES|GAME_ADDR)\s+(0x[0-9A-Fa-f]+|\d+)',
        (args.src/'loader.c').read_text(), re.M)}
    try:
        errors = check_layout(s,loader,(args.src/args.bin).stat().st_size)
    except KeyError as exc:
        errors = [f'missing layout symbol or loader constant: {exc}']
    if errors:
        for error in errors:
            print('ERREUR LC : '+error)
        return 1
    print(f"LC : prefixe {loader['LC_BYTES']} octets en ${loader['LC_STAGE']:04X}, "
          f"MAIN ${s['__MAIN_START__']:04X}-${s['__MAIN_LAST__']-1:04X}, disposition valide")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
