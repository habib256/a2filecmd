#!/usr/bin/env python3
"""Every bench, each with the machine and the image it needs.

The release qualification used to be the `bench` job of ci.yml, replayed
command by command: twenty-five benches out of the ninety-three this
directory holds. The rest -- the readers, the media, the archives, the Mini,
the cards, the serial line -- were run by hand, when someone remembered. The
table below is the whole inventory, and `tools/test_bench_inventory.py`
(in `make test`) refuses a bench file that is in no step: a new bench is
played by the qualification the day it is written, not the day someone adds
it to a list.

    make disk && make benchfloppy ARCH=enh && make benchfloppy ARCH=6502
    python3 bench/all.py --out /tmp/a2fc-bench            # everything
    python3 bench/all.py --group session readers          # a part
    python3 bench/all.py --list                           # what it would run

A step whose fixture is missing is SKIP, with what to build printed; --strict
turns those skips into failures, which is what a release wants. --setup
builds the fixtures that a command can build (the disposable POM2 hosts and,
with --make, the disks themselves).

The port of each bench is read from its source, never written here: with
--jobs, two benches that would answer on the same port never run together.
Parallelism is for iterating, though, not for qualifying: several emulators
at 200 000 cycles a second starve each other, and the benches that count
wall-clock time (a nibble copy, a copy interrupted by Escape) then time out
although nothing is wrong. `make qualify` plays the table one bench at a
time.
"""
import argparse
import os
import re
import signal
import subprocess
import sys
import time
from collections import namedtuple
from pathlib import Path

BENCH = Path(__file__).resolve().parent
ROOT = BENCH.parents[0]
VERSION = re.search(r'^A2FC_VERSION\s*=\s*(\S+)', (ROOT / 'Makefile').read_text(), re.M)[1]
SAMPLE_DISK = Path(os.environ.get('A2FC_SAMPLE_DISK', str(Path.home() / 'src/pom2/hdv/GISTDATA.hdv')))
POM2_ROOT = Path(os.environ.get('POM2_ROOT', str(Path.home() / 'src/pom2')))

# The machines and the images, as the benches read them (bench/README.md).
UNENH = {'A2FC_PRESET': 'iie_unenh'}                     # the 1983 IIe: 6502 NMOS
FULL = {'A2FC_IMG': 'A2FILECMD-full'}                    # build/A2FILECMD-full.po, 65C02
FULL_6502 = {'A2FC_IMG': 'A2FILECMD-full', 'A2FC_BUILD': 'build-6502', 'A2FC_PRESET': 'iie_unenh'}
ENH_BUILD = {'A2FC_BUILD': 'build', 'A2FC_PRESET': 'iie'}
SIX_BUILD = {'A2FC_BUILD': 'build-6502', 'A2FC_PRESET': 'iie_unenh'}
DOS_SLOT5 = {'POM2': '/tmp/a2fc-slot5', 'A2FC_DOS_SLOT': '5'}
PT3_HOST = {'POM2': '/tmp/a2fc-pt3-trace'}

