#!/usr/bin/env python3
"""Banc de la surcouche FIXIT (src/plugins/fixit.c), chantier Read.

    make build-6502/fixit.PLG ARCH=6502 && python3 bench/fixit.py
    A2FC_IMG=A2FILECMD-full python3 bench/fixit.py      # la 65C02

Increments 1 a 8 de docs/FIXIT.md section 8 : FIXIT ne lit que. Le banc
amorce un disque dur jetable portant le FIXIT de CETTE construction, avec
une disquette jetable en lecteur 2 (`tools/mkvolume.py`, jamais un disque
personnel), et fait deux passages.

Passage 1, disquette saine :

1. FIXIT sur le volume sain de la liste des volumes : l'ecran
   « FIXIT /VOL - READ ONLY » apparait, aucun constat n'est affiche et la
   ligne de resume compte zero constat ;
2. la ligne de resume n'offre que les touches du chantier Read : `R` et
   Echap / Entree. Ni `P`, ni `F`, ni `E` : ces touches n'existent pas ;
3. Echap rend la main aux panneaux, le resident et la pile C sont intacts ;
4. FIXIT depuis un dossier du meme volume : meme verdict, l'unite venant
   d'ON_LINE et non de la selection ;
5. une autre surcouche tourne encore apres FIXIT ;
6. sur l'hote, a l'arret de POM2, la disquette est octet pour octet celle
   d'avant l'amorcage, et tools/prodos_check.py la dit toujours saine.

Passage 2, la meme disquette cassee sur l'hote par
`tools/corrupt_prodos.py` en dix-sept endroits (CORRUPTIONS), un par
identifiant de constat, ce qui est le plus qu'une disquette puisse porter
sans que le parcours s'arrete : dix-sept lignes plus celle du debordement
de la table d'echantillons remplissent une page de dix-huit lignes.

1. chaque identifiant de l'oracle `tools/prodos_check.py` est nomme, avec
   son compteur ; les lignes qui portent un bloc portent le premier bloc de
   l'oracle, et son premier rang quand le constat en a un ;
2. la table d'echantillons ne garde que seize constats : au moins un des
   dix-sept controles s'affiche donc avec son seul compteur, sous la ligne
   « more findings than the table holds » ;
3. la page est pleine : « Key: next / ESC: back » attend une touche, et la
   suite tient sur la page suivante ;
4. `R` relance le parcours sur la meme disquette et rend exactement les
   memes lignes : rien ne s'accumule d'un passage a l'autre ;
5. Echap rend la main, le verdict compte les constats et dit que rien n'a
   ete ecrit ;
6. la disquette cassee est elle aussi relue octet pour octet : un
   diagnostic n'ecrit rien, pas meme sur un volume deja casse.

POM2 ne reecrit jamais le .hdv d'amorcage dans son fichier : la preuve sur
l'hote se fait sur la disquette du lecteur 2, ecrite a l'arret de l'emulateur.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from xplug import boot_hd, menu_run, ok_all, RET, ESC
from pom2 import ROOT
import corrupt_prodos
import prodos_check

PORT = 6849
BLOCKS = 280
VOLUME = 'FIXVOL'
# Dix-sept casses qui ne se marchent pas dessus et dont aucune n'arrete le
# parcours : une page pleine de constats. La liste vit dans
# tools/corrupt_prodos.py, ou tools/test_prodos_check.py la tient a ce
# qu'elle declare ; le banc n'en garde pas une copie qui pourrait deriver.
CORRUPTIONS = list(corrupt_prodos.MANY)

# Les identifiants que FIXIT affiche en cas de constat : aucun ne doit
# apparaitre sur un volume sain.
IDS = tuple(prodos_check.CHECKS)
# Les lignes de src/plugins/fixit.c que l'ecran doit montrer.
MORE = 'Key: next / ESC: back'
OVER = 'more findings than the table holds'
SUMMARY = '%u findings.  R rescan  ESC/RETURN back'
LINES_PER_PAGE = 18


def make_po(tmp, name):
    """Un volume ProDOS jetable : des fichiers, un sous-dossier, 280 blocs.

    Plus un fichier etendu, que mkvolume.py ne sait pas ecrire et dont la
    corruption `fork_bad` a besoin ; le volume reste sain."""
    stage = tmp / ('stage-' + name)
    stage.mkdir()
    (stage / 'A.TXT').write_bytes(b'alpha\r' * 40)
    (stage / 'B.TXT').write_bytes(b'beta\r' * 400)
    (stage / 'SUB').mkdir()
    (stage / 'SUB' / 'NEST.TXT').write_bytes(b'nested\r' * 10)
    po = tmp / (name + '.po')
    subprocess.run([sys.executable, str(ROOT / 'tools/mkvolume.py'), str(stage), str(po),
                    '--volume', VOLUME, '--blocks', str(BLOCKS)],
                   check=True, capture_output=True)
    data = bytearray(po.read_bytes())
    corrupt_prodos.add_extended_file(data, 'EXT')
    po.write_bytes(bytes(data))
    return po


def make_broken(tmp, clean):
    """La meme disquette, cassee sur l'hote, et les constats attendus.

    Les deux moities de l'oracle hote se recoupent ici, avant que POM2
    demarre (docs/FIXIT.md section 7, point 1) : `corrupt_prodos.py` declare
    par construction ce que chaque casse doit produire, `prodos_check.py` le
    relit sur l'image. Un desaccord condamne le montage, pas la surcouche :
    le banc s'arrete tout de suite plutot que d'accuser FIXIT.
    """
    data = bytearray(clean.read_bytes())
    declared = corrupt_prodos.apply(data, CORRUPTIONS)
    po = tmp / 'BROKEN.po'
    po.write_bytes(bytes(data))
    result = prodos_check.check(bytes(data))
    assert (prodos_check.to_json(declared.findings)
            == prodos_check.to_json(result.findings)), (
        'corrupt_prodos.py et prodos_check.py ne disent pas la meme chose')
    assert declared.complete == result.complete, (declared.complete, result.complete)
    expect = {}
    for f in result.findings:
        expect.setdefault(f.id, [0, f.block, f.slot])
        expect[f.id][0] += 1
    return po, expect, len(result.findings)


def screen(s):
    return '\n'.join(s.rows())


def run_fixit(s, p, mark='ESC/RETURN back'):
    """Lance FIXIT et attend l'ecran de constats, pas celui du parcours.

    `mark` est ce que la page attendue porte et que l'ecran d'avant n'a
    pas : la ligne de resume quand les constats tiennent sur une page, la
    demande de touche quand la page est pleine."""
    menu_run(s, p, 'FIXIT')
    wait_findings(s, p, mark)


def wait_findings(s, p, mark, gone=None):
    """Attend `mark`, et l'absence de `gone` : sans quoi, relancer le
    parcours par `R` depuis la derniere page rendrait la main aussitot, sur
    l'ecran d'avant, et le banc comparerait une page a elle-meme."""
    s.wait(lambda: s.has(mark) and not (gone and s.has(gone)),
           "l'ecran de constats de FIXIT", 120)
    p.stable()


def wait_note(s, p):
    """La ligne 22 une fois le verdict ecrit ; rend son texte.

    `api->note` ecrit apres que le resident a repose la barre de touches :
    lire la ligne 22 des qu'« ! More » revient la trouve encore vide un
    passage sur deux. On attend qu'elle porte quelque chose, et c'est le
    controle qui dit quoi."""
    s.wait(lambda: s.rows()[22].strip() != '', 'le verdict de FIXIT', 30)
    p.stable()
    return s.rows()[22].strip()


def line_of(rows, id):
    """La ligne de constat de `id` : « ID  compteur  block N [slot S] »."""
    for row in rows:
        if row.strip().startswith(id + ' '):
            return row.split()
    return None


def session(tmp, po, checks):
    """Un amorcage avec `po` en lecteur 2 ; `checks(p, s, back)` fait le reste.

    Chaque passage se monte son propre disque dur, dans son propre dossier :
    `stage_hd` refuse d'ecraser celui du passage precedent."""
    home = tmp / ('boot-' + po.stem)
    home.mkdir()
    with boot_hd(home, {}, port=PORT, plugins=['fixit'], floppy2=po) as (p, s):
        stack = p.peek(0x80, 2)
        floor = s.sym['__HIMEM__'] - s.sym['__STACKSIZE__']
        p.poke(floor, b'\xa5' * 8)
        p.poke(s.sym['_a2fc_ops'], b'\x2a\x00')

        def back(label):
            s.key(ESC)
            s.wait(lambda: s.has('! More'), 'retour aux panneaux', 60)
            p.stable()
            s.ok(label + ' : resident et pile C preserves',
                 s.value('ops') == 42 and p.peek(0x80, 2) == stack)
            s.ok(label + ' : budget de pile respecte', p.peek(floor, 8) == b'\xa5' * 8)

        def volume_list():
            s.key(b'/')
            s.wait(lambda: s.rows()[0].startswith('[Volumes]'), 'la liste des volumes')
            p.stable()

        checks(p, s, back, volume_list)
    return s


