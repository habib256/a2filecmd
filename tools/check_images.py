#!/usr/bin/env python3
"""Check the published BOOT / EXTRA / XL set against each CPU's build."""
from pathlib import Path

from po2dsk import to_dsk
from prodos_read import Image

ROOT = Path(__file__).resolve().parents[1]


def entries(image, block):
    return {e[1:1 + (e[0] & 15)].decode('ascii'): e for e in image.entries(block)}


def check_cpu(cpu):
    build = ROOT / ('build-6502' if cpu == '6502' else 'build')
    expected = {p.name.split('.BIN.')[1] + '.PLG': p.read_bytes()
                for p in build.glob('A2FILE.CODE.BIN.*')}
    expected.update({p.stem.upper() + '.PLG': (build / (p.stem + '.PLG')).read_bytes()
                     for p in (ROOT / 'src/plugins').glob('*.c')})
    plugins = {}
    for role in ('BOOT', 'EXTRA', 'XL'):
        path = ROOT / 'dist' / ('A2FILECMD-%s-%s.%s' % (cpu, role, '2mg' if role == 'XL' else 'po'))
        data = path.read_bytes()
        if role == 'XL':
            assert len(data) == 64 + 65535 * 512 and data[:4] == b'2IMG', path
            assert int.from_bytes(data[24:28], 'little') == 64, path
            data = data[64:]
        else:
            assert len(data) == 280 * 512, path
            assert path.with_suffix('.dsk').read_bytes() == to_dsk(data), path
        image = Image(data)
        volume = {'BOOT': 'A2FC', 'EXTRA': 'A2EXTRA', 'XL': 'A2XL'}[role] + cpu
        assert image.header()['name'] == volume, path
        root = entries(image, 2)
        directory = entries(image, int.from_bytes(root['A2FILE'][17:19], 'little'))
        assert 'FORMAT.SYS' not in directory, path
        assert ('FORMAT.PLG' in directory) == (role != 'EXTRA'), path
        assert ('VOLINFO.PLG' in directory) == (role != 'EXTRA'), path
        for new in ('UNDELETE', 'DISKCMP', 'MKIMAGE', 'RESCUE', 'SYNC', 'TREE'):
            assert (new + '.PLG' in directory) == (role != 'BOOT'), (path, new)
        plugins[role] = {name for name in directory if name.endswith('.PLG')}
        for name in plugins[role]:
            entry = directory[name]
            assert entry[16] == 6 and int.from_bytes(entry[31:33], 'little') == 0x1B00, (path, name)
            assert image.read(entry) == expected[name], (path, name, 'wrong CPU or stale overlay')
        if role == 'EXTRA':
            assert 'PRODOS' not in root and 'A2FILE.SYSTEM' not in root, path
        else:
            assert 'PRODOS' in root and 'A2FILE.SYSTEM' in root, path
            launcher = 'A2FILE.FLOPPY.SYS' if role == 'BOOT' else 'A2FILE.SYSTEM.SYS'
            program = image.read(root['A2FILE.SYSTEM'])
            assert program == (build / launcher).read_bytes(), path
            title = cpu + (' FLOPPY EDITION' if role == 'BOOT' else ' COMPLETE EDITION')
            assert title.encode('ascii') in program, (path, 'wrong launch screen')
            assert image.read(directory['A2FILE.CODE']) == (build / 'A2FILE.CODE.BIN').read_bytes(), path
        assert ('BASIC.SYSTEM' in root) == (role != 'BOOT'), path
        if role == 'XL':
            assert {'DEMO', 'IMGHGR'} <= root.keys() and plugins[role] == expected.keys(), path
        else:
            assert image.read(directory['EXTRAS.CAT']) == (build / 'EXTRAS.CAT').read_bytes(), path
        print('PASS %s: %d overlays, matching build and disk layout' % (path.name, len(plugins[role])))
    assert plugins['BOOT'] | plugins['EXTRA'] == expected.keys()
    assert plugins['BOOT'] & plugins['EXTRA'] == {'MENU.PLG'}


if __name__ == '__main__':
    for cpu in ('6502', '65C02'):
        check_cpu(cpu)
