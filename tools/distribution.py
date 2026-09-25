"""Names and inventories of the five published images (no legacy companions)."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
MAKEFILE = (ROOT / 'Makefile').read_text()
VERSION = re.search(r'^A2FC_VERSION\s*=\s*(\S+)', MAKEFILE, re.M)[1]
RUNTIMES = ('BASIC.SYSTEM', 'INTBASIC.SYSTEM')


def image_name(role, version=VERSION):
    suffix = '2mg' if role in ('XL', 'XL-65C02-enhanced') else 'po' if role == '800K' else 'dsk'
    if role not in ('XL', 'XL-65C02-enhanced', 'DOS3.3', '800K', '140K'):
        raise ValueError('unknown image role: ' + role)
    return f'A2FILECMD-{role}-{version}.{suffix}'


def image_names(version=VERSION):
    return [image_name(role, version) for role in ('XL', 'XL-65C02-enhanced', 'DOS3.3', '800K', '140K')]


def xl_name(cpu):
    return image_name('XL-65C02-enhanced' if cpu == '65C02' else 'XL')


def inventories():
    native = re.search(r'^PLUGINS = (.+)$', MAKEFILE, re.M)[1].split()
    plugins = [p.stem for p in (ROOT / 'src/plugins').glob('*.c')]
    boot = set(re.search(r'^PLUGINS_FLOPPY = (.+)$', MAKEFILE, re.M)[1].split())
    boot.update(re.search(r'^XPLUGINS_FLOPPY = \$\(filter ([^,]+),', MAKEFILE, re.M)[1].upper().split())
    complete = set(native) | {p.upper() for p in plugins}
    if not boot <= complete:
        raise ValueError('unknown essential overlays: ' + str(boot - complete))
    return boot, complete


if __name__ == '__main__':
    print('\n'.join(image_names()))
