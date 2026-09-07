"""Banc POM2 du formateur d'Apple IIe Total Commander : une disquette vierge dans
un Disk II en slot 6, TOTAL lance depuis l'ecran-titre du jeu, F, le choix du
lecteur, le nom, le mot ERASE ; puis le volume neuf est verifie depuis
TOTAL (liste des volumes, dossier vide, creation d'un dossier) et, une fois
l'emulateur arrete, dans l'image .dsk elle-meme (amorce, catalogue, table).
Le disque d'ou tourne TOTAL est presente comme non formatable, et le /RAM
est formate a son tour.

    python3 DOCS/VALIDATION-TOTAL/validate_format.py DOCS/VALIDATION-TOTAL
"""
import sys, os, re, json, time, shutil, tempfile, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[2]
os.chdir(ROOT)
sys.path.insert(0, 'SCOSWAMP.MORE/TOOLS')
sys.path.insert(0, 'SCOSWAMP.MORE/TOOLS')
import playtest as pt
from make_floppy import SECTORS, BLOCKS
out = pathlib.Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
labels = {n: int(a, 16) for a, n in re.findall(r'al ([0-9A-F]+) \.(\w+)', pathlib.Path('SCOSWAMP/SRC/total.lbl').read_text())}

checks = []
def ok(label, cond, detail=''):
    print(('PASS ' if cond else 'FAIL ') + label, detail, flush=True)
    checks.append(dict(label=label, ok=bool(cond)))
    if not cond: raise AssertionError(label + ' ' + str(detail))

def from_dsk(dsk):
    po = bytearray(BLOCKS * 512)
    for block in range(BLOCKS):
        track, pair = divmod(block, 8)
        for half, sector in enumerate(SECTORS[pair]):
            po[block * 512 + half * 256:block * 512 + half * 256 + 256] = dsk[(track * 16 + sector) * 256:(track * 16 + sector) * 256 + 256]
    return bytes(po)

