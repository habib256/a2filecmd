# Contrats des services de fichiers

Première extraction du chantier 1, le 13 septembre 2026 : `file_output.h`
et `file_copy.h` sont inclus dans `a2fc.c`, à leur emplacement d'origine.
Ce sont des modules internes, pas une nouvelle ABI ni une surcouche de service
à charger depuis les plugins. La réservation des plugins commence à être
unifiée ; COPY, EDIT, SYNC, TXTCONV, IMGCONV et GOTO partagent maintenant la transaction
de renommage. BATCH, COPY, EDIT et les utilisateurs résidents de `new_output`
partagent la réservation exclusive. Les autres politiques de création et
de nettoyage restent à rapprocher.

## Erreur du flux de destination après une écriture complète

COPY et EDIT contrôlent `ferror` sur le flux de destination avant fermeture,
même si `fwrite` a annoncé tous les octets demandés. Une relecture correcte
ne transforme pas cette erreur en succès : aucun original n'est renommé,
la copie n'autorise pas la suppression d'une source déplacée et l'éditeur
conserve son tampon modifié. Seul le temporaire possédé est nettoyé ; un
échec de nettoyage est signalé et ses octets restent disponibles.
`tools/test_file_safety.py` injecte ce cas dans les deux opérations, avec
fermeture réussie, puis avec nettoyage refusé et nouvelle tentative.
Validation du 13 septembre 2026 : 33 tests de sécurité des fichiers réussis,
14/14 contrôles `bench/data_safety.py` sur chacun des CPU 65C02 et 6502
(copies, déplacement, sauvegardes persistées et confirmations RAM), deux
compilations natives et sept images de distribution validées. Le banc attend
le libellé courant `Overwrite/Skip/All/None?` de la confirmation.

## Chargement du code avant une opération

`load_overlay` ne lance ni ne met en cache une surcouche après une erreur
de lecture de l'en-tête ou du corps, une erreur de fermeture, un corps vide
ou un fichier dépassant sa fenêtre. Un grand chargement peut écraser les
tables des panneaux en RAM principale ; après échec, les panneaux sont
relus et les marques restaurées. Le chargeur lit le disque sans l'écrire ;
la confirmation AUX précède toujours le code qui pourrait utiliser cette banque.
Le résultat du menu est effacé avant son chargement : un échec ne peut pas
réutiliser une ancienne commande de déplacement ou de plugin.

`tools/test_overlay_load.py` exécute le vrai code résident avec erreurs de
flux, limites exactes des fenêtres, dépassements, cache et résultat de menu
périmé. `bench/overlay_load.py` refuse deux fois un MENU trop grand, puis
charge HELP normalement : 6/6 contrôles sur 6502 et 65C02, avec panneaux,
pile, AUX et volume jetable conservés. Ces contrôles ne sont pas une somme
d'intégrité du code : un fichier altéré qui reste structurellement valide
ne peut pas être identifié par ce seul en-tête.

## Réservation des plugins : `newfile(path, type, aux, storage)`

`plugins/file_create.h` porte le CREATE ProDOS commun à `util.h` (dont
SYNC) et TXTCONV. Il renvoie le code MLI sans le transformer : **zéro seul**
autorise l'appelant à ouvrir le chemin en `wb` et à nettoyer cette entrée.
Une collision, un disque plein ou une erreur d'E/S ne donnent aucun droit
sur le chemin. L'appelant borne le chemin et vérifie ensuite les écritures,
fermetures et relectures ; ce service ne publie pas un remplacement.

Le tampon Pascal est prêté par l'appelant : `pas` pour `util.h`, début de
`T.copy_buf` pour TXTCONV. Il est écrasé pendant l'appel et ne doit contenir
aucune donnée encore utile. La requête CREATE est entièrement réinitialisée,
y compris après une erreur ou un changement fichier/répertoire. Elle utilise
la table API de l'appelant, sans chargement de surcouche ni accès au stockage
AUX. Les permissions initiales restent `$C3`, les dates initiales nulles.
GOTO conserve sa création spécifique `$E3` ; IMGCONV et le résident ne sont
pas encore migrés vers ce contrat de requête MLI.

Le banc `test_file_create.py` exécute le service compilé sur les deux CPU
avec sim65 : disposition MLI de 12 octets, BSS sale, propagation des 256 codes
de retour et séquence fichier puis répertoire. `test_txtconv.py` vérifie les
octets préservés lors des refus de création, en plus des pannes de conversion.

Validation de cet incrément : 106 tests ciblés réussis (`file_create`,
`txtconv`, `six_plugins`, `file_safety`, `tree_stack`, `check_layout`,
`imgconv_safety`, `goto_safety`, `batch`), constructions 6502 et 65C02 avec
contrôles de disposition, puis sept supports ProDOS reconstruits par
`make disk` et contrôlés par `tools/check_images.py`. Pas de qualification
POM2, CI ou matériel pour cet incrément ; la suite globale `make test`
n'a pas été exécutée.

## Installation commune : `file_install(tmp, target, backup, exists)`

`plugins/file_install.h` porte la séquence de renommage de SYNC, GOTO et des
deux conversions. L'appelant fournit des chemins distincts et bornés, un temporaire
possédé, fermé et vérifié, et le résultat du contrôle de présence de la cible.
Il contrôle les protections et le nom de sauvegarde ; le transport ProDOS
refuse aussi tout renommage vers une entrée existante. Le service ne supprime
rien : après publication, l'appelant garde la sauvegarde jusqu'à ses derniers
contrôles (dont les métadonnées pour SYNC).

`FILE_INSTALLED` (1) signifie que le temporaire porte le nom cible ;
`FILE_INSTALL_FAILED` (0) signifie non installé, avec temporaire conservé ;
`FILE_RESTORE_FAILED` (2) signale que l'original demeure dans la sauvegarde,
avec temporaire conservé. Ces codes internes ne sont pas les codes
`REPLACE_*` de l'adaptateur des conversions. Sans ancienne cible, aucune
sauvegarde ni restauration n'est tentée. La fonction ne charge aucune
surcouche ; elle prête les chemins au transport de l'appelant pendant l'appel.
SYNC utilise `pas` et `newpas` pour ses chemins Pascal, sans emprunt AUX.

