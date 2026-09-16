# FIXIT : vérifier puis réparer un volume ProDOS

Spécification de préparation, écrite avant la première ligne de code.
[TODO.md](../TODO.md) place FIXIT **après** la preuve des pannes combinées,
pas avant : « diagnostic sans écriture », puis « corrections seulement après
un plan choisi, original conservé, chaque écriture vérifiée ». Ce document
prépare ces deux chantiers ; il n'ouvre pas le travail.

Les offsets cités ont été relus sur `dist/A2FILECMD-6502-BOOT-0.8.7.po` et
recoupés avec `src/plugins/volinfo.c`, `src/plugins/move.c`,
`src/plugins/wipe.c` et `tools/prodos_read.py` : ce sont eux la référence.

## 1. Périmètre et principes

FIXIT est une **grande surcouche** `A2FILE/FIXIT.PLG`, catégorie DISKTOOLS
(`config/packages.mk`). La disquette BOOT est pleine, un bloc libre : FIXIT
n'y va pas. Le menu `!` range FIXIT sous « Other » tant que la chaîne
`mn_group3` (« Disks ») du résident ne le nomme pas : six octets de résident,
à prendre à la prochaine retouche de `src/a2fc.c`, pas avant.

Le chantier WRITE est une **seconde** grande surcouche,
`A2FILE/REPAIR.PLG` (`src/plugins/repair.c`), même catégorie et même
« Other » : c'est le recours 5 de la section 4, et il a bien fallu s'en
servir — la fenêtre du chantier Read s'est fermée à sept octets près
(mesure du 16 septembre 2026). Aucun état ne survit d'une surcouche à
l'autre : REPAIR **refait sa propre passe** avant de proposer quoi que ce
soit. Les deux partagent une seule source de parcours,
`src/plugins/fixit_walk.h`, incluse par `fixit.c` et par `repair.c`, dont
les parties sont sélectionnées par `#ifdef REPAIR` ; l'oracle de ce partage
est que `build/fixit.PLG` et `build-6502/fixit.PLG` restent **octet pour
octet** ceux d'avant.

Ce que FIXIT accepte : un volume ProDOS **réel**, `pan->fs == FS_PRODOS`. Une
image ouverte comme dossier (`FS_IMG`) ou un disque DOS 3.3 (`FS_DOS33`) est
refusé, comme dans WIPE et VOLINFO. La sélection suit WIPE : entrée `"/VOL"`
de la liste des volumes, unité `selected->mdate << 4`, ou premier composant du
chemin du panneau actif, l'unité venant d'un `ON_LINE` (`$C5`) sur l'unité 0.
L'en-tête doit être valide avant tout comptage.

Les principes, qui viennent de [AGENTS.md](../AGENTS.md) :

- **Chantier Read : aucune écriture.** Le seul fichier qu'il aurait créé est
  le rapport exporté, dans l'**autre** panneau, par création exclusive,
  jamais sur le volume contrôlé — et il n'entre pas dans la fenêtre
  (section 4) : le chantier Read, tel qu'il est livré, ne crée aucun fichier
  du tout. « En cas de doute, refuser l'écriture. »
- **Aucune réparation sans plan choisi.** Le plan est affiché, compté, puis
  confirmé par un mot tapé en entier. « Identifier précisément la cible et
  obtenir la confirmation dans l'interface avant la première écriture. »
- **Original récupérable.** Avant chaque écriture le bloc est relu dans une
  copie conservée ; l'écriture est relue dans un second tampon et comparée ;
  en cas d'échec l'original est réécrit puis vérifié. « Conserver l'original
  récupérable jusqu'à la fin de l'écriture, de la fermeture et des contrôles. »
- **Les écritures brutes contournent ProDOS.** `WRITE_BLOCK` ignore les bits
  d'accès et les fichiers ouverts : FIXIT contrôle tout lui-même, comme MOVE
  et BLKEDIT.
- **Pas d'atomicité.** ProDOS ne fournit aucune transaction couvrant plusieurs
  écritures physiques. Une coupure pendant un plan laisse une partie des
  corrections appliquées. Chaque correction est donc indépendante des autres :
  c'est la seule garantie honnête possible.
- **Volume du programme refusé en écriture**, par nom **et** par unité, comme
  WIPE avec `api->cfg_path`. ProDOS 8 garde en mémoire une copie de bloc de
  bitmap et la réécrit à la première allocation : une correction brute sous un
  système qui lit encore `A2FILE.CODE` et ses `.PLG` peut être annulée sans
  avertissement. Le chantier Read accepte ce volume, il ne fait que lire.
- **Échap partout** : parcours, pagination, plan. Avant la première écriture
  il ne laisse rien ; pendant les écritures, l'arrêt suit la correction en
  cours, jamais le milieu d'un bloc.
- **Jetables seulement** pour les essais destructifs.

## 2. Les structures ProDOS, telles que le dépôt les lit

Offsets **relatifs à l'entrée de 39 octets**. Entre parenthèses, l'offset
depuis le début du bloc quand l'entrée est l'en-tête, qui commence à `+$04`.

En-tête, commun au volume (bloc 2) et au sous-répertoire (son premier bloc) :
`+$00` (`$04`) type de stockage, `$F` pour le volume et `$E` pour un
sous-répertoire, plus la longueur du nom ; `+$01..$0F` le nom ; `+$10` vaut
`$75` dans un sous-répertoire ; `+$1E` (`$22`) `access` ; `+$1F` (`$23`)
`entry_length` = 39 ; `+$20` (`$24`) `entries_per_block` = 13 ; `+$21..$22`
(`$25`) `file_count`. Ensuite les deux en-têtes divergent : le volume porte
`bit_map_pointer` en `+$23..$24` (`$27`) et `total_blocks` en `+$25..$26`
(`$29`) ; le sous-répertoire porte `parent_pointer` en `+$23..$24`, le **bloc**
qui contient son entrée, `parent_entry_number` en `+$25`, son rang **à partir
de 1**, et `parent_entry_length` = 39 en `+$26`.

`volinfo.c` lit `word(buf+39)` et `word(buf+41)` ; `wipe.c` définit
`H_BITMAP 0x27` et `H_TOTAL 0x29` : ce sont bien ces champs.

Entrée de fichier ou de sous-répertoire : `+$00` type de stockage et longueur
du nom (`$0` = entrée libre), `+$10` `file_type`, `+$11..$12` `key_pointer`
(`word(entry+17)` dans `volinfo.c`), `+$13..$14` `blocks_used`
(`word(entry+19)`), `+$15..$17` `eof` sur trois octets poids faible d'abord,
`+$1E` `access` (bit 7 destruction, 6 renommage, 5 sauvegarde, 1 et 0 écriture
et lecture), `+$25..$26` `header_pointer`, le **bloc clé** du répertoire qui la
contient.

Bloc de répertoire : `+$00..$01` bloc précédent, `+$02..$03` bloc suivant,
puis 13 entrées de 39 octets à partir de `+$04` (4 + 13 × 39 = 511).
Fichier étendu (`$5`) : le bloc clé porte deux mini-entrées de 18 octets à
`+$000` et `+$100`, chacune `+$00` type de stockage (1 à 3), `+$01..$02` bloc
clé, `+$03..$04` blocs utilisés, `+$05..$07` eof.

Invariants appliqués tels quels :

- bitmap : **bit à 1 = libre**, bit à 0 = utilisé ; le bit de poids fort d'un
  octet est le bloc le plus bas ; un bloc de bitmap couvre 4 096 blocs ; la
  bitmap occupe `((total-1)/4096)+1` blocs consécutifs ;
- blocs 0 et 1 amorçage, 2 à 5 répertoire de volume (taille fixe), puis les
  blocs de bitmap : tous marqués utilisés ;
- `file_count` compte les entrées de type de stockage non nul, en-tête exclu,
  sur toute la chaîne du répertoire ;
- `blocks_used` d'un répertoire est porté par son entrée chez son parent, et
  son `eof` vaut exactement `blocks_used × 512` (vérifié : A2FILE, 2 blocs,
  eof 1024, entrée bloc 2 rang 2, `parent_pointer` 2) ;
- un pointeur nul dans un bloc d'index est un **trou creux**, pas le bloc 0 ;
- types valides dans une entrée : `$1` seedling, `$2` sapling, `$3` tree, `$5`
  étendu, `$D` sous-répertoire ; `$E` et `$F` seulement en tête de répertoire ;
- plafonds : seedling 512 octets, sapling 128 Ko, tree 16 Mo.

## 3. Catalogue des contrôles, chantier Read

Les identifiants sont ceux de `tools/prodos_check.py`, le contrôleur de
référence hôte. Ils servent tels quels comme énumération C (`CHK_BM_LOST`) et
comme clés JSON. Un constat porte `{id, block, slot, expected, found, path}`,
`expected` étant ce que le contrôle a calculé et `found` ce que le disque
contient.

Ce que VOLINFO compte déjà : `usedfree`, `lost`, `shared`, `bad`, `counts`,
`files`, `fragmented`, et `incomplete` dès qu'une structure l'empêche de
conclure. Il ne sépare pas les causes : `bad` mélange pointeur hors plage,
type inconnu et chaîne incohérente ; `counts` mélange `file_count` et
`blocks_used`. FIXIT sépare, parce qu'une réparation par cause n'est pas une
réparation par compteur.

