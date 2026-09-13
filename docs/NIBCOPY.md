# NIBCOPY transport and validation

NIBCOPY is a foreground DISKTOOLS/XL service plugin. It copies tracks 0–34
between two drives on one Disk II controller, or exchanges disks on one drive.
All code remains resident until the operation returns. It performs no MLI or
file operation while the source/target disks replace BOOT and DISKTOOLS.

## Supported representation

The transport preserves the fourteen encoded address bytes, 349 encoded data
bytes, and circular sector order of each of sixteen sectors. It validates
four-and-four addressing, physical track numbers, unique sector IDs, all GCR
symbols, address/data checksums and complete epilogues. Each 8192-byte capture
must contain seventeen records: a complete revolution plus the first record
again. Two source captures must agree before any write to that track. Target
verification compares every encoded field and circular sector order.

Sync gaps are regenerated, not preserved as flux. Between fields only FF sync
is normally accepted. A physical write splice may produce up to eight partial
nibbles in an inter-sector gap, surrounded on both sides by at least sixteen
FF bytes. A prologue is never skipped, and this exception never applies inside
a field or the address-to-data gap. Missing sectors, damaged checksums,
unbounded gaps, 13-sector framing and unstable fields stop the operation.
This does not preserve copy protections, weak bits or half-track formats.

## Memory and cleanup

| Bank / addresses | Purpose |
| --- | --- |
| MAIN `$1B00–$3FFF` | Header, cleanup trampoline, C, assembly, caches and BSS; linker bounded |
| MAIN `$6500–$84FF` | Borrowed capture/write buffer; all 8192 bytes saved and restored |
| AUX `$4000–$5FFF` | Source capture |
| AUX `$6000–$7FFF` | Second-source or target capture |
| AUX `$8000–$9FFF` | Prepared write image |
| AUX `$A000–$BFFF` | Borrowed resident's backup |
| MAIN `$2000–$21FF` | May be overwritten by the resident `/RAM` formatter on exit |

`OVERLAY_AUX` obtains consent before the first auxiliary write. The transport
masks interrupts before borrowing resident memory, calls no C/MLI until it is
restored, and preserves the caller's interrupt state on errors as on success.
The low-level routines use scratch zero page `$1D–$1E` and ROM AUXMOVE
parameters `$3C–$43`; they leave cc65 zero page and its software stack intact.

The C driver finishes its report and returns **before** rebuilding `/RAM`.
A linker-checked continuation below `$2000` calls the resident formatter,
reports `/RAM not rebuilt` with the verified-track count if it returns zero,
and returns straight to A2FC. Calling that formatter from C in the large
window would erase the code needed to return. No C code runs afterward;
the continuation and its alternate report both remain below `$2000`.

## Timing

Read polling consists of twelve straight-line probes, seven cycles apart on
an unready latch. A stuck latch times out after about 84 cycles. A decrementing
counter inside this loop would increase the interval to fourteen cycles and
lose bits on the real Disk II sequencer. Both read and write loops have
link-time page-boundary assertions and use only NMOS-compatible instructions.

The writer retains the 32-cycle data / 40-cycle sync loop from
[`src/format_diskii.s`](../src/format_diskii.s), with its existing attribution.
It writes main `$6532–$7FFF`. The first address begins at `$6840`: 782 leading
sync bytes absorb the overwrite splice. Six sync bytes precede each data field,
eight follow each sector, and the last epilogue ends 56 bytes before Q7 stops.
The first-address-to-stop interval is 196736 cycles, below a 200000-cycle
revolution at 300 RPM / 1 MHz. The final padding lets the last byte finish
shifting out before write mode ends. This budget is not a drive-speed
measurement or qualification of an accelerator.

## Safety and reproducible checks

The source must remain physically write-protected. Target slot/drive and loss
of all files, including locked files, are shown before writing; single-drive
mode confirms every target exchange. Hardware protection is checked again in
the writer. There is no rollback: a failed or interrupted copy leaves an
incomplete target and reports only the number of verified tracks. All 35
source tracks are not preflighted before the first write.

- `python3 tools/test_nibcopy.py`: real C workflow, 20 host tests, source/target
  byte preservation, valid-checksum corruption, read/write/verification errors,
  source identity through physical protection, cancellation and malformed fields.
- `python3 bench/nibcopy.py --pom2-root /path/to/pom2`: production toolchains,
  real C/assembly and ROM AUXMOVE on both CPU variants. Disposable DSK images
  and 50000-cell WOZ tracks at 300 RPM exercise different source/target data,
  complete encoded comparisons, sector bytes, write protection, stuck-latch
  timeout, interrupt state, stack/main/AUX sentinels and destructive RAM cleanup.
- `A2FC_PRESET=iie_unenh python3 bench/nibcopy_ui.py`: published DISKTOOLS,
  AUX refusal, target confirmation, BOOT removed during the full 35-track copy,
  and exact source/target image comparison after ejection; a single-drive
  exchange copies one track, cancels before the next, and checks untouched tracks.

Physical drives and accelerators still require hardware qualification. A
successful readback does not guarantee persistence across a power cut.

## Local results, 2026-09-13

Working tree based on `6b43fec`, version `0.8.0` (unreleased changes):
`make test` passes 475 tests in 58 suites, including the 20 NIBCOPY cases.
Both architecture builds pass their unchanged resident/stack/BSS/overlay
checks, and all seven distribution images pass `tools/check_images.py`.
DISKTOOLS retains 116 free blocks out of 280.

The native DSK/WOZ transport bench passes on both CPUs, using cc65 master
`e11fb5c` for 6502 and cc65 2.19 for 65C02. The UI bench passes 14/14 checks:
a full two-drive copy and a single-drive exchange/cancellation, with exact
source and target bytes checked after ejection. `bench/extras.py` passes
23/23 checks on the unenhanced IIe, including the BASIC return scenario.
The POM2 CI job now includes the NIBCOPY UI bench; remote CI was not run here.

| Plugin | File bytes | Free bytes after BSS, below `$4000` |
| --- | ---: | ---: |
| 6502 | 6308 | 2304 |
| 65C02 | 6272 | 2340 |

SHA-256 of the tested plugins:

```text
6502   a0afc7782164ec7f58f90969702dcb60ba43ad8b2e71adeceeb0ceec07f8901d
65C02  30286c7f0a70daec6105edc9a815148084d72a6594aebd884591ba01b79380eb
```

Source identity for these binaries:

```text
src/plugins/nibcopy.c  c6fb6b382c136f6930a3e8b8f9f6bd124bd415a4fbb8c8260163abf9f9c967c7
src/plugins/nibcopy.s  de075e07538dc3e25da0751d71b8bb55120ab5adf25b6dc513cce18c78c58298
sdk/nibcopy.cfg        b0580dc4902af48d64c907c5e5fe1e00cb5bf091deddd7d0ad0672eebf228251
```
