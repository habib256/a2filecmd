#!/usr/bin/env python3
"""Le contrat de disposition memoire d'A2 File Cmd, verifie a chaque lien.

Trois choses que ld65 ne verifie pas, et qui ont chacune coute une soiree :

  1. Le lanceur (loader.c) et le lieur doivent s'accorder sur la coupe du
     fichier : 3 Ko d'image carte langage en $1000, le reste en $4000. Une
     constante changee d'un cote seulement produit un binaire qui se charge
     et part dans le decor.

  3. Les surcouches (des fichiers a part que A2FC lit en $1B00 a la
     demande : IMAGE, TEXT, HEX, DELETE, HELP, MUSIC, RUN, ATTR, et les
     grandes EDIT et MENU qui prennent aussi la page graphique) doivent
     tenir entre la fin de la RAM basse et leur plafond -- la page graphique,
     ou ce qu'une grande surcouche y garde pour elle --, et chaque fichier
     doit faire exactement la longueur que le lieur annonce.

  2. Tout ce qui survit a l'initialisation -- CODE, RODATA, DATA, INIT, et la
     BSS ou qu'elle soit -- doit finir sous le plancher de la pile C. ld65
     dimensionne la zone BSS par __HIMEM__ - __STACKSIZE__ - __ONCE_RUN__ et
     lit le resultat en entier NON SIGNE : quand il passe en negatif, il pose
     la BSS au milieu de la pile, sans un mot. Le lien reussit, le programme
     se corrompt a l'usage. Seul ONCE a le droit de depasser : il est mort
     avant le premier appel de main().

    python3 tools/check_layout.py --lbl build/a2fc.lbl --bin build/A2FILE.CODE.BIN
"""
import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


# Les surcouches, une zone memoire chacune, et le plafond de chacune : la
# page graphique pour les petites ; pour les grandes (EDIT, MENU), le debut
# de ce qu'elles y gardent pour elles (le texte de l'editeur, la liste du
# menu).
OVERLAYS = {'IMAGE': 0x2000, 'TEXT': 0x2000, 'HEX': 0x2000, 'DELETE': 0x2000, 'HELP': 0x2000,
            'MUSIC': 0x2000, 'RUN': 0x2000, 'ATTR': 0x2000, 'EDIT': 0x2800, 'MENU': 0x3000,
            'DISKIMG': 0x3400, 'IMGFS': 0x2000, 'DOS33': 0x2000, 'UNSHRINK': 0x3000}


def check_layout(s, loader, length, overlays=None):
    """`overlays` : {nom: longueur du fichier}, None pour ne pas les verifier."""
    errors = []
    def require(ok, message):
        if not ok:
            errors.append(message)
    stage, lc, entry = (loader[k] for k in ('LC_STAGE', 'LC_BYTES', 'CODE_ADDR'))
    prefix = loader['STAGE_BYTES']          # l'image LC, et rien d'autre
    require(s['__LCIMAGE_FILEOFFS__'] == 0, 'LC must be the first bytes in the file')
    require(s['__LCIMAGE_START__'] == stage, 'LC staging address differs from loader')
    require(s['__LCIMAGE_SIZE__'] == lc, 'LC image size differs from loader')
    require(lc <= prefix, 'the staged prefix cannot be smaller than the LC image')
    require(s['__MAIN_FILEOFFS__'] == prefix, 'MAIN file offset differs from loader')
    require(s['__MAIN_START__'] == entry, 'MAIN entry address differs from loader')
    require(0x0C00 <= stage and stage + prefix <= 0x2000,
            'staging overlaps the ProDOS buffers or the graphics page')
    # La fenetre de surcouche : au-dessus de la RAM basse (que la BSS ne doit
    # pas quitter), sous la page graphique, et chaque fichier de la longueur
    # que le lieur lui donne.
    low_end = s['__LOWRAM_START__'] + s['__LOWRAM_SIZE__']
    require(s['__LOWBSS_RUN__'] + s['__LOWBSS_SIZE__'] <= low_end,
            'low BSS runs into the overlay window')
    for name, ceiling in OVERLAYS.items():
        start = s['__%s_START__' % name]
        # code segment NAME then rodata segment NAMERO, both in the same file
        last = s.get('__%sRO_LAST__' % name) or s['__%s_LAST__' % name]
        require(start >= low_end, name + ' overlay starts inside the low RAM')
        require(last <= ceiling, name + ' overlay runs past ${:04X}'.format(ceiling))
        if overlays is not None:
            require(overlays.get(name) == last - start,
                    name + ' overlay file length does not match the link')
    require(0xD400 <= s['__LC_START__'] <= s['__LC_LAST__'] <= 0xE000,
            'LC code crosses its bank-2 execution window')
    require(s['__LC_LAST__'] - s['__LC_START__'] <= lc, 'LC code exceeds the fixed image')
    require(s['__LCIMAGE_LAST__'] - stage == s['__LC_LAST__'] - s['__LC_START__'],
            'LC staging and execution lengths differ')
    require(entry < s['__MAIN_LAST__'] <= 0xBF00,
            'MAIN image is empty or overlaps the ProDOS system page')
    # Le lanceur (loader.c) tient sa pile C en $BF00 et lit A2FILE.CODE jusqu'a
    # __MAIN_LAST__ : il lui faut au moins 32 octets sous $BF00, sinon son dernier
    # fread ecrase son propre cadre et l'amorcage se fige sur l'ecran-titre. Vu
    # deux fois (un tableau local de 64 octets, puis 31 octets de litteral).
    require(s['__MAIN_LAST__'] <= 0xBEE0,
            'A2FILE.CODE ends at ${:04X}: under 32 bytes below $BF00 for the loader stack (ceiling $BEE0)'.format(
                s['__MAIN_LAST__']))
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
    ap.add_argument('--lbl', type=Path, default=ROOT / 'build/a2fc.lbl',
                    help='table de symboles ld65 (-Ln)')
    ap.add_argument('--bin', type=Path, default=ROOT / 'build/A2FILE.CODE.BIN',
                    help="l'image a charge separee")
    args = ap.parse_args()
    s = {name: int(value, 16) for value, name in re.findall(
        r'^al ([0-9A-Fa-f]+) \.([\w]+)$', args.lbl.read_text(), re.M)}
    loader = {name: int(value, 0) for name, value in re.findall(
        r'^#define (LC_STAGE|LC_BYTES|CODE_ADDR|STAGE_BYTES)\s+(0x[0-9A-Fa-f]+|\d+)',
        args.loader.read_text(), re.M)}
    overlays = {}
    for name in OVERLAYS:                  # le lieur les ecrit a cote : %O.NOM
        f = args.bin.with_name(args.bin.name + '.' + name)
        overlays[name] = f.stat().st_size if f.exists() else None
    try:
        errors = check_layout(s, loader, args.bin.stat().st_size, overlays)
    except KeyError as exc:
        errors = [f'missing layout symbol or loader constant: {exc}']
    if errors:
        for error in errors:
            print('LAYOUT ERROR: ' + error)
        return 1
    print(f"layout: {loader['STAGE_BYTES']} bytes staged at ${loader['LC_STAGE']:04X}, "
          f"MAIN ${s['__MAIN_START__']:04X}-${s['__MAIN_LAST__'] - 1:04X}, "
          f"cold end ${s['__ONCE_RUN__']:04X} under a {s['__STACKSIZE__']}-byte C stack, "
          + ', '.join(f"{n} overlay {overlays[n]} bytes at ${s['__%s_START__' % n]:04X}"
                      for n in OVERLAYS) + ', valid')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