| # | Id | Lit | Gravité | VOLINFO |
| --- | --- | --- | --- | --- |
| 1 | `HDR_STORAGE` | bloc 2 `+$04`, quartet haut ≠ `$F` | refus | oui |
| 2 | `HDR_ENTRY_LEN` | en-tête `+$1F` ≠ 39 | refus | oui |
| 3 | `HDR_PER_BLOCK` | en-tête `+$20` ≠ 13 | refus | oui |
| 4 | `HDR_BITMAP` | `+$23` hors `[3, total[`, ou pages débordant le volume | refus | oui |
| 5 | `HDR_TOTAL` | `+$25` nul, < 6, ou dernier bloc illisible ; l'oracle hôte compare à la taille de l'image | refus | partiel |
| 6 | `DIR_CHAIN` | bloc de répertoire `+$00` ≠ bloc précédent, ou `+$02` hors plage | réparable (`prev` seul) | oui (`bad`) |
| 7 | `DIR_LOOP` | bloc clé ou chaînage déjà visité | refus | oui (`bad`) |
| 8 | `DIR_HEADER` | en-tête de sous-répertoire : `$E`, 39, 13 | refus | oui (`bad`) |
| 9 | `DIR_PARENT` | en-tête `+$23`, `+$25`, `+$26` contre l'entrée réelle | réparable | non |
| 10 | `DIR_DEPTH` | plus de 16 niveaux (pile du parcours) | refus | oui (`bad`) |
| 11 | `ENT_STORAGE` | quartet haut hors `$1 $2 $3 $5 $D` | refus | oui (`bad`) |
| 12 | `ENT_NAME` | longueur 0 ou > 15, initiale non alphabétique, caractère hors `A-Z 0-9 .` | irréparable sans saisie | non |
| 13 | `ENT_HEADER_PTR` | entrée `+$25` ≠ bloc clé du répertoire qui la porte | réparable | non |
| 14 | `ENT_KEY` | `key_pointer` nul avec `eof` non nul, ou ≥ `total_blocks` | irréparable sans perte | oui (`bad`) |
| 15 | `FILE_COUNT` | en-tête `+$21` ≠ entrées vivantes comptées | réparable | oui (`counts`) |
| 16 | `DIR_BLOCKS` | entrée `+$13` d'un `$D` ≠ longueur de sa chaîne | réparable | oui (`counts`) |
| 17 | `DIR_EOF` | entrée `+$15` d'un `$D` ≠ `blocs × 512` | réparable | non |
| 18 | `FILE_BLOCKS` | entrée `+$13` ≠ blocs atteints | réparable | oui (`counts`) |
| 19 | `FILE_EOF` | `eof` au-delà du plafond du type de stockage | info | non |
| 20 | `IDX_RANGE` | pointeur ≥ `total_blocks` dans un index ou un index maître | irréparable sans perte | oui (`bad`) |
| 21 | `FORK_STORAGE` | `$5` : mini-entrée `+$000` ou `+$100` de type hors 1 à 3 | refus | oui (`bad`) |
| 22 | `XLINK` | bloc référencé deux fois | irréparable sans perte | oui (`shared`) |
| 23 | `BM_USED_FREE` | bloc référencé, bit de bitmap à 1 | réparable | oui (`usedfree`) |
| 24 | `BM_LOST` | bit à 0, aucune référence | réparable sous condition | oui (`lost`) |
| 25 | `IO_ERROR` | échec `READ_BLOCK` `$80` | refus, pose `complete = 0` | oui (`failed`) |
| 26 | `HDR_NAME` | nom du bloc 2 contre celui d'`ON_LINE` | info | non |
| 27 | `VOLDIR_SIZE` | chaîne du répertoire de volume ≠ blocs 2, 3, 4, 5 | irréparable sans perte | non |
| 28 | `ENT_ACCESS` | `+$1E` bits 4 à 2 non nuls | info | non |
| 29 | `BM_RESERVED` | bloc 0, 1, 2 à 5 ou de bitmap marqué libre | réparable | non |
| 30 | `BM_TAIL` | bit à 1 au-delà de `total_blocks` dans la dernière page | réparable | non |

Les vingt-quatre premiers sont déjà les identifiants de `prodos_check.py` ;
les six derniers sont propres à FIXIT et devront y être ajoutés pour que les
deux listes restent identiques. VOLINFO réclame déjà silencieusement les blocs
réservés, ce qui les empêche d'apparaître en blocs perdus ; il ne dit pas
qu'ils étaient marqués libres.

Règle de complétude, identique à celle de `prodos_check.py`, à deux niveaux :

- **Passe incomplète** (`complete = 0`) : `IO_ERROR`, `DIR_DEPTH`, `DIR_LOOP`,
  un `next` hors plage ou illisible, `HDR_BITMAP`. `BM_LOST` n'est alors
  **pas** signalé, car un bloc que personne ne réclame peut appartenir à la
  partie de l'arbre que le parcours n'a pas atteinte. `BM_USED_FREE` reste
  signalé : une référence constatée est un fait. VOLINFO le dit déjà :
  « Lost blocks (unconfirmed) ». La règle porte sur la passe **entière**,
  pas sur la fenêtre en cours : une coupure survenue dans la fenêtre 3
  annule aussi les `BM_LOST` des fenêtres 1 et 2, déjà inscrits (section 4,
  « La reprise de `BM_LOST` »).
