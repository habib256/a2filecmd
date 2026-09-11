#!/usr/bin/env python3
"""Check the published BOOT / EXTRA / EXTRA2 / XL set against each CPU's build."""
from pathlib import Path
import re

from po2dsk import to_dsk
from prodos_read import Image

ROOT = Path(__file__).resolve().parents[1]
MAKEFILE = (ROOT / 'Makefile').read_text()
VERSION = re.search(r'^A2FC_VERSION\s*=\s*(\S+)', MAKEFILE, re.M)[1]
# Which tool floppy an overlay belongs on is the Makefile's business, not a
# second list here: read it, so the two cannot drift apart.
EXTRA2 = {n.upper() + '.PLG' for n in
          re.search(r'^XPLUGINS_EXTRA2 = \$\(filter ([^,]*),', MAKEFILE, re.M)[1].split()}


def entries(image, block):
    return {e[1:1 + (e[0] & 15)].decode('ascii'): e for e in image.entries(block)}


def check_cpu(cpu):
    build = ROOT / ('build-6502' if cpu == '6502' else 'build')
    native = re.search(r'^PLUGINS = (.+)$', MAKEFILE, re.M)[1].split()
    expected = {name + '.PLG': (build / ('A2FILE.CODE.BIN.' + name)).read_bytes()
                for name in native}
    expected.update({p.stem.upper() + '.PLG': (build / (p.stem + '.PLG')).read_bytes()
                     for p in (ROOT / 'src/plugins').glob('*.c')})
    plugins = {}
    for role in ('BOOT', 'EXTRA', 'EXTRA2', 'XL'):
        path = ROOT / 'dist' / ('A2FILECMD-%s-%s-%s.%s' % (cpu, role, VERSION, '2mg' if role == 'XL' else 'po'))
        data = path.read_bytes()
        if role == 'XL':
            assert len(data) == 64 + 65535 * 512 and data[:4] == b'2IMG', path
            assert int.from_bytes(data[24:28], 'little') == 64, path
            data = data[64:]
        else:
            assert len(data) == 280 * 512, path
            assert path.with_suffix('.dsk').read_bytes() == to_dsk(data), path
        image = Image(data)
        volume = {'BOOT': 'A2FC', 'EXTRA': 'A2EXTRA',
                  'EXTRA2': 'A2EXTRA2', 'XL': 'A2XL'}[role] + cpu
        assert image.header()['name'] == volume, path
        root = entries(image, 2)
        directory = entries(image, int.from_bytes(root['A2FILE'][17:19], 'little'))
        assert 'FORMAT.SYS' not in directory, path
        boot_only = role in ('BOOT', 'XL')
        assert ('FORMAT.PLG' in directory) == boot_only, path
        assert ('VOLINFO.PLG' in directory) == boot_only, path
        plugins[role] = {name for name in directory if name.endswith('.PLG')}
        for name in plugins[role]:
            entry = directory[name]
            assert entry[16] == 6 and int.from_bytes(entry[31:33], 'little') == 0x1B00, (path, name)
            assert image.read(entry) == expected[name], (path, name, 'wrong CPU or stale overlay')
        if role.startswith('EXTRA'):
            assert 'PRODOS' not in root and 'A2FILE.SYSTEM' not in root, path
        else:
            assert 'PRODOS' in root and 'A2FILE.SYSTEM' in root, path
            launcher = 'A2FILE.FLOPPY.SYS' if role == 'BOOT' else 'A2FILE.SYSTEM.SYS'
            program = image.read(root['A2FILE.SYSTEM'])
            assert program == (build / launcher).read_bytes(), path
            title = cpu + (' FLOPPY EDITION' if role == 'BOOT' else ' COMPLETE EDITION')
            assert title.encode('ascii') in program, (path, 'wrong launch screen')
            assert image.read(directory['A2FILE.CODE']) == (build / 'A2FILE.CODE.BIN').read_bytes(), path
        assert ('BASIC.SYSTEM' in root) == (role in ('EXTRA', 'XL')), path
        if role == 'XL':
            assert {'DEMO', 'IMGHGR'} <= root.keys() and plugins[role] == expected.keys(), path
        else:
            assert image.read(directory['EXTRAS.CAT']) == (build / 'EXTRAS.CAT').read_bytes(), path
        print('PASS %s: %d overlays, matching build and disk layout' % (path.name, len(plugins[role])))
    # The three floppies partition the set, MENU excepted: it is the one
    # overlay BOOT and EXTRA both carry, so the menu works with either in.
    assert plugins['BOOT'] | plugins['EXTRA'] | plugins['EXTRA2'] == expected.keys()
    assert plugins['BOOT'] & plugins['EXTRA'] == {'MENU.PLG'}
    assert plugins['EXTRA2'] == EXTRA2, (plugins['EXTRA2'] ^ EXTRA2)
    assert not plugins['EXTRA2'] & (plugins['BOOT'] | plugins['EXTRA'])


if __name__ == '__main__':
    for cpu in ('6502', '65C02'):
        check_cpu(cpu)
