# Take 1 movies (Baudville, 1985)

*Take 1* (and *Take 1 Deluxe*) makes hi-res animated movies on the Apple II.
The user cuts **actors** (sets of sprites called snapshots) out of pictures,
shoots **scenes** frame by frame by placing snapshots and lines of text on a
**background**, then splices scenes into a **movie** with fades between
them. Every part is a separate DOS 3.3 binary file, found by its name.

This document describes the files and what a viewer of them shows, as
observed; it is the only input of A2 File Cmd's player, which is written
from it and from nothing else (Take 1 is not free software, and none of its
code or tables is used).

The facts below were established on the 30 disks of Take 1, its animation
libraries, its programmer's toolkit and users' movies preserved by the
Internet Archive (15 distinct movies, 176 scenes, 290 actors, 67
backgrounds), and checked against the original projector running under
emulation: every frame of every movie (about 9,000) is identical, byte for
byte, to what the rules below produce. Those study tools are private and
are not part of this repository.

Numbers: `$` is hexadecimal. A **row** is a hi-res screen line, 0 (top) to
191; a **column** is a screen byte, 0 to 39, holding 7 dots, bit 0 the
leftmost, bit 7 the palette bit. "Dot x" is screen dot 0–279: column x div 7,
bit x mod 7.

## Files and names

Each file is a DOS 3.3 binary file (type B). Its name is a two-letter
prefix, a period and up to 20 characters (letters, digits, spaces and
punctuation all occur). The prefix gives the kind:

| Prefix | Kind | Load address | Used by a movie |
| --- | --- | --- | --- |
| `MV.` | movie | `$8029` | the movie itself |
| `SN.` | scene | `$9400` | named by the movie |
| `BK.` | background (compressed picture) | `$2000` | named by the movie |
| `AC.` | actor | `$8000` | named by the scene |
| `CS.` | character set (font) | `$6000` | named by the scene |
| `PI.` | hi-res picture | `$2000` | no (editor only) |
| `ST.` | Applesoft shape table | `$6000` | no (editor only) |

The load addresses are what the editor writes; the player does not need
them. Below, "the file" means the data after the DOS 3.3 binary header
(address and length, four bytes). Names inside files are 20 characters,
padded with spaces, without the prefix, and with or without bit 7 set on
each character (a movie sets it, a scene does not): compare them on the low
seven bits, after removing trailing spaces.

All the files of a movie are on one disk. (Take 1 allows a second data
disk; no movie seen uses one.)

## Movie (`MV.`)

| Offset | Meaning |
| --- | --- |
| 0 | `n`, the number of scenes, 1 or more |
| 1 + 42 k … | entry `k` (0 ≤ k < n), 42 bytes: |
| +0 … +19 | scene name (file `SN.` + name) |
| +20 … +39 | background name (file `BK.` + name), or one of the two specials `< BLACK >` and `< UNCHANGED >` written as such |
| +40 | fade-in, 1 to 17 |
| +41 | fade-out, 1 to 17 |

The file length is exactly `1 + 42 n`. Fade 1 is "none"; fades 2–17 are
described under Fades. A scene may appear several times.

## Background (`BK.`)

A compressed 8 KB hi-res page. Byte 0 is `$FF`. Then the 40 columns are
coded one after the other, **from column 39 down to column 0**; each column
is its 192 bytes, row 0 first. A column is a sequence of codes `c`:

- `c` = `$01`–`$7F`: the next `c` bytes, copied;
- `c` = `$00`: the next byte `m` (1–255) is the count, then `m` bytes copied;
- `c` ≥ `$80`: a pattern of `p = 2^(c & 3)` bytes (1, 2, 4 or 8) follows;
  it is repeated, cyclically, for `q` bytes where `q = (c & $7C) >> 2`, or,
  when that is 0, the next byte (before the pattern; 0 means 256).

A column is complete when it holds exactly 192 bytes; a code never crosses
into the next column. Bytes after column 0 are not used. All 67 distinct
backgrounds seen end exactly at the end of their file; a background that
overflows a column, has a zero count or ends early is damaged (one copy
seen, on a damaged disk) and is refused.

## Character set (`CS.`)

An Applesoft shape table: byte 0 is the number of shapes `N`, then 16-bit
offsets (low byte first) from the start of the file, the offset of shape
`i` (1 ≤ i ≤ N) at bytes `2i`, `2i+1`. Character code `ch` (`$20`–`$7F`)
is shape `ch − 31`; a character whose shape number is outside 1…N is drawn
as shape 1. How text is drawn: see Text below.

