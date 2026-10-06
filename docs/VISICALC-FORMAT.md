# VisiCalc worksheets (/SS files)

What A2 File Cmd knows about the files VisiCalc (Software Arts / VisiCorp,
Apple II, 1979–1983) saves with `/SS`, and about the way VisiCalc shows
them, written from our own observations: the files of four VisiCalc disks,
and VisiCalc itself run under POM2 on worksheets written for the purpose.
`tools/visicalc_ref.py` implements everything below; `src/plugins/visicalc.s`
(the VISICALC overlay) is held to it by `tools/test_visicalc.py`, and the
reference to VisiCalc by the same test (the probe sheets and what VisiCalc
showed for them are in `tools/visicalc_probes.json.gz`).

## The file

A text file: DOS 3.3 `T` (high bit set on every byte, CR line ends, the
text ends at the first zero byte), or a ProDOS `TXT` once copied — A2 File
Cmd reads both, the high bit dropped (it also takes LF as a line end). It
is not a picture of the sheet but
the **keystrokes that rebuild it**: VisiCalc loads it by typing it.

```
>D19:/F-"-          a cell: go to D19, then what was typed there
>D18:@SUM(D8...D16)
>C5:/FR"FEB
>B8:650
...
/W1                 the settings, after the cells
/GOC
/GRA
/GF$
/GC9
/X>A1:>A1:
```

**Cell lines** come first, one per non-empty cell, from the bottom right
to the top left: rows descending, and within a row columns descending.
`>` and a cell name (columns `A`–`BK`, 63 of them; rows 1–254), a colon,
then the contents:

| Contents | Cell |
|---|---|
| `/F` + a letter, repeated | the cell's format (the last one counts): `G` general, `I` integer, `L` left, `R` right, `$` two decimals, `*` bar graph, `D` back to the sheet's default |
| `"` and text | a label (the text runs to the end of the line) |
| a letter `A`–`Z` and text | a label too: typed, a letter starts one |
| `/-` and text | a repeated label: the text over and over across the column |
| a number (`650`, `.5`, `1E3`) | a typed number |
| anything else (`+B3*2`, `-1`, `(5)`, `@SUM(...)`) | a formula |
| nothing (`/F$` alone) | a format and no contents |

Only what was typed is stored — never a result. The 80-column VisiCalc
writes a column's width as a cell line, `>B1:/GCC14` (column B, 14
characters), before the settings; Advanced VisiCalc adds lines such as
`>A1:/ADY TY::` and `/PS...` (printer setup). Neither is a cell: a
command typed there, the cell keeping what an earlier line put in it (the
row of titles of a VisiCalc 2 worksheet stays under its `>A1:/GCC..`).

**Settings lines** follow, each a command:

| Line | Meaning |
|---|---|
| `/W1` | one window (`/WH`, `/WV` would split it) |
| `/GOC`, `/GOR` | recalculation order: by columns, by rows |
| `/GRA`, `/GRM` | automatic or manual recalculation (the load recalculates either way, see below) |
| `/GCn` | the column width, `n` characters (A2 File Cmd takes 3 to 77, and `/GCCn` 1 to 77; another value is ignored) |
| `/GF?` | the default format, the letters of `/F` |
| `/X>A1:>B3:` | the window's top left corner, then the cursor (`/X!` or `/X-` may precede: a flag VisiCalc shows top right, of no consequence for the values) |
| `/XH15`, `/XV12`, `;` | a split window at row 15 or column 12; `;` passes to the second window, whose own `/GC`, `/GF`, `/X`, `/TV`... follow |

A2 File Cmd shows window 1: the settings written before the first `;`.
It also reads cells out of VisiCalc's order, or after the settings, and a
cell given twice keeps its last line. It refuses a file that has no cell,
or a line that is neither a cell line nor a command starting with `/`.

## Numbers

VisiCalc's numbers are **decimal**: a mantissa of six base-100 digits —
twelve decimal digits aligned on pairs — and an exponent, `0.m1m2…m6 × 100^e`
with −32 ≤ e ≤ 31. So the values run from 1E−66 to just under 1E62; a
result outside is ERROR (not zero), and so is a literal like `1E99` -- an
ERROR value like any other: `@ISERROR(1E99)` is TRUE, `@IF(@TRUE,1,1E99)`
is 1.

Every operation is **truncated** to those six pairs, never rounded:

