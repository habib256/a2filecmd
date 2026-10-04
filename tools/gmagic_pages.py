#!/usr/bin/env python3
"""The hi-res pages GMAGIC draws, for a comparison with the original
routines done elsewhere (the private oracle of docs/GRAPHICS-MAGICIAN-FORMAT.md).

    gmagic_pages.py PICS OUT [--engine sim65|mos6502|ref] [--cpu 6502|65c02]
                    [--lax] [--picture N]

PICS holds NNN.pic files (the bytes of a picture file, as on the disk) and
index.json, {name: dialect}: the name with or without .pic, the dialect
"V82" or "V84". For each entry the tool writes OUT/NNN.page, the 8,192
bytes of hi-res page 1 ($2000-$3FFF, screen holes included) once the first
picture of the file (or picture N) is drawn on a page cleared to $FF.

Engines:
  sim65    (default) the real overlay, src/plugins/gmagic.s, as
           tools/test_gmagic.py runs it: plugin_entry under sim65 with a
           service table that reads the file, D pressed for V84 when the
           data does not ask for it, N pressed N times; --cpu picks the
           simulated processor (65c02 by default);
  mos6502  the 6502 edition's GMAGIC.PLG as linked by the Makefile, in
           tools/mos6502.py (tools/test_gmagic_writes.py);
  ref      tools/gmagic_ref.py, the host reference written from the spec.
--lax drops the spec's two recognition rules (first command, a line start
among lines) in the sim65 build, for files the shipped overlay refuses.

Exit status 1 if any picture could not be drawn (refused, or V82 asked for
a picture that uses V84 commands); each such case is printed and gets no
.page file.
"""
import argparse
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gmagic_ref as ref  # noqa: E402


def keys_for(data, dialect, picture):
    """The keys that bring the overlay to the page wanted, and the index
    of the wait at which that page is shown."""
    forced = ref.dialect_of(data) == ref.V84
    if dialect == ref.V82 and forced:
        raise ValueError('V82 asked, but the file uses V84 commands')
    keys = 'D' if dialect == ref.V84 and not forced else ''
    return keys + 'N' * picture, len(keys) + picture


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('pics', type=Path)
    ap.add_argument('out', type=Path)
    ap.add_argument('--engine', choices=('sim65', 'mos6502', 'ref'), default='sim65')
    ap.add_argument('--cpu', choices=('6502', '65c02'), default='65c02')
    ap.add_argument('--lax', action='store_true')
    ap.add_argument('--picture', type=int, default=0)
    a = ap.parse_args(argv[1:])
    index = json.loads((a.pics / 'index.json').read_text())
    a.out.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.TemporaryDirectory(prefix='a2fc-gmpages-')
    work = Path(tmp.name)
    if a.engine == 'sim65':
        import subprocess
        import test_gmagic
        exe = test_gmagic.build(work, lax_too=a.lax)[a.cpu, a.lax]
    elif a.engine == 'mos6502':
        import test_gmagic_writes as w
        plg, mp = w.link()
    failed = 0
    for name, dialect in sorted(index.items()):
        stem = name[:-4] if name.endswith('.pic') else name
        data = (a.pics / (stem + '.pic')).read_bytes()
        try:
            dialect = dialect.upper()
            if dialect not in (ref.V82, ref.V84):
                raise ValueError('dialect %r' % dialect)
            if a.engine == 'ref':
                if dialect == ref.V82 and ref.dialect_of(data) == ref.V84:
                    raise ValueError('V82 asked, but the file uses V84 commands')
                page = ref.render(data, dialect, a.picture, recognise=not a.lax)
            else:
                keys, at = keys_for(data, dialect, a.picture)
                if a.engine == 'sim65':
                    (work / 'pic.bin').write_bytes(data)
                    p = subprocess.run(['sim65', str(exe), '6', keys or '-', '-1', '1', '0'],
                                       cwd=work, capture_output=True, timeout=600)
                    if p.returncode:
                        raise ValueError('sim65 failed: %r' % p.stderr[-200:])
                    nwait = (len(p.stdout) - 1392 - 8192) // 8192
                    r = test_gmagic.Run(p.stdout, nwait)
                    pages, note = r.pages, r.note
                else:
                    m = w.Machine(plg, mp, data, keys).run()
                    pages, note = m.pages, m.note
                if len(pages) <= at:
                    raise ValueError('not drawn: %s' % (note or 'no such picture'))
                page = pages[at]
        except (ValueError, ref.Malformed) as e:
            print('%s: %s' % (stem, e))
            failed += 1
            continue
        (a.out / (stem + '.page')).write_bytes(page)
    tmp.cleanup()
    print('%d pages written, %d not drawn' % (len(index) - failed, failed))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
