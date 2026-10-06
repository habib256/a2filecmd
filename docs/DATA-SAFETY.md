# Sécurité des données d’A2FC

La conservation des données est une exigence centrale. Les instructions
obligatoires pour les IA et les contributeurs se trouvent dans
[AGENTS.md](../AGENTS.md). Cette revue du 11 septembre 2026 porte sur les
chemins d’écriture, de remplacement, d’effacement et d’utilisation de la
mémoire auxiliaire. Elle ne constitue pas une garantie contre toute panne
matérielle ni une preuve exhaustive de l’absence de défauts. Le tableau et
les listes ci-dessous ont été revérifiés contre le code le 6 octobre 2026
(branche release-0.9.6) ; les chiffres de validation datés plus bas restent
ceux de leur campagne. Le contrat commun des fichiers et ses aides sont dans
[FILE-SERVICES.md](FILE-SERVICES.md).

Le 12 septembre 2026, le mainteneur confirme une validation réussie sur
matériel réel : Apple //c, IIe enhanced et IIe unenhanced. Des testeurs
ont depuis fait tourner A2FC sur leurs machines, sans défaut rapporté.
Ce retour complète les tests automatisés. Voir le
[suivi de stabilisation](history/STABILIZATION.md#validation-sur-matériel-réel).

## Risques corrigés

| Opération | Risque constaté | Protection et régression |
| --- | --- | --- |
| Copie C et déplacement V | Destination supprimée avant la copie ; source supprimable sans relecture de la destination | Copie dans `A2FC.COPY`, créé exclusivement à côté de la cible ; contrôle des lectures/écritures/fermetures, puis comparaison intégrale des deux flux et de leur taille (`copy_check`). Ensuite seulement, l’ancienne destination passe en `A2FC.BAK`, la copie prend son nom et `A2FC.BAK` est supprimé ; un `A2FC.BAK` préexistant refuse le remplacement avant le premier octet. Restauration sur erreur (`src/file_copy.h`). `test_file_safety.py`, `bench/data_safety.py`, `bench/ops.py`. |
| Parcours récursifs | Lecture courte d’un répertoire assimilée à sa fin ; noms corrompus susceptibles de rediriger un chemin | Un lien de continuation doit être lisible intégralement. Noms ProDOS contrôlés avant utilisation ; `list_dir` transmet l’erreur et empêche de considérer la copie comme complète. `test_core_dirscan.py`. |
| C, V et D sur un dossier | Dossier copié sur l’un de ses ancêtres (`/V/A` vers `/V` : `/V/A/A/A` écrit dans la source, puis effacé par le déplacement) ; arbre à moitié supprimé quand le chemin d’un fichier ne tient pas | `paths_nested` (`src/a2fc_mli.s`) refuse un dossier copié dans lui-même, dans un descendant ou sur un ancêtre. Le comptage de `walk_tree` (`src/tree_walk.h`) contrôle le chemin de chaque fichier et dossier source, pas seulement des dossiers : l’arbre trop profond est refusé entier avant tout effacement, et avant le premier octet d’une copie marquée. Les chemins de destination sont contrôlés pendant la copie, qui s’arrête alors source conservée. `test_tree_walk.py`, `test_keep_tags.py` (modèle de `paths_nested` sur les deux processeurs). |
| Marques après une grande surcouche | Marques rendues par index à un panneau qui avait changé (MOVE, GOTO, FIND, extraction, éditeur, autre fenêtre d’un grand dossier) : D supprimait alors d’autres fichiers que ceux choisis | `keep_tags` ne rend les marques qu’à un panneau de même chemin, mêmes noms et mêmes types aux mêmes index ; sinon il revient sans marque. Limite : l’empreinte `panel_hash` fait 16 bits, un panneau changé sur 65 536 passe pour inchangé. `test_keep_tags.py` (vrai assembleur sous sim65, 6502 et 65C02). |
| Éditeur E | Ouverture tronquante de l’original ; lecture initiale incomplète acceptée | Écriture exclusive dans `A2FC.EDIT`, fermeture et relecture octet par octet avant installation ; original conservé sous `A2FC.ED.BAK` pendant le renommage. Une sauvegarde échouée conserve le tampon modifié. `test_file_safety.py`, `bench/data_safety.py`. |
| Binary II, ShrinkIt, extraction ProDOS/DOS 3.3 | Écrasement silencieux de fichiers existants ; erreurs de fermeture ignorées | Création exclusive commune, aucune suppression d’un fichier préexistant en nettoyage, contrôle de fermeture. Bornes supplémentaires des noms et chemins Binary II/ShrinkIt ; erreurs des grandes surcouches conservées dans le message final. |
| TXTCONV | Suppression de la source avant renommage ; suppression immédiate d’une destination confirmée | Conversion dans un temporaire exclusif, contrôle du nombre d’octets lus et des fermetures, installation avec sauvegarde et restauration. Temporaires et sauvegardes existants conservés. `test_txtconv.py`, `bench/txtconv.py`. |
| IMGCONV | Sonde `fopen(rb)` confondue avec une preuve d’absence ; suppression avant conversion | GET_FILE_INFO distingue absence et erreur ; CREATE exclusif ; conversion temporaire avant remplacement avec sauvegarde. `test_imgconv_safety.py`, `test_imgconv.py`, `bench/imgconv.py`. |
| MOVE, déplacement rapide sur un volume | Erreur entre les écritures brutes laissant deux entrées partageant les mêmes blocs ; backlink de sous-répertoire non validé | Validation du backlink et du stockage ; relecture des écritures ; sur erreur signalée, restauration de l’entrée source, du backlink et des compteurs avant suppression de la copie d’entrée. Avertissement interdisant de supprimer les entrées si la restauration échoue. Tests avant **et après** écriture effective à chaque étape dans `test_move.py`, puis `bench/move.py`. |
| WIPE F | Bitmap déclarant libre un bloc encore utilisé : le mode « espace libre » effaçait des données vivantes | Précontrôle de tous les blocs référencés par les répertoires et les fichiers seedling/sapling/tree, bornes et bits d’allocation. Aucune écriture si lecture impossible, structure non prise en charge, cycle détecté ou annulation. `test_wipe.py`. |
| DISKIMG | Image source tronquée ou 2MG malformée acceptée avant écriture destructrice ; possibilité de cibler le volume contenant l’image | Validation de la taille réelle, du format, de la plage de données et des pistes DSK. Volume source protégé comme cible ; refus de lire un disque dans une image située sur ce même volume ; disque RAM exclu des transferts bruts utilisant AUX. `test_diskimg_input.py`, `test_diskimg_verify.py`. |
| Images, ShrinkIt, copies de disque et formatage physique | Utilisation d’AUX détruisant le disque RAM avec un avis seulement après coup | Drapeau `OVERLAY_AUX` (ou `aux_consent` pour une surcouche qui en décide elle-même) et confirmation explicite avant utilisation, également pour une surcouche déjà chargée ; confirmation dédiée avant le formatage physique. Pas de question quand `/RAM` est en ligne et sans fichier (`ram_empty`, `src/a2fc_mli.s`). La reconstruction reste permise pour libérer de la mémoire. `bench/data_safety.py` compare les octets AUX avant/après refus ; `test_overlay_load.py` et `test_ram_empty.py` couvrent la décision. |
| Ctrl-Reset dans un visualiseur AUX | `/RAM` laissé en ligne, son catalogue intact sur des blocs que le visualiseur avait écrasés | `confirm_aux` lève `aux_dirty` dès que l’accord est donné, la boucle principale le baisse, et la sortie de `src/crt0.s` appelle `ram_format` tant qu’il est levé. `test_overlay_load.py` contrôle le drapeau sur chaque issue de l’accord. Pas encore rejoué dans POM2 avec des fichiers sur `/RAM`. |
| BLKEDIT | Tampon déclaré propre après échec de relecture de contrôle | Le tampon reste modifié pour permettre une nouvelle tentative ou un abandon explicite. |
| IMGFS, extraction d’une image ouverte comme dossier | Sortie fermée sans relecture ; fichier arbre (> 128 Ko) créé puis supprimé | Réservation exclusive après le refus des fichiers arbre ; chaque fichier écrit, fermé, puis relu bloc par bloc contre l’image ; octet faux, réouverture impossible, lecture courte ou image perdue en seconde passe retirent le fichier possédé. `test_imgfs_safety.py`, `bench/run.py`. |
| UNSHRINK | Fil décodé une seule fois ; écriture acceptée sur la seule fermeture | Après fermeture, retour au début du fil et second décodage (stocké, LZW/1, LZW/2) comparé au fichier relu, fin du fichier contrôlée ; `reads back different` retire le fichier possédé. Un enregistrement de type `$0F` (dossier) porteur de données est sauté, comme dans BINARY2, SCIIBIN et UNWRAP ; une fourche de ressources, une compression non prise en charge ou un type impossible sous ProDOS sont comptés dans « N file(s) extracted, M part(s) skipped. » au lieu d’être tus. `test_unshrink_safety.py`, `bench/shk.py`. |
| FIND, lecteurs de texte | Erreur de lecture prise pour une fin : recherche déclarée `complete` après un dossier illisible, `(end)` affiché sur un fichier tronqué par une erreur | `dir_close` rend l’indicateur d’erreur du résident ; FIND marque alors la recherche « some paths skipped ». T, le lecteur BASIC et le lecteur AppleWorks affichent `(READ ERROR)` et, au 80e écran d’un fichier plus long, `(page limit)`. `test_find.py`, `test_text_viewer.py`. |
| VDrive | Le pilote prenait l’emplacement d’une unité SmartPort ou ProFile (ou de `/RAM`, `$BF`) pour libre, et ses deux entrées DEVADR : le volume disparaissait pendant la session | Seul le numéro d’emplacement de DEVLST est comparé (`src/vsdrive.s`). `test_vsdrive.py` (sim65). Pas observé sur une machine équipée d’une telle carte. |
| BOOTBLK | Premier bloc écrasé avant lecture du second ; aucune vérification ni restauration | Lecture préalable des deux blocs source et des deux blocs d’origine. Chaque écriture est relue et comparée. Sur erreur, restauration et vérification des deux originaux ; avertissement distinct si elle échoue. `test_bootblk.py` injecte les erreurs avant et après écriture effective, ainsi que les corruptions silencieuses et les échecs de restauration. |

## Autres chemins d’écriture examinés

- **SYNC** : copie dans `A2FC.SYNC` créé exclusivement, comparaison complète,
  sauvegarde `A2FC.BAK` (refus s’il existe) puis installation ; source
  conservée. `test_six_plugins.py` (pannes, fermetures, tailles périmées,
  échecs de renommage et de restauration).
- **Déplacement marqué (MOVE)** : la liste `A2MOVE.LST`, créée exclusivement
  dans la destination, porte un CRC par enregistrement ; un panneau ou une
  source changés arrêtent le lot, sources restantes conservées. `test_batch.py`,
  `bench/batch_missing.py`.
- **GOTO** : signets écrits dans `GOTO.TMP` créé exclusivement, installés avec
  `GOTO.BAK` comme sauvegarde (`file_install.h`). `test_goto_safety.py`,
  `bench/goto.py`.
- **RESCUE et UNDELETE** : destination sur un autre volume, création exclusive,
  source ouverte en lecture. RESCUE conserve volontairement le résultat partiel
  et son journal ; UNDELETE refuse les blocs réutilisés ou ambigus.
  `test_six_plugins.py`.
- **MKIMAGE, rapports VOLINFO, exports BLKVIEW et DISASM, NRCLIP** : création
  exclusive. Certains exports conservent explicitement un résultat incomplet
  plutôt que de prétendre avoir réussi. `test_six_plugins.py`, `test_volinfo.py`,
  `test_blkview.py`, `test_disasm.py`, `test_nrclip.py`.
- **Extractions UNSQ, SCIIBIN, UNWRAP, CPM, PASCAL** : chaque fichier par
  `newfile` (création exclusive), retiré par `discard` s’il est incomplet.
  `test_unsq.py`, `test_sciibin.py`, `test_unwrap.py`, `test_cpm.py`,
  `test_pascal.py`.
- **Écritures dans une image ou un disque étranger** (IMGPUT, PASCALW, CPMW
  dans une image ; DOSWRITE, DOS33W, DOSREPL sur un vrai disque DOS 3.3 ;
  DOSIMAGE/DOSPUT dans une image DOS 3.3) : écritures brutes hors de ProDOS.
  Chacune explique d’abord le volume ou n’écrit rien, écrit les données dans
  des blocs ou secteurs que rien ne désigne encore, les relit, puis publie
  l’entrée ; l’ordre est décrit en tête de chaque source. DOSIMAGE/DOSPUT
  passent par une copie `A2FC.DOS` et `A2FC.BAK` (`dosimage_io.h`).
  `test_imgput.py`, `test_pascalw.py`, `test_cpmw.py`, `test_doswrite.py`,
  `test_dos33w.py`, `test_dosrepl.py`, `test_dosimage.py`.
- **Suppression, renommage et attributs** : confirmations des suppressions,
  opérations ProDOS pour les fichiers ordinaires, erreurs propagées. RENAME
  ProDOS refuse une destination existante, ce sur quoi s’appuient les
  surcouches RENAME (`bench/rename.py`) et FIXTYPES (`bench/fixtypes.py`) ;
  VOLNAME refuse en plus le nom d’un autre volume en ligne
  (`bench/volname.py`). DATE ne modifie que les dates (SET_FILE_INFO,
  `bench/date.py`). L’édition brute de blocs et MOVE exigent leurs propres
  contrôles puisqu’ils contournent ces garanties.
- **FORMAT, WIPE W, BOOTBLK** : opérations destructrices explicites, cible
  affichée et confirmation ; protection du volume du programme. BOOTBLK
  modifie les deux blocs de démarrage, pas les blocs de fichiers.
- **REPAIR** : écritures brutes après le diagnostic de FIXIT et une
  confirmation ; voir [FIXIT.md](FIXIT.md).
- **Édition Mini (DOS 3.3)** : ses propres chemins RWTS, décrits dans
  [MINI-DOS33.md](MINI-DOS33.md).

## Fichiers de récupération et limites

Ne pas effacer automatiquement `A2FC.BAK`, `A2FC.COPY`, `A2FC.SYNC`,
`A2FC.DOS`, `A2FC.ED.BAK`, `A2FC.EDIT`, `TXTCONV.TMP`, `IMGCONV.TMP`,
`A2FILE.TMP`, `A2FILE.BAK`, `GOTO.TMP`, `GOTO.BAK` ou `A2MOVE.LST`. Un reste peut être la seule version intacte
après un échec de renommage. Examiner/copier son contenu avant de le renommer
ou de le supprimer. Une collision bloque l’opération concernée.

ProDOS ne fournit pas une transaction couvrant plusieurs écritures physiques.
Une coupure pendant MOVE peut encore laisser des entrées partageant des blocs :
ne supprimer **aucune** de ces entrées avant récupération sur un autre volume.
La restauration ajoutée traite les erreurs renvoyées pendant l’exécution ;
elle n’est pas un journal persistant de reprise après coupure.

FORMAT, WIPE W et les écritures brutes ne sont pas annulables après leur début.
Une défaillance physique persistante peut empêcher une restauration. BOOTBLK
conserve ses deux anciens blocs en mémoire principale pendant l’opération,
sans toucher AUX ni `/RAM` ; cette sauvegarde ne survit pas à une coupure.
Si la restauration échoue, le volume peut ne plus démarrer : effectuer une
récupération avant de réessayer. Une
relecture valide le contenu rendu par le pilote, pas sa persistance après une
perte d’alimentation. Chaque conversion ou extraction vérifie ses écritures et
fermetures ; TXTCONV, IMGCONV, COPY, SYNC, l’éditeur, la configuration, et
depuis le 14 septembre 2026 DOSGET, BINARY2, IMGFS et UNSHRINK, relisent en
plus le résultat fermé en entier et le comparent à ce qui devait être
produit : les blocs de l’image lus une seconde fois, ou le fil de l’archive
décodé une seconde fois depuis son début, contre le fichier rouvert, qui
doit finir où finissent les données. Une relecture qui échoue retire le
fichier possédé et nomme le fichier si ce retrait échoue.

WIPE F refuse les stockages étendus et les profondeurs dépassant sa pile de
parcours ; il privilégie le refus à l’effacement avec un diagnostic incomplet.
La configuration `A2FILE.CFG` est écrite dans `A2FILE.TMP`, réservé
exclusivement, fermée puis relue intégralement (`src/config.h`, `test_config.py`). L'original reste dans `A2FILE.BAK` pendant
l'installation et n'est supprimé qu'après vérification du fichier installé.
Les temporaires et sauvegardes préexistants sont conservés ; une erreur de
restauration laisse les fichiers récupérables et bloque une nouvelle sauvegarde.
Une sauvegarde seule peut être chargée si CFG manque. Cela ne garantit pas une
transaction atomique lors d'une coupure physique.
La résistance des décodeurs aux fichiers malformés est
mesurée par les campagnes de mutations décrites plus bas, pas prouvée :
elles couvrent ce que leurs mutateurs savent produire.

Les lecteurs MB1 et PT3 sont désormais des surcouches au premier plan.
MB1 garde ses données en mémoire principale et préserve `/RAM`. PT3 joue
d'abord avec le lecteur de GROUiK, qui place le module en mémoire
auxiliaire : rien n'y est écrit avant `aux_consent` (pas de question si
`/RAM` est vide, sinon « ALL /RAM files will be LOST »), et dès la première
écriture `/RAM` est reconstruit à la sortie et annoncé, quelle que soit
l'issue. Chaque lecture du module par ce lecteur est bornée au module
(`src/plugins/ppt3/README.md`). Sur refus, pt3_lib joue en mémoire
principale seulement et `/RAM` est préservé.

