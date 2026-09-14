# Consolidation : budgets mémoire

## État après la 0.8.5 (14 septembre 2026)

Réserves au lien, en octets, 65C02/6502 ; ce ne sont pas des sommes :

| Zone | 65C02 | 6502 | Objectif |
| --- | ---: | ---: | --- |
| MAIN (résident, plafond `$BEE0`) | **335** | 779 | 256 sur 65C02 : tenu |
| Carte langage | 34 | 26 | ne pas descendre |
| CATALOG (catalogues DOS 3.3 et images) | 15 | 36 | surcouche de lecture, pas à enrichir |
| LOWRAM | 129 | 154 | — |
| Écart avant la pile C de 192 octets | 363 | 996 | — |
| NAV | 142 | 208 | — |
| DELETE | 409 | 405 | libéré par le parcours résident |
| OPEN | 11 | 43 | ne pas retomber à quelques octets au prochain média |
| IMGFS | 5 | 13 | idem |
| UNSHRINK | 9 | 29 | idem |
| ATTR | 26 | 26 | idem |
| COPY | 54 | 51 | — |
| Mini (sous DOS à `$9600`) | 270 | — | — |

Au lien de la 0.8.5, MAIN 65C02 ne gardait que 23 octets (518 sur 6502) :
DUET, DOSGET, IDENT/FIXTYPES et la sonde DUET du routage avaient consommé
la réserve retrouvée au neuvième incrément du chantier 1. Le reste de ce
document est le journal chronologique de la consolidation, le plus récent
en premier.

Dossiers marqués (chantier 4), 14 septembre 2026 : Espace et Ctrl-T
marquent un dossier ; BATCH accepte l’enregistrement (type de stockage `$D`
vérifié à la relecture) ; MOVE réécrit l’entrée d’un dossier sur le même
volume comme pour un fichier ; vers un autre volume, MOVE, qui connaît les
unités ProDOS, rend la main avec une note commençant par l’octet 2, et le
résident (`move_tree_across`) pose le curseur sur le dossier, efface les
marques et appelle `copy_or_move(1)` : l’arbre est compté, copié, relu
fichier par fichier et sa source effacée seulement si tout est arrivé ; la
réussite se constate par la disparition de la source. Quatre formes
mesurées : dupliquer la logique de V dans le résident et comparer les
volumes par nom coûtait 582 octets (MAIN 8) ; réutiliser `copy_or_move`
ramène l’aide à 205 octets ; la comparaison de volumes coûtait 131 octets
où qu’elle soit (résident ou BATCH, où elle faisait franchir un bloc à
BATCH.PLG et déborder la disquette BOOT) ; la remise par MOVE la supprime.
`move_marked` reste en carte langage, sa chaîne d’annulation passe au
résident. Le moteur de copie et l’état du lot empruntent tous deux
`text_starts` (207 et 279 octets sur 320) : après un déplacement d’arbre,
une phase `X` de BATCH reconstruit les trois chemins depuis les panneaux
(les compteurs, au-delà des 207 octets, survivent) — reconstruire dans le
résident coûtait 70 octets de plus. BATCH.PLG 6502 passe à 2 659 octets,
un bloc de plus sur BOOT ; MENU.PLG rend ce bloc en raccourcissant un
message (3 591 → 3 582 octets, sous 3 584). Réserves : MAIN 335/779, LC
34/26, LOWRAM 129/154, écart avant pile 363/996 ; BOOT à 0 bloc libre.

Lanceur, 14 septembre 2026 : RUN.PLG 6502 passe à 3 734 octets (neuf blocs)
pour épeler la commande de retour ; le lanceur disquette rend le bloc en
tombant à 6 134 octets (douze blocs, dix octets de marge) : noms de mois
abrégés, ligne descriptive retirée sur disquette seulement, deux notes
raccourcies. VOLNAME passe ensuite sur DISKTOOLS : BOOT retrouve 4 blocs
libres. Les tailles encore au bord d’un bloc sont RUN.PLG (3 734/4 096),
MENU.PLG (3 582/3 584), BATCH.PLG (2 659/3 072) et le lanceur (6 134/6 144). Test hôte `tools/test_batch.py` (un dossier traverse le manifeste,
relu comme `$D`), banc `bench/roi.py` (dossier marqué à deux niveaux sur le
même volume puis vers l’autre disque, arbres relus, sources parties).

Parcours d’arbres itératif (chantier 2), 14 septembre 2026 : `count_tree`,
`copy_tree` et `delete_tree` récursifs sont remplacés par un moteur unique
`walk_tree(mode)` dans `src/tree_walk.h`, résident, avec un cadre de trois
octets par niveau dans trois tableaux `lv_base/lv_n/lv_i[TREE_DEPTH]`
(32 niveaux, ce qu’un chemin ProDOS de 64 caractères ne peut dépasser) et
les entrées de chaque niveau empilées dans la réserve de 213 entrées comme
avant. Budget mesuré : quatre formes essayées. Un moteur unique avec les
cadres adressés par pointeur de structure coûtait 423 octets de résident ;
une instance par mode depuis l’en-tête (mode en constante) faisait déborder
DELETE de 268 octets, et les trois instances résidentes ramenaient MAIN à
11 octets — cc65 produit ~450 à 600 octets par copie de la boucle. La forme
retenue (moteur unique, cadres en tableaux d’octets indexés par la
profondeur, aides communes `push_paths`/`pop_paths`) coûte 257 octets de
code et 99 de BSS ; DELETE ne garde que l’appel et gagne 405 octets.
Réserves : MAIN 590/1 037, LOWRAM 131/156, écart avant pile 618/1 254,
DELETE 409/405. Test hôte `tools/test_tree_walk.py` (ordre, bornes,
arrêts sur erreur, dix scénarios sur un système de fichiers simulé) et banc
`bench/tree_safety.py` réécrit : un arbre de 18 niveaux se copie, un arbre
de 20 niveaux s’efface mais sa copie s’arrête proprement (le nom temporaire
`A2FC.COPY` dans le dossier cible dépasse 64 caractères), un chemin de 221
entrées est refusé avant toute écriture.