# A fixture: what to look for, and the command that makes it.
Fixture = namedtuple('Fixture', 'paths build')
FIXTURES = {
    'host': Fixture([ROOT / 'build/pom2_playtest'], ['make', 'pom2host']),
    'boot': Fixture([ROOT / ('dist/A2FILECMD-PRODOS-140K-%s.po' % VERSION)], ['make', 'disk']),
    'categories': Fixture([ROOT / ('build-6502/legacy/%s.po' % name)
                           for name in ('FILES', 'MEDIA', 'DISKTOOLS', 'DEVTOOLS')], ['make', 'benchpackages', 'ARCH=6502']),
    '800k': Fixture([ROOT / ('dist/A2FILECMD-PRODOS-800K-%s.po' % VERSION)], ['make', 'disk']),
    'xl': Fixture([ROOT / ('dist/A2FILECMD-PRODOS-XL-%s%s.2mg' % ('65C02-enhanced-' if cpu == '65C02' else '', VERSION)) for cpu in ('6502', '65C02')],
                  ['make', 'disk']),
    'full-enh': Fixture([ROOT / 'build/A2FILECMD-full.po'], ['make', 'benchfloppy', 'ARCH=enh']),
    'full-6502': Fixture([ROOT / 'build-6502/A2FILECMD-full.po'], ['make', 'benchfloppy', 'ARCH=6502']),
    'plg-enh': Fixture([ROOT / 'build/fixit.PLG'], ['make', 'xplugins', 'ARCH=enh']),
    'plg-6502': Fixture([ROOT / 'build-6502/fixit.PLG'], ['make', 'xplugins', 'ARCH=6502']),
    'dos-host': Fixture([Path('/tmp/a2fc-dos-host')], [sys.executable, str(BENCH / 'build_dos_host.py')]),
    'dos-host-s5': Fixture([Path('/tmp/a2fc-slot5')],
                           [sys.executable, str(BENCH / 'build_dos_host.py'), '--slot', '5']),
    'pt3-host': Fixture([Path('/tmp/a2fc-pt3-trace')], [sys.executable, str(BENCH / 'build_pt3_trace.py')]),
    'sample': Fixture([SAMPLE_DISK], None),              # the media corpus, not in the repository
    'mini': Fixture([ROOT / ('dist/A2FILECMD-DOS3.3-%s.dsk' % VERSION)], ['make', 'mini-disk']),   # the .dsk name carries MINI_VERSION
    'pom2-src': Fixture([POM2_ROOT / 'build/libpom2_core.a'], None),
}

Step = namedtuple('Step', 'name bench group env args needs')
_STEPS = []


def step(bench, label, group, env=(), args=(), needs=('host', 'boot')):
    """One bench, one machine: the name is what --only and the summary use."""
    if bench in ('run', 'sequences', 'bny') and 'categories' not in needs:
        needs = (*needs, 'categories')
    _STEPS.append(Step('%s:%s' % (bench, label), bench, group, dict(env), list(args), tuple(needs)))


# -- The published floppies boot ---------------------------------------------
step('smoke', '6502', 'boot', UNENH)
step('smoke', 'enh', 'boot', {})
step('extras', '6502', 'boot', UNENH, needs=('host', 'boot', 'xl', '800k'))
step('extras', 'enh', 'boot', {}, needs=('host', 'boot', 'xl', '800k'))
step('machine', 'launcher', 'boot', FULL, needs=('host', 'boot', 'full-enh'))
step('subdir', 'hd', 'boot', FULL, needs=('host', 'boot', 'full-enh'))

# -- The service overlays on both processors ---------------------------------
step('six', '6502', 'core', UNENH)
step('six', 'enh', 'core', FULL, needs=('host', 'boot', 'full-enh'))
step('disksingle', '6502', 'core', UNENH)
step('tree', '6502', 'core', UNENH)
step('tree', 'enh', 'core', FULL, needs=('host', 'boot', 'full-enh'))
step('blocktools', '6502', 'core', UNENH)
step('blocktools', 'enh', 'core', FULL, needs=('host', 'boot', 'full-enh'))
step('volinfo', '6502', 'core', UNENH, needs=('host', 'boot', 'full-6502', 'plg-6502'))
step('volinfo', 'enh', 'core', FULL, needs=('host', 'boot', 'full-enh', 'plg-enh'))
step('format', '6502', 'core', UNENH)
step('format', 'enh', 'core', FULL, needs=('host', 'boot', 'full-enh'))
step('open_images', '6502', 'core', UNENH)
step('open_images', 'enh', 'core', FULL, needs=('host', 'boot', 'full-enh'))
step('bootblk', '6502', 'core', UNENH)
step('bootblk', 'enh', 'core', FULL, needs=('host', 'boot', 'full-enh'))
step('memory', 'stack', 'core', FULL, needs=('host', 'boot', 'full-enh'))

