# The Newsroom photos and banners (Springboard, 1984)

*The Newsroom* laid out a two-column newsletter from a banner, panels of
text and "photos" cut from its clip art. What its users made lives on their
own data disks, as ordinary DOS 3.3 files: nothing in RECOIL, CiderPress II
or the file-format wikis reads them. A2 File Cmd's NEWSROOM viewer shows the
two picture kinds.

| Prefix | Content | DOS 3.3 | Load address |
| --- | --- | --- | --- |
| `PH.` | A photo: a rectangle cut from the clip art and edited | B | `$4000` |
| `BN.` | A banner, the newsletter's heading | B | `$4000` |
| `PN.` | A text panel (not read yet) | B | `$4000` |
| `PG.` | A page layout (not read yet) | B | `$98A5` |

Copied to ProDOS (A2 File Cmd's `C` from a DOS 3.3 disk, CiderPress, ADTPro),
a photo or a banner becomes a BIN file (`$06`) with auxiliary type `$4000`.
That, with the `PH.`/`BN.` name, is how Return and I recognise it.

## Layout

After the four-byte B header (load address, length), the file is:

| Offset | Size | Meaning |
| --- | --- | --- |
| 0 | 2 | `L`, little-endian: the bitmap's length in bytes |
| 2 | 1 | `y1`, the frame's top row |
| 3 | 1 | `y2`, its bottom row |
| 4 | 1 | `x1`, its left dot |
| 5 | 1 | `x2`, its right dot |
| 6 | … | The clip history, ended by `$FF` |
| size − L | L | The bitmap |

The bitmap has `(x2 − x1) div 7 + 1` bytes a row and `y2 − y1 + 1` rows, so
`L` is their product. A byte holds seven dots, bit 0 on the left; 1 is white
paper, 0 is black ink; bit 7 is not used. That is exactly a hi-res screen
byte with its palette bit clear, the form the program itself draws.

The frame is the rectangle on the Newsroom's editing screen. Every banner of
the corpus is 245 × 80 dots (`x` 7–246, `y` 43–122); photos go from a single
row up to 231 × 168 dots (`x2` ≤ 237, `y2` ≤ 167).

## The clip history

Between the frame and the bitmap, the program keeps what the photo was made
of. What is understood, from the files:

- a count `n` of the clips pasted in;
- `n` bytes, a permutation of 0 … n − 1 (their stacking order);
- `n` rectangles of four bytes, `y1 y2 x1 x2` like the frame;
- `n` records of eight bytes, which clip of which sheet;
- in 84 of the 93 distinct files, sixteen more bytes: `$00`, the name
  `NEWSROOM` in high-bit ASCII, seven zeros;
- `$FF`.

**The trap.** A clip record can hold `$FF` itself (18 files of 93, among them
`PH.CATS`, `PH.GUEST`, `BN.LUMBER`). Reading the bitmap from the first `$FF`
shifts it and misreads those files. The bitmap is the **last `L` bytes** of
the file, and the byte just before them is the terminating `$FF`: that is
what A2 File Cmd checks, and it ignores the history otherwise.

## Checks

The viewer refuses a file, before drawing anything, unless:

- `y1 ≤ y2`, at most 192 rows, and `x1 ≤ x2` (a row is then 37 bytes at most);
- `L = width × height`;
- the file is under 64 KB and holds at least the frame, the history's count
  byte, the `$FF` and the bitmap;
- the byte before the bitmap is `$FF`;
- the file ends exactly after the bitmap (the directory's size is the
  file's), and no read or close fails.

## How this was established

The starting points were Ferg Brand's `NRTOGP`/`NRTONR` converters (1986,
on the archive.org disks `a2_Ferg_Brand_*`), which move pictures between The
Newsroom and other programs, and [newswire](https://github.com/classilla/newswire),
which reads the Commodore 64 edition (eight dots a byte, most significant bit
on the left). The layout above, the end-anchored bitmap in particular, was
then settled on real files: decoded pictures show whole, unsheared images.

The corpus is 125 `PH.`/`BN.` files (93 distinct: 76 photos, 17 banners) on
eleven archive.org data disks — church and school newsletters, clip-art
collections: `703_Newsroom_Page`, `103_`…`106_`, `105_The_Newsroom_Photo_Data_Disk`,
`169_Page_Data_Disk_The_Newsroom`, `a2_Newsroom_Banner_Datadisk_198x_`,
`009_`/`010_Clipart_*_For_NewsRoom` and others. All 125 satisfy every check
above. They are not redistributed here.

## In A2 File Cmd

`tools/newsroom_ref.py` is the reference: the checks, the page the viewer
draws, a generator of synthetic pictures, and a reader of the DOS 3.3 disks
(`--png OUTDIR DISK...` writes the pictures out). The NEWSROOM overlay
(`src/plugins/newsroom.s`) centres the picture on a black hi-res page, in
the main bank only: it writes neither the disk nor the auxiliary memory, so
`/RAM` is untouched. Left and Right go to the neighbouring Newsroom picture
of the directory. `tools/test_newsroom.py` runs the whole overlay under
sim65 on both processors, against the reference: synthetic pictures,
malformed ones, stale sizes, read, error-flag and close failures, and the
real disks when they are in `~/.cache/a2fc/newsroom`.

Not yet: the text panels `PN.*` and page layouts `PG.*`, and the commercial
clip-art disks, whose sheets are packed (index on track 34, "SSI CLIP").