SYNC conserve maintenant `A2FC.SYNC` après un échec d'installation, y compris
si la restauration réussit. Une installation, restauration, mise à jour de
métadonnées ou suppression de fichier échouée nécessitant une récupération
arrête le parcours, avant le fichier suivant, et conserve le diagnostic.
Les échecs de copie dont le nettoyage réussit gardent le comportement de
poursuite existant. Une nouvelle invocation remet l'indicateur de récupération
à zéro, mais ne supprime ni n'écrase les fichiers laissés par la précédente.
La source n'est jamais supprimée. Aucun descripteur de répertoire ne demeure
ouvert entre deux appels du parcours.

Validation locale : 113 tests ciblés réussis (`six_plugins`, `txtconv`,
`imgconv_safety`, `file_install`, `file_create`, `file_safety`, `dirscan`,
`tree_stack`, `check_layout`). `file_install` exécute le vrai code compilé
sur les deux CPU avec sim65. Le banc SYNC exécute aussi `plugin_entry` et
son vrai lecteur de répertoire sur un catalogue jetable simulé, en vérifiant
les octets des sources, du fichier suivant et des fichiers de récupération.
Les deux éditions natives et les sept supports ProDOS passent leurs contrôles.
Pas de nouvelle qualification POM2, CI ou matérielle, ni de suite globale
`make test` exécutée pour cet incrément.

## Sauvegarde des favoris GOTO

GOTO utilise aussi `file_install`, avec ses noms `GOTO.TMP`, `GOTO.CFG` et
`GOTO.BAK`. Avant toute création, il contrôle l'absence de sauvegarde et les
métadonnées de la configuration : seule l'erreur ProDOS `$46` autorise le
cas sans configuration. Une configuration présente doit être un fichier de
stockage 1 à 3 et permettre écriture, renommage et destruction (`$C2`). Une
erreur de contrôle refuse l'opération avant la première écriture.

La création exclusive conserve ses permissions `$E3`. Le texte sérialisé
reste à `$3400` pendant la relecture du temporaire dans `copy_buf`. Après
fermeture et vérification complète, la transaction utilise `A->full` et
`A->other_full` comme chemins Pascal ; les chemins C restent dans les tableaux
privés `cfg`, `temp`, `backup`. Aucun chargement imbriqué ni accès au stockage
AUX. Code et BSS restent sous `$3000`, avant les neuf emplacements de favoris.

Un échec d'installation conserve maintenant le temporaire vérifié, même si
la restauration réussit. En cas d'échec de restauration, les deux fichiers de
récupération restent disponibles. Les erreurs précédant la vérification
tentent encore de nettoyer le temporaire possédé, avec diagnostic si la
suppression échoue. Une nouvelle tentative ne peut écraser ces fichiers.

Validation locale de cet incrément : 108 tests ciblés (`goto_safety`,
`file_install`, `file_create`, `txtconv`, `imgconv_safety`, `six_plugins`,
`batch`, `tree_stack`, `check_layout`), deux éditions natives et sept supports
ProDOS reconstruits et vérifiés. Le banc GOTO exécute le vrai C et compare les
octets sur erreurs de métadonnées, protections, stockage invalide, pannes
combinées et collisions tardives, puis après nouvelle tentative. La création
sans ancienne configuration reste testée. Pas de nouvelle qualification
POM2, CI ou matérielle, ni d'exécution globale de `make test`.

## Publication et nettoyage des conversions

`plugins/replace.h` est partagé par TXTCONV et IMGCONV. Avant
`replace_commit(tmp, target)`, l'appelant possède le temporaire, a fermé et
relu son contenu, a borné les chemins et obtenu l'accord de remplacement.
Le service peut renommer la cible en `A2FC.BAK`, installer le temporaire,
restaurer la sauvegarde et supprimer celle-ci après installation. Il utilise
les deux zones Pascal de `T.copy_buf` (offsets 0 et 128), en RAM principale,
sans charger une autre surcouche ni emprunter le stockage AUX. IMGCONV prête
en plus les octets 256 et suivants au nom de sauvegarde.

Les résultats de publication sont distincts : `REPLACE_FAILED` (0) signifie
non installé, `REPLACE_DONE` (1) installé et sauvegarde supprimée,
`REPLACE_BACKUP` (2) installé mais sauvegarde conservée, et
`REPLACE_RESTORE_FAILED` (3) installation puis restauration échouées.
Ce dernier état conserve l'original dans `A2FC.BAK` et le résultat dans le
temporaire. Une collision pendant l'installation et la restauration ne permet
pas d'écraser le nouveau fichier apparu à la cible. Un retour non nul n'est
donc pas à lui seul une preuve d'installation.

`replace_discard(path)` est réservé à une entrée effectivement créée par
l'opération, avant publication. Il contrôle la suppression ; son retour zéro
laisse un diagnostic dans `T.note`, que l'appelant doit conserver. Ni une
erreur ni une annulation ne doivent alors annoncer que le résultat a disparu.
Sa présence bloque la prochaine création exclusive. Une suppression échouée
peut laisser un résultat incomplet : il ne constitue pas une copie vérifiée.

Validation de cet incrément : 103 tests ciblés (`txtconv`, `imgconv_safety`,
`file_create`, `file_safety`, `six_plugins`, `check_layout`, `tree_stack`).
Les bancs des conversions exécutent le vrai C et comparent les octets lors
des pannes combinées écriture/fermeture/annulation + nettoyage, puis lors
d'une nouvelle tentative ; ils couvrent aussi installation + restauration
échouées, collision tardive et suppression de sauvegarde refusée.
Les constructions des deux CPU et les sept supports ProDOS sont contrôlés.
Ce sont des preuves locales, sans nouvelle qualification POM2, CI ou matériel,
et sans exécution de la suite globale `make test`.

## Réservation résidente : `reserve_output(path)`

