#!/usr/bin/env python3
"""Le contrat de disposition memoire d'A2 Retro Cmd, verifie a chaque lien.

Deux choses que ld65 ne verifie pas, et qui ont chacune coute une soiree :

  1. Le lanceur (loader.c) et le lieur doivent s'accorder sur la coupe du
     fichier : 3 Ko d'image carte langage en $1000, 1 Ko de code LOWEXE en
     $1C00, le reste en $4000. Une constante changee d'un cote seulement
     produit un binaire qui se charge et part dans le decor.

  2. Tout ce qui survit a l'initialisation -- CODE, RODATA, DATA, INIT, et la
     BSS ou qu'elle soit -- doit finir sous le plancher de la pile C. ld65
     dimensionne la zone BSS par __HIMEM__ - __STACKSIZE__ - __ONCE_RUN__ et
     lit le resultat en entier NON SIGNE : quand il passe en negatif, il pose
     la BSS au milieu de la pile, sans un mot. Le lien reussit, le programme
     se corrompt a l'usage. Seul ONCE a le droit de depasser : il est mort
     avant le premier appel de main().

    python3 tools/check_layout.py --lbl build/a2rc.lbl --bin build/A2RETRO.CODE.BIN
"""
import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def check_layout(s, loader, length):
    errors = []
    def require(ok, message):
        if not ok:
            errors.append(message)
    stage, lc, entry = (loader[k] for k in ('LC_STAGE', 'LC_BYTES', 'CODE_ADDR'))
    prefix = loader['STAGE_BYTES']          # l'image LC, plus le code LOWEXE
    require(s['__LCIMAGE_FILEOFFS__'] == 0, 'LC must be the first bytes in the file')
    require(s['__LCIMAGE_START__'] == stage, 'LC staging address differs from loader')
    require(s['__LCIMAGE_SIZE__'] == lc, 'LC image size differs from loader')
    require(lc <= prefix, 'the staged prefix cannot be smaller than the LC image')
    require(s['__MAIN_FILEOFFS__'] == prefix, 'MAIN file offset differs from loader')
    require(s['__MAIN_START__'] == entry, 'MAIN entry address differs from loader')
    require(0x0C00 <= stage and stage + prefix <= 0x2000,
            'staging overlaps the ProDOS buffers or the graphics page')
    # Le code loge au-dessus de l'image LC dans le meme prefixe : il doit
    # commencer apres elle, et la BSS basse ne doit pas venir l'ecraser.
    require(s['__LOWEXE_RUN__'] >= stage + lc, 'LOWEXE starts inside the LC staging area')
    require(s['__LOWEXE_RUN__'] + s['__LOWEXE_SIZE__'] <= stage + prefix,
            'LOWEXE runs past the staged prefix')
    require(s['__LOWBSS_RUN__'] + s['__LOWBSS_SIZE__'] <= s['__LOWEXE_RUN__'],
            'low BSS runs into LOWEXE')
    require(0xD400 <= s['__LC_START__'] <= s['__LC_LAST__'] <= 0xE000,
            'LC code crosses its bank-2 execution window')
    require(s['__LC_LAST__'] - s['__LC_START__'] <= lc, 'LC code exceeds the fixed image')
    require(s['__LCIMAGE_LAST__'] - stage == s['__LC_LAST__'] - s['__LC_START__'],
            'LC staging and execution lengths differ')
    require(entry < s['__MAIN_LAST__'] <= 0xBF00,
            'MAIN image is empty or overlaps the ProDOS system page')
    require(length == prefix + s['__MAIN_LAST__'] - entry,
            'file length does not match the split-load layout')
    floor = s['__HIMEM__'] - s['__STACKSIZE__']
    require(s['__ONCE_RUN__'] <= floor,
            'the cold end (${:04X}) runs into the C stack (${:04X})'.format(
                s['__ONCE_RUN__'], floor))
    require(s['__BSS_RUN__'] + s['__BSS_SIZE__'] <= floor,
            'BSS (${:04X}-${:04X}) runs into the C stack (${:04X})'.format(
                s['__BSS_RUN__'], s['__BSS_RUN__'] + s['__BSS_SIZE__'] - 1, floor))
    return errors


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--loader', type=Path, default=ROOT / 'src/loader.c')
    ap.add_argument('--lbl', type=Path, default=ROOT / 'build/a2rc.lbl',
                    help='table de symboles ld65 (-Ln)')
    ap.add_argument('--bin', type=Path, default=ROOT / 'build/A2RETRO.CODE.BIN',
                    help="l'image a charge separee")
    args = ap.parse_args()
    s = {name: int(value, 16) for value, name in re.findall(
        r'^al ([0-9A-Fa-f]+) \.([\w]+)$', args.lbl.read_text(), re.M)}
    loader = {name: int(value, 0) for name, value in re.findall(
        r'^#define (LC_STAGE|LC_BYTES|CODE_ADDR|STAGE_BYTES)\s+(0x[0-9A-Fa-f]+|\d+)',
        args.loader.read_text(), re.M)}
    try:
        errors = check_layout(s, loader, args.bin.stat().st_size)
    except KeyError as exc:
        errors = [f'missing layout symbol or loader constant: {exc}']
    if errors:
        for error in errors:
            print('LAYOUT ERROR: ' + error)
        return 1
    print(f"layout: {loader['STAGE_BYTES']} bytes staged at ${loader['LC_STAGE']:04X}, "
          f"MAIN ${s['__MAIN_START__']:04X}-${s['__MAIN_LAST__'] - 1:04X}, "
          f"cold end ${s['__ONCE_RUN__']:04X} under a {s['__STACKSIZE__']}-byte C stack, valid")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
