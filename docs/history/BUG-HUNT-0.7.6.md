# Bug hunt avant la 0.7.6 — 12 septembre 2026

Revue locale du contenu de travail, incluant les changements non encore
commités. Ce document ne qualifie pas un tag publié ni une exécution CI distante.
Les corrections portent sur les lectures de répertoires et d'images, la sélection
multimédia et la préparation des bancs/publications. Les parcours corrigés ne
font aucune écriture de fichier ou d'AUX. Les opérations récursives restent
susceptibles de copier/supprimer des fichiers : une lecture ou fermeture de
répertoire échouée doit donc empêcher de considérer leur parcours comme complet.

## Défauts reproduits et corrigés

| Priorité | Déclencheur et conséquence avant correction | Correction et preuve |
| --- | --- | --- |
| **Bloquante** | Copie d’un arbre de 20 niveaux : témoin de pile écrasé en POM2. | Garde de pile réel avant les lectures récursives ; parcours préalable avant suppression. `test_tree_stack.py` teste les 65 536 adresses sur les deux CPU ; `bench/tree_safety.py` vérifie copie/suppression refusées sans aucun octet disque modifié et copie ordinaire conservée. |
| Haute | Échec de fermeture du répertoire après lecture : `list_dir` renvoyait un succès, utilisable ensuite par la copie/suppression récursive. Un panneau acceptait aussi une liste interrompue. | `dir_close` conserve l'erreur ; les panneaux refusent les entrées partielles. C réel et erreurs injectées dans `tools/test_core_dirscan.py`, octets de la source inchangés. |
| Haute | Échec de `fseek` dans une image DOS : lecture au mauvais emplacement. Coordonnées hors de 35 pistes/16 secteurs : accès hors table possible sur disque réel. | Arrêt avant lecture ou appel disque, contrôlé par `tools/test_catalog_safety.py`. |
| Moyenne | Catalogues cycliques ne contenant que des entrées effacées : boucle sans fin, en DOS 3.3 comme dans une chaîne d'image ProDOS. Une erreur de secteur DOS était aussi traitée comme une fin normale. | Budget de 560 secteurs DOS, erreurs propagées ; liens arrière ProDOS vérifiés à chaque bloc. Tests C et `bench/catalog_safety.py`. |
| Haute | Répertoire raccourci entre la recherche du média voisin et la restauration : ancien index remis en place au-delà du nombre d'entrées relues. | Contrôle de la fenêtre et de l'index avant restauration ; refus de lecture dans ce cas. Régression C dans `tools/test_media.py`. |
| Livraison | Un job d'émulation annulé satisfaisait la condition « résultat différent de failure » de publication. | Seuls `success` et `skipped` autorisent cette condition. `skipped` reste prévu pour un dépôt sans exécuteur POM2. |
| Validation | La session complète attendait l'ancien lecteur MB résident et son utilisation d'AUX. Sa disquette complète avait atteint 291 blocs pour une capacité de 280. | Scénario MB au premier plan, retour naturel et AUX comparée ; copie MEDIA en lecteur 2. Archives testées via des disquettes dédiées, construites par `bench/archive_support.py`, avec le même binaire natif. |

Les nouvelles régressions C ont échoué sur les fonctions avant correction puis
réussi après correction. Les mutations utilisent ASan/UBSan, des fichiers
temporaires et les vrais décodeurs C ; les routines graphiques assembleur sont
représentées par les harnais de géométrie, puis exercées par les bancs POM2.

## Validation

- `make test` : **387 tests hôtes réussis**, dont les erreurs injectées et
  l'exécution du garde de pile sous sim65 pour les deux processeurs.
- Mutations déterministes, graine 41724 : **7 140 cas réussis** sur sept
  décodeurs. DGR 1 033 ; Extasie 1 011 ; PACKFOT et 816/Paint 1 022 chacun ;
  MGTK 1 011 ; Print Shop 1 022 ; LZ4FH 1 019.
- Les deux architectures compilent ; les **sept images de distribution** sont
  relues et correspondent aux binaires. Les trois fixtures d'archives restent
  dans 280 blocs chacune ; elles ne font pas partie des supports livrés.
- Bancs natifs ciblés : **68/68 contrôles sur chaque CPU**, soit **136/136**.
  Arbres profonds 6 ; catalogues malformés 5 ; préservation des données 14 ;
  multimédia 34 ; grands répertoires 9. Les refus de copie/suppression profonde
  conservent l'intégralité du volume, pas seulement les noms ou les tailles.
