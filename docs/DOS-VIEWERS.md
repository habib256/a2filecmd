# Direct DOS 3.3 viewers

DOSVIEW is shipped in the complete ProDOS editions (800K and both XLs). It
reads real DOS 3.3 drives through ProDOS READ_BLOCK and also reads
DOS-order DSK/DO and DOS-order 2IMG files. It creates no temporary file.
This does not change the standalone 48K DOS edition.

## Commands

Select a file in a DOS panel and use T for text or H for hex. I and Return
run IDENT and open its detected reader: DOSBAS for Applesoft, DOSINT for
Integer BASIC, SCASM for S-C sources, DOSMCS for Music Construction Set,
DOSNEWS for Newsroom photos/banners, NEWSPAN for PN. panels and NEWSPAGE
for PG. layouts, PRINTSHOP for 572/576-byte clip art and FONTRIX for font
glyphs. DOS HRCG BIN fonts named `.SET`/`.FONT` (768 or 1,024 bytes) use
FONTVIEW's raw renderer through DOSFONT, on 800K and XL. Print Shop BIN borders/fonts use PSBORDER/PSFONT. These readers
validate and close their sources before display, without AUX or disk writes.
PRINTSHOP and FONTRIX are on 800K and XL; PSBORDER/PSFONT are on XL. Other files use DOSVIEW's text/hex/raw-picture modes.
ProDOS uses the same detection and its own readers. Epistole and Extasie
are ProDOS formats; they do not select a DOS document/image reader.
DOS Merlin/ED-ASM TXT sources named `.S`/`.ASM` use MERLIN on 800K/XL
through Return/I or the Programming menu, retaining aligned columns,
quoted strings and comments. Other names can use the menu explicitly.
Original LISA v2 alternate-B sources with the `$1800` editor header use
LISAV2 through Return/I or the Programming menu on 800K/XL. Their DOS
catalog kind is `$40`; the panel presents them as typeless, not BIN.
HRCG, Merlin and Magic Window suffix detection also uses the complete
30-byte DOS catalog name retained by IDREAD, so a suffix hidden by panel
truncation still selects the existing reader. Matching ignores trailing
space padding and ASCII case. Concrete content formats keep priority.
The ! menu also offers DOSVIEW with a T/H/I choice.
Space/Return/Down pages forward; B/Up pages back; R returns to the first
page; Escape returns to the panels.

The other foreign-filesystem guards still refuse editing, execution and
destructive commands. ProDOS image panels retain their previous guard;
this step adds direct readers only for DOS 3.3 panels.

## Data and memory

Only MAIN overlay/BSS and visible screen bytes are written. Disk calls
are READ_BLOCK, image files are opened rb, AUX storage is untouched and
/RAM is not rebuilt. The 64 live screen holes are excluded from lo-res
copying. Image data is fully read and the source closed before display.
HGR is loaded into MAIN page 1 ($2000-$3FFF). The 8184-byte variant has
its eight omitted trailing holes cleared. The C driver first validates
the sector map; a small assembly handoff below $2000 then reads the page,
closes the image file and displays it. It uses only resident API callbacks
and its own argument helpers after graphics data has overwritten the
larger C driver. A linker assertion protects all handoff code and state.
Failed reads or closes return to the panels without showing a partial page.

The fresh catalog must match the selected T/S identity, normalized name
and file type. Cyclic/aliased selected chains, malformed pointers and
offsets, invalid combined type bits, and header lengths beyond allocation are
refused. I/O errors are sticky and never become ordinary EOF. Panel sizes
do not bound reads. This is not a complete volume consistency audit or a
snapshot of a source that changes during reading.

Scope: standard 35-track, 16-sector DOS 3.3, TXT/BIN/INT/BAS and raw S/R/alternate A/B types, with up to 560
logical sectors. BIN/BASIC prefixes supply exact EOF and are omitted from
the logical stream. TXT has no byte EOF: allocated padding and zero-filled
sparse holes remain visible. Text masks the high bit; hex preserves bytes.
Compressed pictures, DHGR and other formats are subsequent steps. Text pagination keeps up to 80 page positions.

| CPU | DOSVIEW file | BSS | Occupied below $4000 | Free |
| --- | ---: | ---: | ---: | ---: |
| 6502 | 7530 | 1884 | 9414 | 58 |
| 65C02 | 7521 | 1884 | 9405 | 67 |

Catalog/T-S scanning storage is reused for the 80 text-page positions
after validation, and for the five lo-res sector pointers when needed.
The HGR handoff ends at $1DFC on both CPUs, leaving 516 bytes before $2000.