# -- Physical DOS 3.3, images and nibbles ------------------------------------
step('doswrite', '6502', 'dos', UNENH, needs=('host', 'boot', 'dos-host'))
step('doswrite', 'enh', 'dos', FULL, needs=('host', 'boot', 'full-enh', 'dos-host'))
step('doswrite', '6502-s5', 'dos', {**UNENH, **DOS_SLOT5}, needs=('host', 'boot', 'dos-host-s5'))
step('doswrite', 'enh-s5', 'dos', {**FULL, **DOS_SLOT5}, needs=('host', 'boot', 'full-enh', 'dos-host-s5'))
step('dosimage', '6502', 'dos', UNENH)
step('dosimage', 'enh', 'dos', FULL, needs=('host', 'boot', 'full-enh'))
step('physical', 'd2', 'dos', {})
step('nibcopy', 'transport', 'dos', {}, args=('--pom2-root', str(POM2_ROOT)), needs=('host', 'boot', 'pom2-src'))
step('nibcopy_ui', '6502', 'dos', UNENH, needs=('host', 'boot', 'categories'))
step('purple', 'grload', 'dos', {})

# -- What must never lose a byte ---------------------------------------------
step('data_safety', '6502', 'safety', {**UNENH, 'A2FC_IMG': 'A2FILECMD-PRODOS-140K'})
step('data_safety', 'enh', 'safety', FULL, needs=('host', 'boot', 'full-enh'))
step('recovery', '6502', 'safety', SIX_BUILD)
step('recovery', 'enh', 'safety', ENH_BUILD)
step('tree_safety', '6502', 'safety', SIX_BUILD)
step('tree_safety', 'enh', 'safety', ENH_BUILD)
step('catalog_safety', '6502', 'safety', SIX_BUILD)
step('catalog_safety', 'enh', 'safety', ENH_BUILD)
step('catalog_overlay', '6502', 'safety', SIX_BUILD)
step('catalog_overlay', 'enh', 'safety', ENH_BUILD)
step('large_nav', '6502', 'safety', SIX_BUILD)
step('large_nav', 'enh', 'safety', ENH_BUILD)
step('overlay_load', 'reject', 'safety', {}, needs=('host', 'boot', 'dos-host'))
step('batch_missing', 'restore', 'safety', {})
step('move_bitmap', 'alloc', 'safety', {})

# -- A whole session, and what chains after it -------------------------------
step('run', 'enh', 'session', FULL, needs=('host', 'boot', 'full-enh'))
step('sequences', '6502', 'session', FULL_6502, needs=('host', 'boot', 'full-6502'))
step('sequences', 'enh', 'session', FULL, needs=('host', 'boot', 'full-enh'))
step('ops', 'progress', 'session', UNENH)
step('ops', 'enh', 'session', FULL, needs=('host', 'boot', 'full-enh'))
step('roi', 'preferences', 'session', {})
step('menu', 'categories', 'session', {})
step('launch', 'enh', 'session', FULL, needs=('host', 'boot', 'full-enh'))
step('launch', '6502', 'session', SIX_BUILD, args=('--companion',), needs=('host', 'boot', 'categories'))
step('plugin', 'sdk', 'session', {})

# -- The published hard disks ------------------------------------------------
step('hd', '6502', 'xl', {**UNENH, 'A2FC_CPU': '6502'}, needs=('host', 'boot', 'xl'))
step('hd', 'enh', 'xl', {}, needs=('host', 'boot', 'xl'))
step('run', 'xl-6502', 'xl', {}, args=('--xl', '6502'), needs=('host', 'boot', 'xl'))
step('run', 'xl-65c02', 'xl', {}, args=('--xl', '65C02'), needs=('host', 'boot', 'xl'))
step('iic', 'smartport', 'xl', {}, needs=('host', 'boot', 'xl'))

# -- The service-table overlays (bench/plugins.py owns their list) ------------
step('plugins', '6502', 'plugins', UNENH, args=('--jobs', '3'), needs=('host', 'boot', 'plg-6502'))
step('plugins', 'enh', 'plugins', {'A2FC_BUILD': 'build'}, args=('--jobs', '3'),
     needs=('host', 'boot', 'plg-enh'))

