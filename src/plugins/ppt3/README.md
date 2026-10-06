# GROUiK's PT3 player in A2 File Cmd

`PT3.PLG` plays a ProTracker 3 / Vortex Tracker II module with this player
first, and with Vince Weaver's pt3_lib (`../pt3lib/`) when it cannot.

## Provenance and licence

- `original/ppt3.a` — "Vortex Tracker II v1.0 PT3 player for 6502", Apple IIe
  version, by **GROUiK / French Touch**, 2019, from the sources of the demo
  *One More Thing* (`OMT_020819/Sources/ppt3.a`, ACME 0.96.1 syntax).
  Translated and adapted from **S.V. Bulba**'s ZX Spectrum player
  (<https://bulba.untergrund.net/main_e.htm>, (c) 2004, 2007), with
  **Ivan Roshin**'s note-table and volume-table generators. Unmodified.
- `original/License.txt` — the archive's notice: the programs and sources are
  free software under the **GNU GPL, version 3 or later**. A2 File Cmd is
  GPLv3 as well. The demo's module (`rt-frag.pt3`) is not part of this
  repository.

## Files

| File | What it is |
| --- | --- |
| `ppt3.s` | The ca65 port of `ppt3.a`. Without `PPT3_A2FC` it assembles to exactly the bytes ACME makes of the original (`tools/test_ppt3_port.py`). Every A2FC change sits behind `PPT3_A2FC` or is a label added on an existing operand. Grouik's comments are kept as he wrote them. |
| `engine.s`, `engine.cfg` | The A2FC wrapper: header and entry, zero-page swap, read guards, push limit, ROUT's conversion without the card. Builds `A2FILE/PPT3.BIN`, the same bytes for both editions. |
| `abi.inc` | The addresses both halves agree on (assembled into both). |
| `notes.inc` | The ZX note tables INIT copies (see "Pitch for the Mockingboard"). |
| `hook.s`, `driver.s` | The main-memory half, linked into `PT3.PLG` at `$3B00` (sdk/pt3.cfg): the trampoline, the AUX copy, the loader and consent logic. |

## How it runs

```
AUX  $0800-$1FFF  untouched (ProDOS /RAM's bitmap $0C00 and directory $0E00)
     $2000-$32CC  engine image (PPT3.BIN, 4,813 bytes): code, the 7 ZX note tables
     $32CD-$3531  its variables, VT_ (built by INIT) and NT_ (copied by INIT)
     $3B00-$3B25  the trampoline's mirror (same bytes as main)
     $4000-$BFFF  the module, whole: 32 KB at most
MAIN $1B00-$36FF  PT3.PLG code and BSS (pt3_lib + the GROUiK hook)
     $3700-$38FF  SONG: the header the scan read (music_info, comparison)
     $3900-$3AFF  SECOND: staging buffer for every transfer to AUX
     $3B00-$3F3C  the driver (hook.s + driver.s); pt3_lib's cache once IT plays
```

1. `pt3.c` scans the whole file as before (length, header, TurboSound footer)
   and shows the player screen.
2. For a single module, `pg_setup` (driver.s): API v6 or later, 32 KB or
   less, `A2FILE/PPT3.BIN` present with this ABI's header (checked before any
   question). Then `api->aux_consent()` — no question when /RAM is empty. On
   no, pt3_lib plays: nothing was written to AUX.
