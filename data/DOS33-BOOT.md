# DOS 3.3 boot tracks

`dos33_boot.tmpl` contains only tracks 0–2 (12,288 bytes, DOS sector order)
from the already distributed `A2FC-MINI-DOS33-0.9.0.dsk`. No catalog or
user files are imported. Its startup filename is HELLO.

Source image SHA-256: `8899bd61110e7fbc8af050c31f3c3fadec0f14e578b93028d8ff8292beb895a4`.

`build_mini_disk.py` reconstructs the minimal master header expected by
`mkmini33.build`, then builds the new catalog and every shipped file from
repository sources. A supplied `MINI_MASTER` remains read-only.