## Validation et contraintes mémoire

`make test` exécute les tests hôtes, dont les pannes injectées dans les véritables
routines C. `make disk` compile les deux architectures et contrôle les plafonds
résident, pile, BSS et surcouches avant de fabriquer les supports. Les nouveaux
scénarios natifs sont dans `bench/data_safety.py` ; les autres bancs cités plus
haut utilisent également des volumes jetables.

Depuis le 16 septembre 2026, `tools/fuzz_archives.py` mène une campagne de
mutations déterministe sur les quatre lecteurs qui écrivent des fichiers sur un
volume : BINARY2, IMGFS, DOSGET et UNSHRINK — pilote NuFX d'un côté, cœur LZW
assembleur de `src/unshrink.s` sous sim65 et sur les deux processeurs de
l'autre. Chaque cas casse une archive ou une image saine (troncature à chaque
frontière du format, champs de longueur nuls, démesurés ou décalés d'un, noms
illégaux ou de plus de quinze caractères, CRC LZW/1 et CRC de fil NuFX faussés,
chaînes de catalogue DOS 3.3 et listes T/S bouclées ou hors disque, VTOC
incohérente, et les corruptions nommées de `tools/corrupt_prodos.py` pour les
images ProDOS), exécute le vrai C sous ASan et UBSan vers un volume jetable qui
contient déjà des fichiers, puis juge cinq invariants : aucun plantage ni
blocage ; aucun fichier préexistant touché (mêmes octets, même taille, même
date, jamais rouvert en écriture, création toujours exclusive) ; tout fichier
conservé identique octet pour octet à ce que décode le déchiffreur de
référence hôte, aucun fichier partiel gardé ; un message de succès prononcé
seulement sur une entrée lue en entier, et son compte est celui de la
référence ; l'archive ou l'image jamais modifiée. **20 000 cas sur deux graines
(2 000 par lecteur et par graine) : aucun défaut, 44 993 fichiers produits
vérifiés.** La seule divergence relevée est nommée dans la
campagne (`NUFX_16BIT_LOW`) : `struct UsState` réduit les champs 16 et 32 bits
de NuFX à leur partie basse, ce qui rend UNSHRINK plus permissif qu'un lecteur
strict sans jamais perdre ni abîmer un fichier. `make test` en exécute une
tranche déterministe (`--count 60 --seed 1`) suivie de
`tools/test_fuzz_archives.py`, qui plante un défaut par famille de décodeur
pour prouver que chaque invariant mord.