# -- Readers, editors and the rest of the panels -----------------------------
step('awp', 'appleworks', 'readers', FULL, needs=('host', 'boot', 'full-enh'))
step('find', 'search', 'readers', FULL, needs=('host', 'boot', 'full-enh'))
step('hexnav', 'offsets', 'readers', {})
step('textrestart', 'pages', 'readers', {})
step('restart_readers', 'pages', 'readers', {})
step('blkedit', 'blocks', 'readers', {})
step('intbasic', 'listing', 'readers', {})
step('move', 'entries', 'readers', {})
step('formats', 'repair', 'readers', {})
step('gotocfg', 'file', 'readers', {})
step('gotobad', 'refusal', 'readers', {})

# -- Archives ----------------------------------------------------------------
step('shk', 'enh', 'archives', FULL, needs=('host', 'boot', 'full-enh'))
step('shk', '6502', 'archives', FULL_6502, needs=('host', 'boot', 'full-6502'))
step('bny', 'enh', 'archives', FULL, needs=('host', 'boot', 'full-enh'))
step('bny', '6502', 'archives', FULL_6502, needs=('host', 'boot', 'full-6502'))

# -- Pictures and sound ------------------------------------------------------
step('music', 'mockingboard', 'media', PT3_HOST, needs=('host', 'boot', 'pt3-host'))
step('duet', 'speaker', 'media', {}, needs=('host', 'boot', 'sample'))
step('pt3', 'player', 'media', PT3_HOST, needs=('host', 'boot', 'sample', 'pt3-host'))
step('pt3_dual', 'two-ay', 'media', PT3_HOST, needs=('host', 'boot', 'pt3-host'))
step('pt3_large', 'cache', 'media', PT3_HOST, needs=('host', 'boot', 'pt3-host'))
step('media', 'transitions', 'media', {})
step('sample_media', 'corpus', 'media', {}, needs=('host', 'boot', 'sample'))
step('paint816', 'pictures', 'media', {}, needs=('host', 'boot', 'sample'))
step('extasie', 'pictures', 'media', {})
step('bigvol', 'fixit-repair', 'media', {})

# -- The cards and the serial line -------------------------------------------
step('chatmauve', 'rgb', 'cards', {}, args=('feline', 'video7', 'eve'))
step('mb4c', 'enh', 'cards', {**PT3_HOST, **FULL}, needs=('host', 'boot', 'full-enh', 'pt3-host'))
step('mb4c', '6502', 'cards', {**PT3_HOST, 'A2FC_BUILD': 'build-6502'}, needs=('host', 'boot', 'pt3-host'))
step('vdrive', 'serial', 'cards', {})

# -- The Apple II+ edition, DOS 3.3 ------------------------------------------
# Each builds its own C++ bench against the POM2 sources (--pom2-root).
MINI_ROOT = ('--pom2-root', str(POM2_ROOT))
step('mini33', 'panels', 'mini', {}, args=MINI_ROOT, needs=('mini', 'pom2-src'))
step('mini33_write', 'writes', 'mini', {}, args=MINI_ROOT, needs=('mini', 'pom2-src'))
step('mini33_ops', 'tags', 'mini', {}, args=MINI_ROOT, needs=('mini', 'pom2-src'))
step('mini33_format', 'format', 'mini', {}, args=MINI_ROOT, needs=('mini', 'pom2-src'))
step('mini33_brun', 'run', 'mini', {}, args=MINI_ROOT, needs=('mini', 'pom2-src'))
step('mini33_review', 'fixes', 'mini', {}, args=MINI_ROOT, needs=('mini', 'pom2-src'))
step('mini33_time', 'cycles', 'mini', {}, args=MINI_ROOT, needs=('mini', 'pom2-src'))
step('mini33_lend', 'hooks', 'mini', {}, args=MINI_ROOT, needs=('mini', 'pom2-src'))

