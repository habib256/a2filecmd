# PDF manual

`A2FILECMD-MANUAL-EN.pdf` is the printable English edition of `MANUAL.md`.
The eight-page guide includes a current two-panel screenshot and clickable
contents on its first page, section bookmarks, page numbers and
repeated table headings. The release workflow copies it into `dist/` as
`A2FILECMD-MANUAL-EN-<version>.pdf`, adds
its SHA-256 checksum and attaches it to the GitHub release.

The screenshot is `screenshots/01-panels-0.7.5.png`.

Regenerate the PDF after updating the manual, before publishing a release.
On macOS, no additional packages are needed:

```sh
swift tools/manual_pdf.swift docs/MANUAL.md docs/A2FILECMD-MANUAL-EN.pdf
```

Commit the refreshed PDF alongside changes to the Markdown manual. The
release job uses that checked-in PDF; it does not require Swift on its
Ubuntu runner.
