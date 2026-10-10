# Music Construction Set scores and exports

`MCS.PLG` plays the two-staff, fixed-size Mockingboard export described by
Will Harvey's published `MUSIC SOURCE`. Select the exported file, press `!`,
open Music and choose MCS. Paired editor scores can also be selected,
through their main file or `.OBJ` companion. A Mockingboard with two AY chips is required.
The player runs on both the 6502 and 65C02 editions.

For exports or paired editor scores on a real DOS 3.3 disk or inside a DOS-order DSK/DO/2IMG image,
select the BIN export, main score or `.OBJ` and choose **! → Music → DOSMCS**. This reads directly,
without extraction, a temporary or AUX storage. DOSMCS is included in the
800K/XL ProDOS editions; this does not extend the standalone DOS edition.

Keys: P or Space pauses/resumes, R restarts, + accelerates, - slows down,
Escape returns to the panels. Playback stops after one pass, at the point
where the original player restarts both staffs. It does not execute code
from the song, install an interrupt handler or write any file.

## File layout

An export is exactly 2,304 bytes: two buffers of 1,152 bytes. Each contains
two-byte records, `(pitch, flags)`. `pitch >> 1` indexes the original
64-entry AY period table; pitch must be below 128. The low six bits of
flags give a nonzero duration. Bit 7 continues a chord and bit 6 ties the
staff, suppressing volume decay. A pitch whose shifted value is zero with
flags zero ends the staff. Both staffs must contain at least one note and
a complete terminator; a chord cannot end in a terminator.

Bytes after the terminator are ignored: real exports preserve old buffer
contents there. The complete physical file must nevertheless be readable,
close successfully and have exactly the expected length before playback.
The panel's cached file size never bounds the read.

The original timer uses a `$40FF` latch, about 61.47 ticks per second on a
1.023 MHz machine, with four ticks per duration unit. Amplitude decays
from 10 to 8 every three ticks unless tied. Voice allocation, ties, decay
and all 64 periods follow the original player, including its final two
period values of 1.

## Direct DOS exports

DOSMCS uses the same sequencer and foreground hardware driver as MCS.
Its DOS reader checks a fresh catalog identity/name/type, VTOC, T/S lists,
sector ranges, aliases and BIN EOF. The logical payload must be exactly
2304 bytes; cached panel sizes never bound reads. Allocations beyond ten
logical sectors, including the four-byte BIN prefix, are refused rather
than truncated. Extra allocation padding is not played.

All payload bytes and both staff terminators must validate, and an image
file must close successfully, before playback starts. Sources are opened
`rb`; real drives use only READ_BLOCK. The 512-byte resident copy buffer
is reused for the current sector and the completed song is in MAIN
`$3700-$3FFF`. All loaded code is linked strictly below `$3700`.
The DOS import stages keep their BSS and a small handoff in MAIN
`$0C00-$0FFF`, the buffer ordinarily reserved for a second open ProDOS
file. They never keep two FILEs open: each source image closes before
an internal stage is opened, and the stage closes before execution.

Paired editor scores are imported directly too. DOSMCS validates both
fresh catalog identities and T/S maps, searches the full thirty-character
DOS names, rejects missing/duplicate companions and allocations shared
between the two files, then hands off to MCSIMPORT. Maps are bounded to
thirteen sectors for editor files; exports retain the ten-sector bound.
MCSIMPORT reads the state/notation using those validated maps, checks exact
lengths and closes the image. MCSPLAY runs the shared sequencer. Both
internal stages must be installed beside DOSMCS; they are hidden from the
menu. The handoff checks the sealed payload length, EOF, error flag,
close status, CPU/version tag and entry bounds before executing it.
No overwritten import code remains on the return stack.
The ProDOS program volume must stay accessible for loading these stages;
there are no mid-reader prompts to swap a single drive between that volume
and the DOS source. A missing stage fails without starting sound.
Other audio formats, neighbour navigation and a complete volume audit
remain separate work. Source changes during reading are not a snapshot.

## Paired editor scores

