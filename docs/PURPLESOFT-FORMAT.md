# Purplesoft GRLOAD/GRSAVE pictures

This reader implements the original DOS 3.3 GRLOAD/GRSAVE pair, identified
from the programs on `purplesoft-juillet83-system.dsk` and
`purplesoft-s2-grload.dsk`, with original pictures IM1–IM4 and DDD.
The bank order and graphics modes are consistent with the
[Le Chat Mauve EVE manual](https://mirrors.apple2.org.za/ftp.apple.asimov.net/documentation/hardware/video/lechatmauve_eve_manuel_ocr.pdf).

| File / offset | Meaning |
| --- | --- |
| `name.FOTO1` | Exactly 8,192 bytes, auxiliary HGR plane |
| `FOTO1[$79]` | Saved `&GR` mode minus one, 0–9 |
| `FOTO1[$7A]` | Signature `S` ($53) |
| `name.FOTO2` | Exactly 8,192 bytes, main HGR plane |

The metadata occupies screen holes. The DOS binary load address/length
prefix is not picture data; strip that four-byte wrapper when extracting
files to ProDOS, as `bench/purple.py` does. Both files must share a basename
and directory. Either member opens the pair. A2FC does not depend on stale
panel sizes: both reads require exactly 8 KB and a clean EOF/close.

| Saved mode | Display | EVE HR1/HR2/HR3 bits |
| --- | --- | --- |
| 0 | HGR | 000 |
| 1 | HGR, HR1 | 001 |
| 2 | HGR, HR2 | 010 |
| 3 | HGR, HR3 | 100 |
| 4 | HGR, HR2 + HR3 | 110 |
| 5 | COL140 | 000 |
| 6 | COL280A | 001 |
| 7 | COL280B | 010 |
| 8 | CP280 | 111 |
| 9 | BW560 | 110 |

Bits are written as HR3:HR2:HR1. EVE's CPREG shadow writes are disabled
before loading MAIN, so reading the source cannot implicitly overwrite AUX.
The extended modes copy FOTO1 through ROM AUXMOVE, then load FOTO2 into MAIN.
Feline/Video-7's AN3 latch is also set for the ordinary COL140/BW560 cases;
the extra EVE modes require EVE hardware/emulation for faithful rendering.

The AUX-capable overlay receives consent before entry, shared only by its
current browsing session. Reopening asks again. Any exit after AUXMOVE,
including a failed second-plane read/close, rebuilds `/RAM`. Source files
are opened read-only and never rewritten. The consent destroys all `/RAM`
files; it does not make a picture stored on that same RAM volume safe to
continue reading after AUX has been overwritten.

Pascal GLOAD/GSAVE's single 16 KB file is a separate format and is not
accepted by this implementation. No signature or bank order is guessed for
that variant. The original DOS images are not distributed in this repository.
