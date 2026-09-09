# Service-table overlays

Every command added since 0.7.1 is a **service-table overlay**: a
`src/plugins/name.c` compiled and linked on its own, exactly like a third
party's (`sdk/`), and reaching the program only through `struct A2fcApi`
(`src/a2fc_plugin.h`). The resident is full, so nothing new goes into
`src/a2fc.c`; an overlay costs the resident nothing and appears in the `!`
menu with the description of its header.

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
    "Menu line: what it does, 65 characters at most"
};
#pragma rodata-name (pop)

void __fastcall__ plugin_entry(const struct A2fcApi* api) { ... }
```

`sdk/hello.c` is the model. The Makefile picks up every `src/plugins/*.c`:
`make build/name.PLG` (65C02, cc65 2.19) and `make build-6502/name.PLG
ARCH=6502` (6502, cc65 master) -- the same source must build for both, so
no 65C02-only inline assembly. A source that mentions `OVERLAY_BIG` is
linked as a big overlay: the Makefile looks for `PLUGIN_MAGIC, OVERLAY_BIG` on one
line of the source. The link refuses a file over its window:

| Overlay | Window | File at most | Scratch memory |
| --- | --- | --- | --- |
| small (`flags = 0`) | `$1B00-$1FFF` | 1,280 bytes | `api->copy_buf` (512), `api->input` (17), `api->other_full` (81, if you do not need the other panel's path) |
| big (`OVERLAY_BIG`) | `$1B00-$3FFF` | 9,472 bytes | the same, plus `$3000-$3FFF` (4 KB) **only if the ld65 map shows BSS ending under `$3000`** — the file size alone does not prove it, since BSS is not in the file |

The disk copies are `A2FILE/NAME.PLG` (upper case). The floppy edition
carries only the ones named in `XPLUGINS_FLOPPY` (Makefile); the `.2mg`
carries them all.

## What the core does around a call

- The menu (`!`) loads the file at `$1B00` and calls `entry(api)` with
  `api->arg == 0`. `api->selected` is a copy of the entry under the cursor
  (`name[0] == 0` if the panel is empty), `api->full` its complete ProDOS
  path (`""` if it does not fit in 80 characters), `api->panels[*api->active]`
  the active panel, `api->other_full` the same path in the other panel.
- After a **big** overlay returns, the core re-reads and redraws both panels,
  reselects `api->reselect` (a name) in the active panel if set, and writes
  `api->note` (79 characters) on the message line. It does the same tag
  bookkeeping: a big overlay may tag freely.
- After a **small** overlay returns, the core only redraws the message line.
  If you changed the disk, call `api->read_panel(0)`, `api->read_panel(1)`
  (each returns 1 on success) and `api->draw_all()` yourself. If you drew a
  full screen (`api->clrscr()`), end with `api->draw_all()`.
- Nothing zeroes the BSS: never rely on an uninitialised static being 0.
  An initialised static (`DATA`) is loaded from the file and is fine.
- The C stack is the program's: about **90 bytes** are yours. Keep locals
  small, no recursion, no big arrays on the stack. Put buffers in the
  scratch memory above.
- Do not write to the zero page, do not install interrupts, do not touch
  `$2000-$2FFF` from a big overlay unless the code needs it (the core
  covers the entry tables there, but MENU keeps its list at `$3000`; both
  are rebuilt on return).

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
- **Screen.** `api->message(s)` on line 22 (79 characters); `api->confirm(s)`
  (Y/N); `api->prompt(label, initial, hex)` reads into `api->input`: a ProDOS
  name (letters, digits, `.`, upper-cased) or, with `hex != 0`, exactly `hex`
  hex digits; returns 0 on Escape. It refuses `=`, `?`, spaces: for a
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
  recursion.
- **ProDOS.** `api->mli(cmd, params)` runs one MLI call and returns the
  ProDOS error (0 = ok). Parameter blocks are cc65 structs (no padding):
  `READ_BLOCK $80` / `WRITE_BLOCK $81` `{3, unit, buffer*, block}`;
  `RENAME $C2` `{2, old*, new*}` (Pascal strings: a length byte then the
  characters; works on `"/VOL"` to rename a volume); `SET_FILE_INFO $C3`
  `{7, path*, access, type, aux, ?, ?, mdate, mtime, cdate, ctime}` after a
  `GET_FILE_INFO $C4` `{10, path*, ...}` of the same shape (see the ProDOS 8
  TRM); `ON_LINE $C5` `{2, unit, buffer*}` gives a volume name per unit
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
- **Every service call costs 25-40 bytes** of cc65 glue. A small overlay
  with many calls will not fit; `volname.c` shows the cure: 6-byte stubs
  (`ldy #offset; jmp tramp`) behind one plain-6502 trampoline, compiled with
  `#pragma optimize(off)`, and inline assembly for the hot loops (1,712 ->
  1,087 bytes).
- **A big overlay covers the entry tables** (`$2000-$3FDC`), so on entry the
  panels' names and tags are gone, and it must NEVER call `api->read_panel`
  or `api->draw_all`: those refill the tables straight over its own code and
  scratch. The core rereads, restores the tags and redraws by itself when a
  big overlay returns, and its last words must go through `api->note`. An
  overlay that walks the tagged entries therefore has to be **small**
  (FIXTYPES, TAGPAT, RENAME, DATE); a big one reads the directory again
  through `dir_open`/`dir_next` (which uses the core's own buffer, not
  yours) and knows only `api->selected`.
- **A small overlay changes nothing on screen by itself**: after it returns
  the core redraws only the message line, so call `api->read_panel(0)`,
  `api->read_panel(1)` and `api->draw_all()` yourself when you touched the
  disk.
- **Renaming the boot volume** invalidates `api->cfg_path` (the core loads
  overlays by that absolute path); VOLNAME rewrites it in place.

## Bench

Each overlay has `bench/name.py`, built on `bench/xplug.py`: it stages a
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
own file counters, which an overlay cannot set (cosmetic).
