# A2FC Mini DOS 3.3 — 0.8.8

A standalone edition for **Apple II+ 48 KB, NMOS 6502**, with two panels in
40 columns, DOS 3.3 copying between two Disk II drives, and formatting
of bootable DOS 3.3 disks. No ProDOS,
80-column hardware, auxiliary memory, or language card is required.
The interface, help, messages, and bundled README are entirely in English.
Written entirely in 6502 assembly; see [Speed](#speed) for what that buys.

![Two panels with inverse video and bottom shortcuts](mini-dos33.png)

The disk image `dist/A2FC-MINI-DOS33-0.8.8.dsk` boots through the Applesoft
`HELLO` program, which centres `A2FILECMD`, `MINI DOS 3.3` and `V0.8.8` at
the top of the 40-column screen, `LOADING .... PLEASE WAIT ....` and
`CAPS LOCK ON IS NEEDED` in the middle (the keys are compared in upper
case, all a II+ types), and `GPL3 VERHILLE ARNAUD` on the last row, before
`BRUN A2FC`. The same
layout stays on screen while the first catalog is read. From DOS 3.3,
use `BRUN A2FC`.
Both panels initially show the boot disk. The right panel is a full copy
of that catalog, catalog slots included, so a write from either side
holds the same entry. Each remembers its drive, selection, and scroll
position independently.

| Key | Action |
|---|---|
| Tab (Ctrl-I), or 1 | Switch panels |
| Up / down (Ctrl-K / Ctrl-J), or I / K | Previous / next file |
| Left / right, or - / +, or < / > | Previous / next page (19 files) |
| [ / ] | First / last file |
| Return, or 2 | Open by content: text, hi-res picture, hexadecimal, or `BRUN NAME?` for a program (see below) |
| T / H | Text / hexadecimal preview; also available inside the preview |
| G | Hi-res viewer: first 8 KB of the selected file |
| B | BRUN the selected binary after Y: A2FC Mini leaves, then DOS runs it from the panel's drive |
| Space | Tag or untag the selected file |
| Ctrl-T / Ctrl-N / * | Tag all / none / invert on the active panel |
| N | New text file: name, then the editor |
| E | Edit a text file in RAM, then save under a new exclusive name |
| D | Delete tagged files, or the cursor if nothing is tagged |
| L | Lock or unlock: the cursor toggles; tagged files unlock if any is locked, or lock if all are unlocked |
| R | Rename the cursor file (exclusive new name; locked files refused) |
| Escape in preview, help or editor | Return to the panels |
| C, or 3 | Copy tagged files, or the cursor if nothing is tagged |
| /, or 4 | Switch the active panel's drive and reread it |
| Ctrl-R, or 5 | Reread both panels, preserving selection by name |
| F | Format the active panel's drive as a bootable DOS 3.3 disk, DOS taken from the boot drive (see [Formatting](#formatting)) |
| ?, or 6 | Show keyboard help |
| = | Show the same disk in the other panel |
| Q, or 7 | Ask to return to DOS 3.3 |

## Controls shared with A2FC ProDOS

The layout follows `src/a2fc.c`: drives at the top, names first, file type and
an `L` lock marker on the right. The active panel header and selected file use
**native II+ inverse video**. The inactive panel remembers its selection but
uses normal characters. The lower separator shows the program name and file
count, followed by the full selected filename and allocated sector count.
Each panel displays **19 rows**, scrolling one row at the edge and paging by
19 entries with the horizontal arrows. Each catalog can hold up to 105 files.

The last row lists the main keys, each in inverse with its short action
attached in normal video: **TAB**PAN **C**OPY **D**EL **B**RUN **/**DRV
**?**HELP **Q**UIT. A label that starts with its key's letter does not
repeat it (**Y**ES **N**O **ESC**ANCEL). The other keys are in `?`. Questions use inverse video
on the status line, just above the file name line. Copy, delete, lock,
rename and create return to the two panels as soon as the write finishes;
the result takes the file name line until the next key. There is no extra
key to dismiss it.
Numbers 1–7 still mean Tab, Open, Copy, Drive, Reread, Help and Quit.
`?` lists every control, each key in inverse video. A key typed while an
operation runs is dropped before the next question: it cannot answer it.

A panel shows `INVALID CATALOG` when the VTOC does not describe a standard
35-track, 16-sector DOS 3.3 disk, when its catalog link is 0/0 or points
off track 17, when the chain loops or exceeds 15 sectors, or when an entry
points at a sector that cannot exist; `READ ERROR` when a sector cannot be
read. Neither state is ever half shown: the panel is then empty. Return, T,
H and G read whatever a file's chain points at, catalog or DOS tracks
included; only C and D refuse such a chain, since they would write.

Return reads the file's first data sector, writes nothing, and picks the
view from what the file holds:

- **T**: the text viewer, or hexadecimal when the bytes are not text.
- **B** whose DOS header (load address and length) matches the file's size:
  an 8 KB load at `$2000` or `$4000` opens in the hi-res viewer; an empty
  file, a load below `$0800` or one reaching DOS's buffers at `$9600`
  opens in hexadecimal; text opens in the text viewer, after the 4-byte
  header; anything else is a program and asks `BRUN NAME?`.
- **B** without a matching header: a raw hi-res page at 32–34 sectors,
  otherwise hexadecimal.
- **A, I, S, R**: hexadecimal.

Bytes read as text when at most one in 16 is neither printable nor RETURN.
T, H, G and B still force the text, hexadecimal or hi-res view, or BRUN.

Since v0.4, horizontal arrows page through files and Tab switches panels.
`/` replaces the old D for drive selection, and Ctrl-R replaces R for
rereading. D is delete. Escape at the browser does nothing because
DOS 3.3 has no parent directory. Q asks for confirmation. **Y confirms;
N or Escape cancels. All other keys, including O, are ignored.**
A `*` after the name marks a tagged file; the status line shows how many.

A working screen image is composed in main RAM. Presentation compares each
character, including its inverse attribute, with the physical text page.
**Only changed characters are written, once each.** Ignored keys and movement
past a boundary produce no screen writes. No physical page clear precedes
presentation.

Lists show 15 filename characters, with `+` marking a shortened name. The full
name and allocated sector count (including T/S lists) appear below the panels.
After rereading or copying, selections are restored by name when still present.

## Copying and disk writes

1. Use Tab and / to assign **two different drives** to the panels.
2. Tag the files to copy (Space, Ctrl-T / Ctrl-N, `*`), or leave them
   unmarked to copy only the cursor. Press C. The two panels stay on
   screen.
3. The footer asks `COPY name?` or `COPY N MARKED?`. Press **Y to
   confirm**, or **N / Escape to cancel without writing**. Cancel puts
   the source drive back so the next D, E, T or `/` does not read or
   write the destination. Other keys, including numeric shortcuts, are
   ignored.
4. Each file is created exclusively. A normal-video `[********----]`
   bar (32 stars or dashes) fills as that file's sectors are written
   and read back, moving once per batch of 32. An existing name is skipped
   so the rest of the batch can still land, and so is a file that does not
   fit, nothing having been written for it: smaller files after it still
   land, and the result then says `DISK OR CATALOG FULL`. An uncertain
   write stops the batch. The panels reread themselves when the result is
   ready.

After a write, only panels showing the **written** disk are reread. Two
panels on that same drive share one catalog read; the other snapshot is
filled with `copy_side`, which copies every entry field including the
catalog slot. Ctrl-R still rereads every panel. The copy engine does not
borrow the name tables as extra RAM: a tagged batch still needs the
source snapshot until the last file, and a 32-sector file therefore
costs a handful of drive changes rather than one per sector.

Copying preserves the name byte for byte (inverse, flashing or control)
characters that the panel shows as `?` included), the type, the lock flag,
and every byte of the file's data sectors, including DOS headers and the
final sector. **An existing name is refused at prepare time**, even when the
existing file is unlocked. The source is never written or deleted by a copy.

The editor: typed characters and RETURN insert, the left arrow deletes the
character before the cursor, the right arrow moves right, Ctrl-K and Ctrl-J
move up and down, Ctrl-S saves, Escape leaves (after `Y Save, N Abandon`).
Letters are letters: I, J, K and L are typed, not moves.

New text files (N) and editor saves (E) use the same exclusive-create engine
with the working area as the source: one new name, never an overwrite. A
name that already exists is not the end of the text: the footer asks
`EXISTS:` for another name, as long as needed; Escape there gives the text
up.
E loads a text file of at most 32 data sectors (8 KB), edits it in RAM, then
asks for a **new** name. A larger file is refused rather than saved truncated.
A full 8 KB of non-zero bytes is refused too: the editor keeps a NUL after
the text, and the last byte would be lost. There is no in-place replace.

L locks or unlocks. With no tags it toggles the cursor file. With tags, if
any marked file is locked the batch **unlocks** (so D can follow); if every
marked file is unlocked the batch locks. Already-set files are skipped.
Only the catalog type byte is written; file data is not touched.

R renames the cursor file only. The new name must not exist. A locked file
must be unlocked first. Only the catalog name bytes are written. The
collision scan runs once, at the prompt; before writing, the VTOC and the
slot's catalog sector are read again and must be byte for byte what was
scanned. A sibling disk swapped at the prompt that differs only by a name
in another catalog sector would not be caught.

After a lock or a rename the panel entry is patched from the sector just
read back, so the catalog is not reread; when the other panel shows the
same drive, it is read once and shared.

Delete (D) acts on the tagged files, or on the cursor when nothing is tagged.
Locked files are skipped so the rest of a batch can still go, and the
result counts both (`2 DELETED, 1 LOCKED`). A read error,
an invalid chain (including T/S or data on DOS tracks 1–2 or the catalog
track), or a changed disk stops the batch. Before the first write of a
batch, delete walks every live file on the disk and refuses if two of them
claim one sector (a cross-linked disk), one has a malformed chain, or one
cannot be read. That audit runs once per D: deleting a file cannot
cross-link the others, and every file of the batch still has its own chain
walked and its slot and the VTOC held to the panel before its write. A
full disk of 105 files costs about 16 s of scattered reads, once, not per
file. The catalog entry is marked deleted first (DOS
`$FF`, with the T/S list track kept in the last name byte, entry `$20`, as
DOS's own DELETE and the UNDELETE utilities expect), then the sectors are
freed in the VTOC. A crash after the catalog write can leak sectors; the
other order would hand those sectors to the next create while the name
still claimed them. An uncertain write (copy, create, delete, lock or
rename) latches the fault byte (`copy_fault` and `del_fault` are two names
for it) so this run cannot write again, by any command.

Delete, lock, rename and copy go back to the **catalog slot** the panel
read the entry from, then hold the disk to the panel: the slot must still
carry the T/S pointer, type, sector count and the name as it was shown, or
the operation is refused as **DISK CHANGED** before any write. A name alone
is not an identity: the panel shows unprintable characters as `?`, and a
sibling disk can reuse a name for another file. A write-protected disk is
refused as itself, before the first write, and does not latch the fault;
protection discovered after the catalog mark is treated as an uncertain
write. A catalog chain longer than the 15 sectors of track 17 is a loop:
rename's collision scan and copy's destination scan refuse it rather than
follow it.

Two drives on the controller used to boot DOS are required. Selecting the same
drive in both panels is refused. Single-drive copying by swapping disks is not
implemented. Do not change disks between confirmation and completion.
After confirmation, the keyboard cannot interrupt the operation.

Prepare walks **only the selected source file** and the destination catalog
names. It does not audit the rest of either disk or pre-read every source
sector. After you press Y, the source catalog slot and the destination VTOC
are read again and compared with what the plan was made on; a disk swapped
at the prompt on either drive is refused as **DISK CHANGED** before the
first write. A source swapped for a byte-identical twin, or a name that
appears in another catalog sector after prepare, **will not be caught**.

Required free sectors are reserved in the destination VTOC before any data.
Each written sector is read back. The catalog entry is published last, and
only if that reserved slot is still empty. RWTS respects physical write
protection. No existing file or backup is opened or replaced.

Standard 35-track, 16-sector DOS 3.3 disks are supported, with multiple T/S lists
per file up to available disk capacity. Sparse, noncanonical, inconsistent chains
or file data on track 0 or the catalog track are refused. Tracks 1 and 2 hold
DOS on an ordinary disk, whose VTOC keeps all 32 of their sectors allocated,
and a chain pointing into them is refused there; on a disk formatted without
DOS, whose VTOC frees some of them, files may live on those tracks and copies
are written there, exactly as DOS itself files data. When all 32 are
allocated, the boot sector decides, read once per file walked: a DOS 3.3 boot
sector means DOS lives there and a chain into it is refused; a disk without
DOS whose tracks 1–2 filled up keeps every file valid, deletable and
copyable. An oversized, full, or partly unreadable
catalog prevents copying. A free entry must exist in the current catalog chain;
the engine does not extend shortened catalogs. The bundled disk supplies all
105 standard entries. 13-sector, 40-track, and nonstandard protected formats
are unsupported.

## Formatting

F formats the disk in the **active panel's drive** and puts DOS on it,
the equivalent of DOS's `INIT` without the HELLO program. The DOS image
is not taken from memory: its 48 sectors on tracks 0–2 are copied from
the drive A2FC Mini was run from, the **boot drive**, whatever `/` has
shown since. So two drives are needed, the target in the active panel
and the boot disk in the other; on the boot drive F answers
`BOOT DRIVE - FORMAT THE OTHER ONE` and asks nothing. The shipped disk
carries the relocatable master image, so a disk made from it boots on any
memory size, like the shipped disk itself. Copy HELLO, A2FC, README and
TIGER onto it afterwards (Ctrl-T, C) and it boots straight into A2FC Mini.

The footer asks `FORMAT D2 WITH DOS: ERASE ALL FILES?`. **Y confirms; N or
Escape cancels**; every other key is ignored. The target is the drive, not a
file: whatever disk is in it when Y is pressed is erased, so do not change
disks at the question. Once a question is answered,
the last row shows the main keys again for the operation's duration.
Then, in this order:

1. The 48 DOS sectors are read from the boot drive before anything is
   written. A read error, or a first sector that is not a DOS 3.3 boot
   sector, refuses with `NO DOS READ ON THE BOOT DRIVE` and the
   target untouched: a read error is no proof that DOS is absent, so the
   message claims neither.
2. Write protection. RWTS's FORMAT does not sense the tab (it fails without
   saying why, the disk untouched), but a sector write does, before touching
   the disk: the target's VTOC sector is read and written back exactly as it
   was, and a protected disk answers `DISK IS WRITE PROTECTED` with nothing
   changed. A target that cannot be read, a blank disk, cannot be sensed and
   goes straight to the format.
3. RWTS formats the 35 tracks with volume 254, about 30 seconds on a real
   drive, under `FORMATTING...`. A progress bar on the file name line fills
   in steps, between the disk phases: the boot disk read, RWTS's own
   format (one call, about half the time, credited when it returns), the
   DOS batches written and read back, the catalog track.
4. The DOS sectors are read again and written to the target in two batches
   through the working area (tracks 0–1, then 2), each batch then read back
   and compared, as the copy does.
5. Catalog sectors 15 down to 1 are built empty in the working area,
   chained as `INIT` chains them, and go out as a third batch, written
   from 15 down and then read back and compared like the DOS ones; the
   VTOC comes last, on its own: volume 254, tracks 0–2 and 17 reserved,
   496 free sectors, allocation starting after the catalog track. A disk
   whose VTOC reads as valid therefore always has a valid catalog behind
   it, because the VTOC goes down only once every catalog sector has been
   read back.

`FORMATTED WITH DOS 3.3` rereads the panels on that drive: `EMPTY DISK`,
`V254`. `FORMAT FAILED: PROTECTED, BAD OR ERASED` covers what RWTS does not
tell apart: a protected blank disk (untouched), a disk it could not format
(state unknown), or the boot disk failing after the format (erased, no DOS).
None of these has a VTOC written, so the reread shows what happened, and the
disk can be formatted again. A target write that does not read back is
`UNCERTAIN WRITE - STOP` and latches the run's write fault, like every other
write here. The boot disk is never written. There is no format without DOS
and no volume number prompt.

### Errors and physical limitations

An error before reservation leaves the disk unchanged. An uncertain error after
writes begin leaves reservations in place and blocks further copies for that
run. Sectors may remain reserved without a visible file. The message instructs
you to stop writing to the target disk and have it checked before reuse.

A physical DOS sector write is **not atomic**. Power loss or failure while writing
the VTOC or a shared catalog sector can damage metadata, including metadata for
existing files. Readback verification detects errors; it cannot guarantee repair.

## Browsing

After changing a disk outside a copy operation, wait for disk access to finish
and press Ctrl-R to reread both panels. Catalogs are snapshots. A missing disk
reports an error after DOS retries; the other panel remains usable afterward.

Previews show only the **first 256 stored bytes** and do not verify the complete
file. BASIC and binary DOS headers are visible in hexadecimal. Files without
a first data sector cannot be previewed.

## Speed

The edition is written in 6502 assembly, and the reason is measurable.
`bench/mini33_time.py` records these on POM2's NMOS core with Disk II
timing, tracing every RWTS call:

| Operation | C, 48 sectors | asm, 85 sectors | now, 90 sectors |
|---|---:|---:|---:|
| Read a 16-sector catalog with `/` (4 files; a drive change, so about 1.1 M of it is RWTS waiting for the motor) | 4 898 568 cycles | 1 703 567 | 1 916 884 |
| The same on a full disk of 105 files, disk time only | — | 4 347 636 | 1 785 324 |
| Copy `A2FC` — prepare (source file + dest names) | 21 577 238 | 5 899 687 | 3 471 793 |
| Copy `A2FC` — write and read back | 258 512 282 | 56 775 543 | 21 565 582 |
| **Copy, total at 1 MHz** | **280 s** | **62.7 s** | **25.0 s** |

DOS 3.3 lays a track down with a 2:1 soft interleave: logical sector n-1
sits two physical slots after sector n, so a chain read **from 15 down to
0** costs two slots (about 24 000 cycles) a sector and a track in two
turns, while an ascending chain waits fourteen slots, nearly a whole
turn, at every sector. DOS allocates its files that way for that reason.
Everything here now follows: the copy reserves and hands out its target
sectors from 15 down, the format visits tracks 0–2 that way, and the disk
builder lays the shipped files down that way too.

The window is small. RWTS decodes a sector after reading it and encodes
one before writing it, and what is left for the program between two
consecutive sectors is a few hundred cycles, not the 25 000 an earlier
version of this page claimed: a 256-byte copy between two RWTS calls
(4 000 cycles) or a redraw of the screen (about 31 000) each cost a whole
turn. So RWTS moves sectors straight to and from their page of the
working area, the progress bar is redrawn only when a cell changes, once
per batch, and the DOS-3.3 screen holes are no longer saved and put back
around every call: nothing in the program writes them.

The copy engine reads a batch of up to 32 sectors from the source, then
writes and verifies it one track at a time: every sector of the track,
then every one read back into a buffer and compared with its page, even
offsets first, then odd, so that a compare fits before the next sector to
read passes under the head (four slots away instead of two; 44 000 cycles
a read-back) and the read-backs never seek back to the batch's other
track. A file is still published only after every one of its sectors
read back. What changed: between a silent bad write and its detection,
the rest of that track is written to sectors that are reserved and
unpublished, where before the batch stopped at that sector; the outcome
for the disk is the same, and on a failing drive the diagnosis comes up
to 15 sectors later. The first batch is read from the source before the
target's VTOC is checked and written, so the copy opens with one change
of drive instead of two. What is left is the drive changes, about a
million cycles each for RWTS to wait for the motor (five for this file),
and the first sector of each track after a seek.

Before the copy, the destination catalog is scanned for the name and a
free slot; the panel's own catalog read stages the VTOC and the chain
in the upper half of the working area, one page each, and parses them
afterwards, since parsing seven entries takes longer than the gap
between two sectors. RWTS reads the chain straight into its buffers in
both cases.

After Y, the result line appears and then the written disk's catalog is
read. Two panels on the same drive share the one read; a copy to the
other drive rereads only the destination; lock and rename patch the entry
instead. Ctrl-R still reads both.

## Building

Requirements: cc65 (`ca65`, `ld65`; `cl65` for the tests), Python 3, make.

```sh
make mini
make test-mini
make mini-disk MINI_MASTER="/path/to/dos33_master.dsk"
```

The master must be a standard 140 KB DOS-order DOS 3.3 image that starts `HELLO`.
Only its three system tracks are read. The builder creates HELLO, A2FC,
README and the raw 8 KB HGR picture TIGER on a new image without changing
the master. Return or G on TIGER opens hi-res. It refuses an existing
output; use `MINI_DISK=dist/A2FC-MINI-test.dsk` for another build. A failed build
may leave a newly created partial output, which must not be used.

The raw binary is `build-mini/A2FC.MINI`. The disk builder adds its `$1000` load
address and length. `make mini` is independent of the ProDOS editions and of
cc65's C compiler and runtime: the assembly modules are linked by
`src/mini/mini-asm.cfg`.

## Memory and validation

- `$0080–$009F`: the only zero page this program touches, saved on entry and
  restored before the closing RTS, because Applesoft keeps its pointers there
  and `HELLO` has to survive the BRUN.
- `$0200–$03CF`: the format engine, DOS's input buffer and the free part of
  page three. It travels inside the working area of the BRUN image and is
  copied out at `$1000` before anything else runs; nothing in DOS or in
  A2FC Mini touches those pages while the panels are up, and the page-3
  BRUN stub is written only on the way out.
- `$0400–$07FF`: 40-column screen; only changed visible characters are written.
  DOS 3.3 keeps each drive's current track in the screen holes (`$0478+slot`
  and the following holes); nothing here writes them, so they are left alone.
- `$0800–$0FFF`: the Applesoft launcher, left untouched.
- `$1000–$1FFF`: editor, delete, lock and rename, and the copy engine's
  prepare-time routines (locating the source entry, counting T/S lists).
  Nothing in the batch path lives here.
- `$2000–$3FFF`: hi-res page one, the one 8 KB working area. Exactly one
  owner at a time: a copy batch, a picture, the editor buffer, the DOS
  sectors of a format, or, while the panels are read, the catalog chain
  staged in its upper half. RWTS reads and writes those sectors in place,
  one page each. In the file it also carries the format engine and
  the code that runs once at start (entry, splash, the first catalog),
  which nothing needs once the panels are up.
- `$4000–$95FF`: resident program and BSS. `$9600` is Applesoft's HIMEM
  under this DOS, measured on a running machine.
- No software stack: page one is the only one.
- `make mini` prints the remaining room at every link and
  `tools/check_mini_layout.py` refuses a build that would reach into DOS,
  into the working area, or into the DOS vectors at `$03D0`.
- DOS, its buffers, and RWTS remain in place. No auxiliary bank or language
  card is used. There are no overlays or dynamic heap allocations.

`make test-mini` runs the shipped 6502 modules under `sim65`, with the two
disk images held by the test process so that a chosen read or write can be
made to fail, tear in half, or silently corrupt a byte. It covers reads at
every stage; refused, partial and corrupt writes; write protection, before
and after the first write; cancellation; collisions, including one hiding
in another catalog sector; full disks and catalogs; stale panel sizes and
pointers; malformed and looping chains; metadata changed between the
prompt and the writing, including a source or destination disk swapped at
the prompt; disks formatted without DOS, with files on tracks 1–2; names
with inverse or control characters; fragmented destinations; empty files; files needing up to five T/S
lists; loading a file without losing its T/S list, and knowing when it did
not fit; exclusive create and its collisions; delete that marks the
catalog before the VTOC with the DOS UNDELETE mark; and delete, lock and
rename refusing an entry whose identity no longer matches the panel; and
format refused on the boot drive, on a latched fault, on a protected
disk (blank or not) and on an unreadable boot disk, stopped by every read,
write, torn write and corruption of its 64 writes after the format, and
otherwise leaving tracks 0–2 equal to the boot disk's and track 17 as
`INIT` leaves it. What
is asserted is the bytes: the source unchanged on a copy, every
pre-existing target byte intact, and a consistent allocation graph
afterwards.

With POM2 built and its Apple II+ / Disk II ROMs available:

```sh
python3 bench/mini33.py --pom2-root /path/to/pom2
python3 bench/mini33_write.py --pom2-root /path/to/pom2
python3 bench/mini33_ops.py --pom2-root /path/to/pom2
python3 bench/mini33_format.py --pom2-root /path/to/pom2
python3 bench/mini33_time.py --pom2-root /path/to/pom2
```

The benches use disposable images and an NMOS CPU. The first checks panels,
long names, disk errors, English text, tags, and physical screen writes through
memory watchpoints: unchanged characters must never be rewritten. The second
checks cancellation, ignored confirmation keys, physical protection, verified
copying, and collisions. It then reloads the copied binary with **DOS BLOAD**
and creates another file with **DOS SAVE**. `mini33_ops.py` checks the hi-res
viewer, exclusive TXT create and delete. `mini33_format.py` refuses F on
the boot drive, cancels, meets a write-protected disk, then formats a
disk holding files, a zero-filled image and a diskette that was never
formatted (no address fields, so the panel reads nothing and the
write-protect probe cannot sense it), copies the four shipped files onto
each and boots the result into A2FC Mini. Contents and allocations are
independently checked afterward. `mini33_time.py` reports the cycle costs
in the table above.

Physical Apple II+ validation of this edition's writes remains outstanding.
The RWTS interface follows the [Apple DOS manual, chapter 9](https://manuals.plus/m/c08d8e894bc01bf74e7348df79c1e3b2360f43ada6e2b08e39f9686651575161).