The current resident reserves are 9/397 MAIN, 3/1 LC and 84/109 LOWRAM
bytes (65C02/6502). All linker and stack checks remain enabled. The old
compact BOOT disk is a private regression fixture; the ProDOS 140K edition
has been withdrawn from builds, download inventories and v0.9.6.

## Reproduce

```sh
make ARCH=6502 all disk
make ARCH=enh all disk
python3 tools/test_fs_keys.py
python3 tools/test_dos_stream.py
python3 tools/test_dos_hgr.py
POM2=/tmp/a2fc-pt3-trace A2FC_BUILD=build-6502 A2FC_PRESET=iie_unenh python3 bench/dosview.py
POM2=/tmp/a2fc-pt3-trace A2FC_BUILD=build A2FC_PRESET=iie python3 bench/dosview.py
python3 tools/check_images.py
```

The command gate is executed under sim65 for all 256 keys, both panels
and both CPUs. Stream tests execute production C on host and sim65,
including malformed data, stale metadata and open/read/seek/close errors.
The native HGR handoff also runs in a 6502 interpreter on both linked
builds: exact page bytes, holes, every sector read/seek failure, FILE error
flags, close failures, software/hardware stack balance and no execution
from graphics memory after loading starts are checked.
POM2 runs the native Disk II driver on a disposable write-protected disk
and the DOS image path; complete source and boot-volume bytes, AUX storage
and the C-stack floor are compared after use. A physical Apple II and
drive still need qualification.

DOSMCS now shares this read-only source/stream implementation for direct
2304-byte Music Construction Set exports and main/`.OBJ` editor pairs, through ! → Music → DOSMCS
on 800K/XL. See [MCS format](MCS-FORMAT.md) for its allocation and memory
limits. The paired importer uses full DOS catalog names and validates both files
before sound; internal MCSIMPORT/MCSPLAY stages fit without AUX.

Next: share the stream contract with more readers, add
compressed/DHGR pictures and ProDOS-image allocation trees, then
neighbour files, slideshows and the remaining audio formats. AUX consumers must preserve the
existing confirmation before destroying occupied /RAM storage.
WOZ and Pinball remain excluded.

## Direct Integer BASIC

Select a DOS Integer BASIC file (catalog type I, shown as `$FA`) and use
**! → Programming → DOSINT**, included in 800K/XL. The existing Integer
BASIC decoder reads the validated stream directly on real READ_BLOCK
units or DOS-order DSK/DO/2IMG images. It does not execute BASIC or create
an extracted file. Space advances, B returns, R restarts and Escape exits.
The paging ring retains the last 64 pages. T/Return still use DOSVIEW;
DOSINT is an explicit menu reader.

The fresh two-byte DOS prefix gives exact EOF, up to 65535 payload bytes.
Its allocation may contain at most 257 logical sectors; larger chains are
refused. Records must have their final `$01` at the declared end, strings
must close and constants must fit. Read/seek errors remain errors on
subsequent pages and require reopening; source close errors are reported.
A line expanding beyond an entire 22-row screen is explicitly refused
as too long rather than reported as a complete listing.

Only MAIN overlay/BSS, the shared copy buffer and text screen are written.
Retired metadata holds the page-position ring. Regression tests execute
production C on both CPUs, including the 65535-byte EOF across the sector
boundary, all source faults, paging, malformed records and byte-preserved
inputs. `bench/dosint.py` exercises protected disposable Disk II media,
DSK and 2IMG, source-volume/AUX preservation and the C-stack floor.

## Direct Applesoft BASIC

Select a DOS Applesoft file (catalog type A, shown as `$FC`) and use
**! → Programming → DOSBAS**, included in 800K/XL. It shares DOSINT's
read-only source, validated allocation and 64-page pagination. It expands
all 107 Applesoft tokens, preserving literal strings, DATA and REM; DATA
ends at a colon outside quotes. An unclosed quote ends at EOL.

Only conventional programs linked from `$0801` are accepted. Each stored
next-line pointer must match the next record's file offset plus `$0801`;
records are read sequentially, never executed or addressed through those
pointers. The final zero pointer must coincide with exact DOS EOF. Unknown
tokens, malformed links, truncation and lines exceeding one screen page
are reported. The highest next-line address limits this layout to 63488
payload bytes including the final two-byte zero pointer; relocated programs
are refused. T/Return remain DOSVIEW; DOSBAS is an explicit menu reader.

`tools/test_dosbas.py` executes production C on both CPUs, with all source
backends, injected I/O failures, literal contexts, paging and invalid data.
`bench/dosbas.py` exercises protected disposable Disk II media, DSK and
2IMG, checking full source-volume/AUX conservation and the C-stack floor.
Physical hardware qualification remains pending.