## Actor (`AC.`)

| Offset | Meaning |
| --- | --- |
| 0 | `n`, the number of snapshots |
| `2i−1`, `2i` | offset (low, high) from the start of the file of snapshot `i`, 1 ≤ i ≤ n |
| `2n+1`, `2n+2` | offset of the actions (editor data; not used by the player) |

A snapshot is a 7-byte header followed by its rows:

| Header byte | Meaning |
| --- | --- |
| 0 | height `h`, in rows (1–255) |
| 1 | width `w`, in dots, low 8 bits |
| 2, 3 | not used |
| 4 | bit 0: the width is `w + 256` (a full-screen-wide snapshot); other bits: kind, not used by the player |
| 5 | sync x, signed (−128…127) |
| 6 | sync y, signed |

Then `h` rows, each a sequence of codes ending with an end code. Codes:

| Code `c` | Meaning |
| --- | --- |
| `$00` | end of row |
| `$07` | end of row, "short" form (see below) |
| `c & 7 = 7`, `c >> 3` = 1…25 | **extension**: adds `(c >> 3) × 7` to the count of the next skip or fill code |
| `c & 7 = 7`, `c >> 3` = 26…31 | **literal**: `k = (c >> 3) − 25` bytes follow (1–6); each gives 7 dots (bit 0 first) and its bit 7 is a palette |
| otherwise, bit 7 set | **skip** of `n = ((c >> 3) & 15) × 7 + (c & 7)` (+ extensions) |
| otherwise, bit 7 clear | **fill** of `n` dots (same count); the next byte `B` gives the dots and the palette |

A fill of `n` dots with byte `B`: dot `j` of the run (0 ≤ j < n) is bit `j`
of `B` for `j < 7`, and bit `3 + (j − 3) mod 4` of `B` for `j ≥ 7` — the
first seven dots are B's bits, then the four-dot pattern of bits 3–6 goes
on. Its palette is bit 7 of `B`.

How a snapshot is drawn is described in its own section below. All 290
distinct actors seen parse exactly; three files of a damaged disk (empty, or
truncated) are refused.

## Scene (`SN.`)

### Header, `$000`–`$0FF`

| Offset | Meaning |
| --- | --- |
| 0, 1 | number of frames + 1 (not needed by the player) |
| 2 | speed, 1–255 (seen: 22–84; higher is slower) |
| 3 | non-zero: the scene uses a character set |
| 4 … 23 | the character set's name (valid only when byte 3 ≠ 0; otherwise left-over bytes) |
| `$18` | `a`, the number of actors, 0–10 |
| `$19 + 22 j` | actor `j` (0 ≤ j < a), 22 bytes: highest snapshot used (not needed), `count`, name (20) |
| up to `$FF` | not used |

The snapshots of a scene are numbered from 1 through all its actors in
order, each actor taking `count` numbers (the `count` recorded in the scene,
even when the actor file has since gained or lost snapshots): with counts
3 and 4, numbers 1–3 are the first actor's snapshots 1–3 and numbers 4–7 the
second actor's snapshots 1–4.

### Body, from `$100`

Offsets in this part are from `$100`.

| Offset | Meaning |
| --- | --- |
| 0, 1 | offset (low, high) of the first frame, from `$100` |
| 2 | `s`, the number of text strings |
| 3 … | the strings, each a length byte then its characters (plain ASCII) |

The frames follow, one after the other, up to an end marker. A frame is a
sequence of elements ending with the element that carries the end-of-frame
flag. Elements start with a byte `o`:

| `o` | Element |
| --- | --- |
| `$01`–`$EF` | an **object**, 4 bytes: `o`, `xl`, `f`, `yl` |
| `$FC` | a **pause, sound or wait**, 4 bytes: `$FC`, `t`, `g`, `u` |
| `$FE` | an **empty frame**, 4 bytes (`$FE` then three bytes not used); it ends the frame |
| `$FF` | the **end of the scene**, 1 byte |
| `$F0`–`$FB`, `$FD` | one byte, ignored (never seen) |

An object's flags `f`:

| Bit | Meaning |
| --- | --- |
| 0–1 | bits 8–9 of `x16 = xl + 256 (f & 3)` |
| 2 | not used |
| 3 | bit 8 of `y16 = yl + 256 ((f >> 3) & 1)` |
| 4 | **wrap**: the object wraps around the screen edges (see below) |
| 5 | **plant**: the object becomes part of the background (see Frames) |
| 6 | **text**: `o` is a string number (1…s); otherwise `o` is a snapshot number |
| 7 | **end of frame** |

`x16` is the dot x plus 280 (0–1023), `y16` the row plus 192 (0–511).

For `$FC`, `g & $7F` gives the kind and bit 7 of `g` ends the frame:
`g & $7F` = 0: wait for a key (Return) or a paddle button; 1: pause for `t`
units; 2: sound effect number `t`. `u` is not used. When a frame holds
several `$FC` elements, only the last one counts.

Seen in the 176 scenes: up to 281 frames, up to 27 strings, 0–10 actors;
690 `$FC` elements (11 waits, 187 pauses, 492 sounds); 260 empty frames.

## Drawing a snapshot object

An object element `[o, xl, f, yl]` with bit 6 clear draws snapshot `o`.

### Where

Let `sx`, `sy` be the snapshot's sync bytes. The coordinates are adjusted
**only when the sync byte is not zero**:

- `sx ≠ 0`: `x16 = x16 + sx`; below 0 → 0. With wrap: below 280 → `+280`,
  280–559 kept, 560 and over → `−280`. Without wrap: over 687 → 687.
- `sy ≠ 0`: `y16 = y16 + sy`; below 0 → 0. With wrap: below 192 → `+192`,
  384 and over → `−192`. Without wrap: over 511 → 511.

Then `X = x16 − 280` is the dot of the snapshot's left edge (it may be
negative or beyond the screen), and the first row:

- **without wrap**: if `y16 ≤ 192`, `skip = 192 − y16` rows of the snapshot
  are above the screen and its first visible row is drawn at row 0;
  otherwise `top = y16 − 192` (192 and more: nothing is drawn).
- **with wrap**: `top = y16 − 192` when `192 ≤ y16 < 384`; when
  `y16 < 192`, `top = y16 + 64`; when `y16 ≥ 384`, `top` = 192. (These only
  happen when `sy` = 0.) A `top` of 192 or more draws nothing.

Without wrap, dots outside 0–279 and rows outside 0–191 are not drawn, and
the snapshot is not drawn at all when its column `X div 7` (floor division)
is 40 or more. With wrap, rows go on from `top` and wrap from 191 to 0;
dots wrap from 279 to 0 — but when `X` is negative, the dots left of the
screen are not drawn (they do not wrap) and only the right edge wraps; and
when `X ≥ 280` nothing is drawn.

### The rectangle

The projector also records, for erasing (see Frames), a rectangle of whole
columns. Let `wb` be the width in columns: start with `A = w`, `wb = 0`
(for a header with bit 0 of byte 4: `A = w + 4`, `wb = 36`); while
`A ≥ 8`: `wb = wb + 1`, `A = A − 7`; then `wb = min(wb + 2, 40)`. Let
`c = X div 7`, capped at 40.

- column `max(c, 0)`; if it is 40, no rectangle and **no drawing**;
- width `wb`; when `c < 0`, width `wb + c + 1`, and if that is 0 or less,
  no rectangle and no drawing; without wrap, when column + width ≥ 40 the
  width becomes `40 − column`;
- top row `top` (0 when rows were skipped above the screen); when it is 192
  or more, no rectangle and no drawing;
- height `h − skip` (with `skip` = 0 with wrap); when negative, no
  rectangle and no drawing.

These rules decide whether the snapshot is drawn at all; when it is, the
rectangle is recorded even if it does not cover every dot drawn.

### What

The rows are drawn top to bottom. Within a row a **cursor** starts on dot
`X` and the codes act on it:

- **fill** and **literal** write their dots (opaque: a 0 dot is black) and
  advance the cursor by their length;
- **skip** of `n`: if the skip is the row's first code, `n` dots are left
  untouched (transparent) and the next dot is made black — the cursor moves
  `n + 1`. Otherwise (anything came before it in the row) the dot under the
  cursor is made black, the next `n − 1` dots are left untouched and the dot
  after them is made black — the cursor moves `n + 1`; a skip of 0 then
  blackens the single dot under the cursor and moves 1;
- **end `$00`**: if any code came before it in the row, the dot under the
  cursor is made black; an empty row draws nothing;
- **end `$07`**: no dot is changed (see the palette rules).