3. From the first AUX write on, `aux` is set: pt3.c will call `pg_end`, which
   rebuilds /RAM and appends "/RAM rebuilt." to the note — whatever happens
   next, and pt3_lib is never used for this run (it would overwrite the
   driver). The engine image, the trampoline mirror, then the module, read a
   second time (its first 512 bytes must equal the scan's, its length must be
   the scan's, read/seek/close errors stop with "PT3 read/seek/close
   error."). **The source file is closed before the first note.**
4. `pg_call(0)` runs INIT; each 50 Hz tick of pt3.c's VIA polling runs
   `pg_call(1)` (PLAY) and pt3.c's own writer sends the 14 registers to the
   card (pause, Left/Right, Escape, silence on every exit: unchanged).

The trampoline (`pg_call`, hook.s) exists at the same address in both banks:
`sta $C003` switches instruction fetches to AUX, the engine runs with RAMRD
and RAMWRT on AUX, interrupts off, decimal mode clear; the registers are
copied back to main with RAMWRT main / RAMRD AUX; `sta $C002` returns.
`sta $C056` (LORES) first: under 80STORE, HIRES would route `$2000-$3FFF` by
PAGE2 instead of RAMRD/RAMWRT. Zero page and the 6502 stack stay in main
memory (ALTZP off).

## Every A2FC change to the player

- **Zero page**: Grouik's `$30`, `$51-$64` move to `$60-$74` (same layout),
  plus `$75-$76` for the guard pointer. The wrapper saves the host's
  `$60-$7F`, installs the engine's own copy, and restores the host's bytes on
  every exit, a guard trip included (tested around every call).
- **Read guards** (`MOD_LDA_C`, `MOD_LDA_L`, `MOD_LDA_IX`, `MOD_ADC_L`, 48
  sites): every read through a pointer derived from the module — pattern
  bytes, position list, pattern/sample/ornament pointer tables, sample and
  ornament data, the header in INIT — checks that the address lies in the
  module `[$4000, $4000+n)` or in the 6 bytes of the player's built-in empty
  sample/ornament (`EMPTYSAMORN`). Anything else is never read: playback
  stops with "Invalid PT3." ($C000-$CFFF can never be reached: the module
  ends at `$BFFF` at the latest). Flags and registers are preserved exactly
  as the original instruction would leave them (the carry passes through).
  The player's reads of its own tables (NT_DATA, T_, NT_, VT_, SPCCOMS,
  AddToEn, AYREGS) are left as they were: their pointers never come from the
  module (counted in `tools/test_ppt3_port.py`).
- **Read budget**: 255 guarded reads per call; a command stream that never
  reaches a row end trips.
- **Deferred commands**: the player pushes the address of each special
  command of a row on the 6502 stack. Those that do nothing (C_NOP: 0, 6, 7,
  10-15 — a channel reading on past its own `$00` end marker meets many)
  are no longer pushed (their only effect, on `z80_L/H`, is reproduced);
  more than 4 real ones in one channel decode trip. The stack stays within
  48 bytes.
- **Self-modified operands**: `MODADDR+7` and `MDADDR2+7` became labels on
  the operand (`MODADDR_H+1`, `MDADDR2_H+1`), because a guarded read is one
  byte longer than the original `LDA (zp),Y`.