- **Entrée partielle** : `ENT_KEY`, `ENT_STORAGE`, `IDX_RANGE`,
  `FORK_STORAGE`. Seule cette entrée est abandonnée : `FILE_BLOCKS` n'est pas
  émis pour elle (la cause est signalée, pas l'arithmétique qui en découle),
  la passe reste complète et `BM_LOST` est signalé pour les blocs orphelins.
  Ces blocs sont peut-être la queue du fichier cassé : le diagnostic les
  nomme, mais le chantier WRITE refuse de les libérer tant qu'une entrée
  partielle ou un `XLINK` subsiste (section 5).

## 4. Mémoire et données

Mesures au lien de VOLINFO, 65C02 : CODE 6 335 (fin `$33FA`), RODATA 1 164
(`$3886`), BSS 1 451 (`$3E34`), fichier 7 562 octets, 7 494 en 6502.
VOLINFO, BLKVIEW et BLKEDIT reçoivent `__OVLSIZE__=0x249E` : la copie de la
table API est posée à `$3F9E`, donc code, données **et** BSS finissent avant.
VOLINFO garde 362 octets de marge. FIXIT prend la même fenêtre,
`$1B00-$3F9D`, 9 374 octets pour tout.

FIXIT n'est **pas** dans `XPLUGINS_SCRATCH` : la variante à 4 Ko de brouillon
(`$3000-$3FFF`) obligerait code et BSS à finir avant `$3000`, soit 5 376
octets, où le seul parcours de VOLINFO n'entre pas.

Une bitmap complète des blocs référencés est écartée : 65 535 blocs font
8 192 octets, à comparer aux 9 374 qui portent aussi le code. FIXIT garde donc
la fenêtre de 4 096 blocs et le `seen[512]` de VOLINFO, et recommence le
parcours du répertoire une fois par fenêtre, jusqu'à 16 fois sur un volume de
32 Mo. C'est lent et c'est éprouvé.

Ce qu'une passe retient :

- `counts[30]`, un compteur 16 bits par contrôle, 60 octets ;
- `sample[16]`, les seize premières occurrences, `{id, block, slot}` sur
  **4** octets, 64 octets, pour l'écran et pour le rapport. Le rang tient en
  un octet et le sentinelle « aucun rang » a déménagé dans le **bit 7 de
  l'identifiant**, qui ne compte que jusqu'à trente : `IDX_RANGE` nomme l'un
  des 256 pointeurs d'un bloc d'index, et un octet de rang n'avait plus de
  valeur libre (constaté à l'incrément 3, contre `prodos_check.py` qui
  rapporte un `IDX_RANGE` de rang 255). Cinq octets à l'incrément 3, quatre
  depuis l'incrément 7 : `sample[j]` devient un décalage au lieu d'une
  multiplication par cinq, et les rangs passent en octet dans tous les
  appels de constat ;
- `plan[32]`, `{block, kind, a, b}` sur 6 octets, 192 octets, chantier
  WRITE — **abandonné** : il n'a pas tenu dans la fenêtre de REPAIR et il
  n'était pas nécessaire (mesures ci-dessous, et section 5).

Au-delà de 16 occurrences, l'écran affiche le compteur et « more » : la
réparation se décide par contrôle, pas par occurrence. Au-delà de 32 blocs à
réécrire, le plan est **refusé** : `Plan full: %u blocks to rewrite, limit 32.
Repair in several passes.` Un plan tronqué qui s'appliquerait à moitié n'est
jamais proposé.

Placement, tel qu'il est au bout de l'incrément 7 : **deux** tampons de 512
octets, et lequel est lequel a coûté 197 octets de code à lui seul. `blk[512]`
est en BSS, à une adresse connue du compilateur : cc65 indexe un tableau
absolu d'une instruction, alors qu'il reconstruit son registre d'indexation
derrière chaque appel quand le tampon est un **pointeur** comme
`api->copy_buf`. Le bloc de répertoire, que le parcours lit plus que tout
autre, est donc dans `blk` — avec, tour à tour, l'en-tête du volume, le bloc
d'index maître d'un fichier arbre (qui coûte le bloc de répertoire, déjà lu à
ce moment-là) et la page de bitmap. `api->copy_buf` (512 octets, hors fenêtre)
garde ce qui est lu une fois puis recopié, ou parcouru au pointeur de toute
façon : la table `ON_LINE`, le bloc clé d'un fichier étendu, un bloc d'index.
Le reste de la BSS : `seen[512]`, `stack[16]` cadres de **13** octets (six
mots et un octet : 208 octets), `forks[16]` pour les deux mini-entrées de huit
octets d'un fichier étendu, et **aucun** `entry[39]` — l'entrée examinée est
lue en place dans `blk`, ses champs relevés avant le premier bloc qui
l'écrase ; plus, au chantier WRITE seulement, `orig[512]` pour le bloc en vol.

Le cadre ne garde plus le bloc ni le rang de l'entrée qui a nommé ce
répertoire, que `DIR_BLOCKS` et `DIR_EOF` doivent désigner et où se lisent
leurs valeurs attendues : c'est le `(block, slot - 1)` du cadre parent, et son
bloc de répertoire est **relu à la dépile** — la lecture dont le parent a
besoin juste après, donc aucun `READ_BLOCK` de plus. Cinq octets de cadre
gagnés seize fois.

Pile C : environ 90 octets. Un seul tableau d'index est parcouru par une
fonction qui s'appelle elle-même, bornée à deux niveaux (bloc d'index maître
puis bloc d'index) : ses locales sont sur la pile C, `#pragma static-locals
(off)`, parce que les surcouches sont compilées avec `-Cl` et qu'une locale
statique casserait la récursion — neuf octets de pile par niveau. Aucun
tableau local. La pile de répertoires est un tableau indexé par la profondeur,
comme dans `volinfo.c` et `wipe.c`, et `DIR_DEPTH` refuse au-delà de 16.

Premier budget, à confirmer au lien : Read ~5 600 de code, ~1 400 de RODATA,
~1 500 de BSS, soit ~8 500 ; WRITE ajoute ~900, ~200 et ~704, soit ~1 800. Les
deux ensemble dépassent les 9 374 octets. Mesure au lien des incréments 1 à 3,
65C02 : CODE 6 521 (fin `$34BF`), RODATA 1 063 (`$38E6`), BSS 1 667 (fin
`$3F6C`), fichier 7 658 octets ; 6502 : CODE 6 474, BSS jusqu'à `$3F3D`,
fichier 7 611. Il restait **49 octets** sous `$3F9D` en 65C02 (96 en 6502) :
le parcours seul tenait, le chantier WRITE devra passer par le recours 5
(surcouche séparée).

### Les huit derniers contrôles : ce qui a été mesuré (16 septembre 2026)

Les huit identifiants des incréments 4 à 7, écrits sans précaution, coûtent
**931 octets de code et 11 de BSS** : le lien débordait de 743 octets. Il a
donc fallu rendre la place avant de les garder. Chaque forme a été mesurée au
lien, 65C02, et la colonne « libre » est ce qui restait sous `$3F9D` après
elle (comme le journal de [MEMORY-BUDGETS.md](MEMORY-BUDGETS.md)) :

| Forme essayée | Effet | Libre | Gardée |
| --- | --- | ---: | --- |
| `#pragma codesize (10 / 50 / 80 / 90)` | CODE +1 301 / +1 193 / +1 101 / +1 083 | — | non |
| `#pragma codesize (110 … 400)` | identique à 100 | 49 | sans objet |
| les 30 noms de contrôle en une chaîne compactée parcourue par index, au lieu de `char[30][15]` | RODATA −132, CODE +24, BSS +2 | 155 | **oui** |
| `struct Frame` de 18 à 13 octets, l'entrée nommante relue à la dépile | BSS −73, CODE +7 | 221 | **oui** |
| le contrôle `DIR_EOF` au même endroit (comparaison octet par octet d'un eof 24 bits contre blocs × 512) | CODE +137 | 84 | **oui** |
| bloc d'index et bloc d'index maître : **une** boucle récursive, locales statiques | CODE −147 | 233 | **non** : `-Cl` rend les locales statiques, la récursion serait fausse |
| la même, `#pragma static-locals (off)` | CODE −107, BSS −6 | 199 | **oui** |
| la même, aplatie sans récursion (deux écritures) | CODE +152 / +294 | 39 / −103 | non |
| les sept autres contrôles, écrits naïvement | CODE +931, BSS +11 | −743 | **oui**, à financer |
| cinq raccourcis de constat (`vfinding`, `bfinding`, `nfinding`, `hfinding`, `efinding`) : 30 des 34 sites ne passent plus qu'un argument | CODE −153 | −590 | **oui** |
| `HDR_NAME` par `memcpy` au lieu d'une boucle, `eof_over` par `word()`, la queue de bitmap fondue dans la boucle de fenêtre | CODE −119 | −470 | **oui** |
| `claim` via `claimed`, `enter` à une seule sortie d'échec, **un seul** site `v_cprintf` pour la ligne de constat (trois formats, un appel variadique porte la taille de ce qu'il a empilé), table `ON_LINE` et mini-entrées parcourues au pointeur, cinq appels `note()` | CODE −292 | −182 | **oui** |
| chemin de coupure unique dans `walk`, l'entrée lue en place au lieu de `entry[39]`, bitmap parcourue octet puis bit | CODE +10, BSS −33 | −159 | **oui** |
| forme du répertoire de volume sans `rootblk[5]` | CODE −34, BSS −7 | −123 | **oui** |
| `struct Frame` rembourré à 16 octets pour que `stack[i]` soit un décalage | CODE +6, BSS +48 | −169 | non |
| `sample` sur 4 octets, le sentinelle testé dans `finding` | CODE +32, BSS −16 | −131 | non (mauvaise forme) |
| `sample` sur 4 octets, le sentinelle **posé par les raccourcis** et le rang en octet partout | CODE −30, BSS −16 | −93 | **oui** |
| trois refus fondus en un dans `plugin_entry`, `note()` | CODE −45 | −48 | **oui** |
| `subheader` relevant tous ses champs dans des locales avant de juger | CODE +93, BSS +10 | −151 | non : une locale statique coûte plus que le `(ptr),y` reconstruit |
| le bloc de répertoire dans un tableau BSS à adresse connue (`blk`), `api->copy_buf` pour ce qui est recopié | CODE −197 | 156 | **oui** |
| le cache du bloc de répertoire gardé quand la lecture va dans `api->copy_buf` (une relecture de moins par fichier) | CODE +12 | 144 | **oui** |

Mesure au lien des incréments 1 à 7, 65C02 : CODE 6 679 (fin `$355D`),
RODATA 931 (`$3900`), BSS 1 546 (fin `$3F0D`), fichier 7 684 octets,
**144 octets libres** sous `$3F9D` ; 6502 : CODE 6 663 (fin `$354D`),
RODATA 931, BSS 1 546 (fin `$3EFD`), fichier 7 668 octets, **160 libres**. Les
trente identifiants de `tools/prodos_check.py` sont tous implémentés : la
table `CLOSED_BY` de `tools/test_fixit.py` est vide.

### L'écran, la relance et l'export : ce qui a été mesuré (16 septembre 2026)

L'incrément 8 a coûté 133 octets : 115 de code, 16 de RODATA (la ligne de
résumé et le verdict compté) et 2 de BSS (`found`, le total des constats,
incrémenté dans `finding` — le recompter à l'affichage coûtait autant et
mentait quand Échap coupait la pagination).

| Forme essayée | Effet | Libre | Gardée |
| --- | --- | ---: | --- |
| la ligne de résumé, `R`, la boucle de touches, `scan()` refait l'en-tête | CODE +70, RODATA +16, BSS +2 | 56 | **oui** |
| le verdict compté, `v_sprintf(A->note, "%u findings, ...", found)` | CODE +47 | 9 | **oui** |
| le même verdict par un pointeur local descendu le long de la chaîne de tests, un seul `note()` | CODE +8, BSS +2 | −1 | non : `-Cl` met la locale en BSS et un pointeur s'y écrit en deux instructions ; les six sites d'appel coûtent moins |
| la page à 18 lignes (`row = 0`, le titre au-dessus du compte) au lieu de 16 | CODE −2 | **11** | **oui** |
| **`E` export**, écrit comme celui de `volinfo.c` : refus image/DOS 3.3, refus du volume contrôlé, `CREATE $C0` exclusif, `fopen("wb")`, une ligne par contrôle non nul, `END REPORT`, chaque `fwrite` et le `fclose` contrôlés ; recherche du premier échantillon factorisée entre l'écran et le rapport | CODE +822, RODATA +294, BSS +20 | −1 127 | **non** |

L'export est donc **reporté**, exactement par le recours 4 : il demande
1 136 octets là où il en restait 11. Rien n'a été relevé pour le faire
entrer — le plafond `__OVLSIZE__` ne bouge pas. `VOLINFO` reste l'outil qui
décrit un volume et sait exporter ; un rapport FIXIT, s'il est un jour
voulu, sera une surcouche séparée qui refait sa propre passe (recours 5),
comme le chantier WRITE. La touche `E` n'apparaît donc **nulle part** : ni
dans la ligne de résumé, ni dans le code.

Mesure au lien des incréments 1 à 8, 65C02 : CODE 6 794 (fin `$35D0`),
RODATA 947 (`$3983`), DATA 3, BSS 1 548 (fin `$3F92`), fichier 7 815 octets,
**11 octets libres** sous `$3F9D` ; 6502 : CODE 6 778 (fin `$35C0`),
RODATA 947, BSS 1 548 (fin `$3F82`), fichier 7 799 octets, **27 libres**.
Le chantier Read est plein : la fenêtre est fermée.

### La reprise de `BM_LOST` : ce qui a été mesuré (16 septembre 2026)

La règle de complétude de la section 3 est une propriété de **toute** la
passe, mais la bitmap de la fenêtre 1 est comparée avant que la fenêtre 2
soit seulement parcourue. Une coupure découverte plus tard — Échap, une
erreur de lecture sur la page de bitmap suivante, une chaîne de répertoire
qui ne se referme que dans une fenêtre ultérieure — laissait donc des
constats `BM_LOST` de la fenêtre 1 dans un rapport qui se dit incomplet :
le résumé nommait des blocs perdus sous un verdict qui dit qu'on ne peut
pas s'y fier. `tools/prodos_check.py`, qui parcourt l'image entière avant
de conclure, n'en signale aucun. Deux tests de `tools/test_fixit.py` le
tenaient en défaut ; `scan()` **reprend** donc le compteur et le total après
`audit()`.