## S-C Assembler sources

**! → Programming → SCASM** now reads S-C Assembler sources saved as DOS
Integer BASIC (type I/$FA) directly on Disk II and DOS-order images. These
files are attested in the original S-C Macro Assembler IIe disk corpus.
Length-prefixed lines, line numbers, compressed spaces and character runs
are decoded by the existing SCASM reader. A complete validation pass and
successful close precede display; the second pass reopens and revalidates
the source. Space advances and Escape cancels. No extraction or AUX.

The DOS prefix supplies exact EOF, up to 65535 bytes, with at most 257
logical sectors. `tools/test_dosscasm.py` checks both CPUs, original DOS
sources, maximum EOF, malformed records and failures in either pass;
`bench/dosscasm.py` checks protected disposable Disk II/DSK/2IMG media,
full source-volume/AUX preservation and the stack floor.

DOS reader eligibility requires evidence that the format exists on DOS
3.3. Epistole and Extasie remain ProDOS formats and must never be launched
as DOS viewers. Recognition of a format does not establish that a reader
can safely consume that filesystem's stream.

## IDENT and Newsroom

IDENT, IDREAD and IDFORMATS form a private relay. The source closes before
a stage is opened, and the stage closes before it is entered. Sealed length,
EOF, I/O/close status, CPU tag and entry bounds are checked in native code.
The returned loader occupies $0C00-$0DFF; the 512-byte sample is preserved
at $0E00-$0FFF. These borrow the second ProDOS FILE buffer: directory
services are closed and only one FILE (buffer $0800) remains open. No AUX.
ProDOS identification reads to actual EOF instead of trusting a stale panel
size. DOS validates the selected allocation and uses its exact BIN/BASIC
length; raw DOS types retain their allocation padding. Content/suffix rules
can be candidates: the actual reader still validates its format. An unknown
or ambiguous file retains a generic reader; not every arbitrary binary can
be identified uniquely. Legacy OPEN still classifies media neighbours.
Missing IDENT can fall back to OPEN/DOSVIEW for partial installations and
historical BOOT fixtures; a reported source/stage error prevents that retry.

DOSNEWS validates PH./BN. headers, the end-anchored bitmap and every source
byte before handing off to code/state below $2000. The second read and
successful close precede display. It centres the exact seven-dot bitmap on
HGR page 1, with no AUX or neighbouring-file lookup.

NEWSPAN recovers PN. text, masks the original style/high bit, skips the
$7F/$FF text sentinel and lists embedded PH. references. NEWSPAGE decodes the
four letter/legal layouts, with/without banner, the page name and component
slots in their stored order. Both perform a complete structural pass and
successful close before a second pass displays paginated text. ESC cancels.
These are text/structure decoders: original fonts, placed photos and a fully
assembled newspaper page are not rendered. Size codes are exposed as stored;
their rendering semantics are not guessed. See NEWSROOM-FORMAT.md.

`tools/test_newsdoc.py` runs production C on host and both CPU targets,
including every truncation, I/O failures, stale sizes, maximum text and the
78 PN./22 PG. originals available locally. `tools/test_dos_news.py` compares
actual native pixels and all read/seek/close faults on both CPUs. The native
`bench/newsdoc.py` covers ProDOS copies, protected Disk II, DSK and 2IMG,
automatic Return/I routing, AUX, stack and whole-volume byte conservation.
Physical hardware remains unqualified.


## Print Shop and Fontrix direct-reader qualification (12 October 2026)

The existing PRINTSHOP and FONTRIX overlays now read both ProDOS files and
DOS BIN streams. PRINTSHOP buffers the complete 572-byte bitmap and accepts
only a 572- or 576-byte logical payload; it closes the source before HGR.
Its assembly renderer, bitmap and live state occupy `$1B3C-$1EE9`, below
the graphics page. The C preflight returns before that page overwrites its
code. The resident `media_wait` callback preserves ProDOS album arrows and
slideshow behavior. Both readers preserve the selected filename on return.
FONTRIX validates every glyph pointer against the actual logical EOF,
including on DOS, then reads and closes each glyph before displaying it.
Neither reader writes files, raw disk blocks or AUX; neither rebuilds `/RAM`.

`tools/test_direct_readers.py` passes five tests: production IDENT routing,
real reader C on physical READ_BLOCK/DSK/2IMG backends, stale panel sizes,
malformed lengths/pointers/catalog identity, injected read/open/seek/close
errors, cc65/sim65 on both CPUs and the assembled HGR handoff against a
complete independent 8 KiB pixel oracle. Input images are byte-compared.
Existing Print Shop, Fontrix, media, routing and distribution regressions pass.

