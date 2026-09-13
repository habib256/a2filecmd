# Stabilisation en cours

Objectif : suivre les quatre étapes de l'évaluation du 11 septembre 2026.
Ce suivi distingue les changements réalisés de leur qualification ; aucune
étape n'est acquise sur la seule présence de tests ou de documentation.

| Étape | Travail requis | Preuve de clôture | État |
| --- | --- | --- | --- |
| 1. Préservation | Corriger MOVE entre volumes ; revoir les validations avant suppression/remplacement, dont SYNC et configuration | Régressions exécutant le C, octets originaux conservés sur chaque échec ; revue des autres chemins | En cours |
| 2. Pannes combinées | Taille périmée + lecture finale ; fermetures ; renommage/restauration ; collisions et annulation | Matrice documentée, tests hôtes et bancs natifs pertinents sur les deux CPU | En cours |
| 3. Décodeurs et mémoire | Distinguer erreurs et fins normales ; contrôler les limites ; étendre les mutations ; dégager de la marge | Corpus/mutations reproductibles, rendus natifs, cartes mémoire avec plafonds inchangés | À faire |
| 4. Livraison | Suivi Git cohérent, TODO/manuels à jour, critères CI explicites ; qualifier une révision précise | Tests complets, sept supports relus, CI, bancs émulateur, résultats matériels identifiés | À faire |

## Périmètre des écritures examinées

- MOVE intervolumes : création exclusive de la destination, écriture puis
  relecture de cette copie, suppression de la source uniquement après succès.
  Tampons en mémoire principale ; pas de reconstruction de `/RAM`.
- SYNC : création exclusive d'A2FC.SYNC ; sauvegarde de l'ancienne destination
  en A2FC.BAK, installation puis nettoyage. Source en lecture seule ; mémoire
  principale. L'original doit rester récupérable lors de toute erreur.

## Validation sur matériel réel

Le 12 septembre 2026, le mainteneur confirme que la validation réelle est
faite sur **Apple //c, Apple IIe enhanced et Apple IIe unenhanced**, avec un
fonctionnement satisfaisant sur les trois machines. Ce résultat remplace
le précédent constat d'indisponibilité de matériel et complète les bancs POM2.

La révision exacte, les lecteurs et le détail des scénarios ne sont pas
consignés dans ce retour. Il confirme le fonctionnement sur ces machines ;
les régressions avec pannes injectées et les travaux logiciels ci-dessous
conservent leur suivi propre. Le IIgs reste à valider.

## État initial observé

- MOVE reproduit : 8 octets source, taille de panneau 4, erreur de lecture
  finale => copie de 4 octets puis source supprimée. Les fermetures finales
  ne bloquent pas non plus la suppression.
- SYNC ignore les fermetures de sa vérification et ne distingue pas une
  erreur de la fin des flux lors du contrôle final.
- Construction 65C02 initiale : 19 octets avant le plafond résident, 17 octets
  de mémoire basse libres, 1 octet de carte langage libre.

## Corrections et preuves partielles

- MOVE : erreurs de lecture finale et de toutes les fermetures bloquent la
  suppression. L'annulation pendant copie/vérification est prise en compte.
  Tests : 31 tests MOVE hôtes, dont taille périmée + erreur finale, disque
  plein simulé, lecture courte, annulation, quatre fermetures en échec.
- SYNC : erreurs des deux flux et quatre fermetures contrôlées. Les tests
  couvrent aussi installation + restauration en échec et nettoyage de
  sauvegarde impossible. Tampon de comparaison réduit de 512 à 256 octets
  pour conserver les plafonds de code/BSS.
- TXTCONV : contrôle d'erreur même si la taille périmée coïncide avec la
  lecture interrompue ; seconde conversion en lecture seule, comparée au
  fichier fermé, y compris EOF. Tests de corruption silencieuse, fermeture,
  réouverture, erreur de vérification et annulation des deux passes.
- IMGCONV : source et destination fermées avec contrôle ; relecture de tous
  les blocs logiques, en-tête généré et EOF avant remplacement. L'écriture
  DSK reste séquentielle mais lit les secteurs à leur position dans la
  source, supprimant le tampon de piste à $3000. Code/BSS restent contrôlés
  sous $4000 ; le tampon partagé est en mémoire principale, sans AUX.
- GOTO : absence distinguée d'une erreur d'ouverture ; erreurs de lecture et
  fermeture bloquent les modifications. La sauvegarde est relue intégralement
  avant renommage. Six tests hôtes couvrent aussi les doubles pannes de
  renommage et les noms de récupération déjà présents.

Les bancs natifs initiaux MOVE (13/13) et six plugins dont SYNC (16/16)
passent sur les deux CPU. TXTCONV/IMGCONV sont en cours de requalification
après ajout de la seconde lecture. Les tests et images doivent encore être
relancés sur la révision finale ; ces résultats ne clôturent pas les étapes.

## Étape configuration, mémoire et MOVE marqué

- A2FILE.CFG : temporaire exclusif, relecture complète, sauvegarde de
  l'original pendant l'installation et contrôle des restaurations/nettoyages.
  Sept tests C avec injections de pannes ; un test sim65 exécute le parseur
  optimisé avec les deux compilateurs et couvre un défaut d'adressage cc65.
