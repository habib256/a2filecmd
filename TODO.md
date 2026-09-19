# A2 File Cmd — feuille de route

[0.8.9](https://github.com/habib256/a2filecmd/releases/tag/v0.8.9)
([CHANGELOG](CHANGELOG.md)). Mini (II+ 48 Ko, DOS 3.3) et ProDOS
(IIe 128 Ko), même numéro. `make mini` ne partage pas `src/a2fc.c`.

Préserver les données prime. Ne pas relever les plafonds
([MEMORY-BUDGETS.md](docs/MEMORY-BUDGETS.md)) ; MAIN 65C02 ≥ 256 octets
(457 après la passe du 18 septembre). **💾** = lecteurs physiques.

Deux niveaux de preuve : **qualifié POM2** et **qualifié sur matériel**.
Un chantier se ferme au premier ; le fer reste ouvert à part, sans
bloquer le reste — mais c’est lui, maintenant.

## Maintenant : le fer 💾

POM2 ne remplace pas le lecteur. La marche à suivre, les images d'essai et
ce que chaque écran doit montrer :
[HARDWARE-CHECKLIST.md](docs/HARDWARE-CHECKLIST.md) et
`python3 tools/hw_media.py --out dist/hw`.

- [ ] **Mini sur II+** — déjà un défaut d’écran vu sur machine ; le reste
  des écritures n’est pas qualifié.
- [ ] **DOSWRITE** sur disque réel.
- [ ] **FIXIT/REPAIR en AUX** — volume > 4 096 blocs, vrai IIe et //c,
  `/RAM` relu après.
- [ ] **REPAIR** sur une disquette réellement abîmée.
- [ ] **IIgs** — premier boot (SmartPort, `$C000`) ; documenter Disk II.

Puis **un seul** : NIBCOPY (IIe et //c, un et deux lecteurs, 300 tr/min
et accélérateur ; ensuite reprise de piste **ou** `.NIB`, pas les deux,
pas de 3½ avant) **ou** ADTPro blocs (dossiers, CRC, NAK).

## Formats — seulement s’il reste des octets

OPEN a 28 octets en 6502 (43 en 65C02), UNSHRINK ~900, SHAPES est plein.
Un format nouveau n’entre que s’il tient sans relever un plafond, avec
oracle hôte et banc POM2. Inventaire CiderPress II du 17 septembre 2026 :

- [ ] **LZC 12 bits dans UNSHRINK** (NuFX 4, et 5 quand son en-tête dit
  ≤ 12 bits). Décodeur de référence écrit et vérifié :
  `tools/lzc_ref.py`, identique octet pour octet à `/usr/bin/compress`
  tant que la table n'est pas pleine, et relisant tous ses flux 12 à 16
  bits, codes CLEAR compris (`make test`). Reste le 6502 : le cœur
  actuel tient en $1B00-$1F59, PREFIX commence à $2000 — 166 octets de
  marge —, donc le décodeur LZC doit être un second cœur stocké ailleurs
  dans la surcouche et recopié en AUX $1B00 selon le format du thread.
- ~~NuFX 5 en 16 bits~~ : hors de portée, et pas faute d'octets. La table
  demanderait 65 536 préfixes de deux octets plus 65 536 suffixes, 192 Ko :
  la machine en a 128. Seul un thread de format 5 dont l'en-tête `compress`
  annonce 12 bits ou moins est décodable.
- ~~NuFX 1, Squeeze~~ : laissé. nufxlib, qui l'a écrit, dit que le format
  n'a jamais servi (« has never actually been used ») et que ni P8
  ShrinkIt ni II Unshrink ne le lisent correctement. Aucun échantillon
  nulle part dans le corpus. UNSQ lit déjà le Squeeze autonome (`.QQ`).
- [ ] AppleWriter / Merlin (textes à bit haut).
- [ ] Bordures Print Shop, Beagle Compress — pas de spec, laisser.

Hors de portée : Teach (fichiers étendus), a2dgrx (pas de fichier propre).
Faits le 17 : ARLEQUIN, MACPAINT, AWDATA, DiskCopy, UNWRAP, SCIIBIN,
SHAPES, FONTVIEW hi-res, BASLIST, Magic Window, UNSQ. Fait le 18 : le
routage Retour `.QQ` / `.ACU` / `.BA3` et le type `$09`, la place prise
dans OPEN même (`ends` fondu dans `by_suffix`, la queue de `file_viewer`
en table).

## Chemins d'écriture neufs

Demandés le 18 septembre 2026. Chacun est un chantier, pas une passe ;
tous relèvent d'AGENTS.md avant tout le reste : cible nommée,
confirmation dans l'interface avant la première écriture, relecture,
essais de régression sur les erreurs de lecture, d'écriture et de
fermeture, et jamais d'atomicité promise que ProDOS ne donne pas.

- [x] **DOS33W — suppression et renommage** sur un vrai disque DOS 3.3.
  `src/plugins/dos33w.c` (DISKTOOLS), la couche volume partagée dans
  `src/plugins/dos33_fs.h`, `tools/test_dos33w.py` dans `make test`.
  Qualifié hôte ; **ni banc POM2 ni matériel**.
- [x] **DOS33W — remplacement**, livré le 19 septembre dans sa propre
  surcouche `src/plugins/dosrepl.c` (DISKTOOLS et XL), 10 essais hôte dans
  `make test`. Marge de fenêtre : 172 octets en 65C02, **74 en 6502**.
  L'ordre des écritures est celui qui ne peut pas perdre le fichier :
  secteurs neufs, écriture, relecture, puis **un seul** secteur de
  catalogue bascule le nom ; l'ancien reste entier jusque-là, donc le
  disque doit porter les deux copies.
  Les octets manquants ne sont pas venus d'`audit()` mais de la façon de
  retenir les secteurs de l'ancien fichier : `claim()` les marque dans une
  carte de 70 octets pendant le parcours que l'audit fait déjà, au lieu de
  reparcourir sa chaîne T/S (`free_chain`, 330 octets de code). −154 de
  code, et la surcouche finit 96 octets plus bas malgré la carte. Marquer
  la carte dans les deux boucles du parcours plutôt que dans `claim()`
  coûtait 169 octets : ne pas refaire.
- [x] **Banc POM2 de DOSREPL** (`bench/dosrepl.py`, port 6913), sur une
  disquette jetable en lecteur 2 : 25/25 sur les deux processeurs. La
  question déclinée qui n'écrit rien, un Applesoft puis TIGER (8 Ko, une
  liste T/S pleine, trente-trois secteurs à réserver avant la bascule)
  remplacés sous leur nom DOS avec leur préfixe exact, les secteurs de
  l'ancien rendus au bitmap et la nouvelle copie ailleurs, le voisin et le
  disque source intacts, un second remplacement qui redonne le même disque,
  et un disque à un secteur près trop plein pour porter les deux copies
  refusé — la disquette est taillée depuis la taille réelle du fichier
  source, pas devinée. Comme pour DOS33W, chaque contrôle éjecte d'abord.
  La panne au milieu d'une écriture reste au banc d'essai hôte
  (`tools/test_dosrepl.py`, qui casse chaque écriture à son tour) : POM2 ne
  sait pas faire échouer un secteur à la demande.
