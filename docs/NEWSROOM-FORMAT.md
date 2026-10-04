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

## Commercial clip-art disks

Springboard's clip art — the disk that came with The Newsroom and the Clip
Art Collections 1 to 3, two sides each — is not stored as files. Each side
is a 35-track DOS 3.3-sized disk with a token VTOC (track 17 sector 0) whose
catalog (track 17 sector 1) holds a short notice, and the rest of the disk
is Springboard's own layout, read by sector (DOS 3.3 logical sector order):

| Where | Content |
| --- | --- |
| Track 0 sector 0 | a boot sector that prints "THIS IS A NON BOOTING DATA DISK" |
| Track 0 sector 1 … track 33 | the pieces, packed one after the other; track 17 sectors 0 and 1 are skipped |
| Track 34 sectors 0–1 | the index: `SSI CLIP`, `$00`, the disk's name, `$00` (bit 7 set on every character); byte `$1A` the side number; byte `$1B` the number of pages `n`; from `$1C`, `n` page names, each ended by `$00` |
| Track 34 sectors 6–15 | the location table |

**Location table.** From byte 0 of sector 6: for each page in index order,
its pieces as three bytes each — track, sector, offset in the sector of the
piece's first byte — then `$FF` before the next page. A page has 1 to 17
pieces. (Past the last page the sectors hold left-overs.)

**A piece** is a rectangle of the page: four bytes, top row `y1`, bottom
row `y2`, left dot `x1`, right dot `x2` (a page is 252 dots × 192 rows,
`x2` ≤ 251, `y2` ≤ 191), then its bitmap. The bitmap is stored in vertical
strips seven dots wide: strip `c` covers dots `x1 + 7c` to `x1 + 7c + 6`
(cut at `x2`), there are `ceil((x2 − x1 + 1) / 7)` strips, and each strip
gives one byte per row from `y1` to `y2`. A byte's bit 0 is the strip's
leftmost dot, 1 white, bit 7 unused (`$80` stands for an empty byte, since
`$00` is reserved). The strips, one after the other, form one stream of
`(y2 − y1 + 1) × strips` bytes, compressed: `$00 n v` is `n` copies of `v`
(`n` ≥ 4 on these disks; a run may continue into the next strip), any
other byte is itself. How The Newsroom combines pieces that overlap is not
established; A2 File Cmd draws a page's pieces in table order, each one's
white dots added to the page (the pieces seen hardly overlap).

The pieces are read across sector and track boundaries; a piece that ends
exactly at the end of a sector may leave the next sector unused (the next
piece then starts at offset 0 of the sector after).

Established on 8 distinct sides (The Newsroom's disk, Collections 1–3),
393 pages: every piece of seven sides decodes exactly from its table entry
to the next one (2,335 of 2,339 pieces on the copies at hand; the four others
come from a damaged copy, and two pages of Collection 3 side A are damaged
on the only copy found). The layout was first suggested by Unison World's
*Art Gallery to Newsroom Clip Art Conversion Program* (1988, on its *American
History Art Gallery* disks), which writes such disks: its encoder shows the
piece header, the seven-dot strips and the runs of four or more; the
details above were then checked on Springboard's own disks. Unison's
converter sets bit 7 on every data byte.

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

The NRCLIP overlay (`!` menu, Images; `src/plugins/nrclip.s`) recovers the
pages of a commercial clip-art disk shown in the active panel — a DOS-order
file image (`.DSK`, `.DO`, a `.2MG` of format 0 and 143,360 bytes) or a real
floppy, read by `READ_BLOCK` — into the ProDOS directory of the other panel.
It checks the index and the whole location table first (`clip_index`,
`clip_table`), and refuses the disk if either fails. Then, for each page in
index order, it draws the page on hi-res page 1, which the screen shows as it
is built, exactly as `clip_page` does, and saves those 8,192 bytes as a BIN
file of auxiliary type `$2000`, named from the page name the way the core
names DOS 3.3 files (letters and digits upper case, anything else a period,
15 characters, an `X` for a first character that is not a letter). The file
is created exclusively: a name already there is counted and skipped; a page
`clip_piece` refuses is counted as damaged and gets no file; a failed write
or close removes the file just created and stops; a read error stops;
Escape stops between pages. The message line gives the three counts. The
disk is only read, the auxiliary memory is not used. Its code runs partly
from `$0C00`, the ProDOS buffer of a second open file, so it never keeps
two files open: the image is closed before each page is saved and reopened
for the next. `tools/test_nrclip.py` runs the whole overlay under sim65 on
both processors, every file and disk service answered by the test: synthetic
disks in each form, the 12 real disk images at hand (391 of the 393 distinct
pages saved, the two damaged pages of Collection 3 side A refused), and
failed reads, seeks, creations, writes, closes and removals, a full disk,
existing names, Escape, missing or damaged indexes and wrong panels.
`bench/nrclip.py` runs it in the real program under POM2, on both
editions: a real clip-art disk image opened from the hard disk, then another
in drive 2 of the Disk II, every page read back from the destination volume.

Not yet: the text panels `PN.*` and page layouts `PG.*`.
