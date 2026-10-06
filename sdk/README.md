# Writing an overlay for A2 File Cmd

An **overlay** (plugin) is a file `A2FILE/NAME.PLG` that A2 File Cmd loads at
`$1B00` on demand and runs on the entry under the cursor. The program's own
commands are overlays (see `src/overlay.s`), and a third party can add one
without touching the program or rebuilding it: the overlay appears in the
overlay menu (the `!` key) and runs on the current selection.

A third-party overlay knows **nothing** of A2 File Cmd but the file
[`../src/a2fc_plugin.h`](../src/a2fc_plugin.h): no address of the program, no
function linked from it. Everything goes through the **service table**
(`struct A2fcApi`) that the core hands to its entry point. This table is the
stable ABI: its fields do not move, new ones are only appended at the end, and
`api->version` says which one you got. That is what lets an overlay compiled
once survive later versions of the program.

## The model: `hello.c`

[`hello.c`](hello.c) is a complete overlay. It has three parts:

1. **The header** `struct Overlay` (here `struct PluginHeader`), placed in the
   `OVLHDR` segment so that it comes **first** in the overlay (`$1B00`):
   - the **signature** `PLUGIN_MAGIC` — this is how the core recognises a
     third-party overlay and refuses a `.PLG` from another build of the program;
   - a **flags** byte — `0` for a small overlay (`$1B00-$1FFF`, 1,280 bytes),
     `OVERLAY_BIG` for a big one, which also takes the graphics page
     `$2000-$3FFF` (then link with `-D __OVLSIZE__=$2500`, the symbol
     [`plugin.cfg`](plugin.cfg) sizes `RAM` with; the core sets the tags
     aside and rereads both panels when a big overlay returns);
   - add `OVERLAY_AUX` when the overlay uses auxiliary memory belonging to
     the ProDOS RAM disk: the core requires explicit consent before entry,
     including a cached overlay. `OVERLAY_BIG` alone does not authorize AUX
     destruction. Rebuild the RAM disk on every exit after damaging its memory;
   - add `OVERLAY_AUDIO` for foreground sound: the core passes the detected Mockingboard slot in `api->arg` (0 if absent).
     This hardware-only probe preserves AUX. The overlay must silence its
     output and disable its timer interrupt before returning;
   - the **address of the entry point**;
   - three reserved bytes, then a one-line **description**, shown in the menu,
     which displays its first 51 characters (`struct MenuItem` in
     `src/a2fc.c`; the 65 of the header's comment is the column width).
2. **The entry point** `void __fastcall__ plugin_entry(const struct A2fcApi*)`.
   The core calls it on the selection. `api->panels[*api->active]` is the
   active panel, `api->selected` the entry under the cursor (copied out of the
   tables, `name[0] == 0` if the panel is empty), `api->full` its complete
   ProDOS path, `api->arg` the key that called (`0` from the menu).
3. **The calls into the table**: `api->message`, `api->confirm`, `api->prompt`,
   `api->fopen`/`fread`/`fwrite`, `api->dir_open`/`dir_next`/`dir_close`,
   `api->mli`, and the usual C functions (`sprintf`, `memcpy`, `strcpy`...).
   The complete list is in `struct A2fcApi`.

   `dir_next` returns 0 at the end of the directory **and** when a block
   cannot be read or an entry is malformed. To tell the two apart, read the
   value `dir_close` leaves in A: non-zero means the listing was cut short.
   The table declares `dir_close` as `void` (the ABI is frozen), so declare
   your own pointer type to read it, as FIND does:
   `((unsigned char (*)(void))api->dir_close)()`. Cores before 0.9.6 leave
   an unrelated value there.

## Building

    ./sdk/build.sh sdk/hello.c HELLO   # -> build/HELLO.PLG

`build.sh` compiles the C for the cc65 `apple2enh` target (the 65C02
edition's: the zero-page addresses and the C stack coincide), then links it with `ld65`
on [`plugin.cfg`](plugin.cfg) and the `apple2enh` library — **without** crt0:
an overlay is not a program, it is called inside the cc65 context that A2FC
already holds. The result is a raw BIN to be placed under `A2FILE/HELLO.PLG`
(ProDOS type `$06`, address `$1B00`), next to `A2FILE.CODE`. From the root of
the repository, `make example` does the same thing. `build.sh` has no 6502
switch: for the 6502 edition compile with `-t apple2` and link with
`apple2.lib`, as `bench/plugin.py` does for that build.

The main Makefile also discovers `src/plugins/NAME.c`. A matching `NAME.s`
is assembled and linked as an optional helper (see VERIFY and VOLINFO's
service-call trampolines). Their linker limits reserve the fixed API copies
above code and BSS; keep those limits in sync with the assembly tables.

## Frozen for 1.0

From release 1.0, what an overlay compiled once depends on does not change:
`struct Entry` (29 bytes), `struct Panel`, `struct DirEntry` and the overlay
header `struct Overlay`, field for field; the first 54 fields of
`struct A2fcApi` (`version`, `arg` and 52 pointers: API version 5), then `aux_consent` (version 6), in order; `PLUGIN_MAGIC`,
`MEDIA_PLUGIN_MAGIC`, the `OVERLAY_*` flags and windows, `MAX_ENTRIES`,
`PATH_LEN`, `NAME_LEN`, `ROWS`, the `FS_*` values and `ENTRY_SNAPSHOT` at
`$3000`. A new service is appended after `aux_consent` and raises
`A2FC_API_VERSION`; an overlay that needs it checks `api->version` first.
The settings file `A2FILE.CFG` keeps its text layout as well.
`tools/test_abi_freeze.py`, part of `make test`, fails on any other change.

## Rules to keep

- **No uninitialised static that must be zero**: nothing clears the overlay
  window. For state, use `api->copy_buf` (512 bytes on loan) or `api->input`,
  or the C stack (local variables). An **initialised** static (`DATA`) is
  loaded from the file and is fine.
- **Stay inside the window**: `$1B00-$1FFF` for a small overlay. `ld65`
  reports it when the code overflows `RAM`.
- **Do not compile with `--all-cdecl`**: `cprintf` and `sprintf` are variadic
  (cdecl), everything else in the table is `fastcall`.
- **Test it**: `python3 bench/plugin.py` builds `hello.c`, puts it on a
  floppy, opens it with `!` and checks that it runs in POM2.

All plugins must follow [the data-safety rules](../AGENTS.md): exclusive
creation, preservation of originals during replacement, checked I/O and
cleanup limited to files owned by the current operation. Declaring flags is
not a sandbox: a third-party plugin is native code and must be audited.

### API 4: foreground media

`media_key(key)` accepts Escape or an available Left/Right neighbour; a true
result asks the overlay to finish normally, silence its hardware and clean up.
`media_wait()` waits for such a key. `music_info(header)` displays the bounded
PT3 title/credit fields of an already validated header (98 readable bytes).

Overlays requiring these services use `MEDIA_PLUGIN_MAGIC` (`$A2FD`), so older
cores refuse them instead of calling absent API fields. Ordinary `$A2FC`
overlays remain supported and earlier API fields retain their offsets.
The core coordinates the built-in music and specialized image viewers by
name; it probes files read-only and preserves AUX consent before each load.

### API 6: conditional AUX consent

`aux_consent()` is the question `OVERLAY_AUX` asks before an overlay runs,
for an overlay that only sometimes needs the auxiliary bank (PT3: GROUiK's
engine when the module fits, pt3_lib otherwise). It answers 1 without a
question when /RAM is on line and holds no file, or when the user already
accepted while leafing through the same media folder; otherwise it asks
"ALL /RAM files will be LOST. Continue?". Call it before the first AUX
write; on 0, write nothing there and take your main-memory path. It
overwrites `copy_buf` (it reads /RAM's directory block there): keep nothing
you still need in it across the call. After any AUX write, call
`ram_format()` and say so in `api->note` -- and know that `ram_format()`
itself overwrites MAIN `$2000-$21FF` (the /RAM driver's FORMAT writes a
block into the buffer it is given): no code or data you still need may lie
there, or save it around the call (`src/plugins/ppt3/driver.s` does). Check
`api->version >= 6` first.

Either way of asking (`OVERLAY_AUX` or `aux_consent()`) also tells the core
that AUX may be damaged until the overlay returns: a Ctrl-Reset meanwhile
makes the program's exit rebuild /RAM (`aux_dirty`, `src/crt0.s`). An
overlay that asks its own question instead does not get that.