| Forme essayée | Effet | Libre | Gardée |
| --- | --- | ---: | --- |
| `if (!complete) { found -= counts[CHK_BM_LOST]; counts[CHK_BM_LOST] = 0; }` après `audit()` | CODE +34 | −23 | **oui**, à financer |
| le seul `counts[CHK_BM_LOST] = 0`, `found` laissé gonflé | CODE +11 | 0 | non : la ligne de résumé compterait ce qu'elle n'affiche pas |
| les dix rangements morts de `reset()` (`total`, `bitmap`, `pages`, `base`, `span`) : les trois premiers sont écrits par `header()` et les deux autres par `audit()` avant la première lecture | CODE −30 | **7** | **oui** |

Mesure au lien des incréments 1 à 8 avec la reprise, 65C02 : CODE 6 798
(fin `$35D4`), RODATA 947 (`$3987`), DATA 3, BSS 1 548 (fin `$3F96`),
fichier 7 819 octets, **7 octets libres** sous `$3F9D` ; 6502 : CODE 6 784
(fin `$35C6`), RODATA 947, BSS 1 548 (fin `$3F88`), fichier 7 805 octets,
**21 libres**.

Ce que la reprise coûte, et qui est assumé : les constats `BM_LOST` déjà
inscrits ont consommé des places dans `sample[16]`, que la reprise ne rend
pas. Sur une passe coupée, un autre contrôle peut donc n'afficher que son
compteur, sous la ligne `more findings than the table holds`. Un rapport
honnête sans bloc vaut mieux qu'un bloc sous un verdict qui le dément.

Deux limites restent, faute de place, et sont ici pour mémoire :

- un constat de l'arbre découvert **seulement** dans une fenêtre autre que
  la première (`dfinding` ne retient que `base == 0`) pose `complete = 0`
  sans s'inscrire : la passe se déclare incomplète sans nommer la cause.
  Il faut pour cela un volume de plus de 4 096 blocs **et** un répertoire
  référencé deux fois dont le bloc clé tombe hors de la première fenêtre ;
  le verdict reste prudent, la liste seule est muette. Y remédier demande de
  consulter `counts[]` dans `dfinding`, une vingtaine d'octets qui
  n'existent pas ;
- `stop()` lit `$C000` et n'acquitte que sur Échap, comme `volinfo.c` : une
  touche quelconque frappée pendant le parcours reste dans le verrou du
  clavier et **masque** l'Échap qui suivrait, jusqu'à ce que l'écran de
  constats la consomme. Elle n'est ni perdue ni prise pour un Échap.

### REPAIR, la surcouche séparée : ce qui a été mesuré (16 septembre 2026)

Le recours 5 a été pris. Le parcours a déménagé dans
`src/plugins/fixit_walk.h`, `fixit.c` n'en garde que son en-tête de
surcouche et l'`#include` : `build/fixit.PLG` et `build-6502/fixit.PLG`
sont restés **octet pour octet** les mêmes (SHA-1
`b440a94748c56461ea56af0f231edfcddaa14038` et
`04979b23af23bf77b04fedcdfc41696e59cc9545`), ce qui est l'oracle du
déménagement : le préprocesseur rend le même flot de jetons, donc ld65 le
même fichier. La règle de fabrication des `.PLG` liste déjà
`$(wildcard $(SRC)/plugins/*.h)` en prérequis, comme pour `dirscan.h` et
`imageio.h` : un changement du parcours reconstruit les deux surcouches.

REPAIR compilé naïvement — le parcours entier, la table de plan, l'écran,
les écritures — débordait la fenêtre de **1 875 octets**. Chaque forme a
été mesurée au lien, 65C02, et la colonne « libre » est ce qui restait sous
`$3F9D` après elle :

| Forme essayée | Effet | Libre | Gardée |
| --- | --- | ---: | --- |
| REPAIR écrit sans précaution (parcours + `plan[32]` + écran + écritures) | — | −1 875 | **oui**, à financer |
| les cinq raccourcis de constat devenus des **macros** qui jettent le bloc et le rang avant l'appel : un paramètre de macro non utilisé n'est même pas évalué, et trente-quatre sites d'appel ne passent plus qu'un argument | CODE −1 491 | −361 | **oui** |
| `plan[32]` réduit de 8 à 6 octets, le rang d'un `DIR_PARENT` logé dans le champ `slot` qu'un en-tête n'utilise pas, un `DIR_EOF` gardant le nombre de blocs dont son eof est 512 fois | CODE −100, BSS −64 | — | **oui** |
| une **seule** boucle de bitmap pour les trois passes : le plan compte, l'application fait un ou exclusif — chaque correction de la section 5 est un bit à l'envers — et la page est écrite une fois | CODE −430 | −518 | **oui** |
| `plan_kind()` et `plan_blocks()` fondus dans `plan_add` | CODE −120 | — | **oui** |
| `VOLDIR_SIZE` retiré de REPAIR (`rootchain`, `voldir_shape`, quatre mots de BSS) | CODE −105, BSS −9 | — | **oui** |
| `ENT_NAME`, `ENT_ACCESS`, `FILE_EOF`, `HDR_NAME` retirés de REPAIR (`valid_name`, `eof_over` et leurs six sites) | CODE −455 | — | **oui** |
| `DIR_HEADER` retiré de REPAIR | CODE −51 | −121 | **oui** |
| la ligne `Blocks %u..%u / %u` du parcours retirée de REPAIR | CODE −62, RODATA −23 | −36 | **oui**, à regret |
| `#pragma codesize (10 / 50 / 80 / 90)` | CODE +1 544 / +1 476 / +1 343 / +1 339 | — | non |
| `#pragma codesize (200 / 400)` | CODE +322 / +308 | — | non |
| `1 << i` avec `i` variable remplacé par une table `BIT[4]` de quatre octets, aux cinq sites dont le plus interne des deux boucles de bitmap | CODE −39 | — | **oui** |
| `same_header()` comparant le nom du bloc 2 octet par octet au lieu de le recopier dans `nm` et d'appeler `strcmp` | CODE −25 | — | **oui** |
| `freeing_ok()` en boucle sur une table de cinq identifiants au lieu de cinq tests écrits | CODE +8 | — | non |
| la **table de plan supprimée** : `plan_add` et ses sept sites d'appel, `plan[32]`, `kn[]`, `dirblocks` | CODE −632, BSS −205 | — | **oui** (section 5) |

Mesure au lien de REPAIR, 65C02 : CODE 6 690 (fin `$3568`), RODATA 1 072
(`$3998`), DATA 3, BSS 1 500 (fin `$3F77`), fichier 7 836 octets,
**38 octets libres** sous `$3F9D` ; 6502 : CODE 6 668 (fin `$3552`),
RODATA 1 072, DATA 3, BSS 1 500 (fin `$3F61`), fichier 7 814 octets,
**60 libres**. `build/fixit.PLG` fait toujours 7 819 octets et
`build-6502/fixit.PLG` 7 805, aux mêmes empreintes.

Ce que ces 1 875 octets ont coûté est dit en clair en section 5 : REPAIR ne
porte pas six des trente contrôles, n'affiche pas l'avancement du parcours,
et n'écrit, dans ce lot, que la bitmap.

### Les sept réparations de répertoire : ce qui a été mesuré (16 septembre 2026)

Les incréments 13 à 15 sont entrés dans une fenêtre qui avait **38 octets**.
Écrits sans précaution — une fonction d'écriture vérifiée par correction,
sept sites d'appel, le compte des blocs — ils débordaient de **709 octets**.
Chaque forme a été mesurée au lien, 65C02, et la colonne « libre » est ce
qui restait sous `$3F9D` après elle :

