# PDF manual

`A2FILECMD-MANUAL-EN.pdf` is the printable English edition of `MANUAL.md`.
The eleven-page guide starts with DOS3.3, then develops the same workflow
under ProDOS. Its cover includes a current two-panel screenshot and twelve
clickable contents entries, followed by section bookmarks, page numbers and
repeated table headings. The release workflow copies it into `dist/` as
`A2FILECMD-MANUAL-EN-<version>.pdf`, adds
its SHA-256 checksum and attaches it to the GitHub release.

The cover uses the first Markdown image in `MANUAL.md`, currently
`screenshots/prodos-panels-0.9.3.png`: the 80-column ProDOS XL panels, which
the README shows first too. `python3 tools/capture_panels.py` retakes it from
the published enhanced XL image of the Makefile's version: POM2's 560 x 192
picture has each scan line doubled to 560 x 384, the screen's proportions.
It boots a disposable copy, checks the image unchanged afterwards, and writes
the source hash and preset to `screenshots/prodos-panels-<version>.json`. The
DOS3.3 capture (`screenshots/dos33-panels-0.9.2.png`, recorded in
`screenshots/panels-0.9.2.json`) illustrates the DOS3.3 chapter; the PDF
shows only the cover image.

Explicit `<!-- pagebreak -->` markers keep related chapters together without
reducing the text size. After regeneration, verify 11 pages, 12 bookmarks,
the first chapter DOS3.3, and the cover image and contents layout.

Regenerate the PDF after updating the manual, before publishing a release.
On macOS, no additional packages are needed:

```sh
swift tools/manual_pdf.swift docs/MANUAL.md docs/A2FILECMD-MANUAL-EN.pdf
```

Commit the refreshed PDF alongside changes to the Markdown manual. The
release job uses that checked-in PDF; it does not require Swift on its
Ubuntu runner.