def healthy(tmp, po):
    def checks(p, s, back, volume_list):
        # 1. depuis la liste des volumes
        volume_list()
        s.select('/' + VOLUME)
        run_fixit(s, p)
        text = screen(s)
        s.ok('le titre nomme le volume et le mode lecture seule',
             'FIXIT /%s - READ ONLY' % VOLUME in text, s.rows()[0])
        s.ok('aucun constat sur un volume sain',
             not any(line_of(s.rows(), i) for i in IDS), text)
        s.ok('la ligne de resume compte zero constat', SUMMARY % 0 in text, text)
        s.ok('aucune touche du chantier WRITE n est proposee',
             not any(k in text for k in ('P plan', 'F fix', 'E export')), text)
        back('liste des volumes')
        note = wait_note(s, p)
        s.ok('le verdict, sur la ligne de message, annonce un volume coherent',
             note.startswith('This volume is consistent'), note)

        # 2. depuis un dossier du meme volume : l'unite vient d'ON_LINE
        volume_list()
        s.select('/' + VOLUME)
        s.key(RET)
        s.wait(lambda: s.rows()[0][:len(VOLUME) + 2] == '/' + VOLUME + ' ',
               'la racine du volume jetable')
        p.stable()
        s.select('SUB')
        s.key(RET)
        s.wait(lambda: s.has('NEST'), 'le sous-dossier')
        p.stable()
        run_fixit(s, p)
        text = screen(s)
        s.ok('depuis un dossier : meme volume, meme verdict',
             'FIXIT /%s - READ ONLY' % VOLUME in text
             and not any(line_of(s.rows(), i) for i in IDS), text)
        back('depuis un dossier')

        # 3. une autre surcouche tourne encore apres FIXIT
        menu_run(s, p, 'HELP')
        s.wait(lambda: s.has('A2 FILE CMD'), 'l aide apres FIXIT', 60)
        # L'attente ci-dessus prouve deja qu'HELP s'affiche : ce qu'elle ne
        # dit pas, c'est que FIXIT a bien rendu la fenetre $1B00-$3F9D.
        s.ok('une autre surcouche prend la fenetre apres FIXIT',
             not s.has('READ ONLY'), screen(s))
        s.key(ESC)
        p.stable()
    return session(tmp, po, checks)