- [x] **Banc POM2 de DOS33W** (`bench/dos33w.py`, port 6912), sur une
  disquette jetable en lecteur 2 : 13/13. Il vérifie les octets du disque,
  pas le message — et POM2 ne réécrit la disquette sur l'hôte qu'à
  l'éjection, donc chaque contrôle éjecte d'abord ; sans cela un « rien
  n'est écrit » aurait laissé passer n'importe quoi.
- [x] **Écriture dans une image** montée. `src/plugins/imgput.c` (IMGPUT,
  DISKTOOLS et XL) copie le fichier sélectionné dans le répertoire qu'un
  panneau a ouvert **dans** une image ProDOS. C'est le second écrivain
  ProDOS : il alloue dans le bitmap de l'image, écrit les blocs de données
  et le bloc d'index, puis l'entrée de répertoire.
  L'ordre est ce qui décide du coût d'une coupure : données d'abord, dans
  des blocs que le bitmap appelle encore libres — une coupure là ne change
  **rien** ; puis le bitmap ; puis l'entrée. Entre les deux derniers, on
  perd de la place et rien d'autre, et le message le dit au lieu de
  prétendre le travail fait. `tools/test_imgput.py` casse chaque écriture
  à son tour et vérifie lequel des deux est arrivé.
  Il a trouvé un vrai trou en chemin : la page de bitmap n'était pas
  relue, si bien qu'une page écrite de travers laissait une entrée nommant
  des blocs déclarés libres — la seule panne qui donne un volume corrompu
  plutôt que de la place perdue. Elle passe maintenant par `put_verified`.
  Marge de fenêtre : 277 octets (6502), 270 (65C02) — trouvés en
  compilant hors du chemin périphérique (`IMAGEIO_NODEVICE` : ni
  `unit_of`, ni `readblk`, ni `writeblk`, 520 octets) et en prenant type,
  aux, accès et date dans l'entrée que le panneau a déjà lue.
  **Limites dites, pas devinées** : au-delà de 128 Ko il faudrait un
  fichier « tree » — refusé ; un répertoire sans emplacement libre est
  refusé (étendre la chaîne est une écriture de plus) ; et il n'y a
  **pas encore de banc POM2**, seulement le banc d'essai hôte.