CATALOG, 14 septembre 2026 : le lecteur de catalogue DOS 3.3
(`read_dos33_panel`, `dos33_type`, 707 + 40 octets de code) puis le parcours
d’un répertoire ProDOS dans une image (`read_image_dir`, `dir_open_image`)
quittent le résident pour une petite surcouche CATALOG, sur BOOT et XL,
chargée à chaque lecture d’un panneau étranger (disque DOS 3.3 réel, image
en ordre DOS, image ProDOS ouverte comme dossier) et mise en cache comme les
autres. `img_open`, `img_read_block` et `dos_read_sector` restent résidents :
IMGFS et DOSGET s’en servent depuis leur propre fenêtre. Quand une image en
ordre DOS n’a pas de répertoire ProDOS à sa racine, la surcouche répond 2
et le résident, seul autorisé à recharger la fenêtre, tente le lecteur
DOS 3.3 ; l’image est fermée par le résident dans tous les cas. Ce que la surcouche ne peut pas faire : être chargée
pendant qu’une autre surcouche a encore du code sur la pile de retour — HELP
relit les deux panneaux, le tri S hébergé par TEXT relit le sien, et un
plugin SDK relit par `api->read_panel` le panneau DOS qu’il vient d’écrire
(DOSWRITE). `load_overlay` pose donc `in_overlay` à chaque chargement ou
succès de cache ; `read_dos33_overlay` diffère alors la lecture (panneau
vide, bit dans `panel_stale`) et `settle_panels`, appelé en tête de la boucle
principale, relit et redessine ce seul panneau — relire l’autre lui ferait
perdre ses marques. `overlay_run` remet `in_overlay` à zéro dès que le point
d’entrée a rendu la main. NAV relit un panneau puis y cherche le dossier quitté
(`nav_select`) : quand cette lecture est différée, le nom est confié à
`reselect` et `settle_panels` le sélectionne après la relecture, sinon Échap
depuis un sous-dossier d’image perdait sa sélection (vu au banc). Coût
résident : 3 octets de BSS, 46/64 octets de code pour ce report, +8 octets
dans MENU pour la liste des surcouches cachées. Gain MAIN net 824/782
octets ;
CATALOG garde 15/36 octets libres, ce qui suffit à une surcouche de lecture
qui n’a pas vocation à grossir. Test hôte `tools/test_catalog_overlay.py`
(différé, direct, chargement refusé, catalogue refusé, « pas un répertoire »
transmis) et banc `bench/catalog_overlay.py` (aide et tri depuis un panneau
DOS puis depuis une image ProDOS et son sous-dossier, octets de l’image
conservés, deux CPU). Les bancs DOSWRITE, DOSIMAGE, catalogues
malformés, smoke et XL passent sur les deux CPU.


UNSHRINK, 13 septembre 2026 : réservation possédée, nettoyage contrôlé,
lectures exactes des threads ignorés, erreurs de flux/fermeture et annulation.
Les opérations de comparaison et lecture des entiers réutilisent les fonctions
`memcmp`/`memcpy` déjà résidentes pour tenir dans la fenêtre inchangée.
UNSHRINK occupe 5 367/5 347 octets (65C02/6502), soit 9/29 octets libres
sous `$3000`. Aucun BSS ajouté ; l'état à `$3000` est borné à 512 octets
par une assertion de compilation. MAIN garde 60/546 octets, LC 31/24,
LOWRAM 277/302, écart avant pile 88/763 ; pile C toujours de 192 octets.
Le résident 6502 prend 12 octets supplémentaires, le 65C02 est inchangé.
Tous les contrôles de disposition restent actifs.

Audit des chaînes DOS, 13 septembre 2026 : ajout du numéro logique attendu
pour les listes T/S, soit deux octets de BSS par moteur. DOSWRITE : fichiers
7 142/7 219, BSS 1 994/1 995, réserves 336/258 octets (65C02/6502).
DOSPUT : fichiers 7 175/7 265, BSS 1 754/1 755, réserves 543/452 octets.
Pas de nouveau tampon, d'AUX ni de récursion ; pile et plafonds inchangés.
Le vrai moteur compilé pour les deux CPU refuse les chaînes malformées sous
sim65 sans écrire de bloc et accepte un fichier existant sur plusieurs listes.

Erreurs de flux en écriture, 13 septembre 2026 : COPY et EDIT vérifient
`ferror` avant de fermer le temporaire, même après un compte d'octets complet.
Réserves COPY 54/51 et EDIT 97/75 octets (65C02/6502). Aucun BSS ajouté ;
réserves résidentes et pile de 192 octets inchangées par cette correction.

