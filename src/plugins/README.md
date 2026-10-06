# Service-table overlays

Every command added since 0.7.1 is a **service-table overlay**: a
`src/plugins/name.c` compiled and linked on its own, exactly like a third
party's (`sdk/`), and reaching the program only through `struct A2fcApi`
(`src/a2fc_plugin.h`). The resident is full, so nothing new goes into
`src/a2fc.c`; an overlay costs the resident nothing and appears in the `!`
menu with the description of its header.

## The overlays

The 63 sources of `src/plugins/*.c`, as of 6 October 2026. "media" means
the `MEDIA_PLUGIN_MAGIC` signature (API 4 services); AUX and AUDIO are the
`OVERLAY_AUX` and `OVERLAY_AUDIO` flags (PT3 and VISICALC ask through
`aux_consent` instead; FIXIT and REPAIR, on a volume of more than 4,096
blocks, ask their own `/RAM` question). The category is the core's `mn_group*` lists in
`src/a2fc.c`; "hidden" ones are run by another command, never from the
menu. Every overlay is on the 800K and XL images.

| Overlay | `!` menu category | Kind | On the 140K floppy | Description (its header) |
| --- | --- | --- | --- | --- |
| ARLEQUIN | Images | big, AUX, media |  | Arlequin $F8 pictures (Chat Mauve) |
| AWDATA | Files | big |  | AppleWorks data bases and spreadsheets ($19, $1B) |
| BLKEDIT | Disks | big |  | Edit a disk block and write it back after ERASE |
| BLKVIEW | Disks | big |  | Read-only blocks: hex, directories and indexes |
| BOOTBLK | Disks | big |  | Rewrite the ProDOS boot blocks of a volume |
| CPM | Disks | big |  | Apple CP/M volume: extract its files |
| CPMW | Disks | big |  | Apple CP/M volume: put the files opposite into it |
| CRC | Programming | small |  | CRC-32 |
| DATE | System | small |  | Date |
| DGRVIEW | Images | big, media |  | Lo-res and double lo-res pictures, a2dgrx sprites |
| DISASM | Programming | big |  | Disassemble BIN/SYS: 6502 or 65C02, read only |
| DISKCMP | Disks | big |  | Compare volumes or disk images block by block |
| DOCVIEW | Files | big |  | Read Epistole, Papyrus, HomeWord, Bank Street docs |
| DOS33W | Disks | big |  | DOS 3.3: delete or rename the selected file |
| DOSIMAGE | hidden | big |  | Prepare and safely install a DOS 3.3 image copy |
| DOSPUT | hidden | big |  | engine of DOSIMAGE (doswrite.c built with DOS_IMAGE) |
| DOSREPL | Disks | big |  | DOS 3.3: replace the file of the same name |
| DOSWRITE | Disks | big |  | Copy selected ProDOS file to a real DOS 3.3 disk |
| DUET | Music | big, AUDIO, media |  | Play Electric Duet music; P pauses, ESC returns |
| EXTASIE | Images | big, AUX, media |  | Extasie $F2 pictures (Chat Mauve 560/140) |
| FIND | Files | big |  | Find files by name, text, type and date |
| FIXIT | Disks | big |  | Check ProDOS volume links and bitmap (read only) |
| FIXTYPES | Files | big |  | Review and repair file types; marked or selected |
| FONTVIEW | Images | big, media |  | MGTK and hi-res fonts |
| GMAGIC | Images | big, media |  | Graphics Magician pictures |
| GOTO | Files | big |  | Favourite directories: jump in two keys, add, del |
| IDENT | Programming | big |  | Say what a file is from its content, like file(1) |
| IMGCONV | Disks | big |  | Convert a disk image: .DSK/.DO, .PO, .2MG, DiskCopy |
| IMGPUT | Disks | big |  | ProDOS image: copy the selected file into it |
| INTBASIC | Programming | big |  | List an Integer BASIC program ($FA) |
| LZ4FH | Images | big, media |  | LZ4FH picture |
| MACPAINT | Images | big, AUX, media |  | MacPaint pictures (576 x 720, scrolled) |
| MDVIEW | Files | big |  | Read Markdown or long text, wrapped to 80 columns |
| MKIMAGE | Disks | big |  | Create an empty formatted .PO or .2MG image |
| MOVE | Files | big | yes | Move without copying: rewrite the directory entry |
| MUSIC | Music | big, AUDIO, media |  | Play MB1 music; P pauses, ESC returns |
| NEWSROOM | Images | big, media |  | The Newsroom photos and banners |
| NIBCOPY | Disks | big, AUX |  | Copy Disk II tracks with verified nibble fields |
| NRCLIP | Images | big |  | Newsroom clip-art disk: pages to HGR files |
| PACKFOT | Images | big, AUX, media |  | Packed $08 pictures ($4000/$4001) |
| PAINT816 | Images | big, AUX, media |  | 816/Paint packed picture |
| PASCAL | Disks | big |  | Apple Pascal volume: list and extract its files |
| PASCALW | Disks | big |  | Apple Pascal volume: put the files opposite into it |
| PRINTSHOP | Images | big, media |  | Print Shop |
| PT3 | Music | big, AUDIO, media |  | ProTracker 3 music |
| PURPLE | Images | big, AUX, media |  | Purplesoft pictures |
| RENAME | Files | small |  | Rename tagged files |
| REPAIR | Disks | big |  | Repair a ProDOS volume: plan, type FIX, every write read back |
| RESCUE | Disks | big |  | Recover file/disk data with retries and a log |
| SCIIBIN | Archives | big |  | BinSCII: decode .BSC/.BSQ text, and its next parts |
| SHAPES | Images | big |  | Applesoft shape tables, 24 a page |
| SYNC | Files | big |  | Copy missing or newer files to the other panel |
| TAGPAT | Files | small |  | Tag files by pattern (= ?), type, size or date |
| TREE | Files | big |  | Directory tree with cumulative file sizes |
| TXTCONV | Files | big |  | Convert text: CR/LF/CRLF, high bit, tabs, accents |
| UNDELETE | Disks | big |  | Recover deleted ProDOS files to another volume |
| UNSQ | Archives | big |  | SQueeze .QQ files and ACU archives: extract |
| UNWRAP | Archives | big |  | AppleSingle and MacBinary: extract the data fork |
| VERIFY | Disks | small | yes | Read files or volume |
| VISICALC | Files | big |  | VisiCalc worksheets (/SS files), recalculated |
| VOLINFO | Disks | big |  | ProDOS space, fragmentation and allocation audit |
| VOLNAME | Disks | small |  | Rename a volume |
| WIPE | Disks | big |  | Zero the free blocks of a volume, or the whole disk |