Le résident et BATCH partagent la réservation `open(O_CREAT | O_EXCL)` et
la fermeture du descripteur. Le résultat sépare trois états : zéro ne donne
aucune propriété sur le chemin ; `OUTPUT_RESERVED` (1) autorise la réouverture
en écriture ; `OUTPUT_CLOSE_FAILED` (2) signifie fichier créé mais fermeture
échouée, donc nettoyage autorisé et réouverture en écriture interdite.
Le service ne nettoie rien lui-même. Il ne charge pas de surcouche et
n'emprunte pas le stockage AUX ; son code résident reste disponible depuis
BATCH comme depuis COPY. L'appelant borne le chemin et prépare type/aux-type.

BATCH mémorise la propriété du manifeste avant de traiter une fermeture
échouée. Si le nettoyage ne réussit pas, `MB->owned` reste vrai et le
diagnostic signale `A2MOVE.LST` conservé ; aucun MOVE n'est lancé. Une nouvelle
tentative refait une création exclusive et ne peut écraser ce manifeste.
Les panneaux, les marques et les vérifications du manifeste conservent leurs
contrats précédents. BATCH écrit uniquement `A2MOVE.LST` dans la destination ;
MOVE reste responsable de chaque transfert et suppression de source.

Validation locale : 42 tests ciblés (`batch`, `file_safety`, `file_output`,
`file_install`, `file_create`, `tree_stack`, `check_layout`), deux éditions
natives et sept supports ProDOS contrôlés. `file_output` exécute le vrai
service compilé sur les deux CPU avec sim65. Les bancs C hôtes vérifient les
octets après fermeture de réservation échouée, ouverture impossible, nettoyage
échoué, collisions et nouvelles tentatives. Les tests COPY vérifient aussi
la source et la destination précédente, restaurée ou conservée en sauvegarde.
Pas de nouvelle qualification POM2, CI ou matérielle ni de suite globale
`make test` pour cet incrément.

## Réservation exclusive : `new_output(path)`

Le chemin désigne un nouveau fichier ProDOS. `reserve_output(path)` doit
renvoyer `OUTPUT_RESERVED` avant toute ouverture `wb`. Une collision ou une erreur ne permet
jamais de tronquer un fichier préexistant. Après réservation, la fermeture du
descripteur est contrôlée ; seule l'entrée créée par cet appel peut être
nettoyée. Le service renvoie le flux d'écriture, ou NULL. L'appelant doit
contrôler écriture, fermeture et relecture avant de considérer le résultat
comme utilisable. Les type et aux-type sont ceux préparés par l'appelant.

Le service est résident : il ne charge aucune surcouche. Ses locaux statiques
et les tampons d'E/S cc65 sont en RAM principale. Il ne touche pas au stockage
AUX de `/RAM`. Un échec de suppression après réservation peut laisser un
fichier vide ; NULL ne garantit donc pas que le chemin soit redevenu libre.
Le prochain essai doit refaire une création exclusive.

## Sauvegarde de l'éditeur : réservation et nettoyage

EDIT appelle directement `reserve_output` pour `A2FC.EDIT`. Zéro refuse
la sauvegarde sans suppression ; `OUTPUT_CLOSE_FAILED` autorise seulement
le nettoyage de l'entrée créée, jamais sa réouverture en `wb`. Le helper
`edit_discard` est limité à ce temporaire possédé. Il contrôle sa suppression
après échec de réservation fermée, ouverture, écriture, fermeture, relecture
ou refus de publication. Si elle échoue, le message nomme `A2FC.EDIT` et
`A2FC.ED.BAK` à récupérer ; une nouvelle tentative ne les écrase pas.
L'original et le tampon modifié restent conservés sur ces échecs.

Les écritures restent limitées au temporaire, à la destination et à sa
sauvegarde dans le même répertoire ProDOS. Chemins prêtés dans `text_starts`,
texte dans HGR MAIN ; aucune utilisation du stockage AUX du disque RAM.
Le helper reste dans EDIT, sans chargement imbriqué ; son argument de deux
octets reste empilé pendant suppression/diagnostic. Il ne rajoute aucun
local statique ni récursion. Validation : 26 tests C copie/édition, dont
pannes combinées de nettoyage et retry avec contrôle des octets sur disque
et du tampon d'édition, service de réservation simulé sur deux CPU et
15 tests de disposition. Les deux liens et les sept images ProDOS passent.
EDIT compile désormais `file_install.h` dans sa propre surcouche, sous le
nom `edit_install`. Les trois chemins et le booléen d'existence restent
valides pendant l'appel (sept octets d'arguments sur la pile). Aucun
chargement de surcouche ni local statique supplémentaire. Après vérification
complète du temporaire et contrôle des protections, tout échec de transaction
conserve ce temporaire, y compris si le premier renommage échoue.
`FILE_RESTORE_FAILED` affiche explicitement l'échec de restauration et le
nom `A2FC.ED.BAK`. Une collision tardive n'est jamais écrasée, même pendant
la restauration. Si seule la suppression de la sauvegarde échoue après
installation, le fichier est sauvegardé et le message indique la sauvegarde
retenue. Les refus avant transaction gardent le nettoyage contrôlé décrit
ci-dessus.

Validation de cette migration : 31 tests C copie/édition, avec contrôle de
l'original pendant chaque écriture/fermeture et interdiction du premier
renommage avant les deux fermetures transfert/relecture ; collisions tardives,
restauration échouée, première publication et nouvelles tentatives. La
transaction et la réservation sont aussi exécutées sous sim65 sur les deux
CPU ; 15 tests de disposition et les sept images ProDOS passent.

## Copie : `copy_file(name, type, aux)`

Entrées : `full` est la source en lecture seule ; `other_full` est la
destination complète, avec un parent et des chemins déjà bornés par
l'appelant. Celui-ci contrôle aussi l'identité source/destination. `name`
doit rester valide jusqu'au retour (sélection ou pool de répertoire).

