# Sécurité des données d’A2FC

La conservation des données est une exigence centrale. Les instructions
obligatoires pour les IA et les contributeurs se trouvent dans
[AGENTS.md](../AGENTS.md). Cette revue du 11 septembre 2026 porte sur les
chemins d’écriture, de remplacement, d’effacement et d’utilisation de la
mémoire auxiliaire. Elle ne constitue pas une garantie contre toute panne
matérielle ni une preuve exhaustive de l’absence de défauts.

## Risques corrigés

| Opération | Risque constaté | Protection et régression |
| --- | --- | --- |
| Copie C et déplacement V | Destination supprimée avant la copie ; source supprimable sans relecture de la destination | Ancienne destination renommée en `A2FC.BAK`, création exclusive, contrôle des lectures/écritures/fermetures, comparaison intégrale des deux flux et de leur taille. Restauration sur erreur. `test_file_safety.py`, `bench/data_safety.py`, `bench/ops.py`. |
| Parcours récursifs | Lecture courte d’un répertoire assimilée à sa fin ; noms corrompus susceptibles de rediriger un chemin | Un lien de continuation doit être lisible intégralement. Noms ProDOS contrôlés avant utilisation ; `list_dir` transmet l’erreur et empêche de considérer la copie comme complète. `test_core_dirscan.py`. |
| Éditeur E | Ouverture tronquante de l’original ; lecture initiale incomplète acceptée | Écriture exclusive dans `A2FC.EDIT`, fermeture et relecture octet par octet avant installation ; original conservé sous `A2FC.ED.BAK` pendant le renommage. Une sauvegarde échouée conserve le tampon modifié. `test_file_safety.py`, `bench/data_safety.py`. |
| Binary II, ShrinkIt, extraction ProDOS/DOS 3.3 | Écrasement silencieux de fichiers existants ; erreurs de fermeture ignorées | Création exclusive commune, aucune suppression d’un fichier préexistant en nettoyage, contrôle de fermeture. Bornes supplémentaires des noms et chemins Binary II/ShrinkIt ; erreurs des grandes surcouches conservées dans le message final. |
| TXTCONV | Suppression de la source avant renommage ; suppression immédiate d’une destination confirmée | Conversion dans un temporaire exclusif, contrôle du nombre d’octets lus et des fermetures, installation avec sauvegarde et restauration. Temporaires et sauvegardes existants conservés. `test_txtconv.py`, `bench/txtconv.py`. |
| IMGCONV | Sonde `fopen(rb)` confondue avec une preuve d’absence ; suppression avant conversion | GET_FILE_INFO distingue absence et erreur ; CREATE exclusif ; conversion temporaire avant remplacement avec sauvegarde. `test_imgconv_safety.py`, `test_imgconv.py`, `bench/imgconv.py`. |
| MOVE, déplacement rapide sur un volume | Erreur entre les écritures brutes laissant deux entrées partageant les mêmes blocs ; backlink de sous-répertoire non validé | Validation du backlink et du stockage ; relecture des écritures ; sur erreur signalée, restauration de l’entrée source, du backlink et des compteurs avant suppression de la copie d’entrée. Avertissement interdisant de supprimer les entrées si la restauration échoue. Tests avant **et après** écriture effective à chaque étape dans `test_move.py`, puis `bench/move.py`. |
| WIPE F | Bitmap déclarant libre un bloc encore utilisé : le mode « espace libre » effaçait des données vivantes | Précontrôle de tous les blocs référencés par les répertoires et les fichiers seedling/sapling/tree, bornes et bits d’allocation. Aucune écriture si lecture impossible, structure non prise en charge, cycle détecté ou annulation. `test_wipe.py`. |
| DISKIMG | Image source tronquée ou 2MG malformée acceptée avant écriture destructrice ; possibilité de cibler le volume contenant l’image | Validation de la taille réelle, du format, de la plage de données et des pistes DSK. Volume source protégé comme cible ; refus de lire un disque dans une image située sur ce même volume ; disque RAM exclu des transferts bruts utilisant AUX. `test_diskimg_input.py`, `test_diskimg_verify.py`. |
| Images, musique, ShrinkIt, copies de disque et formatage physique | Utilisation d’AUX détruisant le disque RAM avec un avis seulement après coup | Drapeau `OVERLAY_AUX` et confirmation explicite avant utilisation, également pour une surcouche déjà chargée ; confirmation dédiée avant le formatage physique. La reconstruction reste permise pour libérer de la mémoire. `bench/data_safety.py` compare les octets AUX avant/après refus. |
| BLKEDIT | Tampon déclaré propre après échec de relecture de contrôle | Le tampon reste modifié pour permettre une nouvelle tentative ou un abandon explicite. |