| Forme essayée | Effet | Libre | Gardée |
| --- | --- | ---: | --- |
| les sept réparations écrites sans précaution (`verified` + `restored` + `dirfix(bloc, offset, n)`, sept sites, `dblocks`, `ov[5]`, `nv[5]`) | CODE +766, BSS +16, RODATA −35 | −709 | **oui**, à financer |
| `fixing()`, `inhand()` et `dirfix()` fondus en **une** `fix(bloc, pointeur, n)` : le pointeur est une adresse dans `blk`, la relecture du bloc et le refus des fenêtres suivantes sont dedans | CODE −140 | −567 | **oui** |
| la colonne « bits %u pages » retirée de l'écran de plan (`pgs[4]`, le format `M_LBM`, la boucle qui les compte) ; `same_header()` comparant les 39 octets de l'entrée d'en-tête copiés par le plan ; **un seul** `v_sprintf` pour les deux verdicts | CODE −193, RODATA −22, BSS −12 | −340 | **oui** |
| `verified(bloc, tampon)` au lieu de trois arguments : le tampon de relecture se déduit de celui qu'on écrit | CODE −13 | −332 | **oui** |
| les six compteurs du plan dans un tableau `zz[]` vidé par un `v_memset` ; `Frame.blocks` renommé `nblk` pour libérer le nom | CODE −103, BSS −18 | −260 | **oui** |
| la page de bitmap corrigée **construite dans `seen`** (mort une fois la page dérivée) au lieu de `buf` : la relecture va toujours dans `buf` et `verified` n'a plus de choix à faire ; `ndir` retiré ; `nm` aliasé sur `blk` (il meurt avant la première lecture) | CODE −60, BSS −19 | −192 | **oui** |
| `nv[5]` devenu une union avec un mot : `nu.w = v` au lieu d'un appel `putw(nv, v)` | CODE −60 | −132 | **oui** |
| blocs × 512 épelé en opérations d'octet sur les deux octets déjà posés dans `nv` | CODE −8 | −124 | **oui** |
| `hdr[39]` logé dans `stack`, vide entre deux parcours ; la copie faite une fois par le plan au lieu de trois fois par `header()` | CODE +24, BSS −39 | −109 | **oui** |
| `v_memset(f, 0, sizeof *f)` dans `enter()` au lieu de six rangements (sous `#ifdef REPAIR` : les octets de FIXIT ne doivent pas bouger) | CODE −60 | −49 | **oui** |
| `fix(genre)` sans arguments, les six valeurs calculées dans une chaîne de comparaisons | CODE +222 | −271 | non : cc65 passe un argument pour moins cher qu'il ne branche |
| les deux boucles de 512 octets (comparaison de relecture, page de bitmap) parcourues au pointeur ou en deux moitiés indexées sur un octet | CODE +3 / +55 / +190 | — | non |
| `on` porté à 16 bits, un bit par contrôle réparable, `BIT[11]` : la question `k > 3 \|\| (on & BIT[k])` devient une seule | CODE +159 | — | non |
| `#pragma codesize (50 / 80 / 90)` | CODE +1 645 / +1 480 / +1 474 | — | non |
| `#pragma codesize (110 / 120 / 150 / 200 / 400)` | CODE +0 / +1 / +9 / +518 / +504 | — | non : 100 reste l'optimum |
| `b`, le numéro de bloc absolu de la boucle de bitmap, remplacé par `base + n` (les constats de REPAIR jettent le bloc, la macro ne l'évalue même pas) | CODE −10 | −22 | **oui** |
| la seconde passe jugée sur `!found` au lieu d'une boucle sur les onze compteurs : plus court **et** plus honnête (un volume qui « reste à 3 constats » ne se dit plus réparé) | CODE −57 | +82 | **oui** |
| `M_CANCEL` retiré de REPAIR, Échap répondant `Scan incomplete: no repair.` | CODE −12, RODATA −49 | +82 → +21 | **non**, repris : la place trouvée ailleurs paie le message |
| le `stop()` en tête de `fix()` : sans lui, une deuxième correction sur un bloc encore dans `blk` — donc sans relecture pour l'arrêter — s'écrivait après une restauration ratée (montage `two_faults_on_one_entry` : 4 écritures au lieu de 2) | CODE +9 | +12 | **oui**, obligatoire |

Mesure au lien des incréments 9 à 15, 65C02 : CODE 6 791 (fin `$35CD`),
RODATA 1 015 (`$39C4`), DATA 3, BSS 1 482 (fin `$3F91`), fichier
7 880 octets, **12 octets libres** sous `$3F9D` ; 6502 : les mêmes tailles,
fin `$3F91`, fichier 7 880 octets, **12 libres**. `build/fixit.PLG` fait
toujours 7 819 octets et
`build-6502/fixit.PLG` 7 805, aux empreintes SHA-1
`b440a94748c56461ea56af0f231edfcddaa14038` et
`04979b23af23bf77b04fedcdfc41696e59cc9545` : toutes les retouches du
parcours partagé sont sous `#ifdef REPAIR`.

Les **onze** contrôles réparables sont donc tous appliqués. Ce qui n'est pas
entré, et qui est dit en section 5 : le regroupement des corrections d'un
même bloc en **une** écriture. Il demande une liste de rustines — l'offset,
la longueur et les octets d'origine de chaque correction en vol — que la
fenêtre ne porte pas (jusqu'à 95 octets d'originaux et 84 d'index pour les
vingt-six corrections que treize entrées peuvent réclamer), et un tampon de
plus, ou un cache à écriture différée vidé à chaque lecture dans `blk`. Un
bloc qui porte plusieurs corrections est donc écrit une fois **par
correction**, chaque écriture relue et comparée, chacune portant déjà celles
d'avant (`blk` garde les rustines posées). La seule paire qui partage une
écriture est `DIR_BLOCKS` avec `DIR_EOF`, cinq octets contigus d'une entrée.

Les risques et les recours, dans
l'ordre :

1. cc65 produit 450 à 600 octets par copie d'une boucle
   ([MEMORY-BUDGETS.md](MEMORY-BUDGETS.md)) : une seule boucle de parcours, un
   seul `readblock`, un seul `verified`, jamais deux variantes ;
2. chaque appel de service coûte 25 à 40 octets de glu ; les talons de 6 octets
   de `volname.c` ont ramené 1 712 octets à 1 087 ;
3. `blk` sert de tampon de relecture pendant l'écriture : 512 octets gagnés ;
4. si le lien déborde encore, l'export du rapport sort de FIXIT ; VOLINFO
   reste le bon outil pour décrire ;
5. en dernier recours, le chantier WRITE devient une surcouche séparée qui
   refait sa propre passe avant de proposer un plan. Aucun état ne survit
   entre deux surcouches : le noyau reconstruit `$2000-$3FFF` au retour.

## 5. Chantier WRITE : les plans de réparation

### Ce que REPAIR fait, tel qu'il est livré (16 septembre 2026)

Trois passes, et la mémoire n'en garde aucune liste :

1. **le plan** : le parcours entier, qui remplit `counts[]`, le nombre de
   pages de bitmap que chaque contrôle touche par fenêtre de 4 096 blocs, et
   `dblocks`, le nombre d'écritures de répertoire que l'application fera ;
2. **l'application** : le **même** parcours refait, fenêtre par fenêtre.
   Chaque correction de répertoire est écrite **là où le parcours calcule sa
   valeur** ; la page de bitmap corrigée est **recalculée** de `seen[]` et de
   la page telle qu'elle est sur le disque. Écrire une page de bitmap ne
   change rien de ce dont le parcours dépend — le parcours lit l'arbre des
   répertoires, jamais la bitmap — donc parcourir puis écrire, fenêtre par
   fenêtre, est correct ; écrire un bloc de répertoire le change, et c'est
   voulu : le bloc corrigé reste dans `blk`, qui est le cache du parcours ;
3. **la seconde passe de lecture**, obligatoire : le verdict ne dit
   `repaired` que si la passe revient **sans aucun constat** — pas même un
   que REPAIR n'a jamais proposé de réparer. Sinon il compte ce qui reste.

Cinq décisions que la préparation laissait ouvertes, et pourquoi :

- **Il n'y a pas de table de plan.** La table `plan[32]` de la section 4 ne
  tenait pas : `plan_add` et ses sept sites d'appel coûtaient 632 octets de
  code et 205 de BSS, dans une fenêtre où il en manquait déjà 500. Et elle
  n'était pas nécessaire : la valeur qu'une correction de répertoire écrit
  est celle que le parcours calcule, et la passe d'application refait le
  parcours. Les corrections de répertoire sont donc écrites **là où le
  parcours les calcule**, exactement comme les pages de bitmap le sont ;
  `counts[]` compte combien il y en a de chaque sorte, et c'est tout ce que
  l'écran de plan a besoin de savoir. Le plafond de 32 disparaît avec la
  table, et avec lui la question de son débordement : une passe
  déterministe qui refuse au-delà de 32 ne serait jamais réparée en
  « plusieurs passes », puisque la deuxième buterait sur le même plafond.
- **Les onze corrections sont appliquées.** La bitmap (incréments 10 à 12)
  et les sept corrections de répertoire (13 et 14). Il n'y a plus de refus
  `Directory repairs: next increment.`
- **Les tampons.** Il y a deux zones de 512 octets dans cette fenêtre et pas
  une troisième : `blk`, où le parcours lit chaque bloc de répertoire, et
  `buf` (`api->copy_buf`). `seen`, la bitmap des blocs atteints de la
  fenêtre, est **vivante** du `memset` d'`audit()` jusqu'à la comparaison de
  la page, donc elle ne peut servir de tampon de relecture que là où elle
  est déjà morte : la page de bitmap, construite d'elle puis écrite. Une
  correction de répertoire n'a pas ce moment : elle s'écrit au milieu du
  parcours. Ce qui lui épargne un troisième tampon est sa **taille** — deux
  à cinq octets. Le bloc original reste dans `blk`, les octets que la
  rustine remplace sont gardés dans `nv[]`, et la rustine est posée dans
  `blk` **sur place** par un échange : `nv[]` revient donc chargé de ce que
  le bloc portait, et refaire le même échange est la restauration. `blk` est
  ensuite écrit et la relecture va dans `buf`, qui à cet instant ne porte
  rien dont le parcours ait besoin (le bloc d'index d'un fichier y a été lu,
  mais la correction vient après). Ainsi `blk` est à la fois ce qui a été
  écrit et, l'échange refait, l'original : la restauration de la séquence
  ci-dessous est une écriture de `blk` dans les deux cas, et la comparaison
  reste les 512 octets entiers. La page de bitmap suit la même règle une
  fois construite **dans `seen`** au lieu de `buf` : la relecture va
  toujours dans `buf`, et `verified()` n'a plus de choix à faire.
- **L'ordre des écritures.** Avec le parcours-puis-écriture par fenêtre,
  l'ordre naturel est : les blocs de répertoire de la fenêtre 1 au fil du
  parcours, puis la page de bitmap de la fenêtre 1, puis les fenêtres
  suivantes — où plus aucune correction de répertoire n'a lieu, l'arbre
  étant le même dans toutes les fenêtres et les corrections n'étant
  comptées et appliquées que dans la première. Les blocs de répertoire
  précèdent donc **toutes** les pages de bitmap. C'est l'inverse de l'ordre
  annoncé plus bas (« d'abord les pages qui ne font que marquer utilisé »),
  et c'est assumé : une correction de compteur interrompue ne laisse rien de
  pire qu'avant, puisque la bitmap n'a pas bougé. Le risque que l'ordre
  annoncé visait est l'autre : une page qui **libère** écrite avant une
  correction de répertoire qui échoue. Il ne se présente pas — aucune page
  n'est écrite avant les corrections de répertoire — et s'il se présentait
  il serait sans conséquence : le parcours a calculé les blocs perdus contre
  le répertoire **non réparé**, donc un bloc rendu reste un bloc que
  personne ne réclame, que la correction de répertoire réussisse, échoue ou
  soit restaurée. Aucune troisième passe n'est donc nécessaire.
- **Un bloc peut être écrit plusieurs fois.** Le regroupement « un bloc,
  une écriture » n'est pas entré (section 4) : il demande une liste de
  rustines que la fenêtre ne porte pas. Chaque correction est une écriture
  vérifiée, et chacune emporte celles d'avant, `blk` gardant les rustines
  déjà posées. Le montage de `tools/test_repair.py` écrit ainsi le bloc 2
  trois fois — un `ENT_HEADER_PTR`, un `FILE_BLOCKS`, puis le `FILE_COUNT`
  que seule la fin de la chaîne connaît. La sûreté n'en souffre pas : à
  chaque étape l'original est en RAM, l'écriture est relue et comparée, et
  une restauration ramène l'état d'avant **cette** écriture. Ce qui en
  souffre est le temps, et le nombre d'instants où une coupure de courant
  peut tomber. La seule paire qui partage une écriture est `DIR_BLOCKS`
  avec `DIR_EOF` : cinq octets contigus, `+$13..$17`, lus du même nombre de
  blocs.

**Ce que REPAIR ne contrôle pas**, faute de place, et qu'il ne répare de
toute façon jamais (section 5, « refus explicites ») : `ENT_NAME`,
`ENT_ACCESS`, `FILE_EOF`, `HDR_NAME`, `VOLDIR_SIZE` et `DIR_HEADER`. FIXIT
les nomme tous les six ; REPAIR ne les voit pas, et dira donc d'un volume
qui ne porte que ceux-là qu'il n'a rien à réparer. `tools/test_repair.py`
tient cette liste (`DROPPED`) et vérifie qu'elle est écrite ici.
REPAIR n'affiche pas non plus la ligne `Blocks %u..%u / %u` du parcours :
elle coûtait 85 octets qui n'existaient pas.

Une correction est la réécriture d'un seul bloc. Aucune correction ne suppose
qu'une autre a réussi. Les valeurs écrites viennent toutes du parcours, jamais
d'une supposition.

| Id | Action exacte |
| --- | --- |
| `BM_RESERVED` | dans `bitmap + (b>>12)`, `octet[(b&4095)>>3] &= ~(0x80 >> (b&7))` |
| `BM_USED_FREE` | même opération, pour chaque bloc référencé marqué libre |
| `BM_TAIL` | mêmes bits mis à 0 pour tout bloc ≥ `total_blocks` |
| `BM_LOST` | `octet |= 0x80 >> (b&7)`, seulement si la passe est complète et sans entrée partielle ni `XLINK` |
| `FILE_COUNT` | en-tête du répertoire, `+$21..$22` = entrées comptées |
| `DIR_BLOCKS`, `FILE_BLOCKS` | entrée chez le parent, `+$13..$14` = blocs atteints |
| `DIR_EOF` | **répertoires seulement**, `+$15..$17` = `blocks_used × 512` |
| `DIR_PARENT` | en-tête du sous-répertoire, `+$23..$24` = bloc porteur, `+$25` = rang + 1, `+$26` = 39 |
| `ENT_HEADER_PTR` | entrée, `+$25..$26` = bloc clé du répertoire qui la porte |
| `DIR_CHAIN` | `+$00..$01` = bloc précédent réel ; le chaînage **avant** fait foi et n'est jamais reconstruit |

Les onze sont appliquées depuis les incréments 13 à 15. `DIR_BLOCKS` et
`DIR_EOF` partagent une rustine de cinq octets, `+$13..$17` : les deux
champs sont réécrits du même nombre de blocs, et celui qui était déjà juste
garde ses propres octets.

Refus explicites :

- `XLINK`. Ne jamais désigner un gagnant. Le message reprend la règle de
  [DATA-SAFETY.md](DATA-SAFETY.md) pour MOVE : `Cross-linked blocks: copy both
  files to another volume before any repair.` Tant qu'un `XLINK` subsiste,
  `BM_LOST` est refusé aussi.
- `ENT_KEY`, `IDX_RANGE`, et de même `ENT_STORAGE`, `FORK_STORAGE`. Tronquer
  un fichier est une perte. Plus tard, et seulement ainsi : choix fichier par
  fichier, entrée d'origine conservée en RAM et réécrite si la troncature
  échoue. Tant qu'une de ces entrées partielles subsiste, `BM_LOST` est
  refusé : les blocs perdus sont peut-être ceux que l'entrée n'atteint plus,
  et RESCUE ou UNDELETE peuvent encore les lire.
- `DIR_LOOP`, `DIR_DEPTH`, `VOLDIR_SIZE`, `ENT_STORAGE`, `DIR_HEADER`,
  `FORK_STORAGE`, `ENT_NAME`, `FILE_EOF`, `ENT_ACCESS`. Réparer voudrait dire
  inventer, ou toucher ce que ProDOS tolère. Jamais dans un plan.
- `HDR_*`, `IO_ERROR`. Le plan entier est refusé.

Ordre des écritures, **tel que la préparation l'annonçait** — ce qui est
livré l'inverse, et la raison en est donnée plus haut (« L'ordre des
écritures ») :

1. regrouper par numéro de bloc : un bloc n'est réécrit qu'une fois, toutes
   ses corrections appliquées ensemble en RAM avant l'écriture ;
2. d'abord les pages de bitmap qui ne font que **marquer utilisé**
   (`BM_RESERVED`, `BM_USED_FREE`) : une interruption y laisse le volume plus
   prudent qu'avant ;
3. ensuite les blocs de répertoire, compteurs et liens ;
4. enfin les libérations `BM_LOST`. Si une page porte les deux sortes, elle est
   écrite une fois avec les deux : la condition de passe complète a déjà été
   exigée, il n'y a plus de gradation à préserver.

Livré : les blocs de répertoire d'abord, dans l'ordre du parcours, puis les
pages de bitmap dans l'ordre des fenêtres ; le point 1 n'est tenu que pour
la paire `DIR_BLOCKS`/`DIR_EOF` (section 4).

Séquence par bloc, sans exception :

Correction de répertoire, telle qu'elle est écrite :

```
blk porte le bloc, lu par le parcours : c'est l'original
échanger les 2 à 5 octets de la correction entre blk et nv[]
WRITE_BLOCK b <- blk
READ_BLOCK  b -> buf           /* la relecture, dans l'autre tampon */
comparer buf et blk sur 512 octets
```

Page de bitmap, la même séquence : la page corrigée est construite dans
`seen`, mort une fois la page dérivée ; `blk` garde la page telle qu'elle est
sur le disque ; la relecture va dans `buf`.

Sur erreur d'écriture, erreur de relecture ou différence : le même échange
est refait — `nv[]` porte les octets d'origine, `blk` redevient l'original —
puis `WRITE_BLOCK b <- blk`, relecture et comparaison de la restauration.
Pour une page de bitmap c'est `blk`, jamais touché, qui est réécrit. Si la
restauration échoue à son tour, le bloc est nommé dans la note, le parcours
s'arrête là et rien d'autre n'est tenté :
`Block %u not restored: recover this volume before using it.` Une erreur
signalée peut avoir atteint le disque : la restauration est donc tentée dans
tous les cas, comme dans `bootblk.c` et dans le `fail:` de `move.c`. Une
correction dont la restauration a **réussi** ne stoppe pas le parcours : les
corrections sont indépendantes, et le verdict comptera ce qui reste.

Les originaux vivent en **RAM principale seulement**, comme BOOTBLK : aucune
banque auxiliaire, aucun `/RAM`, aucun temporaire sur le volume suspect. Un
seul original à la fois, celui du bloc en vol, ce qu'exige la règle « original
récupérable jusqu'à la relecture et à la comparaison » ; les blocs déjà
corrigés ont été relus et comparés. Cette sauvegarde ne survit pas à une
coupure de courant, et ce document ne promet rien d'autre.

Confirmation puis vérification :

1. l'écran de plan donne, par contrôle, le nombre de corrections et de blocs
   touchés, puis la liste des blocs ;
2. le disque est relu et comparé avant d'écrire, comme MOVE le fait après sa
   question, en-tête de volume compris : une disquette échangée pendant la
   question ne reçoit pas des numéros lus sur l'autre ;
3. `api->prompt("Type FIX to confirm", 0, 0)` puis `strcmp(api->input, "FIX")`.
   Le dépôt réserve `ERASE` à ce qui détruit (WIPE W, DISKIMG). Un plan FIXIT
   ne détruit pas un fichier, mais il rend des blocs réutilisables : il mérite
   un mot tapé, et un mot **différent**, pour qu'un réflexe acquis sur WIPE ne
   déclenche pas une réparation ;
4. application, puis **seconde passe de lecture obligatoire**. La note ne dit
   `repaired` que si la passe ne rapporte **plus aucun constat** ; sinon
   `Applied %u of %u blocks; rescan still reports %u findings.` compte ce
   qu'elle voit encore. Un volume à blocs partagés, dont les corrections de
   répertoire et les pages « marquer utilisé » ont bien été appliquées mais
   dont l'`XLINK` et les blocs perdus subsistent, tombe donc dans le second
   cas : dire `repaired` et compter des constats dans la même phrase serait
   se contredire. `%u of %u blocks` compte les **écritures**, une par
   correction de répertoire plus une par page de bitmap.

## 6. Interface

```
liste des volumes ou chemin -> sélection -> en-tête -> parcours -> constats
                                                          |
                                                R relance   (P plan   F fix)
```

- **Parcours** : `FIXIT /VOL - READ ONLY`, puis `Scanning... ESC cancels.` et
  `Blocks %u..%u / %u` par fenêtre, réécrit en ligne 4. Le test d'Échap lit
  `$C000` et acquitte par `$C010`, comme `volinfo.c`.
- **Constats** : une ligne par contrôle non nul, id, compteur, premier bloc
  et, quand le constat en porte un, le rang de l'entrée ; 18 lignes par page,
  `Key: next / ESC: back`. Un contrôle dont le premier constat est tombé
  au-delà des seize échantillons n'affiche que son compteur, et la ligne
  `more findings than the table holds` le dit.
- **Résumé** : la dernière ligne de la liste, `%u findings.  R rescan
  ESC/RETURN back`, compte tous les constats, y compris ceux que la table
  d'échantillons n'a pas gardés.
- **Touches du chantier Read** : `R` relancer, `ESC` ou `RETURN` sortir ;
  toute autre touche réaffiche la liste. `R` refait **tout** — l'en-tête est
  relu et rejugé, les compteurs et les échantillons sont vidés — parce que
  la disquette a pu être changée ; le nom du volume, lui, reste celui
  qu'`ON_LINE` a donné au lancement, et une disquette échangée se dénonce
  donc par un `HDR_NAME`.
- **Touches absentes** : `P` plan et `F` réparer appartiennent au chantier
  WRITE et n'apparaissent pas tant qu'il n'existe pas. `E` export n'entre pas
  dans la fenêtre (section 4, mesure du 16 septembre 2026, 1 136 octets
  contre 11 libres) : reporté à une surcouche séparée, et donc absent lui
  aussi de l'écran.
- Messages en anglais, 79 caractères au plus. Grande surcouche : les derniers
  mots passent par `api->note`, jamais `api->message`, et ni `read_panel` ni
  `draw_all` ne sont appelés, qui reconstruiraient les tables d'entrées
  par-dessus la BSS.

Les messages du chantier Read, tels que `src/plugins/fixit.c` les écrit et
que `tools/test_fixit.py` les recopie :

```
Select a real ProDOS volume.
Volume not on line.
ON_LINE failed.
Invalid volume header: nothing checked.
Block 2 could not be read: nothing checked.
Scanning... ESC cancels.
Blocks %u..%u / %u
Key: next / ESC: back
more findings than the table holds
%u findings.  R rescan  ESC/RETURN back
This volume is consistent: nothing to repair.
%u findings, nothing written: FIXIT only reads.
Scan incomplete: lost blocks unconfirmed, freeing refused.
Scan cancelled: no plan from an incomplete scan.
Read error: this volume was not fully checked.
```

Le verdict, écrit dans `api->note` à la sortie, prend le premier de ces cas
qui s'applique : en-tête illisible, en-tête refusé, parcours interrompu par
Échap, erreur de lecture, passe incomplète, volume cohérent, constats
comptés.

L'interface de REPAIR, telle que `src/plugins/repair.c` l'écrit :

```
sélection -> en-tête -> parcours -> écran de plan
                                       |
                              F -> « Type FIX to confirm » -> écritures
                                       |                          |
                              ESC/RETURN : rien écrit        seconde passe
```

L'écran de plan tient toujours sur une page — onze contrôles au plus —
donc aucune pagination et aucune touche pour redessiner : `F` répare,
Échap ou Entrée sortent, toute autre touche est ignorée. Une ligne par
contrôle, `%s  %u` : son nom et le nombre de corrections. La colonne
« bits / pages » des quatre contrôles de bitmap est tombée avec les
incréments 13 à 15 (section 4) ; la ligne de résumé porte déjà le total des
corrections et le nombre de blocs que le plan écrira. Suivent les refus qui
s'appliquent, puis la ligne de touches.

Les messages de REPAIR, que `tools/test_repair.py` recopie :

```
REPAIR %s
Plan: %u corrections over %u blocks. Nothing written yet.
%s  %u
F fix  ESC back
Type FIX to confirm
Repairing...
Cross-linked blocks: copy both files to another volume before any repair.
Broken entries: lost blocks kept.
That volume holds the running program: repair it from another boot.
Scan incomplete: no repair.
Disk changed: nothing written.
Nothing written.
Applied %u of %u blocks; rescan clean: repaired.
Applied %u of %u blocks; rescan still reports %u findings.
Block %u not restored: recover this volume before using it.
```

Les refus partagés avec FIXIT gardent leurs libellés : `Select a real
ProDOS volume.`, `Volume not on line.`, `ON_LINE failed.`, `Invalid volume
header: nothing checked.`, `Block 2 could not be read: nothing checked.`,
`This volume is consistent: nothing to repair.`, `Scan cancelled: no plan
from an incomplete scan.` et `Read error: this volume was not fully
checked.`

## 7. Tests et bancs

**Harnais hôte** `tools/test_fixit.py`, sur le modèle de
`tools/test_volinfo.py` : le vrai C compilé par `cc` avec `-DFIXIT_HOST`, un
`mock_mli` au-dessus d'une image `.po`, et le fichier relu après chaque
exécution pour prouver qu'il n'a pas bougé. En mode Read, `abort()` sur `$81` :
une écriture est un échec de test. En mode WRITE, chaque `$81` est enregistré
`{block, bytes}` et rejouable.

Deux modes visent la BSS, que rien ne met à zéro et qu'un processus hôte
neuf ne sait pas montrer :

- `after=` appelle `plugin_entry` **deux fois dans le même processus**, sur
  deux volumes différents, comme le noyau rappelle la surcouche restée dans
  la fenêtre. Le second passage doit répondre exactement ce que le passage
  unique sur cette image répond ; le test croise huit images, soit
  cinquante-six paires ;
- `poison=True` remplit chaque statique de `$AA` avant l'appel. C'est lui
  qui tient la promesse de `reset()` : ce qu'il ne remet plus à zéro
  (`total`, `bitmap`, `pages`, `base`, `span`) est écrit avant d'être lu.

**Oracle.** `tools/prodos_check.py` produit les constats en JSON,
`{complete, findings[]}`. `tools/corrupt_prodos.py` applique une corruption
nommée à une image de `tools/mkvolume.py` et publie les constats attendus :
`bitmap_free_used`, `bitmap_lost`, `crosslink`, `key_out_of_range`,
`index_out_of_range`, `file_count_high`, `file_count_low`, `blocks_used_wrong`,
`dir_blocks_wrong`, `dir_eof_wrong`, `chain_broken`, `chain_loop`,
`parent_wrong`, `header_ptr_wrong`, `bad_storage`, `bad_name`, `eof_too_big`,
`hdr_bitmap_bad`, `hdr_entry_len`, `hdr_storage`, `fork_bad`, `two_faults`.
Comparaison, pour chaque montage :

1. constats attendus = `corrupt_prodos.py`, recoupés par `prodos_check.py` sur
   l'image corrompue ; un désaccord entre les deux condamne le montage ;
2. constats obtenus = le harnais C, en JSON, mêmes clés ;
3. égalité **exacte** des compteurs par identifiant, du drapeau `complete`, et
   du premier `{block, slot}` pour les identifiants qui en portent un ;
4. les identifiants que le C ne met pas encore en œuvre figurent dans une liste
   d'exclusion écrite dans le test, jamais ignorés en silence.

Les montages de `test_volinfo.py` sont repris comme non-régression : seedling,
sapling creux, tree, fourches étendues, sous-répertoire, cycle, type inconnu,
pointeur hors plage, bloc perdu, bloc partagé, limite de fenêtre à 4 096
blocs, volume de 65 535 blocs.

Injections obligatoires du harnais WRITE :

| Cas | Attendu |
| --- | --- |
| erreur sur la n-ième écriture | original réécrit, relu, comparé, note nommant le bloc |
| relecture différente de l'écriture | même chose, sans se déclarer réparé |
| échec de la restauration | note `Block %u not restored`, plus aucune écriture |
| Échap pendant le plan | arrêt après la correction en cours, compte exact |
| disque changé entre le plan et `F` | refus avant toute écriture |
| volume du programme | refus avant la question |

**Banc POM2** `bench/fixit.py`, port 6849, sur `bench/xplug.py` : volumes
jetables de `mkvolume.py` corrompus par `corrupt_prodos.py`, jamais un disque
personnel. Chantier Read : un volume sain revient « consistent » et sa ligne
de résumé compte zéro constat ; une disquette cassée en dix-sept endroits
remplit la page, chaque identifiant y porte le compteur, le bloc et le rang
de l'oracle, `R` refait le parcours et rend les mêmes lignes, et les deux
disquettes sont relues octet pour octet. Chantier WRITE : un
volume à bitmap fausse se répare puis revient propre ; un volume cassé dans
le **répertoire** et dans la bitmap (`file_count_high`, `dir_eof_wrong`,
`parent_wrong`, `bitmap_lost`) montre les quatre contrôles au plan, les
applique sur `F` puis FIX, et revient propre sur l'hôte avec les seuls blocs
que l'oracle nomme modifiés ; un volume à blocs partagés est refusé ; Échap
à la question ne change pas un octet. POM2 ne
réécrit jamais le `.hdv` d'amorçage : le volume contrôlé est la disquette du
lecteur 2 (`boot_hd(..., floppy2=po)`), relue sur l'hôte par
`tools/prodos_read.py`. Les deux processeurs.

**Disposition** : `make disk` en 65C02 et en 6502. Le lien refuse un
dépassement de fenêtre ; ne jamais relever un plafond pour faire passer une
compilation. FIXIT est ajouté à `PACKAGE_DISKTOOLS` dans
`config/packages.mk`, et `tools/check_images.py` vérifie le contenu exact des
sept supports. `tools/test_release_notes.py` compte les surcouches livrées en
dur (67 avec FIXIT) et `bench/menu.py` attend FIXIT sous « Other ».

## 8. Ordre des travaux

Chantier Read, chaque incrément lie et se teste seul :

1. squelette, sélection du volume, `ON_LINE`, validation de l'en-tête, refus
   image / DOS 3.3 / hors ligne, Échap. Oracle : `test_fixit.py` en mode Read,
   `abort()` sur toute écriture. **Fait le 16 septembre 2026.**
2. parcours repris de `volinfo.c`, consignant `counts[]` et `sample[]`.
   Oracle : les montages de `test_volinfo.py` rendent les mêmes nombres.
   **Fait le 16 septembre 2026** : `test_fixit.py` fait tourner les deux
   harnais sur les mêmes images et compare `shared`/`usedfree`/`lost` et
   `bad + counts` aux identifiants qui les remplacent, écart par écart.
3. `HDR_*`, `VOLDIR_SIZE`, `DIR_HEADER`, `ENT_STORAGE`, `DIR_CHAIN`,
   `DIR_LOOP`, `DIR_DEPTH`. Oracle : `corrupt_prodos.py`.
   **Fait le 16 septembre 2026**, avec `IO_ERROR` et le `HDR_TOTAL` du
   support trop court. Les identifiants comparés à l'oracle sont ceux-là,
   plus `ENT_KEY`, `IDX_RANGE`, `FORK_STORAGE`, `FILE_COUNT`, `DIR_BLOCKS`,
   `FILE_BLOCKS`, `XLINK`, `BM_USED_FREE`, `BM_LOST` et `BM_RESERVED` : ils
   tombaient exacts en portant le parcours, et `BM_RESERVED` était la
   condition pour que `BM_USED_FREE` le soit. Restaient aux incréments 4 à 7
   `DIR_PARENT`, `ENT_HEADER_PTR`, `HDR_NAME`, `DIR_EOF`, `FILE_EOF`,
   `ENT_NAME`, `ENT_ACCESS` et `BM_TAIL` (liste `CLOSED_BY` du test).
4. `ENT_HEADER_PTR`, `DIR_PARENT`, `HDR_NAME`. **Fait le 16 septembre 2026.**
   `ENT_HEADER_PTR` est le `+$25` de l'entrée contre le bloc clé du
   répertoire qui la porte ; `DIR_PARENT` est un constat au plus par
   sous-répertoire, le premier des trois champs (`parent_pointer`,
   `parent_entry_number`, `parent_entry_length`) qui se trompe, et le cadre
   parent du parcours le fournit sans rien stocker de plus ; `HDR_NAME` est
   le seul contrôle qui demande un appareil — le nom du bloc 2 contre celui
   qu'`ON_LINE` a répondu pour cette unité — et l'oracle hôte ne l'émet
   jamais (`DEVICE_ONLY`).
5. `FILE_COUNT`, `DIR_BLOCKS`, `DIR_EOF`, `FILE_BLOCKS`, `FILE_EOF`.
   **Fait le 16 septembre 2026** : `DIR_EOF` est l'eof d'une entrée de
   sous-répertoire contre blocs de la chaîne × 512, comparé octet par octet
   (l'eof fait 24 bits) à la dépile, où le bloc de l'entrée est relu de toute
   façon ; `FILE_EOF` est par **fourche** pour un fichier étendu (bloc = le
   bloc clé, rang 0 ou 1), jamais l'eof de l'entrée `$5` elle-même, et un
   fichier arbre ne peut pas déborder — 32 Mo est au-delà des 16 Mo qu'un eof
   de 24 bits sait épeler.
6. `ENT_KEY`, `IDX_RANGE`, `FORK_STORAGE`, `ENT_NAME`, `ENT_ACCESS`.
   **Fait le 16 septembre 2026** : un nom ProDOS est de 1 à 15 caractères,
   une lettre d'abord, puis lettres, chiffres ou `.` — vérifié sur l'en-tête
   du volume (bloc 2, rang 0), sur l'en-tête de chaque sous-répertoire et sur
   chaque entrée ; `ENT_ACCESS` est le `+$1E` masqué par `$1C`.
7. `BM_USED_FREE`, `BM_LOST`, `BM_RESERVED`, `BM_TAIL` sur les fenêtres de
   4 096 blocs, avec la règle de complétude. Oracle : montage de 65 535 blocs.
   **Fait le 16 septembre 2026** : `BM_TAIL` nomme chaque bit encore levé
   au-delà du dernier bloc du volume dans la dernière page de bitmap ; la
   boucle de fenêtre parcourt les 4 096 bits de la page et non la seule
   étendue du volume ; les autres fenêtres étant pleines, leur queue est vide.
   `tools/test_fixit.py` compare désormais les **trente** identifiants de
   l'oracle, corruption par corruption : `CLOSED_BY` est vide et `NOT_YET`
   aussi.
8. écran de constats, pagination, `R`, `E`, Échap. `bench/fixit.py` en lecture
   seule sur les deux processeurs, `make disk` sur les deux architectures.
   **Fait le 16 septembre 2026**, sauf `E` : l'export coûte 1 136 octets là
   où il en restait 11 (section 4), il sort donc de FIXIT par le recours 4 et
   n'apparaît sur aucun écran. Le reste est livré : une ligne par contrôle
   non nul, 18 lignes par page, la ligne de résumé qui compte les constats,
   `R` qui refait l'en-tête et le parcours en vidant tout, et le verdict
   compté dans `api->note`. Le harnais hôte garde désormais l'écran (`clrscr`
   est un saut de page), rejoue un script de touches et, sur le `R` de ce
   script, change la disquette du lecteur : un deuxième passage ne doit rien
   croire du premier. Le banc casse sa disquette en **dix-sept** endroits, le
   plus qu'un volume puisse porter sans que le parcours s'arrête : avec la
   ligne de débordement cela fait exactement une page, et la pagination se
   voit sur l'Apple II.

Chantier WRITE, dans la surcouche séparée `REPAIR.PLG` :

9. construction et affichage du plan, aucune écriture avant le mot tapé.
   Oracle : le plan comparé aux constats de `tools/prodos_check.py`.
   **Fait le 16 septembre 2026** : l'écran de plan nomme les onze contrôles
   réparables, les quatre de la bitmap avec leurs bits et leurs pages, les
   sept de répertoire avec leur compte ; il n'y a pas de table de plan
   (section 5). La touche `P` n'existe pas : le plan **est** l'écran.
10. l'écriture vérifiée (original, écriture, relecture, comparaison,
    restauration) pour `BM_RESERVED` seul. Oracle : les trois injections
    d'échec. **Fait le 16 septembre 2026**, pour les quatre contrôles à la
    fois : une seule fonction, `blk` porte l'original et le tampon de
    relecture est celui qui est mort à cet instant (recours 3). Depuis les
    incréments 13 à 15 la page corrigée se construit dans `seen` et la
    relecture va toujours dans `buf` (section 5, « Les tampons »).
