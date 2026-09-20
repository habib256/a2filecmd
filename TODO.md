# A2 File Cmd — feuille de route

[0.9.1](https://github.com/habib256/a2filecmd/releases/tag/v0.9.1)
([CHANGELOG](CHANGELOG.md)). Mini et ProDOS, même numéro ;
`make mini` ne partage pas `src/a2fc.c`.

Préserver les données prime ([AGENTS.md](AGENTS.md)). Ne pas relever
les plafonds ([MEMORY-BUDGETS.md](docs/MEMORY-BUDGETS.md)). Un chantier
se ferme avec un oracle hôte et un banc POM2.

## 0.9.1

Cinq images, plus de disquettes par catégorie : XL 6502, XL 65C02
(processeur **et** ROM enhanced ; souris facultative), 800K complète
sans corpus de démo, 140K essentielle, DOS 3.3.

Fait : phases copie / vérification distinctes, compteur de relecture,
activité des catalogues, annonce de chargement.
Qualification automatisée : **98/98 scénarios au bilan consolidé**,
1 162 tests hôte ; [rapport et limites](docs/QUALIFICATION-0.9.1.md).
MB4c : réveil corrigé et appels souris bloqués si sa ROM est masquée.

- [ ] MAIN 65C02 ≥ 256 octets.
- [ ] À 1 MHz, mesurer les pauses des appels disque bloquants
  (catalogue, copie, vérification, chargement) et les rendre visibles.

## 1.0

Geler les formats. Qualifier les cinq images (`make qualify`, puis
[HARDWARE-CHECKLIST.md](docs/HARDWARE-CHECKLIST.md)). Publier sans
défaut connu qui puisse perdre des données ; limites restantes dites
dans le manuel.

Avant release : `make test`, `make qualify`,
`tools/check_images.py`. `/RAM` : confirmer **avant**. Jetables pour
les essais destructifs. Deux CPU.

## Ensuite

Formats, seulement s’il reste des octets. OPEN a 28 octets en 6502
(43 en 65C02), UNSHRINK ~900, SHAPES est plein. Une petite surcouche
(DELETE, COPY, IMGFS, ATTR, OPEN) ne bouge que si on doit la modifier.

- [ ] **LZC 12 bits dans UNSHRINK** (NuFX 4, et 5 si l’en-tête dit
  ≤ 12 bits). `tools/lzc_ref.py` est dans `make test`. Le cœur actuel
  tient en `$1B00–$1F59` ; PREFIX commence à `$2000`. Le décodeur LZC
  est un second cœur, recopié en AUX `$1B00`.
- [ ] AppleWriter / Merlin (textes à bit haut).

Laissé, pas de spec : bordures Print Shop, Beagle Compress.
Hors de portée : NuFX 5 en 16 bits, Squeeze NuFX, Teach, a2dgrx.

Limites : CPMW un extent (16 Ko) et volume vide refusé ; CPM
`CPAM40B.dsk` / `CPM.DSK` refusés ; PASCALW sans Krunch ; IMGPUT sans
tree (> 128 Ko) ni extension de répertoire.

Plus tard : favoris de programmes ; PT3 sous pression, Fantavision,
ANIMATE ; DIRSORT, BACKUP, SHRINK ; NIBCOPY reprise de piste **ou**
`.NIB` (pas les deux, pas de 3½) ; XMODEM, ADTPro blocs, TFTP ;
PASSWORD ; `GISTDATA.hdv` ; CPMW à plusieurs extents si la fenêtre
se libère.
