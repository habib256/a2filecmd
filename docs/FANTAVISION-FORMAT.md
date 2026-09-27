# Fantavision movies (Brøderbund, 1985)

*Fantavision* animates up to eight polygon, line or dot objects between key
frames: the user draws the key frames, the program computes the frames in
between ("tweening"). Its movies are ordinary ProDOS files. This document
describes the file and what a viewer of it shows, as observed; it is the
only input of A2 File Cmd's player, which is written from it and from
nothing else (the original player is not free software, and none of its
code or tables is used).

The facts below were established on 144 movies — the demonstration movies
of Fantavision 1 and 2 and users' movies — and checked frame by frame
against the original player running under emulation. Those study tools are
private and are not part of this repository.

## The file

| | |
| --- | --- |
| Name | `M.` followed by the title, e.g. `M.APPLE` |
| ProDOS type | BIN (`$06`), auxiliary type `$8400` (Fantavision loads it there) |
| Size | 513 to 9,216 bytes |

Offsets below are from the start of the file.

### Header, `$000`–`$19F` (416 bytes)

| Offset | Meaning |
| --- | --- |
| 0 | Speed. Its low three bits `e` give the number of steps `S` from one key frame to the next: `S = 2^(e−1)` for `e` = 1…7 (1, 2, 4 … 64), and `S = 8` for `e = 0`. The other bits are not used. |
| 1 | Low nibble: how many times the movie plays. The whole byte 0 means "loop forever". |
| 2 | A frame count kept by the editor; the player does not use it. |
| 3 | Always 4. |
| 4 | Background colour: high nibble for even rows, low nibble for odd rows (see Colours). |
| 5 | Always 8. |
| 6–7 | Not used by the player. |
| 8 | Clip window, left, in movie x. |
| 9 | Clip window, right, in movie x. |
| 10 | Clip window, top row. |
| 11 | Clip window, bottom row. |
| 12–415 | Not used by the player. |

Every movie seen has the clip window within x 5–250, rows 12–159.

### Frames, from `$1A0`

A frame is exactly eight object records, for objects 0 to 7, one after the
other. A record starts with its length `L` in bytes, the length byte
included:

- `L = 1`: the object is absent from this frame;
- `L = 0` where a frame would start: the end of the movie;
- otherwise `L = 4 + 2n`, for an object of `n` points (0 ≤ n ≤ 32):

| Offset in the record | Meaning |
| --- | --- |
| 0 | `L` |
| 1 | Attributes: bits 0–1 the kind, bits 4–7 its mode (bits 2–3 unused) |
| 2 | Colour: high nibble even rows, low nibble odd rows |
| 3 | Animation: 0 normal, 1 trace, 2 background, 3 lightning |
| 4 … 3+n | The `n` x coordinates, 0–255 |
| 4+n … 3+2n | The `n` y coordinates (rows), 0–255 |

A movie holds 1 to 127 frames. Object `k` of one frame and object `k` of
the next are the same object: that is what is tweened.

## What the objects are

**Kinds** (attribute bits 0–1):

| Kind | Object | Mode (bits 4–7) |
| --- | --- | --- |
| 0 | Dots: a round spot at each point | the dot size, 1 (smallest) to 9 (largest); 0 and 10–15 draw nothing |
| 1 | Lines joining the points in order | 10: open (the last point is not joined back to the first); 11: closed; 1–9: dashed, `m` segments drawn then one left blank, in order from the first; 0 and 12–15: open |
| 2, 3 | A solid shape, the polygon of the points, filled | 0: no outline; 1: black outline, closed; 2: white outline, closed; 3: black outline, last segment open; 4: white outline, last segment open; 5–15: as 1–4 by the same rule (odd black, even white, 3 and more open) |

An outline is drawn after its fill, in black or white of the same palette
as the fill (see Colours). Two consecutive equal points count once in a
solid shape; a shape reduced to one point is a single smallest dot. A line
object of one point, or a segment whose ends coincide, is a smallest dot.

