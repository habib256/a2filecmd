# Music Construction Set exports

`MCS.PLG` plays the two-staff, fixed-size Mockingboard export described by
Will Harvey's published `MUSIC SOURCE`. Select the exported file, press `!`,
open Music and choose MCS. A Mockingboard with two AY chips is required.
The player runs on both the 6502 and 65C02 editions.

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

## Editor files are a separate format

The studied editor disks contain `.OBJ` files with four-byte notation
records, and editor save files containing state plus those records. They
are not the fixed-size two-staff export. This implementation refuses them;
renaming an editor score to `.MCS` does not convert it. The suffix `.MCS`
is used only for the generated demonstration, not as a historical magic.
Editor-score conversion remains to be implemented.

## Written memory and hardware

The plugin writes its MAIN overlay, BSS, the `$3000-$38FF` song buffer and
the text screen. It does not use AUX, destroy `/RAM`, touch an IRQ vector,
or write the input file. Its foreground driver polls VIA timer 1. On exit
it silences both AY chips and restores the VIA ACR, IER, timer latch and
both chips' DDR configuration. It does not restore the previous timer
counter phase or replay previous AY sound registers.

## Validation and provenance

`tools/test_mcs.py` executes the actual production C with injected I/O
faults, every truncation, excess input, stale panel sizes, malformed notes,
chords, ties and controls. The C also runs under sim65 for both CPUs.
The actual assembly driver runs in the 6502 interpreter with observed
hardware writes and restored configuration. When the reference toolkit
disk is available, ten real songs are compared tick by tick with the
original 6502 player, not merely another translation.

`bench/mcs.py` uses a disposable ProDOS disk in POM2 to exercise menu
launch, AY sound, pause/resume, restart, tempo, Escape, natural completion,
malformed input, AUX preservation and the C-stack floor.

Reference: [Cybernesto's mcs-player](https://github.com/cybernesto/mcs-player),
revision `118279b8e73e023d11fe861bfc3dde539acbd94b`, MIT; Will Harvey's
published player is included there. Its license is preserved in
`data/licenses/MCSPLAYER.TXT`. No commercial editor or song is distributed.
