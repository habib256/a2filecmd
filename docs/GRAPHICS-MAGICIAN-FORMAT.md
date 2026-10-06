# The Graphics Magician picture format (Apple II hi-res)

Status: phase 1 of the A2FC viewer work (study and specification),
2026-10-04. This document is written for a **clean-room implementer**: it
describes the data and the observable behaviour of the original drawing
routines precisely enough to reproduce their hi-res page byte for byte,
without reading or copying Penguin Software's code. It contains no code or
code taken from the original programs. By decision of the maintainer
(2026-10-04), the pattern palette and the eight brushes are given in
Appendix A as interoperability data, observed on the screen; Penguin's
font is **not** reproduced: text is drawn with an A2FC substitute font
(section 12). Section 17 sums up what a viewer must do; Appendix B lists
synthetic test pictures with the SHA-256 of their expected page, so that an
implementation can check itself without the original programs.

The Graphics Magician (Penguin Software, 1982; revised 1983 and 1984;
Penguin became Polarware) stores a picture as the list of drawing commands
the artist used in its Picture Painter (PICEDIT): lines, flood fills with
108 dithered colour patterns, brush stamps, and (1984 only) text. A small
machine-language routine shipped with the package (PICDRAW, PICDRAWF,
PICDRAWH, PICDRAWL) replays the list on the hi-res screen. Adventure games
by Penguin and others embedded that routine and their pictures.

## 1. How this was established

- Sources: Andy McFadden's commented disassembly of the 1984 PICDRAWH
  (6502disassembly.com, 2025) and his format summary; the 1982 manual
  (scanned, asimov and graphicsmagician.com); the disks of the
  1982, 1983 and 1984 releases; games: Transylvania (1982), The Quest
  (1983), Ring Quest (1984), The Quest double-res re-release, all
  published by the former Polarware staff on graphicsmagician.com or
  archived on archive.org.
- Oracle: the original routines (six builds, section 2) run unmodified in
  the POM2 emulator (Apple IIe ROM, so the Applesoft line routines are the
  real ones); the hi-res page is captured after each call.
- A private reference renderer (Python, kept outside the repository) was
  made byte-identical to the oracle, over the whole 8,192-byte page
  including the screen holes:
  - **398 distinct real pictures** (352 files: The Quest 110, its
    re-release 102, Ring Quest 94, Transylvania 72, Graphics Magician
    sample groups 20), each drawn by the routine its own disk ships:
    **398/398 identical**; plus 84 multi-part overlays drawn on top of
    their base picture: 84/84;
  - every real picture also drawn by the "other" dialect's routine: the
    1984 model matches 392/393 (the one difference reads memory outside
    the screen, section 11), the 1982 models 512/512;
  - 2,800 random synthetic pictures (lines, fills on random shapes and on
    patterned areas, brushes and text at the screen edges, all 108
    patterns, every colour) through six routine builds, drawn by models
    written from sections 6-11 of this document: 6,799 of 6,800 runs
    identical; the one difference is again a read outside the screen
    (section 11).

## 2. Versions (dialects)

The command set is almost the same everywhere, but the flood fill was
rewritten in 1984 and the two fills do not give the same pixels: on the
398 real pictures, the two dialects produce identical pages for only 93;
the median difference is 84 bytes, the 90th percentile 2,484 bytes. A
renderer must therefore know which dialect a picture was made for.

| Dialect | Builds seen | Where |
|---|---|---|
| **V82** | PICDRAW (load $8E00, 2,048 bytes) and PICDRAWF ("fast", $8C00, 2,560 bytes, adds row tables in front); the same PICDRAWF relocated to $0800 in games (Transylvania `PICDRAW2`, The Quest `PICDRAWF`, Ring Quest `PICDRAWR`) | 1982 and 1983 Graphics Magician disks, games 1982-1984 |
| **V82E** | an earlier PICDRAW (one disk image, `d144s1`) | identical to V82 except the initial pen position (section 5) |
| **V84** | PICDRAWH ($8D00, 3,072 bytes), PICDRAWL (the same at $0800), an earlier 1983 build of PICDRAWH, and a PICDRAWL without font on The Quest re-release | 1983/84 "revised" Graphics Magician, later games |

PICDRAW and PICDRAWF draw identically on every real picture; they differ
only for brush or glyph rows below the screen (section 11).

The double hi-res routines of 1984 (DPICDRAW*, `.DPC` pictures), the
Comprehend games' extended dialect (section 14) and Penguin's other
graphics formats are not covered.

## 3. Files and identification

There is **no header, no magic number and no file-type convention**.
Pictures are DOS 3.3 `B` files (ProDOS BIN, type $06, aux = load address
after conversion) whose load address is whatever the program used: $4000
for picture groups, $6800 for the rooms of Transylvania, The Quest and Ring
Quest, $6000, $6300, $1100 or $1201 for others. Names follow each game
(`R12`, `O5`, `P103`, `T5`, `P90.SPC`, `PICTURE GROUP`...). A picture
measured 6 to 3,574 bytes (median 753).

A file holds one or more pictures back to back, each ended by its own end
command, optionally followed by slack (35 of 378 files carry leftover bytes
after their last picture). Two layouts exist:

- **Picture groups** (PICEDIT "save group", e.g. `DEMO PICTURE GROUP`,
  `PICSAMPLES`): independent full pictures. The caller draws picture *n*
  by drawing pictures 0 to *n*-1 first or, as the routines leave their data
  pointer just after the end byte, by chaining calls.
- **Picture plus overlays** (multi-part room files of The Quest and Ring
  Quest): part 0 is the room; the following parts are small additions
  (an open door, an object) that the game draws over it without clearing.

Recommended recognition (measured on 1,607 unrelated binary files from
A2FC's other format studies: 0 false positives; on the 378 picture files:
0 misses):

1. BIN file, at least 2 bytes.
2. The first command's high nibble is $2, $4, $6, $8 or $A.
3. The first picture parses **strictly** to its end byte within the file:
   only the commands of section 4, with: line colour 0-7, brush 0-7,
   pattern 0-107 with a zero low nibble, X high part 0 or 1, X ≤ 279,
   Y ≤ 191, text characters $20-$7F with a zero low nibble, end byte
   exactly $00.
4. If the picture contains line commands it must contain at least one
   line start ($8x) (this rejects a text-like program file that otherwise
   parses).
5. The picture must draw something: at least one line ($Ax), brush ($Cx)
   or fill ($Ex) command. (Without this rule, 2-byte "pictures" such as
   `26 00` match the first bytes of many unrelated files: Take 1 scenes,
   Movie Maker animations, Map Pack files, Applesoft programs.)
6. Whatever follows the first picture is either more pictures or ignored.

Dialect: a picture using $1x, $3x or $5x is V84. Otherwise the data does
not say; the routine file on the same disk does (PICDRAW, PICDRAWF,
PICDRAW2, PICDRAWR: V82; PICDRAWH, PICDRAWL: V84). Most pictures in
circulation come from 1982-1984 games, so V82 is the sensible default,
with a key to redraw in the other dialect.

## 4. Command stream

Each command is 1 to 3 bytes. The high nibble selects the command, the low
nibble is an argument. Coordinates are absolute screen positions: X 0-279,
Y 0-191; the X high part (0 or 1) is the low nibble of the command byte,
followed by the X low byte, then Y.

| Byte | Bytes | V84 | V82 |
|---|---|---|---|
| $00 | 1 | end of picture | end |
| $1x | 3 | set text cursor X,Y | (end: see below) |
| $2c | 1 | line colour c (0-7) | same |
| $30 | 2 | XOR text: next byte = character | — |
| $4b | 1 | select brush b (0-7) | same |
| $50 | 2 | text: next byte = character | — |
| $60 | 2 | fill/brush/text pattern: next byte = pattern 0-107 | same |
| $8x | 3 | line start (move the pen) | same |
| $Ax | 3 | line from the pen to X,Y | same |
| $Cx | 3 | stamp the brush with its top-left corner at X,Y | same |
| $Ex | 3 | flood fill from X,Y | same |

