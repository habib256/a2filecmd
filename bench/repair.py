#!/usr/bin/env python3
"""Banc de la surcouche REPAIR (src/plugins/repair.c), chantier WRITE.

    make build-6502/repair.PLG ARCH=6502 && python3 bench/repair.py
    A2FC_IMG=A2FILECMD-full python3 bench/repair.py      # la 65C02

Increments 9 a 15 de docs/FIXIT.md section 8. Le banc amorce un disque dur
jetable portant le REPAIR de CETTE construction, avec une disquette jetable
en lecteur 2 (`tools/mkvolume.py`, jamais un disque personnel), et fait
neuf passages, chacun sur sa propre disquette.

Passage 1, une disquette dont SEULE la bitmap est fausse
(`bitmap_lost` + `bitmap_reserved_free` + `bitmap_tail_set` : un bloc que
personne ne reclame, et deux fautes qui ne tiennent qu'a la bitmap) :

1. l'ecran de plan nomme chaque controle de l'oracle avec son compteur, et
   la ligne « Plan: N corrections over M blocks. Nothing written yet. » ;
2. `F` pose la question, le mot FIX est tape en entier ;
3. le verdict dit « rescan clean: repaired » ;
4. sur l'hote, a l'arret de POM2, la disquette est saine pour
   `tools/prodos_check.py` et les SEULS octets qui ont bouge sont ceux du
   bloc de bitmap.

Passage 2, une disquette cassee dans le REPERTOIRE et dans la bitmap
(`file_count_high` + `dir_eof_wrong` + `parent_wrong` + `bitmap_free_used`) :
les quatre controles sont au plan, `F` puis FIX les applique, le verdict
dit « repaired », et sur l'hote la disquette est saine et les seuls blocs
qui ont bouge sont ceux que l'oracle nomme.

Passage 3, la meme disquette avec un bloc partage (`crosslink`) : le plan
refuse de liberer, le message le dit, et la disquette est octet pour octet
celle d'avant l'amorcage.

Passage 4, la disquette du passage 1 de nouveau cassee : Echap a la
question FIX, et la disquette ne bouge pas d'un octet.

Passages 5 a 9, UN pointeur abime par disquette (les montages `DAMAGE` de
`tools/test_repair.py`, les trois defauts du 6 octobre 2026 et deux de leurs
voisins) : la cle d'un sous-dossier qui designe le bloc d'index d'un de ses
fichiers, le chainage du repertoire de volume qui mene a un bloc libre, une
entree dont le quartet de stockage est a zero, la cle d'un fichier d'un bloc
deplacee sur un bloc libre, un sous-dossier dont le quartet de stockage dit
« fichier ». Chacun rendait « rescan clean: repaired » apres avoir libere
les blocs du fichier ; chacun est maintenant refuse avant le plan, par le
message que le montage attend, et la disquette est octet pour octet celle
d'avant l'amorcage. C'est le code de cc65 qui est juge ici, sur les deux
processeurs : le harnais hote le compile avec clang.

POM2 ne reecrit jamais le .hdv d'amorcage dans son fichier : la preuve sur
l'hote se fait sur la disquette du lecteur 2, ecrite a l'arret de
l'emulateur.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from xplug import boot_hd, menu_run, ok_all, wait_note, RET, ESC
from pom2 import ROOT
import corrupt_prodos
import prodos_check
import test_repair

PORT = 6850
BLOCKS = 280
VOLUME = 'FIXVOL'
# Trois casses de la bitmap et rien d'autre : le plan les corrige toutes
# les trois, en une page ecrite une fois. Un bloc perdu n'est rendu que si
# l'arbre n'a rien d'autre a se reprocher et ne reclame aucun bloc libre :
# il voyage donc avec les deux fautes qui ne tiennent qu'a la bitmap.
BITMAP = ['bitmap_lost', 'bitmap_reserved_free', 'bitmap_tail_set']
# Le repertoire et la bitmap ensemble : un compteur de fichiers, l'eof d'un
# sous-dossier, l'en-tete d'un sous-dossier qui nomme le mauvais rang chez
# son parent, et un bloc de fichier que la bitmap dit libre.
MIXED = ['file_count_high', 'dir_eof_wrong', 'parent_wrong', 'bitmap_free_used']
# Les lignes de src/plugins/repair.c que l'ecran doit montrer.
PLAN = 'Plan: %u corrections over %u blocks. Nothing written yet.'
KEYS = 'F fix  ESC back'
ASK = 'Type FIX to confirm'
XLINK = 'Cross-linked blocks: copy both files to another volume before any repair.'
DONE = 'Applied %u of %u blocks; rescan clean: repaired.'
NOTHING = 'Nothing written.'
KEPT = 'Lost blocks may hold a damaged file: nothing written. See FIXIT.'
NOPLAN = 'Scan incomplete: no repair.'
# Un pointeur abime par disquette, et le refus attendu (tools/test_repair.py
# tient les memes sur l'hote, avec l'etat d'avant le correctif).
POINTERS = (('sub_key_at_a_file_block', NOPLAN),
            ('root_link_to_a_free_block', NOPLAN),
            ('entry_looks_deleted', KEPT),
            ('seedling_key_moved', KEPT),
            ('directory_reads_as_a_seedling', KEPT))


def make_po(tmp, name):
    """Un volume ProDOS jetable : des fichiers, un sous-dossier, 280 blocs."""
    stage = tmp / ('stage-' + name)
    stage.mkdir()
    (stage / 'A.TXT').write_bytes(b'alpha\r' * 40)
    (stage / 'B.TXT').write_bytes(b'beta\r' * 400)
    # Les noms que les montages DAMAGE de tools/test_repair.py visent, et
    # assez d'entrees pour que le repertoire de volume deborde du bloc 2 :
    # un chainage abime y cache alors de vrais fichiers.
    (stage / 'TREE.BIN').write_bytes(bytes(range(256)) * 9)
    for i in range(10):
        (stage / ('ZZ%d.TXT' % i)).write_bytes(b'tail %d\r' % i * 30)
    (stage / 'SUB').mkdir()
    (stage / 'SUB' / 'NEST.TXT').write_bytes(b'nested\r' * 10)
    (stage / 'SUB' / 'NEST2.TXT').write_bytes(b'deeper\r' * 100)
    po = tmp / (name + '.po')
    subprocess.run([sys.executable, str(ROOT / 'tools/mkvolume.py'), str(stage), str(po),
                    '--volume', VOLUME, '--blocks', str(BLOCKS)],
                   check=True, capture_output=True)
    data = bytearray(po.read_bytes())
    corrupt_prodos.add_extended_file(data, 'EXT')
    po.write_bytes(bytes(data))
    return po


def break_it(tmp, clean, names, stem):
    """La disquette cassee, et les constats attendus.

    Les deux moities de l'oracle hote se recoupent ici, avant que POM2
    demarre (docs/FIXIT.md section 7) : `corrupt_prodos.py` declare par
    construction ce que chaque casse doit produire, `prodos_check.py` le
    relit sur l'image. Un desaccord condamne le montage, pas la surcouche.
    """
    data = bytearray(clean.read_bytes())
    declared = corrupt_prodos.apply(data, names)
    po = tmp / (stem + '.po')
    po.write_bytes(bytes(data))
    result = prodos_check.check(bytes(data))
    assert (prodos_check.to_json(declared.findings)
            == prodos_check.to_json(result.findings)), (
        'corrupt_prodos.py et prodos_check.py ne disent pas la meme chose')
    assert declared.complete == result.complete, (declared.complete, result.complete)
    expect = {}
    for f in result.findings:
        expect[f.id] = expect.get(f.id, 0) + 1
    return po, expect


def bitmap_blocks(data):
    """Les blocs de la bitmap : les seuls qu'une reparation peut reecrire."""
    head = data[2 * 512 + 4:2 * 512 + 4 + 39]
    first = int.from_bytes(head[0x23:0x25], 'little')
    total = int.from_bytes(head[0x25:0x27], 'little')
    return set(range(first, first + (total + 4095) // 4096))


def screen(s):
    return '\n'.join(s.rows())


def line_of(rows, id):
    """La ligne de plan de `id` : « ID compteur »."""
    for row in rows:
        if row.strip().startswith(id + ' '):
            return row.split()
    return None


def changed_blocks(before, after):
    return {i // 512 for i, (a, b) in enumerate(zip(after, before)) if a != b}


def wait_plan(s, p):
    s.wait(lambda: s.has(KEYS), 'l ecran de plan de REPAIR', 120)
    p.stable()


def session(tmp, po, checks):
    """Un amorcage avec `po` en lecteur 2 ; `checks(p, s, back, list)` fait le reste."""
    home = tmp / ('boot-' + po.stem)
    home.mkdir()
    with boot_hd(home, {}, port=PORT, plugins=['repair'], floppy2=po) as (p, s):
        stack = p.peek(0x80, 2)
        floor = s.sym['__HIMEM__'] - s.sym['__STACKSIZE__']
        p.poke(floor, b'\xa5' * 8)
        p.poke(s.sym['_a2fc_ops'], b'\x2a\x00')

        def back(label):
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


def repaired(tmp, po, expect, writes, label='apres la reparation'):
    """Le plan, la question, le mot FIX, le verdict.

    `writes` est le nombre de blocs que le plan annonce ecrire : une page de
    bitmap plus une ecriture par correction de repertoire (docs/FIXIT.md
    section 5, il n'y a pas de table de rustines).
    """
    def checks(p, s, back, volume_list):
        volume_list()
        s.select('/' + VOLUME)
        menu_run(s, p, 'REPAIR')
        wait_plan(s, p)
        rows = s.rows()
        text = '\n'.join(rows)
        s.ok('le titre nomme le volume', 'REPAIR /%s' % VOLUME in text, rows[0])
        total = 0
        for id, count in sorted(expect.items()):
            got = line_of(rows, id)
            s.ok('%s est au plan' % id, got is not None, text)
            if got:
                total += count
                s.ok('%s : le compteur de l oracle' % id, got[1] == str(count), got)
        s.ok('la ligne de plan compte les corrections et les blocs',
             PLAN % (total, writes) in text, text)
        s.ok('aucune touche que REPAIR n a pas',
             KEYS in text and not any(k in text for k in ('R rescan', 'P plan')),
             text)
        s.ok('rien n est ecrit avant la question', 'Nothing written yet.' in text)

        # F, puis le mot en entier
        s.key(b'F')
        s.wait(lambda: ASK in s.rows()[22], 'la question FIX', 60)
        p.stable()
        s.type('FIX')
        s.key(RET)
        note = wait_note(s, p)
        s.ok('le verdict dit que le volume est repare',
             note == DONE % (writes, writes), note)
        back(label)
    return session(tmp, po, checks)


def refused(tmp, po, label, escape, expect=XLINK):
    """Un plan refuse : le bloc partage, un pointeur abime, ou Echap a la
    question. `expect` est le message du refus."""
    def checks(p, s, back, volume_list):
        volume_list()
        s.select('/' + VOLUME)
        menu_run(s, p, 'REPAIR')
        if escape:
            wait_plan(s, p)
            s.key(b'F')
            s.wait(lambda: ASK in s.rows()[22], 'la question FIX', 60)
            p.stable()
            s.key(ESC)
            note = wait_note(s, p)
            s.ok(label + ' : le verdict dit que rien n a ete ecrit',
                 note == NOTHING, note)
        else:
            # Aucune touche n'est envoyee : un ecran de plan attendrait la
            # sienne et la note n'arriverait jamais (wait_note leve alors).
            note = wait_note(s, p)
            s.ok(label + ' : le refus et son motif, sans plan ni question',
                 note == expect, note)
        back(label)
    return session(tmp, po, checks)


def main():
    with tempfile.TemporaryDirectory(prefix='a2fc-repair-') as tmp:
        tmp = Path(tmp)
        po = make_po(tmp, VOLUME)
        assert prodos_check.check(po.read_bytes()).findings == [], \
            'le volume de depart doit etre sain'

        bad, expect = break_it(tmp, po, BITMAP, 'BITMAP')
        bad_before = bad.read_bytes()
        assert set(expect) == {'BM_LOST', 'BM_RESERVED', 'BM_TAIL'}, expect
        mixed, mexpect = break_it(tmp, po, MIXED, 'MIXED')
        mixed_before = mixed.read_bytes()
        assert set(mexpect) == {'FILE_COUNT', 'DIR_EOF', 'DIR_PARENT',
                                'BM_USED_FREE'}, mexpect
        # les blocs que l'oracle nomme : les trois corrections de repertoire
        # et l'unique page de bitmap
        mblocks = {f.block for f in prodos_check.check(mixed_before).findings
                   if not f.id.startswith('BM_')} | bitmap_blocks(mixed_before)
        # un pointeur abime par disquette : l'oracle y voit des blocs perdus
        # dans une passe complete, la forme que REPAIR liberait
        pointers = []
        for name, note in POINTERS:
            data, stake = test_repair.damaged(po.read_bytes(), name)
            result = prodos_check.check(data)
            assert result.complete and any(f.id == 'BM_LOST' for f in result.findings), name
            target = tmp / (name.upper()[:12] + '.po')
            target.write_bytes(data)
            pointers.append((name, note, target, data))
        shared, _ = break_it(tmp, po, ['crosslink'], 'SHARED')
        shared_before = shared.read_bytes()
        keep, _ = break_it(tmp, po, BITMAP, 'KEEP')
        keep_before = keep.read_bytes()

        s = repaired(tmp, bad, expect, 1)
        after = bad.read_bytes()
        s.ok('la disquette est saine pour tools/prodos_check.py',
             prodos_check.check(after).findings == [],
             prodos_check.check(after).findings[:3])
        moved = changed_blocks(bad_before, after)
        s.ok('seul le bloc de bitmap a bouge',
             moved and moved <= bitmap_blocks(bad_before), sorted(moved)[:4])

        # repertoire ET bitmap : trois ecritures de repertoire puis la page
        s1 = repaired(tmp, mixed, mexpect, 4, 'apres la reparation du repertoire')
        after = mixed.read_bytes()
        s1.ok('la disquette cassee dans le repertoire est saine',
              prodos_check.check(after).findings == [],
              prodos_check.check(after).findings[:3])
        moved = changed_blocks(mixed_before, after)
        s1.ok('seuls les blocs que l oracle nomme ont bouge',
              moved and moved <= mblocks, (sorted(moved), sorted(mblocks)))

        s2 = refused(tmp, shared, 'bloc partage', escape=False)
        after = shared.read_bytes()
        s2.ok('la disquette a blocs partages est intacte, octet pour octet',
              after == shared_before,
              [i for i, (a, b) in enumerate(zip(after, shared_before)) if a != b][:4])

        s3 = refused(tmp, keep, 'Echap a la question', escape=True)
        after = keep.read_bytes()
        s3.ok('Echap a la question ne change pas un octet',
              after == keep_before,
              [i for i, (a, b) in enumerate(zip(after, keep_before)) if a != b][:4])

        others = [s1, s2, s3]
        for name, note, target, data in pointers:
            sp = refused(tmp, target, name, escape=False, expect=note)
            after = target.read_bytes()
            sp.ok(name + ' : la disquette est intacte, octet pour octet',
                  after == data,
                  [i for i, (a, b) in enumerate(zip(after, data)) if a != b][:4])
            others.append(sp)

        for other in others:
            s.checks.extend(other.checks)
    return ok_all(s, 'repair')


if __name__ == '__main__':
    sys.exit(main())