Chargeur de surcouches, 13 septembre 2026 : lecture et fermeture contrôlées,
refus des corps vides ou trop grands, restauration des panneaux après échec
d'un grand chargement. Le menu vide son résultat avant chargement pour éviter
la réexécution d'une ancienne commande. Réserves finales 65C02/6502 : MAIN
128/627, LC 38/31, LOWRAM 281/306, écart avant pile 156/844. La pile reste à
192 octets et aucun plafond n'est changé. Le contrôle de fin utilise `fread`
déjà résident. POM2 : 6/6 contrôles sur chaque CPU, dont le motif sous la pile,
la mémoire auxiliaire et l'intégralité du volume jetable après sauvegarde.

Écriture DOS physique et images, 13 septembre 2026 : DOSWRITE utilise le
slot Disk II sélectionné, avec signature ROM et protection matérielle.
DOSIMAGE prépare/installe le temporaire ; DOSPUT partage le moteur DOS.
Appels successifs, sans chargement imbriqué ni AUX, avec fichiers fermés
entre phases. L'allocation est un bitmap de 70 octets au lieu de 260 mots.
La préparation conserve offset, résultat, CRC-32 et longueur dans 12 octets
du tampon `input` résident ; le chemin est reconstruit après chaque chargement.

| Surcouche | Fichier 65C02/6502 | BSS 65C02/6502 | Libre sous `$4000` |
| --- | ---: | ---: | ---: |
| DOSWRITE | 7 114 / 7 192 | 1 992 / 1 993 | 366 / 287 |
| DOSPUT | 7 147 / 7 238 | 1 752 / 1 753 | 573 / 481 |
| DOSIMAGE | 6 954 / 7 087 | 653 / 654 | 1 865 / 1 731 |

Réserves résidentes : MAIN 266/769, LC 38/31, LOWRAM 282/307, écart avant
pile 294/986 ; pile inchangée à 192 octets. Les textes privés IMAGE et
UNSHRINK sont dans leurs surcouches ; le message RAM reste en LC permanente.
IMAGE garde 66/69 octets, UNSHRINK 52/67, MENU 2 111/2 054. Aucun plafond ni
contrôle de disposition n'est désactivé. LC reste sous la réserve de travail
visée et ne doit pas accueillir une nouvelle fonctionnalité sans libération.
Le banc DOS protège aussi la zone sous la pile par un motif contrôlé après
copie. Le CRC-32 de l'image d'origine utilise une table de 1 Ko pour éviter
huit décalages C 32 bits par octet sur 6502.
Le contrôle final compare aussi les octets hors secteurs modifiés à l'original.
Les diagnostics transitoires du moteur interne sont portés par son résultat,
puis affichés par DOSIMAGE. Celui-ci conserve les 64 octets de l'en-tête 2MG
validé pour détecter une modification pendant la confirmation.


Finalisation DISKIMG, 13 septembre 2026 : la réservation exclusive directe
et la finalisation commune aux modes R/W/O rendent 50/39 octets à DISKIMG
(65C02/6502), réserves 369/313. `DiskImg` occupe 200 octets à `$3E00`, avec
assertion sur les 512 disponibles ; son nouveau champ de propriété n'ajoute
pas de BSS résident. MAIN 272/782, LC 80/73, LOWRAM 282/307 et écart avant
pile 300/999 inchangés. Le helper de finalisation garde un octet de résultat
pendant les fermetures/nettoyages ; pas de récursion ni de chargement imbriqué.
Les deux liens gardent leurs plafonds et la pile de 192 octets. Validation :
32 tests ciblés et sept images ProDOS contrôlés.

DOSWRITE et retour aux volumes, 13 septembre 2026 : surcouche 6 773/6 838
octets (65C02/6502), BSS 2 433/2 434, fin `$3EF5`/`$3F37`, soit 266/200
octets libres sous `$4000`. Locaux statiques, aucune récursion ni AUX ;
appels API par trampoline sans chargement imbriqué. La pile reste à 192 octets.
Le routage C et la remise à zéro du mode DOS coûtent du résident ; des
textes privés déplacés dans leurs surcouches et deux noms/diagnostics placés
en LC maintiennent MAIN à 272/782 octets libres. LC 80/73, LOWRAM 282/307,
écart avant pile 300/999 ; COPY 69/66, EDIT 116/96, DISKIMG 319/274,
MENU 2 181/2 124. Aucun plafond relevé, deux architectures compilées.
Validation : 102 tests ciblés, 15 contrôles POM2 par CPU et sept images
ProDOS contrôlées.

Extraction Binary II contrôlée, 13 septembre 2026 : coût BINARY2 238/247
octets (65C02/6502), réserves 1 694/1 709. MAIN 281/791, LC 117/110,
LOWRAM 282/307 et écart avant pile 309/1 008 inchangés. Les locaux restent
sur la pile : suppression du compteur de lecture et réduction du remplissage
à un octet compensent le pointeur de diagnostic, la propriété et le compteur
d'extraits élargi. Aucun BSS supplémentaire, récursion ou chargement imbriqué.
Pile de 192 octets et plafonds conservés aux deux liens. Validation :
56 tests ciblés et reconstruction/contrôle des sept images ProDOS.