- NAV contient la navigation ; BATCH orchestre les fichiers marqués via un
  manifeste exclusif et vérifié dans la destination. Cinq tests C couvrent
  collisions, annulation, données altérées et erreurs d'E/S/fermeture.
- MUSIC contient désormais tout le lecteur MB1 au premier plan, avec 4 Ko
  en mémoire principale. Cinq tests C contrôlent les limites des paquets
  et les erreurs avant démarrage matériel. Seule la petite détection de
  Mockingboard partagée avec PT3 reste résidente.
- Compilation enhanced à cette étape (avant la navigation multimédia) : fin MAIN à `$B775`, soit 1 899 octets avant `$BEE0` ;
  123 octets de carte langage libres et 314 octets libres dans LOWRAM.
  Les plafonds de pile et de surcouche sont inchangés sur les deux CPU.
- Bancs natifs dédiés : `music.py`, `pt3.py`, `roi.py` et `batch_missing.py`.
  Résultats POM2 : 53/53 contrôles sur IIe non enhanced et 54/54 sur IIe
  enhanced (MB : 9 chacun ; BATCH invalide : 3 chacun ; PT3 : 16/17 ;
  configuration/MOVE : 25 chacun). Les octets déplacés, les collisions,
  les fichiers non marqués, AUX, la pile et le redémarrage sont contrôlés.
  `make test` : 372 tests hôtes réussis ; les sept images sont conformes
  aux binaires construits. Les images de test sont jetables ; ces nouvelles
  modifications ne sont pas implicitement couvertes par le retour matériel
  antérieur.

## Navigation multimédia, crédits PT3 et retour au dossier parent

- Gauche/droite parcourt les morceaux du même format (MB ou PT3) et les
  images du même lecteur, y compris Extasie, PACKFOT, 816/Paint, DGR,
  MGTK, LZ4FH et Print Shop. La recherche traverse les fenêtres de 139
  entrées, conserve les marques et reste dans le répertoire courant.
- Le lecteur PT3 affiche les champs titre et artiste/crédit du module,
  bornés à 32 octets chacun, ainsi que le crédit du lecteur Vince Weaver
  et de l'adaptation A2FC. Aucun en-tête de module n'est modifié.
- Échap et « .. » retrouvent le dossier quitté par son nom dans le parent,
  même au-delà de la première fenêtre, sur chacun des deux panneaux.
- Ces chemins lisent les fichiers et répertoires sans écriture disque.
  La musique ne touche pas AUX ; les lecteurs d'images qui utilisent AUX
  conservent la confirmation préalable de perte de TOUS les fichiers `/RAM`,
  y compris lors du passage à l'image suivante. Une erreur de relecture
  pendant la recherche empêche de lancer un média sur une sélection incertaine.
- Construction enhanced à cette étape : fin MAIN `$BE4E`, soit 146 octets avant
  `$BEE0` ; carte langage 123 octets libres, LOWRAM 292. NAV finit à `$1F1A`
  et OPEN à `$1FB6`, sous `$2000`. Les deux architectures passent les contrôles
  de disposition sans changer les plafonds ; le module PT3 conserve ses
  4 608 octets disponibles.
- Validation finale de cette étape : 376 tests hôtes réussis ; 43/43
  contrôles POM2 sur chaque CPU (34 multimédia et 9 navigation de grand
  répertoire), soit 86/86. Les bancs contrôlent les rendus, les crédits,
  les marques, AUX, la pile et les octets des volumes après arrêt avec
  sauvegarde effective du disque émulé. Les sept images de distribution
  correspondent aux binaires construits. Manuel et PDF actualisés.
  Les supports POM2 sont jetables ; le retour matériel antérieur n'est pas
  présenté comme une qualification de ces nouvelles modifications.

## Bug hunt préalable à la 0.7.6

La revue suivante est consignée dans [BUG-HUNT-0.7.6.md](BUG-HUNT-0.7.6.md).
Elle corrige notamment un dépassement de pile reproduit sur un arbre de vingt
niveaux, les erreurs/cycles de catalogues, un curseur devenu invalide et deux
problèmes de qualification/livraison. Les résultats et marges mémoire de cette
revue remplacent ceux des étapes précédentes pour le contenu de travail actuel.

## Travail restant identifié

- Terminer la revue des autres chemins avant suppression/remplacement et
  consigner leurs limites, notamment les erreurs de nettoyage et de restauration.
- Décodeurs : erreurs d'E/S, sorties partielles et toutes les sorties après
  utilisation destructive d'AUX ; campagne de mutations élargie.
- Finaliser CI, suivi Git, TODO et manuels ; qualification intégrale d'une
  révision précise, en complément de la validation matérielle confirmée
  sur //c et sur les deux variantes du IIe.

## Candidat 0.8.0

La dernière passe et les empreintes du candidat sont consignées dans
[BUG-HUNT-0.8.0.md](BUG-HUNT-0.8.0.md). Le numéro est désormais 0.8.0 ;
les résultats historiques ci-dessus restent ceux des étapes précédentes.
