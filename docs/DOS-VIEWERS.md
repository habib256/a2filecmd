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
for PG. layouts. Other files use DOSVIEW's text/hex/raw-picture modes.
ProDOS uses the same detection and its own readers. Epistole and Extasie
are ProDOS formats; they do not select a DOS document/image reader.
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
