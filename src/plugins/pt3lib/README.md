# PT3 decoder provenance and A2FC adapter

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
- Code/BSS stop below `$3300`; a fixed 512-byte header occupies `$3300–$34FF`
  and eleven 256-byte FIFO cache pages occupy `$3500–$3FFF`. The read-only
  source can contain up to 65,535 bytes. An initial scan establishes its actual
  size without trusting panel metadata. The linker and runtime guards bound
  these regions; no auxiliary memory is borrowed.
- Decoder pointers are logical file offsets. Each guarded read checks overflow
  and EOF before consulting the page map. Cache misses restore host zero page
  around resident seek/read calls, then restore decoder state. Failed reads
  never publish a cache mapping and abort playback. Source closure is checked
  on exit; slow media can cause playback delays.
- Playback polls the Mockingboard VIA timer at 50 Hz, writes the first AY,
  supports pause, stops at the end of the order list, and silences on all exits
  after hardware start. The core supplies a hardware-only card probe.
- The unused loop-patch reference in upstream initialization stores the loop
  index in decoder state; A2FC plays once rather than looping automatically.
- Frequency tables 0–3 include the pre-3.4 variants.
  `tools/test_pt3_frequency.py` checks all 96 periods and emitted tones against
  the archived full upstream C tables on both CPUs, with/without conversion.
  Reference: [pt3_lib.c](https://github.com/deater/vmw-meter/blob/master/ay-3-8910/pt3/pt3_lib.c), retrieved 2026-09-12.
- The 1.77 MHz → 1 MHz period conversion (×9/16) is ROUNDED and computed
  without overflow, by one routine (`conv916`) shared by the three tones and
  the envelope. Upstream's four inline copies truncated: harmless on a 12-bit
  tone period, audible on the small envelope periods a buzz bass tunes to its
  note — AUTUMN.PT3's bass came out up to 69 cents sharp (EP 37 → 20 instead
  of 20.8); rounded, 27 at worst. The envelope copy also lost the top bits of
  P×8 for P ≥ 8192 and masked the result with a tone's `AND #$0F`. The shared
  routine is 81 bytes smaller than the four copies. `tools/test_pt3_conv.py`
  runs it under `sim65` on all 65,536 periods. The overall 9/16 ratio (vs the
  exact 0.5767) still plays every module 2.5 % sharp, uniformly.
- This compact decoder has one deferred special-effect slot per channel/row.
  Multiple deferred effects in one row are refused instead of silently losing
  the earlier command. TurboSound dual-module playback is not implemented.

Tests: `tools/test_pt3.py` validates the C loader; `tools/test_pt3_conv.py`
the period conversion; `tools/test_pt3_cache.py` compares complete small and
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
