# Additional readers

These plugins are available through `!`; supported content and metadata
also select readers automatically through Return/I. They read only: no disk output, AUX
memory, `/RAM` reconstruction, or execution of file contents.

| Plugin | Input and implemented output | Limits |
| --- | --- | --- |
| PASTEXT | Apple Pascal TEXT, 1 KB editor header and independent 1 KB chunks, DLE indentation | Text only; extracted file, not a Pascal disk |
| SCASM | S-C Assembler length-prefixed tokenized lines, line numbers, spaces and repeated characters | ProDOS INT/BIN through Return/I and direct DOS type I; complete records required; validation/close before display |
| MERLIN | High-bit Merlin / ED-ASM text, aligned label/opcode/operand/comment columns | Source listing only |
| LISAV2 | LISA version 2 length-prefixed source, mnemonic table, labels and comments | Versions 3–5 and their symbol tables are not implemented |
| GUTTEXT | Extracted Gutenberg text, high-bit ASCII and line breaks | Custom filesystem extraction is not implemented; external font glyphs show `?` |
| TEACHTXT | Teach data fork, line breaks and simplified MacRoman text | Resource-fork styles, fonts, rulers and layout are not implemented |
| FONTRIX | Fontrix glyphs, one at a time, as monochrome marks on the text screen | Up to 94 glyphs, height 32, width 32; heights over 20 combine pairs of rows |
| MCS | Music Construction Set two-staff Mockingboard exports and paired editor scores | See [MCS format](MCS-FORMAT.md); main file + `.OBJ` required for scores |
| DOSMCS | Direct Music Construction Set exports/editor pairs on DOS 3.3 disks/DSK/DO/2IMG | BIN payload of 2304 bytes; no temporary or AUX; main/`.OBJ` pairs validated using full DOS names |
| DOSINT | Direct DOS 3.3 Integer BASIC listing | Real disks/DSK/DO/2IMG; exact DOS EOF, 64-page ring, no temporary or AUX; malformed/oversized lines refused |
| DOSBAS | Direct DOS 3.3 Applesoft listing | Real disks/DSK/DO/2IMG; $0801 links and exact EOF checked; literal strings/DATA/REM, 64-page ring, no temporary or AUX |

Text readers validate a complete pass and successful close before showing
the first page, then reopen for display. Space, Down or Return advances;
Escape returns. A read or close failure in either pass is reported. The
readers use the actual stream, not the panel's cached length. File changes
between the two passes are not snapshot-isolated, but no source is written.

Fontrix validates every glyph pointer against the actual EOF before the
first preview, and completes the read and close for each glyph before
showing it. Left/Up selects the previous glyph; Right/Down/Space selects
the next; Escape returns. It accepts both known header signatures. The
preview combines tall glyph rows with OR; it is not a pixel-perfect HGR
rendering at the original scale.

Tests execute the production C on the host and both sim65 CPU targets,
compare rendered text or glyph pixels and preserve the input bytes. Local
corpus tests additionally compare every glyph in 21 real Fontrix fonts.
External corpus checks skip explicitly if those files are unavailable;
generated fixtures remain part of the repository's tests.

LISA regression input includes the two DOS v2 sources in CiderPress II's
test disk; Merlin checks nine real sources, including macro comparisons
with a lone quote. The LISA length word counts from offset 2 and excludes
the three-byte `$FF` marker. Literal control bytes in comments show `?`.

`bench/retrotext.py` opens all seven document/font plugins from the menu
on a disposable POM2 image, checks paging/navigation and malformed LISA,
and compares AUX and the C-stack floor before/after.

S-C BIN qualification (12 October 2026): the existing first-record rule now
accepts ProDOS BIN, independently of name and auxiliary address. The reader
still validates the complete stream, including successful close, before
display. All twelve sources from the original S-C Macro Assembler IIe 1.1
disk produce identical listings as INT and BIN on the host and both sim65
CPUs. Tests include 255-byte records, line number 65535, space/RLE tokens,
truncated final records, invalid tokens, stale panel sizes, cancellation and
read/open/close failures in both passes. Every source is byte-compared.

Reader (13), three-stage detector (13) and DOS identification (12) suites
pass with cc65 2.19 and HEAD on both CPUs. DOS BIN retains its fallback;
direct DOS type I remains supported. The sample-size check in id_restore
guarantees sample length <= actual EOF; duplicate minimum-size comparisons
were removed from the Magic Window and Print Shop font rules. Invalid
contexts, including sample length exceeding EOF, are refused.

Both native builds and all four distribution images pass with layout guards
active. IDFORMATS ends at `$3ED1` (65C02) / `$3FC9` (6502), SCASM at `$39CA` /
`$39C0`, below `$4000`. IDENT handoff and bench inventory pass; signedness
analysis reports zero sites.

`bench/retrotext.py --sc-only` targets BIN opening by Return/I and preservation
on disposable volumes : **7/7 controls on each CPU**, including unchanged AUX,
stack floor and whole source volume. The menu now holds 128 commands and
exposes SCASM and all distributed readers on XL. The complete menu-based
bench passes **16/16 controls on each CPU**, including FONTRIX navigation
and source-volume/AUX/stack preservation. Physical Apple II hardware
remains untested.
The bench runner declares the required original S-C disk as a fixture;
missing corpus data is not reported as a successful native qualification.

The format rules and LISA mnemonic interoperability table follow
[CiderPress II](https://github.com/fadden/CiderPress2), revision
`7a055a200e31f752f3a92bb9fe6ae6f67cd55534`, Apache 2.0. Fontrix was
reverse engineered by Mark Long. Licenses and attribution are preserved
in `data/licenses/`.
