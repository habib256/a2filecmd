# Additional readers

These plugins are launched explicitly from `!`; Return's existing format
classifier does not select them. They read only: no disk output, AUX
memory, `/RAM` reconstruction, or execution of file contents.

| Plugin | Input and implemented output | Limits |
| --- | --- | --- |
| PASTEXT | Apple Pascal TEXT, 1 KB editor header and independent 1 KB chunks, DLE indentation | Text only; extracted file, not a Pascal disk |
| SCASM | S-C Assembler length-prefixed tokenized lines, line numbers, spaces and repeated characters | Complete records required |
| MERLIN | High-bit Merlin / ED-ASM text, aligned label/opcode/operand/comment columns | Source listing only |
| LISAV2 | LISA version 2 length-prefixed source, mnemonic table, labels and comments | Versions 3–5 and their symbol tables are not implemented |
| GUTTEXT | Extracted Gutenberg text, high-bit ASCII and line breaks | Custom filesystem extraction is not implemented; external font glyphs show `?` |
| TEACHTXT | Teach data fork, line breaks and simplified MacRoman text | Resource-fork styles, fonts, rulers and layout are not implemented |
| FONTRIX | Fontrix glyphs, one at a time, as monochrome marks on the text screen | Up to 94 glyphs, height 32, width 32; heights over 20 combine pairs of rows |
| MCS | Music Construction Set two-staff Mockingboard exports | See [MCS format](MCS-FORMAT.md); editor `.OBJ` is not supported |

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

The format rules and LISA mnemonic interoperability table follow
[CiderPress II](https://github.com/fadden/CiderPress2), revision
`7a055a200e31f752f3a92bb9fe6ae6f67cd55534`, Apache 2.0. Fontrix was
reverse engineered by Mark Long. Licenses and attribution are preserved
in `data/licenses/`.