Écritures possibles : `A2FC.COPY`, entrée de destination et `A2FC.BAK` dans
son parent. La copie réserve exclusivement le temporaire ; l'ancienne
destination reste à son nom jusqu'à la fin de l'écriture, de la fermeture et
de la vérification. La copie relit les deux flux fermés et compare tous les octets,
leurs erreurs, leurs fermetures et la taille mesurée sur la source ouverte.
La taille du panneau ne sert pas de preuve. La source n'est jamais supprimée
par ce service. Après vérification, le contrôle de sauvegarde doit renvoyer
exactement `$46` ; toute collision ou erreur conserve le temporaire et refuse
la publication. La transaction commune renomme alors l'ancienne destination
en sauvegarde, puis installe le temporaire, avec restauration sur échec.
La sauvegarde n'est supprimée qu'après installation réussie. Le nom cible
`A2FC.COPY` est refusé ; un temporaire préexistant, même identique à la source,
ne peut être écrasé ni nettoyé par cette opération.

Valeurs de retour :

- 0 : échec ou annulation ; aucune autorisation de supprimer la source.
- 1 : copie vérifiée et nettoyage de la sauvegarde réussi.
- 2 : entrée ignorée selon la politique d'écrasement ; ce n'est **pas** une
  preuve de copie. Le parcours COPY la compte comme traitée, pas comme copiée.

Sur échec, seul le résultat dont COPY possède la création est supprimable.
COPY appelle directement `reserve_output` : la propriété reste connue même
si la fermeture du descripteur échoue, et aucune ouverture `wb` n'est alors
permise. Si la suppression du résultat échoue, un diagnostic de nettoyage
apparaît aussi après annulation ; l'ancienne destination reste intacte et
aucune restauration n'est nécessaire à ce stade. Après échec d'installation,
le temporaire vérifié est conservé, même si la restauration réussit. Un
renommage de restauration échoué laisse l'original dans la sauvegarde, sans
écraser une éventuelle nouvelle entrée apparue à la cible. Une suppression
de sauvegarde échouée après installation renvoie 0 et conserve la source.

## Durée de vie des tampons et de la surcouche

`copy_file` reste résident. Il sauvegarde la destination dans `CopyState`
avant `overlay("COPY")`, car le chargeur peut écraser `other_full`, puis
restaure ce chemin au retour. Si le chargement échoue, aucun résultat vérifié
d'une copie précédente n'est réutilisé. `copy_stage`, `copy_check` et la
question d'écrasement restent dans COPY, sans chargement imbriqué.
`copy_check` vérifie désormais les flux et met à jour l'état ; la finalisation
`copy_finish` résidente traite nettoyage, restauration, compteurs et résultat.
Elle ne s'exécute ni après refus de chargement ni pour une entrée ignorée.
Le résident ne charge pas d'autre surcouche pendant cette finalisation.
La transaction utilise la variante `FI_STATE` de `file_install`, liée à CP :
pas de copie des trois pointeurs et du booléen sur la pile C. La logique de
renommage est identique à celle de la variante à paramètres des plugins.

`CopyState` emprunte `text_starts` pendant l'opération : pagination texte et
manifeste BATCH ne doivent pas vivre simultanément avec cette copie. Un
contrôle de compilation borne la structure au tampon. Ses trois chemins
portent la structure native à 204 octets dans les 320 disponibles, sans
nouveau tampon global. `copy_buf` prête ses
512 octets au transfert, puis 256 octets à chaque flux de vérification.
Les tables des panneaux et le pool de répertoire restent intacts. Les
compteurs, métadonnées GFI, politique d'écrasement et indicateur d'annulation
sont partagés ; l'appelant réinitialise l'annulation au début d'une nouvelle
opération. Le service n'est pas réentrant.

Les messages et barres de progression écrivent l'écran texte principal/AUX,
sans emprunter le stockage du disque RAM. Le chargement de COPY remplace la
fenêtre `$1B00-$1FFF` : l'appelant qui doit reprendre ne peut pas y résider.

## Extraction Binary II : propriété et lecture complète

BINARY2 lit `full` et crée exclusivement les fichiers normalisés dans le
répertoire du panneau opposé. Aucune source n'est supprimée, aucun accès au
stockage AUX du disque RAM. `reserve_output` conserve la propriété même si
sa fermeture échoue ; seul `OUTPUT_RESERVED` permet la réouverture `wb`.
La propriété est remise à zéro après fermeture réussie du fichier extrait.
Un enregistrement suivant incomplet ne permet donc pas de supprimer le
fichier précédent. Une collision de noms normalisés refuse le nouvel extrait.

En-tête attendu, contenu et remplissage de 128 octets sont lus exactement,
avec contrôle des erreurs. Le remplissage est lu plutôt que sauté par seek,
qui pouvait réussir au-delà de la fin. Un en-tête suivant annoncé mais absent
ou invalide est une erreur, jamais une fin normale. La fermeture de l'archive
est contrôlée avant l'annonce de succès ; si elle échoue, les extraits déjà
fermés sont conservés et l'erreur est signalée. La suppression d'un extrait
incomplet est limitée à l'entrée possédée ; son échec nomme le fichier retenu.
Une nouvelle tentative ne peut pas le tronquer.

Neuf tests exécutent le vrai C sur fichiers jetables : tailles limites,
troncatures, lectures/écritures/fermetures échouées, réservation, collisions,
nettoyage échoué puis retry et conservation des enregistrements précédents.
Le test est intégré à `make test`. Les deux liens et les sept images ProDOS
sont contrôlés. L'extraction ne relit pas encore les octets écrits et ne
valide pas tous les attributs Binary II ; ceci ne constitue pas une garantie
contre une corruption physique silencieuse ou une coupure d'alimentation.

## DOSWRITE : création exclusive sur un vrai disque DOS 3.3

Surcouche indépendante, chargée par C vers un panneau FS_DOS33 ou par !.
Une seule sélection ProDOS TXT/BIN/BAS/INT, taille relue au lieu de celle
du panneau, maximum 65 535 octets. Disque cible physique S1–S7,D1/D2 sur un
autre périphérique ; déplacements et remplacements de fichiers DOS refusés.
La signature ROM et les commutateurs de protection utilisent le slot choisi,
pas le slot 6 imposé auparavant.

