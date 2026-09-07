#!/usr/bin/env python3
"""Construit une image de volume ProDOS 8 amorcable a partir d'un dossier.

    mkvolume.py STAGE SORTIE.po --volume A2FILECMD --boot data/prodos_boot.tmpl
                --blocks 280

Pourquoi en Python : A2 File Cmd doit se construire avec cc65 et rien
d'autre. Un outil C++ tiers pour ecrire les structures ProDOS obligerait
quiconque -- l'integration continue comprise -- a compiler un emulateur pour
obtenir une disquette. Trois cents lignes ici suffisent, et le format est
figé depuis 1983.

Ce que le dossier STAGE devient :

  bloc 0-1   l'amorce ProDOS, telle quelle depuis le gabarit
  bloc 2-5   le repertoire de volume, 4 blocs de 13 entrees de 39 octets
  bloc 6     la table d'allocation : un bit par bloc, 1 = libre
  bloc 7...  les fichiers et les sous-repertoires, dans l'ordre alphabetique

Le type ProDOS vient de l'extension de l'hote (.SYS .BIN .TXT .BAS .SYSTEM
retiree du nom), ou d'un suffixe explicite NOM#TTAAAA -- TT le type, AAAA
l'auxtype -- comme le veut la convention des outils Apple II. Les dates sont
fixes par defaut : deux constructions du meme contenu donnent le meme octet,
ce qui rend les SHA256 d'une publication verifiables.

Un fichier de plus de 512 octets devient "sapling" : un bloc d'index de 256
pointeurs (poids faibles en premiere moitie, poids forts en seconde) et ses
blocs de donnees. Au-dela de 128 Ko il faudrait un arbre a trois niveaux ;
aucun fichier d'A2 File Cmd n'en approche, et l'outil refuse plutot que de
mentir.
"""
import argparse
import re
import sys
from pathlib import Path

BLOCK = 512
ENTRY_LEN = 39
ENTRIES_PER_BLOCK = 13
DIR_START = 2            # le repertoire de volume commence au bloc 2
DIR_BLOCKS = 4           # ... et occupe quatre blocs, comme tout volume ProDOS
BITMAP = DIR_START + DIR_BLOCKS
ACCESS_FILE = 0xE3       # detruire, renommer, ecrire, lire
ACCESS_DIR = 0xC3
TYPE_DIR = 0x0F

EXT_TYPES = {'.bas': 0xFC, '.bin': 0x06, '.sys': 0xFF, '.txt': 0x04, '.int': 0xFA}


def prodos_date(text):
    """'2026-09-07T12:00' -> (mot date, mot heure) au format ProDOS."""
    m = re.fullmatch(r'(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?', text)
    if not m:
        raise argparse.ArgumentTypeError('date attendue : AAAA-MM-JJ[THH:MM]')
    y, mo, d = int(m[1]), int(m[2]), int(m[3])
    h, mi = int(m[4] or 0), int(m[5] or 0)
    return ((y % 100) << 9) | (mo << 5) | d, (h << 8) | mi


def prodos_name(host):
    """Nom ProDOS et type, d'apres le nom d'hote. Rend (nom, type, auxtype)."""
    name, ftype, aux = host, None, 0
    m = re.fullmatch(r'(.*)#([0-9A-Fa-f]{2})([0-9A-Fa-f]{4})', name)
    if m:
        name, ftype, aux = m[1], int(m[2], 16), int(m[3], 16)
    else:
        stem, dot, ext = name.rpartition('.')
        if dot and ('.' + ext.lower()) in EXT_TYPES:
            ftype = EXT_TYPES['.' + ext.lower()]
            name = stem
    if ftype is None:
        ftype = 0x06
    name = name.upper()
    if not re.fullmatch(r'[A-Z][A-Z0-9.]{0,14}', name):
        raise SystemExit(f'{host}: "{name}" n\'est pas un nom ProDOS (lettre, puis '
                         'lettres, chiffres ou points, 15 au plus)')
    return name, ftype, aux