Transaction commune EDIT, 13 septembre 2026 : coût EDIT 110/116 octets
(65C02/6502), réserves 138/118. MAIN 281/791, LC 117/110, LOWRAM 282/307,
écart avant pile 309/1 008 et COPY 79/76 inchangés. La transaction est
compilée dans EDIT ; ses sept octets d'arguments restent empilés pendant
les renommages, sans récursion ni chargement imbriqué. Aucun BSS ajouté,
plafonds et pile de 192 octets inchangés. Les deux liens, 48 tests ciblés
et les sept images ProDOS sont validés.

Nettoyage contrôlé EDIT, 13 septembre 2026 : EDIT coûte 62/64 octets
(65C02/6502) et conserve 248/234 octets libres. Le remplacement du diagnostic
littéral « Save » libère cinq octets MAIN : réserves 281/791, écart avant
pile 309/1 008. LC 117/110, LOWRAM 282/307 et COPY 79/76 inchangés.
Le helper EDIT garde deux octets d'argument pendant suppression/diagnostic,
sans récursion ni nouveau local statique. Les deux liens conservent tous
les plafonds et la pile de 192 octets ; 42 tests ciblés et sept images
ProDOS contrôlés.

Localisation des textes de surcouches, 13 septembre 2026 : neuf tableaux
nommés dans EDITRO, MENURO, BINARY2RO et UNSHRINKRO remplacent des littéraux
que cc65 plaçait dans RODATA résident. Gain MAIN de 127 octets sur chaque
CPU : réserves 276/786 octets (65C02/6502), objectif de 256 retrouvé.
Écart avant pile 304/1 003 ; LC 117/110 et LOWRAM 282/307 inchangés.
Réserves des surcouches concernées : EDIT 310/298, MENU 2 190/2 133,
BINARY2 1 932/1 956 et UNSHRINK 86/101. COPY reste à 79/76.
Les textes sont consommés pendant leur surcouche ou copiés dans `note`
avant son déchargement ; aucun pointeur ne lui survit. Aucun appel ni
local supplémentaire, aucune écriture AUX et aucun changement du protocole
de fichiers. Les contrôles des deux liens gardent tous les plafonds et
la pile de 192 octets. Validation : 24 tests C de copie/édition, 15 tests
du contrôle de disposition et reconstruction/contrôle des sept images ProDOS.

Publication COPY par temporaire, 13 septembre 2026 : réserves COPY 79/76
octets, MAIN 149/659, LC 117/110, LOWRAM 282/307, écart avant pile 177/876
(65C02/6502). MAIN coûte 107 octets sur chaque CPU et le BSS un octet ;
le chemin temporaire supplémentaire tient dans `CopyState` (204 octets sur
les 320 de `text_starts`). La variante de transaction liée à CP évite ses
sept octets d'arguments empilés ; la profondeur des appels reste bornée,
sans récursion ni chargement imbriqué. Les deux liens passent sans relever
les plafonds ni réduire la pile de 192 octets. La réserve MAIN 65C02 est
cependant sous l'objectif de 256 : marge à regagner avant d'enrichir encore.

Finalisation COPY résidente, 13 septembre 2026 : COPY passe de 1 247/1 255
à 1 164/1 169 octets (65C02/6502), soit 116/111 octets libres dans sa fenêtre
de 1 280. Le résident absorbe nettoyage, restauration et compteurs : MAIN
conserve 256/766 octets (coût net 79/84), écart avant pile 284/983. LC et BSS
sont inchangés ; LOWRAM conserve 283/308 octets. La finalisation remplace
la vérification dans la chaîne d'appels, sans ajouter de niveau récursif ;
la réservation directe retire le détour par `new_output`. Pile de 192 octets
et plafonds de toutes les surcouches conservés sur les deux liens.

Réservation résidente/BATCH commune, 13 septembre 2026 : CODE résident
+30/+35 octets (65C02/6502), BATCH -20/-20 et LOWBSS -2/-2. Il s'agit d'un
contrat de résultat supplémentaire ; le résident ne gagne pas de code dans
cet incrément. Réserves après lien : MAIN 335/850, LC 117/110, LOWRAM 283/308,
écart avant pile 363/1 067, BATCH 2 817/2 834. COPY conserve 33/25 octets de
marge et demande toujours un chantier séparé. La nouvelle fonction résidente
garde deux octets d'argument pendant `open`/`close`, sans récursivité ni
chargement de surcouche. Les plafonds et la pile de 192 octets sont inchangés.

Migration GOTO vers l'installation commune, 13 septembre 2026 : fichier
4 969/4 953 octets (+157/+164), BSS 262/263 octets (+1), fin
`$2F6E`/`$2F5F` (65C02/6502). Réserve 145/160 octets sous `$3000`, sans
empiéter sur LIST (`$3000`) ou TEXT (`$3400`). La transaction commune garde
sept octets d'arguments pendant le renommage, sans récursivité ni chargement
imbriqué. Les deux liens respectent les limites d'origine et la pile de
192 octets ; les autres plugins restent identiques octet pour octet.