## Autres chemins d’écriture examinés

- **SYNC** : copie temporaire exclusive, comparaison complète, sauvegarde puis
  installation ; source conservée. Tests existants de pannes et tailles périmées.
- **RESCUE et UNDELETE** : destination sur un autre volume, création exclusive,
  source ouverte en lecture. RESCUE conserve volontairement le résultat partiel
  et son journal ; UNDELETE refuse les blocs réutilisés ou ambigus.
- **MKIMAGE, rapports VOLINFO, exports BLKVIEW et DISASM** : création exclusive.
  Certains exports conservent explicitement un résultat incomplet plutôt que
  de prétendre avoir réussi.
- **Suppression, renommage et attributs** : confirmations des suppressions,
  opérations ProDOS pour les fichiers ordinaires, erreurs propagées. RENAME
  ProDOS refuse une destination existante. L’édition brute de blocs et MOVE
  exigent leurs propres contrôles puisqu’ils contournent ces garanties.
- **FORMAT, WIPE W, BOOTBLK** : opérations destructrices explicites, cible
  affichée et confirmation ; protection du volume du programme. BOOTBLK
  modifie les deux blocs de démarrage, pas les blocs de fichiers.

## Fichiers de récupération et limites

Ne pas effacer automatiquement `A2FC.BAK`, `A2FC.ED.BAK`, `A2FC.EDIT`,
`TXTCONV.TMP` ou `IMGCONV.TMP`. Un reste peut être la seule version intacte
après un échec de renommage. Examiner/copier son contenu avant de le renommer
ou de le supprimer. Une collision bloque l’opération concernée.

ProDOS ne fournit pas une transaction couvrant plusieurs écritures physiques.
Une coupure pendant MOVE peut encore laisser des entrées partageant des blocs :
ne supprimer **aucune** de ces entrées avant récupération sur un autre volume.
La restauration ajoutée traite les erreurs renvoyées pendant l’exécution ;
elle n’est pas un journal persistant de reprise après coupure.

FORMAT, WIPE W et les écritures brutes ne sont pas annulables après leur début.
Une défaillance physique persistante peut empêcher une restauration ; BOOTBLK
ne possède pas de restauration automatique de ses deux anciens blocs. Une
relecture valide le contenu rendu par le pilote, pas sa persistance après une
perte d’alimentation. Les conversions vérifient leurs écritures et fermetures,
mais ne disposent pas toutes d’une seconde comparaison intégrale sur le support.

WIPE F refuse les stockages étendus et les profondeurs dépassant sa pile de
parcours ; il privilégie le refus à l’effacement avec un diagnostic incomplet.
La configuration de session `A2FILE.CFG` reste une écriture directe : une erreur
peut perdre des préférences de panneaux, sans autoriser l’écrasement d’un fichier
choisi dans les panneaux. La résistance complète des décodeurs à tout fichier
malformé demanderait une campagne de fuzzing distincte.

## Validation et contraintes mémoire

`make test` exécute les tests hôtes, dont les pannes injectées dans les véritables
routines C. `make disk` compile les deux architectures et contrôle les plafonds
résident, pile, BSS et surcouches avant de fabriquer les supports. Les nouveaux
scénarios natifs sont dans `bench/data_safety.py` ; les autres bancs cités plus
haut utilisent également des volumes jetables.

Résultats de cette revue : **290 tests hôtes réussis**, huit images contrôlées
(BOOT, EXTRA, EXTRA2 et XL pour 6502 et 65C02), **14/14 contrôles de sécurité
natifs sur chacune des deux architectures** et **72/72 contrôles de session
complète**. Les bancs natifs ciblés passent également : opérations 7/7,
TXTCONV 25/25, IMGCONV 25/25, MOVE 13/13, WIPE 13/13 et FORMAT 31/31. Les tests de sécurité
sur les deux processeurs sont ajoutés à la CI pour les modifications futures.

La copie réside désormais dans la petite surcouche interne `COPY.PLG`, livrée
avec BOOT. Elle conserve les deux tables de fichiers pendant les parcours.
L’éditeur réserve davantage de code de protection et accepte **5 104 octets**.
DISKIMG utilise trois blocs de préparation en mémoire principale au lieu de
quatre pour loger ses contrôles supplémentaires. Aucun plafond de mémoire
ni contrôle du lieur n’a été désactivé.