So a snapshot is outlined, left and right, by black dots (the editor's
"sprite" snapshots), while `$07` rows (the editor's "blocks") are not.

**Palette bits.** Every screen byte that receives a dot (black dots
included) is rewritten as a whole: its undrawn dots keep their values, and
bit 7 is set as follows.

- The projector keeps a **palette register**. It starts each snapshot in a
  special state, written `P3` here; each fill or literal byte sets it to
  its own palette when one of its dots is drawn or lies left of the screen
  (left of dot 0); runs entirely right of the screen (without wrap), and
  rows above or below the screen, do not change it. It carries from row to
  row.
- A dot of a fill or literal gives its byte that run's palette.
- A black dot under the cursor (after a run, before a skip or at an `$00`
  end) gives its byte the palette register.
- The black dot made at the end of a skip gives its byte the palette of
  the fill or literal that follows in the row; but when this black dot is
  the last dot of its byte (bit 6), it does not set the byte's bit 7: the
  byte keeps the bit 7 that the row's earlier dots in that byte gave it (the
  palette register, through the black dot under the cursor that began the
  skip, or a run), or, when no earlier dot of the row fell in that byte, the
  bit 7 the screen had.
- A byte receiving dots from several runs takes the palette of the last.
- **`$07` end** after codes: if the cursor is not on bit 0 of a byte, that
  byte (the one under the cursor) has its bit 7 set to the palette register
  and no dot changed. A row made only of `$07` (an empty row): if `X mod 7`
  ≠ 0 and the start byte is on the screen, the start byte has its bit 7 set
  to the palette register.
- With wrap and `X ≥ 0`, a row whose cursor ends exactly 280 dots after its
  start, by an `$00` end, came back to its first byte: no black dot is made
  there, and that byte's bit 7 is set to the palette register.
- A byte rewritten while the register is `P3` (before any fill or literal of
  the snapshot was drawn) gets bit 7 cleared and bits 0 and 1 set, whatever
  its dots. (This happens in one actor seen, whose first row is an empty
  `$07` row.)

## Text

An object element with bit 6 set writes string `o` with the scene's
character set. In every scene seen, text elements have wrap set and
`280 ≤ x16 < 560`, `192 < y16 < 384`; a player may refuse anything else.
The pen starts on dot `x16 − 280`, row `y16 − 192`. No sync, no clipping.

Each character is drawn as Applesoft's `XDRAW` at scale 1, rotation 0,
continuing from where the previous character's shape left the pen. A shape
is a sequence of bytes ended by 0. Each byte holds three vectors, A in bits
0–2, B in bits 3–5, C in bits 6–7. Vector A: if its bit 2 is set, the dot
under the pen is inverted (exclusive or); then the pen moves by bits 0–1.
Then the byte is shifted right by 3; if nothing is left, the byte is done.
Vector B the same way. Then, if anything is left, vector C moves the pen
(no inversion). Moves: 0 up, 1 right, 2 down, 3 left. Moving right from dot
279 goes to dot 0, left from 0 to 279, down from row 191 to row 0, up from
row 0 to 191. Inversion leaves bit 7 alone.

The rectangle recorded for a text: the projector tracks the pen's leftmost
and rightmost positions in (column, bit) terms and its top and bottom rows,
starting from the first position, with a width of 1 column and a height of
1 row. Each time the pen moves **left from the leftmost position**, the
leftmost position becomes the new one, and if the column changed the width
grows by 1; the same to the right; each time it moves up from the top row,
or down from the bottom row, the height grows by 1. Rectangle: the leftmost
column, the width (capped at 40), the top row, the height (capped at 192).

A text's cost (see Timing) is 11 per shape byte drawn.

## Frames

The player uses three 8 KB pages: the two hi-res pages and a third page,
**page 3**, which holds the scene's background (and the planted objects).

At the start of a scene, page 3 holds the background (see Movies), and the
**back page** (the one not shown) is a copy of page 3. Each page has a list
of rectangles to erase, empty, and a "full" mark, clear.

For each frame:

1. **Plant.** The objects at the beginning of the frame whose plant flag is
   set (up to the first one that is not) are drawn into page 3. Their
   rectangles are added to both pages' lists.
2. **Erase.** The back page's list is applied: if it is marked full, page 3
   is copied over the whole back page; otherwise each rectangle is copied
   from page 3 to the back page, row by row, each row from its column for
   its width — a column beyond 39 continues at column 0 of the same row, a
   row beyond 191 continues at row 0. The list is then emptied and the mark
   cleared.