The supported Apple II editor layout has a 256-byte state header followed
by staff 0 records in the main file; `NAME.OBJ` contains staff 1 records.
Both files are required in the same directory/catalog. Select either file.
On ProDOS, for names longer than eleven characters, rename both extracted files with
the same shorter basename so the `.OBJ` suffix fits ProDOS's 15-character
limit. The importer does not guess truncated companion names.

Four-byte notation objects encode kind, vertical position and 16-bit
horizontal position. The importer supports notes, rests, chords, dots,
accidentals, key signatures, the two clef offsets, octave marks, beams and
the original exporter’s tie behaviour. Header start pointers must be
`$4100` and `$7400`, with aligned end pointers inside the editor's pools.
Positions must be ordered and objects within their staff's bounds.
End pointers identify the last unprocessed four-byte slot, which may hold
stale object bytes. Both physical file lengths, read status and closes
are checked before starting sound. No editor instructions are executed.

Conversion produces the existing two-staff export in MAIN. A silent or
shorter staff is padded with silent rests to play the longer staff fully;
an entirely empty score is refused. Each converted staff must fit 575
note/rest pairs, including padding. Unsupported layouts or objects are
refused rather than partially played.

Stored editor tempo, instrument and volume settings are not imported:
playback uses the existing Mockingboard sound and adjustable default tempo.
Second-staff ties follow the studied original exporter's omission. These
are explicit compatibility limits, not full editor playback emulation.
On DOS, full names are used directly; the main basename must leave room
for `.OBJ` within thirty characters. No commercial song is packaged
with the application.

## Written memory and hardware

The plugin writes its MAIN overlay/BSS below `$3680`, the `$3680-$3F7F` song buffer and
the text screen. It does not use AUX, destroy `/RAM`, touch an IRQ vector,
or write the input file. Its foreground driver polls VIA timer 1. On exit
it silences both AY chips and restores the VIA ACR, IER, timer latch and
both chips' DDR configuration. It does not restore the previous timer
counter phase or replay previous AY sound registers.
DOSMCS uses the same hardware policy, with its song at `$3700-$3FFF` and
the common DOS reader's metadata in MAIN, including its exclusive use
of the second-file buffer while no second FILE is open. Neither edition writes AUX storage.

## Validation and provenance

`tools/test_mcs.py` executes the actual production C with injected I/O
faults, every truncation, excess input, stale panel sizes, malformed notes,
chords, ties and controls. The C also runs under sim65 for both CPUs.
The actual assembly driver runs in the 6502 interpreter with observed
hardware writes and restored configuration. When the reference toolkit
disk is available, ten real songs are compared tick by tick with the
original 6502 player, not merely another translation.

`tools/test_mcs_score.py` executes the real importer on the host and both
sim65 CPU targets. It checks both selected filenames, controls, silent
staff padding, missing companions, every truncation, malformed records,
capacity, and injected read/close failures before hardware start. When the
private reference editor disk is available, nine saved scores are compared
with the original editor's conversion instructions in disposable 6502 RAM.

`tools/test_dosmcs.py` runs the production direct reader and sequencer on
the host and both sim65 processors: exact AY frames on real-driver/image
callbacks, all read failures, open/seek/close failures, stale sizes,
malformed chains/music and allocation limits, paired scores selected through
either file, full DOS names, duplicate/missing companions and cross-file aliases. Every source is byte-compared.
`tools/test_mcs_handoff.py` executes both actual native handoffs with
faults, truncated/oversized payloads and corrupt headers; it observes writes,
keeps the canonical song intact and checks CPU and C-stack balance.
`bench/dosmcs.py` runs native menu launch, audible AY output, controls,
bad-data rejection and natural end on a disposable write-protected Disk II
source, a DSK and a 2IMG. It compares source volumes, AUX and the C-stack floor.

`bench/mcs.py` uses a disposable ProDOS disk in POM2 to exercise menu
launch, AY sound, pause/resume, restart, tempo, Escape, natural completion,
malformed input, paired-score conversion, missing companions, AUX preservation
and the C-stack floor.

Reference: [Cybernesto's mcs-player](https://github.com/cybernesto/mcs-player),
revision `118279b8e73e023d11fe861bfc3dde539acbd94b`, MIT; Will Harvey's
published player is included there. Its license is preserved in
`data/licenses/MCSPLAYER.TXT`. No commercial editor or song is distributed.
