"""Names and inventories of the four published images (no legacy companions)."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
MAKEFILE = (ROOT / 'Makefile').read_text()
VERSION = re.search(r'^A2FC_VERSION\s*=\s*(\S+)', MAKEFILE, re.M)[1]
RUNTIMES = ('BASIC.SYSTEM', 'INTBASIC.SYSTEM')


def image_name(role, version=VERSION):
    suffix = '2mg' if role in ('XL', 'XL-65C02-enhanced') else 'po' if role == '800K' else 'dsk'
    if role not in ('XL', 'XL-65C02-enhanced', 'DOS3.3', '800K'):
        raise ValueError('unknown image role: ' + role)
    system = '' if role == 'DOS3.3' else 'PRODOS-'   # the file names say which system boots
    return f'A2FILECMD-{system}{role}-{version}.{suffix}'


def image_names(version=VERSION):
    return [image_name(role, version) for role in ('XL', 'XL-65C02-enhanced', 'DOS3.3', '800K')]


def xl_name(cpu):
    return image_name('XL-65C02-enhanced' if cpu == '65C02' else 'XL')


def inventories():
    native = re.search(r'^PLUGINS = (.+)$', MAKEFILE, re.M)[1].split()
    plugins = [p.stem for p in (ROOT / 'src/plugins').glob('*.c')]
    boot = set(re.search(r'^BENCH_BOOT_NATIVE = (.+)$', MAKEFILE, re.M)[1].split())
    boot.update(re.search(r'^BENCH_BOOT_PLUGINS = \$\(filter ([^,]+),', MAKEFILE, re.M)[1].upper().split())
    complete = set(native) | {p.upper() for p in plugins}
    if not boot <= complete:
        raise ValueError('unknown regression fixture overlays: ' + str(boot - complete))
    return boot, complete


def floppy_inventory():
    """Explicit practical 800K selection; XL alone grows with plugin sources."""
    config = (ROOT / 'config/800k.mk').read_text()
    native = re.search(r'^PLUGINS = (.+)$', MAKEFILE, re.M)[1].split()
    if not re.search(r'^PLUGINS800 = \$\(PLUGINS\)$', config, re.M):
        raise ValueError('800K must retain the native routing overlays')
    plugins = re.search(r'^XPLUGINS800 = (.+)$', config, re.M)[1].split()
    if len(plugins) != len(set(plugins)):
        raise ValueError('duplicate 800K overlay')
    selected = set(native) | {name.upper() for name in plugins}
    if not selected <= inventories()[1]:
        raise ValueError('unknown 800K overlays')
    return selected


if __name__ == '__main__':
    print('\n'.join(image_names()))