3. **Draw.** The other objects of the frame are drawn on the back page, in
   order; each one's rectangle is added to the back page's list.
4. **Show.** The back page is shown (it becomes the front page), except for
   the first frame of a scene with a fade-in, which is revealed by the fade
   (see Movies); that page stays the back page and its list is applied at
   once (step 2), erasing the first frame's objects from it before the
   second frame is drawn on it.
5. If a page was just shown, the new back page's list is applied (step 2):
   after the first frame shown in a scene, this new back page is first
   marked full.
6. `$FC` element of the frame, if any: a wait, a pause or a sound (Timing).

The very first frame of a scene starts, in the original, with the back
page's list marked full (step 2 copies the whole page; it changes nothing
visible but counts in the timing).

Adding a rectangle to a list: if the list is marked full, nothing; the
rectangle is appended, and the sum of the areas (width × height) of the
list's rectangles is kept; when it reaches `$0D00` (3,328) the list is
marked full. A list never holds more than 20 rectangles in any movie seen;
a player marks it full rather than add a 21st.

The rectangles do not always cover what was drawn: a dot left outside its
object's rectangle stays on that page until another rectangle covers it.
Real movies show it (the frames above are what the original shows,
including those leftovers).

## Movies

The player shows the scenes of the movie in order. Before the first scene
the screen, the back page and page 3 are black.

For each entry:

1. **Background.** `< BLACK >`: page 3 is cleared to black. `< UNCHANGED >`:
   page 3 is kept as the previous scene left it, planted objects included.
   Otherwise the `BK.` file is decoded into page 3.
2. The back page is set to a copy of page 3, and the scene plays (Frames).
   With a fade-in (2–17), its first frame, drawn on the back page, is
   revealed by fade number `fade-in` (see Fades) from the back page onto the front page,
   which keeps showing; without one, it is shown like any other frame.
3. **Fade-out** (2–17): fade number `fade-out` copies a black page onto the
   front page, the last frame being shown; then page 3 is cleared to black.
   Without a fade-out the last frame stays shown until the next scene's
   first frame.

So `< UNCHANGED >` after a fade-out is black, and a fade-in without a
fade-out before it starts from the previous scene's last frame.

## Fades

A fade copies a **source** page onto the page being shown (the
**destination**), byte by byte, in an order that makes the effect. In every
fade the destination ends equal to the source in all 7,680 visible bytes.
"Copy row x" means: for column 39 down to 0, destination byte = source
byte. "Copy (x, y)" copies one byte. "Stripe row x" writes, for column 39
down to 1 by steps of 2, `$AA` at the column then `$D5` at the one before
(odd columns `$AA`, even columns `$D5`) on the destination, then waits
`D(30)`. `D(a)` is a delay (Timing).

| Fade | Effect |
| --- | --- |
| 2 | for column 0 to 39: for row 0 to 191, copy (row, column); then `D(40)` |
| 3 | the same, column 39 down to 0 |
| 4 | for row 191 down to 0: copy row; `D(30)` |
| 5 | for row 191 down to 0: stripe row; copy row |
| 6 | for row 0 to 191: copy row; `D(30)` |
| 7 | for row 0 to 191: stripe row; copy row |
| 8 | centre out: rows 96, 95, 97, 94, 98, … — after each row copied, `D(30)`; alternately the next row above (while any) and the next row below |
| 9 | stripes from the centre: stripe 95, stripe 96; then for k = 0 to 95: copy row 96+k, stripe row 97+k (if < 192); copy row 95−k, stripe row 94−k (if ≥ 0) |
| 10 | see below |
| 11 | see below |
| 12 | interlace: rows alternately from the top (0, 1, 2…) and from the bottom (191, 190, …), starting with row 0: the first row copies columns 39, 37 … 1, the second (191) columns 38, 36 … 0, the third (1) columns 39, 37 … 1, and so on alternating; `D(24)` after each row; it ends after row 191 has been copied from the top side (384 rows in all) |
| 13 | centre out by twos: rows 96, 94, 98, 92, 100, … (as fade 8 with steps of 2, `D(45)` after each), then 97, 95, 99, 93, 101, … the same way |
| 14 | see below |
| 15 | see below |
| 16 | scroll up: the shown picture moves up 8 rows at a time and the new one comes in from the bottom (see below) |
| 17 | scroll down: the same downwards, the new picture coming in from the top |

