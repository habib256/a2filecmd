#!/usr/bin/env python3
"""VDrive never touches the printer: the Super Serial Card of slot 1.

    make disk && make pom2host && python3 bench/vdrive_printer.py

A //e keeps its printer on the SSC of slot 1; on a //c, port 1 IS the
printer port. VDrive (src/vsdrive.s) used to take the first serial card it
found, slot 2 then slot 1: with no card in slot 2 it reprogrammed the
printer's 6551 (115,200 bps, DTR) and pushed its $C5 envelopes to the
printer at every volume read. pom2_playtest --printer-ssc LOG plugs a
printer SSC in slot 1 and logs every access to its registers; this bench
drives a session (volume list, reread, a directory, quit) and requires the
log to hold no write -- and no read either: detection must not even look at
that card's 6551.

Three machines, each booting the floppy of the build in use:
  1. the preset of A2FC_PRESET (//e by default): printer in slot 1, no
     serial card in slot 2 -- no VDrive, the printer untouched;
  2. the //c: port 1 printer, port 2 (modem) with no host -- VDrive takes
     port 2, as it always did on a //c, and never port 1;
  3. the same preset with a VDrive host on slot 2 (bench/vsdrive_server.py):
     VDrive still works there, and the printer is still untouched."""

import os, shutil, sys, tempfile, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pom2 import Pom2, Session, DISK, PRESET
from run import scratch_volume, RET, ESC, volume
from vsdrive_server import Server

OFS = int(os.environ.get('A2FC_PORT_OFFSET', '0'))
PORT = 6770             # the emulators of the printer-only sessions: 6770, 6771
SSC_PORT = 6775         # the VSDrive host's socket
HOST_PORT = 6776        # the emulator of the session with VDrive


def playtest_has_printer_ssc():
    """pom2_playtest returns 2 on an unknown flag, before anything else."""
    from pom2 import POM2
    import subprocess
    r = subprocess.run([POM2, '--printer-ssc', os.devnull], capture_output=True)
    return r.returncode != 2


def accesses(log):
    """[(kind, reg, value)] from the --printer-ssc log."""
    out = []
    for line in log.read_text().splitlines():
        k, r, v = line.split()
        out.append((k, int(r, 16), int(v, 16)))
    return out


def describe(acc):
    w = [a for a in acc if a[0] == 'W']
    data = bytes(v for k, r, v in w if r & 11 == 8)
    ctl = ['$%02X' % v for k, r, v in w if r & 11 == 11]
    cmd = ['$%02X' % v for k, r, v in w if r & 11 == 10]
    return ('%d accesses, %d writes: %d data bytes %s, control %s, command %s'
            % (len(acc), len(w), len(data), data[:16].hex(), ctl, cmd))


def session(tmp, preset, tag, port, ssc=None):
    """Boot, list the volumes, reread, open a directory, quit; the log path."""
    floppy = tmp / ('A2FILECMD-%s.po' % tag)
    shutil.copyfile(DISK, floppy)
    log = tmp / ('printer-%s.log' % tag)
    (tmp / tag).mkdir()
    hdv = scratch_volume(tmp / tag)
    with Pom2(hdv, floppy=floppy, port=port, preset=preset, ssc=ssc, printer_log=log) as p:
        s = Session(p)
        s.boot()
        vd = s.rows()[22].strip()
        s.key(b'/'); s.wait(lambda: s.has('[Volumes]'), 'volumes', 60); p.stable()
        vols = ' '.join(r[:40] for r in s.rows()[2:10])
        s.key(b'\x12'); p.stable(); time.sleep(0.5)          # Ctrl-R: read the list again
        s.select('/SCRATCH'); s.key(RET)
        s.wait(lambda: s.rows()[0][:9] == '/SCRATCH ', 'SCRATCH', 60); p.stable()
        s.key(b'Q'); s.wait(lambda: s.has('Quit to ProDOS?'), 'Q'); s.key(b'Y')
        s.wait(lambda: not s.has('Type  Aux     Size'), 'quit', 30); time.sleep(1)
    return log, vd, vols


def main():
    if not playtest_has_printer_ssc():
        print('SKIP pom2_playtest has no --printer-ssc: make pom2host')
        return 0
    checks = []
    def ok(label, cond, detail=''):
        checks.append(bool(cond))
        print(('PASS ' if cond else 'FAIL ') + label + (' ' + str(detail) if detail else ''), flush=True)

    presets = [PRESET] + (['iic'] if PRESET != 'iic' else [])
    with tempfile.TemporaryDirectory(prefix='a2fc-vdprn-') as tmp:
        tmp = Path(tmp)
        for i, preset in enumerate(presets):
            log, vd, vols = session(tmp, preset, preset, PORT + i + OFS)
            acc = accesses(log)
            # The //c always has port 2 (modem): VDrive may take it, never port 1.
            ok('%s: VDrive does not take slot 1' % preset,
               'serial card in slot 2' in vd if preset == 'iic' else 'VDrive' not in vd, vd[:70])
            ok('%s: the slot-1 printer card is never accessed' % preset, not acc, describe(acc))
        # VDrive on slot 2 with the printer in slot 1: both, neither disturbed.
        remote = tmp / 'remote'
        remote.mkdir()
        (remote / 'FAR.TXT').write_bytes(b'served over the serial line\r')
        image = volume(remote, tmp / 'REMOTE.po', 'REMOTE', 280)
        sport = SSC_PORT + OFS
        server = Server([str(image)], port=sport).start()
        try:
            log, vd, vols = session(tmp, PRESET, 'vdrive', HOST_PORT + OFS, ssc=sport)
        finally:
            server.close()
        acc = accesses(log)
        ok('%s + VDrive host: VDrive installs on slot 2' % PRESET, 'VDrive: serial card in slot 2' in vd, vd[:70])
        ok('%s + VDrive host: the remote volume is listed' % PRESET, '/REMOTE' in vols, vols[:80])
        ok('%s + VDrive host: the host served reads' % PRESET, any(e[0] == 'read' for e in server.log), len(server.log))
        ok('%s + VDrive host: the slot-1 printer card is never accessed' % PRESET, not acc, describe(acc))

    passed = sum(1 for c in checks if c)
    print(f'\n{passed}/{len(checks)} checks', flush=True)
    return 0 if passed == len(checks) else 1


if __name__ == '__main__':
    sys.exit(main())
