"""Banc POM2 headless de TOTAL : lancement depuis Bitsy Bye, navigation,
image DHGR verifiee octet a octet, texte, hexa, copie / renommage /
suppression / dossier sur la COPIE du disque, retour a Bitsy Bye.

    python3 DOCS/VALIDATION-TOTAL/validate.py DOCS/VALIDATION-TOTAL
"""
import sys, tempfile, pathlib, shutil, time, json, re, hashlib, gzip, os
ROOT = pathlib.Path(__file__).resolve().parents[2]
os.chdir(ROOT)
sys.path.insert(0, 'SCOSWAMP.MORE/TOOLS')
import playtest as pt
out = pathlib.Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
labels = {n: int(a, 16) for a, n in re.findall(r'al ([0-9A-F]+) \.(\w+)', pathlib.Path('SCOSWAMP/SRC/total.lbl').read_text())}

def decode(path):
    b = path.read_bytes(); assert b[:8] == b'DHRR\x01\x00\x00\x40'; o = bytearray(); i = 8
    while len(o) < 16384:
        t = b[i]; i += 1
        if t & 128: o.extend([b[i]] * ((t & 127) + 3)); i += 1
        else: o.extend(b[i:i + t + 1]); i += t + 1
    assert len(o) == 16384 and i == len(b)
    return bytes(o)

def png_from_ppm(d):
    import zlib, struct
    parts = d.split(maxsplit=4); w, h = int(parts[1]), int(parts[2]); px = d[len(d) - w * h * 3:]
    raw = b''.join(b'\x00' + px[y * w * 3:(y + 1) * w * 3] for y in range(h))
    def chunk(t, b): return struct.pack('>I', len(b)) + t + b + struct.pack('>I', zlib.crc32(t + b) & 0xffffffff)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b''))

checks = []
def ok(label, cond, detail=''):
    print(('PASS ' if cond else 'FAIL ') + label, detail, flush=True)
    checks.append(dict(label=label, ok=bool(cond)))
    if not cond:
        print('\n'.join(p.screen()), flush=True)   # l'ecran au moment de l'echec
        low = p.peek(0x1000, 0x1000)
        print('LOWBSS:', [m.decode() for m in re.findall(rb'[ -~]{6,}', low)][:40], flush=True)
        raise AssertionError(label + ' ' + str(detail))