- **Pitch for the Mockingboard** (2026-10-03, user decision): INIT no longer
  generates its note table. Grouik's generator divided Bulba's periods by
  1.7734 (a 1.000 MHz AY: 39 cents sharp on the Apple's 1.0227 MHz) and
  then applied Bulba's ZX fix-up to note 23 of the ST table, which in the
  scaled table gave `$02FD` instead of about `$0240` (five semitones flat).
  It also left sample tone offsets, slides and portamento steps in ZX units
  on that scaled base. Now INIT copies the ZX table of the module's table
  number and version (`notes.inc`, the very tables of
  `tools/pt3_frequency_reference.json`, ST note 23 = `$03FD`), the player
  computes everything in ZX units, as on the Spectrum, and the wrapper
  converts what it outputs: tone periods (12 bits), noise period (5 bits)
  and envelope period (16 bits), each `x 1181/2048` rounded, i.e.
  `x 1.0227/1.7734` within 0.09 cent -- exactly what pt3_lib now does
  (`conv_mb`). Every pitch then is the ZX one to the rounding of the
  period: within 2.5 cents wherever the period is 290 or more.
- **No card access**: `ROUT`/`ROUT2` are left out; `MUTE` and the end of
  `INIT` return instead. The envelope shape is `$FF` (do not write R13)
  when the player says `>= $80`. Grouik's ROUT wrote R13 on every frame
  (restarting the envelope each time) and alternated the two AYs of the
  card from frame to frame; A2FC's writer writes the first AY each frame
  and R13 only when it changes.
- **Play once**: `SETUP` bit 0 is set at INIT; bit 7 after PLAY means the end
  of the order list (result 2).
- **INIT refuses** a module bound outside `$40CA-$C000` (shorter than a PT3
  header, or past the AUX window).

What the player stores, it stores into its own variables: through
`(z80_IX),Y` with IX = ChanA/B/C or the volume table, through `(z80_L),Y`
into its note table, AddToEn and AYREGS, and into the 30 self-modified
operands it always patched. `tools/test_ppt3_engine.py` records every read
and write of the real image on real, crafted and randomly mutated modules.

## Tests

- `tools/test_ppt3_port.py` — ACME vs ca65 byte identity (skips without
  ACME: `brew install acme`), guarded-site counts.
- `tools/test_ppt3_engine.py` — the access audit (tools/mos6502.py), guard
  trips (pointers past the end or into `$C0xx`, a runaway stream, five real
  deferred commands, a sample offset on the empty sample, untrustworthy
  bounds), C_NOP runs, the stack bound, the A2FC engine's AYREGS frame for
  frame equal to the **original** player's given the same ZX note table
  (sim65), INIT's tables against the references, PPT3_OUT as the
  Mockingboard conversion of AYREGS, both CPUs.
- `tools/test_ppt3_driver.py` — the real driver, trampoline and engine under
  sim65 with a scripted service table: consent declined, API v5, too big,
  missing/foreign/stale engine file (no question, AUX untouched), read
  errors, short and long streams, close and seek errors, a module changed
  between the passes, an INIT trip — each with /RAM rebuilt once and said;
  AUX `$0800-$1FFF` never written; main `$2000-$21FF` restored around
  ram_format; host zero page preserved.
- `tools/test_pt3.py` — pt3.c's side of the hook.
- `tools/pt3_compare.py` — register streams of both engines (see below).
- `bench/pt3.py`, `bench/pt3_dual.py`, `bench/pt3_large.py`, `bench/media.py`
  — POM2, both editions.

## How GROUiK's player differs from pt3_lib

Measured with `tools/pt3_compare.py` (sim65, both engines, 400 modules of a
local corpus, 3000 frames each), after the 2026-10-03 fixes: **394 of 400
modules give the same 14 registers on every frame**, as written to the card,
and all 400 end on the same frame. Both convert every period the same way,
to the Mockingboard's 1.0227 MHz (`x 1181/2048`, 0.09 cent flat of
1.0227/1.7734): the median tone is 0.2 cent from the exact ZX pitch; the
spread (up to about 50 cents) comes only from rounding very small periods
(top notes, buzz envelopes). The six differences:

- **A note before any sample command** (ALEXWINSTO5, RNRT.A.D.30,
  RNRT.A.D.94, and CJEFFSIMPLE, where an on/off effect switches a channel
  on that never had a sample): GROUiK uses Bulba's built-in empty sample
  (silent), pt3_lib sample 1, as AY_Emul does. Left as each player has it.
- **Portamento over 256 periods or more** (DEBUGGERDEB, LUCHIBOB172):
  Bulba's ZX player, hence GROUiK's, tells the slide direction from the
  high byte of the accumulated slide; once a long slide passes 256 periods
  it takes it for the other direction and jumps to the target note a few
  frames early. pt3_lib compares signed values. Kept as the original plays.

Before the fixes, 348 of 400 were identical (with pt3_lib's ZX note table
imposed on GROUiK); the rest came from:

- **Pitch**: GROUiK's table was Bulba's divided by 1.7734 (a 1 MHz AY: 39
  cents sharp), with ZX-unit offsets and slides on that scaled base and ST
  note 23 at `$02FD`; pt3_lib's x9/16 played 43 cents sharp. Both now
  compute in ZX units and convert what they output (see "Every A2FC change").
- **Noise**: GROUiK halved it without masking it to 5 bits first (33 became
  16); pt3_lib multiplied by 9/16, truncated. Both now `(n & 31) x 1181/2048`.
- **Envelope period**: x 289/512 truncated vs x 9/16 rounded; now the same
  conversion.
- pt3_lib defects, all fixed (`../pt3lib/README.md`, `tools/test_pt3_fixes.py`):
  **patterns longer than 64 rows** cut at row 64 (13 of 400); **envelope
  offsets of samples** added unsigned, and one too small when negative;
  the **on/off effect** never muting (non-zero-page build); and, found while
  checking the last differences, an **amplitude slide** going up from -1 to
  0 that silenced the channel for one tick (DR.DISMALAC, FOXXRAIN281).

Classification from the first differing frame and register, each class
confirmed on its modules by reading both players' code at that frame.

