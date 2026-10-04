# PT3 decoder provenance and A2FC adapter

Since 2026-10-03 this is PT3.PLG's **fallback** player: GROUiK / French
Touch's player (`../ppt3/`) plays a single module of 32 KB or less when the
auxiliary memory may be used; pt3_lib plays TurboSound pairs, larger
modules, and everything when the user keeps /RAM or `A2FILE/PPT3.BIN` is
missing. The comparison of the two (`tools/pt3_compare.py`,
`../ppt3/README.md`) found pt3_lib behaviours that differed from Bulba's
players; fixed on 2026-10-03 (`tools/test_pt3_fixes.py`, each fix
mutation-checked):

- a pattern always ended at row 64 (`eor #64` in the line advance);
  Vortex Tracker patterns can be longer. It now ends where its channels end
  ($00, early_end), the line counter stopping at 255 instead of wrapping;
- the envelope offset of a sample was added unsigned (`adc #0` into the
  period's high byte): it is sign-extended now. Its down path also kept
  the carry of a `bcs`, so every negative offset came out one too small
  (-15 for -16); both paths clear it now;
- in this build (no `PT3_USE_ZERO_PAGE`), `handle_onoff` reloaded its
  countdown (`lda note_a+NOTE_ONOFF,X; tay`) instead of storing it, so the
  on/off effect never muted a channel: `tya; sta` now.

Channels still start with sample 1, where Bulba's ZX player starts with a
silent built-in sample (by design: AY_Emul's choice).

`core.inc`, `init.inc` and `zp.inc` originate from Vince Weaver's
[pt3_lib](https://github.com/deater/dos33fsprogs/tree/master/music/pt3_lib),
version 0.5 (upstream README), retrieved on 2026-09-12. A2FC uses the **0BSD**
option of the upstream dual licence; `LICENSE` retains the upstream declaration.
The original author and optimization credits remain in the sources.

A2FC changes:

- Every indirect module read goes through an address guard; each decoder call
  has a finite input-read budget. Bad pointers and nonterminating command runs
  return to the caller with an error.
- Decoder calls save and restore CPU interrupt/decimal state and zero page
  `$60–$7F`. They never access auxiliary RAM. No IRQ vector is installed.
- The 448-byte note/volume tables use the service table's 512-byte `copy_buf`,
  independently of source reads. Only explicitly listed operands are relocated.
- Code/BSS stop below `$3700`. Headers occupy `$3700–$3AFF`, the initial
  three cache pages `$3B00–$3DFF`, and the second tables `$3E00–$3FBF`.
  After both initializations, two linker-checked whole init-code pages and
  unused header pages become cache: 5–8 pages depending on order-list lengths
  and whether there are two modules. Only runtime operands are patched then;
  tests poison the reclaimed code and ensure it stays untouched by patching.
  No auxiliary memory is borrowed. An initial complete scan establishes the
  actual source size, up to 65,535 bytes including a possible TurboSound footer.
- Replacement uses a bounded second-chance scan. Sample and ornament reads
  mark a page as recently used; streaming pattern reads preserve an existing
  mark but do not promote cold pages. The physical mapping stores the mark
  in bit 6, cleared before address use. Only the selected slot's own mapping
  is invalidated before I/O; stale tags cannot invalidate headers or peers.
- Decoder pointers are logical file offsets. Each guarded read checks overflow
  and subfile EOF before adding its physical file base and consulting the page map. Cache misses restore host zero page
  around resident seek/read calls, then restore decoder state. Failed reads
  never publish a cache mapping and abort playback. Source closure is checked
  on exit; slow media can cause playback delays.
- Playback polls the Mockingboard VIA timer at 50 Hz, writes one or both AY chips,
  supports pause, stops at the end of the order list, and silences on all exits
  after hardware start. The core supplies a hardware-only card probe.
- The unused loop-patch reference in upstream initialization stores the loop
  index in decoder state; A2FC plays once rather than looping automatically.
- Frequency tables 0–3 include the pre-3.4 variants.
  `tools/test_pt3_frequency.py` checks all 96 periods and emitted tones against
  the archived full upstream C tables on both CPUs, with/without conversion.
  Reference: [pt3_lib.c](https://github.com/deater/vmw-meter/blob/master/ay-3-8910/pt3/pt3_lib.c), retrieved 2026-09-12.
- Periods are converted from the ZX Spectrum 128's 1.7734 MHz AY to the
  Mockingboard's, clocked by the Apple II at 1.0227 MHz, by one routine
  (`conv_mb`) shared by the three tones (12 bits), the envelope and the
  noise (5 bits): (P x 1181 + 1024) >> 11, 1.0227/1.7734 within 0.09 cent,
  so every pitch is the ZX one to the rounding of the period (2026-10-03,
  user decision). It replaced a rounded x9/16 that played every module
  43 cents sharp (2.5 %); before that, upstream's four truncating inline
  copies put buzz basses up to 69 cents off their note, and lost the top
  bits of P x 8 for P >= 8192. `tools/test_pt3_conv.py` runs the routine
  under `sim65` on all 65,536 periods; `tools/test_pt3_frequency.py`
  checks every table and tone against the Mockingboard periods archived in
  `tools/pt3_frequency_reference.json`. The noise goes through the GUARD
  pair of zero page, free while a frame is output.
- The decoder's zero-page copies (`host_zp`, `song_zp`) live at
  `$3FC0-$3FFF`, above the second tables and GROUiK's driver, out of the
  code window (the sim65 harnesses, which move PT3_LOC, keep them in BSS).
- This compact decoder has one deferred special-effect slot per channel/row.
  Multiple deferred effects in one row are refused instead of silently losing
  the earlier command.
- Standard TurboSound: two PT3 subfiles followed by the 16-byte footer
  `PT3!`, first LE16 size, `PT3!`, second LE16 size, `02TS`. Both headers,
  exact disjoint lengths and each read are validated. The second subfile may
  start mid-page. The two decoders have separate persistent state and tables;
  one context swap per tick alternates processing order. An ended stream is
  silenced and never decoded again; its partner continues to its own end.
  Pause, Escape, track changes and errors silence both chips.
  Other multi-chip container variants remain unsupported.
- At 1 MHz, the compact dual fixture fits in cache and keeps 50 Hz; the sparse
  stress fixture takes about 8–10 seconds instead of its nominal 5.8 seconds
  on the tested IIe/IIc profiles, excluding the later panel redraw.
  Instrument-priority replacement reduces runtime misses from 156 to 105:
  enhanced IIe measures 8.20 s (previously 9.15 s), IIe 6502 8.23 s,
  and IIc/Mockingboard 4c 9.95 s. Compact pairs take 5.75–5.78 s.
  Since the exact Mockingboard conversion (2026-10-03: `conv_mb`, about 290
  cycles a period instead of about 100 for x9/16, skipped for periods of 0)
  a tick of a pair costs more: on POM2 at 1x the compact pair takes 5.87 s
  (6502) / 5.88 s (65C02) for its nominal 5.78 s, i.e. about 1.5 % slow, and
  the sparse pair 8.32-8.35 s (8.22 before). Single modules are unaffected
  (bench/pt3_large.py: 8.26-8.27 s, as before).
  Main-RAM cache pressure can therefore slow dual playback even on a hard disk.
  The implementation does not drop decoded frames to mask that limitation.

Tests: `tools/test_pt3.py` validates the C loader; `tools/test_pt3_conv.py`
the period conversion; `tools/test_pt3_clock.py` exhausts cache sizes 1–8,
reference masks and scan positions on both CPUs, including stale tags.
`tools/test_pt3_cache.py` runs the real guard and replacement policy, checks
instrument promotion and shared pattern pages, and compares complete small and
65,535-byte song output under sim65, forcing eviction and I/O failures while
checking zero-page restoration and offset overflow. `bench/pt3_large.py` checks
large-module transport, natural completion, stack bounds and unchanged source
volume/AUX at 1x speed on both CPUs. `bench/pt3.py` checks actual 6502/65C02 decoder output,
AY registers, pause/stop, malformed modules and AUX preservation using a
disposable POM2 trace host (`bench/build_pt3_trace.py`).

Channel-volume audit: `tools/test_pt3_volume.py` executes the complete assembly
decoder and output routine under sim65, on 6502 and 65C02, both with and without
clock conversion. Each run exercises 4,805 synthetic songs across versions
3.3–3.7: all 15 channel-volume settings and 16 sample amplitudes, distinct A/B/C
levels, changes to A without changing B/C, amplitude slides, envelope selection,
holds, rests, new notes and reinitialization. Generated volume tables are checked
against the archived reference tables; register bytes are captured at the VIA
data write. Module bytes and the unused tail of the shared table buffer are
checked for preservation. No volume-path defect was found in this audit.

All three channel volumes start at 15 on each song. C1–CF changes only the
addressed channel; C0 rests the note and does not select table row zero. Sample
amplitude, after sliding and clamping, is combined with that channel's volume
through the version-specific table. R8–R10 receive these values unchanged by
the ZX-to-Mockingboard clock conversion, which scales periods only.

Envelope mode is different from fixed volume: AY bit 4 selects the envelope
generator instead of the low four amplitude bits, as described in the
[General Instrument data manual](https://www.silicon-heaven.net/atom/howel/parts/ay3891x_datasheet.htm).
A2FC preserves that mode, rather than adding software attenuation absent on
the source AY. Register-level agreement does not establish identical analogue
loudness across AY/YM variants, output circuits or speakers; this audit does
not include new listening measurements on physical hardware.

`tools/test_pt3_dual.py` compares two interleaved assembly decoders with
independent runs on both CPUs, including differing table versions and effects.
The actual C transport also tests either stream ending first, on odd/even ticks.
`bench/pt3_dual.py` captures both actual AY buses, measures compact and sparse
pairs separately, and checks transport, frame counts, stack, AUX and source bytes.