Écritures : VTOC, secteurs libres de données/listes, puis un secteur de
catalogue. Chaque écriture MLI de 512 octets préserve le secteur DOS voisin
et vérifie les 512 octets. L'audit parcourt tous les fichiers, y compris
verrouillés, refuse cycles, secteurs partagés ou marqués libres, comptes
incohérents, collisions et catalogues pleins. Les pistes 0–2 et 17 ne sont
jamais allouées. Confirmation nominative, puis nouvelle vérification du
bitmap et audit avant réservation. La source est refermée après transfert,
puis relue et comparée intégralement, EOF et fermeture contrôlés, avant
publication. Le catalogue et le VTOC sont comparés de nouveau avant publication.

Aucun nettoyage automatique après une écriture incertaine : la réservation
peut rester occupée, sans publication d'un fichier incomplet. Aucune source
n'est supprimée. La protection matérielle est testée avant chaque écriture.
Il n'y a ni récursion, ni chargement imbriqué, ni accès AUX. Les locaux
statiques et tampons appartiennent à la surcouche ; le bloc d'E/S est prêté
par l'API résidente. Une coupure ou une écriture physique déchirée du VTOC ou
du catalogue peut endommager des métadonnées partagées : aucune atomicité
physique n'est promise.

Tests : moteur C complet sur fichiers jetables avec pannes à chaque lecture
et écriture, écritures partielles/silencieusement corrompues, fermeture,
annulation, protection, collision, tailles limites et retry. Exécution
6502/65C02 sous sim65 avec transport de blocs côté hôte. Le banc POM2
`bench/doswrite.py` utilise le vrai pilote Disk II ProDOS et vérifie copie
BAS/BIN/TXT, consentement refusé, protection physique, fichiers existants,
volume source, AUX et trois allers-retours catalogue/volumes. Résultat local :
17/17 contrôles POM2 par CPU, dont TIGER BIN de 8 192 octets en slot 5,
plus les tests C/sim65 et les sept images ProDOS contrôlées.
Il s'agit d'une validation du pilote Disk II sous émulation, pas d'un essai
sur un Apple II physique.

## DOSIMAGE / DOSPUT : écriture dans une image DOS

L'audit DOS commun exige une fin de catalogue `(piste 0, secteur 0)` et
des décalages T/S successifs de 0, 122, 244… secteurs logiques. Une fin de
chaîne indiquant encore la piste 17 ou un décalage T/S erroné interdit la
première écriture DOS. Sur une image, le clone possédé est nettoyé et l'image
originale reste inchangée. Validation du 13 septembre 2026 : 28 tests DOS,
dont les refus sans écriture et un fichier valide de 32 Ko sous sim65 sur
les deux CPU ; deux compilations natives et sept distributions contrôlées.

C prépare une transaction en trois appels successifs, sans surcouche imbriquée :
DOSIMAGE réserve et vérifie le clone, DOSPUT exécute le moteur DOS commun sur
ce clone, DOSIMAGE l'installe. Chaque phase ferme tous ses fichiers avant de
rendre la main. `input[0]` porte le résultat, `[1..3]` l'offset DOS et `[4]`
un diagnostic ; `[5..8]` et `[9..11]` gardent le CRC-32 et la longueur
de l'image d'origine, relue intégralement avant installation. Une variation
ou erreur de lecture/fermeture refuse le remplacement et conserve le
temporaire vérifié. Le chemin temporaire est reconstruit après chaque chargement,
car le chargeur utilise `other_full`. Aucun tampon de panneau écrasé ne sert
à conserver l'état entre phases. Les deux helpers sont masqués dans le menu.

Écritures : création exclusive et données de `A2FC.DOS` dans le dossier de
l'image, puis renommages image → `A2FC.BAK`, `A2FC.DOS` → image. Les formats
acceptés sont DSK/DO et 2MG DOS-order avec géométrie 35×16×256. Contrôle des
attributs ProDOS, du verrou 2MG, du format/offset/taille et des collisions
source/temporaire/sauvegarde. Toute l'image fermée est comparée avant les
mutations DOS ; après celles-ci, données, listes T/S, VTOC et catalogue sont
relus après fermeture, avec la source entièrement relue et refermée.
Une comparaison intégrale supplémentaire exige que tous les octets hors
secteurs DOS volontairement modifiés correspondent encore à l'original,
y compris les fichiers existants, l'en-tête et les données annexes 2MG.
L'en-tête validé avant confirmation doit aussi correspondre à celui du clone :
un changement de protection ou d'offset pendant la confirmation refuse la copie.

Seul le temporaire créé par cette opération est nettoyé après une erreur de
préparation ou d'écriture. L'original reste récupérable jusqu'à l'installation.
Les erreurs de renommage/restauration conservent les fichiers de récupération,
et l'échec de suppression de la sauvegarde est signalé. Coupures pendant les
renommages ou écritures ProDOS : aucune atomicité promise. Pas d'AUX, pas de
suppression de source, pas de remplacement d'un nom déjà présent dans DOS.

`tools/test_dosimage.py` exécute les deux phases C et le moteur livré : octets
conservés, écritures courtes, erreurs de lecture/seek/fermeture, disque plein,
collisions, annulation, protections et échecs de renommage/restauration/nettoyage.
`bench/dosimage.py` ouvre DSK et 2MG, copie BAS/BIN/TXT via C puis contrôle les
octets sauvegardés avec un lecteur indépendant. `bench/build_dos_host.py`
construit un hôte jetable avec persistance HDV ; option `--slot 5` pour reproduire
Disk II S5 et ProDOS S6. Tous les médias de ces bancs sont jetables.

Validation locale finale (13 septembre 2026) : 28 tests C/sim65, 44 autres
régressions ciblées et sept images de distribution validées. Sur chacun des
CPU 6502 et 65C02, POM2 passe 17/17 contrôles physiques en slot 5 et 17/17
en slot 6, 19/19 pour DSK et 20/20 pour 2MG. Le capteur assembleur et le
CRC-32 sont également exécutés sous sim65 pour les deux processeurs.
Aucun essai sur du matériel Apple II physique n'est revendiqué.