- [x] **Pascal — lecture.** `src/plugins/pascal.c` (DEVTOOLS) extrait tous
  les fichiers d'un volume UCSD depuis une image, contrat des services de
  fichiers compris ; `tools/pascal_ref.py` est la référence et le
  générateur de fixtures, `tools/test_pascal.py` dans `make test`.
  Vérifié contre le format publié, des volumes synthétiques **et quatre
  vrais disques Pascal d'Asimov** (FORT1, TGP, TK, EXPRESS) : les 46
  fichiers sortent octet pour octet comme `tools/pascal_ref.py` les lit.
  Marge de fenêtre : 1 697 octets.
- [x] **CP/M — lecture.** `src/plugins/cpm.c` (DEVTOOLS) : extensions
  remises en ordre, longueur prise sur le compte de records du dernier
  extent, contrat des services de fichiers. Le décalage de secteurs n'est
  pas deviné — la surcouche essaie les tables candidates et garde celle
  dont le répertoire s'explique ; un mauvais ordre donne un refus, jamais
  des octets faux, et `tools/test_cpm.py` le prouve en lisant des images
  écrites dans chaque ordre sans le lui dire. Marge de fenêtre : 283
  octets. **Confronté à de vrais disques le 19 septembre** (Asimov,
  images/cpm) : la table a été *mesurée* sur eux, les trois premières
  candidates étaient fausses et refusaient tout — comme prévu.
  `CPM2.2(56k).dsk` rend ses 19 fichiers, `CPM MAG #01.DSK` ses 8, et les
  27 sortent identiques octet pour octet à ce que lit `tools/cpm_ref.py`.
  Deux disques sur quatre restent refusés (`CPAM40B.dsk`, `CPM.DSK`) :
  leur répertoire commence ailleurs. À éclaircir si quelqu'un en a besoin.
- ~~CP/M — lecture, l'ancienne difficulté~~ :
  l'ordre des secteurs propre à l'Apple II. Le répertoire (64 entrées de
  32 octets, numéro d'utilisateur, nom 8+3 à bit haut d'attributs, EX/S2
  pour les extensions, 16 numéros de blocs) et le DPB 5¼ (bloc de 1 024,
  128 blocs, 3 pistes réservées, deux blocs de répertoire) sont connus ;
  la table de décalage logique → physique ne l'est pas de façon sûre et il
  n'y a pas d'échantillon pour trancher. Piste : la lecture étant sans
  écriture, on peut essayer les tables candidates et garder celle dont le
  répertoire se valide — un mauvais décalage donne un refus, jamais des
  octets faux. À faire avec un vrai disque sous la main.
- [ ] **Pascal / CP/M — écriture.** Après la lecture, et pas avant.

Une petite surcouche (DELETE, COPY, IMGFS, ATTR, OPEN) ne bouge que si
on doit la modifier : extraire un service, mesurer au lien.

## Plus tard

Favoris de programmes. Médias (PT3 sous pression, Fantavision, ANIMATE).
Disques (journal de coupure sans promettre l’atomicité, DISKIMG, VERIFY,
DIRSORT, BACKUP, images montées, SHRINK). Transferts (XMODEM, VDrive
après ADTPro, TFTP). Confort (DATE, TAGPAT, PASSWORD…). Corpus :
`GISTDATA.hdv`, [SAMPLE-MEDIA.md](docs/SAMPLE-MEDIA.md).

Clos (CHANGELOG) : contrat d’écriture, séquences, FIXIT/REPAIR, Mini
entrelacement et relecture, Commander, grille des tableurs AppleWorks.

## Livraison

[AGENTS.md](AGENTS.md). `/RAM` : confirmer **avant**. Jetables pour les
essais destructifs. Deux CPU. Avant release : `make test`, `make qualify`
(toute la table de `bench/all.py`, `--strict`), `tools/check_images.py`.