Résultats de la revue du 11 septembre (chiffres historiques, comme ceux des
sous-sections datées qui suivent) : **290 tests hôtes réussis**, huit images contrôlées
(BOOT, EXTRA, EXTRA2 et XL pour 6502 et 65C02), **14/14 contrôles de sécurité
natifs sur chacune des deux architectures** et **72/72 contrôles de session
complète**. Les bancs natifs ciblés passent également : opérations 7/7,
TXTCONV 25/25, IMGCONV 25/25, MOVE 13/13, WIPE 13/13 et FORMAT 31/31. Les bancs
de sécurité des deux processeurs forment le groupe `safety` de `bench/all.py`,
que le travail `bench` de la CI rejoue — seulement sur un exécuteur
auto-hébergé qui a POM2 (variable de dépôt `POM2_RUNNER`) ; sans lui, la CI
n’exécute que `make test` et les contrôles de construction et d’images.

La copie réside désormais dans la petite surcouche interne `COPY.PLG`, livrée
avec BOOT. Elle conserve les deux tables de fichiers pendant les parcours.
L’éditeur réserve davantage de code de protection et accepte **5 104 octets**.
DISKIMG utilise trois blocs de préparation en mémoire principale au lieu de
quatre pour loger ses contrôles supplémentaires. Aucun plafond de mémoire
ni contrôle du lieur n’a été désactivé.