| Typed | VisiCalc shows (wide column) |
|---|---|
| `1/3` | `.333333333333` (12 digits) |
| `10/3` | `3.3333333333` (11: the leading pair is `03`) |
| `2/3` | `.666666666666` |
| `1/3*3` | `.999999999999` |
| `1234567890125` | `1234567890100` |
| `1E12+1-1E12` | `0` |
| `1-1E-12` | `1` (the smaller operand is cut to the larger's digits first) |
| `.1+.2-.3` | `0` |

**Operators are evaluated strictly from left to right**, parentheses apart:
`2+3*4` is 20, `1/3+1/3+1/3` is `((1/3+1)/3+1)/3`. A unary minus binds
first: `-2^2` is 4. Comparisons (`< > = <= >= <>`) are operators like the
others and give TRUE or FALSE: `1<2+5` is `(1<2)+5`, ERROR. Parentheses or
a function call left open at the end of the formula are closed by it
(`(D13/(100+D6)*100` is accepted).

Values are numbers, `TRUE`, `FALSE`, `NA` and `ERROR`. A blank cell or a
label read by a formula counts as 0. ERROR wins over NA in any operation;
a truth value in arithmetic is ERROR, and so is a number where a truth value
is wanted (`@IF(1,2,3)`). One quirk: a formula that is nothing but `+` and
a number (`+7`, `+.5`) reads ERROR; `+7+0` and `-7` do not.

## Functions

`@NA`, `@ERROR`, `@PI` (3.1415926536), `@TRUE`, `@FALSE` take no
parentheses. `@ABS`, `@INT` (toward zero), `@NOT`, `@ISNA`, `@ISERROR`,
`@SQRT`, `@EXP`, `@LN`, `@LOG10`, `@SIN`, `@COS`, `@TAN`, `@ASIN`,
`@ACOS`, `@ATAN` take one value. The list functions take values and ranges
(`A1...A9`, a row or a column, never wider):

| Function | Observed |
|---|---|
| `@SUM`, `@AVERAGE`, `@COUNT` | in a range, blank cells and labels are left out; a value argument always counts (`@COUNT(A3,A4)` is 2 whatever they hold). `@AVERAGE` of nothing is ERROR |
| `@MIN`, `@MAX` | in a range, blanks and labels count as 0 |
| `@AND`, `@OR` | truth values only (a blank cell given as a value is 0: ERROR) |
| `@CHOOSE(n, ...)` | the n-th item (n truncated), NA out of range, ERROR with no value at all (`@CHOOSE(H5...H1)` over blanks) |
| `@IF(c, a, b)` | c must be a truth value |
| `@NPV(r, range)` | Σ vᵢ / (1+r)ⁱ, the power by repeated multiplication |
| `@LOOKUP(x, range)` | the last entry ≤ x (a sorted range assumed), the cell to its right (a column range) or below it (a row range); NA below the first; ERROR for a single cell |

`@IF`, `@CHOOSE`, `@AND`, `@OR`, `@NOT`, `@ISNA`, `@ISERROR`, `@TRUE`,
`@FALSE` belong to the later versions (1.93 here; not 1.37).

## The recalculation on loading

The keystrokes enter every cell; a typed number has its value at once, a
**formula is ERROR** until it is computed. Then VisiCalc recalculates the
sheet **once**, in its order (columns A, B, ... each top to bottom, or
rows), whether recalculation is automatic or manual. A formula that refers
to a formula not yet reached in that pass therefore reads ERROR — and so
does anything built on it:

```
>A1:+B1      A1 shows ERROR: B1 comes after A1 in column order
>B1:+C1      B1 shows 5
>C1:5
```

A sheet saved by VisiCalc in that state shows those ERRORs when loaded:
it is what the user saw, until `!` recalculated again.

## The display

A cell has its column's width w. **A label** takes all w characters, from
the left (`/FR`: against the right), cut at w — it never runs into the next
column. A repeated label fills w. **A value** takes at most w − 1
characters, against the right edge (a blank always on its left); `/FL`:
one blank, then from the left. NA, ERROR, TRUE and FALSE are shown cut to
w − 1 (`ERRO` in a column of 5). When a number cannot be written, w − 1
`>` stand for it.

**General format** (n = w − 1 characters):

1. Zero is `0`. A number whose exact writing fits is written so: `12345.678`,
   `.000123`, `-4095.9` (no leading `0`).
2. Otherwise, with at most two zeros after the point (|x| ≥ .001), it is
   rounded half up to the decimals that fit after its integer part —
   `12345.68`, `-.333333` — keeping the zeros the rounding leaves
   (`3.641144730`, `-41437.0`). When the rounding carries into a new digit
   the result is a power of ten written short, with its point:
   `.99999995` → `1.`, `9.9999999` → `10.`, `.099999` → `.1`. Rounded to
   nothing it is `0.`. Below .1, three decimals must fit, or step 3 is taken.
   When the integer part fills the field exactly, the number is rounded to
   an integer without a point; if that grows a digit, step 3 writes it.
3. In exponent form: one digit, a point and as many digits as fit before
   `E` and the exponent: `4.2741E8`, `-1.235E7`, `3.303E-4`. A mantissa of
   exactly one digit is written without a point for a positive exponent
   (`1E10`), with one for a negative one when there is room (`1.E-9`,
   `5.E-63`). A mantissa rounded to more than fits is cut: `999999999` in
   eight characters is `10.000E8`.

**$** rounds to two decimals, always written, half away from zero: `1.01`
for 1.005, `0.33`, `-1.50`; a leading `0` goes when the field is too narrow
(`.50` in three characters), except for an exact zero (`0.00` or `>>>`). A
negative value rounded to zero keeps its sign's place, blank: ` 0.00`.
**I** rounds to an integer the same way. **\*** draws one star per unit of
the integer part, w − 1 at most, from the left after a blank; nothing for
less than 1 or a negative number.

## What A2 File Cmd does not reproduce

- **Powers and the transcendental functions** (`^`, `@SQRT`, `@EXP`, `@LN`,
  `@LOG10`, `@SIN`... ) are computed by VisiCalc with its own decimal series,
  whose last digits are its own: `3^2` is 8.99999995, `2^10` 1024.0000005,
  `@EXP(1)` 2.718281828. The overlay hands them to the Applesoft ROM (nine
  digits, binary) and reads its result back: `3^2` is 9. In the columns of
  the 80 real worksheets tried, every cell still shows what VisiCalc shows;
  in a wide column, or at a rounding edge, the last digits can differ. A
  value beyond the ROM's range (1.7E38) is ERROR there. 0 to a power of 0
  or less is VisiCalc's ERROR (the ROM would say 1 or 0): the overlay
  answers it before the ROM.
- VisiCalc's screen sometimes leaves a **left-aligned zero** undrawn (in
  a 3-character column, depending on the order in which it redraws); A2 File
  Cmd always draws it. One `@MIN` of a blank and a number was left blank by
  VisiCalc on one probe sheet, `0` on another: A2 File Cmd shows `0`.
