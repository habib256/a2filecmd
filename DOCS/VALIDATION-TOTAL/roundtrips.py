"""Cinq allers-retours TOTAL -> F (formateur) -> ESC -> TOTAL : ProDOS n'a que
quatre entrees d'interruption, un talon qui ne les libere pas finit sur
« Failed to alloc interrupt »."""
import sys, os, re, time, shutil, tempfile, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[2]; os.chdir(ROOT); sys.path.insert(0, 'SCOSWAMP.MORE/TOOLS')
import playtest as pt
with tempfile.TemporaryDirectory(prefix='total-rt-') as work:
    disk = pathlib.Path(work) / 'TEST.hdv'; shutil.copyfile(pt.HDV_SRC, disk)
    p = pt.Pom2(str(disk), port=6543)
    def rows(): return p.screen()
    def has(n): return any(n in r for r in rows())
    def wait(test, what, seconds=60):
        t = time.time() + seconds
        while time.time() < t:
            if test(): return True
            time.sleep(.05)
        print('\n'.join(rows())); return False
    def key(k): p.raw(k); time.sleep(.15)
    try:
        p.start(); p.wait_for('LANGUE'); p.keys('T'); assert wait(lambda: has('Type  Aux     Size'), 'TOTAL')
        for i in range(5):
            key(b'F'); assert wait(lambda: has('Open the disk formatter?'), 'confirm'); key(b'Y')
            assert wait(lambda: has('FORMAT A DISK FOR PRODOS'), 'formatter')
            key(b'\x1b')
            back = wait(lambda: has('Type  Aux     Size') or has('alloc interrupt') or has('BITSY'), 'back')
            print('round', i + 1, 'TOTAL' if has('Type  Aux     Size') else 'FAILED: ' + ' | '.join(r.strip() for r in rows() if r.strip())[:1500], flush=True)
            if not has('Type  Aux     Size'): break
            time.sleep(.5)
    finally:
        p.stop()