## DISKIMG : réservation et fermeture des images créées

Le mode R appelle `reserve_output` directement : zéro ne donne aucun droit
de suppression, `OUTPUT_CLOSE_FAILED` autorise uniquement le nettoyage et
seul `OUTPUT_RESERVED` permet l'ouverture en `wb`. Le contrôle d'existence
préalable est remplacé par cette création exclusive. La propriété est dans
`DiskImg.output_owned`, remise à zéro à chaque entrée dans DISKIMG.

`di_finish` ferme les deux flux éventuels avant le diagnostic final et remet
leurs pointeurs à NULL. Toute fermeture échouée interdit l'annonce de succès.
Sur erreur ou annulation, il ne supprime que l'image créée par R ; W et O
ne reçoivent aucune propriété sur un fichier. Si la suppression échoue, le
message nomme l'image conservée et prime sur l'erreur initiale. Une nouvelle
tentative refuse cette entrée sans la tronquer. Une erreur de fermeture du
flux source W est désormais signalée ; ce fichier reste intact.

Le champ supplémentaire tient dans l'état à `$3E00` (200/512 octets), avec
assertion de capacité. Aucun nouveau tampon ni accès AUX : les chemins,
banques de staging, consentement préalable et reconstruction du disque RAM
restent ceux de DISKIMG. Cette correction ne fournit pas encore la relecture
complète des images créées. Les écritures sur périphérique conservent leur
vérification existante ; aucune atomicité physique n'est ajoutée.

Validation : cinq tests C de réservation/transfert/finalisation, avec PO/DSK,
fermetures, écriture courte, seek, annulation, nettoyage échoué, collision et
retry contrôlés sur les octets ; 32 tests ciblés au total, deux liens et sept
images ProDOS contrôlés.

## Limites ouvertes et preuves

### UNSHRINK : propriété des extraits et fin de lecture

UNSHRINK réserve chaque nom par `reserve_output`. Seul `OUTPUT_RESERVED`
permet l'ouverture en écriture ; une fermeture de réservation échouée donne
uniquement le droit de nettoyer cette entrée. Échec de suppression : le
diagnostic nomme l'extrait conservé, reste prioritaire même si la fermeture
de l'archive échoue aussi, et une nouvelle tentative ne peut pas le tronquer.
Les extraits précédents et l'archive source restent conservés.

Les lectures sont exactes et contrôlent `ferror`, même après un compte complet.
Les sauts sont remplacés par des lectures : un thread ignoré ou un remplissage
tronqué arrête le parcours. Le nom est sauvegardé avant de réutiliser le tampon
pour ce saut. Les tailles stockées et les en-têtes LZW ne peuvent plus faire
sous-déborder le compteur d'entrée ; la fenêtre distingue les vrais octets lus
du remplissage, et refuse une consommation nulle ou hors fenêtre renvoyée par
le décodeur. Un en-tête d'attributs trop court est refusé avant utilisation.
Échap arrête entre blocs ; les erreurs de flux de destination et les fermetures
sont contrôlées avant succès. Une compression ignorée conserve son diagnostic.

Écritures : seulement les nouveaux fichiers du dossier cible, leur nettoyage,
le tampon principal partagé et l'état `$3000` (borné à 512 octets), ainsi que
les zones AUX déjà utilisées par le décodeur. Le drapeau `BIG|AUX` conserve
le consentement résident avant l'entrée dans la surcouche ; `/RAM` reste
refusé pour la source et la destination, puis reconstruit après utilisation.
Aucun BSS ajouté, aucun plafond relevé, aucune nouvelle transaction de renommage.

`tools/test_unshrink_safety.py` exécute le pilote C réel avec ASan/UBSan sur
fichiers jetables : stockage, enveloppe Binary II, réservations, collisions,
lectures/écritures/fermetures, annulation, nettoyages échoués et retries,
troncatures, tailles incohérentes, longs noms, threads ignorés et fenêtres LZW.
Le transport AUX et le décodeur sont substitués dans ce test ; `bench/shk.py`
exécute le décodeur natif et compare les extraits persistés, avec garde de pile.

Validation locale du 13 septembre 2026 : 18 tests C réussis ; quatre méthodes
de régression essayées sur l'ancien pilote détectent les défauts. `make test`
passe ; les deux liens, leurs contrôles mémoire et les sept images ProDOS
passent également. POM2 : 30/30 contrôles sur 65C02 et 30/30 sur 6502 NMOS,
avec fichiers stockés, LZW/1, LZW/2, retours HGR/DHGR, octets persistés et
garde de pile. Aucun essai sur matériel physique ni résultat CI revendiqué.

Limites : pas encore de contrôle complet des CRC et métadonnées NuFX, de
validation complète des flux LZW malformés ni de relecture des sorties par
UNSHRINK lui-même. La vérification des octets par le banc ne remplace pas cette
relecture en production. Aucune atomicité sur coupure n'est promise.

### Services restants

COPY utilise maintenant la transaction des temporaires vérifiés. Les
nettoyages internes de `new_output` pour ses autres appelants restent ouverts.
Le code dépend du
refus d'écrasement de RENAME ProDOS ; un port POSIX doit le reproduire.
Une coupure d'alimentation pendant une écriture ou un renommage reste hors
des garanties de restauration sur erreur signalée.

Validation de la publication COPY : 134 tests ciblés (`file_safety`,
`file_install`, `txtconv`, `imgconv_safety`, `six_plugins`, `goto_safety`,
`batch`, `file_output`, `tree_stack`, `check_layout`), deux éditions natives
et sept supports ProDOS contrôlés. Le banc COPY contrôle les octets de
l'ancienne destination pendant chaque écriture et fermeture, et interdit le
premier renommage avant les quatre fermetures de transfert/vérification.
Il couvre les fichiers vides, les limites de chemin, les collisions de
temporaires, les conflits avec la source, les pannes d'installation et de
restauration. Les deux variantes de `file_install` sont exécutées sur les
deux CPU avec sim65. Pas de nouvelle qualification POM2, CI ou matérielle,
ni d'exécution globale de `make test` pour cet incrément.

