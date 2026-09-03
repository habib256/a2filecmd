#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""playtest.py -- le banc de traversee automatisee de SCOSWAMP.

Personne n'avait jamais joue ce jeu de bout en bout. Les trois derniers bugs
(Pompatarte qui n'offrait aucune Pierre, les Graines d'Arbre-Epee qui
n'existaient pas dans le catalogue, l'image des Loups montrant leur Maitre)
auraient tous ete attrapes par un banc qui rejoue les missions. Le voici.

Le principe, en trois phrases :

  1. On lance POM2 sur une COPIE de dist/SCOSWAMP.HDV -- l'original n'est
     jamais ouvert en ecriture.
  2. On lit l'ecran texte 80 colonnes directement en RAM ($400-$7FF, page
     principale = colonnes impaires, page auxiliaire = colonnes paires), ce
     que memory_swap.c garantit valable meme en HGR plein ecran.
  3. On se teleporte ou l'on veut en ecrivant dans la BSS du jeu
     (pending_scene, la Feuille d'Aventure, la graine des des), et on frappe
     une touche inerte pour que la boucle principale consomme le tout.

Aucun octet n'est ajoute au binaire livre : le banc n'a besoin d'aucune porte
derobee dans le jeu. Les adresses viennent du lien (SCOSWAMP/SRC/build.lbl,
produit par `ld65 -Ln`) et de la carte memoire, jamais d'une constante ecrite
a la main -- voir la classe Symbols.

Usage :
    python3 SCOSWAMP.MORE/TOOLS/playtest.py            # tout le banc
    python3 SCOSWAMP.MORE/TOOLS/playtest.py --list
    python3 SCOSWAMP.MORE/TOOLS/playtest.py --only combat_degats --keep
    make -C SCOSWAMP/SRC playtest

Documentation de conception : DOCS/AUTOMATISATION.md.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

# ── Racines ────────────────────────────────────────────────────────────────
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))          # le depot
SRCDIR = os.path.join(ROOT, "SCOSWAMP", "SRC")
HDV_SRC = os.path.join(ROOT, "dist", "SCOSWAMP.HDV")
POM2 = os.environ.get("POM2", "/Users/gistair/src/pom2/build/POM2")

# 6503..6506, 6510 sont pris (POM2 par defaut, et les bancs voisins) : on
# commence a 6520.
DEFAULT_PORT = 6520


# ═══════════════════════════════════════════════════════════════════════════
# 1. Les adresses, lues au lien
# ═══════════════════════════════════════════════════════════════════════════
#
# ld65 -Ln n'ecrit que les symboles GLOBAUX : _app y est, mais `restoring`,
# `state` (dice.c), `visited`/`seen` (rules.c) sont des statiques C, et
# mb_slot/playing (music.s) des labels locaux. Aucun n'est exporte.
#
# On les retrouve sans deviner : la carte memoire donne, pour chaque module et
# chaque segment, l'offset du bloc de ce module dans le segment ; le .s genere
# donne la SUITE ORDONNEE des labels de ce bloc avec leur taille. L'adresse
# d'un symbole est donc segment_start + offset_du_module + somme des tailles
# qui le precedent. Le resultat est verifie contre le .lbl pour les symboles
# qui, eux, y figurent : si les deux methodes divergent, le banc refuse de
# demarrer plutot que de poker au hasard dans le tas.

class SymbolError(RuntimeError):
    pass


class Symbols(object):
    """La table d'adresses du binaire courant."""

    # Les .s a lire, dans l'ordre du Makefile. music.s / sfx.s / hgr_loader.s
    # sont ecrits a la main, les autres sont generes par cc65 : la meme
    # grammaire suffit pour les deux.
    MODULES = ["scoswamp", "paths", "memory_swap", "rules", "dice",
               "messages", "hgr_loader", "sfx", "music"]

    def __init__(self, srcdir=SRCDIR):
        self.srcdir = srcdir
        self.mapfile = os.path.join(srcdir, "build.map")
        self.lblfile = os.path.join(srcdir, "build.lbl")
        for f in (self.mapfile, self.lblfile):
            if not os.path.exists(f):
                raise SymbolError(
                    "%s absent : lancer `make -C SCOSWAMP/SRC all` "
                    "(le .lbl vient de `-Wl -Ln`, voir le Makefile)" % f)
        self.seg = self._segments()
        self.mod = self._modules()
        self.lbl = self._labels()
        self.sym = self._resolve()
        self._check()

    # -- lecture des trois fichiers ----------------------------------------
    def _segments(self):
        out, on = {}, False
        for line in open(self.mapfile):
            if line.startswith("Segment list"):
                on = True
                continue
            if on:
                if line.startswith("Exports list"):
                    break
                m = re.match(r"^(\w+)\s+([0-9A-F]{6})\s+([0-9A-F]{6})", line)
                if m:
                    out[m.group(1)] = int(m.group(2), 16)
        return out

    def _modules(self):
        out, cur = {}, None
        for line in open(self.mapfile):
            if line.startswith("Segment list"):
                break
            m = re.match(r"^(\S+\.o):", line)
            if m:
                cur = m.group(1)
                out[cur] = {}
                continue
            m = re.match(r"^\s+(\w+)\s+Offs=([0-9A-F]+)\s+Size=([0-9A-F]+)", line)
            if m and cur:
                out[cur][m.group(1)] = (int(m.group(2), 16), int(m.group(3), 16))
        return out

    def _labels(self):
        out = {}
        for line in open(self.lblfile):
            m = re.match(r"al\s+([0-9A-Fa-f]+)\s+\.(\S+)", line)
            if m:
                out[m.group(2)] = int(m.group(1), 16)
        return out

    # -- la grammaire des .s ------------------------------------------------
    SIZE_OF = {"byte": 1, "res": 0, "word": 2, "addr": 2, "dbyt": 2,
               "dword": 4, "faraddr": 3}

    @staticmethod
    def _count_items(args):
        """Nombre d'elements d'une liste .byte/.word : les virgules de premier
        niveau plus un. Les chaines et les parentheses sont respectees."""
        n, depth, instr = 1, 0, False
        for c in args:
            if instr:
                if c == '"':
                    instr = False
            elif c == '"':
                instr = True
            elif c in "([":
                depth += 1
            elif c in ")]":
                depth -= 1
            elif c == "," and depth == 0:
                n += 1
        return n

    def _walk(self, path):
        """Rend {segment: [(label, taille), ...]} dans l'ordre du fichier."""
        seq, seg = {}, None
        pending = []          # labels vus sans directive de taille encore
        equ = {}              # les `NOM = valeur` du fichier (music.s en a)
        for raw in open(path, errors="replace"):
            line = raw.split(";")[0].rstrip()
            if not line.strip():
                continue
            m = re.match(r"^\s*(\w+)\s*=\s*([^;]+)$", line)
            if m and not line.lstrip().startswith("."):
                try:
                    equ[m.group(1)] = expr(m.group(2), equ)
                except Exception:
                    pass
                continue
            m = re.match(r'^\s*\.segment\s+"?(\w+)"?', line)
            if m:
                seg = m.group(1)
                pending = []
                continue
            if re.match(r"^\s*\.(proc|endproc|export|import|include|macro|"
                        r"endmacro|autoimport|case|debuginfo|forceimport|"
                        r"assert|if|endif|else|globalzp|global|zeropage)", line):
                continue
            # label: [directive]
            m = re.match(r"^\s*([A-Za-z_@][\w@]*):\s*(.*)$", line)
            if m:
                pending.append(m.group(1))
                line = "\t" + m.group(2)
                if not m.group(2).strip():
                    continue
            m = re.match(r"^\s*\.(\w+)\s*(.*)$", line)
            if not m or seg is None:
                continue
            d, args = m.group(1), m.group(2).strip()
            if d == "res":
                size = expr(args.split(",")[0], equ)
            elif d in self.SIZE_OF:
                size = self.SIZE_OF[d] * self._count_items(args)
            elif d == "asciiz":
                size = len(args.strip('"')) + 1
            else:
                continue
            seq.setdefault(seg, [])
            if pending:
                seq[seg].append([pending[0], size])
                for extra in pending[1:]:
                    seq[seg].append([extra, 0])   # alias sur la meme adresse
                # les alias precedent la taille : on remet dans l'ordre
                block = seq[seg][-len(pending):]
                block[0][1], block[-1][1] = 0, size
                if len(pending) == 1:
                    block[0][1] = size
                pending = []
            else:
                seq[seg].append(["", size])
        return seq

    def _resolve(self):
        out = {}
        for name in self.MODULES:
            obj, spath = name + ".o", os.path.join(self.srcdir, name + ".s")
            if obj not in self.mod or not os.path.exists(spath):
                continue
            seq = self._walk(spath)
            for seg, items in seq.items():
                if seg not in self.mod[obj] or seg not in self.seg:
                    continue
                addr = self.seg[seg] + self.mod[obj][seg][0]
                for label, size in items:
                    if label:
                        out.setdefault(label, addr)
                    addr += size
        return out

    # -- les garde-fous -----------------------------------------------------
    def _check(self):
        for name, want in self.lbl.items():
            got = self.sym.get(name)
            if got is not None and got != want:
                raise SymbolError(
                    "%s : la carte memoire dit $%04X, le .lbl dit $%04X. "
                    "L'un des deux est perime -- refaire `make`." %
                    (name, got, want))
        self.sym.update(self.lbl)
        for need in ("_app", "_restoring", "_state", "_visited", "_seen",
                     "_music_buf", "_music_cur", "_music_zone"):
            if need not in self.sym:
                raise SymbolError("symbole %s introuvable" % need)
        size = self.sym["_restoring"] - self.sym["_app"]
        if size != APP_SIZE:
            raise SymbolError(
                "AppState fait %d octets et non %d : la table OFF de "
                "playtest.py est perimee (scoswamp.c a bouge)." % (size, APP_SIZE))
        if self.sym["_visited"] - self.sym["_seen"] != 160:
            raise SymbolError("rules.c a change : _seen ne fait plus 160 octets")

    def __getitem__(self, k):
        return self.sym[k]