Exact orders, as integer procedures (rows `x`, columns `y`; all variables
are bytes unless said otherwise):

**Fade 8 / 13** (`step` 1 / 2, delay 30 / 45): `up = dn = x = 96`; loop:
copy row x; `D(delay)`; if `x ≥ 96`: `up = (up − step) & 255`, `x = up`,
and if `x < 128` loop again; `dn = dn + step`, `x = dn`; if `x < 192` loop
again. Fade 8 ends there. Fade 13: if `x = 192`, set `up = 97`, `dn = 95`,
`x = 95` and loop again (rows 95, 97, … — written as the same procedure
continuing with these values); otherwise it ends.

**Fade 10**: `f7 = 186, f6 = 0, f5 = 39, fa = 0`; copy row 0 (columns 39…0).
Pass: `f9 = min(186 − f7, 95)`; `f8 = max(f7 + 5, 96)`; `x = f8`; loop:
band(x); `D(1)`; if `x ≥ 97`: `f9 = f9 + 1`, `x = f9`, loop; else
`f8 = f8 − 1`, `x = f8`; if `x < 96` the pass ends; if `x = f7`, `fa = 1`;
loop. After a pass: `f7 = (f7 − 5) & 255`, `fa = 0`, `f6 = f6 + 1`,
`D((f6 × 4) & 255)`, `f5 = f5 − 1`; another pass while `f5 ≥ 20`.
band(x): if `fa`: copy (x, f5) then (x, f6); else copy (x, y) for y = f5
down to f6 (stopping below 0).

**Fade 11**: `f7 = 5, f6 = 19, f5 = 20, fa = 0`. Pass: `f9 = f8 = x = 96`;
loop: band(x); `D(2)`; if `x ≥ 96`: `f9 = (f9 − 1) & 255`, `x = f9`, if
`x < 128` loop; `f8 = f8 + 1`, `x = f8`; if `x − 96 < f7` loop; if `fa`:
`f7 = min(f7 + 5, 96)`, `fa = 0`, loop (with this same x); otherwise the
pass ends. After a pass: `fa = 1`, `f6 = f6 − 1`, `f5 = f5 + 1`; another
pass while `f5 < 40`.

**Fade 14**: `f7 = 191, f6 = 39`; loop: `x = f7`, `y = f6`; repeat: copy up
to six bytes of column y going up from row x (copy (x, y); stop if `x = 0`;
`x = x − 1`; at most 6 copies), then `y = y + 1`, until `y = 40`. Then
`f6 = f6 − 1`; while `f6 ≥ 0` loop; when it goes below 0, `f6 = 0`, and if
`f7 < 6` the fade ends, else `f7 = f7 − 6` and loop. No delay.

**Fade 15**: a checkerboard of strips 8 bytes wide, in two passes. A
*strip* (x, y) copies row x at columns y, y−1 … y−7, then y−16 … y−23, then
y−32 … y−39, stopping below column 0 (8 bytes copied, 8 skipped). Pass with
start column `y0` (39, then 31): for `g` = 0 to 31, for `k` = 0 to 5: strip
(g + 32k, y0 when k is even, y0 xor 56 when k is odd), then `D(25)`. After
each pass, `D(48)`. (Rows g, g+32, … g+160: the whole screen; the second
pass fills the squares the first one left.)

**Fades 16 and 17** move 8-row blocks. Copying block (a ← b, page) copies,
for column 39 down to 0, the 8 rows b … b+7 of `page` to rows a … a+7 of
the destination, row by row within each column. Fade 16: `first = 0`,
`step = 8`, `last = 184`, `end = 192`; fade 17: `first = 184`,
`step = −8`, `last = 0`, `end = −8` (byte arithmetic). `s = first`; pass:
`x = first`; repeat: block (x ← x + step, destination itself); `x = x +
step`; until `x = last`, with `D(20)` between blocks; then block
(x ← s, source); `s = s + step`; if `s = end` the fade ends, else `D(20)`
and another pass.

The editor's names for some fades: *center out*, *shrink in*, *split
sweep*, *split dissolve*, *checkerboard*.

## Sounds

Sound `t` plays effect `t mod 32`, then `−18` if 18 or more (so 0–17), on
the speaker. An effect is a list of steps:

- **tone** (`count`, `p`): `count` speaker toggles, each preceded by a wait
  of `p` delay steps;
- **silence** (`count`): `count` delay steps;
- **rough tone** (`count`): `count` toggles, each preceded by a random wait
  of 1–256 steps;