with tempfile.TemporaryDirectory(prefix='total-validate-') as work:
    disk = pathlib.Path(work) / 'TEST.hdv'; shutil.copyfile(pt.HDV_SRC, disk)
    hdv_sha = hashlib.sha256(disk.read_bytes()).hexdigest()
    p = pt.Pom2(str(disk), port=6527)
    shots = 0
    def shot(name):
        global shots
        import urllib.request
        shots += 1
        ppm = urllib.request.urlopen(p.base + '/screen.ppm').read()
        (out / f'{shots:02d}-{name}.ppm').write_bytes(ppm)
        (out / f'{shots:02d}-{name}.png').write_bytes(png_from_ppm(ppm))
        (out / f'{shots:02d}-{name}.txt').write_text('\n'.join(p.screen()) + '\n')
    def value(name, n=2): return int.from_bytes(p.peek(labels['_total_' + name], n), 'little')
    def wait(test, what='condition', seconds=10):
        deadline = time.time() + seconds
        while time.time() < deadline:
            if test(): return
            time.sleep(.02)
        print('\n'.join(p.screen()), 'ops', value('ops'), 'errors', value('errors'), flush=True)
        raise AssertionError('Timed out: ' + what)
    def screen40():
        m = p.peek(0x400, 1024)
        return [''.join(p._cell(m[0x80 * (r % 8) + 0x28 * (r // 8) + c]) for c in range(40)) for r in range(24)]
    def rows(): return p.screen()
    def has(needle): return any(needle in r for r in rows())
    def wait_text(needle, seconds=10): wait(lambda: has(needle), needle, seconds); return p.stable()
    def key(k):
        p.raw(k); time.sleep(.15)
    def cursor_row(panel_x):
        # la ligne en inverse du panneau : caracteres < $80 dans la page texte
        main = p.peek(0x400, 1024); aux = p.peek(0x400, 1024, 'aux')
        for r in range(2, 20):
            base = 0x80 * (r % 8) + 0x28 * (r // 8)
            cells = [aux[base + c // 2] if c % 2 == 0 else main[base + c // 2] for c in range(panel_x, panel_x + 38)]
            if all(v < 0x80 for v in cells[:16]): return r
        return None
    def select(panel_x, name):
        # remonter en tete de liste, puis descendre jusqu'a la ligne inverse
        # qui porte le nom : le meme chemin qu'un joueur au clavier
        for _ in range(12): key(b'<')
        for _ in range(180):
            r = cursor_row(panel_x)
            line = rows()[r][panel_x:panel_x + 38] if r is not None else ''
            if line.startswith(name + ' '): return
            key(b'\x0a')
        raise AssertionError('cannot select ' + name)
    try:
        def bitsy_pick(prefix):
            # Bitsy Bye : la liste commence ligne 2, curseur en tete ; on
            # descend jusqu'a l'entree puis Entree. Rend 0 si elle est absente.
            r40 = screen40()
            for i, r in enumerate(r40):
                if r.startswith(prefix):
                    p.raw(b'\x0a' * (i - 2) + b'\r'); time.sleep(.5); return 1
            return 0
        def launch_total():
            wait(lambda: any('BITSY  BYE' in r for r in screen40()), 'Bitsy Bye')
            time.sleep(.5)
            if '/SCOSWAMP' not in screen40()[0]:
                p.raw(b'5'); time.sleep(.5)     # TAB,#:NEW VOL -> slot 5
                ok('Bitsy Bye est revenu sur /SCOSWAMP sans changer de volume', False, screen40()[0])
            # Bitsy Bye rouvre le dossier du programme quitte, ou la racine
            if not bitsy_pick('- TOTAL.SYSTEM'):
                for _ in range(3):
                    if bitsy_pick('  /TOTAL'): break
                    p.raw(b'\x1b'); time.sleep(.5)
                else:
                    raise AssertionError('TOTAL absent de Bitsy Bye:\n' + '\n'.join(screen40()))
                assert bitsy_pick('- TOTAL.SYSTEM'), '\n'.join(screen40())
            wait_text('Type  Aux     Size')
        # l'ecran-titre du jeu : [T] lance TOTAL, [D] lance DIAPO
        p.start(); p.wait_for('LANGUE')
        ok('l ecran-titre propose les utilitaires en bas', has('Utilitaires / Utilities') and has('[D] Diaporama') and has('[T] Apple IIe Total Commander'))
        p.keys('T'); wait_text('Type  Aux     Size', 20)
        ok('[T] de l ecran-titre lance TOTAL', has('/SCOSWAMP/DHGR'))
        key(b'Q'); wait_text('Quit to ProDOS?'); key(b'Y')
        wait(lambda: any('BITSY  BYE' in r for r in screen40()), 'Bitsy Bye'); time.sleep(.5)
        assert bitsy_pick('- SCOSWAMP.SYSTEM'), '\n'.join(screen40())
        p.wait_for('LANGUE'); p.keys('D'); wait_text('RETURN start slideshow', 20)
        ok('[D] de l ecran-titre lance DIAPO', True)
        key(b'\x1b'); wait(lambda: any('BITSY  BYE' in r for r in screen40()), 'Bitsy Bye after DIAPO')
        launch_total()
        shot('panels')
        ok('lancement depuis Bitsy Bye, deux panneaux', has('/SCOSWAMP') and has('/SCOSWAMP/DHGR'))
        ok('barre d aide facon Norton', rows()[23].startswith('TABPanel RETOpen SPCTag  C Copy  V Move  R Ren  D Del  K Mkdir  S Sort  ? Help'))
        def cells(r, a, b):
            main = p.peek(0x400, 1024); aux = p.peek(0x400, 1024, 'aux'); base = 0x80 * (r % 8) + 0x28 * (r // 8)
            return [aux[base + c // 2] if c % 2 == 0 else main[base + c // 2] for c in range(a, b)]
        ok('les touches sont en inverse, les libelles en clair',
           all(v < 0x80 for v in cells(23, 0, 3)) and all(v >= 0x80 for v in cells(23, 3, 8)) and all(v < 0x80 for v in cells(23, 17, 20)))
        ok('espace libre du volume affiche', has('blocks free'))
        key(b']'); p.stable()
        ok('] va au dernier, la ligne d information porte la date', re.search(r'bytes  \d\d/\d\d/\d\d', rows()[21]) is not None)
        key(b'['); p.stable()
        key(b'?'); wait(lambda: value('view', 1) == 4, 'help'); p.stable(); shot('help')
        ok('? affiche l aide', has('APPLE IIe TOTAL COMMANDER') and has('NAVIGATION') and has('FILES') and has('VIEWERS') and rows()[23].startswith('ANYReturn to the panels'))
        key(b' '); wait(lambda: value('view', 1) == 0, 'back from help'); p.stable()
        key(b"'"); wait_text('Jump to name starting with'); key(b'T'); p.stable()
        ok("' T saute a TEXTEN", rows()[cursor_row(0)].startswith('TEXTEN '))
        key(b"'"); key(b'T'); p.stable()
        ok("' T encore : TEXTFR", rows()[cursor_row(0)].startswith('TEXTFR '))
        key(b'['); p.stable()
        # panneau droit : DHGR -> N000 -> N000.RLE
        key(b'\t'); select(40, 'N000'); key(b'\r'); wait_text('/SCOSWAMP/DHGR/N000')
        shot('n000')
        ok('entree dans DHGR/N000', rows()[0][40:].startswith('/SCOSWAMP/DHGR/N000'))
        ok('tri : dossiers puis fichiers', rows()[2][40:].startswith('..') and 'B012.RLE' in rows()[3])
        select(40, 'N000.RLE'); key(b'\r')
        wait(lambda: value('view', 1) == 1, 'image view')
        time.sleep(1.5)
        expected = decode(pathlib.Path('SCOSWAMP/DHGR/N000/N000.RLE.BIN'))
        actual = p.peek(0x2000, 8192, 'aux') + p.peek(0x2000, 8192)
        ok('image N000.RLE decodee AUX+MAIN a l identique', actual == expected)
        shot('image')
        key(b'\x15'); time.sleep(1.5)
        expected = decode(pathlib.Path('SCOSWAMP/DHGR/N000/N001.RLE.BIN'))
        actual = p.peek(0x2000, 8192, 'aux') + p.peek(0x2000, 8192)
        ok('fleche droite : image suivante N001.RLE sans quitter', actual == expected and value('view', 1) == 1)
        key(b'\x08'); time.sleep(1.5)
        expected = decode(pathlib.Path('SCOSWAMP/DHGR/N000/N000.RLE.BIN'))
        actual = p.peek(0x2000, 8192, 'aux') + p.peek(0x2000, 8192)
        ok('fleche gauche : retour a N000.RLE', actual == expected)
        key(b' '); wait(lambda: value('view', 1) == 0, 'back from image'); p.stable()
        ok('retour aux panneaux apres l image, curseur sur N000.RLE', has('Type  Aux     Size') and rows()[cursor_row(40)][40:].startswith('N000.RLE '))
        ok('le format reconnu est annonce', has('N000.RLE: DHGR RLE, 16384 bytes on screen.'))
        # remonter d un niveau : le curseur retombe sur N000
        key(b'\x1b'); wait_text('/SCOSWAMP/DHGR ')
        ok('ESC remonte et reselectionne N000', rows()[cursor_row(40)][40:].startswith('N000 '))
        key(b'S'); p.stable(); ok('S trie par taille', has('Size*'))
        key(b'S'); p.stable(); ok('S trie par type', has('Type*'))
        key(b'S'); p.stable(); ok('S revient au tri par nom', has('Name*'))
        # panneau gauche : TITLE.TXT en texte
        key(b'\t'); select(0, 'TITLE'); key(b'\r'); wait(lambda: value('view', 1) == 2, 'text view'); p.stable()
        shot('text')
        ok('TITLE (TXT) lu page par page', has('page 1'))
        key(b'\x1b'); wait(lambda: value('view', 1) == 0, 'back from text'); p.stable()
        # hexa sur MAP
        select(0, 'MAP'); key(b'H'); wait(lambda: value('view', 1) == 3, 'hex view'); p.stable()
        shot('hex')
        ok('MAP en hexadecimal', has('00000 ') and has('bytes page 1/'))
        key(b'\x1b'); wait(lambda: value('view', 1) == 0, 'back from hex'); p.stable()
        # dossier de travail dans DHGR (panneau droit), puis copie de TITLE dedans
        key(b'\t'); key(b'K'); wait_text('New directory:'); p.keys('BANC'); key(b'\r'); p.stable()
        ok('K cree le dossier BANC', has('BANC ') and value('ops') == 1)
        select(40, 'BANC'); key(b'\r'); wait_text('/SCOSWAMP/DHGR/BANC')
        key(b'\t'); select(0, 'TITLE'); key(b'C'); wait(lambda: value('ops') == 2, 'copy'); p.stable()
        shot('copy')
        ok('C copie TITLE dans BANC, type TXT conserve', any('TITLE' in r[40:] and 'TXT' in r[40:] for r in rows()))
        key(b'C'); wait_text('TITLE exists: Overwrite, Skip, All, None?'); key(b'S'); p.stable()
        ok('recopier demande, S passe le fichier', has('0 files copied, 1 skipped'))
        key(b'C'); wait_text('TITLE exists: Overwrite, Skip, All, None?'); key(b'O'); wait(lambda: value('ops') == 3, 'overwrite'); p.stable()
        ok('O ecrase le fichier', has('1 file copied') and value('ops') == 3)
        # comparaison : les fichiers de /SCOSWAMP absents de BANC, sauf TITLE
        key(b'M'); p.stable()
        ok('M marque les fichiers absents de l autre panneau', has('4 files missing') and not any(r.startswith('TITLE          *') for r in rows()) and any(r.startswith('MAP            *') for r in rows()))
        key(b'*'); p.stable()
        ok('* inverse les marques', any(r.startswith('TITLE          *') for r in rows()) and not any(r.startswith('MAP            *') for r in rows()) and has('1 tagged'))
        key(b'*'); p.stable()
        # marquage : le panneau gauche va dans DHGR/N000, marque B012 et B026, copie vers BANC
        select(0, 'DHGR'); key(b'\r'); wait_text('/SCOSWAMP/DHGR ')
        select(0, 'N000'); key(b'\r'); wait_text('/SCOSWAMP/DHGR/N000')
        select(0, 'B012.RLE'); key(b' '); key(b' '); p.stable()
        ok('Espace marque deux fichiers', has('2 tagged') and any(r.startswith('B012.RLE       *') for r in rows()))
        key(b'C'); wait(lambda: value('ops') == 5, 'copy tagged'); p.stable(); shot('tagged-copy')
        ok('C copie les deux fichiers marques', has('2 files copied') and any('B012.RLE' in r[40:] and 'BIN' in r[40:] for r in rows()) and any('B026.RLE' in r[40:] for r in rows()))
        key(b'\t'); select(40, 'B012.RLE'); key(b' '); key(b' '); key(b'D'); wait_text('Delete 2 tagged files?'); key(b'Y'); p.stable()
        ok('D supprime les deux fichiers marques', has('2 items deleted') and not any('B012.RLE' in r[40:] for r in rows()) and value('ops') == 7)
        key(b'='); p.stable()
        ok('= ouvre le meme dossier dans l autre panneau', rows()[0][:20].startswith('/SCOSWAMP/DHGR/BANC'))
        key(b'\t'); select(0, '..'); key(b'\r'); wait_text('/SCOSWAMP/DHGR '); key(b'\x1b'); wait_text('/SCOSWAMP  ')
        # renommer la copie, puis la supprimer, puis le dossier
        key(b'\t'); select(40, 'TITLE'); key(b'R'); wait_text('New name:'); p.raw(b'\x08' * 5); p.keys('COPIE'); key(b'\r'); p.stable()
        ok('R renomme en COPIE', has('COPIE ') and value('ops') == 8)
        select(40, 'COPIE'); key(b'L'); p.stable()
        ok('L verrouille COPIE', any(r[40:].startswith('COPIE           L') for r in rows()) and has('locked') and value('ops') == 9)
        key(b'D'); wait_text('Delete COPIE?'); key(b'Y'); p.stable()
        ok('un fichier verrouille ne se supprime pas', has('Delete failed') and any(r[40:].startswith('COPIE ') for r in rows()))
        key(b'L'); p.stable()
        ok('L deverrouille', not any(r[40:].startswith('COPIE           L') for r in rows()) and value('ops') == 10)
        key(b'A'); wait_text('File type: $04_'); p.raw(b'\x08\x08'); p.keys('F1'); key(b'\r'); wait_text('Aux type: $0000_'); p.raw(b'\x08\x08\x08\x08'); p.keys('1234'); key(b'\r'); p.stable()
        ok('A change type et auxtype', any(r[40:].startswith('COPIE ') and '$F1 $1234' in r[40:] for r in rows()) and value('ops') == 11)
        select(40, 'COPIE'); key(b'D'); wait_text('Delete COPIE?'); key(b'Y'); p.stable()
        ok('D supprime COPIE', not any('COPIE ' in r[40:] for r in rows()) and value('ops') == 12)
        # copie d'un dossier entier : TOTAL (2 fichiers) dans BANC, compteur de fichiers
        key(b'\t'); select(0, 'TOTAL'); key(b'C'); wait(lambda: value('ops') == 18, 'copy dir', 30); p.stable(); shot('dir-copy')
        ok('C copie le dossier TOTAL entier (mkdir + 5 fichiers, formateur, aide et TOTAL.CFG compris)', has('5 files copied') and any(r[40:].startswith('TOTAL ') and '<DIR>' in r[40:] for r in rows()))
        key(b'\t'); select(40, 'TOTAL'); key(b'\r'); wait_text('/SCOSWAMP/DHGR/BANC/TOTAL')
        code_size = str(os.path.getsize('SCOSWAMP/TOTAL/TOTAL.CODE.BIN')); sys_size = str(os.path.getsize('SCOSWAMP/TOTAL/TOTAL.SYSTEM.SYS'))
        ok('la copie garde noms, types et tailles', any(r[40:].startswith('TOTAL.CODE ') and 'BIN' in r[40:] and code_size in r[40:] for r in rows())
           and any(r[40:].startswith('TOTAL.SYSTEM ') and 'SYS' in r[40:] and sys_size in r[40:] for r in rows()))
        ok('aucun reste de la liste precedente en fin de ligne de fichier',
           all(seg[35:38] == '   ' for r in rows()[2:20] for seg in (r[:38], r[40:78]) if '$' in seg))
        key(b'\x1b'); wait_text('/SCOSWAMP/DHGR/BANC ')
        # un dossier ne se copie pas dans lui-meme
        key(b'\t'); select(0, 'DHGR'); key(b'\r'); wait_text('/SCOSWAMP/DHGR '); select(0, 'BANC'); key(b'C'); p.stable()
        ok('refus de copier un dossier dans lui-meme', has('into itself'))
        # copie a deux niveaux : DHGR/BANC (BANC/TOTAL/2 fichiers) vers /SCOSWAMP
        key(b'\t'); key(b'\x1b'); wait_text('/SCOSWAMP/DHGR '); key(b'\x1b'); wait_text('/SCOSWAMP  ')
        key(b'\t'); select(0, 'BANC'); key(b'C'); wait(lambda: value('ops') == 24, 'copy tree depth 2', 30); p.stable()
        ok('C copie un arbre a deux niveaux (BANC/TOTAL/5 fichiers)', has('5 files copied') and any(r[40:].startswith('BANC ') for r in rows()))
        # suppression recursive a deux niveaux, puis de l'original
        key(b'\t'); select(40, 'BANC'); key(b'D'); wait_text('Delete BANC and everything inside?'); key(b'Y'); p.stable()
        ok('D supprime /SCOSWAMP/BANC et ses deux niveaux', not any(r[40:].startswith('BANC ') for r in rows()) and value('ops') == 31)
        key(b'\t'); select(0, 'BANC'); key(b'D'); wait_text('Delete BANC and everything inside?'); key(b'Y'); p.stable()
        ok('D supprime DHGR/BANC et tout son contenu', not any(r[:38].startswith('BANC ') for r in rows()) and value('ops') == 38)
        key(b'\x1b'); wait_text('/SCOSWAMP  '); key(b'\t')
        ok('une seule erreur ProDOS, celle du fichier verrouille', value('errors') == 1)
        # editeur : un fichier neuf NOTE dans /SCOSWAMP (curseur sur un dossier), deux lignes, sauve, relu, supprime
        select(40, 'TOTAL'); key(b'E'); wait_text('New text file:'); p.keys('NOTE'); key(b'\r'); wait(lambda: value('view', 1) == 5, 'editor'); p.stable()
        ok('E sur un dossier cree un fichier neuf dans l editeur', has('Line 1') and has('Col 1') and has('0/8176 bytes'))
        p.keys('HELLO'); key(b'\r'); p.keys('WORLD'); time.sleep(.5); p.stable()
        ok('la saisie s affiche, deux lignes, texte modifie', rows()[0].startswith('HELLO') and rows()[1].startswith('WORLD') and has('Line 2') and has('11/8176 bytes *'))
        key(b'\x1b'); wait_text('Save'); key(b'X'); wait(lambda: value('view', 1) == 0, 'editor exit'); p.stable()
        ok('X sauve et revient : NOTE, TXT, 11 octets', any(r[40:].startswith('NOTE ') and 'TXT' in r[40:] and '  11 ' in r[40:] for r in rows()) and value('ops') == 39)
        select(40, 'NOTE'); key(b'T'); wait(lambda: value('view', 1) == 2, 'text view'); p.stable()
        ok('le fichier relu contient les deux lignes', rows()[0].startswith('HELLO') and rows()[1].startswith('WORLD'))
        key(b'\x1b'); wait(lambda: value('view', 1) == 0, 'back'); p.stable()
        key(b'D'); wait_text('Delete NOTE?'); key(b'Y'); p.stable()
        ok('NOTE supprime', not any(r[40:].startswith('NOTE ') for r in rows()))
        # musique Mockingboard : Entree sur MUSIC/WELCOME.MB joue en boucle, P met en pause
        select(40, 'MUSIC'); key(b'\r'); wait_text('/SCOSWAMP/MUSIC'); select(40, 'WELCOME.MB'); key(b'\r'); time.sleep(1.5); p.stable()
        ok('Entree sur un .MB le joue sur la Mockingboard', has('Playing WELCOME.MB once on the Mockingboard in slot') and value('playing', 1) == 1)
        mb = pathlib.Path('SCOSWAMP/MUSIC/WELCOME.MB.BIN').read_bytes()
        got = p.peek(0x1000, len(mb), 'aux')
        ok('le flux MB1 est monte en AUX $1000, drapeau de boucle a zero (octet 5)', got[:5] == mb[:5] and got[5] == 0 and got[6:] == mb[6:])
        key(b'P'); p.stable()
        ok('P met la musique en pause', has('Music paused') and value('playing', 1) == 2)
        key(b'P'); p.stable()
        ok('P la reprend', has('Music resumed') and value('playing', 1) == 1)
        key(b'\x1b'); wait_text('/SCOSWAMP  ')
        # liste des volumes
        key(b'/'); p.stable(); shot('volumes')
        ok('/ liste les volumes avec slot et espace libre', has('[Volumes]') and any(r[40:].startswith('/SCOSWAMP ') and 'S5,D1' in r[40:] and 'free' in r[40:] for r in rows()))
        # le panneau droit sur DIAPO : TOTAL.CFG doit le restaurer au relancement
        select(40, '/SCOSWAMP'); key(b'\r'); wait_text('/SCOSWAMP  '); select(40, 'DIAPO'); key(b'\r'); wait_text('/SCOSWAMP/DIAPO')
        # quitter
        key(b'Q'); wait_text('Quit to ProDOS?'); key(b'Y')
        wait(lambda: any('BITSY  BYE' in r for r in screen40()), 'Bitsy Bye back')
        ok('Q rend la main a Bitsy Bye', True)
        # relancer TOTAL, puis lancer DIAPO.SYSTEM depuis TOTAL (X)
        launch_total()
        ok('TOTAL.CFG restaure le panneau droit sur /SCOSWAMP/DIAPO', rows()[0][40:].startswith('/SCOSWAMP/DIAPO'))
        ok('TOTAL.CFG restaure le panneau actif (droit)', cursor_row(40) is not None)
        key(b'\t')
        select(0, 'DIAPO'); key(b'\r'); wait_text('/SCOSWAMP/DIAPO ')
        select(0, 'DIAPO.SYSTEM'); key(b'X'); wait_text('Run DIAPO.SYSTEM?'); key(b'Y')
        wait_text('RETURN start slideshow', 20)
        ok('X lance DIAPO.SYSTEM (exec ProDOS)', True)
        shot('diapo-from-total')
        key(b'\x1b'); wait(lambda: any('BITSY  BYE' in r for r in screen40()), 'Bitsy Bye after DIAPO')
        ok('DIAPO rend la main a Bitsy Bye', True)
        result = dict(hdv_sha256=hdv_sha, headless=pt.POM2, checks=checks)
        (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
        print('PASS', len(checks), 'controles', flush=True)
    finally:
        p.stop(); (out / 'pom2.log.gz').write_bytes(gzip.compress((pathlib.Path(work) / 'pom2.log').read_bytes(), mtime=0))