STEPS = tuple(_STEPS)
GROUPS = tuple(dict.fromkeys(s.group for s in STEPS))

# The files that are not benches: the emulator driver and the fixtures builders.
HELPERS = {
    'pom2': 'the emulator driver',
    'all': 'this runner',
    'plugins': 'the overlay bench list, a step of this runner',
    'xplug': 'the ! menu helpers the overlay benches share',
    'archive_support': 'substitutes a reader for FORMAT in a disposable floppy',
    'build_dos_host': 'builds the write-back POM2 host (fixture)',
    'build_pt3_trace': 'builds the AY-tracing POM2 host (fixture)',
    'vsdrive_server': 'the VSDrive server bench/vdrive.py talks to',
}


def ports(bench):
    """The ports a bench answers on, read from its source -- never written here."""
    text = (BENCH / (bench + '.py')).read_text()
    return {int(n) for n in re.findall(r'(?:PORT\s*=\s*|port=)(\d{4})', text)}


def missing(step_):
    """What a step needs and does not have, as '(tag: how to build it)'."""
    for tag in step_.needs:
        fixture = FIXTURES[tag]
        absent = [p for p in fixture.paths if not p.exists()]
        if absent:
            hint = ' '.join(fixture.build) if fixture.build else 'not buildable here'
            return '%s: %s' % (tag, hint)
    return None


def stale():
    """Disk images older than the build they carry.

    `make all` relinks the resident and the overlays but does not restage the
    volumes: only `make disk` does. A bench then boots the previous binary
    with the new overlays -- on 2026-09-14 that cost two debugging rounds,
    and it looks like a crash at boot, not like a stale file.
    """
    late = []
    for build in ('build', 'build-6502'):
        resident = ROOT / build / 'A2FILE.CODE.BIN'
        if not resident.exists():
            continue
        made = resident.stat().st_mtime
        images = list((ROOT / build).glob('*.po'))          # the bench floppies
        cpu = '6502' if build.endswith('6502') else '65C02'
        names = (['A2FILECMD-PRODOS-140K-%s.po' % VERSION, 'A2FILECMD-PRODOS-800K-%s.po' % VERSION,
                  'A2FILECMD-PRODOS-XL-%s.2mg' % VERSION] if cpu == '6502' else
                 ['A2FILECMD-PRODOS-XL-65C02-enhanced-%s.2mg' % VERSION])
        images += [ROOT / 'dist' / name for name in names if (ROOT / 'dist' / name).exists()]
        late += [p for p in images if p.stat().st_mtime < made]
    return sorted(late)


def build_fixtures(tags, run_make):
    """--setup: build what is missing and can be built."""
    for tag in tags:
        fixture = FIXTURES[tag]
        if all(p.exists() for p in fixture.paths) or not fixture.build:
            continue
        if fixture.build[0] == 'make' and not run_make:
            print('== skipped (--make): %s' % ' '.join(fixture.build), flush=True)
            continue
        print('== %s' % ' '.join(fixture.build), flush=True)
        result = subprocess.run(fixture.build, cwd=ROOT)
        if result.returncode:
            return False
    return True