- **Titles** (`/TH`, `/TV`) and the **second window** are not shown, nor
  the printer settings; the column widths and formats are window 1's.
- The 40-column VisiCalc shows labels in capitals; the overlay shows them
  as stored.
- The **80-column versions' per-column widths** (`/GCC`) are read as their
  files say; no 80-column VisiCalc could be run to check how they show.
  Advanced VisiCalc's own formats (`/F-`, decimals `/F2`...) are not
  interpreted (the cell keeps the default format).
- **DIF** files (`/S#`, the Data Interchange Format) are not read.
- A formula nested 24 operands deep, or that puts aside more values than
  the overlay's stack holds (144 bytes: 9 a value, 17 a list function's
  state), is
  ERROR; VisiCalc's own limits were not measured.

## Versions and samples

Seen: VisiCalc 1.37 (1979; no `@IF`), 1.93 (`VC-193B0-AP2`, with the
logical functions: the oracle used here), 2.08 (`VC-208B0-AP2`, 40 and 80
columns), Advanced VisiCalc (ProDOS). Their saved files share the format
above; the later ones add `@IF`... and `/GCC`.

Method: each worksheet is loaded in VisiCalc 1.93 under POM2 (`/SL`), the
whole sheet read off the text screen by moving the cursor with `>` (goto),
cell by cell, and compared with the reference: 27,045 cells of 67 real
worksheets (the Home and Office Companion disks, VisiCalc's own sample
disks) match but for the two kinds of difference above, and so do the
7,000 cells of the probe sheets. Those disks are not redistributable and
stay private; the probe sheets and the demonstration worksheet
(`DEMO/DOCUMENTS/BUDGET.VC`, written by `tools/mkdemo_viewers.py`) are
our own.
