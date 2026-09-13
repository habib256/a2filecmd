# A2FC Mini DOS 3.3 — 0.7.0

A standalone edition for **Apple II+ 48 KB, NMOS 6502**, with two panels in
40 columns and DOS 3.3 copying between two Disk II drives. No ProDOS,
80-column hardware, auxiliary memory, or language card is required.
The interface, help, messages, and bundled README are entirely in English.
Written entirely in 6502 assembly; see [Speed](#speed) for what that buys.

![Two panels with inverse video and bottom shortcuts](mini-dos33.png)

The disk image `dist/A2FC-MINI-DOS33-0.7.0.dsk` boots through the Applesoft
`HELLO` program. From DOS 3.3, use `BRUN A2FC.MINI`.
Both panels initially show the boot disk. Each remembers its drive, selection,
and scroll position independently.

| Key | Action |
|---|---|
| Tab (Ctrl-I), or 1 | Switch panels |
| Up / down (Ctrl-K / Ctrl-J), or I / K | Previous / next file |
| Left / right, or - / +, or < / > | Previous / next page (18 files) |
| [ / ] | First / last file |
| Return, or 2 | Preview by type; a 32–34 sector binary opens as hi-res |
| T / H | Text / hexadecimal preview; also available inside the preview |
| G | Hi-res viewer: first 8 KB of the selected file |
| Space | Tag or untag the selected file |
| Ctrl-T / Ctrl-N / * | Tag all / none / invert on the active panel |
| N | New text file: name, then the editor |
| E | Edit a text file in RAM, then save under a new exclusive name |
| D | Delete the selected file, or every tagged file |
| Escape in preview, help or editor | Return to the panels |
| C, or 3 | Copy to the other panel's drive |
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
Each panel displays **18 rows**, scrolling one row at the edge and paging by
18 entries with the horizontal arrows. Each catalog can hold up to 105 files.

The ProDOS command bar occupies two bottom rows to fit 40 columns:
**inverse key blocks with normal labels**. Numbers 1 through 7 activate these
commands in display order. They do not apply to confirmation prompts.
`?` lists all controls; the bar includes only commands implemented in Mini.

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
2. Select the source file and press C.
3. Mini checks both disks and shows the full filename, drives, and volume
   numbers read from the disks.
4. Press **Y to confirm**, or **N / Escape to cancel without writing**.
   Other keys, including numeric shortcuts, are ignored.
5. Wait for `COPY VERIFIED`, then press a key to reread the panels.

Copying preserves the name, type, lock flag, and every byte of the file's data
sectors, including DOS headers and the final sector. **An existing name is
refused**, even when the existing file is unlocked. The source is never written
or deleted by a copy.

New text files (N) and editor saves (E) use the same exclusive-create engine
with the working area as the source: one new name, never an overwrite.
E loads a text file, edits it in RAM, then asks for a **new** name. There is
no in-place replace.

Delete (D) acts on the tagged files, or on the cursor when nothing is tagged.
Locked files are refused. The catalog entry is marked deleted first (DOS
`$FF`, original track kept for UNDELETE), then the sectors are freed in the
VTOC. A crash after the catalog write can leak sectors; the other order
would hand those sectors to the next create while the name still claimed
them. An uncertain write latches `del_fault` so this run cannot write again.

Two drives on the controller used to boot DOS are required. Selecting the same
drive in both panels is refused. Single-drive copying by swapping disks is not
implemented. Do not change disks between checking, confirmation, and completion.
After confirmation, the keyboard cannot interrupt the operation.

The engine checks both VTOCs, complete catalogs and T/S chains, shared sectors,
bounds, and allocation consistency. It rereads the source before any write;
cached panel sizes are not authoritative. After confirmation it rechecks the
disks, including name collisions in other catalog sectors.

Required free sectors are reserved in the destination VTOC. Data and new T/S
lists are written and read back sector by sector. Every source/destination data
byte is compared again before publishing the catalog entry. RWTS respects
physical write protection. No existing file or backup is opened or replaced.

Standard 35-track, 16-sector DOS 3.3 disks are supported, with multiple T/S lists
per file up to available disk capacity. Sparse, noncanonical, inconsistent chains
or file data on system tracks are refused. An oversized, full, or partly unreadable
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

| Operation | Before | Now |
|---|---:|---:|
| Read a 16-sector catalog (`/`, motor already turning) | 4 898 568 cycles | 1 703 592 cycles |
| Copy `A2FC.MINI`, 48 sectors — checking | 21 577 238 | 16 579 936 |
| Copy `A2FC.MINI`, 48 sectors — writing | 258 512 282 | 47 713 385 |
| **Copy, total** | **280 s at 1 MHz** | **64 s** |

DOS 3.3 lays out a track with a 2:1 soft interleave, which leaves a
program roughly 25 000 cycles to digest one sector before the next
arrives under the head. Miss that window and RWTS waits a whole
revolution, about 200 000 cycles. Parsing a catalog sector now takes a
few thousand cycles, so the chain is read at the speed of the disk.

The copy engine reads a batch of thirty-two sectors (the whole working
area) from the source, then writes and verifies that batch on the target,
then re-reads both disks for the final comparison. It performs the same
six disk operations per sector as before and in the same order of safety;
what changed is that the drives alternate four times per batch instead of
four times per sector, and a change of drive costs a seek and a motor
spin-up.

## Building

Requirements: cc65 (`ca65`, `ld65`; `cl65` for the tests), Python 3, make.

```sh
make mini
make test-mini
make mini-disk MINI_MASTER="/path/to/dos33_master.dsk"
```

The master must be a standard 140 KB DOS-order DOS 3.3 image that starts `HELLO`.
Only its three system tracks are read. The builder creates HELLO, A2FC.MINI,
and README on a new image without changing the master. It refuses an existing
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
- `$0800–$0FFF`: the Applesoft launcher, left untouched.
- `$1000–$1FFF`: editor and delete. They never run at the same time as a
  copy or a picture.
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
every stage; refused, partial and corrupt writes; write protection;
cancellation; collisions, including one hiding in another catalog sector;
full disks and catalogs; stale panel sizes and pointers; malformed chains;
metadata changed between the prompt and the writing; fragmented
destinations; empty files; files needing up to five T/S lists; loading a
file without losing its T/S list; exclusive create and its collisions;
and delete that marks the catalog before the VTOC. What is asserted is
the bytes: the source unchanged on a copy, every pre-existing target byte
intact, and a consistent allocation graph afterwards.

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