### Validation complémentaire : BOOTBLK et catégories

BOOTBLK passe 11/11 contrôles natifs sur chaque processeur, avec inspection
sur l’hôte des blocs modifiés et conservés. Ses six tests hôtes injectent
également les pannes de prélecture, d’installation, de vérification et de
restauration. Les tests de catalogue couvrent les noms de volumes malformés
pour empêcher un dépassement du tampon de question.

La distribution suivante remplace les huit images mentionnées dans la revue
initiale par **sept supports** : BOOT, FILES, MEDIA, DISKTOOLS et DEVTOOLS en
6502, plus XL en 6502 et 65C02. `config/packages.mk` impose une catégorie
unique à chaque outil absent de BOOT ; le contrôle des images vérifie leurs
contenus exacts. Tous les essais de changements de disque utilisent des copies
jetables.

Validation finale de cette distribution : **300 tests hôtes réussis**, sept
images contrôlées, **22/22 contrôles natifs de catégories et d’échanges de
disquettes**, puis **14/14 contrôles de préservation des données sur chacun
des deux processeurs** avec le nouveau chargeur.

### Aiguillage des visualiseurs

Entrée et I partagent désormais la même classification sur les deux CPUs.
Les métadonnées des formats compressés priment sur une taille ressemblant à
une page brute ; l’album HGR/RLE saute les formats des autres décodeurs.
`OPEN.PLG` calcule le choix puis rend la main au résident avant le chargement
suivant, afin de ne pas remplacer une surcouche en cours d’exécution. Un échec
de chargement ne réutilise pas la commande précédente.

