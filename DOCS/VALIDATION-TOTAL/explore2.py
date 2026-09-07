"""Seconde exploration (chasse finale) de TOTAL sur un volume de test : dossier de
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
with tempfile.TemporaryDirectory(prefix='total-explore2-') as work:
    work = pathlib.Path(work); stage = work / 'vol'
    for d in ('TOTAL', 'BIG', 'EMPTY', 'AAAAAAAAAAAAAAA/BBBBBBBBBBBBBBB'): (stage / d).mkdir(parents=True)
    shutil.copy('SCOSWAMP/PRODOS.SYS', stage); shutil.copy('dist/.floppy/TOTAL.SYSTEM.SYS', stage)
    for f in ('TOTAL.CODE.BIN', 'TOTAL.HELP.TXT', 'FORMAT.SYS.SYS'): shutil.copy('SCOSWAMP/TOTAL/' + f, stage / 'TOTAL')
    for i in range(1, 151): (stage / 'BIG' / f'F{i:03d}.TXT').write_bytes(b'x\r')
    (stage / 'LONG.TXT').write_bytes((b'L' * 200 + b'\r') * 5 + b'END\r')
    (stage / 'ZERO.TXT').write_bytes(b''); (stage / 'ZERO.RLE.BIN').write_bytes(b'')
    (stage / 'AAAAAAAAAAAAAAA/BBBBBBBBBBBBBBB/CCCCCCCCCCCCCCC.TXT').write_bytes(b'deep\r')
    (stage / 'TWO.TXT').write_bytes(b'two\r'); (stage / 'ONE.TXT').write_bytes(b'one\r')
    (stage / 'SMALL.TXT').write_bytes(b'abcdefgh\r'); (stage / 'NOCR.TXT').write_bytes(b'no newline at end'); (stage / 'LF.TXT').write_bytes(b'a\nb\nc\n')
    (stage / 'FAKE.IMG.BIN').write_bytes(bytes(8192))
    subprocess.run([str(TOOLS / 'build/build_prodos_volume'), str(stage), str(TOOLS / 'prodos_boot.tmpl'), str(work / 'EXPLORE.hdv'), 'EXPLORE'], check=True, capture_output=True)
    p = pt.Pom2(str(work / 'EXPLORE.hdv'), port=6547)
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
        print('\n'.join(rows()), flush=True); raise AssertionError('cannot select ' + name)
    try:
        p.start(); wait(lambda: has('Type  Aux     Size'), 'boot', 40); p.stable()
        # 1. editeur : raccourcir un fichier et sauver (SET_EOF de cc65)
        select(0, 'SMALL'); key(b'E'); wait(lambda: value('view', 1) == 5, 'editor'); p.stable()
        for _ in range(4): key(b'\x04')
        p.stable(); ok('Ctrl-D x4 : 5/8176 octets', has('5/8176 bytes'), rows()[23][30:60])
        key(b'\x1b'); wait(lambda: has('Save'), 'menu'); key(b'X'); wait(lambda: value('view', 1) == 0, 'exit'); p.stable()
        ok('le fichier raccourci fait 5 octets sur le disque', any(r.startswith('SMALL ') and '   5 ' in r for r in rows()), line(0))
        key(b'H'); wait(lambda: value('view', 1) == 3, 'hex'); p.stable()
        ok('hexa : 65 66 67 68 0D, rien apres', has('65 66 67 68 0D') and has('5 bytes'), rows()[1][:50])
        key(b'\x1b'); wait(lambda: value('view', 1) == 0, 'back'); p.stable()
        # 2. editeur sur un fichier sans CR final, et sur des LF
        select(0, 'NOCR'); key(b'E'); wait(lambda: value('view', 1) == 5, 'editor'); p.stable()
        key(b'\x02'); p.stable(); ok('sans CR final : Ctrl-B en colonne 18 de la ligne 1', has('Line 1  Col 18'), rows()[23][30:60])
        p.keys('!'); key(b'\x1b'); wait(lambda: has('Save'), 'menu'); key(b'X'); wait(lambda: value('view', 1) == 0, 'exit'); p.stable()
        ok('NOCR sauve a 18 octets', any(r.startswith('NOCR ') and '  18 ' in r for r in rows()), line(0))
        select(0, 'LF'); key(b'\r'); wait(lambda: value('view', 1) == 2, 'text'); p.stable()
        ok('LF seuls : trois lignes a, b, c', rows()[0].startswith('a') and rows()[1].startswith('b') and rows()[2].startswith('c'))
        key(b'\x1b'); wait(lambda: value('view', 1) == 0, 'back'); p.stable()
        # 3. fichier verrouille : l editeur ne peut pas sauver, pas de plantage
        select(0, 'TWO'); key(b'L'); p.stable(); ok('L verrouille TWO', line(0)[15:17].strip() == 'L', line(0))
        key(b'E'); wait(lambda: value('view', 1) == 5, 'editor'); p.keys('x'); key(b'\x1b'); wait(lambda: has('Save'), 'menu'); key(b'S'); p.stable()
        ok('sauver un verrouille : erreur affichee, editeur encore la', has('Save failed') and value('view', 1) == 5, rows()[22].strip())
        key(b'\x1b'); wait(lambda: has('Save'), 'menu'); key(b'Q'); wait(lambda: has('Discard'), 'discard'); key(b'Y'); wait(lambda: value('view', 1) == 0, 'exit'); p.stable()
        ok('TWO intact, toujours verrouille, 4 octets', line(0).startswith('TWO ') and 'L' in line(0)[15:17] and '   4 ' in line(0), line(0))
        key(b'L'); p.stable()
        # 4. fausse image : 8192 octets de zeros type BIN
        select(0, 'FAKE.IMG'); key(b'\r'); wait(lambda: value('view', 1) == 1 or has('not an image'), 'fake'); time.sleep(.5)
        ok('FAKE.IMG (8 Ko de zeros) : affiche comme HGR brute ou refuse, sans plantage', value('view', 1) == 1 or has('not an image'), str(value('view', 1)))
        if value('view', 1) == 1: key(b'\x1b'); wait(lambda: value('view', 1) == 0, 'back')
        p.stable(); ok('les panneaux reviennent', has('Type  Aux     Size'))
        # 5. marques : une seule dans une fenetre pleine (pas de fantomes), copie depuis la 2e fenetre
        key(b'\t'); key(b'/'); wait(lambda: rows()[0][40:].startswith('[Volumes]'), 'vol'); select(40, '/EXPLORE'); key(b'\r'); wait(lambda: rows()[0][40:].startswith('/EXPLORE '), 'expl'); select(40, 'EMPTY'); key(b'\r'); wait(lambda: rows()[0][40:].startswith('/EXPLORE/EMPTY'), 'EMPTY'); key(b'\t')
        select(0, 'BIG'); key(b'\r'); wait(lambda: has('/EXPLORE/BIG'), 'BIG'); p.stable()
        key(b'\x0a'); p.stable(); key(b' '); p.stable()
        ok('une marque dans une fenetre pleine : "1 tagged"', has('1 tagged') and not has('5 tagged'), rows()[21][60:])
        key(b'\x0b'); key(b' '); p.stable()
        key(b']'); key(b'\x0a'); time.sleep(.5); p.stable(); ok('2e fenetre', rows()[1].startswith('139 + disk order'))
        n2 = line(0).split()[0]; key(b' '); n3 = line(0).split()[0]; key(b' '); p.stable()
        ok('deux marques en 2e fenetre', has('2 tagged'), rows()[21][60:] + ' ' + n2 + ' ' + n3)
        key(b'C'); wait(lambda: has('files copied') or has('failed'), 'copy', 30); p.stable()
        ok('copie des deux marques vers EMPTY', any(r[40:].startswith(n2 + ' ') for r in rows()) and any(r[40:].startswith(n3 + ' ') for r in rows()), rows()[22].strip())
        # 6. deplacement vers un autre volume (/RAM)
        key(b'\x1b'); wait(lambda: has('/EXPLORE  '), 'root'); key(b'\t'); key(b'/'); wait(lambda: has('[Volumes]'), 'volumes'); select(40, '/RAM'); key(b'\r'); wait(lambda: rows()[0][40:].startswith('/RAM '), 'ram'); key(b'\t')
        select(0, 'ONE'); key(b'V'); wait(lambda: has('moved') or has('failed'), 'move', 30); p.stable()
        ok('V deplace ONE vers /RAM', any(r[40:].startswith('ONE ') for r in rows()) and not any(r.startswith('ONE ') for r in rows()), rows()[22].strip())
        key(b'\t'); select(40, 'ONE'); key(b'\r'); wait(lambda: value('view', 1) == 2, 'text'); p.stable()
        ok('ONE sur /RAM se lit : one', rows()[0].startswith('one'))
        key(b'\x1b'); wait(lambda: value('view', 1) == 0, 'back'); key(b'\t')
        # 7. les deux panneaux sur le meme dossier : copie refusee
        key(b'\t'); key(b'\x1b'); wait(lambda: rows()[0][40:].startswith('[Volumes]'), 'vol'); select(40, '/EXPLORE'); key(b'\r'); wait(lambda: rows()[0][40:].startswith('/EXPLORE '), 'expl'); key(b'\t')
        select(0, 'TWO'); key(b'C'); p.stable()
        ok('copie vers le meme dossier refusee', has('Both panels show the same directory'), rows()[22].strip())
        # 8. suppression de l arbre BIG (150 fichiers), espace libere
        before = rows()[20]
        select(0, 'BIG'); key(b'D'); wait(lambda: has('Delete BIG and everything inside?'), 'confirm'); key(b'Y'); wait(lambda: not any(r.startswith('BIG ') for r in rows()), 'deleted', 90); p.stable()
        ok('BIG supprime, blocs libres en hausse', not has('BIG ') and rows()[20] != before, rows()[20][30:60])
        print('DONE')
    finally:
        p.stop()
