#!/usr/bin/env python3
"""Banc de la surcouche WIPE (src/plugins/wipe.c) : mettre a zero les blocs
libres d'un volume, ou le volume entier.

    make build-6502/wipe.PLG ARCH=6502 && python3 bench/wipe.py

POM2 ne recopie le disque dur dans son fichier a aucun moment : la preuve
sur l'hote se fait sur une disquette en lecteur 2, ecrite dans son .po a
l'arret de l'emulateur. Et comme la seconde moitie du banc (W, le volume
entier) detruit ce que la premiere (F, les blocs libres) doit prouver, il y
a deux amorcages, chacun avec sa disquette :

1. /WORKPO porte KEEP1, GONE et KEEP2. GONE est supprime depuis A2FC (D
   puis Y), puis WIPE tourne dessus avec F depuis la liste des volumes.
   Sur l'hote on relit le .po : les blocs qu'occupait GONE -- releves dans
   l'image AVANT l'amorcage, bloc index et blocs de donnees -- doivent etre
   a zero, KEEP1 et KEEP2 intacts, l'en-tete du volume intact, et le compte
   annonce a l'ecran egal au nombre de bits libres du bitmap. Au passage, W
   sur /WORKHD, le volume d'amorcage, doit etre refuse.

2. /WIPEPO subit W : un mot autre qu'ERASE n'ecrit rien, puis ERASE efface
   les 280 blocs. Sur l'hote, le bloc 2 (l'en-tete du repertoire de volume)
   et toute l'image sont a zero.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from xplug import boot_hd, menu_run, ok_all, RET, ESC
from pom2 import ROOT
from prodos_read import Image

PORT = 6813
BLOCKS = 280

# GONE fait 3 000 octets : un sapling, un bloc index et six blocs de donnees,
# tous non nuls -- de quoi voir la difference apres le nettoyage.
GONE = b'GONE! ' * 500
KEEP1 = b'keep one\r' * 200
KEEP2 = b'keep two\r' * 30
FILES = {'KEEP1.TXT': KEEP1, 'GONE.TXT': GONE, 'KEEP2.TXT': KEEP2}


def make_po(tmp, name, files):
    stage = tmp / ('stage_' + name)
    stage.mkdir()
    for rel, data in files.items():
        (stage / rel).write_bytes(data)
    po = tmp / (name + '.po')
    subprocess.run([sys.executable, str(ROOT / 'tools/mkvolume.py'), str(stage), str(po),
                    '--volume', name, '--blocks', str(BLOCKS)], check=True, capture_output=True)
    return po


def entries(img, key=2):
    return {e[1:1 + (e[0] & 15)].decode(): e for e in img.entries(key)}


def file_blocks(img, e):
    """Les blocs qu'occupe un fichier : le bloc index, puis ses blocs de
    donnees (seedling et sapling : ce banc n'a pas de plus gros fichier)."""
    storage = e[0] >> 4
    key = int.from_bytes(e[0x11:0x13], 'little')
    eof = int.from_bytes(e[0x15:0x18], 'little')
    if storage == 1:
        return [key]
    assert storage == 2, 'storage type %d hors du banc' % storage
    index = img.block(key)
    return [key] + [index[n] | (index[256 + n] << 8) for n in range((eof + 511) // 512)]


def volumes(s):
    return [r[:16].split(' ')[0].rstrip('/') for r in s.rows()[2:20] if r.startswith('/')]


def volume_list(s, p):
    s.key(b'/')
    s.wait(lambda: s.rows()[0].startswith('[Volumes]'), 'la liste des volumes')
    p.stable()


def ask_wipe(s, p, vol, key):
    """Selectionne `vol` dans la liste des volumes et lance WIPE, touche `key`."""
    volume_list(s, p)
    s.select(vol)
    menu_run(s, p, 'WIPE')
    s.wait(lambda: s.has('F) the free blocks'), 'la question de WIPE', 20)
    s.key(key)


def zeroed(s):
    """La ligne "N blocks zeroed on /VOL" et son compte."""
    line = [r.strip() for r in s.rows() if 'blocks zeroed' in r][0]
    return line, int(line.split()[0])


def main():
    with tempfile.TemporaryDirectory(prefix='a2fc-wipe-') as tmp:
        tmp = Path(tmp)
        po1 = make_po(tmp, 'WORKPO', FILES)
        po2 = make_po(tmp, 'WIPEPO', FILES)
        # un dossier par amorcage : stage_hd repart de BUILD/vol a chaque fois
        d1, d2 = tmp / 'boot1', tmp / 'boot2'
        d1.mkdir(); d2.mkdir()
        before = Image(po1.read_bytes())
        gone_blocks = file_blocks(before, entries(before)['GONE'])

        # ── 1. F : les blocs libres seulement ─────────────────────────────
        with boot_hd(d1, {}, port=PORT, plugins=['wipe'], floppy2=po1) as (p, s):
            volume_list(s, p)
            s.select('/WORKPO')
            s.key(RET)
            s.wait(lambda: s.rows()[0][:8] == '/WORKPO ', 'la racine de /WORKPO')
            p.stable()
            s.ok('la disquette du lecteur 2 porte KEEP1, GONE et KEEP2',
                 s.has('KEEP1 ') and s.has('GONE ') and s.has('KEEP2 '),
                 [r[:24] for r in s.rows()[2:8] if r.strip()])

            # GONE supprime : ses blocs passent libres dans le bitmap.
            s.select('GONE')
            s.key(b'D')
            s.wait(lambda: s.has('Delete GONE?'), 'la confirmation de la suppression', 20)
            s.key(b'Y')
            s.wait(lambda: s.has('deleted') or s.has('failed'), 'la suppression', 60)
            p.stable()
            s.ok('GONE supprime, KEEP1 et KEEP2 restent',
                 not s.has('GONE ') and s.has('KEEP1 ') and s.has('KEEP2 '), s.rows()[22].strip())

            # WIPE, F, sur /WORKPO depuis la liste des volumes.
            ask_wipe(s, p, '/WORKPO', b'F')
            s.wait(lambda: s.has('Zero every free block of /WORKPO?'), 'la confirmation de F', 20)
            s.key(b'Y')
            s.wait(lambda: s.has('blocks zeroed') or s.has('Nothing was written') or s.has('failed'),
                   'la fin du nettoyage des blocs libres', 300)
            p.stable()
            line, nfree = zeroed(s)
            s.ok('F annonce les blocs mis a zero et A2FC reprend la main',
                 'zeroed on /WORKPO' in line and s.rows()[0].startswith('[Volumes]'), line)

            # W sur le volume d'amorcage : refuse avant toute question.
            ask_wipe(s, p, '/WORKHD', b'W')
            s.wait(lambda: s.has('holds the running program'), 'le refus du volume d amorcage', 30)
            p.stable()
            s.ok('W sur le volume d amorcage est refuse',
                 s.has('holds the running program') and not s.has('Type ERASE'), s.rows()[22].strip())

        # La disquette, recopiee dans son .po a l'arret de POM2.
        after = Image(po1.read_bytes())
        head = after.header()
        left = entries(after)
        s.ok('les blocs du fichier supprime sont a zero sur la disquette',
             all(after.block(b) == bytes(512) for b in gone_blocks),
             [(b, after.block(b)[:8]) for b in gone_blocks if after.block(b) != bytes(512)][:3])
        s.ok('KEEP1 et KEEP2 sont intacts, GONE a disparu du repertoire',
             'GONE' not in left and after.read(left['KEEP1']) == KEEP1
             and after.read(left['KEEP2']) == KEEP2, sorted(left))
        s.ok('l en-tete du volume est intact : /WORKPO, 280 blocs',
             head['name'] == 'WORKPO' and head['blocks'] == BLOCKS, head)
        s.ok('le compte annonce est celui des bits libres du bitmap',
             nfree == after.free_blocks(), (nfree, after.free_blocks()))

        # ── 2. W : le volume entier ───────────────────────────────────────
        with boot_hd(d2, {}, port=PORT, plugins=['wipe'], floppy2=po2) as (p, s2):
            s2.checks = s.checks              # un seul verdict pour les deux amorcages

            # ESC a la question : rien n'est ecrit.
            ask_wipe(s2, p, '/WIPEPO', ESC)
            s2.wait(lambda: s2.has('Nothing was written'), "l'abandon a la question", 30)
            p.stable()
            s2.ok('ESC a la question n ecrit rien',
                  s2.has('Nothing was written') and '/WIPEPO' in volumes(s2), volumes(s2))

            # Un mot autre qu'ERASE : rien n'est ecrit.
            ask_wipe(s2, p, '/WIPEPO', b'W')
            s2.wait(lambda: s2.has('Type ERASE to confirm'), "l'invite ERASE", 20)
            s2.type('NOPE')
            s2.key(RET)
            s2.wait(lambda: s2.has('Nothing was written'), 'le refus', 30)
            p.stable()
            s2.ok('un autre mot qu ERASE n ecrit rien et le volume reste en ligne',
                  s2.has('Nothing was written') and '/WIPEPO' in volumes(s2), volumes(s2))

            # ERASE : les 280 blocs, en-tete comprise.
            ask_wipe(s2, p, '/WIPEPO', b'W')
            s2.wait(lambda: s2.has('Type ERASE to confirm'), "l'invite ERASE", 20)
            s2.type('ERASE')
            s2.key(RET)
            s2.wait(lambda: s2.has('blocks zeroed') or s2.has('Nothing was written') or s2.has('failed'),
                    'la fin du nettoyage du volume', 300)
            p.stable()
            line, nall = zeroed(s2)
            s2.ok('W efface les 280 blocs du volume et A2FC reprend la main',
                  nall == BLOCKS and s2.rows()[0].startswith('[Volumes]'), line)

        data = po2.read_bytes()
        s2.ok('sur l hote, le bloc 2 (en-tete du repertoire de volume) est a zero',
              data[2 * 512:3 * 512] == bytes(512), data[2 * 512:2 * 512 + 16])
        s2.ok('toute la disquette est a zero',
              data == bytes(BLOCKS * 512),
              [i for i, b in enumerate(data) if b][:4])
    return ok_all(s2, 'wipe')


if __name__ == '__main__':
    sys.exit(main())