Les 306 tests hôtes passent. `bench/open_images.py` passe 15/15 contrôles sur
chaque processeur : octets décodés, Entrée et I, refus de perte de `/RAM`, H
explicite et album brut. Les sept images sont reconstruites avec OPEN dans
BOOT et les deux XL, sans changer les limites mémoire.
La session complète passe également ses 72 contrôles, dont l’ouverture à la
souris, les autres lecteurs, les opérations sur fichiers et le retour depuis
Applesoft.

### Bug hunt préalable à la 0.7.6

Le [rapport dédié](history/BUG-HUNT-0.7.6.md) consigne les défauts reproduits et leurs
régressions, dont les arbres profonds qui dépassaient la pile. Les parcours
récursifs contrôlent désormais l'espace de pile avant lecture de répertoire ;
la suppression précontrôle l'arbre avant son premier effacement. Les erreurs de
lecture/fermeture de répertoire et les chaînes d'images incohérentes sont refusées.

### NIBCOPY

NIBCOPY écrit physiquement la disquette cible, pistes 0–34, après confirmation
identifiant slot et lecteur et annonçant la perte de tous les fichiers, même
verrouillés. La source doit rester matériellement protégée ; le contrôle de
protection est répété avant chaque écriture. En mode un lecteur, chaque échange
cible demande confirmation. Aucun appel MLI ou chargement de plugin ne survient
pendant la copie : BOOT peut être retiré. AUX n’est touché qu’après l’accord
`OVERLAY_AUX`, et `/RAM` est reconstruit après tout emprunt, même en cas
d’échec (`/RAM not rebuilt` sinon, avec le nombre de pistes vérifiées).

Une panne sur une piste tardive laisse les précédentes copiées, et une erreur
d’écriture peut laisser la piste courante détruite. Aucune restauration ni
atomicité en cas de coupure n’est promise. La carte mémoire, les timings, les
formats acceptés et les tests (`tools/test_nibcopy.py`, `bench/nibcopy.py`)
sont dans [NIBCOPY.md](NIBCOPY.md) ; ces essais ne valent pas qualification
des lecteurs physiques ni des accélérateurs.