## Layout of a source

```c
/* name.c -- one line on what it does. */
#include "../a2fc_plugin.h"

void __fastcall__ plugin_entry(const struct A2fcApi* api);

struct PluginHeader {
    unsigned int signature; unsigned char flags;
    void __fastcall__ (*entry)(const struct A2fcApi*);
    unsigned char r0, r1, r2; char desc[66];
};
#pragma rodata-name (push, "OVLHDR")
const struct PluginHeader __plugin_header = {
    PLUGIN_MAGIC, 0, plugin_entry, 0, 0, 0,     /* `PLUGIN_MAGIC, OVERLAY_BIG,` for a big one, on this line */
    "Menu line: what it does; the menu shows 51 characters"
};
#pragma rodata-name (pop)

void __fastcall__ plugin_entry(const struct A2fcApi* api) { ... }
```

`sdk/hello.c` is the model. The Makefile picks up every `src/plugins/*.c`:
`make build/name.PLG` (65C02, the machine's cc65: Homebrew's 2.18 here) and
`make build-6502/name.PLG ARCH=6502` (6502, cc65 master in `~/opt/cc65-head`) -- the same source must build for both, so
no 65C02-only inline assembly. A source that mentions `OVERLAY_BIG` is
linked as a big overlay: the Makefile looks for `PLUGIN_MAGIC, OVERLAY_BIG` on one
line of the source. The link refuses a file over its window:

