# Direct viewers: DOS 3.3 first

Branch: `work/direct-viewers-dos33`, based on `main` merge `c79c92d`.
This is a feasibility prototype, built explicitly and kept out of the
release inventory. No existing reader or resident service is replaced.

The prototype supplies a logical byte stream to a text reader, hex reader
and simple lo-res reader, **without extraction or a temporary file**.
Real DOS 3.3 drives are the primary backend. They are read through ProDOS
`READ_BLOCK`, translating a DOS sector into its half of a ProDOS block,
exactly as A2FC's DOS browser does. DOS-order `.DSK`/`.DO` images and
DOS-order 2IMG containers use the same logical stream.

## Use and reproduce

```sh
python3 experiments/direct-viewers/build.py
python3 experiments/direct-viewers/test_stream.py

POM2=/tmp/a2fc-pt3-trace A2FC_BUILD=build-6502 A2FC_PRESET=iie_unenh \
  python3 experiments/direct-viewers/bench.py
POM2=/tmp/a2fc-pt3-trace A2FC_BUILD=build A2FC_PRESET=iie \
  python3 experiments/direct-viewers/bench.py
```

The POM2 host can be built with `python3 bench/build_pt3_trace.py`.
Both normal A2FC builds and disk stages must already exist. The prototype
builder writes `build/dosview.PLG` and `build-6502/dosview.PLG`; the bench
adds the matching binary to its disposable ProDOS boot disk. It mounts a
disposable, write-protected DOS disk in Disk II drive 2. No personal disk
is used or modified.

For manual use on disposable media, copy the matching `DOSVIEW.PLG` under
`A2FILE`, ProDOS BIN at `$1B00`. Open a DOS 3.3 drive or DOS image in a
panel, select a file, press `!`, choose Unsorted then DOSVIEW. Choose T,
H or I. Text and hex support forward/backward paging and restart; Escape
returns. The existing T/H/I panel commands are not yet connected.

## Observed result

Production-C regression tests pass on the host and under sim65 for both
CPU targets. They compare bytes across physical-driver callbacks, raw
images and 2IMG containers; exercise seeks across sectors and T/S lists,
sparse holes, stale panel sizes, wrong identity/type, cyclic chains,
invalid pointers/offsets, excessive header EOF, and read/open/seek/close
failures. Lo-res testing verifies all visible bytes and preserved screen
holes. Inputs are compared after every invocation. Write/delete/format
services are absent and the physical callback rejects any MLI command
other than `READ_BLOCK`.

The POM2 bench exercises the actual Disk II/ProDOS driver path as well as
the image path. It checks text paging, exact hex offsets and all 960
visible lo-res bytes; compares screen holes, AUX RAM-disk storage and the
C-stack floor; and compares the complete DOS disk and ProDOS boot volume
after shutdown. Emulator success is evidence for the native driver path;
qualification on a physical Apple II and drive remains to be done.

## Memory measured on both CPUs

| CPU | File bytes | BSS bytes | Window occupied | Free below `$4000` |
| --- | ---: | ---: | ---: | ---: |
| 6502 | 6,963 | 2,211 | 9,174 | 298 |
| 65C02 | 6,969 | 2,211 | 9,180 | 292 |

The window is `$1B00-$3FFF` (9,472 bytes). ld65 enforces code **and** BSS
within it; the builder also checks the generated code for known cc65
traps. No limit is relaxed. Resident MAIN, LC and LOWRAM grow by **zero
bytes**, since the prototype uses the existing service table.

The initial separate picture buffer overflowed by 468 bytes. The fixed
version first preserves the five sector pointers needed for the 1,024-byte
lo-res page plus DOS header, then reuses the retired 1,120-byte file-sector
map for that page. It reads and closes successfully before display.

## Data preservation and supported subset

- All disk calls are reads; image files are opened only with `rb`. No
  writable destination, free space or temporary name is needed.
- The selected T/S identity is found again in the catalog; the displayed
  normalized name and DOS type must still match. Panel sizes never bound
  the read. Malformed/aliased/cyclic selected chains are refused.
- BIN, Integer BASIC and Applesoft streams omit their DOS prefix and use
  the exact EOF in that prefix. TXT streams expose their allocated extent,
  including zero-filled holes and sector padding; DOS stores no exact byte
  length for them. Text display masks the high bit; hex preserves bytes.
- Scope is standard 35-track, 16-sector DOS 3.3, TXT/BIN/INT/BAS, up to
  560 logical sectors. Large sparse layouts and other DOS file types are
  refused. This is not a complete volume consistency audit.
- I currently displays only a raw BIN `$0400` page of exactly 1,024 bytes,
  in 40-column lo-res. Only 40 visible bytes per text row are copied;
  firmware/card screen holes are preserved. AUX is not used for graphics
  or storage and `/RAM` is not rebuilt.
- The stream is read-only, not a snapshot: changing/ejecting a source
  during reading can cause a read error or change displayed data. No source
  is deleted, rewritten or recovered from cached contents.

## What the next implementation must connect

1. Route panel T/H/I and appropriate Return actions to the stream readers
   for **real DOS drives and images**, without weakening the read-only
   guard that still rejects editing, execution and destructive commands.
2. Separate the stream contract from its DOS backend so existing format
   readers can adopt it. Add a ProDOS image backend (seedling, sapling,
   tree and eventually forks). Avoid fake `FILE*` objects: several current
   plugins inspect cc65's error flag directly.
3. Add raw HGR and compressed pictures. The prototype occupies the HGR
   page; rendering at `$2000` would overwrite its code. The hot sector-read
   and display loop must first be relocated below `$2000`, with their
   metadata and support routines, using an enforced layout like NRCLIP's.
   There is only about 300 bytes free in the current complete window.
4. Add neighbour files, slideshows, music and program-based viewers as
   separate steps. AUX consumers must keep the existing confirmation
   before destroying an occupied `/RAM` volume.

WOZ and Pinball remain outside the requested scope.