- **burst**: a random silence (1–256 delay steps, half of the time 512
  more), then a random odd number (1–31) of toggles, each preceded by a
  random wait of 1–256 steps.

A delay step is 12 cycles; a toggle with its wait of `p` steps takes
`12 p + 9` cycles. (The original takes its random numbers from memory; they
are not reproduced.)

| Sound | Steps |
| --- | --- |
| 0 click | tone 24 × 8; tone 24 × 6 |
| 1 pop | tone 10 × 11; tone 19 × 15; tone 5 × 23 |
| 2 footstep | tone 3 × 21; silence 3,457; tone 3 × 24 |
| 3 beep | tone 56 × 112; tone 3 × 21 |
| 4 double beep | tone 44 × 136; tone 32 × 168; tone 3 × 21 |
| 5 crash | tone 10 × 10; tone 19 × 14; burst; burst; silence 1; burst; silence 257; rough 6; silence 1; rough 5; silence 769; rough 4 |
| 6 explosion | tone 10 × 11; tone 20 × 15; burst ×3; silence 64; rough 10; silence 127; rough 9; silence 129; rough 8; silence 641; rough 7; silence 1,665; rough 6; silence 129; rough 5; silence 1,665; rough 3 |
| 7 ray gun | tone 96 × 32; tone 18 × 33; tone 16 × 36; tone 10 × 41; tone 3 × 160; tone 3 × 208 |
| 8 slide up | tone 16 × p for p = 192, 176, 160, 144, 128, 112, 96, 80, 64, 32 |
| 9 slide down | tone 16 × p for p = 32, 48, 64, 80, 96, 112, 128, 144, 160, 176, 192 |
| 10–17 scale | tone 36 × 168, 42 × 152, 48 × 136, 54 × 128, 60 × 112, 66 × 100, 72 × 90, 78 × 84 |

("tone `count` × `p`")

## Timing

Times are in cycles of the 1.02 MHz Apple II, as the original spends them.

**Delay** `D(a)`: `(5a² + 27a + 26) / 2` cycles (the monitor's WAIT
formula), `a = 0` counting as 256.

**Frame wait.** The projector counts a **cost** for each frame, from the
moment the previous frame was shown: the erase of step 5 that followed it
(the sum of the rectangle areas, or 3,430 for a full copy), the erase of
the planted rectangles, 2 × width × height of each snapshot's rectangle,
and 11 per shape byte of each text. After showing a frame it waits `n`
steps of 350 cycles, with 18 more cycles after every fourth step, where
`n = ceil((256 × speed − 4 × cost) / 64)` when that is positive and
`4 × cost < 65,536`, and 0 otherwise. Then the cost is reset. After the
first frame of a scene with a fade-in, there is no wait and no reset: the
cost goes on accumulating into the next frame.

The drawing itself takes time too: the original's time from one frame to
the next is this wait plus its erasing and drawing; a player whose erasing
and drawing take about the same time as the original's (copying a byte
about 20 cycles, a full page about 79,000; drawing a snapshot row about
140 cycles per code plus 55 per byte written plus 1,700 per snapshot; a
text about 280 cycles per shape byte) shows each frame for about the same
time. Measured against the original on 8,093 frames, that model of the
original's own time is within 1.6 % (median), 6.2 % (90 %) of it.

**`$FC` elements**, after the frame is shown and the wait done:

- pause: `t` times `D(141)` (about 51,600 cycles each; `t` = 0: no pause);
  Return or Escape ends it early, other keys are ignored;
- wait: until Return or a paddle button is pressed (other keys are
  ignored); Escape ends it too;
- sound: the effect plays to its end.

Fades take their delays and their copying time (about 16 cycles per byte
copied, as the original).

## Checks (A2 File Cmd)

The player refuses, with a message naming the file, anything it cannot
draw exactly as above:

- a movie whose length is not `1 + 42 n` with `n ≥ 1`, or a fade outside
  1–17;
- a missing file (the message names the DOS name);
- a background that does not decode exactly;
- a scene shorter than `$103` bytes, whose frames start outside it, whose
  strings or elements run past its end, that has no end marker, more than
  10 actors, a snapshot number above the sum of the counts, a string
  number of 0 or above `s`, a text element without a character set or
  outside the screen as described in Text;
- an actor whose snapshot offset, header or rows run past its end, or a
  snapshot number above its own count;