Decoding rules of the originals (needed only to explain malformed data,
section 11):

- V84 dispatches on the full high nibble. Any byte $00-$0F ends the
  picture. The unused nibbles $7, $9, $B, $D, $F fall through to "set text
  cursor" and consume 3 bytes.
- V82 dispatches on the top three bits (byte AND $E0): $00-$1F end the
  picture, $3x acts as $2x, $5x as $4x, $7x as $6x, $9x as $8x, $Bx as $Ax,
  $Dx as $Cx, $Fx as $Ex. The argument is still the low nibble.
- The argument of $6x, $3x, $5x is ignored by both.

## 5. Drawing model

The routines draw on hi-res page 1 ($2000-$3FFF) in the usual layout: row
y starts at offset 1024·(y mod 8) + 128·((y div 8) mod 8) + 40·(y div 64);
byte column c (0-39) holds pixels 7c to 7c+6, pixel 7c+i in bit i; bit 7
selects the colour group of the byte. A "white" picture is drawn on a page
first filled with $FF (all 8,192 bytes, screen holes included) by the
"clear and draw" entry point; the "draw only" entry point draws over
whatever is there (overlays, chained pictures).

State at the start of **every** picture (both entry points):

- line colour 4 (black, $80), and the pen moved to (140, 6) as by a line
  start command (V82E: (140, 96));
- pattern 0, brush 5, text cursor (0, 0) (V84), XOR text off.

The state is not reset between commands. Brush, fill and text never move
the pen.

### Colours

Line colour c selects the Applesoft colour byte: 0 → $00, 1 → $2A,
2 → $55, 3 → $7F, 4 → $80, 5 → $AA, 6 → $D5, 7 → $FF (black, green,
violet, white, black, orange, blue, white). These are the values the
Applesoft `HCOLOR=` table holds; they are public documentation.

## 6. Lines

Lines are drawn by the Applesoft ROM routines (HCOLOR, HPOSN, HGLIN: the
routine calls them at their fixed ROM entry points). An implementation may
call the ROM itself (every IIe, IIc and IIgs has it) or reproduce the
following model exactly.

Line state: the pen (X, Y), the current byte column `col`, a one-bit
pixel mask `m` (bit 7 always set, plus bit `X mod 7`), and the **colour
bits** `cb`.

- **Colour shift.** For the colour bytes whose bits 0-6 alternate ($2A,
  $55, $AA, $D5), the byte used in an odd byte column is the colour byte
  XOR $7F (green and violet swap, orange and blue swap). $00, $7F, $80 and
  $FF never change.
- **Line start (X, Y)**: pen = (X, Y); col = X div 7; m = $80 + 2^(X mod 7);
  cb = current colour byte, shifted if col is odd.
- **Set colour** only records the colour byte. The colour bits used by a
  line are those loaded by the last line start: **a colour change takes
  effect at the next line start, not at the next line** (the well-known
  `HPLOT TO` behaviour). Real pictures rely on this.
- **Plot** writes the current byte as `(old AND NOT m) OR (cb AND m)`.
  Because `m` contains bit 7, every plotted pixel also sets bit 7 of its
  byte from the colour, which changes the colour of the other pixels of
  that byte. This is part of the expected output.
- **Line to (X1, Y1)** from the pen (X0, Y0): dx = X1 - X0, dy = Y1 - Y0,
  A = |dx|, B = |dy|, error e = A - B. Plot the current position (the
  start point is plotted again). Then repeat A + B times: if e ≥ 0, step
  one pixel horizontally (towards X1) and e = e - B; otherwise step one row
  (towards Y1) and e = e + A; then plot. The line is 4-connected and has
  exactly A + B + 1 plots. The pen becomes (X1, Y1).
  - A horizontal step changes `m` to the neighbouring pixel. When it leaves
    the byte, col changes by one and `cb` is shifted (rule above), so the
    colour stays consistent with the column parity.
  - A vertical step keeps col, m and cb.

## 7. Patterns

Fills, brushes and text are drawn with the current **pattern** (0-107). A
pattern is a pair of **row patterns**, one for even screen rows and one
for odd rows. A row pattern is four bytes, used according to the absolute
byte column: byte column c uses byte (c mod 4). So a pattern tiles the
screen with a period of 28 pixels by 2 rows, and areas filled separately
with the same pattern join without seams. The pattern bytes include bit
7: drawing with a pattern also sets each touched byte's bit 7 from the
pattern.

The 108 patterns use 27 different row patterns out of 30 that the routine
holds. The 30 decompose into simple, rule-generated dithers of the six
Applesoft colours: the 8 solid colour rows (as in section 5, with the
violet/green and blue/orange swap between even and odd byte columns);
two-pixels-on/two-off stripes (period 4, two phases, each with bit 7 clear
or set); one pixel in four (four phases × two colour groups); three in four
(four phases × two); one pixel in three (one phase × two, its 28-pixel
repetition leaving a seam because 28 is not a multiple of 3). The
assignment of row-pattern pairs to the indices 0-107 (the order of
PICEDIT's palette: 11 columns of 10, the last two slots unused) is
arbitrary data, needed for compatibility: Appendix A gives it.

## 8. Brushes, glyphs and text

**Bitmaps.** Brush stamps and text characters are drawn from 8-row
bitmaps, one byte per row, of which only bits 0-6 count (bit 7 of the
stored bytes is discarded by the drawing code). Drawing a bitmap at byte
column c, pixel offset p (0-6), top row y:

for each row r = 0..7, with v = (row bits) shifted left by p (a 13-bit
value), the low part v AND $7F goes to byte column c and v shifted right
by 7 to byte column c+1, both on row y + r. For each of these two bytes,
if its part `k` is not zero:
`new = (old AND NOT k AND $7F) OR ((k OR $80) AND P)`, where P is the row
pattern byte for that row's parity and that byte's column (c or c+1)
mod 4. So the bitmap's pixels take the pattern's bits, the byte's bit 7
takes the pattern's bit 7, and a byte whose part is zero is left
untouched.

In **XOR text** mode the two parts are XORed into the screen instead
(`new = old XOR k`), bit 7 unchanged, pattern ignored.

**Brushes.** A brush is 16 rows × 14 pixels made of four bitmaps:
top-left at (c, p, Y), top-right at (c+1, p, Y), bottom-left at
(c, p, Y+8), bottom-right at (c+1, p, Y+8), where c = X div 7, p = X mod 7.
It therefore touches byte columns c to c+2 and rows Y to Y+15, drawn in
that order (top-left, top-right, bottom-left, bottom-right). Nothing is
clipped: the cell of a brush stamped at X ≥ 266 covers byte columns
40-41, which are the first bytes of the row 64 lines below (or of the next
row group), and that of one at Y ≥ 177 rows 192-206 (section 11). Since a
byte whose part is zero is untouched, the brushes of Appendix A actually
write there from X ≥ 267 (pixel X+13 of brush 5) and Y ≥ 178 (row 14 of
brushes 5 and 7), down to row 205 at most. The real pictures do
both (725 edge stamps in the corpus), and the expected output contains
those wrapped pixels.

Brushes 0 to 5 are solid round dots of increasing size (1, 4, 12, 32, 80
and 156 pixels: from a single pixel to a 14 × 14 disc on rows 1-14 of the
cell), all centred on pixel (7, 7) of the cell, so the visual centre of a
stamp is (X+7, Y+7) although X, Y name its top-left corner; brushes 6 and
7 are scattered "spray" dots (12 and 50 pixels).
Brush 7 is by far the most used command operand in the corpus (12,387
stamps out of 27,498).

**Text (V84).** A character code k is drawn as an 8-row bitmap (glyph k)
at the text cursor (c = X div 7, p = X mod 7, top row Y), with exactly the
bitmap rule above, then the cursor X advances by 8 pixels (no wrap, no
line feed). The original font has 96 glyphs ($20-$7F), 7 × 8 pixels with
two-pixel-wide strokes. **A2FC does not use it** (section 12): an A2FC
viewer draws the glyphs of its own 7 × 8 font, with the same placement,
pattern and XOR rules and the same 8-pixel advance; pictures with text are
then not byte-identical to the original, and the tests of Appendix B
contain no text. Codes $00-$1F address the brush bitmaps in the original
(code 4b + q = quarter q of brush b, quarters in the order above) and
codes $80-$FF read undefined memory: a viewer refuses both (section 11).
No real picture of the corpus uses text (0 text commands in 398
pictures): text was a 1984 addition.

## 9. Flood fill, V84

A pixel is **white** when, in its own byte, its bit and the bit of the
pixel to its left are both set; for the leftmost pixel of a byte (offset
0) the test uses bits 0 and 1 instead. Bit 7 and the neighbouring bytes are
ignored.

Fill at (X, Y), with c = X div 7, p = X mod 7:

1. **Find the top.** If (c, p) on row Y is white: if Y = 0 the top is 0,
   else move up one row and test again. If it is not white, the top is the
   row **below** the current one, and that row is filled without being
   tested. (Consequence: a fill started on a non-white pixel still fills
   the span of the row under it.)
2. **Fill one row** (row y, start byte c, start offset p). Let s be the
   byte.
   - Left border in the start byte: L = the highest clear bit among bits 0
     to p (offset p included), if any. Right border: R = the lowest clear
     bit among bits p to 6, if any.
   - The start byte's mask is: the bits strictly between L and R (all of
     bits 0-6 on a side without a border), plus bit 7.
   - Write `new = (s AND NOT mask) OR (P AND mask)` (P = pattern byte for
     this row and column). Bit 7 always becomes the pattern's.
   - If there was no left border, walk left, byte by byte: a byte whose
     bits 0-6 are all set gets mask $FF and the walk continues; otherwise
     L = its highest clear bit, mask = bits above L plus bit 7, written,
     and the walk stops there (lc = that column). Walking past column 0
     stops with lc = 0 and L = 0. If the border was in the start byte,
     lc = c.
   - The same to the right: a full byte gets $FF; otherwise R = its
     lowest clear bit, mask = bits below R plus bit 7, written, stop
     (rc = that column). Walking past column 39 stops with rc = 39 and
     R = 6. If the border was in the start byte, rc = c.
   - Next position: X' = floor((7·(lc + rc) + L + R) / 2), the middle of
     the two border pixels; c = X' div 7, p = X' mod 7.