Validation locale de la finalisation COPY : 43 tests ciblés (`file_safety`,
`batch`, `file_output`, `file_install`, `file_create`, `tree_stack`,
`check_layout`), deux constructions natives et sept supports ProDOS contrôlés.
Les nouveaux cas combinent nettoyage échoué avec écriture, fermeture,
annulation ou ouverture échouée, avec et sans ancienne destination. Ils
comparent les octets et interdisent toute tentative de restauration après
nettoyage échoué. Pas de nouvelle qualification POM2, CI ou matérielle, ni
de suite globale `make test` pour cet incrément.

`tools/test_file_safety.py` compile ces deux modules réels avec le code de
sauvegarde de l'éditeur. Les tests contrôlent les octets de la source, de la
destination et des sauvegardes sur fichiers jetables : lecture, écriture,
fermeture, corruption silencieuse, collision, restauration et nettoyage.
Deux séquences supplémentaires couvrent annulation puis copie, et succès
puis refus de chargement, en conservant les tampons sales entre opérations.
Les mesures natives sont dans [MEMORY-BUDGETS.md](MEMORY-BUDGETS.md).

## DOSGET and FIXTYPES (September 2026)

DOSGET writes only exclusively reserved ProDOS outputs; it reads the DOS
source without modifying it. BIN load address and BIN/BAS/INT EOF come from
the first sector header, not the rounded catalog size. Repeated/out-of-range
sectors and malformed end links are refused. Reads, writes, stream errors,
reservation/output/source closes and cleanup failures are checked. Completed
outputs remain if the source close fails; a failed cleanup names the retained
partial output. This is extraction, not move: the source is never deleted.
No full output readback or power-loss atomicity is promised.

FIXTYPES reads content and writes only confirmed SET_FILE_INFO/RENAME calls.
GET_FILE_INFO must succeed, the file must be writable, and metadata is checked
again after confirmation. A rename requires a positive $46 (not found) for
the destination; any other lookup error refuses it. DUET repair preserves
names and bytes; generic BIN suffixes preserve an existing load address.
Each format proposal is confirmed separately. A failed metadata verification
is reported; ProDOS cannot make a physical metadata write power-fail atomic.
Neither operation writes AUX. Both consume the API v5 active-entry snapshot
at $3000; DOSGET code ends below $2800, its visited-sector bitmap is at $2800,
and its T/S list copy is at $2F00. FIXTYPES code and BSS end below $3000.

## Journal du chantier 1 (0.8.0 → 0.8.5)

Déplacé de `TODO.md` à la publication de la 0.8.5 : les incréments dans
l’ordre où ils ont été livrés, avec les coûts mesurés à chaque lien. Les
contrats en vigueur sont décrits plus haut ; ce journal explique pourquoi
ils ont cette forme.

Premier incrément du 13 septembre : réservation exclusive et moteur COPY
extraits dans `src/file_output.h` et `src/file_copy.h`, contrats de buffers
et de chargement dans [FILE-SERVICES.md](FILE-SERVICES.md). Binaires
identiques sur les deux CPU ; contrôle de capacité de `CopyState` et deux
séquences de pannes ajoutés au banc C. Le contrat unique, les migrations des
plugins et le gain de marge COPY restent à faire : aucune case globale close.

Deuxième incrément ProDOS : CREATE commun à TXTCONV et aux utilisateurs de
`util.h` (dont SYNC), dans `src/plugins/file_create.h`. Tous les codes MLI
restent des refus sauf zéro ; tests natifs sur deux CPU avec BSS sale et
séquences fichier/répertoire, plus conservation des octets sur erreur de
création. TXTCONV coûte +35/+33 octets (65C02/6502), BSS inchangé ; les autres
plugins sont identiques. GOTO, IMGCONV et les remplacements restent à unifier.

Troisième incrément ProDOS : résultat de restauration explicite dans
`replace.h` et nettoyage contrôlé partagé par TXTCONV/IMGCONV. Une annulation
IMGCONV n'annonce plus la suppression si elle échoue. Les tests comparent
les octets après pannes combinées, nouvelle tentative et collision tardive
empêchant la restauration. Le contrat est décrit dans FILE-SERVICES ; les
autres moteurs et leurs nettoyages restent à migrer (chantiers 1 et 3 ouverts).

Quatrième incrément : transaction de renommage commune à SYNC, TXTCONV et
IMGCONV dans `file_install.h`. SYNC garde son résultat vérifié après échec
d'installation et s'arrête sur récupération nécessaire, avec diagnostic
persistant. Tests du parcours complet et du fichier suivant ; séquences
natives sur les deux CPU. Les appels API compacts libèrent 730/728 octets
dans SYNC, sans relever son plafond. COPY, GOTO, BATCH et l'unification de
leurs politiques de nettoyage restent ouverts.

Cinquième incrément : GOTO rejoint `file_install`, après contrôle explicite
des métadonnées/protections de `GOTO.CFG`, avant toute création. Le temporaire
vérifié reste récupérable après échec d'installation. Les tests contrôlent
les octets après collisions tardives, pannes combinées et nouvelle tentative.
Coût 157/164 octets et un octet BSS, avec 145/160 octets encore libres avant
les favoris à `$3000` (65C02/6502). COPY et BATCH restent à traiter ; la
création particulière `$E3` de GOTO n'est pas encore mutualisée.

Sixième incrément : BATCH utilise la réservation exclusive résidente commune
à `new_output` et donc COPY. Le résultat distingue absence de propriété,
réservation utilisable et création suivie d'une fermeture échouée. BATCH garde
la propriété du manifeste si son nettoyage échoue ; aucune source n'est
déplacée. Tests des octets, collisions et nouvelles tentatives, plus exécution
du service sur deux CPU. BATCH gagne 20 octets, LOWBSS 2 ; coût résident
30/35 octets. La publication récupérable de COPY et les politiques de
nettoyage restantes ne sont pas encore unifiées ; aucune case globale close.

