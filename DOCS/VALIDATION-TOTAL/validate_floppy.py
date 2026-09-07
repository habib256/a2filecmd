"""Banc POM2 de la disquette APPLE.TOTAL : l'emulateur amorce la disquette
(Disk II en slot 6, devant le disque dur), TOTAL demarre a la racine du
volume, F ouvre le formateur, ESC revient a TOTAL (TOTAL.SYSTEM est a la
racine de la disquette, pas dans TOTAL/), et la musique de TEST joue.
    python3 DOCS/VALIDATION-TOTAL/validate_floppy.py
"""
import sys, os, re, time, shutil, tempfile, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[2]
os.chdir(ROOT)
sys.path.insert(0, 'SCOSWAMP.MORE/TOOLS')
import playtest as pt
labels = {n: int(a, 16) for a, n in re.findall(r'al ([0-9A-F]+) \.(\w+)', pathlib.Path('SCOSWAMP/SRC/total.lbl').read_text())}
def ok(label, cond, detail=''):
    print(('PASS ' if cond else 'FAIL ') + label, detail, flush=True)
    if not cond: raise AssertionError(label + ' ' + str(detail))
with tempfile.TemporaryDirectory(prefix='total-floppy-') as work:
    work = pathlib.Path(work)
    disk = work / 'TEST.hdv'; shutil.copyfile(pt.HDV_SRC, disk)
    floppy = work / 'APPLE.TOTAL.dsk'; shutil.copyfile('dist/APPLE.TOTAL.dsk', floppy)
    p = pt.Pom2(str(disk), port=6542)
    real_popen = pt.subprocess.Popen
    def popen(args, **kw):
        if args and str(args[0]).endswith('pom2_playtest'): args = args[:-1] + ['--disk', str(floppy), '--boot', '6'] + args[-1:]
        return real_popen(args, **kw)
    pt.subprocess.Popen = popen
    def value(name, n=2): return int.from_bytes(p.peek(labels['_total_' + name], n), 'little')
    def active(): return p.peek(labels['_music_active'], 1)[0]   # le lecteur : 0 quand le flux est fini
    def rows(): return p.screen()
    def has(needle): return any(needle in r for r in rows())
    def wait(test, what, seconds=30):
        deadline = time.time() + seconds
        while time.time() < deadline:
            if test(): return
            time.sleep(.05)
        print('\n'.join(p.screen()), flush=True); raise AssertionError('Timed out: ' + what)
    def key(k): p.raw(k); time.sleep(.15)
    def cursor_row(x):
        main = p.peek(0x400, 1024); aux = p.peek(0x400, 1024, 'aux')
        for r in range(2, 20):
            base = 0x80 * (r % 8) + 0x28 * (r // 8)
            cells = [aux[base + c // 2] if c % 2 == 0 else main[base + c // 2] for c in range(x, x + 38)]
            if all(v < 0x80 for v in cells[:16]): return r
    def select(x, name):
        for _ in range(12): key(b'<')
        for _ in range(60):
            r = cursor_row(x); line = rows()[r][x:x + 38] if r is not None else ''
            if line.startswith(name + ' '): return
            key(b'\x0a')
        raise AssertionError('cannot select ' + name)
    try:
        p.start()
        wait(lambda: has('APPLE IIe TOTAL COMMANDER'), 'loader banner', 60)
        ok('la disquette amorce sur le lanceur de TOTAL', has('ProDOS 8 only') or has('PLEASE WAIT') or has('GPL'))
        wait(lambda: has('Type  Aux     Size'), 'TOTAL', 60); p.stable()
        ok('TOTAL demarre a la racine /APPLE.TOTAL', rows()[0].startswith('/APPLE.TOTAL'), rows()[0][:40])
        ok('le panneau droit montre les volumes', '[Volumes]' in rows()[0])
        ok('la disquette est vue avec ses blocs libres', any('/APPLE.TOTAL' in r and 'S6,D1' in r for r in rows()))
        key(b'F'); wait(lambda: has('Open the disk formatter?'), 'confirm'); key(b'Y')
        wait(lambda: has('FORMAT A DISK FOR PRODOS'), 'formatter', 60); p.stable()
        ok('F lance TOTAL/FORMAT.SYS depuis la disquette', has('Press the number'))
        ok('la disquette est marquee IN USE', any('/APPLE.TOTAL' in r and 'IN USE' in r for r in rows()))
        key(b'\x1b'); wait(lambda: has('Type  Aux     Size'), 'back to TOTAL', 60); p.stable()
        ok('ESC revient a TOTAL (TOTAL.SYSTEM a la racine)', rows()[0].startswith('/APPLE.TOTAL'), rows()[0][:40])
        key(b'?'); wait(lambda: value('view', 1) == 4, 'help'); p.stable()
        ok('l aide se lit sur la disquette', has('APPLE IIe TOTAL COMMANDER 1.0') and has('NAVIGATION'))
        key(b'\x1b'); wait(lambda: value('view', 1) == 0, 'back'); p.stable()
        # la musique de TEST : WELCOME.MB joue une fois sur la Mockingboard du slot 2
        select(0, 'TEST'); key(b'\r'); wait(lambda: rows()[0].startswith('/APPLE.TOTAL/TEST'), 'TEST'); p.stable()
        ok('le dossier TEST est present', has('WELCOME') and has('README') and has('DHGR'))
        select(0, 'WELCOME.MB'); key(b'\r'); wait(lambda: value('playing', 1) == 1, 'music', 20)
        ok('WELCOME.MB joue sur la Mockingboard', value('playing', 1) == 1 and value('slot', 1) == 2)
        select(0, 'DHGR.RLE'); key(b'\r'); wait(lambda: value('view', 1) == 1, 'image', 20); time.sleep(1)
        ok('DHGR.RLE s affiche, la musique continue', value('view', 1) == 1 and value('playing', 1) == 1)
        key(b'\x1b'); wait(lambda: value('view', 1) == 0, 'back'); p.stable()
        wait(lambda: active() == 0, 'music ends (plays once)', 300)
        ok('la musique s arrete d elle-meme : jouee une fois', active() == 0)
        print('DONE')
    finally:
        p.stop()