3. Move down one row. Stop if the row is 192, or if (c, p) on the new row
   is not white. Otherwise go to 2.

The fill only ever turns white pixels into the pattern: it is intended for
"fill a white area". On already patterned areas it stops at the first
non-white pixel; on the first row (case of step 1) it may paint nothing.

## 10. Flood fill, V82

Same notion of white pixel. Fill at (X, Y), c = X div 7, p = X mod 7:

1. **Find the top.** If Y = 0, the top is row **p** (an oddity of the
   original: a fill on row 0 starts on row X mod 7; 106 fills of the corpus
   are on row 0). Otherwise move up while the pixel above is white and
   the row is above 0.
2. Stop if the current row is 192 or more, or if (c, p) on it is not
   white. (So, unlike V84, a fill started on a non-white pixel draws
   nothing.)
3. **Fill one row.** s = the start byte.
   - lb = the highest clear bit **below** p, rb = the lowest clear bit
     **above** p (bit p itself is known set). The run is bits lo..hi, with
     lo = lb + 1 (0 if no lb) and hi = rb - 1 (6 if no rb). mask = the run.
   - Write `new = (s AND NOT mask AND $7F) OR (P AND (mask OR $80))`: same
     effect as V84 (run gets the pattern, bit 7 gets the pattern's).
   - Two counters: Rc = 7 - rb (0 if no rb), Ls = lo.
   - If there was no rb, walk right from c+1 to 39: a byte whose bits 0-6
     are all set gets mask $7F and the walk continues; otherwise i = its
     lowest clear bit, mask = bits below i, written, Rc = 7 - i, stop.
     rc = the last column visited (39 at the edge, Rc then still 0).
   - If there was no lb, walk left from c-1 to 0: full bytes get $7F;
     otherwise i = its highest clear bit, mask = bits above i, written,
     **Ls = i** (the border pixel itself, not i + 1 as in the start byte),
     stop. lc = the last column visited (0 at the edge, Ls then 0).
   - With a border in the start byte, lc (or rc) = c.
   - **Next position**, in 8-bit arithmetic as the original does it:
     w = rc - lc - 1; A = 7 if w < 0, else (7·w + 14) mod 256;
     b = 1 if A < Rc else 0; half = ((A - Rc - Ls - b) mod 256) div 2;
     X' = 7·lc + Ls + half; c = X' div 7, p = X' mod 7.
     (For spans narrower than 37 bytes this is simply the middle of the
     white run; the wrap-around changes the result for nearly full-width
     rows, and X' still always lands on the screen.)
4. Move down one row and go to 2.

## 11. Rows below the screen and other edge cases

Rows 192 and beyond are reached only by brush stamps at Y ≥ 177, text
there, and the V84 fill of section 9 step 1 on row 191.

- V82 PICDRAW (and V82E) compute a row address with the formula of
  section 5 for any row number 0-255: rows 192-255 fall inside the page
  (40·3 = 120: the screen holes and the end of other rows).
- V82 PICDRAWF and V84 read their row tables past the end. For row
  192 + k (k = 0-63) the address becomes:
  low byte = $20 + 4·(k mod 8) + ((k div 16) mod 4),
  high byte = $20 for k with bit 3 clear, $A0 with bit 3 set.
  So k = 0-7 lands inside page 1 (offsets $0020-$003F, plus the column),
  k = 8-15 lands at $A0xx, **outside the screen** (in DOS 3.3 itself on
  the original machine). A renderer reproduces the in-page writes and
  must drop the others. The V84 fill continuing on such rows reads that
  memory too: its result there depends on what the original machine had
  in memory, which is the one real-picture difference of section 1. A
  renderer should treat any read outside the page as a non-white pixel.

Malformed data (the originals do not check anything):

| Data | Original behaviour | Viewer |
|---|---|---|
| no end byte | runs on through memory | refuse |
| line colour 8-15 | Applesoft error `?ILLEGAL QUANTITY` (BASIC error handler) | refuse |
| brush 8-15 | V84: glyph bitmaps used as brush quarters; V82: bytes after the routine | refuse |
| pattern 108-255 | reads past the palette (version-dependent garbage) | refuse |
| X ≥ 280, Y ≥ 192 | lines wrap inside the page; fills, brushes, text write anywhere in memory | refuse |
| X high nibble 2-15 | line start treats any non-zero high part as 256; the others use the whole nibble | refuse |
| character outside $20-$7F | brush quarters or undefined memory | refuse |
| unknown opcode | see section 4 | refuse |

Never write outside the page, whatever the input.

## 12. Patterns, brushes and font as data

These three blocks are the only content of the original routines that a
byte-identical renderer needs besides the algorithms above. All three are
**fully observable on the screen**: drawing each pattern into a white
area, and each brush and each character in a black pattern, under the
emulator, gives back exactly the bits that matter (verified: 108/108
patterns, 8/8 brushes, 96/96 glyphs equal to the functional bits of the
original tables; the stored bytes whose bit 7 is set are never used for
that bit).

| Block | Content | Observable size |
|---|---|---|
| Patterns | 108 pairs (even row, odd row) of 27 distinct 4-byte row patterns, simple periodic dithers (section 7) | 27 × 4 bytes + 108 × 2 indices |
| Brushes | 8 bitmaps of 16 rows × 14 pixels: six filled dots, two sprays | 8 × 16 × 14 bits = 224 bytes |
| Font | 96 glyphs of 7 × 8 pixels, bold two-pixel strokes | 672 bytes |

**Decision (maintainer, 2026-10-04): option 2.** The patterns and the
brushes are integrated as interoperability data: they are given in
**Appendix A**, in a form of my own (the row patterns are numbered in
order of first use by the palette, not as the original stores them; the
brushes are drawn as pictures), checked by rebuilding the tables from the
text of this document and rendering the 398 real pictures and the 152
expected pages of Appendix B: all identical. **The font is not
integrated**: a viewer draws text with an A2FC 7 × 8 font (section 8).
Since no real picture uses text, every known picture stays byte-identical.

Facts that led to the decision, for the record: the patterns are
functional dithers whose numbering is dictated by compatibility (99 of the
108 occur in real pictures); brushes 0-5 are minimal discs and brushes
6-7 small dot scatters, brush 7 being the most used brush of the corpus;
the font is a typeface design, unused by real pictures; the rights holder
(Penguin, then Polarware, which stopped trading) is unclear, and former
employees distribute the software freely on graphicsmagician.com.

## 13. Timing

The originals draw progressively on the visible page; games show the
drawing as it happens. Measured on the oracle at 1.02 MHz: 0.3 to 8.9
million cycles per real picture, median 2.4 million (about 2.4 s). Fills
dominate. A viewer need not reproduce the speed.

## 14. Related formats not covered

- **Comprehend games** (The Crimson Crown, Transylvania (1985),
  Oo-Topos, The Coveted Mirror (Comprehend), Talisman, the Spy series):
  their engine has its own Graphics Magician-derived dialect (the same
  sixteen-way dispatch, with a rectangle command at $9x, a delay at $Dx,
  further commands at $Bx and $Fx, $7x as a 1-byte no-op) and stores
  pictures inside its own disk format, not as files. A separate study.
- The Coveted Mirror (1985, non-Comprehend) and Penguin's Map Pack
  `.PAC` files use other formats.
- Double hi-res pictures (`.DPC`, DPICDRAW*, 1984).

## 15. Synthetic test corpus

Appendix B defines 60 random and 12 hand-made test pictures, a picture
group and a picture with an overlay, with the SHA-256 of their expected
page in both dialects. They exercise every rule of sections 5-11: colour
change at the next line start, colours across byte columns, the whole
palette, every brush at the right and bottom edges (column wrap, rows
below the screen), V82 fills on row 0 at every X mod 7, the V84
row-below rule, the V82 8-bit middle on 36-38-byte spans, and a V84 fill
continuing below row 191. A test script must also check that each
malformed picture of section 11 is refused before anything is drawn and
that no write ever leaves the page.

## 16. Notes for the implementation

- Everything is page arithmetic on 8 KB; a 6502 renderer needs the
  tables of Appendix A (27 × 4 + 216 + 8 × 32 bytes once packed as four
  8-row quarters per brush), a substitute font, the two fills, the bitmap
  stamp, and either the ROM line routines or the model of section 6.
- Calling the Applesoft ROM for lines (HCOLOR with the colour in X at
  $F6EC, HPOSN at $F411 with A = Y, X = X low, Y = X high, HGLIN at $F53A
  with A = X low, X = X high, Y = Y; page $20 in $E6) needs the
  motherboard ROM selected at $D000-$FFFF and uses the zero page at
  $1A-$1D, $26-$27, $30, $D0-$D5 and $E0-$E6. HCOLOR raises a BASIC error
  for a colour above 7, which the refusal rules exclude beforehand.
  The model of section 6 gives the same pixels and avoids the ROM.
- A brush or glyph quarter is easier to store as four 8-byte quarters
  (top-left, top-right, bottom-left, bottom-right), each byte holding
  7 pixels in bits 0-6, pixel j of a row in bit j.

## 17. Viewer requirements (summary)

1. **Recognise** with the rule of section 3 (measured: 0 false positive in
   1,607 unrelated binary files, 0 miss in 378 picture files).
2. **Refuse** before drawing anything when the first picture does not
   parse strictly (section 3, rule 3) or contains any case of the
   section 11 table. Never write outside page 1.
3. **Dialect**: V84 if a picture of the file uses $1x, $3x or $5x (the
   key then does nothing); otherwise **V82 by default**, and a key (D in
   A2FC) redraws the picture in the other dialect (the
   original routines give different pixels for most pictures, section 2).
   V82 means the PICDRAWF behaviour shipped with the games, including
   rows 192 and beyond addressed as in section 11 (PICDRAW gives the same
   pages on every real picture).
4. **Drawing**: clear page 1 to $FF (all 8,192 bytes), reset the state
   (section 5), run the commands; lines as in section 6 (or the ROM);
   patterns from Appendix A by byte column mod 4 and row parity; brushes
   and glyphs with the bitmap rule; the fill of the dialect; reads
   outside the page count as non-white pixels, writes outside it are
   dropped.
5. **Several pictures per file**: a file may hold several pictures back
   to back, each ended by $00, then possibly leftover bytes. Show the
   first; browse the next ones (each on a cleared page for picture groups;
   for room files with overlays, the overlays drawn over part 0, without
   clearing). Every part is held to rules 2-5 of section 3, not only the
   first; stop at the first part that fails them (A2FC also stops after
   255 parts); ignore the rest of the file.
6. **Text** (V84 only) with the A2FC substitute font: not byte-identical.
7. **Timing**: the original takes 0.3 to 8.9 million cycles per real
   picture (median 2.4 million, about 2.4 s at 1 MHz), drawing on the
   visible page. A viewer may be faster; showing the drawing progress
   (the original's visible drawing, or the A2FC progress cell) keeps the
   0.9.3 rule that long operations show activity.
8. **Self-check** with Appendix B; the maintainer can also compare
   against the original routines on the 398 real pictures (private
   oracle).

## 18. A2FC's viewer (GMAGIC)

The overlay `src/plugins/gmagic.s` (header in `gmagic.c`, tables generated
into `gmagic_tables.inc` and `gmagic_text.inc` by
`tools/gmagic_ref.py --includes`) was written from this document alone;
`tools/gmagic_ref.py` is the in-tree reference written from the same
text (the private one of section 1 stays outside). What it does beyond, or
short of, section 17:

- **Routing.** Return opens GMAGIC (kind 11 of `src/open.s`, mirrored by
  `tools/file_viewer_ref.c`) on a BIN whose first 8 bytes look like a
  picture: first command $2x-$Ax with an even nibble, every command
  starting in those bytes a known one with its argument nibble in range;
  a picture that ends within them must obey rules 4 and 5; one that goes
  on must not repeat its first three bytes at once (bytes 3-5), which
  rejects tables, data and text. Arguments are not checked there: the
  overlay checks the whole file.
- **Checks.** The file type must be BIN ($06); every part is checked
  before anything is drawn; a read error at any byte, even after the
  first picture, or a failed rewind refuses the whole file. Every refusal
  gives the one note "Not a whole Graphics Magician picture, or I/O
  error."
- **Keys.** N or the space bar: the next part on a cleared page (after
  the last, the first again); O: the next part drawn over the page (a
  room and its overlays; the viewer cannot tell a group from a room file,
  the reader chooses); D: the same view redrawn in the other dialect (not
  for a V84 file); Left, Right, S (slideshow) and Escape are the core's.
- **Only V82 (PICDRAWF) and V84.** The V82E pen start and PICDRAW's row
  addressing below the screen (section 11) are not implemented by the
  viewer.
- **Text** past the right edge: a character whose byte column would be
  above 40 (cursor X ≥ 287) is not drawn, the cursor still advances.
  The substitute font is BOLD.SET (CiderPress II's STANDARD font, each
  dot doubled to its right).
- **Memory.** Read-only, main bank only: it writes hi-res page 1, the
  112-byte heads of the main text page's 128-byte blocks (font and row
  patterns), its own $0C00 area and buffers the core lends it; never
  auxiliary memory, never a disk.
- **Tests.** `tools/test_gmagic.py` runs the overlay under sim65 on both
  processors against every page of Appendix B, the malformed cases of
  section 11, read errors and the keys; `tools/test_gmagic_writes.py`
  runs the shipped 6502 GMAGIC.PLG in an interpreter that records every
  write; `tools/gmagic_pages.py` writes the overlay's pages for a
  comparison with the private oracle.


## Appendix A. Pattern and brush data

Observed on the screen under the emulator from the original routine (1984 PICDRAWH; the 1982 routines hold the same functional data), and checked by rebuilding the tables from this text. Bit conventions: in a screen byte, bit i (0-6) is the pixel 7c + i of byte column c (leftmost pixel in bit 0); bit 7 selects the colour group of the whole byte.

### A.1 Row patterns (27)

Each line: row-pattern number, then the four bytes used in byte columns c with c mod 4 = 0, 1, 2, 3 (hexadecimal, bit 7 included).

```
R00  7F 7F 7F 7F
R01  FF FF FF FF
R02  77 6E 5D 3B
R03  6E 5D 3B 77
R04  BB F7 EE DD
R05  3B 77 6E 5D
R06  F7 EE DD BB
R07  33 66 4C 19
R08  CC 99 B3 E6
R09  00 00 00 00
R10  EE DD BB F7
R11  80 80 80 80
R12  AA D5 AA D5
R13  A2 C4 88 91
R14  2A 55 2A 55
R15  88 91 A2 C4
R16  22 44 08 11
R17  B3 E6 CC 99
R18  D5 AA D5 AA
R19  08 11 22 44
R20  DD BB F7 EE
R21  91 A2 C4 88
R22  55 2A 55 2A
R23  11 22 44 08
R24  C4 88 91 A2
R25  5D 3B 77 6E
R26  44 08 11 22
```

### A.2 The 108 patterns

Each entry `n:e/o` gives pattern n, the row pattern of even screen rows (e) and of odd rows (o), numbers from A.1.

```
  0:00/01    1:02/01    2:03/04    3:05/06    4:07/08    5:09/10
  6:09/11    7:00/10    8:00/12    9:03/12   10:09/12   11:09/13
 12:14/12   13:05/15   14:16/15   15:16/01   16:14/10   17:14/01
 18:14/06   19:14/17   20:03/11   21:16/11   22:14/18   23:19/06
 24:03/01   25:00/06   26:02/20   27:00/18   28:00/21   29:03/21
 30:03/18   31:16/18   32:09/21   33:09/06   34:07/18   35:02/18
 36:22/18   37:02/08   38:22/01   39:22/06   40:22/17   41:22/11
 42:02/11   43:23/24   44:22/10   45:22/13   46:23/06   47:23/11
 48:02/15   49:22/12   50:02/12   51:23/13   52:01/01   53:11/11
 54:01/10   55:10/04   56:01/13   57:12/01   58:06/12   59:12/10
 60:12/12   61:11/12   62:13/15   63:11/13   64:06/01   65:06/08
 66:06/20   67:18/01   68:06/18   69:01/21   70:18/18   71:18/21
 72:21/24   73:11/21   74:06/11   75:18/10   76:18/12   77:00/00
 78:02/00   79:00/23   80:09/09   81:07/03   82:14/02   83:03/05
 84:00/16   85:14/00   86:14/03   87:14/14   88:19/05   89:09/03
 90:19/03   91:16/19   92:09/16   93:00/03   94:02/03   95:02/19
 96:22/14   97:02/25   98:22/00   99:22/03  100:22/02  101:22/22
102:22/09  103:02/09  104:02/23  105:02/26  106:23/26  107:09/23
```

### A.3 The 8 brushes

16 rows of 14 pixels each, top row first; in each row the leftmost character is the pixel at X (offset 0 of the stamp), `#` = pixel drawn with the pattern, `.` = untouched. Row r, column j of the stamp lands on screen pixel (X + j, Y + r).

Brush 0:
```
..............
..............
..............
..............
..............
..............
..............
.......#......
..............
..............
..............
..............
..............
..............
..............
..............
```
Brush 1:
```
..............
..............
..............
..............
..............
..............
..............
......##......
......##......
..............
..............
..............
..............
..............
..............
..............
```
Brush 2:
```
..............
..............
..............
..............
..............
..............
......##......
.....####.....
.....####.....
......##......
..............
..............
..............
..............
..............
..............
```
Brush 3:
```
..............
..............
..............
..............
..............
.....####.....
....######....
....######....
....######....
....######....
.....####.....
..............
..............
..............
..............
..............
```
Brush 4:
```
..............
..............
..............
.....####.....
...########...
...########...
..##########..
..##########..
..##########..
..##########..
...########...
...########...
.....####.....
..............
..............
..............
```
Brush 5:
```
..............
.....####.....
..##########..
.############.
.############.
.############.
##############
##############
##############
##############
.############.
.############.
.############.
..##########..
.....####.....
..............
```
Brush 6:
```
..............
..............
..............
..............
......#.......
...#.....#....
.....#........
.......#..#...
...#.#........
.......#.#....
....#.........
.......#......
..............
..............
..............
..............
```
Brush 7:
```
..............
.....#...#....
...#...#......
..#..#...#.#..
......#.......
.#..#..##.#.#.
...#.####.....
.....#####..#.
.#...#####.#..
...#..##..#...
.#...#..#...#.
...#.#.#.#.#..
..............
....#...#.#...
......#.......
..............
```

## Appendix B. Synthetic test pictures

All tests are pictures made for this purpose; none comes from Penguin's
disks. A clean-room renderer regenerates them from the rules below and
compares the SHA-256 of its page with B.3. Every random picture is valid
in both dialects (no text), so each has an expected page for V82 and for
V84. Notation: `P(c, x, y)` is the 3-byte command `c OR (x >> 8)`,
`x AND $FF`, `y`; `[...]` are literal bytes; every picture ends with `00`.

### B.1 Random pictures R00-R59

Generator: a 31-bit linear congruential generator,
`state = (state × 1103515245 + 12345) mod 2^31`, and `rnd(n)` = update the
state, then return `(state >> 16) mod n`. Two edge lists:
EX = 0, 1, 2, 5, 6, 7, 8, 13, 14, 265, 266, 270, 272, 273, 276, 278, 279
and EY = 0, 1, 2, 175, 176, 177, 183, 184, 190, 191.
`point(edge)`: only when edge is true, draw `rnd(2)`; if it is 0: x = EX[rnd(17)], y = EY[rnd(10)]
(x drawn first); otherwise x = rnd(280), then y = rnd(192).

Picture k (k = 0-59): seed = 1000 + k, count n = 10, 40, 120 for
k mod 3 = 0, 1, 2. Repeat n times: r = rnd(100);
r < 8: `[20 + rnd(8)]`; r < 12: `[40 + rnd(8)]`; r < 18: `[60, rnd(108)]`;
r < 30: line start at point(no edge); r < 55: line to point(no edge);
r < 70: brush at point(edge); otherwise fill at point(edge). Then `00`.

### B.2 Hand-made pictures

- H01 empty picture.
- H02 colour change between lines: `[22]` P(80,0,10) P(A0,279,10) `[25]`
  P(A0,0,20) P(80,0,30) P(A0,279,30): the second line is still violet, the
  third orange.
- H03 every colour on diagonals: for c = 0-7: `[20+c]` P(80,0,40+12c)
  P(A0,279,46+12c) P(A0,3,52+12c).
- H04 the palette: `[24]`; for k = 0-12: P(80,23k,0) P(A0,23k,189); for
  k = 0-9: P(80,0,21k) P(A0,276,21k); for i = 0-107: `[60, i]`
  P(E0, 23(i mod 12)+11, 21(i div 12)+10).
- H05 brushes and edges: `[60, 80]` (pattern 80 is black); for k = 0-7:
  `[40+k]` P(C0,20+30k,20); for k = 0-7: `[40+k]` P(C0,266+13(k mod 2),60+18k);
  for k = 0-7: `[40+k]` P(C0,10+33k,176+(2k mod 16)).
- H06 fills on row 0: `[24]`; for k = 0-13: P(80,20k,0) P(A0,20k,30);
  P(80,0,30) P(A0,279,30); for k = 0-12: `[60, 7k+3]` P(E0,21k+7,0).
- H07 fill started on a black line (V84 row-below rule, V82 draws nothing).
- H08 triangles W = 8, 36, 37, 38 bytes wide, h = floor(7W/2): `[24]`
  P(80,140-h,10) P(A0,140+h,10) P(A0,140,180) P(A0,140-h,10) `[60, 40]`
  P(E0,140,12) (V82 8-bit middle).
- H09 fill started on a black line on row 191 (V84 rows below the screen).
- G01 a group of three pictures in one file; O01 a picture and an overlay.

### B.3 Expected pages

Columns: test name; first 16 hex digits of the SHA-256 of the picture bytes (to check the generator); SHA-256 of the 8,192-byte page $2000-$3FFF after drawing on a page cleared to $FF, for V82 and V84. All values were produced by the private reference and confirmed by running the original routines (PICDRAWF relocated, as shipped in the games, for V82; PICDRAWH for V84) under the emulator: 152/152 equal.

```
H01-empty                      pic 6e340b9cffb37a98
  V82 7d2c7ac4888bfd75cd5f56e8d61f69595121183afc81556c876732fd3782c62f
  V84 7d2c7ac4888bfd75cd5f56e8d61f69595121183afc81556c876732fd3782c62f
H02-colour-at-line-start       pic d6ab1c33d9cf2ac3
  V82 85d05f1fd0db6cfde5348ee839ec0a6d0c45de4cc3f6ce11d6af52c5b915a7ac
  V84 85d05f1fd0db6cfde5348ee839ec0a6d0c45de4cc3f6ce11d6af52c5b915a7ac
H03-all-colours-diagonals      pic aba30541236f8b35
  V82 782bf4903f1b6065a815394fd0d9f5af3bc4a59d15e573352dc974af55a3c53e
  V84 782bf4903f1b6065a815394fd0d9f5af3bc4a59d15e573352dc974af55a3c53e
H04-palette-108-cells          pic a25c3f58f512fe9e
  V82 b67842bf38ed8566acc7e8e5932f5c5e980014e76a9c80f7ca2e933e43f11408
  V84 b67842bf38ed8566acc7e8e5932f5c5e980014e76a9c80f7ca2e933e43f11408
H05-brushes-and-edges          pic c70cf85993673fee
  V82 64ff66e9b0ec854af0a2205ad2acfa2bb4b300f285ed1bdd63840d212f0ed94d
  V84 64ff66e9b0ec854af0a2205ad2acfa2bb4b300f285ed1bdd63840d212f0ed94d
H06-fills-on-row-0             pic c9d868c13a0ebd3d
  V82 1544b5807f831a2cf5b1b8b8fc1da5046a8e5b031f424631ee7a914b2e009806
  V84 9b262e8bf50f79ced583157e629fcc9cb0296ddd5862ca0591e4cc2513bfe672
H07-fill-from-non-white        pic dff59b9f619a2772
  V82 7948c9c7bfe6ad3adf26c3bf3b5be14734ba30abdb2f2ea524d9547832144db5
  V84 b3141c073eaf7d70f6cebad92e23f95e0da98d14345058e38651e67d8c54267e
H08-triangle-8-bytes           pic c9e44615bc56322b
  V82 02c678ea60ef04fe24868778c95214fabb22d32bcd8020b5a4e16c5c5254a9f2
  V84 02c678ea60ef04fe24868778c95214fabb22d32bcd8020b5a4e16c5c5254a9f2
H08-triangle-36-bytes          pic 9a7119c16fc58f11
  V82 1ab2015438d20c386f86ef0db7d4e4062e08dfc2e74198d821350540c4db1f8a
  V84 1ab2015438d20c386f86ef0db7d4e4062e08dfc2e74198d821350540c4db1f8a
H08-triangle-37-bytes          pic 8717d383e283d19f
  V82 a248cb08b2a4b6c0693f5e380251ad824eaea19b5a6d53cdf6df3d53df5a446e
  V84 7af6237120245d00fd041ce0c9423c672905928136c9336af2f0223e7eb5d1ef
H08-triangle-38-bytes          pic 6c1d3f24638f6ae5
  V82 1d0ce233f2ec2e53ca7c8551dcf96086d632659f5c82611596191515cc32c97d
  V84 fd31ddd476470fe74bbe2c2c4ea481aab509f2d610a0d7aa6bd01e349791a087
H09-fill-at-row-191-non-white  pic 727f87412301e858
  V82 4a5f5897a2fe26f1ca653c53880f7e69ceb3595ab2bf0cc11f6c53727c8b292f
  V84 8680f8d30b788e692c7d767db97accc1abb1708caf518bb415859163442a49b4
R00-seed1000-n10               pic 69232c717f0f59e6
  V82 1ece7888291b60f61860e92c2b96bb32f690bea39cd7d3a18e1bf1ad81a1a609
  V84 fd4747c8fea292a79212017bbad5b9f485b5d082ca67859f71326067ec4c756c
R01-seed1001-n40               pic c9167a6140da6734
  V82 eed4d1573324eac536f36e78a6afb4cfd5a97b7179493f664a33394190f52f12
  V84 fe43b36a7e902ade1249a9867343922aa08d030e6218886ece22d1bb38196563
R02-seed1002-n120              pic 97f829bd4bbd68eb
  V82 d2ff900cbf573382c55499e678a0c0d4a6cad3d5929d9f55e12f0570d838e2bf
  V84 e512329d240e5619576cc539170fb7303c68f00c4db3e27aa03d370d6d2499e2
R03-seed1003-n10               pic c89a1abc9530f576
  V82 8323432cd38621999620965e7b5deb5e627988d09f400b120306389408afe7e6
  V84 8323432cd38621999620965e7b5deb5e627988d09f400b120306389408afe7e6
R04-seed1004-n40               pic ad6edaf656932b0c
  V82 5df02df371d728d308b405ed9a4006a540c7ef823a367a3c7ad93c6e0dfd9796
  V84 879c20f7081d35ffff437b1d74461455fb5476ec5e749853f658a278fdc9f0d7
R05-seed1005-n120              pic ca1b96464699a901
  V82 71414d3c08a76d87a6ef61417f5397e23dffd9b1d026fe53bf6e88e8dae5ae22
  V84 b5a56ebfd2ee3e6595027f1732f4519f28b2311c045259e8e0396f1a22d267de
R06-seed1006-n10               pic d246e611b9744bc9
  V82 96f65cb69e9b7b80d6f973e7973e7bc31a9cb23b734ea08266b2d468fea1681b
  V84 0d835b6ea89d025e301d8e63754c788be4fe1c5c685d362765d36e6f6e7ad618
R07-seed1007-n40               pic 47d70fd5da45a946
  V82 033b9216e7bdef4884ffd52edf436d6264063415394079bbbde0b2da0fbf1fda
  V84 c00d3e7d30131774fba4a731f55927aea1c82b0e006017350eff0bf358e0ef51
R08-seed1008-n120              pic 70b3cbda65dd7bf2
  V82 7906cadefe405dd4343f9b9deb4f40c41981216c67b1cb07a379cbba0761dc5c
  V84 71ce8fd2b616133c929c8f44de87981a6cfcbb25d145291669f9de8f4d560c93
R09-seed1009-n10               pic fc2d85a99d042049
  V82 eda7afebaa6c9f161fb3853530f113f1ab8911a560629dc491ff55adb4aaad43
  V84 eda7afebaa6c9f161fb3853530f113f1ab8911a560629dc491ff55adb4aaad43
R10-seed1010-n40               pic 791d154eb9d055e0
  V82 29e8486b693edeb1e9088da0b5bde6c37fc8765713e3b517fffed42f1c7230e9
  V84 8ce09a06fe4790e69cb60b5a8dae586836d0fa20b114d42187a4c315826e7c61
R11-seed1011-n120              pic c69d8ab9d008ed08
  V82 80c019558b02a2742de563d3769b6281ad7dc9342c6ad986129861bf269b9a6e
  V84 f9662a890398d768ccf11e4db93f5b184f25172e5b312a8d005e30ddd245f3f6
R12-seed1012-n10               pic 5703c6b753fcb5fd
  V82 84403b5e51b9762d4894fc9c8ec5dd117e03f0fe94b52d0bfab2d1770a89bf60
  V84 84403b5e51b9762d4894fc9c8ec5dd117e03f0fe94b52d0bfab2d1770a89bf60
R13-seed1013-n40               pic bd8a2ac883c10edb
  V82 dbbe3e3ec2274283936172193fa3dff09359fc75bbd979ce4cfe652a36097665
  V84 b0f6f1e6e3ca8de5b39af4bdc7f2a38b03919e0a18f9f106a0162974667ef9e9
R14-seed1014-n120              pic 5ffa5c4a4635dcfb
  V82 882e041c206ccc162f702700aa405bf3b53aacfc4703b1c02f91b3190fb9fa61
  V84 b2dd76a48df70c1a866487410f208c7d47b62659022867bdb2eb7984115af1c1
R15-seed1015-n10               pic 8d70f19bf8f3edc5
  V82 ba8beb9e4ec13614ea5d0949acfec0275c6bd5abe641bc7000742f7090abe068
  V84 ba8beb9e4ec13614ea5d0949acfec0275c6bd5abe641bc7000742f7090abe068
R16-seed1016-n40               pic e906717916e1f8c1
  V82 3a53d941341a7e81ce298cee5b5a222fbd5ffe9904eadf2444bfa189c465f313
  V84 3b399bc795aec30e9332a0d7d39e1a8f65135758fdfb43ea02d3d3fbc6914466
R17-seed1017-n120              pic 208f584fcedaf31b
  V82 478f6d732635fd01328e1018bf3d393f93843892246f054ec6ec3a120d75c071
  V84 59614aae75b9c9814be136b5b45e22a20af80356490b2955fe73cdd9b4f868d8
R18-seed1018-n10               pic bb9bb66f15fb4db5
  V82 6b1852aa7569fb5c58db4f3c7e3ae83ed82d219a4f3cb42c268451089ea05cdc
  V84 6b1852aa7569fb5c58db4f3c7e3ae83ed82d219a4f3cb42c268451089ea05cdc
R19-seed1019-n40               pic 89a421484af46d07
  V82 4bd715fb39fbe9ee280e1a2027b1c54d43a0ddc302cb3ecedc0abed7c3857461
  V84 8d1f63ab65a75440780c9e2ef96f7d240310c87d12d4d399e88ef4f24de42353
R20-seed1020-n120              pic 03a3450e3de8bd6c
  V82 e92a8512c41534a30dfe505484121b0246e057940738b29f1c5f152b93a6de26
  V84 2470b518c698f3f943941f815165124941d011ee073598f9dfe595c25480dfe5
R21-seed1021-n10               pic 409562bbc7332a2a
  V82 f9e401e0db22691dd814629fb72c6e15ae94c0232ae4fe9a7a8a9ab544cc200d
  V84 f9e401e0db22691dd814629fb72c6e15ae94c0232ae4fe9a7a8a9ab544cc200d
R22-seed1022-n40               pic 0d5dd3bb09e8a194
  V82 5953d9b15743f9f0f0525fbd895842af0087a10a0ed377e98703409447cc089f
  V84 8dfa5c49980b509fc43d246c4d24facccff2b0721d7f0a944a6cb8ebeff3d2fc
R23-seed1023-n120              pic 2811a201bb33167f
  V82 259f861c361e4a145a7354ed53a0d770005cc320b859cc926a34783b16b79895
  V84 a75283b668a53d90d29ae760f0f0bf1896a169485d56dc12740a64a9c3e14685
R24-seed1024-n10               pic fba548c32cfd7a60
  V82 1e6523b7eab4d2f6c0c0451664f8b67de4053bea7dbc8949116b72a86e49ba47
  V84 1e6523b7eab4d2f6c0c0451664f8b67de4053bea7dbc8949116b72a86e49ba47
R25-seed1025-n40               pic e5b0c1933a6d87ef
  V82 0df932c5c141103be7c2b7a29b2055179f8a51815522a6ccd4abc52454fd7282
  V84 5685343663f6037034e5307a87eba6296fa32e5f2bdf0d290d3b186832d00af2
R26-seed1026-n120              pic a8aa85447706a120
  V82 12fd43979ecc6eeea7b919d0d810a760d1151f57b1a4ccf6df2564c6d8191d1f
  V84 55c29e18ea6a44d8f0014f18d14f34d87a06162ecf1bd50084e1981972fdd694
R27-seed1027-n10               pic 90b36a07a4b4c368
  V82 182695a340263dcb1e427429055de510d0bf3596ab454d6ee76ae003727d179f
  V84 182695a340263dcb1e427429055de510d0bf3596ab454d6ee76ae003727d179f
R28-seed1028-n40               pic 4dd1a9384281a699
  V82 f4c5815f8b43560ae341203a248de3e96c09a53b95bfac79efa6f468b649970e
  V84 296e332bab2a5c96ceb296c4af7a04b09f5675cc612dca7950b94099806db9df
R29-seed1029-n120              pic 428c9a33927977dd
  V82 05a2ae831a8c2614ac982d9738777c9028d69119bb0d541813e0cdc82d4ef02f
  V84 1b2cc09ffd5de5e1b79f8bacbba20f96d8b94fb85b1db7057ec1124d9dab316e
R30-seed1030-n10               pic 5902f8e0f91f53e0
  V82 99a3f7b3ade28fb77320512a4c0f08aa727d120ade1389349dfbdbe93cc23b60
  V84 18f1daa79d899f8723a2e07626b570206818964a1d770e8c8087c9bf96e91317
R31-seed1031-n40               pic 3d4cf6ae983e2f26
  V82 67abe98e61c754651a39b4561b5190f4e40c0c3f218711bafae33708eaa7f3a6
  V84 67abe98e61c754651a39b4561b5190f4e40c0c3f218711bafae33708eaa7f3a6
R32-seed1032-n120              pic 1b165d5821482875
  V82 4b28c8a482dd79d012317be7ed49926427a82a88a6da06d1c2368e81cb9183c0
  V84 b50df7400144a65114595c81758e33bb242e3c19a9a812d575185ea992a4ea0f
R33-seed1033-n10               pic bc6c213e907ca254
  V82 0c92dece46279e2de87794d81e4b1304af18df404a7ed333d4d4a45cf0eb1ade
  V84 0c92dece46279e2de87794d81e4b1304af18df404a7ed333d4d4a45cf0eb1ade
R34-seed1034-n40               pic d89b1d69a4a02cac
  V82 04fd38a899c0af85cfdd1c02a99a8ec2502a532871030bb0c027d73e374ec5fb
  V84 6f117d39bde83931e813f71be92744b5f9ab50c0992a6025bec325b26121f3a5
R35-seed1035-n120              pic 1dcef6a860c12197
  V82 f73c4c2c671bd1fa53c45be83c6d72ebc11490cfc8cca17889a45c2681e3c07a
  V84 75d8e44c1a4bc37339c30f6ea4d004f8999de63cbcfed5e9f924d28da506d507
R36-seed1036-n10               pic 3eed525aea99f559
  V82 3133190b6b63d199a2bb4f43555e51f08a6afb1f09d0cce8061789e5538f0d65
  V84 3133190b6b63d199a2bb4f43555e51f08a6afb1f09d0cce8061789e5538f0d65
R37-seed1037-n40               pic bef9a7a7148e291d
  V82 3dd55d5e9e343bd1b82cad0cc3eba7278b9a261b963a41987410d35fa5ad0fd1
  V84 caa0d2b2d2a87f1bd326610c01279b393aeb2834d0a966cb289c26f617ba5362
R38-seed1038-n120              pic 1beb1f5a1ae5007d
  V82 61ad0adddfff0ed0bd1e7b122060f03803419f26388ac3831bc67d942d6372d3
  V84 db620fc4a12276c86e280aea8e43ba0b17c28da929d977343d33e2e27cc0962d
R39-seed1039-n10               pic 144827a3462c73be
  V82 4529dd6cc991cf1913d58b936e59cf7fb6a47ff6f1d036a49f5abc99760b99ca
  V84 6b7201765f4b525556de10f155850b95be46cd20ee7d2b31433efd3d9ec3001d
R40-seed1040-n40               pic 03c5d7c4c12ad33d
  V82 224f029ccccfe3c6e19e1da28a851ac658b52eaafc2b83f38709b6709cf3e03b
  V84 0df875b57b5235a260fc8dbc033f73a3c76b81d291afcf08bb0034c46af736df
R41-seed1041-n120              pic 0e8b3da3a03672c8
  V82 0bb16a86e6035d44a6870c76c1b435f1e23c76c8ee5c3865b15008c018938b15
  V84 643fa3ea20d4223d7566a8ca110b9ddbbf37f303f78f90330dd6a88e3fa0f351
R42-seed1042-n10               pic 6921ce9726243609
  V82 05b7a6c4a13ae3f60049ea077e2609ea406725b270a3489374fd6e6a9a560a80
  V84 05b7a6c4a13ae3f60049ea077e2609ea406725b270a3489374fd6e6a9a560a80
R43-seed1043-n40               pic d75e8263068c20aa
  V82 2523902f484e0f23ed391f80e80713d9f1056fba0fe062aff08d9782b4a0e4bf
  V84 fb85756131bf9673016e1212fbae7d54c7c471a195a1e6994497c15909ef47f3
R44-seed1044-n120              pic c27098e6ce26aa9c
  V82 55e92f1f9f8cc1a5fbb86d1d2c460a24fd6794e33cbfe84797c6fe0d00b66729
  V84 722e37c6824e4ebca64b14f63b9536129893e5f2ac869d7bcbf05735e6836a8d
R45-seed1045-n10               pic a15892b9372d8f38
  V82 46163562586d41ca2b0e1e2fe3b2ee685bef978f5bdea25488acae3d783358fa
  V84 46163562586d41ca2b0e1e2fe3b2ee685bef978f5bdea25488acae3d783358fa
R46-seed1046-n40               pic 344ae87bacc8d4ba
  V82 5771885db259905b0e835961b7331dcc0059ca0dfbfa5d0807f73cedd145c9ad
  V84 18cc38d16e8227f5269abc053a240d9db2261d19874e1acb5a8c218352913b13
R47-seed1047-n120              pic cd536fe1627c8319
  V82 2748958643ec2e0a37a3ad445c5884a8d1d6da6ffb829ffbc36e68ed64924296
  V84 1014ee4bbc6d10436ba71c9fed0f292819f648b7139e41dfe608614a27ee8f14
R48-seed1048-n10               pic afa836b84b6abc9e
  V82 222733222c455cce7103853427d0f17849fcf9c0620cfb400def8aae508eec51
  V84 222733222c455cce7103853427d0f17849fcf9c0620cfb400def8aae508eec51
R49-seed1049-n40               pic a67de618787bf07a
  V82 fdf6879a657669b689a80978f7276d4838ac76b65c9ff39aa8e63a203b60a07b
  V84 ffac57d345fb566687a23d00b9b23ba56b9c033ac5a4d0b5afd759762c3c0372
R50-seed1050-n120              pic ea705c73a037482f
  V82 b3865c6e9cad1d9d9a2f3402bba7be73dc075bee8d6747a206ac1cef17e2eb26
  V84 b6f67c9c15a2eea6667798878ca848e6b5822c2b8cae59601b1fe2db0bd263e4
R51-seed1051-n10               pic e32b1d89b01fba51
  V82 d2da962648b76b9e8b6f2c77c9875bbfd40dda3fcb3c7b01eb45253f57d25ea8
  V84 d2da962648b76b9e8b6f2c77c9875bbfd40dda3fcb3c7b01eb45253f57d25ea8
R52-seed1052-n40               pic 51c74c0c1e52cb69
  V82 17db2e28195c017d255d30b882ef2288701b5d6bfdf01a0147c44cf51347537a
  V84 1da0adbb972bb1f50e2a5dd28c7091e5dde59b2b604194c65a2b599592b4de33
R53-seed1053-n120              pic c10158fdf3214cfe
  V82 046f3a96653af7400e18753464602b45cbb3a5447d7493efbb72962a26b0668e
  V84 620c7a06281cbca362ff9c91e5a23318660f39094595f5bc4b9795e77a91a212
R54-seed1054-n10               pic 2181b33640ed14d8
  V82 b768b3a310f2db9ea93539bbcdf40bd5af331b21f9c8e2ba1529d30a2760665f
  V84 b768b3a310f2db9ea93539bbcdf40bd5af331b21f9c8e2ba1529d30a2760665f
R55-seed1055-n40               pic e6812b12ec7d9a1f
  V82 862a651cd095d60a8e50b499023c5179ed7d5a47068adfd3f8642cdd4538e96c
  V84 862a651cd095d60a8e50b499023c5179ed7d5a47068adfd3f8642cdd4538e96c
R56-seed1056-n120              pic 7c9929d1c899b29c
  V82 58300f214a4184fa0f4744f989dc41b7410e22ae0f88650fbe39a95ccbd6ec2d
  V84 fc0852d8593877d97688669941ae269b1c50c3df6fde8a6a670ecfc24791e192
R57-seed1057-n10               pic f8c3f1af079401ac
  V82 246304867287c501f7d2dd7a00ab86a2482f19b860fcb09fa93aca57227c33ce
  V84 246304867287c501f7d2dd7a00ab86a2482f19b860fcb09fa93aca57227c33ce
R58-seed1058-n40               pic 43d2d7d6dc364136
  V82 08f1ccd3ba720746d500d01a91c03d6a2eba0e2c56dacb22d89c7ea17461ea3f
  V84 7e4ba337708c1f86ef6b52086a94c6c5047fb238f9f4602398e7c0cdf5214465
R59-seed1059-n120              pic bb3a87c80843e179
  V82 3b1d284c881c10426e506b24675bc2d5e0d7cc46857c29077d22bf47d3dec860
  V84 8d2186d1aa36f547fe710b4a0143eabbfa4884890f2c9cdc530eb64077cc45f0
G01-group-of-3 (each picture drawn on a cleared page)
  [0] V82 eae051fac75f2e9b16c728c29fee97b900bb5326b1774c61f624eb80b20d6261
      V84 eae051fac75f2e9b16c728c29fee97b900bb5326b1774c61f624eb80b20d6261
  [1] V82 0fa3d17b35977125109c416b39621f61c3281d81d6e920d5b6c0b71ddca459a0
      V84 0fa3d17b35977125109c416b39621f61c3281d81d6e920d5b6c0b71ddca459a0
  [2] V82 48bac11f3aa6a70758b08f21d6b09a554480f133385303e9fd2f1c504185e76d
      V84 48bac11f3aa6a70758b08f21d6b09a554480f133385303e9fd2f1c504185e76d
O01-picture-plus-overlay (part 0 cleared, part 1 drawn on top)
  V82 c1fa2c112c1e27d0fad98de384aee9ad558a3dee5af1cab1a8fceff293a30aee
  V84 89eab067e86ac72336ce1e75e500ea57ea7fa49b11123b3ff6a5503c2bf28eae
```

Hexadecimal of the short hand-made pictures (the others follow from B.1):

```
H01-empty                      00
H02-colour-at-line-start       2280000AA1170A25A0001480001EA1171E00
H07-fill-from-non-white        24800064A117646014E08C6400
H08-triangle-8-bytes           2480700AA0A80AA08CB4A0700A6028E08C0C00
H08-triangle-36-bytes          24800E0AA10A0AA08CB4A00E0A6028E08C0C00
H08-triangle-37-bytes          24800B0AA10D0AA08CB4A00B0A6028E08C0C00
H08-triangle-38-bytes          2480070AA1110AA08CB4A0070A6028E08C0C00
H09-fill-at-row-191-non-white  248000BFA117BF601EE064BF00
G01 parts: 600FE00A0A00 | 24800A0AA0C89600 | 605A47C0646400
O01 parts: 24803232A0E632A08C96A032326007E08C3C00 | 603CE00A0A26800000A117BF00
```
