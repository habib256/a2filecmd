#!/usr/bin/env python3
"""Ecrit et relit un document AppleWorks (traitement de texte, type $1A).

    mkawp.py SORTIE.awp < texte

Le format, tel que le lit la surcouche AWP d'A2 File Cmd : 300 octets
d'en-tete (octets 4-83 la regle de tabulation, +183 SFMinVers : 30 pour un
fichier 3.0, qui fait suivre l'en-tete d'un mot de deux octets a sauter),
puis des enregistrements de ligne a deux octets d'en-tete :

  n  $00   une ligne de texte de n octets : position du curseur (ou $FF,
           une regle), compte des caracteres avec le bit 7 pour "retour
           chariot en fin de ligne", puis le texte -- les codes sous $20
           sont des enrichissements ($01/$02 gras...) et $16 une tabulation
  p  $D0   un retour chariot seul (une ligne vide), p sa position
  x  $D1+  une commande de mise en page (centre, marges...), deux octets
  $FF $FF  la fin

Un paragraphe du texte source devient une suite de lignes de 78 colonnes,
la derniere seule portant le retour chariot, comme AppleWorks le range.
Un `*` bascule le gras, une tabulation devient le code $16 : de quoi
verifier que le lecteur saute les enrichissements et rend les tabulations.
"""
import sys
from pathlib import Path

HEADER = 300
WIDTH = 78


def write_awp(path, text, version=30):
    hdr = bytearray(HEADER)
    hdr[4:84] = b'=' * 80                     # la regle : pas de taquet
    hdr[183] = version
    body = bytearray()
    if version >= 30:
        body += b'\x00\x00'                   # le mot que les lecteurs sautent
    body += bytes([0, 0xD9])                  # une commande (centrage) a sauter
    for para in text.split('\n'):
        if not para:
            body += bytes([0, 0xD0])          # un retour chariot seul
            continue
        words, lines, cur = para.split(' '), [], ''
        for w in words:
            if cur and len(cur) + 1 + len(w) > WIDTH:
                lines.append(cur); cur = w
            else:
                cur = (cur + ' ' + w) if cur else w
        lines.append(cur)
        for i, line in enumerate(lines):
            data, bold = bytearray(), False
            for ch in line:
                if ch == '*':
                    data.append(0x02 if bold else 0x01); bold = not bold
                elif ch == '\t':
                    data.append(0x16)
                else:
                    data.append(ord(ch))
            cr = 0x80 if i == len(lines) - 1 else 0
            body += bytes([len(data) + 2, 0, min(len(data), 0x7F), (len(data) & 0x7F) | cr]) + data
    body += b'\xff\xff'
    Path(path).write_bytes(bytes(hdr) + bytes(body))


def read_awp(path):
    """Les lignes du document, telles que la surcouche AWP les affiche."""
    buf = Path(path).read_bytes()
    pos = HEADER + (2 if buf[183] >= 30 else 0)
    lines = []
    while pos + 1 < len(buf):
        n, kind = buf[pos], buf[pos + 1]
        pos += 2
        if kind == 0xFF:
            break
        if kind == 0xD0:
            lines.append(''); continue
        if kind > 0xD0:
            continue
        rec = buf[pos:pos + n]; pos += n
        if rec[0] == 0xFF:
            continue
        out = ''
        for c in rec[2:]:
            if 0x20 <= c < 0x7F:
                out += chr(c)
            elif c in (0x16, 0x17):
                out += ' ' * (8 - len(out) % 8)
            elif c == 0x0B:
                out += ' '
        lines.append(out)
    return lines


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        raise SystemExit(__doc__)
    write_awp(argv[0], sys.stdin.read())
    return 0


if __name__ == '__main__':
    sys.exit(main())