11. `BM_USED_FREE` et `BM_TAIL`, avec le regroupement par bloc.
    **Fait le 16 septembre 2026** : une page de bitmap est écrite une seule
    fois, avec toutes ses corrections, et n'est pas écrite du tout si ses
    octets ne changent pas.
12. `BM_LOST` derrière la condition de passe complète. Oracle : les refus.
    **Fait le 16 septembre 2026** : `freeing_ok()` est demandé au plan
    **et** de nouveau à chaque page de la passe d'application, et une passe
    d'application incomplète n'écrit rien.
13. `FILE_COUNT`, `DIR_BLOCKS`, `FILE_BLOCKS`, `DIR_EOF` : à écrire là où le
    parcours calcule leur valeur, comme les pages de bitmap le sont déjà.
    **Fait le 16 septembre 2026.** `FILE_COUNT` est écrit à la fin de la
    chaîne, le seul moment où le compte est connu, dans le bloc d'en-tête —
    relu s'il n'est plus celui qu'on a en main ; `FILE_BLOCKS` à la fin de
    `file()`, le bloc de répertoire étant relu si le parcours d'un fichier
    arbre a pris `blk` ; `DIR_BLOCKS` et `DIR_EOF` à la dépile, dans le bloc
    porteur que `subdir_entry` relit de toute façon, et en **une** rustine de
    cinq octets contigus, `+$13..$17`, tirée du même nombre de blocs.