def broken(tmp, po, expect, total):
    def pages(p, s, label):
        """Les deux pages de constats ; rend leurs lignes bout a bout."""
        first = s.rows()
        s.ok(label + ' : la page est pleine et attend une touche',
             any(r.strip() == MORE for r in first), '\n'.join(first))
        body = [r for r in first[2:2 + LINES_PER_PAGE] if r.strip()]
        s.ok(label + ' : dix-huit lignes sur la page',
             len(body) == LINES_PER_PAGE, body)
        s.ok(label + ' : la table d echantillons a deborde',
             any(r.strip() == OVER for r in body), body)
        s.key(b' ')
        s.wait(lambda: s.has('ESC/RETURN back'), 'la page suivante', 60)
        p.stable()
        second = s.rows()
        s.ok(label + ' : la ligne de resume compte les constats de l oracle',
             SUMMARY % total in '\n'.join(second), '\n'.join(second))
        return first + second

    def checks(p, s, back, volume_list):
        volume_list()
        s.select('/' + VOLUME)
        run_fixit(s, p, MORE)
        rows = pages(p, s, 'volume casse')
        text = '\n'.join(rows)
        blocks = 0
        for id, (count, block, slot) in sorted(expect.items()):
            got = line_of(rows, id)
            s.ok('%s est signale' % id, got is not None, text)
            if not got:
                continue
            s.ok('%s : le compteur de l oracle' % id, got[1] == str(count), got)
            if len(got) > 2:
                blocks += 1
                s.ok('%s : le premier bloc de l oracle' % id,
                     got[2] == 'block' and got[3] == str(block), got)
                if slot is not None:
                    s.ok('%s : le premier rang de l oracle' % id,
                         got[4:6] == ['slot', str(slot)], got)
        s.ok('la table de seize echantillons nomme un bloc, pas plus',
             15 <= blocks <= 16 and blocks < len(expect), (blocks, len(expect)))
        s.ok('aucun constat que l oracle ne voit pas',
             not any(line_of(rows, i) for i in IDS if i not in expect), text)

        # R : le meme parcours, refait en entier, rend les memes lignes
        s.key(b'R')
        wait_findings(s, p, MORE, gone='ESC/RETURN back')
        again = pages(p, s, 'apres R')
        s.ok('R relance le parcours et rend exactement les memes constats',
             [r.rstrip() for r in again] == [r.rstrip() for r in rows],
             '\n'.join(again))

        back('volume corrompu')
        note = wait_note(s, p)
        s.ok('le verdict compte les constats et dit que rien n a ete ecrit',
             note.startswith('%u findings, nothing written' % total), note)
    return session(tmp, po, checks)


