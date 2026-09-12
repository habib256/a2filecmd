"""One distribution manifest, shared by image building, catalogs and checks."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / 'config/packages.mk'
VALUES = dict(re.findall(r'^(\w+)\s*=\s*(.*?)\s*$', CONFIG.read_text(), re.M))
ROLES = VALUES['PACKAGE_ROLES'].split()
PACKAGES = {role: VALUES['PACKAGE_' + role].split() for role in ROLES}
VOLUMES = {role: VALUES['PACKAGE_VOLUME_' + role] for role in ROLES}
BASIC = VALUES['PACKAGE_BASIC']


def assignments(native, plugins):
    """Fail the build on duplicates, missing tools, or unknown names."""
    makefile = (ROOT / 'Makefile').read_text()
    boot_native = re.search(r'^PLUGINS_FLOPPY = (.+)$', makefile, re.M)[1].split()
    boot_plugins = re.search(r'^XPLUGINS_FLOPPY = \$\(filter ([^,]+),', makefile, re.M)[1].upper().split()
    expected = set(native) | {p.upper() for p in plugins}
    boot = set(boot_native) | (set(boot_plugins) & expected)
    result = {name: 'BOOT' for name in boot}
    for role, names in PACKAGES.items():
        if not names or len(VOLUMES[role] + '65C02') > 15:
            raise ValueError('invalid package: ' + role)
        for name in names:
            if name not in expected or name in result:
                raise ValueError('unknown or duplicate overlay: ' + name)
            result[name] = role
    if result.keys() != expected:
        raise ValueError('unassigned overlays: ' + ', '.join(sorted(expected - result.keys())))
    return result