`bench/direct_readers.py --6502` (unenhanced IIe) and `--enh` pass 18/18
checks each in POM2, using disposable volumes: Return/I, exact rendered
pixels, ProDOS album navigation, glyph navigation, selection restored,
unchanged AUX, stack floor and complete source disks. This is emulator
qualification, not a physical-hardware run.

Both distributions build with their original layout checks. The four images
pass `tools/check_images.py`; 800K includes FONTRIX and retains 246 free
blocks. Global `make test` stops at `test_sign_compare.py` on 21 existing
unannotated findings in other source files; none concerns these changes.


## HRCG follow-up qualification (12 October 2026)

IDENT now routes DOS BIN `.SET`/`.FONT` files of 768 or 1,024 bytes to
DOSFONT. This adapter uses FONTVIEW's shared glyph and screen assembly;
ProDOS MGTK handling remains in FONTVIEW. Automatic selection still uses
both the filename and logical size; manual DOSFONT selection requires a
DOS BIN and validates its actual logical EOF. Arbitrary bytes of the two
supported lengths are raw glyphs, not a signature-authenticated font.

The complete DOS source is read and closed before copying the first 512
bytes into the resident `copy_buf` and the remainder into protected HGRSAFE
storage. Sector I/O uses `copy_buf` only before that transfer. The renderer,
live state and trailing font bytes occupy `$1B3C-$1E6C` on both CPUs and
are linker-asserted below HGR. The C driver has returned before HGR overwrites
its window. No source files, disk blocks, AUX or `/RAM` are written.

`tools/test_dosfont.py` passes six tests: exact source bytes and split-buffer
contents on READ_BLOCK/DSK/2IMG, stale sizes, every read fault and image
open/seek/close faults, malformed EOF/catalog/sector aliases, actual C under
cc65/sim65 on both CPUs, and the assembled handoff's whole 8 KiB page and
stack against the existing independent FONTVIEW oracle. All 48 distinct
saved DOS HRCG fonts available in the local corpus pass the real C reader;
SHA-1 and length are checked against the corpus index, source images remain
byte-identical. Missing optional local corpus data is reported as a skip.

`bench/direct_readers.py --6502` and `--enh` pass 30/30 checks each in POM2:
the two HRCG sizes through Return/I on ProDOS, DOS-order images and real DOS
drives, plus the existing Print Shop/Fontrix, album, selection, AUX, stack and
whole-source-disk controls. These are emulator checks, not a hardware run.

FONTVIEW now also refuses an initial close error before reopening a raw font.
`tools/test_fontview.py` passes four native tests on both CPUs, including
that new refusal and unchanged source bytes. Existing MGTK and HRCG pages
still match their complete render oracles.

Both builds and the four distribution images validate without relaxing any
memory limit. DOSFONT ships on 800K/XL; 800K now retains 232 free blocks.
The signed-arithmetic check still reports the same 21 pre-existing findings
in other files; the newly added C adapter introduces none.

## Merlin follow-up qualification (12 October 2026)

MERLIN now reuses the existing read-only DOS stream in `retrotext.h`.
Automatic detection requires DOS TXT, a `.S`/`.ASM` name and a high-bit
first byte; the full decoder then validates the source. Other names can
use the existing Programming menu. ProDOS decoding keeps its earlier
rules. The DOS stream supports up to 257 allocated data sectors, ignores
stale panel sizes and validates catalog identity and sector aliases.

A first NUL ends DOS text. The validation pass still reads the remaining
allocation, including stale bytes after that NUL, and closes the image
before any text is displayed. The display pass reopens read-only; its
read/close errors are also reported. Cancellation closes the source.
Only MAIN reader state, `copy_buf` and the text screen are written;
source disks, AUX and `/RAM` are preserved.

`tools/test_dosmerlin.py` passes six tests with real C: exact columns,
quotes/comments, sector boundaries, trailing allocation read errors,
every backend read fault, image open/seek/close faults, malformed data,
catalog/sector aliases, paging cancellation, stale sizes and sim65 on
both CPUs. All nine TXT sources on the locally cached Merlin-8 DOS disk
pass. Each invocation compares every byte of the disposable input disk.
The existing retrotext (12), direct readers (5), DOS stream (9) and
identification handoff (4) tests also pass.

Both native builds and all four distribution image checks pass with
layout checks enabled. MERLIN BSS ends at `$37A1` (65C02) and `$3797`
(6502). IDFORMATS BSS ends at `$3EEC` and `$3FF5` respectively: the
6502 detector has only ten bytes left in its `$4000` window. The 800K
image retains 96 overlays and 232 free blocks. Physical hardware has
not been tested.