def main():
    with tempfile.TemporaryDirectory(prefix='a2fc-fixit-') as tmp:
        tmp = Path(tmp)
        po = make_po(tmp, VOLUME)
        before = po.read_bytes()
        assert prodos_check.check(before).findings == [], 'le volume de depart doit etre sain'
        bad, expect, total = make_broken(tmp, po)
        bad_before = bad.read_bytes()
        # Une page de dix-huit lignes : un identifiant par ligne, plus celle
        # du debordement, qui n'existe que si les constats depassent les
        # seize echantillons. Compte, jamais recopie.
        assert len(expect) == 17, sorted(expect)
        assert len(expect) + 1 == LINES_PER_PAGE, (len(expect), LINES_PER_PAGE)
        assert total > 16, (total, 'la table de seize echantillons doit deborder')

        s = healthy(tmp, po)
        after = po.read_bytes()
        s.ok('la disquette saine est intacte, octet pour octet',
             after == before,
             [i for i, (a, b) in enumerate(zip(after, before)) if a != b][:4])
        s.ok('elle est toujours saine pour tools/prodos_check.py',
             prodos_check.check(after).findings == [],
             prodos_check.check(after).findings[:3])

        s2 = broken(tmp, bad, expect, total)
        after = bad.read_bytes()
        s2.ok('la disquette corrompue est intacte, octet pour octet',
              after == bad_before,
              [i for i, (a, b) in enumerate(zip(after, bad_before)) if a != b][:4])
        s.checks.extend(s2.checks)
    return ok_all(s, 'fixit')


if __name__ == '__main__':
    sys.exit(main())