def run_step(step_, out, timeout):
    """One bench in its own process, its output kept in its own log."""
    argv = [sys.executable, str(BENCH / (step_.bench + '.py'))] + step_.args
    if step_.bench == 'plugins':                # it wants a directory of its own
        argv += ['--out', str(out / ('plugins-' + step_.name.split(':')[1]))]
    elif step_.bench == 'run':
        argv += ['--out', str(out / step_.name.replace(':', '-'))]
    log = out / (step_.name.replace(':', '-') + '.log')
    start = time.time()
    with log.open('w') as handle:
        handle.write('$ %s %s\n\n' % (' '.join('%s=%s' % kv for kv in sorted(step_.env.items())),
                                      ' '.join(argv)))
        handle.flush()
        process = subprocess.Popen(argv, cwd=ROOT, stdout=handle, stderr=subprocess.STDOUT,
                                   env={**os.environ, **step_.env}, start_new_session=True)
        try:
            code = process.wait(timeout)
        except subprocess.TimeoutExpired:
            # Its own session: the emulator dies with the bench, instead of
            # keeping its port and failing whatever runs there next.
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            handle.write('\n== no answer after %d s\n' % timeout)
            code = 'timeout'
    return code, time.time() - start, log


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--out', type=Path, default=Path('/tmp/a2fc-bench'), help='one log per step')
    parser.add_argument('--group', nargs='+', choices=GROUPS, help='only these groups')
    parser.add_argument('--only', nargs='+', help='only these steps (bench or bench:label)')
    parser.add_argument('--jobs', type=int, default=1, help='benches at once; ports never collide')
    parser.add_argument('--timeout', type=int, default=1800, help='seconds before a bench is lost')
    parser.add_argument('--list', action='store_true', help='print the steps and stop')
    parser.add_argument('--strict', action='store_true', help='a missing fixture is a failure')
    parser.add_argument('--setup', action='store_true', help='build the missing fixtures first')
    parser.add_argument('--make', action='store_true', help='--setup may also run make')
    args = parser.parse_args()

    chosen = [s for s in STEPS
              if (not args.group or s.group in args.group)
              and (not args.only or s.name in args.only or s.bench in args.only)]
    if args.only:
        unknown = set(args.only) - {s.name for s in chosen} - {s.bench for s in chosen}
        if unknown:
            parser.error('unknown bench: ' + ', '.join(sorted(unknown)))
    if args.list:
        for s in chosen:
            gap = missing(s)
            print('%-24s %-8s %-40s %s' % (s.name, s.group,
                                           ' '.join('%s=%s' % kv for kv in sorted(s.env.items())) or '-',
                                           '' if gap is None else 'needs ' + gap))
        print('%d steps, %d benches' % (len(chosen), len({s.bench for s in chosen})))
        return 0

    if args.setup and not build_fixtures(sorted({t for s in chosen for t in s.needs}), args.make):
        return 2
    old = stale()
    if old:
        print('== %d images older than build/ (make disk): %s'
              % (len(old), ', '.join(p.name for p in old[:3])), flush=True)
        if args.strict:
            return 2
    args.out.mkdir(parents=True, exist_ok=True)

    results, skipped = [], []
    todo = list(chosen)
    running = {}                                 # future -> (step, ports)
    from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        while todo or running:
            busy = {p for _, taken in running.values() for p in taken}
            while todo and len(running) < max(1, args.jobs):
                nxt = next((s for s in todo if not (ports(s.bench) & busy)), None)
                if nxt is None:
                    break
                todo.remove(nxt)
                gap = missing(nxt)
                if gap is not None:
                    print('SKIP %-24s %s' % (nxt.name, gap), flush=True)
                    skipped.append((nxt, gap))
                    continue
                taken = ports(nxt.bench)
                busy |= taken
                running[pool.submit(run_step, nxt, args.out, args.timeout)] = (nxt, taken)
            if not running:
                continue
            done, _ = wait(list(running), return_when=FIRST_COMPLETED)
            for future in done:
                finished, _ = running.pop(future)
                code, seconds, log = future.result()
                ok = code == 0
                results.append((finished, ok, seconds, log))
                print('%s %-24s %5.0fs  %s' % ('PASS' if ok else 'FAIL', finished.name, seconds,
                                               '' if ok else log), flush=True)

    failed = [r for r in results if not r[1]]
    print('\n%d/%d steps, %d skipped' % (len(results) - len(failed), len(results), len(skipped)))
    for s, gap in skipped:
        print('  skipped %-22s %s' % (s.name, gap))
    for s, _, _, log in failed:
        print('  failed  %-22s %s' % (s.name, log))
    return 1 if failed or (args.strict and skipped) else 0


if __name__ == '__main__':
    sys.exit(main())
