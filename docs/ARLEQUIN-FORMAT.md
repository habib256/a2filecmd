# Arlequin pictures (Le Chat Mauve, 1985)

ARLEQUIN 1.1 is the double hi-res graphics interpreter Le Chat Mauve sold
for its Féline RGB card: `GLI16.2`, an Applesoft `&` extension, on the
maker's ProDOS demonstration disk (`/ARLEQUIN`, side 2). Its pictures are
ProDOS files of type `$F8` (auxiliary type `$0385` for the full-screen ones,
`$0000` for the windows) drawn by `& LOAD (x, y, "NAME")`. They are not
Purplesoft GRLOAD pairs: `/GISTDATA/IMG/PURPLE` holds eleven of them, and
PURPLE rightly refuses them.

| Offset | Meaning |
| --- | --- |
| 0 | Width in groups of seven colour cells, 1–20 (20 = 140 cells, the screen) |
| 1 | Height in rows, 1–192 |
| 2–3 | Signature `gs` ($67 $73) |
| 4… | The stream |

A group of seven cells is two byte columns, each one auxiliary byte and one
main byte: a row is `4 × width` bytes, auxiliary then main, column by column.
Rows go top to bottom. `& LOAD (x, y)` puts the left edge at byte column
`2x` and the bottom row at Arlequin line `y`, counted from the bottom of the
screen: the seasons (9 × 81) at `(5, 65)` start at column 10, screen row 46.

| Stream byte | Meaning |
| --- | --- |
| `$80`–`$FF` | One byte as it is; it becomes the last byte |
| `$00` | Toggles the output mask between `$FF` and `$7F` (bit 7: colour or black and white in the mixed mode) |
| `$01`–`$7F` | A run of `c AND $3F` bytes, 0 meaning 256. The last byte keeps its low seven bits and takes bit 7 from bit 6 of `c`; each byte of the run is the last byte rotated left by one, bit 7 into bit 0, and becomes the last in turn |

Every output byte is `(v OR $80) AND mask`. A run may cross rows. A
four-dot colour pattern rotated by one bit is the same colour one byte to
the right, which is what the runs are for.

**How this was established.** The decoder was read in GLI16.2's relocated
language-card code (`$D46C`–`$D4B8`: the self-modified mask at `$D4A8`, the
run counter at `$D504`, the skip counter at `$D4AA` for clipping, the
auxiliary-then-main store loop at `$D4DB`). The Arlequin demonstration disk
was then booted under POM2 with a Féline card: after the real loader drew
MOTO, AIGLE, MAMMOUTH, FEN and FE1–FE4, the main and auxiliary pages were
read back and matched the reference decoder byte for byte (the windows at
column 10, row 46). All eleven pictures consume their stream exactly.

**In A2 File Cmd.** `tools/arlequin_ref.py` is the reference decoder and an
encoder for synthetic pictures (the maker's pictures are not distributed
here). The ARLEQUIN overlay centres a picture smaller than the screen on
black, shows it in the card's mixed mode (as EXTASIE does), checks the whole
stream before writing the auxiliary bank, and rebuilds `/RAM` afterwards.
`tools/test_arlequin.py` runs the 6502 decoder under sim65 on both
processors, with the maker's pictures when `/GISTDATA` is available;
`bench/arlequin.py` runs the overlay under POM2 with a Féline card.