14. `ENT_HEADER_PTR`, `DIR_PARENT`, `DIR_CHAIN` : de même. **Fait le
    16 septembre 2026.** `ENT_HEADER_PTR` est écrit sur l'entrée examinée,
    `DIR_PARENT` sur les quatre octets `+$27..$2A` de l'en-tête du
    sous-répertoire (bloc porteur, rang + 1, 39), `DIR_CHAIN` sur les deux
    premiers octets du bloc de répertoire — le chaînage **avant** n'est
    jamais reconstruit. Les sept passent par une seule fonction, `fix()`,
    qui refuse les fenêtres autres que la première, compte le bloc au lieu
    de l'écrire pendant la passe de plan, et ne fait rien pendant la
    seconde. Les sept réparations ont coûté 709 octets à trouver dans une
    fenêtre qui en avait 38 : le journal des formes est en section 4.
15. confirmation `FIX`, garde du disque changé, refus du volume du programme,
    seconde passe obligatoire, libellés définitifs. `bench/repair.py` sur les
    deux processeurs, octets relus sur l'hôte.
    **Fait le 16 septembre 2026** : `F` puis
    `api->prompt("Type FIX to confirm", 0, 0)` et `strcmp(api->input,
    "FIX")` ; le bloc 2 relu et comparé — les trente-neuf octets de son
    entrée d'en-tête, copiés par la passe de plan — avant la première
    écriture ; le volume du programme refusé avant la première lecture ; la
    seconde passe obligatoire, dont le verdict ne dit `rescan clean:
    repaired` que si elle ne rapporte **plus aucun constat**, de répertoire
    ou non, et compte sinon ce qu'elle voit encore.

Ce que le chantier WRITE tient déjà, et qui ne changera plus : aucune
écriture avant le mot, un seul `verified`, un seul `readblock`, les
originaux en RAM principale seulement, et `tools/test_repair.py` qui
enregistre chaque `WRITE_BLOCK` — bloc, octets, rang — puis relit l'image
et compare les octets, jamais le seul message.

Rappel pour finir : [TODO.md](../TODO.md) garde FIXIT fermé tant que la case
« Pannes combinées » n'est pas cochée. Ce document est une préparation, pas
une autorisation de commencer.