Installation commune SYNC/conversions, 13 septembre 2026 : les appels API
compacts de SYNC compensent l'ajout des diagnostics et de l'arrêt de
récupération. Le premier essai dépassait la fenêtre de 45 octets sur 65C02 ;
aucun plafond n'a été relevé. Bilan final (65C02/6502) : SYNC 6 732/6 755
octets, soit -730/-728 ; BSS 1 746/1 747 (+1 pour l'indicateur), fin
`$3C1D`/`$3C35`, réserve 994/970 octets sous `$4000`. TXTCONV ajoute 66/79
octets (6 017/6 036), IMGCONV 57/71 (6 814/6 916), leurs BSS inchangés.
La fonction d'installation garde sept octets d'arguments sur la pile pendant
le transport de renommage ; elle est non récursive. Les contrôles natifs des
deux éditions conservent la pile de 192 octets et toutes les limites de lien.
Les autres plugins sont identiques octet pour octet.

Nettoyage et restauration des conversions, 13 septembre 2026 : TXTCONV ajoute
243/237 octets et IMGCONV 190/184 octets (65C02/6502), messages compris.
Leurs fichiers occupent désormais 5 951/5 957 et 6 757/6 845 octets.
Le BSS reste inchangé : 592/593 et 730/731 octets ; fins respectives
`$348E`/`$3495` et `$383E`/`$3897`, sous `$4000`. Le nettoyage ajoute un
argument de deux octets sur la pile pendant l'appel, sans récursivité ;
la chaîne de restauration reste de même profondeur. Les autres plugins
sont identiques octet pour octet. Les plafonds et la pile de 192 octets
restent en vigueur sur les deux constructions.

Extraction CREATE des plugins, 13 septembre 2026 : TXTCONV passe de
5 673 à 5 708 octets sur 65C02 et de 5 687 à 5 720 sur 6502. BSS inchangé
(592/593 octets), fin BSS `$339B`/`$33A8`, soit 3 172/3 159 octets libres
avant `$4000`. Le nouvel appel garde six octets d'arguments sur la pile C
pendant CREATE ; il n'est pas récursif et ne charge aucune surcouche.
Les autres plugins restent identiques octet pour octet, comme le résident
et ses budgets. Aucun plafond ni réserve de pile n'est modifié.

Premier relevé du 12 septembre 2026, code natif de `af84617`, après reconstruction
forcée des deux architectures. `tools/check_layout.py` affiche maintenant les
réserves à chaque lien réussi, en complément des contrôles bloquants existants.
Les chiffres ci-dessous sont un point de départ, pas des constantes à recopier
dans un futur rapport de qualification.

## Mesures et objectifs du premier chantier

Les réserves sont en octets. Les objectifs sont des seuils de travail proposés,
pas des garanties déjà obtenues ni des plafonds assouplis.

| Zone | 65C02 | 6502 | Réserve visée sur chaque architecture |
| --- | ---: | ---: | ---: |
| MAIN, jusqu'à `$BEE0` | 5 | 542 | ≥ 256 |
| Carte langage, jusqu'à `$E000` | 0 | 4 | ≥ 128 |
| LOWRAM, BSS compris, jusqu'à `$1B00` | 290 | 315 | ≥ 256 |
| Espace entre code persistant et pile C | 33 | 759 | ≥ 128 |
| BSS FORMAT, jusqu'au tampon `$3E00` | 147 | 147 | ≥ 128 |

La pile C réserve 192 octets : l'espace avant la pile ne mesure **pas** sa
consommation dynamique et ne justifie pas de réduire sa taille. MAIN contient
aussi le code ONCE jetable ; ses octets libres ne s'ajoutent pas à cet espace.
Les surcouches se recouvrent et leurs réserves ne s'additionnent pas non plus.

| Surcouche liée au résident | 65C02 | 6502 |
| --- | ---: | ---: |
| BATCH | 2797 | 2814 |
| NAV | 230 | 296 |
| OPEN | 74 | 110 |
| COPY | 33 | 25 |
| FORMAT | 428 | 428 |
| IMAGE | 113 | 116 |
| TEXT | 61 | 33 |
| HEX | 49 | 42 |
| DELETE | 4 | 3 |
| HELP | 219 | 183 |
| RUN | 2190 | 2202 |
| ATTR | 26 | 26 |
| EDIT | 370 | 358 |
| MENU | 2241 | 2184 |
| DISKIMG | 328 | 283 |
| IMGFS | 5 | 13 |
| DOS33 | 59 | 84 |
| UNSHRINK | 122 | 137 |
| BASLIST | 1863 | 1856 |
| COMPARE | 86 | 111 |
| SEARCH | 335 | 338 |
| BINARY2 | 1968 | 1992 |
| AWP | 216 | 197 |

Viser au moins 64 octets dans chaque petite surcouche modifiée ; traiter DELETE,
IMGFS, COPY et ATTR en priorité avant de les enrichir. Les plugins SDK liés
séparément ne figurent pas dans ce relevé : leurs limites code/BSS et tampons
restent imposées par leurs configurations de lien, à contrôler aussi lors des
extractions. BINARY2 utilise ici sa grande fenêtre sur les deux architectures.

## Premier gain : diagnostics résidents

Les diagnostics ProDOS sont extraits dans `src/errors.h`, toujours en carte
langage. Une table de douze codes remplace le switch, et le diagnostic n'est
recherché qu'une fois par affichage. Le message sans appelant de l'ancien
lecteur Mockingboard est retiré ; le message « SYS, BIN or BAS only. » rejoint
RUNRO, dont RUN est l'unique utilisateur, sans chargement supplémentaire.

| Zone après modification | 65C02 | 6502 | Évolution |
| --- | ---: | ---: | --- |
| MAIN | 27 | 564 | +22 sur les deux |
| Carte langage | 71 | 74 | +71 / +70 |
| LOWRAM | 287 | 312 | −3 sur les deux |
| Espace avant pile C | 55 | 781 | +22 sur les deux |
| RUN | 2168 | 2180 | −22 sur les deux |

Les trois octets LOWRAM servent à l'indice et au pointeur de diagnostic
(locaux statiques cc65). Les autres surcouches et la réserve BSS FORMAT gardent
leurs marges initiales. Les objectifs MAIN, LC et espace avant pile ne sont
**pas encore atteints** sur 65C02 ; LC reste également sous l'objectif sur 6502.

Le service n'écrit aucun fichier ni volume. Il modifie le compteur d'erreurs
en RAM principale, ses locaux statiques, et l'écran texte 80 colonnes
MAIN/AUX `$0400-$07FF` via conio, sans toucher le stockage du disque `/RAM`.
Le message déplacé reste disponible pendant tout son affichage : `message()`
est résident et ne remplace pas la surcouche RUN.

Les tests exécutent le vrai C pour les 256 valeurs de code ProDOS : douze
messages connus, repli numérique pour tous les autres, contenu exact de la
ligne, compteur et conservation de `_oserror`/`errno`.

Validation locale du lot : `make test`, les deux liens et leurs contrôles,
construction des sept supports puis `tools/check_images.py` passent. POM2
valide l'amorçage BOOT sur 6502, les 11 contrôles XL sur 65C02 et mesure
92 octets de pile utilisés sur les 192 réservés dans `bench/memory.py`.
Ces scénarios ne prouvent pas une borne exhaustive pour tous les parcours.

### Après l'extension du lanceur à Integer BASIC

Le chantier demandé ensuite ajoute `src/launch.h`, toujours dans RUN, et
`INTBASIC.SYSTEM` sur DEVTOOLS/XL. Les chemins de lancement vivent à
`$3400-$347F`, séparés du tampon de configuration `$3000-$33FF` ; des contrôles
de taille à la compilation empêchent leur recouvrement. Aucun plafond n'est
relevé. Deux messages de sélection et deux libellés d'erreur sont placés en LC
pour garder RUN dans sept blocs sur la disquette BOOT 6502.

| Réserve du lien après extension | 65C02 | 6502 |
| --- | ---: | ---: |
| MAIN | 62 | 593 |
| Carte langage | 8 | 11 |
| LOWRAM | 280 | 305 |
| Espace avant pile C | 90 | 810 |
| RUN | 1781 | 1795 |
| OPEN | 83 | 119 |

BOOT occupe les 280 blocs : l'échec de sauvegarde d'une nouvelle configuration
y reste signalé avant de proposer de lancer quand même le programme. Les
objectifs de réserve restent ouverts, particulièrement la carte langage.

## Deuxième lot : affichage et saisie

Le lot suivant part de `68c39f5`. Une table compacte remplace le `switch` des
types de fichiers. Un seul en-tête sert aux trois tris ; l'étoile est ajoutée
à sa colonne d'origine. La ligne d'information partage son préfixe entre
fichiers ProDOS et fichiers dans une image. Les questions utilisent `cputs`
et `cputc` pour leur texte fixe, avec les mêmes réponses admises.

`src/display.s` remplace le parseur de barre de touches et la conversion
hexadécimale : mêmes conventions cc65 sur 6502/65C02 et même interface pour
les plugins. Le parseur recharge ses pointeurs après les appels conio ; ses
quatre octets d'état restent résidents. Aucune nouvelle surcouche n'est chargée.

| Réserve après ce lot | 65C02 | 6502 | Gain 65C02 / 6502 |
| --- | ---: | ---: | ---: |
| MAIN | 290 | 835 | +228 / +242 |
| Carte langage | 172 | 169 | +164 / +158 |
| LOWRAM | 281 | 306 | +1 / +1 |
| Espace avant pile C | 318 | 1052 | +228 / +242 |
| BSS FORMAT | 147 | 147 | inchangé |

Les objectifs initiaux sont atteints sur les deux architectures. Les plafonds,
la réserve de pile de 192 octets et les fenêtres des surcouches restent
inchangés. Les réserves de ces dernières n'évoluent pas. BOOT gagne un bloc
libre, et la disquette de banc enhanced passe de huit à neuf blocs libres.

### Écritures et qualification

Ces services ne font aucune opération de fichier ou de volume. Ils écrivent
leurs variables en MAIN, les registres temporaires cc65 en page zéro et
l'écran texte MAIN/AUX `$0400-$07FF`. La saisie écrit dans `input`, comme avant.
La ligne d'information utilise `copy_buf` en MAIN, désormais aussi pour les
fichiers dans une image : ses appelants ont terminé la lecture des répertoires
avant l'affichage. Le préfixe fait au plus 66 caractères, le texte complet
84 avant troncature à 79 ; le tampon en contient 512. Le disque `/RAM` n'est
pas utilisé comme réserve de mémoire par ces services.

`tools/test_display.py` exécute le C réel pour les 256 types, les trois tris
sur les deux panneaux, les attributs maximaux, les limites de ligne/tampon,
les saisies et les 256 touches de confirmation (seuls Y/y, N/n et Échap
terminent la question). Le test de style des questions reste dans
`tools/test_ui.py`. Sur sim65, le véritable assembleur est comparé à l'ancien
parseur C, texte et vidéo inverse compris, avec passage de page et appel par
le pointeur de fonction des plugins. Les 65 536 valeurs hexadécimales sont
vérifiées sur chacun des deux processeurs.

Validation locale : `make test`, les deux constructions natives et la relecture
des sept supports passent. POM2 valide les 11 contrôles XL sur 6502. Le parcours
`bench/memory.py` sur enhanced (visionneuses, édition abandonnée, copie
récursive sur volumes jetables) mesure toujours 92 octets de pile utilisés
sur 192. Cette mesure n'est pas une borne exhaustive pour tous les parcours.

## Suite de la consolidation

Poursuivre avec les contrats de buffers et les services de fichiers sûrs,
en mesurant séparément le gain MAIN et carte langage. Déplacer un service dans
une surcouche demande de vérifier tous ses appelants : charger cette surcouche
peut écraser celle qui appelle le service. Une réserve dans MENU ou BATCH n'est
donc pas automatiquement disponible pour un service partagé.

Avant toute modification native, établir les fichiers, volumes, buffers et
banques écrits par les fonctions concernées et leurs appels. Conserver les
garanties de création exclusive, copie vérifiée et remplacement récupérable.
Ne pas emprunter AUX pour gagner de la place sans le consentement préalable
requis pour la destruction de `/RAM`.

L'outil de mesure lit les symboles et tailles des fichiers construits sans
modifier les volumes ProDOS ni les banques mémoire.

## Reproduire

```sh
make -B all ARCH=enh
make -B all ARCH=6502
python3 tools/check_layout.py --big BINARY2
python3 tools/check_layout.py --lbl build-6502/a2fc.lbl --bin build-6502/A2FILE.CODE.BIN --big BINARY2
make test
```

Outils observés : `cc65 V2.18 - N/A` pour enhanced et `cc65 V2.19 - Git e11fb5c`
pour 6502. Relever les versions réellement utilisées plutôt que déduire leur
version des commentaires du Makefile. Ce relevé local ne constitue pas un test
sur émulateur ou matériel.

## PT3 : grands modules et TurboSound

Le lecteur accepte 65 535 octets, conteneur TurboSound compris, sans AUX.
La fenêtre BIG reste `$1B00–$3FFF` et les bornes de lien sont conservées.

| Zone PT3 | Adresses | Taille |
| --- | --- | ---: |
| Code, données, BSS | `$1B00–$36FF` | 7 168 |
| Deux en-têtes | `$3700–$3AFF` | 1 024 |
| Cache initial | `$3B00–$3DFF` | 768 |
| Tables du second module | `$3E00–$3FBF` | 448 |

Les premières tables empruntent 448 octets de `copy_buf`. Après initialisation,
deux pages entières de code devenu mort sont réutilisées ; une assertion de
lien vérifie leurs bornes. Les pages d'en-tête inutilisées peuvent aussi être
récupérées : cinq à huit pages de cache. Les opérandes d'initialisation ne
sont plus modifiés ensuite, ce que vérifie un test avec pages empoisonnées.
Le cache donne une seconde chance aux pages de samples et d'ornements ;
les lectures de patterns ne promeuvent pas les pages froides. Le bit 6 de la
table des pages porte cette référence et est masqué avant tout accès mémoire.
Le BSS PT3 finit à `$36AB` / `$36ED` (65C02/6502), laissant
84 / 18 octets avant les en-têtes.
Aucune donnée AUX, pile ou zone résidente n'est utilisée comme cache.

PURPLE reste sous `$2000` (fenêtre de 1 280 octets), ses lectures vont dans
MAIN `$2000–$3FFF`, puis AUXMOVE copie la première page vers AUX pour les
modes étendus. Le consentement précède le chargement ; toute sortie après
AUXMOVE reconstruit `/RAM`, y compris en cas d'erreur de lecture/fermeture.

Après intégration Purplesoft, les réserves résidentes sont : MAIN 145/682,
LC 168/163, LOWRAM 278/303, espace avant pile C 173/899, OPEN 4/42 octets
(65C02/6502). La pile C réservée reste de 192 octets. MAIN enhanced demeure
sous la réserve de travail visée de 256 octets ; OPEN enhanced est presque
plein. Les contrôles de disposition restent obligatoires.

Les bancs PT3 vérifient le plancher de pile, la mémoire AUX hors écran texte
et le volume source octet par octet sur des images jetables. Le lecteur
Purplesoft vérifie ses deux plans, les sorties et le consentement par session
sur les deux architectures. Ce sont des validations en émulation, pas des
mesures sur matériel physique.


## Consolidation du routage média

La correction des transitions ajoute un écran `Loading <cible>` préparé dans
MAIN/AUX `$0400–$07FF` dès la flèche, avant le nettoyage du lecteur. La relecture
des tables de panneaux attend son retour : elles partagent sa mémoire. Aucun
fichier ni octet AUX à partir de `$0800` n'est écrit par cette coordination.
Le parcours HGR/DHGR brut utilise la même annonce et redessine les panneaux
après relecture ; il n'a plus besoin des anciennes empreintes d'écran.
Les réserves après cette correction sont MAIN 365/885, LC 117/110,
LOWRAM 281/306 et espace avant pile C 393/1102 octets (65C02/6502),
avec une pile C réservée de 192 octets et les mêmes plafonds.

Les identifiants de `src/viewer_ids.h` indexent une seule table résidente de
noms. OPEN renvoie un octet plutôt qu'un pointeur vers ses propres chaînes ;
le feuilletage compare cet identifiant. Zéro reste une erreur de sonde et ne
sélectionne jamais un lecteur de repli. Les suffixes musicaux ne sont évalués
qu'une fois par candidat. La priorité des types explicites est conservée.

Le contrôle de taille HGR/DHGR regroupe les tailles exactes et leurs variantes
sans les huit derniers octets invisibles. Un test du vrai C couvre les 65 536
valeurs du mot bas, avec mot haut nul et non nul (393 216 vérifications pour
les deux configurations). Il conserve exactement 8 184, 8 192, 16 376 et
16 384 octets et refuse les tailles plus grandes ayant le même mot bas.

| Réserve | 65C02 avant → après | 6502 avant → après |
| --- | ---: | ---: |
| MAIN | 145 → 259 | 682 → 779 |
| OPEN | 4 → 185 | 42 → 215 |
| LC | 168 → 168 | 163 → 163 |
| LOWRAM | 278 → 277 | 303 → 302 |
| Espace avant pile C | 173 → 287 | 899 → 996 |

La réserve de travail MAIN de 256 octets est de nouveau atteinte sur 65C02.
Aucune limite de lien, taille de pile, API de plugin ou autorisation AUX n'est
modifiée. Les sondes n'écrivent que le buffer principal de lecture ; les
lecteurs conservent leur contrôle de consentement avant toute utilisation AUX.

Validation : 428 tests automatisés, compilations et limites des deux CPU ;
109 contrôles POM2 par architecture (`open_images.py`, `media.py`, `purple.py`),
avec écrans relus octet par octet, flèches, Échap, refus AUX et conservation du
volume source. Les essais utilisent uniquement des images jetables.

## Extraction des services de fichiers, 13 septembre 2026

Mesure sur l'arbre de travail courant, qui comprend les modifications en cours
de NIBCOPY et du routage. `file_output.h` et `file_copy.h` conservent leur
position dans l'unité de compilation ; aucun nouveau chargement ni appel
n'est ajouté. Tous les `.BIN` et `.PLG` existants sont identiques octet pour
octet avant/après sur les deux CPU (SHA-256), ainsi que les symboles `.lbl`.
Le contrôle de capacité de `CopyState` ne produit pas de code.

| Réserve, octets | 65C02 avant/après | 6502 avant/après |
| --- | ---: | ---: |
| MAIN | 365 / 365 | 885 / 885 |
| Carte langage | 117 / 117 | 110 / 110 |
| LOWRAM, BSS compris | 281 / 281 | 306 / 306 |
| Espace avant pile C | 393 / 393 | 1102 / 1102 |
| COPY | 33 / 33 | 25 / 25 |
| FORMAT BSS | 147 / 147 | 147 / 147 |

Les contrôles de disposition passent pour les deux architectures, avec la
pile C de 192 octets et tous les plafonds inchangés. Aucune modification du
graphe d'appels ni des binaires : consommation dynamique de pile inchangée,
sans nouvelle mesure sur émulateur. COPY reste sous l'objectif de 64 octets,
et la carte langage sous celui de 128 ; l'extraction ne revendique aucun gain
mémoire. Les autres surcouches gardent exactement leurs réserves.

### DOSGET, IDENT et FIXTYPES — 13 septembre 2026

DOSGET remplace la petite surcouche DOS33 par une grande surcouche explicitement
signalée BIG. Son plafond de code est `$2800` ; le bitmap de 70 octets est à
`$2800`, la copie T/S de 244 octets à `$2F00`. Le snapshot des 140 entrées
actives occupe `$3000-$3FDB`. FIXTYPES utilise le même snapshot, avec code et
BSS obligatoirement sous `$3000` (fin BSS `$2B5A` / `$2B21`). Le chargeur fait
un memmove avant de charger une grande surcouche ; BATCH réutilise ce service.
Aucun de ces nouveaux espaces n'utilise AUX. L'API passe à v5 sans déplacer
les services ; FIXTYPES refuse une ancienne API avant toute modification.

| Réserve en octets | 65C02 | 6502 |
| --- | ---: | ---: |
| MAIN | 23 | 518 |
| Carte langage | 14 | 6 |
| LOWRAM avec BSS | 245 | 270 |
| Espace avant pile C | 51 | 735 |
| OPEN | 11 | 43 |
| DOSGET avant `$2800` | 1547 | 1528 |
| FIXTYPES BSS avant `$3000` | 1189 | 1246 |

La pile reste à 192 octets et les contrôles de disposition sont actifs sur
les deux architectures. DOSGET ne tient plus dans le budget disque de BOOT :
il est distribué sur FILES/XL, sans agrandir les disquettes de 280 blocs.
Le banc formats passe 13 contrôles par CPU, dont le garde de pile, AUX intact
et la comparaison intégrale des fichiers sur une disquette jetable relue
après flush. FIXTYPES passe également 17 contrôles par CPU.