def expr(s, env=None):
    """Evalue une expression ca65 simple : nombres $hex / %bin / decimaux,
    constantes definies dans le meme fichier, et les quatre operations. C'est
    tout ce dont les `.res` du projet ont besoin."""
    env = env or {}
    s = re.sub(r"\$([0-9A-Fa-f]+)", lambda m: str(int(m.group(1), 16)), s)
    s = re.sub(r"%([01]+)", lambda m: str(int(m.group(1), 2)), s)
    s = re.sub(r"\b([A-Za-z_]\w*)\b",
               lambda m: str(env.get(m.group(1), m.group(1))), s)
    if not re.fullmatch(r"[\d\s+\-*/()]+", s):
        raise ValueError("expression non evaluable : %r" % s)
    return int(eval(s, {"__builtins__": {}}, {}))


# ── La forme de AppState, recopiee de scoswamp.c ──────────────────────────
# cc65 ne bourre jamais une structure : les champs se suivent. Les tailles
# viennent de scoswamp.c (MAX_CHOICES 5, MAX_PATH 10, MAX_FOES 3) et de
# rules.h (Character 24 octets, Monster 29). Le total est verifie contre
# `_restoring - _app` au demarrage : toute modification de la structure fait
# echouer le banc bruyamment au lieu de le laisser ecrire n'importe ou.
_APP_FIELDS = [
    ("current_scene", 2), ("video_mode", 1), ("choices", 5 * 8),
    ("num_choices", 1), ("language", 3), ("imgPath", 10), ("txtPath", 10),
    ("has_image", 1), ("hero", 24), ("hero_ready", 1), ("foes", 3 * 29),
    ("foe_img", 3 * 2), ("foe_count", 1), ("foe_cur", 1), ("flee_target", 2),
    ("pending_scene", 2), ("revisit", 2), ("choose_n", 1), ("choose_cats", 3),
    ("luck_ok", 2), ("luck_ko", 2), ("luck_dok", 2), ("luck_dko", 2),
    ("win_scene", 2), ("dice_n", 1), ("dice_carac", 1), ("cs_ok", 2),
    ("cs_ko", 2), ("cs_carac", 1), ("mb_ok", 2), ("mb_ko", 2),
    ("last_loss", 1), ("dv_done", 1), ("music_name", 16), ("music_over", 1),
]
OFF, _o = {}, 0
for _n, _s in _APP_FIELDS:
    OFF[_n] = _o
    _o += _s
APP_SIZE = _o

# Les memes offsets a l'interieur de Character (rules.h).
HERO = dict(hab=0, hab0=1, end=2, end0=3, cha=4, cha0=5, gold=6,
            weapon_bonus=8, stones=9, objects=21, amulets=23)

STONES = ["HABILETE", "ENDURANCE", "CHANCE", "FEU", "GLACE", "ILLUSION",
          "AMITIE", "CROISSANCE", "BENEDICTION", "TERREUR", "FLETRISSURE",
          "MALEDICTION"]
OBJECTS = ["ANNEAU", "CAPE", "CHAINE", "AIMANT", "FIOLE", "BAIE", "EPEMAGIQUE",
           "BIJOU", "CORNE", "PLUMES", "GRAINES", "ANTHERIQUE"]
AMULETS = ["LOUP", "FLEUR", "OISEAU", "ARAIGNEE", "GRENOUILLE", "FAUSSE_OISEAU"]

# music.s : mb_slot, playing... suivent _music_buf, seul symbole exporte du
# module. Les offsets sont resolus par Symbols ; ces noms servent de secours
# si un jour le parseur ne les trouvait plus.
MUSIC_FALLBACK = dict(mb_slot=3584, playing=3585, paused=3586, half=3587,
                      delay=3588, cur_lo=3589, cur_hi=3590)


# ═══════════════════════════════════════════════════════════════════════════
# 2. Le pilote POM2
# ═══════════════════════════════════════════════════════════════════════════