`bench/direct_readers.py --6502` and `--enh` pass 36/36 checks each in
POM2, adding Merlin's exact columns through Return/I on ProDOS, DOS-order
images and the emulated DOS drive. AUX, the stack floor and both whole
source disks remain unchanged. The global host suite still has the 21
previously recorded signed/unsigned findings in unrelated decoders; these
targeted results do not claim that the global suite is clean.

## LISA v2 follow-up qualification (12 October 2026)

LISAV2 now reads the original DOS alternate-B allocation through the same
read-only stream as Merlin and S-C. DOS panels expose this catalog type
(`$40`) as typeless (`$00`). The IDV1 relay proposes LISAV2 for its verified
`$1800` editor header and a plausible declared length; the reader then
checks the actual catalog kind, complete allocation map, record bounds,
line terminators and mandatory `$FF $FF $FF` end marker. Other DOS types
cannot masquerade as alternate-B. ProDOS keeps its existing LISA routing.

Every allocated sector after the end marker is read before display, and
image closure must succeed. The display pass reopens read-only, reports
its own read/close errors and closes on cancellation. The reader writes
only MAIN overlay state, `copy_buf` and the text screen. No extracted file,
disk write, AUX use or `/RAM` reconstruction occurs.

`tools/test_doslisa.py` passes seven tests using the real reader C and
actual IDV1/IDFORMATS stages: exact listings on drives, DSK and 2IMG,
stale panel sizes, all backend read faults, image open/seek/close faults,
truncated and malformed records/end markers, catalog and sector aliases,
wrong raw types, cancellation and native sim65 runs on both CPUs. The
largest accepted declared body (`65533` in the length word) crosses three
T/S lists and its final end marker follows byte 65535; it passes both
native CPU tests. The two original alternate-B sources in the local
CiderPress II DOS sample image pass. Every invocation compares the full
disposable input disk with its original bytes.

Native builds and all four distribution image checks pass with layout
checks enabled. LISAV2 BSS ends at `$3D1D` (65C02) and `$3D25` (6502).
Using byte lengths for bounded Entry-name suffixes leaves IDFORMATS BSS
at `$3ED9` and `$3FE1`, respectively; 6502 has 30 bytes remaining below
`$4000`. Longest panel names and short/nonmatching suffixes are tested
through the real stage on host and both CPUs. The 800K edition remains
at 96 overlays and 232 free blocks. No physical hardware qualification
is claimed. Automatic DOS identification currently targets the verified
`$1800` v2 header; later LISA variants are not guessed.

`bench/direct_readers.py --6502` and `--enh` pass 42/42 checks each in
POM2: LISA v2 listings through Return/I on ProDOS, DOS-order images and
the emulated DOS drive, together with the previous direct readers. AUX,
the stack floor and both entire source disks remain unchanged. Retrotext
(12), direct-reader (5), IDENT handoff (4) and bench inventory (7) tests
also pass. The signedness check still reports the same 21 pre-existing
findings in other decoders; no global-suite success is claimed.

## Complete DOS-name qualification (12 October 2026)

The full 30-byte DOS catalog name was already retained by IDREAD in
`other_full[10..39]`, but suffix rules used only the normalized panel
name, which is shortened to 15 characters. IDV1 now checks that saved,
space-padded name for HRCG `.FONT`/`.SET`, Merlin `.ASM`/`.S` and Magic
Window `.MW`. Matching stays within those 30 bytes, folds ASCII lowercase
and retains the existing file-type/content/actual-EOF requirements.

IDFORMATS first tries its existing content rules. Only an unclassified
DOS source takes the additional IDV1 name pass, then proceeds to the
normal generic classifier when no name rule matches. Thus the change
preserves Print Shop/Fontrix/Apple Writer and other concrete detections.
The fresh T/S key and normalized catalog name remain the reader's entry
identity; a matching suffix never substitutes a lookup by shortened name.
Readers still revalidate their own sources before display.

`tools/test_dos_names.py` passes six tests using the real IDREAD, IDV1
and IDFORMATS C units on host and both native CPU simulators: maximum
30-byte names, hidden suffixes, mixed case, padding, actual file sizes,
Return/I/O routing, all source read and image open/seek/close errors,
bad context identity, misleading suffixes and existing-reader priority.
Two different catalog names that normalize to the same panel name route
independently through their own T/S keys. Each invocation compares the
complete disposable source disk. The original `BLIPPO BLACK.SET` in the
local HRCG corpus also passes, with its saved SHA-1 verified; nine corpus
occurrences are one distinct font, not nine new formats.