with tempfile.TemporaryDirectory(prefix='total-format-') as work:
    work = pathlib.Path(work)
    disk = work / 'TEST.hdv'; shutil.copyfile(pt.HDV_SRC, disk)
    floppy = work / 'BLANK.dsk'; floppy.write_bytes(bytes(143360))
    p = pt.Pom2(str(disk), port=6541)
    p_args_extra = ['--disk', str(floppy)]
    # pom2_playtest accepte --disk : on le glisse dans la ligne de commande
    real_popen = pt.subprocess.Popen
    def popen(args, **kw):
        if args and str(args[0]).endswith('pom2_playtest'): args = args[:-1] + p_args_extra + args[-1:]
        return real_popen(args, **kw)
    pt.subprocess.Popen = popen
    def value(name, n=2): return int.from_bytes(p.peek(labels['_total_' + name], n), 'little')
    def rows(): return p.screen()
    def has(needle): return any(needle in r for r in rows())
    def wait(test, what, seconds=15):
        deadline = time.time() + seconds
        while time.time() < deadline:
            if test(): return
            time.sleep(.05)
        print('\n'.join(p.screen()), flush=True); raise AssertionError('Timed out: ' + what)
    def key(k): p.raw(k); time.sleep(.15)
    def shot(name):
        import urllib.request
        (out / f'format-{name}.txt').write_text('\n'.join(rows()) + '\n')
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
        p.start(); p.wait_for('LANGUE'); p.keys('T'); wait(lambda: has('Type  Aux     Size'), 'TOTAL', 30); p.stable()
        key(b'F'); wait(lambda: has('Open the disk formatter?'), 'confirm'); key(b'Y')
        wait(lambda: has('FORMAT A DISK FOR PRODOS'), 'formatter', 30); p.stable(); shot('list')
        lines = rows()
        ok('le formateur liste les lecteurs', has('Disk II 5.25"') and has('/SCOSWAMP') and has('/RAM'))
        ok('le disque de TOTAL est marque IN USE', any('/SCOSWAMP' in r and 'IN USE' in r for r in lines))
        ok('la disquette vierge est sans volume ProDOS', any('Disk II' in r and 'drive 1' in r and 'no ProDOS volume' in r and '280 blocks' in r for r in lines))
        ok('rien avant confirmation : ESC rend a TOTAL', has('ESC Back to Total Commander'))
        # le disque en usage est refuse
        inuse = next(r for r in lines if 'IN USE' in r)[3]
        key(inuse.encode()); p.stable()
        ok('choisir le disque en usage est refuse', has('cannot be formatted from here'))
        key(b' '); p.stable()
        # la disquette : nom, puis ERASE
        target = next(r for r in lines if 'Disk II' in r and 'drive 1' in r)[3]
        key(target.encode()); wait(lambda: has('Step 2 of 3'), 'name'); p.keys('TESTDISK'); key(b'\r')
        wait(lambda: has('Step 3 of 3'), 'confirm'); shot('confirm')
        ok('l avertissement nomme le lecteur, le type et la perte des donnees', has('slot 6, drive 1') and has('EVERYTHING ON THAT DISK WILL BE LOST FOREVER') and has('/TESTDISK'))
        p.keys('erase'); key(b'\r'); wait(lambda: has('Press the number'), 'list again', 60); p.stable()
        ok('un mot inexact annule sans formater', has('FORMAT A DISK FOR PRODOS') and has('Press the number'))
        key(target.encode()); wait(lambda: has('Step 2 of 3'), 'name'); p.keys('TESTDISK'); key(b'\r'); wait(lambda: has('Step 3 of 3'), 'confirm')
        p.keys('ERASE'); key(b'\r')
        wait(lambda: has('Done: /TESTDISK'), 'format done', 120); shot('done')
        ok('la disquette est formatee : /TESTDISK, 280 blocs', has('Done: /TESTDISK, 280 blocks, 273 free') and has('Read back and verified'))
        # le /RAM aussi
        key(b' '); wait(lambda: has('Press the number'), 'list'); lines = rows()
        ram = next(r for r in lines if '/RAM' in r)[3]
        key(ram.encode()); wait(lambda: has('Step 2 of 3'), 'name'); p.keys('RAMTEST'); key(b'\r'); wait(lambda: has('Step 3 of 3'), 'confirm')
        p.keys('ERASE'); key(b'\r'); wait(lambda: has('Done: /RAMTEST'), 'ram done', 60)
        ok('le /RAM est formate en /RAMTEST', has('Done: /RAMTEST, 127 blocks'))
        key(b'\x1b'); wait(lambda: has('Type  Aux     Size'), 'back to TOTAL', 30); p.stable()
        ok('ESC recharge Total Commander', has('/SCOSWAMP'))
        time.sleep(1); key(b'/'); wait(lambda: has('[Volumes]'), 'volumes'); p.stable(); shot('volumes')
        ok('TOTAL voit /TESTDISK en S6,D1 et /RAMTEST', any('/TESTDISK' in r and 'S6,D1' in r and '273/  280' in r for r in rows()) and any('/RAMTEST' in r for r in rows()))
        select(0, '/TESTDISK'); key(b'\r'); wait(lambda: rows()[0].startswith('/TESTDISK') and rows()[2].startswith('..'), 'enter', 60); time.sleep(.5); p.stable()
        ok('le volume neuf est vide', rows()[2].startswith('..') and rows()[3][:38].strip() == '')
        key(b'K'); wait(lambda: has('New directory:'), 'mkdir'); p.keys('HELLO'); key(b'\r')
        wait(lambda: any(r.startswith('HELLO ') for r in rows()) or has('failed'), 'mkdir on floppy', 60); p.stable(); shot('mkdir')
        ok('on peut y creer un dossier', any(r.startswith('HELLO ') and '<DIR>' in r for r in rows()) and value('errors') == 0, rows()[22].strip())
        key(b'Q'); wait(lambda: has('Quit to ProDOS?'), 'quit'); key(b'Y'); time.sleep(1)
        # lance depuis Bitsy Bye, FORMAT.SYSTEM revient bien a TOTAL (ESC)
        def rows40():
            m = p.peek(0x400, 1024); return [''.join(p._cell(m[0x80*(r%8)+0x28*(r//8)+c]) for c in range(40)) for r in range(24)]
        wait(lambda: any('BITSY  BYE' in r for r in rows40()), 'Bitsy Bye'); time.sleep(.5)
        if '/SCOSWAMP' not in rows40()[0]: p.raw(b'5'); time.sleep(.8)   # TAB,#:NEW VOL -> slot 5, la racine
        r40 = rows40()
        if not any(r.startswith('- FORMAT.SYS') for r in r40):
            row = next(i for i, r in enumerate(r40) if r.startswith('  /TOTAL')); p.raw(b'\x0a' * (row - 2) + b'\r'); time.sleep(.5); r40 = rows40()
        row = next(i for i, r in enumerate(r40) if r.startswith('- FORMAT.SYS')); p.raw(b'\x0a' * (row - 2) + b'\r')
        wait(lambda: has('FORMAT A DISK FOR PRODOS'), 'formatter from Bitsy Bye', 30)
        key(b'\x1b'); wait(lambda: has('Type  Aux     Size'), 'TOTAL after formatter', 30)
        ok('FORMAT.SYS lance par Bitsy Bye revient a TOTAL', has('/SCOSWAMP'))
        key(b'Q'); wait(lambda: has('Quit to ProDOS?'), 'quit'); key(b'Y'); time.sleep(1)
    finally:
        p.stop()
        pt.subprocess.Popen = real_popen
    # l'image .dsk une fois ecrite par l'emulateur
    shutil.copyfile(floppy, out / 'format-TESTDISK.dsk')
    po = from_dsk(floppy.read_bytes())
    print('bloc 0 :', po[:16].hex(), ' bloc 1 :', po[512:528].hex(), ' bloc 2 :', po[1024:1040].hex(), flush=True)
    hdr = po[2 * 512:3 * 512]
    name = hdr[5:5 + (hdr[4] & 15)].decode()
    total = int.from_bytes(hdr[4 + 0x25:4 + 0x27], 'little'); bitmap = int.from_bytes(hdr[4 + 0x23:4 + 0x25], 'little')
    free = sum(bin(x).count('1') for x in po[bitmap * 512:(bitmap + 1) * 512])
    ok('l image .dsk porte le volume TESTDISK de 280 blocs', name == 'TESTDISK' and total == 280 and bitmap == 6)
    ok('l amorce ProDOS est en bloc 0', po[0:2] == b'\x01\x38')
    ok('la table d allocation compte HELLO (272 libres)', free == 272, free)
    (out / 'format-result.json').write_text(json.dumps(dict(checks=checks), indent=2) + '\n')
    print('PASS', len(checks), 'controles', flush=True)