Lines are drawn thick enough to keep their colour: about two dots wide. A
dot of size `s` is a round spot about `2s` dots wide and `2s` rows tall,
centred on its point. A self-intersecting shape is filled with the
even-odd rule.

**Animation** (record byte 3), as the manual names the modes:

- 0 **Normal**: each new version of the object replaces the previous one,
  which is erased;
- 1 **Trace**: the object is never erased; every version stays on screen;
- 2 **Background**: the object becomes part of the background: drawn once
  into it and never erased (the manual asks for the object to be absent
  from the frames on either side);
- 3 **Lightning**: never erased either, but drawn only on the page being
  built; with the two pages alternating, the trail flickers.

Values above 3 behave as 3. Objects are drawn in order, 0 to 7: a later
object covers an earlier one.

## The screen

Hi-res, full screen, page 1 and page 2 alternating: a frame is built on the
hidden page and then shown, so no frame is seen half drawn.

- Movie x 0–255 is screen x 14–269; rows are screen rows, and only 0–191
  are on screen.
- Nothing is drawn outside the clip window (header bytes 8–11).
- The background, when no backdrop picture is loaded, is black, with the
  rectangle movie x 5–250, rows 12–159 filled in the background colour
  (header byte 4). Fantavision could also load a separate hi-res picture as
  a backdrop (BIN `$4000`); a movie does not name it, and A2 File Cmd's
  player does not load one.
- Erasing an object restores the background under it.

### Colours

A colour nibble 0–15 names a pattern of two bytes: the one written at an
even screen byte column and the one at an odd column. The same nibble with
bit 3 set is the other hi-res palette (bit 7 of every byte set).

| Nibble | Even byte | Odd byte | Seen as |
| --- | --- | --- | --- |
| 0 | `$00` | `$00` | black |
| 1 | `$55` | `$2A` | violet |
| 2 | `$2A` | `$55` | green |
| 3 | `$7F` | `$7F` | white |
| 4 | `$36` | `$36` | a mixed pattern |
| 5 | `$49` | `$49` | a mixed pattern |
| 6 | `$2D` | `$2B` | a mixed pattern |
| 7 | `$56` | `$55` | a mixed pattern |
| 8–15 | as 0–7, OR `$80` | as 0–7, OR `$80` | black, blue, orange, white, mixes |

Even rows use the colour byte's high nibble, odd rows its low nibble: two
different nibbles give a striped mix. Only the dots an object covers take
the pattern; the others of the byte keep what was there.

## Playing

1. Build the background; show the first key frame (frame 0).
2. For each next frame `k+1` (wrapping from the last frame to frame 0):
   move every object from key `k` to key `k+1` in `S` steps — `S − 1`
   in-between frames, then key `k+1` itself, exactly as stored. With `S = 1`
   the keys follow one another.
3. At each step an object's points move in a straight line from their
   position in key `k` towards key `k+1`, the same fraction of the way for
   every point: after `t` steps, `P = Pk + (Pk+1 − Pk) · t / S`, rounded.
4. Different point counts: when key `k+1` has more points, the existing
   points are shared out evenly so that there are as many (some start on
   the same spot and separate); when it has fewer, several points of key
   `k` travel to the same point of key `k+1`. Either way the object is a
   whole polygon at every step.
5. An object absent from key `k+1` disappears when the transition starts.
   An object absent from key `k` appears at key `k+1`.
6. Play count (header byte 1): with a count `c`, the movie plays through
   `c` times and stops on its last frame, without the wrap to frame 0. With
   byte 1 zero it loops until stopped. A movie of a single frame is just
   shown.

There is no fixed frame rate: the original runs each step as fast as it
can draw it, so a movie of big solid shapes plays more slowly than one of
dots. The speed byte sets how many steps, not how long they last.

### How long the original takes