Only MAIN identification buffers and stage state are written. No source
file, source volume, AUX or `/RAM` is modified. Both native builds and
all four distribution image checks pass with layout controls enabled.
IDV1 BSS ends below `$3000`; IDFORMATS ends at `$3EEE` (65C02) and `$3FF8`
(6502), leaving seven bytes in the tight 6502 detector window. The 800K
edition retains 96 overlays and 231 free blocks. Physical Apple II
hardware has not been tested. The global signedness check still reports
its 21 pre-existing findings in other decoders, without a new finding.

`bench/direct_readers.py --6502` and `--enh` pass 60/60 checks each in
POM2. The additions cover both HRCG sizes (including a 30-character
name), Merlin and Magic Window through Return/I on DOS images and the
emulated DOS drive, plus the normal generic text fallback. Exact HGR
pages and text listings are checked, selection survives return, and AUX,
the stack floor and both entire source disks remain unchanged. The
existing direct-reader (5), LISA relay/decoder (7), IDENT handoff (4) and
bench inventory (7) tests also pass.

## Merlin content qualification (12 October 2026)

The late IDV1 pass also recognizes DOS TXT assembly without a filename
suffix. It scans IDREAD's first 512 bytes for three complete CR-terminated
statements: fixed 6502 mnemonics, selected Merlin directives, or numeric
`label = value` equations in Merlin columns. Blank lines and comments
do not count. High-bit printable bytes and literal ASCII spaces match the
existing reader's syntax; control bytes reject the content candidate.
Concrete format rules still run first. Fewer clues, lowercase mnemonics,
or a long opening comment can leave a genuine source in DOSVIEW; MERLIN
remains accessible through the Programming menu. This heuristic is a
tentative identification, not a proof of assembler syntax.

Eight real-C relay tests pass, including the original nine TXT files from
`MERLIN-8_DOS33.dsk` on host, sim6502 and sim65c02: its eight source/macro/
equate files route to MERLIN, while the `PI.NAMES` filename list keeps the
generic fallback. Tests cover insufficient and unfinished statements,
comments, malformed bytes, non-TXT input, Apple Writer priority and every
source read/open/seek/close failure on all three DOS backends. Entire
disposable images and the original corpus image are compared unchanged.
The six Merlin reader tests and four IDENT handoff tests also pass.

Identification only changes MAIN stage state; MERLIN continues to read
and close every allocated sector before display. No source file, volume,
AUX or RAM disk is written. Both native builds and four distribution
image checks pass with layout checks enabled. IDV1 BSS ends at `$330E`
(65C02) and `$3369` (6502), within its `$4000` boundary. The 800K edition
contains 96 overlays and has 228 free blocks. The global signedness test
now passes without findings after the decoder corrections described below.

`bench/direct_readers.py --6502` and `--enh` each pass 64/64 checks,
including automatic suffixless Merlin viewing through Return/I on both
DOS backends. AUX, the stack floor and both entire source disks are
unchanged. This qualifies emulation; physical Apple II hardware remains
untested.

## Decoder arithmetic qualification (12 October 2026)

All 21 outstanding signedness findings are corrected in seven production
files, without adding suppressions or changing the checker. Explicit signed
operands preserve LISA token bounds, Apple Writer indentation/centering,
stored decimal formatting and Movie Maker rectangle bounds. Font navigation
and LISA symbol loops compare incremented indexes rather than potentially
negative differences.

The Movie Maker case was a real cc65 2.19 rendering error: a sprite at
X=-116 with width 10 could still paint pixels. A disposable reproduction
using the previous expression produced frame hash 59475, against the
independent blank-frame expectation 0. The corrected decoder gives 0.
Regression cases cover negative positions, both horizontal edges and three
widths, with a Python pixel oracle independent of the C renderer.

The signedness suite passes all four tests. The seven affected decoder
suites pass 55 tests with each compiler (cc65 2.19 and cc65 master), running
real C on host, sim6502 and sim65c02. Added cases cover complete/truncated/
oversized LISA strings and numeric tokens, paragraph indentation extremes,
centering with narrow margins, decimal exponents and font navigation at
both limits. Existing I/O-fault and corpus checks still compare source
bytes unchanged. No new source-write or AUX-memory operation is introduced.
Both native builds and all four distribution images pass with layout
controls enabled; LISAV4 BSS ends at `$3EF1` (65C02) and `$3F42` (6502).

## Shared Merlin identification (12 October 2026)

