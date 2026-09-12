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
     `$2000-$3FFF` (then raise `RAM` to `$2500` in the `.cfg`);
   - add `OVERLAY_AUX` when the overlay uses auxiliary memory belonging to
     the ProDOS RAM disk: the core requires explicit consent before entry,
     including a cached overlay. `OVERLAY_BIG` alone does not authorize AUX
     destruction. Rebuild the RAM disk on every exit after damaging its memory;
   - add `OVERLAY_AUDIO` for foreground sound: the core passes the detected Mockingboard slot in `api->arg` (0 if absent).
     This hardware-only probe preserves AUX. The overlay must silence its
     output and disable its timer interrupt before returning;
   - the **address of the entry point**;
   - three reserved bytes, then a one-line **description**, shown in the menu
     (65 characters at most: the menu row uses all 80 columns).
2. **The entry point** `void __fastcall__ plugin_entry(const struct A2fcApi*)`.
   The core calls it on the selection. `api->panels[*api->active]` is the
   active panel, `api->selected` the entry under the cursor (copied out of the
   tables, `name[0] == 0` if the panel is empty), `api->full` its complete
   ProDOS path, `api->arg` the key that called (`0` from the menu).
3. **The calls into the table**: `api->message`, `api->confirm`, `api->prompt`,
   `api->fopen`/`fread`/`fwrite`, `api->dir_open`/`dir_next`, `api->mli`, and
   the usual C functions (`sprintf`, `memcpy`, `strcpy`...). The complete list
   is in `struct A2fcApi`.

## Building

    ./sdk/build.sh sdk/hello.c HELLO   # -> build/HELLO.PLG

`build.sh` compiles the C for the cc65 `apple2enh` target (the same as A2FC:
the zero-page addresses and the C stack coincide), then links it with `ld65`
on [`plugin.cfg`](plugin.cfg) and the `apple2enh` library — **without** crt0:
an overlay is not a program, it is called inside the cc65 context that A2FC
already holds. The result is a raw BIN to be placed under `A2FILE/HELLO.PLG`
(ProDOS type `$06`, address `$1B00`), next to `A2FILE.CODE`. From the root of
the repository, `make example` does the same thing.

The main Makefile also discovers `src/plugins/NAME.c`. A matching `NAME.s`
is assembled and linked as an optional helper (see VERIFY and VOLINFO's
service-call trampolines). Their linker limits reserve the fixed API copies
above code and BSS; keep those limits in sync with the assembly tables.

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