class Volume:
    def __init__(self, name, blocks, boot, date):
        if not re.fullmatch(r'[A-Z][A-Z0-9.]{0,14}', name):
            raise SystemExit(f'/{name} : nom de volume ProDOS invalide')
        self.name, self.blocks, self.date = name, blocks, date
        self.image = bytearray(blocks * BLOCK)
        self.image[:len(boot)] = boot
        self.next_free = BITMAP + self.bitmap_blocks()

    def bitmap_blocks(self):
        return (self.blocks + 4095) // 4096

    def block(self, n):
        if n >= self.blocks:
            raise SystemExit(f'le contenu deborde le volume de {self.blocks} blocs')
        return memoryview(self.image)[n * BLOCK:(n + 1) * BLOCK]

    def alloc(self, n=1):
        first = self.next_free
        self.next_free += n
        if self.next_free > self.blocks:
            raise SystemExit(f'le contenu deborde le volume de {self.blocks} blocs')
        return first

    # ── les entrees ────────────────────────────────────────────────────────
    def entry(self, storage, name, ftype, key, used, eof, aux, header):
        e = bytearray(ENTRY_LEN)
        e[0] = (storage << 4) | len(name)
        e[1:1 + len(name)] = name.encode('ascii')
        e[0x10] = ftype
        e[0x11:0x13] = key.to_bytes(2, 'little')
        e[0x13:0x15] = used.to_bytes(2, 'little')
        e[0x15:0x18] = eof.to_bytes(3, 'little')
        e[0x18:0x1A] = self.date[0].to_bytes(2, 'little')
        e[0x1A:0x1C] = self.date[1].to_bytes(2, 'little')
        e[0x1E] = ACCESS_DIR if storage == 0xD else ACCESS_FILE
        e[0x1F:0x21] = aux.to_bytes(2, 'little')
        e[0x21:0x23] = self.date[0].to_bytes(2, 'little')
        e[0x23:0x25] = self.date[1].to_bytes(2, 'little')
        e[0x25:0x27] = header.to_bytes(2, 'little')
        return e

    def write_file(self, data):
        """Rend (storage_type, bloc cle, blocs occupes)."""
        if len(data) <= BLOCK:
            key = self.alloc()
            self.block(key)[:len(data)] = data
            return 1, key, 1
        chunks = [data[i:i + BLOCK] for i in range(0, len(data), BLOCK)]
        if len(chunks) > 256:
            raise SystemExit('fichier de plus de 128 Ko : il faudrait un arbre')
        index = self.alloc()
        blocks = [self.alloc() for _ in chunks]
        for i, (b, chunk) in enumerate(zip(blocks, chunks)):
            self.block(b)[:len(chunk)] = chunk
            self.block(index)[i] = b & 0xFF
            self.block(index)[256 + i] = b >> 8
        return 2, index, 1 + len(chunks)

    # ── les repertoires ────────────────────────────────────────────────────
    def dir_blocks_needed(self, count):
        """Blocs pour `count` entrees, l'en-tete du repertoire comprise."""
        return max(1, (count + 1 + ENTRIES_PER_BLOCK - 1) // ENTRIES_PER_BLOCK)

    def write_dir(self, path, blocks, header_entry):
        """Ecrit un repertoire dans `blocks` (deja alloues, chaines ici).

        `header_entry` est son en-tete, deja formee. Rend le nombre d'entrees.
        """
        for i, b in enumerate(blocks):
            blk = self.block(b)
            blk[0:2] = (blocks[i - 1] if i else 0).to_bytes(2, 'little')
            blk[2:4] = (blocks[i + 1] if i + 1 < len(blocks) else 0).to_bytes(2, 'little')
        self.block(blocks[0])[4:4 + ENTRY_LEN] = header_entry

        slots = []                       # (bloc, index de l'entree dans le bloc)
        for i, b in enumerate(blocks):
            for k in range(ENTRIES_PER_BLOCK):
                if i == 0 and k == 0:
                    continue             # l'en-tete
                slots.append((b, k))

        items = sorted(path.iterdir(), key=lambda p: p.name.upper())
        if len(items) > len(slots):
            raise SystemExit(f'{path} : {len(items)} entrees pour {len(slots)} places')
        for (blk_no, k), item in zip(slots, items):
            name, ftype, aux = prodos_name(item.name)
            if item.is_dir():
                sub_count = len(list(item.iterdir()))
                sub_blocks = [self.alloc() for _ in range(self.dir_blocks_needed(sub_count))]
                head = self.entry(0xE, name, 0, 0, 0, 0, 0, 0)
                head[0x10] = 0x75        # le marqueur d'en-tete de sous-repertoire
                head[0x11:0x18] = bytes((0x24, 0x00, 0xC3, 0x27, 0x0D, 0x00, 0x00))
                head[0x1E] = ACCESS_DIR
                head[0x1F] = ENTRY_LEN
                head[0x20] = ENTRIES_PER_BLOCK
                head[0x21:0x23] = sub_count.to_bytes(2, 'little')
                head[0x23:0x25] = blk_no.to_bytes(2, 'little')
                head[0x25] = k + 1       # le rang de l'entree dans le bloc, a partir de 1
                head[0x26] = ENTRY_LEN
                self.write_dir(item, sub_blocks, head)
                e = self.entry(0xD, name, TYPE_DIR, sub_blocks[0], len(sub_blocks),
                               len(sub_blocks) * BLOCK, 0, blocks[0])
            else:
                data = item.read_bytes()
                storage, key, used = self.write_file(data)
                e = self.entry(storage, name, ftype, key, used, len(data), aux, blocks[0])
            self.block(blk_no)[4 + k * ENTRY_LEN:4 + (k + 1) * ENTRY_LEN] = e
        return len(items)

    def build(self, stage):
        head = self.entry(0xF, self.name, 0, 0, 0, 0, 0, 0)
        head[0x10:0x1E] = bytes(14)      # reserve, jusqu'a l'octet d'acces
        head[0x1E] = ACCESS_DIR
        head[0x1F] = ENTRY_LEN
        head[0x20] = ENTRIES_PER_BLOCK
        head[0x23:0x25] = BITMAP.to_bytes(2, 'little')
        head[0x25:0x27] = self.blocks.to_bytes(2, 'little')
        # Le repertoire de volume porte sa date de creation, pas celle d'un
        # fichier : les octets 0x10-0x1D sont reserves et doivent rester nuls.
        count = self.write_dir(stage, list(range(DIR_START, DIR_START + DIR_BLOCKS)), head)
        self.block(DIR_START)[4 + 0x21:4 + 0x23] = count.to_bytes(2, 'little')
        self.write_bitmap()
        return count

    def write_bitmap(self):
        used = self.next_free
        for i in range(self.bitmap_blocks()):
            blk = self.block(BITMAP + i)
            for b in range(4096):
                n = (i << 12) + b
                if used <= n < self.blocks:
                    blk[b >> 3] |= 0x80 >> (b & 7)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('stage', type=Path, help='le dossier a mettre sur le volume')
    ap.add_argument('out', type=Path, help="l'image .po a ecrire")
    ap.add_argument('--volume', required=True, help='nom du volume, sans la barre')
    ap.add_argument('--boot', type=Path, help="l'amorce ProDOS (2 blocs)")
    ap.add_argument('--blocks', type=int, default=280, help='taille du volume (280 = 5,25 pouces)')
    ap.add_argument('--date', type=prodos_date, default=prodos_date('2026-09-07T12:00'),
                    help='date portee par les entrees (fixe : construction reproductible)')
    args = ap.parse_args()

    boot = args.boot.read_bytes() if args.boot else b''
    if args.boot and len(boot) < 2 * BLOCK:
        boot = boot + bytes(2 * BLOCK - len(boot))
    vol = Volume(args.volume, args.blocks, boot[:2 * BLOCK], args.date)
    count = vol.build(args.stage)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(bytes(vol.image))
    free = args.blocks - vol.next_free
    print(f'/{args.volume} : {count} entrees a la racine, {vol.next_free} blocs occupes, '
          f'{free} libres sur {args.blocks} -> {args.out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
