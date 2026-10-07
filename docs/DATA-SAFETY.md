# Sécurité des données d’A2FC

La conservation des données est une exigence centrale. Les instructions
obligatoires pour les IA et les contributeurs se trouvent dans
[AGENTS.md](../AGENTS.md). Cette revue du 11 septembre 2026 porte sur les
chemins d’écriture, de remplacement, d’effacement et d’utilisation de la
mémoire auxiliaire. Elle ne constitue pas une garantie contre toute panne
matérielle ni une preuve exhaustive de l’absence de défauts. Le tableau et
les listes ci-dessous ont été revérifiés contre le code le 7 octobre 2026
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
| C, V et D sur un dossier | Dossier copié sur l’un de ses ancêtres (`/V/A` vers `/V` : `/V/A/A/A` écrit dans la source, puis effacé par le déplacement) ; arbre à moitié supprimé quand le chemin d’un fichier ne tient pas | `paths_nested` (`src/a2fc_mli.s`) refuse un dossier copié dans lui-même, dans un descendant ou sur un ancêtre. Le comptage de `walk_tree` (`src/tree_walk.h`) contrôle le chemin de chaque fichier et dossier source, pas seulement des dossiers : l’arbre trop profond est refusé entier avant tout effacement, et avant le premier octet d’une copie marquée. Le comptage parcourt aussi les chemins de destination : un arbre dont un chemin cible ne tient pas est refusé (« Path too long for ProDOS. ») avant le premier octet. `test_tree_walk.py`, `test_keep_tags.py` (modèle de `paths_nested` sur les deux processeurs). |
| Marques après une grande surcouche | Marques rendues par index à un panneau qui avait changé (MOVE, GOTO, FIND, extraction, éditeur, autre fenêtre d’un grand dossier) : D supprimait alors d’autres fichiers que ceux choisis | `keep_tags` ne rend les marques qu’à un panneau de même chemin, mêmes noms et mêmes types aux mêmes index ; sinon il revient sans marque. L’empreinte `panel_hash` (16 bits) mélange chaque octet de façon non linéaire (rotation, ou exclusif, addition) depuis la seconde chasse : deux entrées échangées à 8 rangs ou « AB » devenu « CA » passaient avec la première. Un album est sauvegardé une fois par session. Limite : une modification quelconque passe encore pour inchangée environ une fois sur 65 536 (`test_keep_tags.py` le mesure). `test_keep_tags.py` (vrai assembleur sous sim65, 6502 et 65C02). |
| Éditeur E | Ouverture tronquante de l’original ; lecture initiale incomplète acceptée | Écriture exclusive dans `A2FC.EDIT`, fermeture et relecture octet par octet avant installation ; original conservé sous `A2FC.ED.BAK` pendant le renommage. Une sauvegarde échouée conserve le tampon modifié. Le chargement lit un octet de plus que la capacité : un fichier plus long que sa taille de panneau périmée est refusé au lieu d’être tronqué par la sauvegarde. `test_file_safety.py`, `bench/data_safety.py`. |
| Binary II, ShrinkIt, extraction ProDOS/DOS 3.3 | Écrasement silencieux de fichiers existants ; erreurs de fermeture ignorées | Création exclusive commune, aucune suppression d’un fichier préexistant en nettoyage, contrôle de fermeture. Bornes supplémentaires des noms et chemins Binary II/ShrinkIt ; erreurs des grandes surcouches conservées dans le message final. La réservation est un seul appel MLI CREATE (`reserve_output`, `src/file_output.h`) : l’entrée est créée ou rien ; l’`open()` de cc65 laissait, sur un OPEN refusé, un fichier vide (A2FC.COPY, A2FC.EDIT, A2MOVE.LST) qui bloquait les copies suivantes. `test_file_output.py`. |
| TXTCONV | Suppression de la source avant renommage ; suppression immédiate d’une destination confirmée | Conversion dans un temporaire exclusif, contrôle du nombre d’octets lus et des fermetures, installation avec sauvegarde et restauration. Temporaires et sauvegardes existants conservés. `test_txtconv.py`, `bench/txtconv.py`. |
| IMGCONV | Sonde `fopen(rb)` confondue avec une preuve d’absence ; suppression avant conversion | GET_FILE_INFO distingue absence et erreur ; CREATE exclusif ; conversion temporaire avant remplacement avec sauvegarde. `test_imgconv_safety.py`, `test_imgconv.py`, `bench/imgconv.py`. |
| MOVE, déplacement rapide sur un volume | Erreur entre les écritures brutes laissant deux entrées partageant les mêmes blocs ; backlink de sous-répertoire non validé | Validation du backlink et du stockage ; relecture des écritures ; sur erreur signalée, restauration de l’entrée source, du backlink et des compteurs avant suppression de la copie d’entrée. Avertissement interdisant de supprimer les entrées si la restauration échoue. Tests avant **et après** écriture effective à chaque étape dans `test_move.py`, puis `bench/move.py`. |
| WIPE F | Bitmap déclarant libre un bloc encore utilisé : le mode « espace libre » effaçait des données vivantes | Précontrôle de tous les blocs référencés par les répertoires et les fichiers seedling/sapling/tree, bornes et bits d’allocation. Aucune écriture si lecture impossible, structure non prise en charge, cycle détecté ou annulation. `test_wipe.py`. |
| DISKIMG | Image source tronquée ou 2MG malformée acceptée avant écriture destructrice ; possibilité de cibler le volume contenant l’image | Validation de la taille réelle, du format, de la plage de données et des pistes DSK. Volume source protégé comme cible ; refus de lire un disque dans une image située sur ce même volume ; disque RAM exclu des transferts bruts utilisant AUX. En copie à un lecteur, la première invite TARGET relit le bloc 2 de la source et redemande tant qu’il est présent : la marque n’est plus écrite sur la source. `test_diskimg_input.py`, `test_diskimg_verify.py`. Limite : une cible au bloc 2 identique à celui de la source n’est pas distinguée. |
| Images, ShrinkIt, copies de disque et formatage physique | Utilisation d’AUX détruisant le disque RAM avec un avis seulement après coup | Drapeau `OVERLAY_AUX` (ou `aux_consent` pour une surcouche qui en décide elle-même) et confirmation explicite avant utilisation, également pour une surcouche déjà chargée ; confirmation dédiée avant le formatage physique. Pas de question quand `/RAM` est en ligne et sans fichier (`ram_empty`, `src/a2fc_mli.s`). La reconstruction reste permise pour libérer de la mémoire. `bench/data_safety.py` compare les octets AUX avant/après refus ; `test_overlay_load.py` et `test_ram_empty.py` couvrent la décision. |
| Ctrl-Reset dans un visualiseur AUX | `/RAM` laissé en ligne, son catalogue intact sur des blocs que le visualiseur avait écrasés | `confirm_aux` lève `aux_dirty` dès que l’accord est donné, la boucle principale le baisse, et la sortie de `src/crt0.s` appelle `ram_format` tant qu’il est levé. `test_overlay_load.py` contrôle le drapeau sur chaque issue de l’accord. Pas encore rejoué dans POM2 avec des fichiers sur `/RAM`. |
| BLKEDIT | Tampon déclaré propre après échec de relecture de contrôle | Le tampon reste modifié pour permettre une nouvelle tentative ou un abandon explicite. |
| IMGFS, extraction d’une image ouverte comme dossier | Sortie fermée sans relecture ; fichier arbre (> 128 Ko) créé puis supprimé | Réservation exclusive après le refus des fichiers arbre ; chaque fichier écrit, fermé, puis relu bloc par bloc contre l’image ; octet faux, réouverture impossible, lecture courte ou image perdue en seconde passe retirent le fichier possédé. `test_imgfs_safety.py`, `bench/run.py`. |
| UNSHRINK | Fil décodé une seule fois ; écriture acceptée sur la seule fermeture | Après fermeture, retour au début du fil et second décodage (stocké, LZW/1, LZW/2) comparé au fichier relu, fin du fichier contrôlée ; `reads back different` retire le fichier possédé. Un enregistrement de type `$0F` (dossier) porteur de données est sauté, comme dans BINARY2, SCIIBIN et UNWRAP ; une fourche de ressources, une compression non prise en charge ou un type impossible sous ProDOS sont comptés dans « N file(s) extracted, M part(s) skipped. » au lieu d’être tus. `test_unshrink_safety.py`, `bench/shk.py`. |
| FIND, lecteurs de texte | Erreur de lecture prise pour une fin : recherche déclarée `complete` après un dossier illisible, `(end)` affiché sur un fichier tronqué par une erreur | `dir_close` rend l’indicateur d’erreur du résident ; FIND marque alors la recherche « some paths skipped ». T, le lecteur BASIC et le lecteur AppleWorks affichent `(READ ERROR)` et, au 80e écran d’un fichier plus long, `(page limit)`. `test_find.py`, `test_text_viewer.py`. |
| VDrive | Le pilote prenait l’emplacement d’une unité SmartPort ou ProFile (ou de `/RAM`, `$BF`) pour libre, et ses deux entrées DEVADR : le volume disparaissait pendant la session | Seul le numéro d’emplacement de DEVLST est comparé (`src/vsdrive.s`). `test_vsdrive.py` (sim65). Pas observé sur une machine équipée d’une telle carte. |
| REPAIR | Un pointeur abîmé pris au mot : une clé de sous-répertoire pointant un bloc d’index parcourue comme répertoire puis « réparée », le vrai répertoire libéré ; un chaînage du répertoire de volume vers un bloc libre, chaînage arrière réécrit et toutes les entrées suivantes libérées (295 blocs) ; une entrée au quartet de stockage effacé, compteur baissé et blocs libérés — chaque fois « rescan clean: repaired. » | REPAIR n’écrit que là où ce qu’il voit ne peut pas être l’effet d’un seul pointeur abîmé qui laisse encore les données sur le disque : un bloc n’est parcouru comme répertoire que sur preuve (en-tête `$E/39/13`, chaînage arrière concordant, répertoire de volume aux blocs 2 à `bitmap−1`), un bloc perdu n’est rendu que si l’arbre n’a aucun autre constat et ne réclame aucun bloc marqué libre ; sinon rien n’est écrit, pas même un compteur : « Lost blocks may hold a damaged file: nothing written. See FIXIT. » ; s’il y a aussi des blocs utilisés marqués libres : « Used blocks marked free: copy the files off this volume, write nothing to it. » `test_repair.py` (96 tests, octets de l’image comparés), `fuzz_prodos.py` invariant 8, `bench/repair.py`. Limites : un pointeur déplacé sur un bloc déjà perdu, ou une entrée effacée dont le compteur a déjà été ajusté, restent indétectables ([FIXIT.md](FIXIT.md) §5) ; rendre un bloc perdu exige le mot FREE (voir plus bas). |
| IMGPUT | Bitmap de l’image cru sur parole : un bloc de données d’un autre fichier marqué libre était donné au nouveau fichier, le bloc clé du dossier visé marqué libre écrasé — « Copied » ; taille de panneau périmée copiée (EOF 0 pour 512 octets réels) ; blocs réservés avant la question sans revérification | Parcours des références de l’image avant tout choix de bloc (`prodos_claims.h` : chaînes, blocs clés/index/maître, les deux forks, pointeurs de données ; boucles, pointeurs hors volume, types inconnus, blocs illisibles, profondeur > 16 refusés) : « Image damaged: nothing written. Run FIXIT. » ; la source est lue et comptée avant la question, l’EOF écrit est ce que le fichier contient ; blocs choisis après la réponse, bit déjà effacé refusé, clé de destination exigée en-tête de répertoire vivant ; drapeau 2IMG « protégé » respecté (IMGPUT, PASCALW, CPMW, BLKEDIT). `test_imgput.py` (44 tests, image comparée octet pour octet sur chaque refus), `bench/imgput.py`. Limites : le parcours prouve « référencé ⇒ marqué utilisé », pas l’unicité des références ni les compteurs (FIXIT) ; un refus après le début de la copie laisse les octets de l’essai dans des blocs que rien ne référence ; ~135 000 cycles par bloc lu, ~90 s à 1 MHz pour une image de 16 Mo de 765 fichiers ; Échap arrête le parcours ou la copie des données sans rien publier, mais n’est plus lu à partir de l’écriture du bitmap ; un échec entre le bitmap et l’entrée perd l’espace des blocs, annoncé « Bitmap written, entry unverified: run FIXIT. » ; un fichier qui pointe sur un autre bloc de répertoire que ceux écrits n’est pas détecté. |
| BLKEDIT, BOOTBLK et WIPE après un échange de disquette | Écriture sur le disque présent dans le lecteur au moment de l’écriture : BLKEDIT écrivait le bloc édité sur une disquette changée pendant l’édition ou l’invite ERASE ; BOOTBLK installait les blocs d’amorce sur un disque changé pendant la question, ou depuis une source changée ; WIPE W effaçait les 280 blocs de l’autre disque, F ses blocs libres, une entrée de liste périmée faisait de même | Identité revérifiée après la confirmation, avant la première écriture brute : BLKEDIT calcule à l’ouverture le CRC-32 du bloc 2 (du bloc 0 pour une image de 1 ou 2 blocs) et le recalcule après ERASE, garde l’édition pour un W une fois le bon disque revenu, renouvelle l’identité quand c’est ce bloc qui est écrit ; BOOTBLK exige les noms de volume sur les disques avant sa question et compare les 512 octets du bloc 2 de la cible et de la source après ; WIPE conserve le bloc 2 lu avant la question, en-tête ProDOS au nom affiché exigé, relu après la réponse et comparé sur 512 octets, puis une seconde fois pour F après le parcours d’allocation. Différence ou lecture impossible : rien n’écrit. `test_blkedit.py`, `test_bootblk.py`, `test_wipe.py` (hôte puis cc65 des deux éditions sous sim65), octets des deux disques comparés. Limites : un disque dont le bloc 2 est identique octet pour octet n’est pas distingué (pour BLKEDIT, ni un bloc différent de même CRC-32, une chance sur 2^32) ; un échange une fois les écritures commencées n’est pas détecté. |
| UNSQ, SCIIBIN, TAKE1, Mini | UNSQ créait un fichier plat de type `$0F` (pris pour un dossier par les panneaux) ; SCIIBIN joignait le nom brut de l’archive à la destination (`SUB/EVIL` écrit dans un sous-dossier) et son remplissage non nul faisait supprimer un bon fichier à la relecture ; TAKE1.SYSTEM lisait au-delà de la piste 34 dans une image ; B du Mini pouvait lancer un autre fichier que celui confirmé (nom en caractères FLASH ou inverses) | Enregistrement `$0F` ignoré et compté ; nom BinSCII rendu légal (jamais un chemin), CRC du remplissage tel qu’envoyé ; piste bornée à 35 sur les deux chemins de lecture ; B refuse un nom contenant une virgule ou un octet brut inférieur à `$A0` ou égal à `$FF` (FLASH, inverse, contrôle) ; les minuscules `$E0-$FE` sont rendues exactement et lancées. `test_unsq.py`, `test_sciibin.py`, `test_take1.py`, `test_mini33_write.py`, `bench/mini33_brun.py`. |
| Questions après une longue phase | Une touche tapée pendant la lecture de VISICALC ou le parcours d’IMGPUT répondait à la question suivante : un Y tapé d’avance faisait reconstruire `/RAM` sans que la question s’affiche | `question_begin` écrit `$C010` avant toute question (confirm, prompt, ERASE, disk_question, di_ask, may_overwrite). `test_ui.py`, `bench/visicalc.py` (étape de frappe anticipée). |
| Chemins des panneaux | A2FILE.CFG en minuscules : avec « /workhd/dir » et « /WORKHD/DIR », V déplaçait un fichier sur lui-même puis l’effaçait | `cfg_parse` met en majuscules et ôte la barre finale ; le `valid_path` de GOTO met en majuscules (une barre finale y était déjà refusée). V ou C entre deux panneaux sur le même dossier : « Both panels show the same directory. » `test_config.py`, `test_config_native.py`, `test_goto_safety.py`, `bench/case_paths.py`. Limite : `target_check` compare toujours des chaînes ; seules les deux sources de chemins sont normalisées. |
| Volumes homonymes | Un chemin désigne un volume, pas un lecteur : avec deux lecteurs du même nom, WIPE W effaçait le disque de 1600 blocs pendant que le panneau montrait la disquette (POM2) ; BOOTBLK, BLKEDIT, VOLINFO, RESCUE, UNDELETE, BLKVIEW, MOVE, FIXIT et REPAIR prenaient le premier enregistrement ON_LINE | En mode chemin, WIPE, BOOTBLK, BLKEDIT, RESCUE, VOLINFO, FIXIT et REPAIR refusent un nom porté par deux lecteurs : « Two volumes named /X: pick it in the volume list. » ; une ligne de la liste des volumes (par unité) fonctionne. BLKVIEW et UNDELETE refusent avec leur message habituel (UNDELETE aussi depuis la liste des volumes, puisqu’il lit le répertoire par son chemin) ; MOVE se replie sur la copie vérifiée ; les tables ON_LINE s’arrêtent à l’octet nul. `test_wipe.py`, `test_bootblk.py`, `test_blkedit.py`, `test_volinfo.py`, `test_blkview.py`, `test_six_plugins.py`, `test_move.py`, `test_fixit.py`, `test_repair.py`. Limite : la liste des volumes du résident ouvre une ligne par son chemin. |
| FORMAT et NIBCOPY | FORMAT ne cherchait `/RAM` et le volume du programme que parmi les 9 unités affichées (`/RAM` laissé sur des blocs écrasés), ne distinguait pas deux disquettes DOS 3.3 (bloc 2 identique), empruntait AUX avant de voir la protection d’écriture ; NIBCOPY ne nommait pas la cible et écrivait une disquette échangée | FORMAT parcourt toute la DEVLST, identifie un disque non ProDOS par les blocs 24-27 et 136-143, lit la protection avant AUX, relit les 280 blocs d’une disquette (bloc d’amorce et en-tête ailleurs), refuse un nom déjà en ligne ; NIBCOPY nomme le volume cible, refuse celui du programme, et revérifie avant chaque écriture la piste écrite juste avant. `test_format.py`, `test_format_asm.py`, `test_nibcopy.py`, `bench/format.py`, `bench/nibcopy_ui.py`. Limites : FORMAT ne distingue pas deux disques dont les blocs lus (le bloc 2 seul pour un volume ProDOS) donnent la même empreinte de 16 bits ; NIBCOPY ne détecte pas une disquette dont les 16 empreintes de 16 bits de la piste précédente coïncident ; deux disquettes jamais formatées ne se distinguent pas. |
| REPAIR, blocs perdus | Un pointeur déplacé sur un bloc déjà perdu ressemble exactement à une suppression interrompue : le bloc du fichier était rendu | Le plan liste les blocs perdus et un second mot, FREE, est exigé avant FIX. Limite : si l’utilisateur tape les deux mots, le bloc est rendu (indiscernable). `test_repair.py`. |
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
  modifie les deux blocs de démarrage, pas les blocs de fichiers. WIPE (F et
  W) et BOOTBLK relisent le bloc 2 après la réponse, BLKEDIT son CRC-32
  (bloc 0 d’une image de 1 ou 2 blocs), et refusent un disque changé ou
  illisible.
- **REPAIR** : écritures brutes après le diagnostic de FIXIT et une
  confirmation ; voir [FIXIT.md](FIXIT.md), section 5 pour ce qu’il refuse
  de croire. Sur un volume de plus de 4 096 blocs, FIXIT et REPAIR
  demandent l’accord `/RAM` par l’`aux_consent` du résident : pas de question
  si `/RAM` est vide (`ram_empty`), et `aux_dirty` est levé, si bien qu’un
  Ctrl-Reset pendant l’analyse reconstruit `/RAM` (`test_fixit.py`,
  `test_repair.py`).
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
WIPE ne reconnaît pas un disque dont le bloc 2 est identique octet pour octet
(copie dont le premier bloc de répertoire n’a pas changé), et ne réinterroge
pas l’unité entre deux blocs : un échange une fois les écritures commencées
n’est pas détecté. La reconstruction de `/RAM` par Ctrl-Reset (`aux_dirty`)
n’a pas encore été rejouée sous POM2.
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