Septième incrément : finalisation COPY résidente, sans chargement imbriqué ;
COPY conserve la propriété issue de `reserve_output`, y compris sur fermeture
échouée. Un nettoyage échoué est signalé même après annulation et bloque la
restauration par-dessus le résultat. Source et sauvegarde restent conservées.
La marge COPY passe de 33/25 à 116/111 octets ; MAIN conserve 256/766 octets,
BSS inchangé. Tests des octets avec et sans ancienne destination. La
publication par temporaire vérifié reste à unifier : COPY écrit encore sous
le nom final après sauvegarde préalable.

Huitième incrément : COPY publie désormais `A2FC.COPY` avec la transaction
commune après fermeture et relecture complète. L'ancienne destination reste
intacte jusqu'à ces contrôles ; installation ou restauration échouées gardent
les fichiers de récupération. Tests des octets pendant le transfert et des
collisions tardives. La variante liée à CP évite sept octets d'arguments sur
la pile. COPY conserve 79/76 octets libres ; MAIN tombe à 149/659 : regagner
la marge 65C02 devient prioritaire avant le prochain enrichissement. Les
autres nettoyages de `new_output` et les créations particulières des plugins
restent ouverts ; le contrat global n'est pas encore clos.

Neuvième incrément : les textes privés d'EDIT, MENU, BINARY2 et UNSHRINK
résident dans leurs surcouches, avec une durée de validité bornée à l'appel
ou une copie dans `note`. Gain MAIN de 127 octets par CPU ; réserves
276/786, objectif 65C02 de 256 retrouvé. Pile, BSS, plafonds et opérations
sur fichiers inchangés. Les surcouches modifiées gardent au moins 86 octets
libres ; 39 tests ciblés et les sept images ProDOS contrôlés. Les nettoyages
restants du chantier 1 et les marges DELETE/IMGFS/ATTR restent ouverts.

Dixième incrément : EDIT conserve la propriété de sa réservation et contrôle
les suppressions de `A2FC.EDIT` après échec. Une fermeture de réservation
échouée interdit la réouverture ; nettoyage échoué et nouvelle tentative
conservent les fichiers et le tampon modifié, avec diagnostic de récupération.
42 tests ciblés, deux liens et sept images ProDOS contrôlés. EDIT garde
248/234 octets libres, MAIN 281/791. Les autres appelants de `new_output`
et la mutualisation du renommage EDIT restent ouverts.

Onzième incrément : EDIT publie via `file_install.h`, compilé dans sa
surcouche. Le temporaire vérifié reste conservé après tout échec de
transaction ; restauration échouée et sauvegarde retenue ont leurs diagnostics.
Tests des collisions tardives, du premier renommage, de la restauration,
d'une première sauvegarde et des nouvelles tentatives, avec contrôle des
octets et des fermetures avant renommage. 48 tests ciblés, deux liens et
sept images ProDOS passent ; EDIT garde 138/118 octets libres, MAIN reste
à 281/791. Les nettoyages des autres appelants de `new_output` restent ouverts.

Douzième incrément : BINARY2 réserve directement ses sorties et contrôle
leur nettoyage. Une troncature d'en-tête, contenu ou remplissage, ou une
fermeture échouée, n'annonce plus un succès. Les extraits précédents et les
collisions restent intacts ; un nettoyage échoué nomme le fichier conservé.
Neuf régressions C intégrées à `make test`, 56 tests ciblés et sept images
ProDOS validés. BINARY2 garde 1 694/1 709 octets libres ; résident inchangé.
Les nettoyages UNSHRINK, DISKIMG, IMGFS et DOS33 restent ouverts, ainsi que
la relecture des sorties et la validation complète des attributs Binary II.

Incrément demandé : écriture sur vrai DOS 3.3 depuis ProDOS par C / DOSWRITE
(FILES/XL), pour la sélection TXT/BIN/BAS/INT jusqu'à 65 535 octets. Audit
complet des allocations, création sans remplacement, contrôle de protection,
confirmation, VTOC réservé, relecture et publication finale du catalogue.
Source conservée ; pas de MOVE. Écriture dans les images ajoutée à la
demande explicite suivante, via copie temporaire vérifiée et remplacement
récupérable (DOSIMAGE/DOSPUT, FILES/XL). Les échecs peuvent
laisser de l'espace réservé, signalé. Le retour à la liste des volumes
réinitialise aussi le mode DOS/image pour permettre les réouvertures.
Le slot réel du Disk II est désormais utilisé, notamment S5 avec le volume
ProDOS en S6. Tests C de pannes, sim65 deux CPU, banc POM2 Disk II dans
`doswrite` et images DSK/2MG dans `dosimage`. Aucun accès AUX.
La copie par lots et les autres mutations DOS restent à faire.

Suite du chantier 1 : DISKIMG conserve la propriété de sa réservation,
contrôle les fermetures et nettoie uniquement l'image créée par R. Un
nettoyage échoué nomme le fichier conservé, même après annulation ; W/O
n'effacent jamais leur source. Tests C PO/DSK, pannes combinées et retry,
32 tests ciblés et sept images contrôlés. DISKIMG gagne 50/39 octets,
résident inchangé. Restent UNSHRINK, IMGFS, DOS33 et la relecture complète
des images créées.

Suite du chantier 1 : UNSHRINK réserve directement ses sorties et signale
leur nettoyage échoué, avec conservation des octets lors d'une nouvelle
tentative. Les sauts deviennent des lectures exactes ; troncatures, erreurs
de flux et fermetures échouées ne donnent plus un succès. Annulation entre
blocs, noms longs préservés avant lecture du remplissage, bornes des tailles
et compte rendu des compressions ignorées. Tests C avec pannes combinées,
ASan/UBSan, octets conservés et garde de pile dans le banc natif. Restent
IMGFS/DOS33, les CRC et métadonnées NuFX complets, la validation complète du
décodeur LZW sur flux malformés et la relecture des extraits ; aucune case
globale close.
