"""Exploration des cas limites de TOTAL sur un volume de test : dossier de
150 entrees (mode fenetre), dossier vide, fichiers de 0 octet, lignes de
200 caracteres, chemins trop longs, renommage en double, disque plein.
Imprime les ecrans ; les FAIL sont a lire par un humain.

    python3 DOCS/VALIDATION-TOTAL/explore.py
"""
import sys, os, re, time, shutil, tempfile, subprocess, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[2]; os.chdir(ROOT)
sys.path.insert(0, 'SCOSWAMP.MORE/TOOLS')
import playtest as pt
labels = {n: int(a, 16) for a, n in re.findall(r'al ([0-9A-F]+) \.(\w+)', pathlib.Path('SCOSWAMP/SRC/total.lbl').read_text())}
TOOLS = ROOT / 'SCOSWAMP.MORE/TOOLS'
def ok(label, cond, detail=''):
    print(('PASS ' if cond else 'FAIL ') + label, detail, flush=True)
with tempfile.TemporaryDirectory(prefix='total-explore-') as work:
    work = pathlib.Path(work); stage = work / 'vol'
    for d in ('TOTAL', 'BIG', 'EMPTY', 'AAAAAAAAAAAAAAA/BBBBBBBBBBBBBBB'): (stage / d).mkdir(parents=True)
    shutil.copy('SCOSWAMP/PRODOS.SYS', stage); shutil.copy('dist/.floppy/TOTAL.SYSTEM.SYS', stage)
    for f in ('TOTAL.CODE.BIN', 'TOTAL.HELP.TXT', 'FORMAT.SYS.SYS'): shutil.copy('SCOSWAMP/TOTAL/' + f, stage / 'TOTAL')
    for i in range(1, 151): (stage / 'BIG' / f'F{i:03d}.TXT').write_bytes(b'x\r')
    (stage / 'LONG.TXT').write_bytes((b'L' * 200 + b'\r') * 5 + b'END\r')
    (stage / 'ZERO.TXT').write_bytes(b''); (stage / 'ZERO.RLE.BIN').write_bytes(b'')
    (stage / 'AAAAAAAAAAAAAAA/BBBBBBBBBBBBBBB/CCCCCCCCCCCCCCC.TXT').write_bytes(b'deep\r')
    (stage / 'TWO.TXT').write_bytes(b'two\r'); (stage / 'ONE.TXT').write_bytes(b'one\r')
    subprocess.run([str(TOOLS / 'build/build_prodos_volume'), str(stage), str(TOOLS / 'prodos_boot.tmpl'), str(work / 'EXPLORE.hdv'), 'EXPLORE'], check=True, capture_output=True)
    p = pt.Pom2(str(work / 'EXPLORE.hdv'), port=6546)
    def value(name, n=2): return int.from_bytes(p.peek(labels['_total_' + name], n), 'little')
    def rows(): return p.screen()
    def has(n): return any(n in r for r in rows())
    def wait(f, what, s=20):
        d = time.time() + s
        while time.time() < d:
            if f(): return
            time.sleep(.05)
        print('\n'.join(rows()), flush=True); raise AssertionError('timeout ' + what)
    def key(k): p.raw(k); time.sleep(.15)
    def cursor_row(x):
        main = p.peek(0x400, 1024); aux = p.peek(0x400, 1024, 'aux')
        for r in range(2, 20):
            base = 0x80*(r%8)+0x28*(r//8)
            if all(v < 0x80 for v in [aux[base+c//2] if c%2==0 else main[base+c//2] for c in range(x, x+16)]): return r
    def line(x): r = cursor_row(x); return rows()[r][x:x+38] if r is not None else ''
    def select(x, name):
        for _ in range(12): key(b'<')
        for _ in range(160):
            if line(x).startswith(name + ' '): return
            key(b'\x0a')
        raise AssertionError('cannot select ' + name)
    try:
        p.start(); wait(lambda: has('Type  Aux     Size'), 'boot', 40); p.stable()
        # 1. dossier de 150 entrees : fenetres
        select(0, 'BIG'); key(b'\r'); wait(lambda: has('/EXPLORE/BIG'), 'BIG'); p.stable()
        ok('BIG : mode fenetre annonce en tete', rows()[1].startswith('0   + disk order'), rows()[1][:40])
        key(b']'); p.stable(); last = line(0)
        ok('] va au dernier de la fenetre (F139)', last.startswith('F139 '), last)
        key(b'\x0a'); time.sleep(.5); p.stable()
        ok('Bas apres le dernier charge la fenetre suivante', rows()[1].startswith('139 + disk order') and line(0).startswith('F140 '), rows()[1][:24] + ' | ' + line(0)[:12])
        key(b']'); p.stable(); ok('la 2e fenetre finit a F150', line(0).startswith('F150 '), line(0)[:12])
        key(b'['); p.stable(); key(b'\x0b'); time.sleep(.5); p.stable()
        ok('Haut avant le premier revient a la fenetre 1, curseur en bas', rows()[1].startswith('0   + disk order') and line(0).startswith('F139 '), line(0)[:12])
        key(b'\x1b'); wait(lambda: has('/EXPLORE  '), 'up'); p.stable()
        ok('ESC depuis une fenetre remonte et reselectionne BIG', line(0).startswith('BIG '), line(0)[:10])
        # 2. dossier vide
        select(0, 'EMPTY'); key(b'\r'); wait(lambda: has('/EXPLORE/EMPTY'), 'EMPTY'); p.stable()
        ok('EMPTY ne montre que ..', rows()[2].startswith('..') and rows()[3][:38].strip() == '')
        key(b'D'); p.stable(); ok('D sur .. : refus', has('Nothing to delete'))
        key(b'C'); p.stable(); ok('C sur .. : refus propre', has('Both panels') or has('Select') or has('Open a directory') or has('0 file'), rows()[22].strip())
        key(b'\x1b'); wait(lambda: has('/EXPLORE  '), 'up'); p.stable()
        # 3. fichiers de 0 octet
        select(0, 'ZERO'); key(b'\r'); wait(lambda: value('view', 1) == 2, 'text 0'); p.stable()
        ok('ZERO (TXT vide) : visionneuse texte, page 1 (end)', has('page 1 (end)'))
        key(b'\x1b'); wait(lambda: value('view', 1) == 0, 'back'); key(b'H'); wait(lambda: value('view', 1) == 3, 'hex 0'); p.stable()
        ok('ZERO en hexa : 0 bytes page 1/1', has('0 bytes page 1/1'))
        key(b'\x1b'); wait(lambda: value('view', 1) == 0, 'back'); p.stable()
        select(0, 'ZERO.RLE'); key(b'\r'); wait(lambda: has('not an image'), 'zero rle'); p.stable()
        ok('ZERO.RLE (0 octet) : refuse comme image sans planter', has('ZERO.RLE: not an image'))
        # 4. lignes de 200 caracteres
        select(0, 'LONG'); key(b'\r'); wait(lambda: value('view', 1) == 2, 'text long'); p.stable()
        ok('LONG en visionneuse : lignes coupees, END visible', rows()[0].startswith('L' * 79) and has('END'))
        key(b'\x1b'); wait(lambda: value('view', 1) == 0, 'back'); key(b'E'); wait(lambda: value('view', 1) == 5, 'editor'); p.stable()
        key(b'\x05'); p.stable(); ok('editeur : Ctrl-E sur une ligne de 200, colonne 201 annoncee', has('Col 201'), rows()[23][:60])
        key(b'\x0a'); key(b'\x0a'); p.stable(); ok('deux Bas : ligne 3', has('Line 3'))
        key(b'\x02'); p.stable(); ok('Ctrl-B : fin du texte, apres le dernier CR : ligne 7 vide', has('Line 7  Col 1'), rows()[23][30:70])
        p.keys('Z'); key(b'\x1b'); wait(lambda: has('Quit without saving'), 'menu'); key(b'Q'); wait(lambda: has('Discard'), 'discard'); key(b'Y'); wait(lambda: value('view', 1) == 0, 'exit'); p.stable()
        ok('Q puis Y abandonne sans sauver : LONG garde 1009 octets', any(r.startswith('LONG ') and '1009' in r for r in rows()))
        # 5. chemin trop long
        select(0, 'AAAAAAAAAAAAAAA'); key(b'\r'); wait(lambda: has('/EXPLORE/AAAAAAAAAAAAAAA'), 'A'); select(0, 'BBBBBBBBBBBBBBB'); key(b'\r'); wait(lambda: any(r.startswith('CCCCCCCCCCCCCCC ') for r in rows()), 'B'); p.stable()
        ok('chemin long : le panneau montre la fin du chemin', rows()[0].startswith('/AAAAAAAAAAAAAAA/BBBBBBBBBBBBBBB') or rows()[0][:38].endswith('BBBBBBBBBBBBBBB'), rows()[0][:38])
        select(0, 'CCCCCCCCCCCCCCC'); key(b'\r'); wait(lambda: value('view', 1) == 2, 'deep text'); p.stable()
        ok('un chemin de 56 caracteres s ouvre (limite ProDOS 64)', rows()[0].startswith('deep'))
        key(b'\x1b'); wait(lambda: value('view', 1) == 0, 'back'); p.stable()
        key(b'\x1b'); wait(lambda: has('/EXPLORE/AAAAAAAAAAAAAAA '), 'A'); key(b'\x1b'); wait(lambda: has('/EXPLORE  '), 'root'); p.stable()
        # 6. renommage vers un nom existant
        select(0, 'ONE'); key(b'R'); wait(lambda: has('New name:'), 'rename'); p.raw(b'\x08\x08\x08'); p.keys('TWO'); key(b'\r'); p.stable()
        ok('renommer ONE en TWO (existant) : erreur ProDOS affichee, ONE intact', has('Rename failed') and any(r.startswith('ONE ') for r in rows()), rows()[22].strip())
        # 7. disque plein : copier BIG (150 fichiers) vers /RAM (127 blocs)
        key(b'\t'); key(b'/'); wait(lambda: has('[Volumes]'), 'volumes'); select(40, '/RAM'); key(b'\r'); wait(lambda: rows()[0][40:].startswith('/RAM '), 'ram'); key(b'\t')
        select(0, 'BIG'); key(b'C'); wait(lambda: has('failed') or has('files copied'), 'copy big', 120); p.stable()
        ok('copie de 150 fichiers vers /RAM plein : erreur annoncee, pas de plantage', has('failed'), rows()[22].strip())
        ok('le panneau /RAM a ete relu apres l echec', any(r[40:].startswith('BIG ') for r in rows()))
        key(b'Q'); wait(lambda: has('Quit to ProDOS?'), 'quit'); key(b'Y'); time.sleep(1)
        print('DONE', flush=True)
    finally:
        p.stop()
