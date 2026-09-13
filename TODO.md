# A2 File Cmd — feuille de route après la 0.8.0

La [0.8.0 est publiée](https://github.com/habib256/a2filecmd/releases/tag/v0.8.0).
Les fonctions livrées sont dans le [CHANGELOG](CHANGELOG.md). Deux produits
distincts : **Mini** (II+ 48 Ko, DOS 3.3, 40 colonnes) et **A2FC ProDOS**
(IIe 128 Ko). `make mini` ne partage pas `src/a2fc.c`.

**Prochaine étape ouverte : Mini en 6502 pur** (chantier 0). Ce n’est pas
un raccourci pour les services ProDOS. Sur ProDOS, le goulot reste
d’écrire sans régresser, dans 128 Ko, pile C de 192 octets.

Les réserves ProDOS se recalculent à chaque lien. Point de départ après le
routage média : MAIN libre 259/779, OPEN 185/215, LC 168/163 octets
(65C02/6502). Les petites surcouches restent serrées (voir
[MEMORY-BUDGETS.md](docs/MEMORY-BUDGETS.md)) ; ne pas relever les plafonds.

## Contrat

Préserver les données prime. Un gestionnaire Apple II se juge sur les
écritures, pas sur un format d’image de plus.

Mini (**0**) est livré et indépendant de 1–10. Sur ProDOS :
**1 → 6** (mesure mémoire à chaque extraction) **→ 2 → 3 → 4**, avec
**7 en continu**. Puis **5**. Ensuite **un seul** parmi 8, 9 ou 10 — pas les
trois. Ne pas ouvrir SHRINK, l’écriture dans une image montée, un journal de
coupure, Pascal/CP/M ni un nouveau média tant que 1–4 ne sont pas clos.
Mini 0.7.0 ajoute tags, HGR, création TXT exclusive, éditeur et DEL
(catalogue d'abord). Pas de renommage, remplacement sur place, copie à
un seul lecteur ni formatage.

Les travaux sur lecteurs physiques sont signalés par **💾**.

| # | Chantier | Résultat recherché | État |
| --- | --- | --- | --- |
| **0** | Mini 6502 pur | Copie 4,4× plus rapide ; 0.7.0 : HGR, éditeur, TXT, DEL, tags | **Fait ; C retiré** |
| **1** | Services de fichiers sûrs | Un contrat unique : création exclusive, remplacement récupérable, copie vérifiée | À faire |
| **2** | Parcours d’arbres itératifs | État borné à la place de la récursivité ; refus sûrs conservés | À faire |
| **3** | Trous de préservation 0.8.0 | Conversions relues, pannes combinées, nettoyages/restaurations consignés | À faire |
| **4** | MOVE d’arbre entre volumes | Dossiers et marquage ; aucune source touchée après une copie partielle | À faire, après 1 et 2 |
| **5** | FIXIT lecture seule | Diagnostic et plan choisis par l’utilisateur ; zéro écriture | Après 4 |
| **6** | Contrats plugins et petites surcouches | Buffers, AUX, restauration ; respiration mesurée sans relever les plafonds | Avec 1 |
| **7** | Preuves de séquences | États d’overlays, mutations archives/FS, XL deux CPU, premier boot IIgs | Continu |
| **8** | 💾 NIBCOPY réel, puis un gain | Qualification Disk II physique ; un seul format ou reprise ensuite | Après 5, au choix |
| **9** | 💾 ADTPro blocs | Dossiers, envoi/réception, CRC, NAK ; pas de nibble en premier | Après 5, au choix |
| **10** | LAUNCHER | Favoris de programmes et retour automatique fiable à A2FC | Après 5, au choix |

## 0. Mini DOS 3.3 en 6502 pur

Édition autonome II+ 48 Ko : [MINI-DOS33.md](docs/MINI-DOS33.md).
**Réécriture faite ; les sources C sont retirées.** Huit modules
assembleur, sans compilateur ni bibliothèque cc65, sans pile logicielle.

Le goulot n’était pas le calcul mais l’attente du disque, et il est
mesuré (`bench/mini33_time.py`, cœur NMOS POM2, timings Disk II) :

| Mesure | C | asm | Gain |
| --- | ---: | ---: | ---: |
| Lecture d’un catalogue de 16 secteurs | 4 898 568 cycles | 1 703 592 | 2,9× |
| Copie de 48 secteurs, contrôles | 21 577 238 | 16 579 936 | 1,3× |
| Copie de 48 secteurs, écriture | 258 512 282 | 47 713 385 | 5,4× |
| **Copie totale à 1 MHz** | **280 s** | **64 s** | **4,4×** |
| Binaire livré | 12 065 octets | 7 750 | −4 315 |

Deux causes, aucune évidente d’avance : DOS 3.3 entrelace une piste en
2:1 et laisse ~25 000 cycles pour digérer un secteur avant l’arrivée du
suivant ; le C les dépassait et attendait un tour (200 000 cycles) par
secteur. Et le moteur de copie alternait les lecteurs **à chaque
secteur**, alors qu’un changement de lecteur coûte une course de tête et
un démarrage moteur. Les lots de 16 secteurs conservent les six
opérations disque par secteur et l’ordre de sûreté ; seul le rythme change.

Sémantique de copie inchangée et vérifiée : création exclusive, source
intacte, nom existant refusé, VTOC réservée avant toute donnée,
relecture de chaque écriture, comparaison intégrale des deux disques
avant publication, entrée de catalogue publiée en dernier, `copy_fault`
verrouillé sur une écriture incertaine. 0.7.0 ajoute les tags, le viewer
HGR, un éditeur qui ne sauve que sous un nom nouveau, et DEL qui marque
l'entrée de catalogue avant de libérer les secteurs. Toujours pas de
renommage, remplacement sur place, formatage ni copie à un seul lecteur.

Les tests hôtes exécutent désormais le **vrai 6502** sous sim65, les deux
images restant côté test pour pouvoir faire échouer, tronquer ou
corrompre une lecture ou une écriture choisie : 33 tests, plus les deux
bancs POM2 inchangés.

- [x] **Interface, catalogue, copie, runtime** — huit modules asm ;
  `tools/check_mini_layout.py` refuse à chaque lien un binaire qui
  mordrait sur DOS et affiche la réserve (1 096 octets aujourd’hui).
- [ ] **Réduire encore les changements de lecteur** — ils dominent ce qui
  reste : environ 20 par copie, à ~1 s chacun. Un lot plus grand demande
  de la mémoire, et les tables de noms des panneaux sont la seule réserve
  disponible ; mais `reload()` y relit le nom sélectionné pour retrouver
  le fichier après l’opération. Ne pas emprunter cette zone sans traiter
  ce point d’abord.
- [ ] **Relecture groupée après écriture** — écrire le lot puis le relire
  ferait gagner ~7 s, au prix d’écrire jusqu’à 15 secteurs de plus après
  la détection d’une corruption silencieuse. Trancher explicitement et
  documenter, ou laisser en l’état.
- [ ] **💾 II+ physique** — la qualification des écritures sur matériel
  réel reste ouverte ; les bancs POM2 ne la remplacent pas.

## 1. Services de fichiers sûrs

Centraliser progressivement les créations exclusives, remplacements
récupérables et copies vérifiées aujourd’hui dispersés (`replace.h`, COPY,
SYNC, TXTCONV, GOTO, BATCH). Conserver les tests de pannes et mesurer le
coût de chaque extraction (MAIN, carte langage, BSS, fenêtre de surcouche).

- [ ] **Contrat unique** — création exclusive, original récupérable jusqu’à
  la fermeture et aux contrôles, nettoyage limité aux fichiers réellement
  créés par l’opération, collisions de temporaires/sauvegardes refusées.
- [ ] **Découpage du résident** — extraire des modules de `src/a2fc.c` **sans**
  augmenter sa taille, au fil de ce chantier et du 6 ; pas de réécriture
  globale. Charger une surcouche de service ne doit pas écraser l’appelant.

Premier incrément du 13 septembre : réservation exclusive et moteur COPY
extraits dans `src/file_output.h` et `src/file_copy.h`, contrats de buffers
et de chargement dans [FILE-SERVICES.md](docs/FILE-SERVICES.md). Binaires
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

## 2. Parcours d’arbres itératifs

`count_tree`, `copy_tree` et `delete_tree` restent récursifs. Le refus quand
la pile est trop courte est correct ; ce n’est pas une architecture. Sans
état borné : pas de MOVE d’arborescence entre volumes, pas de DELETE
enrichi, pas de SYNC plus profond.

- [ ] **État borné** — remplacer progressivement la récursivité ; conserver
  les refus sûrs, le précontrôle avant le premier effacement, et la
  vérification complète avant toute suppression de source.
- [ ] **Très grands répertoires** — étendre les scénarios restants ; le
  retour au dossier quitté et la navigation entre fenêtres sont acquis.

## 3. Trous de préservation déjà identifiés

Dette de la 0.8.0, pas une fonctionnalité. Tant que ce n’est pas clos, toute
nouvelle écriture dilue la preuve. Voir aussi
[STABILIZATION.md](docs/STABILIZATION.md) et [DATA-SAFETY.md](docs/DATA-SAFETY.md).

- [ ] **Conversions** — comparaison intégrale du résultat relu pour les
  conversions qui ne vérifient encore que les écritures et fermetures.
- [ ] **Pannes combinées** — fermeture + collision + annulation ; taille
  périmée + lecture finale ; échecs de renommage, restauration et
  nettoyage. Consigner les limites restantes, y compris un nettoyage
  impossible.
- [ ] **Revue des autres chemins** — avant suppression/remplacement, y
  compris les erreurs de restauration. Une erreur de lecture, de
  métadonnées ou de fermeture n’est ni une fin de fichier, ni la preuve
  qu’un chemin est libre.

## 4. MOVE d’un arbre entre volumes

Trou Commander le plus visible. Aujourd’hui : même volume = réécriture
d’entrée ; autre volume = fichier seul, relu, puis source effacée ; dossiers
marqués refusés. Ne pas le bricoler dans le récursif actuel.

- [ ] **Répertoires et descendance** — entre volumes, copier et vérifier ;
  ne supprimer **aucune** source après une copie partielle, une arborescence
  incomplètement lue, ou une taille de panneau périmée.
- [ ] **Dossiers marqués** — même garanties que le fichier seul ; une
  confirmation identifie la cible avant la première écriture.

## 5. FIXIT : diagnostic et plan, zéro écriture

VOLINFO sait scanner. Le saut utile n’est pas « réparer », c’est un **plan**
que l’utilisateur choisit. Les écritures de correction viennent **après** la
clôture de ce plan, pas avant.

- [ ] **Diagnostic et plan** — partir du rapport sans écriture de VOLINFO :
  allocation, références partagées, pointeurs invalides, compteurs et blocs
  perdus. Compléter types, dates et effacements incomplets. Signaler les
  blocs partagés ou hors volume **sans les modifier**.
- [ ] **Corrections (après le plan)** — conserver les blocs d’origine, faire
  choisir et confirmer chaque correction, puis vérifier chaque écriture.
  Étudier séparément la reconstruction d’une racine perdue et l’isolement
  des blocs défectueux.

## 6. Contrats des plugins et petites surcouches

DELETE, COPY, IMGFS et ATTR ne peuvent plus absorber une ligne de garde.
Documenter et extraire, sans relever les plafonds. Une réserve dans MENU ou
BATCH n’est pas disponible pour un service partagé.

- [ ] **Contrats** — buffers prêtés, durée de validité, banques modifiées,
  états à restaurer, erreurs, consentement AUX. Uniformiser aussi
  ouverture, navigation, sortie et restauration d’écran des visualiseurs,
  sans changer le consentement AUX.
- [ ] **Respiration mesurée** — viser de la marge dans chaque petite
  surcouche **modifiée** ; traiter DELETE, COPY, IMGFS et ATTR avant de les
  enrichir. OPEN ne doit pas retomber à quelques octets au prochain média.

## 7. Preuves de séquences (continu)

Les tests isolés ne voient pas un overlay qui écrase les panneaux, un
consentement AUX qui survit, ou une table périmée après Échap. Ce chantier
accompagne 1–6 ; il n’attend pas la fin de 5.

- [ ] **Tests de séquences** — image → musique → copie ; annulation →
  nouvelle opération ; changement de disque → reprise. Vérifier états,
  ressources et octets, pas seulement le code de retour.
- [ ] **Mutations** — étendre `tools/fuzz_images.py` à UNSHRINK, BINARY2,
  IMGFS, DOS33 et aux autres décodeurs ; enrichir les corpus ; intégrer la
  campagne à la CI. Sept décodeurs d’images sont déjà couverts.
- [ ] **Images XL** — porter la session complète `bench/run.py` sur les
  éditions 6502 et 65C02.
- [ ] **Banc //c** — compléter session, pile et disquette ; vérifier la
  souris sur les configurations équipées. Le fonctionnement de base sur //c
  et les deux IIe est acquis, sans valoir chaque révision future.
- [ ] **💾 Matériel** — premier boot IIgs (SmartPort, `$C000`) ; documenter
  les lecteurs Disk II. Les retours //c / IIe ne qualifient pas le IIgs.

## 8. 💾 NIBCOPY : fer d’abord, un gain ensuite

La copie 16 secteurs standard existe. Les bancs POM2 ne valent pas lecteurs
physiques ni accélérateurs. Ne pas assimiler la copie actuelle à une
préservation flux des protections.

- [x] **NIBCOPY 5¼** — un ou deux lecteurs Disk II, 35 pistes à 16 secteurs
  standard ; champs nibble et ordre conservés, synchronisation régénérée,
  double lecture source, vérification et rapport. Cœur en RAM après retrait
  de BOOT ; source obligatoirement protégée, consentement AUX préalable et
  confirmation de chaque échange cible.
- [ ] **Qualification matérielle** — IIe et //c, un et deux lecteurs,
  300 tr/min et accélérateur ; rapport d’échec honnête. Avant tout nouveau
  format.
- [ ] **Un seul gain** — reprise sur la piste courante, **ou** images `.NIB`
  lues/écrites sur le même transport, validées piste par piste. Pas les
  deux d’un coup. Pas de 3½ tant que le 5¼ standard n’est pas mesuré sur
  fer.

## 9. 💾 ADTPro : un parcours blocs

Trou pratique après NIBCOPY : faire entrer/sortir une image. Un client qui
écrit mal une image est pire que l’absence de client ; dépend de 1–3.

- [ ] **Client blocs** — serveur réel, navigation dans les dossiers,
  envoi/réception d’images, CRC et reprise sur NAK.
- [ ] **Mode nibble** — seulement après le parcours blocs et après le gain
  du chantier 8.

## 10. LAUNCHER : A2FC comme hub

GOTO a les dossiers favoris. Il manque les programmes et un retour
automatique fiable. Un lanceur qui écrase la config ou le préfixe casse la
session : pas avant 1–4.

- [ ] **Favoris de programmes et retour à A2FC.**
  À isoler dans POM2 //e non amélioré : le scénario `bench/extras.py` lance
  bien Applesoft depuis DEVTOOLS, mais après `HOME` le relancement manuel
  `-/A2FC6502/A2FILE.SYSTEM` produit parfois `SYNTAX ERROR`. Le scénario
  sans `HOME` a passé ; ni l’attente de l’invite, ni `CALL 976`, ni un essai
  de passage en 40 colonnes n’ont fiabilisé le cas d’origine. Le changement
  de mode vidéo a été retiré. Le banc complet n’est donc pas validé.

## Déjà livré hors contrat ouvert

Retiré des tâches ouvertes, ou coché plus haut :

- 0.8.0 : sauvegarde sûre des préférences, MOVE des fichiers marqués, menu
  par catégories, questions inversées, ouverture automatique des images,
  feuilletage Extasie et autres médias, retour au dossier quitté, lecteurs
  MB1 et PT3 au premier plan. Qualification et CI de cette révision :
  [changelog](CHANGELOG.md), [BUG-HUNT-0.8.0.md](docs/BUG-HUNT-0.8.0.md).
- Après 0.8.0 : réserve mémoire et affichage compact ; routage média ;
  NIBCOPY 5¼ standard ; PT3 jusqu’à 65 535 octets, tables historiques,
  TurboSound, cache prioritaire ; Purplesoft `.FOTO1`/`.FOTO2`.

- [x] **Réserve mémoire** — budgets par zone, réserves affichées à chaque
  lien, premiers objectifs atteints sans relever les plafonds
  ([MEMORY-BUDGETS.md](docs/MEMORY-BUDGETS.md)).
- [x] **Routage média compact** — table de noms commune et identifiants
  internes ; erreurs de sonde, paires Purplesoft et consentement par
  session vérifiés sur les deux architectures.
- [x] **PT3 : grands modules** — 65 535 octets, cache en mémoire principale,
  source en lecture seule, `/RAM` préservée.
- [x] **PT3 : tables de fréquences** — quatre tables, 96 notes, deux CPU.
- [x] **TurboSound** — conteneur `02TS`, deux AY, pause/navigation/fin
  indépendantes ; AUX préservée.
- [x] **Cache PT3** — 156 → 105 défauts, 9,15 → 8,20 s sur le banc
  TurboSound IIe enhanced à 1 MHz. La cadence sous forte pression reste une
  limite, sans emprunt AUX.
- [x] **Purplesoft** — paires GRLOAD, mode EVE, flèches sans doublon ni
  nouveau consentement AUX, retour Échap.

## Plus tard

Pas avant la clôture de 1–4. Ensuite, seulement si le chantier 5 est clos
ou si 8/9/10 n’est pas déjà ouvert. Ce n’est pas une file d’attente à
entamer en parallèle.

### Médias

La cadence PT3 sous cache, les effets multiples et les variantes
multi-puces restent des limites honnêtes ; ne pas les masquer.

- [ ] **PT3 : compatibilité restante** — effets multiples par ligne, autres
  variantes multi-puces, cadence à 1 MHz sous forte pression du cache.
- [ ] **a2dgrx** — bitmaps et fontes au-delà des pixmaps DGRVIEW. Sans
  en-tête ni dimensions : définir les paramètres d’ouverture. Fonte de
  référence : 288 octets.
- [ ] **Purplesoft Pascal GLOAD** — format mono-fichier de 16 Ko ; les
  paires DOS GRLOAD sont prises en charge.
- [ ] **FANTAVISION Apple II** — objets, images-clés, interpolation,
  écrans, sons et polices. Ne pas confondre 8 bits, IIgs et Amiga
  (`FANT`/IFF).
- [ ] **ANIMATE / MOVIE MAKER** — échantillons, personnages, fonds, scènes ;
  commencer image par image.
- [ ] **Autres images** — MACPAINT, BMP, GIF, SHAPES, SLIDESHOW, SHR (IIgs).
- [ ] **Autres sons** — DUET et SAMPLE.
- [ ] **Reconnaissance des fichiers** — aiguillage par type, aux-type,
  suffixe et en-tête au-delà des images.
- [ ] **Documents** — ADB, ASP, AWRITER, CALC ; TOKENIZE pour Applesoft.
- [ ] **Corpus** — image disque, catalogue, type/aux-type, taille, signature
  et capture pour chaque format. Identifier le `$D5` restant dans
  `GISTDATA/SAMPLE.MEDIA`. Ne pas présumer la compatibilité Amiga ou IIgs
  avec l’Apple II 8 bits.

Corpus de référence : `~/src/pom2/hdv/GISTDATA.hdv`, lecture seule. Inventaire :
[SAMPLE-MEDIA.md](docs/SAMPLE-MEDIA.md). APPLEVISION (5 964 octets) est déjà
lisible par INTBASIC.

Références : [a2dgrx](https://github.com/iolo/a2dgrx),
[manuel EVE/Purplesoft](https://mirrors.apple2.org.za/ftp.apple.asimov.net/documentation/hardware/video/lechatmauve_eve_manuel_ocr.pdf),
[manuel Fantavision](https://mirrors.apple2.org.za/ftp.apple.asimov.net/documentation/applications/misc/Fantavision-Manual.pdf)
et [images](https://mirrors.apple2.org.za/ftp.apple.asimov.net/images/productivity/graphics/fantavision),
[manuel Animate](https://www.cvxmelody.net/Animate%20manual%20for%20Apple%20II%20%281986%20Broderbund%29.pdf),
[manuel Extasie](https://mirrors.apple2.org.za/ftp.apple.asimov.net/documentation/non_english/french/crealude_extasie_manuel_ocr.pdf),
[notes Chat Mauve/POM2](https://github.com/habib256/pom2/blob/main/docs/chatmauve_plan.md),
disques `Extasie disk1.dsk` / `Extasie disk2.dsk` du corpus POM2.

### Écritures et disques

- [ ] **Reprise après coupure** — **étudier** une sauvegarde persistante ou
  un journal pour MOVE et BOOTBLK. La restauration sur erreur signalée
  existe. Ne jamais promettre une atomicité que ProDOS ne fournit pas.
- [ ] **DISKIMG : reprise** — nouvelles tentatives après erreur et reprise
  après interruption ; garder la validation des sources et le refus
  d’auto-écrasement.
- [ ] **💾 VERIFY CERTIFY** — motif écrit puis relu après ERASE ;
  confirmation et rapport des blocs défectueux.
- [ ] **💾 DIRSORT** — tri physique d’un dossier ProDOS, sauvegarde des
  blocs, conservation des liens, vérification. Après FIXIT.
- [ ] **💾 Transport nibble 3½** — possibilités du matériel et du
  contrôleur d’abord ; transport distinct des timings Disk II 5¼.
- [ ] **💾 DRIVESPD** — tour Disk II, RPM et durée.
- [ ] **BACKUP** — volume sur disquettes numérotées. Après les services
  sûrs (1).
- [ ] **DOS33W / DOS33FMT** — écriture ProDOS vers DOS 3.3 et formatage
  16 secteurs.
- [ ] **PASCALFS / CPMFS** — Apple Pascal et CP/M.
- [ ] **Écriture dans les images** — modifier une image ouverte comme
  dossier. Après 1 et 5.
- [ ] **Défragmentation** — après FIXIT et VERIFY.
- [ ] **Archives SHRINK** — créer l’archive inverse. Après 1 ; écriture
  lourde, pas un visualiseur.

### Transferts secondaires

- [ ] **TERM / XMODEM** — terminal et transferts série.
- [ ] **SPLIT** — découpage et réassemblage.
- [ ] **VDrive** — Uthernet II ; Super Serial Card réelle et //c. Après
  ADTPro blocs si 9 est choisi.
- [ ] **TFTP / NTP** — réseau et horloge.

### Confort et documentation

- [ ] **DATE** — dates de création et de volume ; horloge de session.
- [ ] **TAGPAT** — plages de dates et confirmation fichier par fichier
  à la copie ou à la suppression.
- [ ] **Confort** — PASSWORD, LCASE, PLGINFO, PRINT, SETUP, SYSINFO.
- [ ] **Manuel et crédits** — liens du manuel et génération du PDF.
- [ ] **Langue des outils** — outils et bancs Python en anglais ; conserver
  le TODO en français.

## Règles communes

La préservation des données prime : [AGENTS.md](AGENTS.md),
[DATA-SAFETY.md](docs/DATA-SAFETY.md). Toute destruction du contenu de
`/RAM` exige un avertissement et une confirmation **avant** le premier
accès destructif.

Pour chaque modification native :

- Identifier fichiers, volumes, buffers et banques pouvant être écrits.
- Ajouter les régressions pertinentes et contrôler les octets conservés
  lors des pannes ; supports jetables uniquement pour les essais
  destructifs.
- Valider les deux architectures, la pile, le BSS et toutes les surcouches.
  Petite fenêtre : 1 280 octets ; les grandes ont leurs propres limites.
- Mesurer les disquettes (280 blocs) et classer tout nouveau plugin dans
  [config/packages.mk](config/packages.mk), sans assouplir les contrôles
  mémoire.

Pour terminer un chantier : retirer sa tâche ouverte, actualiser manuel et
changelog, puis exécuter les tests adaptés. Avant livraison : `make test`,
construction des sept supports, `tools/check_images.py` et échanges de
catégories avec `bench/extras.py`. Associer révision, version, empreintes,
outils et résultats. Committer sur une branche, fusionner dans `main`,
pousser et vérifier la CI, y compris POM2 lorsque l’exécuteur est
configuré. Distinguer essais locaux, émulateur, CI et matériel.

Une coupure pendant une écriture physique peut encore laisser deux entrées
sur les mêmes blocs. La restauration traite les erreurs **signalées**, pas
la perte d’alimentation.