ProDOS TXT files without `.S`/`.ASM` now reuse the bounded DOS Merlin
content rule and the existing MERLIN reader. `id_merlin.h` contains one
shared sample detector. The native IDFORMATS relay tries concrete formats
first, then passes the unchanged sample to IDV1 for saved DOS names or
Merlin content. Unmatched files continue to the generic IDENT classifier.
The host IDENT and corpus classifier use the same rule in the same order.
ProDOS files never use the DOS catalog-name bytes in the context.

The rule still needs three complete statements within the 512-byte
sample and remains tentative. A long opening comment or fewer statements
can leave a source in the generic viewer; manual MERLIN remains available.
The reader performs its existing complete validation and successful close
before display. Identification only writes MAIN sample/context state; no
source, temporary, AUX or RAM-disk data is written.

`tools/test_merlin_ident.py` passes four tests with both compiler versions
on host and both CPU simulators. Actual IDV1/IDFORMATS units cover stale
panel sizes, Return/I/O routing, sample boundaries, insufficient statements,
invalid source bytes, wrong file types, corrupted context and Apple Writer
priority. Seven original suffixless sources from the Merlin DOS corpus,
staged as ProDOS TXT, now route to MERLIN; the existing `.S` source still
does, and `PI.NAMES` keeps the generic fallback. Every disposable source
and the corpus image are compared unchanged. Host classifier parity is
checked separately. DOS-name (8), LISA relay (7), IDENT handoff (4), legacy
reader (12), signedness (4) and bench inventory (7) suites also pass.

Both native builds and all four distribution images pass, with memory
checks enabled. The simpler IDFORMATS handoff recovers space in its tight
6502 overlay: BSS ends before `$3FDA`, within the `$4000` boundary. The
800K edition retains 96 overlays and 228 free blocks. Signedness checks
remain clean; hardware qualification is still limited to emulation.

POM2 passes 66/66 checks on each CPU through `bench/direct_readers.py`.
The two new ProDOS checks verify the aligned label, opcode and operand
rows through Return and I and retain the selected file after exit. Existing
DOS-drive/image readers still pass. AUX, the stack floor and both whole
source disks remain byte-identical.

## Renamed Print Shop qualification (12 October 2026)

PSFONT and late identification now share `ps_font_layout.h`: dimensions,
every stored glyph pointer and bitmap length must fit the freshly measured
EOF. BIN layouts use 59 entries at `$6000` or `$5FF4`; ProDOS F5/$1000
uses 95 entries and its stored bitmap-byte count. The whole header must
be present in the identification sample. Renamed fonts therefore no longer
need `FONT.` as a clue. Existing concrete detections run first; this remains
a candidate, and PSFONT reads and closes the complete source before display.

ProDOS F5/$2000 borders with exactly 264 bytes likewise route to PSBORDER
without a `BORD.` name. BIN borders retain their name rule, as those load
addresses/sizes alone do not distinguish them safely. Both readers now
ship on 800K and XL; the 800K selection has 98 overlays and 193 free blocks.

Print Shop (8), DOS-name/reader (10), detector-stage (5), IDENT handoff (4)
and signedness (4) suites pass; the first three also pass with both compiler
versions on both CPU simulators. Independent corpus classification verifies
149 renamed entries: 36 legacy BIN fonts, 36 F5 fonts and 77 F5 borders.
Existing paired pixel checks still pass. Tests reject truncated headers,
last-glyph dimensions/pointers outside bounds, wrong metadata and stale
panel sizes. Every source read/open/seek/close failure on all DOS backends
is exercised; failed PSFONT reads produce no glyph display. Sources and
corpus images are compared unchanged. Bench inventory also passes.

Only MAIN validation state and the existing text display are changed;
no source, temporary, AUX RAM-disk storage or volume is written. Both
native builds and four distribution image checks pass with bounds enabled.
PSFONT BSS ends before `$3F05` (65C02) and `$3FB8` (6502); the tight 6502
IDFORMATS stage ends before `$3FEF`, within the `$4000` limit. The shared
validator uses private scalar state to stay within these memory budgets.

POM2 passes 82/82 checks per CPU. Through Return and I, the additions
compare every visible pixel of the first font glyph for both BIN headers
on ProDOS, a DOS image and an emulated DOS drive, plus F5 fonts and three
independent F5 border pixels on ProDOS. The bench waits for drawing to
finish before comparing the screen. Selection survives exit; AUX, the
stack floor and both entire source disks remain byte-identical. Physical
Apple II hardware is still untested.

### 12 October: reuse Movie Maker after ProDOS renaming