- Pile enhanced : **3/3 contrôles**, 92 octets utilisés sur les 192 réservés
  dans le scénario courant. Les arbres profonds ont leur propre scénario
  de refus avec comparaison de tous les octets du disque.
- Session fonctionnelle finale : **73/73 contrôles**, jusqu'à la relance
  d'A2FC depuis Applesoft. Avec les bancs ciblés et la pile : **212 contrôles
  POM2 réussis** sur les binaires finaux.
- Manuel et PDF actualisés ; `git diff --check` sans erreur.

## Limites et décision de livraison

Les défauts reproduits sont corrigés et les contrôles locaux sont tous réussis.
Le candidat peut passer à la CI sur une révision figée avant publication ; ce
constat ne remplace ni cette CI ni une qualification matérielle de cette révision.


- La construction enhanced finit à `$BEDB`, soit 5 octets avant le plafond `$BEE0` ;
  la carte langage atteint `$E000` et LOWRAM conserve 290 octets. Le code vivant
  finit à `$BE1F`, avant le plancher de pile `$BE40`. Aucun plafond ni contrôle
  de disposition n'a été assoupli. Toute modification native ultérieure exige
  un nouveau lien et une nouvelle qualification des limites.
- La CI distante n'a pas été exécutée sur ces changements locaux. Son job POM2
  reste facultatif quand aucun exécuteur n'est configuré. Les essais PT3 utilisant
  AUTUMN dépendent du corpus GISTDATA local, lu sans modification.
- Le retour matériel antérieur sur //c et les deux IIe reste documenté ; il ne
  constitue pas un nouvel essai matériel de ces corrections.
- Les tests ne prouvent pas l'absence de tout défaut. Les coupures pendant les
  écritures physiques ProDOS ne sont pas rendues atomiques par ces corrections.
- Aucun commit, tag, push ou publication n'est effectué par ce bug hunt.

## Reproductibilité locale

Versions affichées par les outils utilisés : `cl65 V2.18 - N/A` pour enhanced,
`cl65 V2.19 - Git e11fb5c` pour 6502. Le second correspond au commit cc65
épinglé dans la CI. Empreintes SHA-256 des résidents qualifiés :

- `build/A2FILE.CODE.BIN` : `f4b41f2f872522a00005f2e81dca9ea7c7ba5f390b1e21ca9b3848a0438752cd`.
- `build-6502/A2FILE.CODE.BIN` : `21034d582e0764b570de7055cd734e320f7b91067400927c1a4aaf32cc4af001`.

## Passe complémentaire : livraison et choix du numéro

La revue complémentaire recommande **0.8.0**. Depuis la 0.7.5, PT3, les nouveaux
visualiseurs, la navigation multimédia, les catégories de surcouches et l'API
de plugins étendue constituent une évolution fonctionnelle substantielle.
La 0.7.6 conviendrait à une livraison limitée aux corrections. Le numéro de
construction reste pour l'instant 0.7.6 ; aucun tag 0.8.0 n'est créé.

Trois défauts supplémentaires des outils de livraison sont corrigés :

- La CI pouvait publier un tag différent de `A2FC_VERSION`, donc annoncer
  0.8.0 avec des fichiers construits et nommés 0.7.6. Elle refuse désormais
  cette incohérence avant compilation.
- Les notes annonçaient 53 surcouches alors que les XL en contiennent 59.
  Le nombre est désormais calculé depuis les sources et le manifeste des
  catégories, dont la cohérence est également contrôlée.
- Sur une branche avec une section Unreleased vide, les notes reprenaient
  l'ancien numéro pour les noms des téléchargements. Elles conservent désormais
  le numéro configuré pour la construction courante.

Sept tests de régression couvrent ces métadonnées et les refus du programme
en ligne de commande ; la suite complète `make test` a été réexécutée avec
**394 tests hôtes réussis**. Les tâches de configuration et de feuilletage Extasie
déjà réalisées sont également corrigées dans TODO, ainsi que la liste des
sept décodeurs soumis aux mutations.

Cette passe ne modifie aucun code natif. Les empreintes des deux résidents
correspondent toujours à celles ci-dessus ; les sept images passent à nouveau
`tools/check_images.py`. Les 7 140 mutations et 212 contrôles POM2 restent les
résultats de la qualification précédente, sans prétendre les avoir réexécutés
pour cette modification des outils de livraison. La CI distante sur une
révision figée reste à exécuter avant publication.