Timed on the original player under emulation (6,787 frames of ten movies,
from dots to full-screen solids), the time between two frames shown is
well predicted, in 1 MHz cycles, by the work the frame does:

    cycles ≈ 6,300
           + 230 per row segment drawn   + 20 per byte those segments cover
           + 270 per row segment erased  + 45 per byte those cover
           + 1,100 per edge whose slope is worked out

- a *row segment* is one horizontal run of one object on one row (a dot of
  size 3 is 6 of them, a filled shape one or more per row it spans, a line
  about one per row it crosses); its *bytes* are the screen byte columns it
  touches, after clipping;
- *erased* segments are those of the normal-mode objects of the previous
  frame shown, whose shape the original goes over again to put the
  background back;
- an *edge* is a segment between two consecutive points of a line or solid
  object (n edges for n points), counted for every such object drawn.

The median error is 10 % (90 % of frames within 20 %): from about 10,000
cycles a frame for a movie of small dots to 240,000 for large solids,
roughly 100 down to 4 frames a second.

## Checks (A2 File Cmd)

The player refuses a file, before anything is shown, unless:

- it is 513 to 9,216 bytes, header byte 3 is 4 and byte 5 is 8;
- the clip window has left ≤ right and top ≤ bottom;
- from `$1A0` there is at least one whole frame: eight records, each of
  length 1 or `4 + 2n` with n ≤ 32, all within the file.

**A damaged tail is cut, not refused.** The movie ends at the first frame
that is not whole: a 0 where a record should be, a record length that is
odd, below 4 or above 68, a record running past the end of the file, or the
end of the file inside a frame. The frames before it play; the original
does the same with a 0 inside a frame (it shows only the frames before).
Three of 144 real movies need this: one has a 0 inside its second frame,
one ends in a corrupt record after 40 good frames (a save cut at 9,216
bytes), one has a 68-point object in its tenth frame. A movie is refused
only when not even its first frame is whole, or it has more than 127
frames.

Anything else in a record (unused bits, unexpected modes, animation values
above 3) is played with the meanings above, never refused and never allowed
to leave the object's own buffers: a damaged movie must not hang the
machine.

## The player in A2 File Cmd (design)

The original player needs two hi-res pages and a background buffer: more
than an overlay window. A2 File Cmd therefore launches a separate program,
`FANTA.SYSTEM`, as it launches BASIC.SYSTEM: a ProDOS interpreter (the
startup-path convention: `JMP`, `$EE $EE`, buffer length, path) given the
movie's path.

- Main memory only: pages 1 and 2 ($2000–$5FFF), the background copy, the
  movie (≤ 9 KB) and the engine above; no auxiliary memory, so `/RAM` is
  untouched. Nothing is ever written to a disk.
- Keys: Escape stops and returns, Space pauses and resumes. The end of a
  counted movie waits for a key.
- Accelerated: the original spends 11,000 to 128,000 cycles a frame, most
  of it redrawing and erasing whole shapes. This player aims to be clearly
  faster on the same 1 MHz machine: erase only the rows and byte columns
  an object covered (its bounding box, restored from the background copy),
  fill spans a byte at a time from tables (row addresses, edge masks,
  colour bytes), a scan-line fill with an active edge list, and 8.8
  fixed-point steps added, never recomputed.
- Two speeds, switched by Tab while playing: **accelerated** (the default,
  as fast as this player draws; the digits 1–9 add a delay per frame, 0
  removes it) and **original**, where each frame is held until the time the
  original would have taken for it has passed, by the formula of "How long
  the original takes" computed on the frame's own segments and edges. The
  player knows its own cost per frame (the same kind of count, calibrated
  on itself) and waits for the difference; a frame it cannot draw faster
  than the original is simply not delayed.
- Return to A2 File Cmd by loading `A2FILE.SYSTEM` again.
- An invalid movie is refused with a message, then the same return.
