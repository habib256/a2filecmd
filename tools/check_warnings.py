"""The build says nothing but what the service-stub idiom cannot help saying.

Five hundred warnings hide the one that matters. Two kinds are inherent here
and stay:

- **Control reaches end of non-void function**, in the files that define
  service stubs: a stub's body is `asm("jmp ...")`, it never returns to C.
  Adding a `return` would cost bytes in an overlay that has none.
- **'X' is defined but never used**: a helper of a shared header (util.h,
  service_stubs.h, hgr_io.h...) that this overlay, or this variant of it,
  does not call.

Anything else -- an unused parameter outside a stub block, a pointer used as
an integer, a comparison that is always true, a statement without effect --
fails here, which is what makes the two kinds above harmless.

    python3 tools/check_warnings.py [--arch enh|6502|both]
"""
import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WARNING = re.compile(r'^(\S+?)\((\d+)\): Warning: (.*)$')
NO_RETURN = 'Control reaches end of non-void function'
UNUSED = re.compile(r"^'\w+' is defined but never used$")
CC65_HEAD = Path.home() / 'opt/cc65-head'


def stub_files():
    """The files whose functions are `asm` bodies that jump away."""
    return {str(p.relative_to(ROOT)) for p in (ROOT / 'src/plugins').glob('*')
            if p.suffix in ('.c', '.h') and 'unused-param' in p.read_text()}


def build(arch, out):
    """A whole build of one edition, its compiler output as text."""
    result = subprocess.run(['make', 'BUILD_SUFFIX=-' + out, 'ARCH=' + arch, 'all'],
                            cwd=ROOT, capture_output=True, text=True)
    return result.returncode, result.stdout + result.stderr


def unexpected(text, stubs):
    """The warnings that are neither of the two kinds this build may emit."""
    bad = []
    for line in text.splitlines():
        m = WARNING.match(line.strip())
        if not m:
            continue
        where, _, message = m.groups()
        if message == NO_RETURN and where in stubs:
            continue
        if UNUSED.match(message):
            continue
        bad.append(line.strip())
    return bad


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--arch', choices=('enh', '6502', 'both'), default='both')
    args = p.parse_args()
    stubs = stub_files()
    editions = ['enh', '6502'] if args.arch == 'both' else [args.arch]
    failed = 0
    for arch in editions:
        if arch == '6502' and not (CC65_HEAD / 'bin/cc65').exists():
            print('cc65 master absent: edition 6502 not read')
            continue
        out = 'warncheck-' + arch
        shutil.rmtree(ROOT / ('build-' + out), ignore_errors=True)
        try:
            code, text = build(arch, out)
            if code:
                print('%s: the build itself failed' % arch)
                print('\n'.join(text.splitlines()[-5:]))
                failed = 1
                continue
            bad = unexpected(text, stubs)
            print('%s: %d warnings, %d unexpected' % (arch, text.count('Warning:'), len(bad)))
            for line in bad[:20]:
                print('  ' + line)
            failed = failed or bool(bad)
        finally:
            shutil.rmtree(ROOT / ('build-' + out), ignore_errors=True)
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