class Pom2(object):
    """Un emulateur, sa copie du disque, et l'API AI-control."""

    def __init__(self, hdv, port=DEFAULT_PORT, speed=200000, pom2=POM2,
                 verbose=False):
        self.port = port
        self.base = "http://127.0.0.1:%d" % port
        self.hdv = hdv
        self.speed = speed
        self.exe = pom2
        self.verbose = verbose
        self.proc = None

    # -- cycle de vie -------------------------------------------------------
    def start(self):
        cwd = os.path.dirname(self.hdv)          # le jail de safeCwdRelativePath
        log = open(os.path.join(cwd, "pom2.log"), "w")
        self.proc = subprocess.Popen(
            [self.exe, "--ai-control=%d" % self.port, "--speed", str(self.speed),
             os.path.basename(self.hdv)],
            cwd=cwd, stdout=log, stderr=subprocess.STDOUT,
            start_new_session=True)
        deadline = time.time() + 30
        while time.time() < deadline:
            try:
                self.rq("/status")
                return self
            except Exception:
                time.sleep(0.2)
        raise RuntimeError("POM2 ne repond pas sur le port %d" % self.port)

    def stop(self):
        """Tuer l'emulateur par son port : le PID ne suffit pas toujours (POM2
        peut se relancer sous un autre process pendant un changement de
        profil), et deux bancs ne doivent jamais se marcher dessus."""
        if self.proc is not None:
            try:
                os.killpg(os.getpgid(self.proc.pid), signal.SIGTERM)
            except Exception:
                pass
            try:
                self.proc.wait(timeout=5)
            except Exception:
                try:
                    os.killpg(os.getpgid(self.proc.pid), signal.SIGKILL)
                except Exception:
                    pass
            self.proc = None
        subprocess.call(["pkill", "-f", "ai-control=%d" % self.port])

    # -- transport ----------------------------------------------------------
    def rq(self, path, body=None, timeout=10):
        req = urllib.request.Request(
            self.base + path,
            data=json.dumps(body).encode() if body is not None else None)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())

    def peek(self, addr, n, bank="main"):
        out = b""
        while n:
            k = min(n, 4096)                     # GET /mem plafonne a 4096
            q = "/mem?addr=%d&len=%d" % (addr, k)
            if bank == "aux":
                q += "&bank=aux"
            out += bytes.fromhex(self.rq(q)["data"])
            addr += k
            n -= k
        return out

    def poke(self, addr, data):
        if addr + len(data) > 0xC000:
            raise ValueError("POST /mem refuse l'espace d'E/S et la ROM")
        return self.rq("/mem?addr=%d" % addr, {"data": data.hex()})["written"]

    def keys(self, text):
        return self.rq("/keyboard", {"text": text})["queued"]

    def raw(self, data):
        """Envoie des octets bruts (ESC = \\x1b).

        Le corps est bati a la main : le lecteur JSON de POM2
        (AiControlServer.cpp:220-244) ne connait PAS les echappements \\uXXXX
        -- il prend la lettre qui suit une contre-oblique telle quelle. Un
        json.dumps("\\x1b") lui aurait fait taper « u001b », soit cinq touches,
        dont un 'b' qui prend le choix B de la page en cours. C'est le genre de
        bug qui fait croire a un bug du jeu."""
        if isinstance(data, str):
            data = data.encode("latin-1")
        body = b'{"raw":"' + data + b'"}'
        req = urllib.request.Request(self.base + "/keyboard", data=body)
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())["queued"]

    # -- l'ecran texte 80 colonnes -----------------------------------------
    #
    # SCOSWAMP ecrit sa barre de titre en video inverse (revers(1)). Sur //e
    # avec ALTCHARSET -- que le firmware 80 colonnes allume -- l'inverse occupe
    # $00-$7F : un masque & 0x7F rendrait $13 (S inverse) illisible. D'ou ce
    # decodage en quatre branches.
    @staticmethod
    def _cell(b):
        if b >= 0x80:
            return chr(b & 0x7F)          # normal
        if b < 0x20:
            return chr(b + 0x40)          # inverse @ A-Z [ \ ] ^ _
        if b < 0x40:
            return chr(b)                 # inverse espace et ponctuation
        if b < 0x60:
            return "▯"               # MouseText -- le jeu n'en met pas
        return chr(b)                     # inverse minuscules

    def screen(self):
        """24 lignes de 80 caracteres. La page texte ne quitte jamais
        $400-$7FF, meme en HGR plein ecran (memory_swap.c) : ce releve est
        valable dans les trois modes video."""
        main = self.peek(0x0400, 1024)
        aux = self.peek(0x0400, 1024, "aux")
        rows = []
        for r in range(24):
            base = 0x80 * (r % 8) + 0x28 * (r // 8)
            rows.append("".join(self._cell(aux[base + c]) + self._cell(main[base + c])
                                for c in range(40)))
        return rows

    def digest(self):
        m = self.peek(0x0400, 1024) + self.peek(0x0400, 1024, "aux")
        return hashlib.blake2s(m).digest()

    def stable(self, tries=200, pause=0.05, need=6):
        """Attend que l'ecran ne bouge plus `need` releves de suite. C'est
        l'indicateur que le jeu est retourne dans son cgetc() : POM2 n'expose
        pas pendingPasteSize(), il n'y a pas mieux.

        La fenetre de silence doit etre GENEREUSE. Une page de combat ecrit
        son texte, puis lit son image RLE au disque -- 160 ms d'ecran fige a
        12x -- puis seulement alors peint le bandeau des combattants. Avec
        deux releves de 50 ms le banc rendait la main pendant la lecture
        disque et jurait que le bandeau n'existait pas. Six releves, soit
        300 ms de silence, couvrent la plus longue lecture mesuree."""
        prev, same = None, 0
        for _ in range(tries):
            cur = self.digest()
            if cur == prev:
                same += 1
                if same >= need:
                    return self.screen()
            else:
                same = 0
            prev = cur
            time.sleep(pause)
        raise TimeoutError("l'ecran ne se stabilise pas")

    def wait_for(self, needle, tries=200, pause=0.1):
        """Attend qu'un fragment apparaisse a l'ecran, puis rend l'ecran."""
        for _ in range(tries):
            rows = self.screen()
            if any(needle in r for r in rows):
                return self.stable()
            time.sleep(pause)
        raise TimeoutError("« %s » n'apparait pas" % needle)


# ═══════════════════════════════════════════════════════════════════════════
# 3. Le jeu vu de l'hote
# ═══════════════════════════════════════════════════════════════════════════

BAR_FR = re.compile(r"HAB (\d+)/(\d+)\s+END (\d+)/(\d+)\s+CHA (\d+)/(\d+)")


class Game(object):
    def __init__(self, pom, sym):
        self.p = pom
        self.s = sym

    # -- adresses -----------------------------------------------------------
    def A(self, field):
        return self.s["_app"] + OFF[field]

    def H(self, field):
        return self.A("hero") + HERO[field]

    def M(self, field):
        """Une variable locale de music.s, derriere _music_buf."""
        try:
            return self.s[field]
        except KeyError:
            return self.s["_music_buf"] + MUSIC_FALLBACK[field]

    # -- demarrage ----------------------------------------------------------
    def boot(self, lang="F"):
        self.p.wait_for("LANGUE")
        self.p.keys(lang)
        self.p.wait_for("MARAIS AUX SCORPIONS")
        rows = self.p.stable()
        self.assert_addresses()
        return rows

    def assert_addresses(self):
        """La sonde de §4.2 : avant toute ecriture, verifier que _app est bien
        la ou le lien le dit. app.language vaut FR ou EN des que le choix de
        langue est passe ; sinon l'adresse est fausse ou le jeu n'a pas fini
        de demarrer, et poker serait ecrire au hasard."""
        lang = self.p.peek(self.A("language"), 2)
        if lang not in (b"FR", b"EN"):
            raise SymbolError(
                "sonde _app : app.language vaut %r et non FR/EN -- "
                "adresse fausse ou jeu pas pret" % lang)

    # -- lecture -----------------------------------------------------------
    def screen(self):
        return self.p.screen()

    def text(self, rows=None):
        return "\n".join(rows or self.p.screen())

    def sheet(self, rows=None):
        m = BAR_FR.search((rows or self.p.screen())[0])
        if not m:
            raise AssertionError("Feuille d'Aventure absente de la barre de titre")
        v = [int(x) for x in m.groups()]
        return dict(hab=v[0], hab0=v[1], end=v[2], end0=v[3], cha=v[4], cha0=v[5])

    def hero(self):
        """La Feuille d'Aventure lue en RAM, plus fiable que la barre."""
        b = self.p.peek(self.A("hero"), 24)
        return dict(hab=b[0], hab0=b[1], end=b[2], end0=b[3], cha=b[4], cha0=b[5],
                    gold=struct.unpack_from("<H", b, 6)[0], bonus=b[8],
                    stones=list(b[9:21]),
                    objects=struct.unpack_from("<H", b, 21)[0], amulets=b[23])

    def scene(self):
        return struct.unpack("<h", self.p.peek(self.A("current_scene"), 2))[0]

    def choices(self, rows=None):
        """Les lettres offertes, lignes 20-23. Un choix barre porte '-)'."""
        rows = rows or self.p.screen()
        out = []
        for r in rows[20:24]:
            out += re.findall(r"(?:^|\s\s)([A-Z-])\)", r)
        return out

    def stones(self):
        h = self.hero()
        return {STONES[i]: n for i, n in enumerate(h["stones"]) if n}

    def objects(self):
        m = self.hero()["objects"]
        return [o for i, o in enumerate(OBJECTS) if m & (1 << i)]

    def amulets(self):
        m = self.hero()["amulets"]
        return [a for i, a in enumerate(AMULETS) if m & (1 << i)]

    def music(self):
        cur = self.p.peek(self.s["_music_cur"], 16).split(b"\0")[0].decode("ascii", "replace")
        zone = self.p.peek(self.s["_music_zone"], 16).split(b"\0")[0].decode("ascii", "replace")
        return dict(slot=self.p.peek(self.M("mb_slot"), 1)[0],
                    playing=self.p.peek(self.M("playing"), 1)[0],
                    cur=cur, zone=zone,
                    cursor=struct.unpack("<H", self.p.peek(self.M("cur_lo"), 2))[0])

    # -- frappe -------------------------------------------------------------
    def press(self, k, settle=True):
        if k == "ESC":
            self.p.raw("")
        else:
            self.p.keys(k)
        return self.p.stable() if settle else None

    def press_until(self, k, needle, tries=12):
        for _ in range(tries):
            rows = self.press(k)
            if any(needle in r for r in rows):
                return rows
        raise AssertionError("« %s » n'apparait pas apres %d fois [%s]"
                             % (needle, tries, k))

    def choose(self, letter, expect=None):
        rows = self.press(letter)
        if expect is not None:
            self.expect(expect, rows)
        return rows

    # -- la porte cachee ----------------------------------------------------
    def sheet_bytes(self, hab=12, end=20, cha=11, hab0=None, end0=None,
                    cha0=None, gold=20, bonus=0, stones=(), objects=(),
                    amulets=()):
        st = bytearray(12)
        for name, n in (stones.items() if isinstance(stones, dict) else stones):
            st[STONES.index(name)] = n
        om = 0
        for o in objects:
            om |= 1 << OBJECTS.index(o)
        am = 0
        for a in amulets:
            am |= 1 << AMULETS.index(a)
        return (bytes([hab, hab if hab0 is None else hab0,
                       end, end if end0 is None else end0,
                       cha, cha if cha0 is None else cha0])
                + struct.pack("<H", gold) + bytes([bonus]) + bytes(st)
                + struct.pack("<H", om) + bytes([am]))

    def goto(self, page, seed=0x1234, replay=True, visited=(), foes=(),
             land=None, tries=8, **hero):
        """Teleporte le heros a `page` avec l'etat demande.

        La boucle principale relit pending_scene AVANT chaque cgetc() : il
        suffit donc de poser l'etat pendant qu'elle est bloquee sur la touche,
        puis d'envoyer une touche inerte. 'Z' convient : la branche lettre
        calcule choice_num = 25, superieur a num_choices, et ne fait rien.

        Mais le jeu n'est pas toujours dans cette boucle : un jet de des, un
        combat, le sac ou la page des sauvegardes ont leur propre cgetc(), et
        la touche y serait avalee. On insiste donc : a chaque essai on repose
        TOUT l'etat puis on frappe -- d'abord ESPACE, qui denoue n'importe
        quelle invite interne, puis 'Z'. Le dernier essai est celui qui a
        reussi, donc l'etat pose est bien celui qu'on lit ensuite.

        replay=False met restoring a 1, ce qui inhibe les effets d'entree
        (E, E0, ED, G, GX, GA, P, PC, PD, PO, PX, CE, TR, V) exactement comme
        une reprise de sauvegarde.

        `land` dit sur quelle page on doit atterrir quand la page demandee en
        renvoie vers une autre -- une ligne V, par exemple."""
        want = page if land is None else land
        self.assert_addresses()
        for attempt in range(tries):
            self.p.poke(self.s["_state"], struct.pack("<I", seed))
            self.p.poke(self.A("hero"), self.sheet_bytes(**hero))
            self.p.poke(self.A("hero_ready"), b"\x01")   # sinon roll_character
            self.p.poke(self.s["_visited"], bits52(visited))
            self.p.poke(self.s["_seen"], slots160(foes))
            self.p.poke(self.s["_restoring"], b"\x00" if replay else b"\x01")
            self.p.poke(self.A("pending_scene"), struct.pack("<h", page))
            # ESPACE denoue les invites (jet de des, assaut, « continuer »),
            # 'A' celles qui exigent une lettre (choix des Pierres, sac), et
            # 'Z' est la touche inerte qui rend la main a la boucle
            # principale. On insiste un peu plus a chaque essai.
            self.p.keys(" A" * (2 * attempt) + "Z")
            rows = self.p.stable()
            pending = struct.unpack("<h", self.p.peek(self.A("pending_scene"), 2))[0]
            if pending == -1 and self.scene() == want:
                return rows
        raise AssertionError(
            "impossible d'atteindre la page %d : on est reste sur la %d "
            "(le jeu etait peut-etre bloque dans une invite interne)"
            % (want, self.scene()))

    # -- assertions ---------------------------------------------------------
    def expect(self, needle, rows=None):
        rows = rows or self.p.screen()
        if not any(needle in r for r in rows):
            raise AssertionError("« %s » absent de l'ecran" % needle)
        return rows

    def refute(self, needle, rows=None):
        rows = rows or self.p.screen()
        if any(needle in r for r in rows):
            raise AssertionError("« %s » ne devrait pas etre a l'ecran" % needle)
        return rows


def bits52(scenes):
    b = bytearray(52)
    for s in scenes:
        b[s >> 3] |= 1 << (s & 7)
    return bytes(b)


def slots160(foes):
    b = bytearray(160)
    for i, (sc, idx, end) in enumerate(list(foes)[:40]):
        struct.pack_into("<HBB", b, i * 4, sc, idx, end)
    return bytes(b)


# ═══════════════════════════════════════════════════════════════════════════
# 4. Les sauvegardes forgees
# ═══════════════════════════════════════════════════════════════════════════
#
# forge_save.build() fabrique les 276 octets SCS3. Reste a les poser dans le
# volume ProDOS. Les numeros de bloc de PARTIE9 changent a chaque
# reconstruction de l'image : on parcourt le catalogue plutot que de porter
# des constantes -- sinon un jour on ecrit 276 octets au milieu d'une image
# RLE, et le bug qui en sort coute une soiree.

sys.path.insert(0, HERE)
import forge_save  # noqa: E402


def prodos_find(hdv, path):
    """Rend (bloc_de_l_entree, offset, bloc_cle, storage_type) d'un fichier."""
    with open(hdv, "rb") as f:
        def block(n):
            f.seek(n * 512)
            return f.read(512)

        def entries(key):
            blk = key
            while blk:
                data = block(blk)
                nxt = data[2] | (data[3] << 8)
                for i in range(13):
                    off = 4 + i * 39
                    e = data[off:off + 39]
                    st, nl = e[0] >> 4, e[0] & 0x0F
                    if st == 0 or nl == 0:
                        continue
                    yield (blk, off, e[1:1 + nl].decode("ascii", "replace"), st,
                           e[0x11] | (e[0x12] << 8))
                blk = nxt

        key = 2
        for part in path.strip("/").split("/")[1:]:   # le 1er est le volume
            found = None
            for blk, off, name, st, kp in entries(key):
                if name.upper() == part.upper():
                    found = (blk, off, st, kp)
                    break
            if not found:
                raise RuntimeError("%s introuvable dans %s" % (part, hdv))
            blk, off, st, kp = found
            key = kp
        return blk, off, kp, st


def install_save(hdv, blob, slot=9):
    """Ecrit `blob` dans PARTIE<slot> du volume, EOF compris.

    Un seedling ProDOS porte jusqu'a 512 octets : les 276 d'une sauvegarde y
    entrent sans reallocation, sans toucher la bitmap ni le type de stockage.
    """
    blk, off, key, st = prodos_find(hdv, "/SCOSWAMP/SAVE/PARTIE%d" % slot)
    if st != 1:
        raise RuntimeError("PARTIE%d n'est pas un seedling (type %d)" % (slot, st))
    with open(hdv, "r+b") as f:
        f.seek(key * 512)
        f.write(blob.ljust(512, b"\0"))
        f.seek(blk * 512 + off + 0x15)
        f.write(bytes((len(blob) & 0xFF, (len(blob) >> 8) & 0xFF, 0)))
    return key


# ═══════════════════════════════════════════════════════════════════════════
# 5. Le banc : scenarios et verdicts
# ═══════════════════════════════════════════════════════════════════════════

SCENARIOS = []


def scenario(name, title, forge=None):
    """Enregistre un scenario. `forge` est un dict d'arguments pour
    forge_save.build : le disque est alors patche avant le lancement de POM2,
    et le scenario reprend la partie par [L] 9."""
    def deco(fn):
        SCENARIOS.append(dict(name=name, title=title, fn=fn, forge=forge))
        return fn
    return deco


class Bench(object):
    """Le compteur d'assertions d'un scenario."""

    def __init__(self, name, verbose):
        self.name = name
        self.verbose = verbose
        self.ok = 0
        self.failures = []

    def check(self, label, cond, detail=""):
        if cond:
            self.ok += 1
            if self.verbose:
                print("      . %s" % label)
        else:
            self.failures.append((label, detail))
            print("      X %s%s" % (label, ("  -- " + detail) if detail else ""))
        return bool(cond)

    def eq(self, label, got, want):
        return self.check(label, got == want, "obtenu %r, attendu %r" % (got, want))

    def has(self, label, rows, needle):
        return self.check(label, any(needle in r for r in rows),
                          "« %s » absent" % needle)

    def hasnt(self, label, rows, needle):
        return self.check(label, not any(needle in r for r in rows),
                          "« %s » present" % needle)


# ── (a) Le prologue, les trois employeurs, l'entree dans le Marais ────────

@scenario("demarrage", "Demarrage, langue, accueil, creation du personnage")
def sc_demarrage(g, b):
    rows = g.p.wait_for("LANGUE")
    b.has("l'ecran de langue propose [F] et [E]", rows, "[F]")
    g.p.keys("F")
    rows = g.p.wait_for("LE MARAIS AUX SCORPIONS")
    b.has("l'accueil (page 000) s'affiche en francais", rows, "Creer mon personnage")
    b.eq("app.language vaut FR", g.p.peek(g.A("language"), 2), b"FR")
    b.eq("la page courante est la 000", g.scene(), 0)
    b.has("la barre rappelle les touches avant les des", rows, "I=SAC")

    rows = g.press("A")            # A) Creer mon personnage -> roll_character
    b.has("la creation du personnage montre la Feuille d'Aventure",
          rows, "FEUILLE D'AVENTURE")
    b.has("HABILETE : 1 de + 6", rows, "HABILETE")
    h = g.hero()
    b.check("HABILETE dans 7..12", 7 <= h["hab"] <= 12, "hab=%d" % h["hab"])
    b.check("ENDURANCE dans 14..24", 14 <= h["end"] <= 24, "end=%d" % h["end"])
    b.check("CHANCE dans 7..12", 7 <= h["cha"] <= 12, "cha=%d" % h["cha"])
    b.check("les trois totaux de depart egalent les valeurs courantes",
            (h["hab"], h["end"], h["cha"]) == (h["hab0"], h["end0"], h["cha0"]))

    rows = g.press(" ")            # [ESPACE] entrer dans le Marais -> page 001
    b.eq("le village (page 001) suit la creation", g.scene(), 1)
    b.has("le titre de la page est dans la barre", rows, "Le chemin vers le Marais")
    s = g.sheet(rows)
    b.eq("la barre porte la Feuille d'Aventure", (s["hab"], s["end"], s["cha"]),
         (h["hab"], h["end"], h["cha"]))
    b.check("deux choix sont offerts au village", g.choices(rows) == ["A", "B"],
            repr(g.choices(rows)))
    b.check("aucune ligne ne deborde de 80 colonnes",
            all(len(r) == 80 for r in rows))


@scenario("gayolard", "Gayolard : la quete de l'Antherique et six Pierres")
def sc_gayolard(g, b):
    g.goto(335)
    b.has("on arrive Chez Gayolard", g.screen(), "Chez Gayolard")
    rows = g.choose("A")                 # 371 : lui reveler l'Anneau
    b.eq("la quete de l'Antherique est la page 371", g.scene(), 371)
    b.has("l'ecran des Pierres s'ouvre", rows, "CHOISISSEZ VOS PIERRES")
    b.has("il reste six Pierres a prendre", rows, "il en reste 6")
    b.hasnt("aucune Pierre malefique n'est proposee (PC 6 NB)", rows, "Maledicti")
    for _ in range(6):
        rows = g.press("A")              # la premiere de la liste, six fois
    b.eq("les six Pierres sont dans le sac", sum(g.hero()["stones"]), 6)
    b.has("la page rend la main sur le choix de depart", rows, "Commencer votre aventure")
    rows = g.choose("A")
    b.eq("on entre dans le Marais par la page 009", g.scene(), 9)
    b.has("la lisiere sud est annoncee", rows, "L'entree du Marais")


@scenario("pompatarte", "Pompatarte : la carte, et ses cinq Pierres neutres")
def sc_pompatarte(g, b):
    g.goto(27)
    b.has("on arrive Chez Pompatarte", g.screen(), "Chez Pompatarte")
    rows = g.choose("B")                 # 173 : le guerrier hors pair
    b.eq("le Marchand Rouge est la page 173", g.scene(), 173)
    # Le bug de septembre : la page 173 n'avait PAS de ligne PC, et le heros
    # partait de chez Pompatarte les mains vides alors que le texte lui offre
    # cinq Pierres. C'est cette assertion qui l'aurait attrape.
    b.has("Pompatarte ouvre bien l'ecran des Pierres", rows, "CHOISISSEZ VOS PIERRES")
    b.has("il en reste cinq a prendre", rows, "il en reste 5")
    for _ in range(5):
        rows = g.press("A")
    n = sum(g.hero()["stones"])
    b.eq("les cinq Pierres promises sont dans le sac", n, 5)
    b.check("elles sont toutes neutres (PC 5 N)",
            all(g.hero()["stones"][i] == 0 for i in range(6, 12)),
            repr(g.stones()))
    rows = g.choose("A")
    b.eq("on entre dans le Marais par la page 009", g.scene(), 9)


@scenario("stratagus", "Stratagus : les Amulettes et six Pierres sans le Bien")
def sc_stratagus(g, b):
    rows = g.goto(255)
    b.has("la tour de Stratagus", rows, "La tour de Stratagus")
    rows = g.choose("B")                 # 040 : aller frapper a la porte
    b.eq("on frappe a la porte (page 040)", g.scene(), 40)
    b.check("trois issues sont offertes devant Stratagus",
            g.choices(rows) == ["A", "B", "C"], repr(g.choices(rows)))
    # La mission elle-meme est page 206, au bout d'une epreuve. On y va
    # directement : c'est l'offre de Pierres qu'on veut mesurer.
    rows = g.goto(206)
    b.has("la mission de Stratagus", rows, "Mission de Stratagus")
    b.has("l'ecran des Pierres s'ouvre", rows, "CHOISISSEZ VOS PIERRES")
    b.has("il en reste six a prendre", rows, "il en reste 6")
    b.hasnt("aucune Pierre benefique (PC 6 NM)", rows, "Benediction")
    for _ in range(6):
        rows = g.press("A")
    b.eq("les six Pierres sont dans le sac", sum(g.hero()["stones"]), 6)
    rows = g.choose("A")
    b.eq("on quitte la tour vers le Marais (page 009)", g.scene(), 9)
    rows = g.choose("A")
    b.eq("le sentier mene a la clairiere 1 (page 195)", g.scene(), 195)


# ── (b) Le combat, la mort, et [R] ────────────────────────────────────────

@scenario("combat", "Un combat simple : deux points par coup encaisse")
def sc_combat(g, b):
    # Page 222 : le Demon de la tour, M 12 16, aucune ligne MD -- donc les
    # 2 points par defaut du livre. Des deterministes : la graine est posee.
    rows = g.goto(222, seed=0x2222, hab=12, end=20, cha=11)
    b.has("le Demon attend", rows, "DEMON")
    b.has("le bandeau porte les deux combattants", rows, "VOUS")
    b.has("l'invite propose d'engager", rows, "engager")
    end0 = g.hero()["end"]
    foe0 = g.p.peek(g.A("foes") + 1, 1)[0]
    losses, hits, rounds = 0, 0, 0
    for _ in range(40):
        rows = g.press(" ")
        rounds += 1
        if any("ENDURANCE est tombee" in r for r in rows):
            break
        if any("s'effondre" in r for r in rows):
            break
        e, f = g.hero()["end"], g.p.peek(g.A("foes") + 1, 1)[0]
        if e < end0:
            losses += end0 - e
            b.check("le coup encaisse coute exactement 2 points d'ENDURANCE",
                    (end0 - e) in (0, 2), "perte de %d" % (end0 - e))
            end0 = e
        if f < foe0:
            hits += foe0 - f
            b.check("le coup porte coute 2 points a l'adversaire",
                    (foe0 - f) == 2, "perte de %d" % (foe0 - f))
            foe0 = f
    b.check("le combat a bien echange des assauts", rounds > 1, "rounds=%d" % rounds)
    b.check("au moins un camp a ete touche", losses + hits > 0)


@scenario("mort", "La mort : ecran de mort, [R] recommence")
def sc_mort(g, b):
    rows = g.goto(222, seed=0x1111, hab=6, end=2, cha=4)
    b.has("le combat s'ouvre avec 2 points d'ENDURANCE", rows, "DEMON")
    for _ in range(30):
        rows = g.press(" ")
        if any("ENDURANCE est tombee" in r for r in rows):
            break
    b.has("l'ecran de mort annonce l'ENDURANCE a zero", rows,
          "Votre ENDURANCE est tombee a zero")
    b.has("il propose [R], [L] et [Q]", rows, "[R] recommencer")
    rows = g.press("R")
    b.eq("[R] ramene a l'accueil (page 000)", g.scene(), 0)
    b.eq("le heros n'est plus pret : les des seront rejetes",
         g.p.peek(g.A("hero_ready"), 1)[0], 0)
    b.eq("la memoire des clairieres est videe",
         g.p.peek(g.s["_visited"], 52), bytes(52))
    b.eq("la memoire des monstres est videe",
         g.p.peek(g.s["_seen"], 160), bytes(160))


# ── (c) La page 155 : la benediction de Grognard ──────────────────────────

@scenario("benediction", "Page 155 : E0 CHANCE +2 leve la valeur ET le plafond")
def sc_benediction(g, b):
    g.goto(155, cha=9, hab=11, end=18)
    before = g.hero()
    b.eq("le heros arrive a 9 de CHANCE sur 9", (before["cha"], before["cha0"]), (9, 9))
    rows = g.screen()
    b.has("la benediction de Grognard", rows, "La benediction de Grognard")
    after = g.hero()
    b.eq("la CHANCE monte de 2", after["cha"], before["cha"] + 2)
    b.eq("le PLAFOND de CHANCE monte aussi (E0)", after["cha0"], before["cha0"] + 2)
    s = g.sheet(rows)
    b.eq("la barre affiche 11/11", (s["cha"], s["cha0"]), (11, 11))
    # restoring=1 : les effets d'entree sont inhibes, comme a la reprise.
    g.goto(155, cha=9, hab=11, end=18, replay=False)
    again = g.hero()
    b.eq("a la reprise d'une sauvegarde, E0 ne rejoue pas",
         (again["cha"], again["cha0"]), (9, 9))


# ── (d) Sauvegarde et chargement ──────────────────────────────────────────

@scenario("sauvegardes", "Sauvegarde [S], liste des titres, rechargement [L]")
def sc_sauvegardes(g, b):
    g.goto(195, hab=12, end=20, cha=11, gold=77,
           stones={"FEU": 2}, objects=("ANNEAU",))
    titre = g.screen()[0].strip().split("  ")[0]
    rows = g.press("S")
    b.has("la page de sauvegarde s'ouvre", rows, "SAUVER")
    b.has("dix emplacements sont listes", rows, "9)")
    rows = g.press("7")
    b.has("la partie est sauvee", rows, "Partie sauvee")
    rows = g.press("L")
    b.has("la page de chargement s'ouvre", rows, "REPRENDRE")
    b.check("l'emplacement 7 porte le titre de la page",
            any(re.search(r"7\)\s+\S", r) and "vide" not in r for r in rows),
            repr([r.strip() for r in rows if r.strip().startswith("7)")]))
    # On abime volontairement le heros, puis on recharge : tout doit revenir.
    g.p.poke(g.H("end"), bytes([3]))
    g.p.poke(g.H("gold"), struct.pack("<H", 0))
    rows = g.press("7")
    b.eq("le rechargement rend l'or", g.hero()["gold"], 77)
    b.eq("le rechargement rend l'ENDURANCE", g.hero()["end"], 20)
    b.eq("le rechargement rend les Pierres", g.stones(), {"FEU": 2})
    b.eq("on est revenu a la page sauvee", g.scene(), 195)
    rows = g.press("L")
    rows = g.press("0")
    b.has("un emplacement vide est refuse proprement", rows,
          "Emplacement vide ou fichier corrompu")
    b.eq("la partie en cours survit au refus", g.hero()["gold"], 77)


@scenario("forge", "Une sauvegarde forgee hors du jeu se recharge",
          forge=dict(scene=195, title="BANC FORGE 195", hab=(10, 12),
                     end=(15, 22), cha=(8, 11), gold=1234,
                     stones={"FEU": 3, "GLACE": 1},
                     objects=("ANNEAU", "BAIE"), amulets=("LOUP", "OISEAU"),
                     visited=(1, 195)))
def sc_forge(g, b):
    rows = g.p.wait_for("LANGUE")
    g.p.keys("F")
    g.p.wait_for("LE MARAIS AUX SCORPIONS")
    rows = g.press("L")
    b.has("la page de chargement s'ouvre depuis l'accueil", rows, "REPRENDRE")
    b.has("l'emplacement 9 porte le titre forge", rows, "BANC FORGE 195")
    rows = g.press("9")
    h = g.hero()
    b.eq("la page forgee est chargee", g.scene(), 195)
    b.eq("les trois caracteristiques sont celles du fichier",
         (h["hab"], h["hab0"], h["end"], h["end0"], h["cha"], h["cha0"]),
         (10, 12, 15, 22, 8, 11))
    b.eq("l'or aussi", h["gold"], 1234)
    b.eq("les Pierres aussi", g.stones(), {"FEU": 3, "GLACE": 1})
    b.eq("les objets aussi", sorted(g.objects()), ["ANNEAU", "BAIE"])
    b.eq("les amulettes aussi", sorted(g.amulets()), ["LOUP", "OISEAU"])
    b.eq("la memoire des clairieres est restauree",
         g.p.peek(g.s["_visited"], 52), bits52((1, 195)))


# ── (e) L'interface : sac, aide, page sans issue ──────────────────────────

@scenario("interface", "[I] le sac, [H] l'aide, page sans issue R/L/Q")
def sc_interface(g, b):
    g.goto(195, gold=42, stones={"FEU": 2, "AMITIE": 1},
           objects=("ANNEAU", "CAPE"), amulets=("LOUP",))
    avant = g.p.digest()
    rows = g.press("I")
    b.has("le sac s'ouvre", rows, "SAC A DOS")
    b.has("l'or y figure", rows, "42 Pieces d'Or")
    b.has("les Pierres y figurent", rows, "Feu")
    b.has("les objets y figurent", rows, "Anneau de Cuivre")
    b.has("les amulettes y figurent", rows, "Loup")
    g.press("I")
    b.check("[I] referme le sac et restitue la page a l'identique",
            g.p.digest() == avant)
    rows = g.press("H")
    b.check("[H] ouvre l'aide", any("MARAIS" in r or "Pierre" in r for r in rows),
            repr(rows[2][:60]))
    g.press("ESC")
    b.check("l'aide se referme et rend la page", g.p.digest() == avant)
    # Sac vide : le message dedie.
    g.goto(195, stones=(), objects=(), amulets=())
    rows = g.press("I")
    b.has("un sac vide le dit", rows, "Aucune Pierre Magique")
    g.press("I")
    # Page terminale : 175 est une fin, aucun choix.
    rows = g.goto(175, objects=("BAIE",))
    b.eq("une page terminale n'offre aucune lettre", g.choices(rows), [])
    b.has("elle propose [R], [L] et [Q]", rows, "[R] recommencer")


@scenario("video", "[ESPACE] fait tourner les trois modes video")
def sc_video(g, b):
    rows = g.goto(195)
    b.eq("la page 195 est illustree", g.p.peek(g.A("has_image"), 1)[0], 1)
    b.eq("on demarre en mode texte", g.p.peek(g.A("video_mode"), 1)[0], 0)
    txt0 = g.screen()
    g.press(" ")
    b.eq("[ESPACE] passe en HGR plein ecran",
         g.p.peek(g.A("video_mode"), 1)[0], 1)
    b.check("la page texte survit au plein ecran (memory_swap.c)",
            g.screen() == txt0)
    g.press(" ")
    b.eq("[ESPACE] passe en mode mixte", g.p.peek(g.A("video_mode"), 1)[0], 2)
    g.press(" ")
    b.eq("[ESPACE] revient au texte", g.p.peek(g.A("video_mode"), 1)[0], 0)


# ── (f) Un objet donne puis exige ─────────────────────────────────────────

@scenario("graines", "Les Graines d'Arbre-Epee : page 022 les donne, 374 les exige")
def sc_graines(g, b):
    # Le bug de septembre : OBJ_GRAINES n'existait pas dans OBJFR.TXT, donc
    # `G GR` de la page 022 ne posait aucun bit, et la page 374 n'offrait
    # jamais son sortilege de Croissance.
    rows = g.goto(22, objects=())
    b.has("les pousses rapides", rows, "Les pousses rapides")
    b.check("la page 022 donne les Graines d'Arbre-Epee",
            "GRAINES" in g.objects(), repr(g.objects()))
    rows = g.press("I")
    b.has("elles ont un nom dans le sac", rows, "Graines")
    g.press("I")
    # Sans les graines, la page 374 n'offre que quatre sortileges.
    rows = g.goto(374, objects=())
    n_sans = len(g.choices(rows))
    b.hasnt("sans les Graines, aucun sortilege de Croissance", rows, "Croissance")
    rows = g.goto(374, objects=("GRAINES",))
    b.has("avec les Graines, le sortilege de Croissance apparait",
          rows, "Croissance")
    b.eq("il ajoute exactement un choix", len(g.choices(rows)), n_sans + 1)
    letters = g.choices(rows)
    rows = g.choose(letters[0])
    b.eq("le sortilege mene aux graines-armes (page 228)", g.scene(), 228)
    b.check("les Graines sont consommees (GU)", "GRAINES" not in g.objects(),
            repr(g.objects()))


@scenario("baie_anneau", "La Baie chez Gayolard, l'Anneau vendu chez Pompatarte")
def sc_baie_anneau(g, b):
    rows = g.goto(6, objects=("ANNEAU",))
    b.has("Gayolard demande la baie", rows, "Maison de Gayolard")
    b.eq("sans la baie, un seul aveu est offert", len(g.choices(rows)), 1)
    rows = g.goto(6, objects=("ANNEAU", "BAIE"))
    b.eq("avec la baie, deux reponses sont offertes", len(g.choices(rows)), 2)
    # L'Anneau : page 049, GX ANNEAU, la vente qui termine l'aventure.
    rows = g.goto(49, objects=("ANNEAU",), gold=20)
    b.check("la vente retire l'Anneau du sac", "ANNEAU" not in g.objects(),
            repr(g.objects()))


# ── (g) Une revisite de clairiere par une autre porte ─────────────────────

@scenario("revisite", "Ligne V : revenir dans une clairiere par une autre porte")
def sc_revisite(g, b):
    line = open(os.path.join(ROOT, "SCOSWAMP", "TEXTFR", "N350", "N350.TXT")
                ).read().splitlines()
    vline = [l for l in line if l.startswith("V ")]
    b.check("la page 350 porte bien une ligne V", bool(vline), repr(vline))
    target = int(vline[0].split()[1]) if vline else 331
    others = [int(x) for x in vline[0].split()[2:]] if vline else []
    rows = g.goto(350, visited=())
    b.eq("premiere visite : on reste sur la page 350", g.scene(), 350)
    b.check("la premiere visite affiche du texte",
            any(r.strip() for r in rows[2:18]))
    rows = g.goto(350, visited=(350,))
    b.eq("deja vue par la meme porte : detour immediat", g.scene(), target)
    if others:
        rows = g.goto(350, visited=(others[0],))
        b.eq("deja vue par une AUTRE porte (liste de la ligne V) : "
             "detour aussi", g.scene(), target)
    else:
        b.check("la ligne V porte une liste de pages soeurs", False,
                "aucune page citee apres la cible")
    rows = g.goto(350, visited=(350,), replay=False)
    b.eq("a la reprise d'une sauvegarde, V est inhibe", g.scene(), 350)


# ── (h) Les trois fins ────────────────────────────────────────────────────

@scenario("fin_175", "Fin 175 : la baie rendue a Gayolard, succes complet",
          forge=dict(scene=6, title="AVANT LA FIN 175", hab=(10, 12),
                     end=(14, 22), cha=(9, 11), gold=30,
                     objects=("ANNEAU", "BAIE"), visited=(1, 6)))
def sc_fin_175(g, b):
    g.p.wait_for("LANGUE")
    g.p.keys("F")
    g.p.wait_for("LE MARAIS AUX SCORPIONS")
    g.press("L")
    rows = g.press("9")
    b.eq("la sauvegarde forgee ouvre chez Gayolard", g.scene(), 6)
    b.check("la Baie est bien dans le sac", "BAIE" in g.objects(), repr(g.objects()))
    b.eq("deux reponses sont offertes", len(g.choices(rows)), 2)
    rows = g.choose("A")
    b.eq("remettre la baie mene a la page 175", g.scene(), 175)
    b.has("le miracle de l'Antherique", rows, "Le miracle de l'Antherique")
    b.has("la fin annonce le SUCCES COMPLET", rows, "SUCCES COMPLET")
    b.eq("la fin est terminale", g.choices(rows), [])


@scenario("fin_158", "Fin 158 : la carte rendue a Pompatarte",
          forge=dict(scene=56, title="AVANT LA FIN 158", hab=(11, 12),
                     end=(16, 22), cha=(7, 11), gold=90, visited=(1, 56)))
def sc_fin_158(g, b):
    g.p.wait_for("LANGUE")
    g.p.keys("F")
    g.p.wait_for("LE MARAIS AUX SCORPIONS")
    g.press("L")
    rows = g.press("9")
    b.eq("la sauvegarde forgee ouvre chez Pompatarte", g.scene(), 56)
    b.has("il reclame la carte de Courbensaule", rows, "Courbensaule")
    rows = g.choose("A")
    b.eq("« oui » mene a la page 158", g.scene(), 158)
    b.has("la carte est complete", rows, "la carte est complete")
    b.eq("la fin est terminale", g.choices(rows), [])


@scenario("fin_358", "Fin 358 : les Amulettes payees par Stratagus",
          forge=dict(scene=226, title="AVANT LA FIN 358", hab=(9, 12),
                     end=(12, 22), cha=(6, 11), gold=15,
                     amulets=("LOUP", "FLEUR", "ARAIGNEE"), visited=(1, 226)))
def sc_fin_358(g, b):
    g.p.wait_for("LANGUE")
    g.p.keys("F")
    g.p.wait_for("LE MARAIS AUX SCORPIONS")
    g.press("L")
    rows = g.press("9")
    b.eq("la sauvegarde forgee ouvre a la porte de la tour", g.scene(), 226)
    b.eq("trois amulettes ont ete rapportees", len(g.amulets()), 3)
    letters = g.choices(rows)
    b.check("seule la branche « trois ou plus » porte une lettre (CA 3 6)",
            letters == ["C"], repr(letters))
    rows = g.choose("C")
    b.eq("elle mene a la page 194", g.scene(), 194)
    rows = g.choose("B")                 # exiger d'abord le paiement -> 207
    b.eq("exiger le paiement mene a la page 207", g.scene(), 207)
    or_avant = g.hero()["gold"]
    b.check("GA 500 paie 500 pieces par amulette",
            or_avant >= 15 + 1500, "or=%d" % or_avant)
    b.eq("les amulettes ont ete remises", g.amulets(), [])
    rows = g.choose("A")
    b.eq("on quitte la tour sur la fin 358", g.scene(), 358)
    b.has("mission accomplie", rows, "Mission accomplie")
    b.eq("la fin est terminale", g.choices(rows), [])


# ── (i) La musique ────────────────────────────────────────────────────────

@scenario("musique", "La Mockingboard joue, et change d'air par clairiere")
def sc_musique(g, b):
    m = g.music()
    b.check("music_detect a trouve la Mockingboard",
            m["slot"] != 0,
            "mb_slot=%d -- POM2 la met dans le slot de state.cfg" % m["slot"])
    if m["slot"] == 0:
        return
    g.goto(195)                                  # clairiere 1, MU MARAISUD.MB
    m1 = g.music()
    b.check("une musique joue sur la page 195", m1["playing"] == 1,
            "playing=%d" % m1["playing"])
    b.check("elle porte un nom", bool(m1["cur"]), repr(m1["cur"]))
    c1 = m1["cursor"]
    time.sleep(0.6)
    b.check("le curseur de lecture avance", g.music()["cursor"] != c1,
            "cur reste a %d" % c1)
    # Une autre page de la MEME clairiere : le nom ne doit pas changer.
    same = g.goto(208)
    m2 = g.music()
    b.eq("a l'interieur d'une clairiere, l'air ne change pas", m2["cur"], m1["cur"])
    # Une clairiere differente : le nom change.
    g.goto(78)                                   # Courbensaule
    m3 = g.music()
    b.check("en changeant de clairiere, l'air change",
            m3["cur"] != m1["cur"], "%r partout" % m3["cur"])
    b.check("et il joue toujours", m3["playing"] == 1, "playing=%d" % m3["playing"])
    b.eq("la zone memorisee suit l'air courant", m3["zone"], m3["cur"])


# ── Le balayage large : ce que la porte cachee rend possible ──────────────

@scenario("balayage", "Balayage : trente pages tirees du corpus, sans erreur")
def sc_balayage(g, b):
    pages = [1, 9, 12, 22, 41, 44, 58, 79, 87, 91, 92, 105, 118, 120, 135,
             138, 144, 152, 155, 156, 157, 170, 183, 191, 195, 204, 206, 226,
             240, 256, 275, 290, 304, 320, 336, 350, 361, 374, 387, 400]
    bad = []
    for p in pages:
        rows = g.goto(p, hab=12, end=24, cha=12, gold=50,
                      stones={"FEU": 2, "CHANCE": 2},
                      objects=("ANNEAU", "AIMANT", "BAIE", "GRAINES"),
                      amulets=("LOUP",))
        txt = "\n".join(rows)
        if "Erreur" in txt or "errno=" in txt:
            bad.append((p, "message d'erreur"))
        elif any(len(r) != 80 for r in rows):
            bad.append((p, "ligne hors format"))
    b.check("les %d pages du balayage se chargent sans erreur" % len(pages),
            not bad, repr(bad[:5]))
    b.check("la barre de titre reste lisible apres le balayage",
            bool(BAR_FR.search(g.screen()[0])), repr(g.screen()[0][:60]))


# ═══════════════════════════════════════════════════════════════════════════
# 6. Le lanceur
# ═══════════════════════════════════════════════════════════════════════════

def run_one(spec, args, sym, workdir):
    """Un scenario = un emulateur neuf sur une copie neuve du disque.

    C'est plus lent qu'un snapshot, mais c'est la seule facon d'etre sur qu'un
    scenario n'herite pas de l'etat du precedent -- et le cache de blocs de
    POM2 rend de toute facon obligatoire une relance apres chaque patch du
    .hdv (DOCS/AUTOMATISATION.md, §1.3).
    """
    b = Bench(spec["name"], args.verbose)
    hdv = os.path.join(workdir, "SCOSWAMP-%s.hdv" % spec["name"])
    shutil.copyfile(args.hdv, hdv)
    if spec["forge"]:
        blob = forge_save.build(**spec["forge"])
        install_save(hdv, blob, slot=9)
    pom = Pom2(hdv, port=args.port, speed=args.speed, pom2=args.pom2)
    t0 = time.time()
    try:
        pom.start()
        g = Game(pom, sym)
        if not spec["forge"] and spec["name"] not in ("demarrage",):
            g.boot("F")
        spec["fn"](g, b)
    except Exception as exc:
        b.failures.append(("scenario interrompu", "%s: %s" % (type(exc).__name__, exc)))
        print("      X scenario interrompu -- %s: %s" % (type(exc).__name__, exc))
        if args.verbose:
            import traceback
            traceback.print_exc()
    finally:
        if args.keep:
            print("      (--keep : POM2 reste ouvert sur le port %d)" % args.port)
        else:
            pom.stop()
            os.unlink(hdv)
    b.seconds = time.time() - t0
    return b


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=DEFAULT_PORT,
                    help="port --ai-control (defaut %d ; 6503-6506 et 6510 "
                         "sont pris)" % DEFAULT_PORT)
    ap.add_argument("--hdv", default=HDV_SRC,
                    help="l'image de reference ; elle n'est JAMAIS modifiee")
    ap.add_argument("--pom2", default=POM2, help="le binaire de l'emulateur")
    ap.add_argument("--src", default=SRCDIR, help="ou lire build.map et build.lbl")
    ap.add_argument("--speed", type=int, default=200000,
                    help="cycles par trame (17045 = 1x)")
    ap.add_argument("--only", action="append", default=[],
                    help="ne lancer que ces scenarios (repetable)")
    ap.add_argument("--keep", action="store_true",
                    help="laisser le dernier emulateur ouvert pour regarder")
    ap.add_argument("--list", action="store_true", help="lister les scenarios")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    if args.list:
        for s in SCENARIOS:
            print("  %-14s %s" % (s["name"], s["title"]))
        return 0

    if not os.path.exists(args.hdv):
        print("Image absente : %s\n  make -C SCOSWAMP/SRC hdv" % args.hdv)
        return 2
    if not os.path.exists(args.pom2):
        print("Emulateur absent : %s" % args.pom2)
        return 2

    try:
        sym = Symbols(args.src)
    except SymbolError as e:
        print("Adresses : %s" % e)
        return 2
    print("SCOSWAMP -- banc de traversee")
    print("  image    %s" % args.hdv)
    print("  _app     $%04X   (AppState %d octets)" % (sym["_app"], APP_SIZE))
    print("  _state   $%04X   _visited $%04X   _seen $%04X"
          % (sym["_state"], sym["_visited"], sym["_seen"]))
    print("  music    _music_buf $%04X   mb_slot $%04X"
          % (sym["_music_buf"], sym.sym.get("mb_slot",
                                            sym["_music_buf"] + 3584)))
    print("")

    todo = [s for s in SCENARIOS if not args.only or s["name"] in args.only]
    if args.only and not todo:
        print("Aucun scenario ne correspond a %r" % args.only)
        return 2

    workdir = tempfile.mkdtemp(prefix="scoswamp-playtest-")
    results, total_ok, total_ko = [], 0, 0
    try:
        for i, spec in enumerate(todo, 1):
            print("[%d/%d] %s -- %s" % (i, len(todo), spec["name"], spec["title"]))
            b = run_one(spec, args, sym, workdir)
            results.append(b)
            total_ok += b.ok
            total_ko += len(b.failures)
            print("      %d assertions, %d echecs, %.1f s"
                  % (b.ok + len(b.failures), len(b.failures), b.seconds))
    finally:
        if not args.keep:
            shutil.rmtree(workdir, ignore_errors=True)

    print("")
    print("=" * 72)
    print("%d assertions passees, %d en echec, sur %d scenarios"
          % (total_ok, total_ko, len(results)))
    if total_ko:
        print("")
        for b in results:
            for label, detail in b.failures:
                print("  %-14s %s%s" % (b.name, label,
                                        ("  [%s]" % detail) if detail else ""))
    return 1 if total_ko else 0


if __name__ == "__main__":
    sys.exit(main())