ProDOS BIN/$6000 films no longer require a `.MVM` suffix for Return/I.
The existing IDREAD sample must contain the complete 256-byte shape table
and the first bitmap header. Identification shares bitmap length/start
bounds with MVMOVIE and checks freshly measured EOF against the minimum
remaining commands. A second bitmap header is checked when present in the
512-byte sample. This is a candidate, not a full-file validity claim:
MVMOVIE still reads, validates and closes the complete film before drawing
and rejects embedded machine code. DOS keeps its existing generic fallback.

Real C detector tests qualify 13 distinct original films renamed to a
neutral name, wrong metadata, malformed sampled headers, truncated data,
stale panel sizes and host/corpus parity. Decoder tests reject bitmap
spans outside either plane before any frame; existing read/open/close/seek
fault and clipping oracles remain covered. Both CPU simulators pass with
cc65 2.19 and HEAD; source bytes remain unchanged. No source or volume
writes are introduced. Detection uses MAIN scalars and the saved sample;
the existing preview writes MAIN lores only and preserves AUX `/RAM`.

Both native architectures and all four images build with layout checks
enabled. IDV1 ends at `$39A6` (65C02) and `$3A0C` (6502), below `$4000`;
MVMOVIE ends at `$382B` and `$3866`. Native IDENT handoff tests pass.
The new renamed-film route has not been exercised on physical hardware
or through POM2; the previous 82-check POM2 qualification above is unchanged.

### 12 October: reuse PSBORDER for renamed legacy BIN borders

The BIN name clue is removed for 144/148-byte borders at `$4800`, `$5800`,
`$6800` or `$7800`. The exact length/address profile is shared with PSBORDER;
identification uses IDREAD's fresh EOF and preserves DOS allocation identity.
ProDOS and all three DOS source backends route Return/I to the existing
reader. It still reads and closes the full source before displaying the
three motifs; four-byte options remain uninterpreted. No source, volume,
temporary or AUX writes are introduced.

The Print Shop corpus classifier now qualifies 226 renamed entries,
including 77 legacy BIN borders. Actual detector stages cover both lengths,
all four addresses, bad metadata, truncated/extended lengths, an oversized
length with matching low bytes, and stale panel sizes. DOS tests inject
every read and applicable open/seek/close/ferror failure into identification
and the actual reader. A failed source produces no border title or pixels;
each source image is compared byte-for-byte after execution.

Print Shop (8), DOS detector/reader (12), and detector-stage (6) suites pass
with cc65 2.19 and HEAD on both CPU simulators; IDENT handoff (4), image
inventory and bench inventory checks also pass. Both native architectures
and four images build with layout checks enabled. The 6502 IDFORMATS stage
ends at `$3FD3`, below `$4000`; PSBORDER ends at `$396C` (65C02) and `$394E`
(6502). Signedness analysis still reports zero sites.

Targeted POM2 runs pass 18/18 checks per CPU: both BIN layouts through
Return/I on ProDOS, a DOS image and an emulated DOS drive, plus the existing
F5 border route. Four independent BIN pixels and the total ink count are
compared after complete drawing. Selection survives exit; AUX, the stack
floor and both entire disposable source disks remain byte-identical.
The full bench contains the new cases but was not rerun in this qualification.
Physical Apple II hardware is still untested.

### 12 October: reuse MULTISCR for intact ProDOS BIN imports

The existing MultiScribe TXT/WPF discriminator also accepts ProDOS BIN
documents with the same original headers. It has no filename requirement;
the unchanged reader performs its full structural pass and successful close
before displaying text. Unsupported styles and incomplete rulers still
fail. This adds no direct DOS backend: the DOS detector regression checks
that BIN documents keep their generic fallback. Only MAIN identification
state and the existing MAIN text display are written, never source or AUX.

Real detector stages qualify 12 original documents imported as BIN on both
CPU simulators, including stale panel sizes and Return/I/O. Host corpus
classification agrees. The actual C reader compares the complete text of
each BIN import with its TXT counterpart; malformed styles, truncated
headers, read/open/close faults and source-byte comparisons remain covered.
Detector (9), word-processor (5) and DOS (12) suites pass with cc65 2.19 and
HEAD on both CPU targets. Native IDENT handoff and bench inventory pass.

Both native builds and four distribution images pass with bounds enabled.
IDFORMATS ends at `$3EEB` (65C02) / `$3FE3` (6502), under `$4000`;
MULTISCR remains at `$24C8` / `$24E6`. Signedness analysis reports zero sites.
POM2 passes 17/17 checks per CPU: original TXT/WPF routes, both corresponding
BIN imports through Return/I, malformed BIN refusal, Apple Writer including
DOS, paging, AUX and stack floor preservation, all document bytes and the
entire source volume unchanged. All disks are disposable. Physical Apple II
hardware is still untested.
