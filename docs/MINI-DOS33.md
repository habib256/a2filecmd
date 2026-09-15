# A2FC Mini DOS 3.3 — 0.8.7

A standalone edition for **Apple II+ 48 KB, NMOS 6502**, with two panels in
40 columns and DOS 3.3 copying between two Disk II drives. No ProDOS,
80-column hardware, auxiliary memory, or language card is required.
The interface, help, messages, and bundled README are entirely in English.
Written entirely in 6502 assembly; see [Speed](#speed) for what that buys.

![Two panels with inverse video and bottom shortcuts](mini-dos33.png)

The disk image `dist/A2FC-MINI-DOS33-0.8.7.dsk` boots through the Applesoft
`HELLO` program, which centres `A2FILECMD`, `MINI DOS 3.3` and `V0.8.7` at
the top of the 40-column screen, then `GPL3 VERHILLE ARNAUD` and
`LOADING .... PLEASE WAIT ....` at the bottom, before
`BRUN A2FC.MINI`. The same
layout stays on screen while the first catalog is read. From DOS 3.3,
use `BRUN A2FC.MINI`.
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
| Return, or 2 | Preview by type; a 32–34 sector binary opens as hi-res, any other binary runs (BRUN, after Y) |
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
attached in normal video: **TAB**Pan **C**Copy **D**Del **B**Run **/**Drv
**?**Help **Q**Quit. The other keys are in `?`. Questions use inverse video
on the status line, just above the file name line. Copy, delete, lock,
rename and create return to the two panels as soon as the write finishes;
the result takes the file name line until the next key. There is no extra
key to dismiss it.
Numbers 1–7 still mean Tab, Open, Copy, Drive, Reread, Help and Quit.
`?` lists every control.

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
   bar (32 stars or dashes) fills while that file's sectors are written
   and read back. An existing name is skipped
   so the rest of the batch can still land. An uncertain write stops the
   batch. The panels reread themselves when the result is ready.

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

New text files (N) and editor saves (E) use the same exclusive-create engine
with the working area as the source: one new name, never an overwrite.
E loads a text file of at most 32 data sectors (8 KB), edits it in RAM, then
asks for a **new** name. A larger file is refused rather than saved truncated.
A full 8 KB of non-zero bytes is refused too: the editor keeps a NUL after
the text, and the last byte would be lost. There is no in-place replace.

L locks or unlocks. With no tags it toggles the cursor file. With tags, if
any marked file is locked the batch **unlocks** (so D can follow); if every
marked file is unlocked the batch locks. Already-set files are skipped.
Only the catalog type byte is written; file data is not touched.

R renames the cursor file only. The new name must not exist. A locked file
must be unlocked first. Only the catalog name bytes are written.

Delete (D) acts on the tagged files, or on the cursor when nothing is tagged.
Locked files are skipped so the rest of a batch can still go, and the
result counts both (`2 DELETED, 1 LOCKED`). A read error,
an invalid chain (including T/S or data on DOS tracks 1–2 or the catalog
track), or a changed disk stops the batch. Before any write, delete walks
every other live file on the disk and refuses if one of them claims a
sector of the target (a cross-linked disk), has a malformed chain, or cannot
be read. The catalog entry is marked deleted first (DOS
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
are written there, exactly as DOS itself files data. An oversized, full, or partly unreadable
catalog prevents copying. A free entry must exist in the current catalog chain;
the engine does not extend shortened catalogs. The bundled disk supplies all
105 standard entries. 13-sector, 40-track, and nonstandard protected formats
are unsupported.

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
Two things used to cost whole disk revolutions, and `bench/mini33_time.py`
records both on POM2's NMOS core with Disk II timing:

| Operation | Before (C, 48 sectors) | Now (asm, 85 sectors) |
|---|---:|---:|
| Read a 16-sector catalog (`/`, motor already turning) | 4 898 568 cycles | 1 703 567 cycles |
| Copy `A2FC.MINI` — prepare (source file + dest names) | 21 577 238 | 5 899 687 |
| Copy `A2FC.MINI` — write and read back | 258 512 282 | 56 775 543 |
| **Copy, total at 1 MHz** | **280 s** | **62.7 s** |

DOS 3.3 lays out a track with a 2:1 soft interleave, which leaves a
program roughly 25 000 cycles to digest one sector before the next
arrives under the head. Miss that window and RWTS waits a whole
revolution, about 200 000 cycles. Parsing a catalog sector now takes a
few thousand cycles, so the chain is read at the speed of the disk.

The copy engine reads a batch of sectors from the source, then writes and
reads each of them back on the target. The two disks are not compared
again. A change of drive costs a seek and a motor spin-up, so writes stay
on the destination until the next batch of source reads. Per-sector
readback is kept: a grouped verify of the whole batch would write more
reserved sectors after a silent bad write before noticing. The extra
seconds are the cost of catching that on the sector that failed.

After Y, the result line appears and then the written disk's catalog is
read. Two panels on the same drive used to pay that catalog twice
(about 7 s with spin-up); they now share the one read. A copy to the
other drive rereads only the destination. Ctrl-R still reads both.

## Building

Requirements: cc65 (`ca65`, `ld65`; `cl65` for the tests), Python 3, make.

```sh
make mini
make test-mini
make mini-disk MINI_MASTER="/path/to/dos33_master.dsk"
```

The master must be a standard 140 KB DOS-order DOS 3.3 image that starts `HELLO`.
Only its three system tracks are read. The builder creates HELLO, A2FC.MINI,
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
- `$0400–$07FF`: 40-column screen; only changed visible characters are written.
  Disk II's current-track bytes live in that page (`$0478+slot×16` and the
  following holes). They are saved at entry and restored before every RWTS
  call, so drawing the panels cannot send the next seek to the wrong track.
- `$0800–$0FFF`: the Applesoft launcher, left untouched.
- `$1000–$1FFF`: editor, delete, lock and rename, and the copy engine's
  prepare-time routines (locating the source entry, counting T/S lists).
  Nothing in the batch path lives here.
- `$2000–$3FFF`: hi-res page one, the one 8 KB working area. Exactly one
  owner at a time: a copy batch, a picture, or the editor buffer.
- `$4000–$95FF`: resident program and BSS. `$9600` is Applesoft's HIMEM
  under this DOS, measured on a running machine.
- No software stack: page one is the only one.
- `make mini` prints the remaining room at every link and
  `tools/check_mini_layout.py` refuses a build that would reach into DOS
  or into the working area.
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
rename refusing an entry whose identity no longer matches the panel. What
is asserted is the bytes: the source unchanged on a copy, every
pre-existing target byte intact, and a consistent allocation graph
afterwards.

With POM2 built and its Apple II+ / Disk II ROMs available:

```sh
python3 bench/mini33.py --pom2-root /path/to/pom2
python3 bench/mini33_write.py --pom2-root /path/to/pom2
python3 bench/mini33_ops.py --pom2-root /path/to/pom2
python3 bench/mini33_time.py --pom2-root /path/to/pom2
```

The benches use disposable images and an NMOS CPU. The first checks panels,
long names, disk errors, English text, tags, and physical screen writes through
memory watchpoints: unchanged characters must never be rewritten. The second
checks cancellation, ignored confirmation keys, physical protection, verified
copying, and collisions. It then reloads the copied binary with **DOS BLOAD**
and creates another file with **DOS SAVE**. `mini33_ops.py` checks the hi-res
viewer, exclusive TXT create and delete. Contents and allocations are
independently checked afterward. `mini33_time.py` reports the cycle costs
in the table above.

Physical Apple II+ validation of this edition's writes remains outstanding.
The RWTS interface follows the [Apple DOS manual, chapter 9](https://manuals.plus/m/c08d8e894bc01bf74e7348df79c1e3b2360f43ada6e2b08e39f9686651575161).