- a character set whose offsets or shapes run past its end;
- data that does not fit in the memory the player gives it.

## The player in A2 File Cmd (design)

**TAKE1.SYSTEM**, a ProDOS interpreter like FANTA.SYSTEM (header `JMP`,
`$EE $EE`, buffer length, path buffer at `$2006`), on the 800K and XL disks
next to FANTA.SYSTEM. A2 File Cmd launches it with the prefix set to its own
directory (where `A2FILE.SYSTEM` is, to come back) and one of three command
forms (46 characters at most):

- `/PATH/TO/IMAGE.DSK,TTSS` — the movie is a file of a DOS 3.3 disk image;
  `TT`, `SS` (hexadecimal) are the track and sector of its first
  track/sector list. The image is a `.DSK`/`.DO` file (DOS order, sector
  `(T, S)` at offset `(16 T + S) × 256`) or a `.2MG` in DOS order (the same
  from the offset at header bytes `$18`–`$1B`; byte `$0C` must be 0).
- `%UU,TTSS` — the movie is on a real DOS 3.3 disk in the drive whose
  ProDOS unit number is `UU` (hexadecimal); sector `(T, S)` is half of
  block `8 T + (H >> 1)`, the upper half when `H & 1`, where
  `H = [0, 14, 13, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1, 15][S]`, read
  with `READ_BLOCK`.
- `/PATH/TO/MV.NAME` — the movie is a ProDOS file (extracted by A2 File
  Cmd). Its files are looked for in the same directory under the ProDOS
  name A2 File Cmd gives a DOS name when it extracts it: the first 15
  characters of the DOS name, upper case, every character that is not a
  letter or a digit replaced by a period, and a first character that is not
  a letter replaced by `X`. That reduction is not one to one, and real disks
  hold names that collide: `BK.UNDERGROUND-1` to `-4` and
  `SN.ELEVATOR-DOWN-2`/`-3` (Sniper III data disk), `SN.HOPPY.WALK.ON1` to
  `ON3`, `AC.ANNUAL.PROFIT.1`/`.2` all become one ProDOS name each. Only one
  of them can be extracted beside the movie, and the player reads that one
  for all of them: such a movie plays the wrong scenes or backgrounds, or is
  refused. Nothing tells the files apart once extracted; a movie is only
  played faithfully from its DOS 3.3 disk or image, where files are found by
  their full names.

In a disk, files are found by name in the DOS 3.3 catalog (VTOC at track
17 sector 0: catalog track and sector at bytes 1, 2; each catalog sector
links to the next at bytes 1, 2 and holds seven 35-byte entries from byte
11: track and sector of the first T/S list, type, name in 30 characters with
bit 7 set, sector count; an entry starting `$FF` is deleted, `$00` ends the
catalog). A file's data are the sectors listed by its T/S lists (each list:
next list at bytes 1, 2, then up to 122 track/sector pairs from byte 12; a
pair 0, 0 is a hole of zeros), and a binary file starts with its address and
length. The number of sectors read is bounded (a file of more than 140 KB,
or a catalog or T/S chain longer than the disk, is damaged).

**Memory**: main memory only — auxiliary memory, and so `/RAM`, is not
touched. The three pages, the scene, its actors and character set (10.5 KB
at most in the movies seen) and the program fit below the ProDOS buffers.

**Original speed**: each frame stays shown for the time the original would
keep it: the modelled time of the original's own erase and draw (Timing:
the per-code, per-byte, per-snapshot, per-shape-byte, per-byte-erased and
full-page figures) plus its exact frame wait. The player estimates its own
cost for the same work (constants fitted on its own code) and waits the
difference, never less than nothing — as FANTA.SYSTEM does. A player that
only repeats the original's work and wait runs slower than the original
wherever its drawing costs more.

**Keys**: Escape returns to A2 File Cmd; Space pauses and resumes; Tab
switches between the original speed and the accelerated one (no frame
waits, no pauses, fades without delays); Return and the paddle buttons
answer a wait. Other keys are ignored. Ctrl-Reset returns to A2 File Cmd
too: the player sets the reset vector to its way back (A2 File Cmd's own
vector would point into the hi-res page the player draws on).

**The end**: the movie stays two seconds on its last frame and starts
again from the beginning, until Escape.

**Data safety**: read-only. The only MLI calls are OPEN, SET_MARK, READ,
CLOSE, READ_BLOCK and QUIT; nothing is written to any disk.