| Overlay | Window | File at most | Scratch memory |
| --- | --- | --- | --- |
| small (`flags = 0`) | `$1B00-$1FFF` | 1,280 bytes | `api->copy_buf` (512), `api->input` (17), `api->other_full` (81, if you do not need the other panel's path) |
| big (`OVERLAY_BIG`) | `$1B00-$3FFF` | 9,472 bytes | the same, plus `$3000-$3FFF` (4 KB) **only if the ld65 map shows BSS ending under `$3000`** — the file size alone does not prove it, since BSS is not in the file |
| scratch group (`XPLUGINS_SCRATCH`: MUSIC, BOOTBLK, GOTO, MDVIEW, WIPE, DGRVIEW, FIXTYPES) | `$1B00-$2FFF` | 9,472 bytes | `$3000-$3FFF`, enforced by the link |
| FIND (`sdk/find.cfg`) | `$1B00-$30FF`, setup code at `$3100-$38FF` | 9,472 bytes | queue `$3100-$38FF` (over the setup code once it has run), results `$3900`, pool `$3E00`, table copy `$3F9E` |
| picture viewers (`XPLUGINS_HGR`: PURPLE, EXTASIE, ARLEQUIN, MACPAINT, SHAPES, PACKFOT, PAINT816, FONTVIEW, PRINTSHOP, LZ4FH, NEWSROOM) | big, but code and BSS in `$1B00-$1FFF` | 1,280 bytes | the hi-res page they decode into |
| VOLINFO, BLKVIEW, BLKEDIT, FIXIT, REPAIR (their own case in the Makefile) | `$1B00-$3F9D` | 9,472 bytes | `$3F9E-$3FFF`: their 98-byte copy of the service table (up to `ram_format`) |
| DUET (its own case in the Makefile) | `$1B00-$23FF` | 2,304 bytes | `$2400-$3FFF` (7 KB) for the song |
| PT3 (`sdk/pt3.cfg`) | `$1B00-$36FF`, headers `$3700-$3AFF`, page cache from `$3B00` | 9,472 bytes | see `src/plugins/pt3.c` |
| NIBCOPY (`sdk/nibcopy.cfg`) | `$1B00-$3FFF`, cleanup code first | 9,472 bytes | MAIN `$6500-$84FF` borrowed and restored, AUX after consent ([`docs/NIBCOPY.md`](../../docs/NIBCOPY.md)) |
| VISICALC (`sdk/visicalc.cfg`) | `$1B00-$25FF` kept, three phases swapped in at `$2600-$35FF` (`A2FILE/VISICALC.BIN`), BSS `$3600` | 9,472 bytes | the value table from the end of BSS to `$3FFF`, then AUX after `aux_consent` |
| VERIFY (small) | `$1B00-$1FC1` | 1,280 bytes | `$1FC2-$1FFF`: its copy of the service table |
| DOCVIEW (its own case in the Makefile) | `$1B00-$3D5F` | 8,800 bytes | `$3D60-$3FFF` (672 bytes) |
| NRCLIP (`sdk/nrclip.cfg`) | `$1B00-$1FFF` in place, a part copied to `$0C00-$0FFF` with the BSS, the entry run at `$2000` | 9,472 bytes | the hi-res page, once the entry is done; `$0C00` is the second ProDOS buffer, so never two files open |
| GMAGIC (`sdk/gmagic.cfg`) | as NRCLIP (`GMLOW` and `GMBSS` at `$0C00`) | 9,472 bytes | `copy_buf` for tables, the note buffer as its read buffer until it returns, and the 112-byte heads of the main text page's 128-byte blocks (font, row patterns) once the hi-res screen is on -- never the screen holes or `$06F7` |

The Makefile writes `build/name.map` (or `build-6502/name.map`) and checks
code **and BSS** against the window. Add an overlay using `$3000` scratch
to `XPLUGINS_SCRATCH`; VERIFY has a separate `$1FC2` ceiling for its table.

The disk copies are `A2FILE/NAME.PLG` (upper case). The 140K boot floppy
carries only the ones named in `XPLUGINS_FLOPPY` (Makefile: MOVE and
VERIFY); the 800K `.po` and the two XL `.2mg` carry them all, and
`config/packages.mk` gives each its `!` menu category disk. The current
size of each and its room in its window are in
[`docs/MEMORY-BUDGETS.md`](../../docs/MEMORY-BUDGETS.md).

## What the core does around a call

- The menu (`!`) loads the file at `$1B00` and calls `entry(api)` with
  `api->arg == 0`. `api->selected` is a copy of the entry under the cursor
  (`name[0] == 0` if the panel is empty), `api->full` its complete ProDOS
  path (`""` if it does not fit in 80 characters), `api->panels[*api->active]`
  the active panel, `api->other_full` the same path in the other panel.
- After a **big** overlay returns, the core re-reads and redraws both panels,
  reselects `api->reselect` (a name) in the active panel if set, and writes
  `api->note` (79 characters) on the message line. The entry tables are covered while a big overlay runs: it must use
  `api->selected` or reread directories, and leave panel restoration to the core.
- After a **small** overlay returns, the core only redraws the message line.
  If you changed the disk, call `api->read_panel(0)`, `api->read_panel(1)`
  (each returns 1 on success) and `api->draw_all()` yourself. If you drew a
  full screen (`api->clrscr()`), end with `api->draw_all()`.
- Nothing zeroes the BSS: never rely on an uninitialised static being 0.
  An initialised static (`DATA`) is loaded from the file and is fine.
- The C stack is the program's: about **90 bytes** are yours. Keep locals
  small, no recursion, no big arrays on the stack. Put buffers in the
  scratch memory above.
- Do not write to the zero page, and leave no interrupt installed when you
  return (`OVERLAY_AUDIO` overlays silence their card and stop its timer).
  A big overlay owns `$2000-$3FFF` while it runs, minus what its group
  keeps (table above): the entry tables and the `$3000` snapshot there are
  rebuilt by the core on return.

## The table, in short

Read `struct A2fcApi` in `src/a2fc_plugin.h`; the useful parts:

- **Panels.** `struct Panel`: `path` (`""` = the volume list), `count`,
  `cursor`, `e[i]` (`struct Entry`: `name`, `type` (`0x0F` = directory,
  `".."` is the parent), `access` (bit 7 clear = locked), `aux`, `blocks`,
  `size`, `mdate`), `tags` (bit `i & 7` of `tags[i >> 3]`; set them and call
  `api->draw_all()`), `fs` (`FS_PRODOS` = 0; else a read-only image or
  DOS 3.3 disk: refuse to write there), `free_blocks`, `total_blocks`.
  In the volume list an entry is a volume: `name` = `"/VOL"`, `mdate` = its
  ProDOS unit number **shifted right by four** (`read_volumes` stores `b >> 4`),
  so `READ_BLOCK` wants `mdate << 4`; `aux` = free
  blocks, `blocks` = total blocks.
- **Change directory.** `api->strcpy(pan->path, "/VOL/DIR")`, `pan->first =
  0`, `api->read_panel(index)`, then `api->draw_all()`; set `api->reselect`
  to land the cursor on a name (big overlays) or search `pan->e[]` and set
  `pan->cursor` yourself.
- **Paths.** `api->build_full(buf, pan, e)` writes the full path of an
  entry (returns 0 if too long). `api->cfg_path` (version 2) is
  `"/VOL/A2FILE/A2FILE.CFG"`: cut at the last `/` for the program directory,
  where an overlay keeps its own file (`GOTO.CFG`...) and where the program
  booted from.
- **Screen.** `api->message(s)` on line 22 (79 characters); prefix `s` with `"\1"`
  for a question in inverse video (the marker is not displayed and normal
  video is restored after printing). `api->confirm(s)` asks in inverse video
  (Y/N); `api->prompt(label, initial, hex)` reads into `api->input`: a ProDOS
  name (letters, digits, `.`, upper-cased) or, with `hex != 0`, exactly `hex`
  hex digits, also in inverse video; returns 0 on Escape. It refuses `=`, `?`, spaces: for a
  free pattern, read keys yourself with `api->cgetc()` and echo with
  `api->cprintf`. `api->progress_bar(name, done, total)`, `api->keys_bar(x,
  "KEY Label,KEY Label")`, `api->bar_begin()`, `api->wait_key()`, and the
  conio set: `clrscr`, `gotoxy`, `cputs`, `cputc`, `cprintf`, `revers`,
  `cclearxy`, `cgetc`. Keys: `KEY_UP`... in the header, `KEY_ESC` = 27.
- **Files.** `api->fopen(path, "rb"|"wb")`; before `"wb"` set
  `*api->filetype` and `*api->auxtype` (cc65 reads them at creation);
  `fread`, `fwrite`, `fseek`, `fclose`, `remove`. `api->dir_open(path)` /
  `api->dir_next()` (fills `*api->dir_entry`: `name`, `type`, `access`,
  `aux`, `blocks`, `size`, `mdate`, `key`...) / `api->dir_close()`: **one
  directory open at a time**, so a tree walk keeps a queue of names, not a
  recursion. `dir_next` also ends on a read error or a damaged entry: the
  value `dir_close` leaves in A (declared `void` in the frozen table) is
  non-zero then, and FIND reads it to say "some paths skipped" (see
  [`sdk/README.md`](../../sdk/README.md)).
- **ProDOS.** `api->mli(cmd, params)` runs one MLI call and returns the
  ProDOS error (0 = ok). Parameter blocks are cc65 structs (no padding):
  `READ_BLOCK $80` / `WRITE_BLOCK $81` `{3, unit, buffer*, block}`;
  `RENAME $C2` `{2, old*, new*}` (Pascal strings: a length byte then the
  characters; works on `"/VOL"` to rename a volume); `SET_FILE_INFO $C3`
  `{7, path*, access, type, aux, ?, ?, mdate, mtime, cdate, ctime}` after a
  `GET_FILE_INFO $C4` `{10, path*, ...}` of the same shape. Only the
  modification date/time belongs to the seven SET_FILE_INFO parameters;
  creation date/time is returned by GET_FILE_INFO and stays unchanged by SET. `ON_LINE $C5` `{2, unit, buffer*}` gives a volume name per unit
  (16 bytes: length-in-low-nibble byte then the name; unit 0 = all, 16
  entries); `GET_TIME $82` `{0}`. The system date is `$BF90-$BF91` (day 5
  bits, month 4 bits, year 7 bits, from bit 0), the time `$BF92` (minute) and
  `$BF93` (hour); `MACHID` `$BF98` bit 0 says a clock is present.
- **C library.** `sprintf`, `memcpy`, `memset`, `strcpy`, `strcmp`, `strlen`.
  Anything else you need, write it.
- **Destructive commands** ask for the word `ERASE` (`api->prompt("Type
  ERASE to confirm", 0, 0)` then `strcmp(api->input, "ERASE")`), like
  `DISKIMG`.

## Pitfalls met so far

- **cc65 2.19 miscompiles `BUF[i++] = c`** when `i` is an `unsigned char`
  static and `BUF` a constant address (`(char*)0x3200`): it increments before
  the store. Write `BUF[i] = c; ++i;` (found by MDVIEW).
- **In inline assembly, a `jsr`/`jmp` to a label defined further down the
  same function is taken for an external symbol**, and ld65 ends on
  `Unresolved external`. Backward jumps are fine, and so are branches in
  both directions (`bne`, `beq`...). Cure: make the target a real static
  function and `jsr %v` it, or turn the jump into an unconditional branch
  (found by TAGPAT).
- **`#<%v+2` is read by ca65 as `(<%v)+2`**, so the high byte gets the
  offset too. Write `#<(%v+2)` and `#>(%v+2)`.
- **Every service call costs 25-40 bytes** of cc65 glue. A small overlay
  with many calls will not fit; `volname.c` shows the cure: 6-byte stubs
  (`ldy #offset; jmp tramp`) behind one plain-6502 trampoline, compiled with
  `#pragma optimize(off)`, and inline assembly for the hot loops (1,712 ->
  1,087 bytes).
- **A big overlay covers the entry tables** (`$2000-$3FB7`: two panels of
  140 entries of 29 bytes), so on entry the
  panels' names and tags are gone, and it must NEVER call `api->read_panel`
  or `api->draw_all`: those refill the tables straight over its own code and
  scratch. The core rereads, restores the tags and redraws by itself when a
  big overlay returns, and its last words must go through `api->note`. API v5 snapshots the active entries at `$3000` before loading a big overlay.
  FIXTYPES uses this immutable snapshot, with code/BSS linked below `$3000`;
  the 140 entries occupy 4,060 bytes. Other big overlays may overwrite it
  with their own scratch and instead enumerate via `dir_open`/`dir_next`.
  TAGPAT, RENAME and DATE remain small. Panel tags live outside this window.
- **A small overlay changes nothing on screen by itself**: after it returns
  the core redraws only the message line, so call `api->read_panel(0)`,
  `api->read_panel(1)` and `api->draw_all()` yourself when you touched the
  disk.
- **`api->ram_format()` overwrites MAIN `$2000-$21FF`**: the /RAM driver's
  FORMAT writes a block into the buffer A2FC hands it. A big overlay whose
  code runs through that range after the call drops to the monitor (PT3
  did, on its way out, 2026-10-03); keep it clear or save it around the
  call. **`api->aux_consent()` (API v6) overwrites `copy_buf`**: ram_empty
  reads /RAM's directory block there. PT3 staged its engine's first chunk
  in copy_buf across the question, and AUX received /RAM's directory.
- **Renaming the boot volume** invalidates `api->cfg_path` (the core loads
  overlays by that absolute path); VOLNAME rewrites it in place.
- **cc65 2.19 miscompiles `BUF[i]` with a 16-bit `i` when `BUF` is a
  page-aligned constant address** (`(unsigned char*)0x2400`): it adds the high
  bytes into `ptr1+1` and indexes with the low byte, but never writes `ptr1`
  itself, so the read lands wherever the previous library call left it. The
  host tests cannot see it. Walk such a buffer with a pointer (found by DUET,
  whose validator accepted a truncated song).
- **A cycle-counted loop must not cross a page** (a taken branch then costs
  one more cycle): put it in the `LOOP` segment of `sdk/plugin.cfg`, which
  ld65 aligns on 128 bytes, `.align 128` before it, and `.assert` that its
  first and last bytes share a page. Branches cannot leave a segment: exit
  through a `jmp` placed inside it (DUET).

## Bench

Most overlays have `bench/name.py`, built on `bench/xplug.py`, and are
listed in `BENCHES` of `bench/plugins.py`, which runs them in groups
(`bench/all.py` and [`bench/README.md`](../../bench/README.md) have the
inventory and the ports): it stages a
hard disk from `BUILD/vol` plus your `.PLG` and the test files, boots it in
POM2, and `menu_run(s, p, 'NAME')` runs the overlay on the selection. Read
`bench/xplug.py`, `bench/plugin.py` and `bench/pom2.py` (`Session`: `rows`,
`has`, `key`, `type`, `select`, `wait`, `cursor_row`, `ok`). Every check is an
`s.ok(label, condition, detail)`; end with `sys.exit(ok_all(s))`. Use the
port assigned to your overlay. Run it with `python3 bench/name.py` from the
root once `make build-6502/name.PLG ARCH=6502` (floppy edition, the
default) or `make build/name.PLG` with `A2FC_IMG=A2FILECMD-full` (complete
edition) is done. Test files are host files staged by `tools/mkvolume.py`: a host name
`NOTE.TXT` becomes the ProDOS file `NOTE` of type `$04` (the suffixes `.TXT`
`.BIN` `.BAS` `.SYS` `.SYSTEM` set the type and are dropped), and
`NAME#TTAAAA` sets type `$TT` and auxtype `$AAAA` explicitly; any other name
is a `$06` BIN with the name kept. Check what the disk holds afterwards by reading the `.hdv`
back on the host (`tools/prodos_read.py`, or the ProDOS structures directly)
rather than trusting the screen alone. Mind that POM2 never writes the
boot `.hdv` back to the host: anything you must verify on the host has to
be written to a floppy in drive 2 (`boot_hd(..., floppy2=po)`, a `.po` made
with `tools/mkvolume.py`, flushed when POM2 stops), as `bench/txtconv.py`
does. Two more facts learned the hard way: after a **big** overlay the core
clears the screen and redraws, so its last words must go through
`api->note`, not `api->message`; and `api->progress_bar` shows the core's
own file counters, which the core resets to "1/1" before every overlay.

## Progress: never a still screen

Anything that can last more than a few seconds at 1 MHz -- a volume walk,
a whole file read, copied, converted or read back -- must move something
on the screen, or it passes for a crash:

- `api->progress_bar(name, done, total)` on row 22. Only the first **15
  characters** of `name` show: a label with its escape key reads "Rescue
  (ESC)", not "Recovering (ESC cancels)". It redraws only when a cell of
  the bar or the `name` pointer changes, so a pass must start with
  `done == 0`, which always redraws: a verification pass that restarts at
  0 is visible, and a static `name` buffer shared by every file (a
  directory entry) still shows each new file. The same call with the same
  values only turns the activity cell -- useful inside retries.
- With no room for a bar, `spin()` (`spin.h`, 15 bytes) or the same four
  instructions inline (12 bytes) turns the resident's activity cell, row
  21 column 79 of the MAIN text page, between / and \. Call it once per
  block or per file, not in a loop that may run an even number of times
  between two reads, or the glyph stands still. Never from DGRVIEW: a
  lo-res picture is the text page.
- A picture viewer decodes behind the core's "Loading NAME" screen, which
  stays in text: the activity cell is safe there, a conio call after the
  decoder turned 80STORE off is not.

The host harnesses (`tools/test_*.py`) record every bar their stub
receives; a new long loop comes with a test that the bar moves in it.
