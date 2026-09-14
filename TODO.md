# A2 File Cmd — feuille de route

La [0.8.5](https://github.com/habib256/a2filecmd/releases/tag/v0.8.5) est
publiée ([qualification](docs/history/RELEASE-0.8.5.md),
[CHANGELOG](CHANGELOG.md), [index](docs/README.md)). Deux produits, un
numéro : **Mini** (II+ 48 Ko, DOS 3.3) et **A2FC ProDOS** (IIe 128 Ko).
`make mini` ne partage pas `src/a2fc.c`.

Préserver les données prime. Ne pas relever les plafonds mémoire
([MEMORY-BUDGETS.md](docs/MEMORY-BUDGETS.md)) ; viser au moins 256 octets
libres dans MAIN 65C02. Les travaux sur lecteurs physiques portent **💾**.

## Priorité

**2 → 4**, avec un budget mesuré à chaque lien. **6** seulement si une
petite surcouche doit changer. **1** et **3** en rendement décroissant,
**7** en continu. Puis **5**. Ensuite **un seul** parmi 8, 9 ou 10.

Mini (**0**) est livrée et indépendante. Ne pas ouvrir SHRINK, l’écriture
dans une image montée, un journal de coupure, Pascal/CP/M ni un nouveau
média tant que 1–4 ne sont pas clos.

## Chantiers

| # | Chantier | État |
| --- | --- | --- |
| **0** | Mini 6502 pur | Livrée en 0.8.5 ; qualification II+ ouverte |
| **1** | Services de fichiers sûrs | En cours : IMGFS/DOS33/DOSGET, NuFX, relectures |
| **2** | Parcours d’arbres itératifs | État borné fait ; relecture d’arbre avec le 4 |
| **3** | Trous de préservation 0.8.x | À faire |
| **4** | MOVE d’arbre entre volumes | Dossiers marqués faits ; curseur seul via V |
| **5** | FIXIT lecture seule | Après 4 |
| **6** | Contrats plugins | Petites surcouches à traiter à la demande |
| **7** | Preuves de séquences | Continu |
| **8** | 💾 NIBCOPY réel, puis un gain | Après 5, au choix |
| **9** | 💾 ADTPro blocs | Après 5, au choix |
| **10** | LAUNCHER | **Clos** : retour épelé et validé ; favoris de programmes en « Plus tard » |

## 0. Mini DOS 3.3

[MINI-DOS33.md](docs/MINI-DOS33.md). Copie 4,4× plus rapide, tags, HGR,
éditeur, TXT, DEL, LOCK, RENAME. Pas de remplacement sur place, de copie
à un seul lecteur ni de formatage.

- [ ] **Changements de lecteur** — encore ~20 par copie ; ne pas emprunter
  les tables de noms des panneaux sans traiter `reload()`.
- [ ] **Relecture groupée** — gagner ~7 s, ou laisser : trancher et
  documenter.
- [ ] **💾 II+ physique** — les bancs POM2 ne remplacent pas le fer.

## 1. Services de fichiers sûrs

Journal : [FILE-SERVICES.md](docs/FILE-SERVICES.md). Extraire sans
grossir `src/a2fc.c`.

- [ ] **Contrat unique** — création exclusive, original récupérable jusqu’aux
  contrôles, nettoyage limité aux fichiers créés, collisions refusées.
- [ ] **Découpage du résident** — extraire des modules de `src/a2fc.c` sans
  l’augmenter ; une surcouche de service ne doit pas écraser l’appelant.
- [ ] **Reste ouvert** — nettoyages IMGFS/DOS33/DOSGET, CRC et métadonnées
  NuFX, relecture des extraits.

## 2. Parcours d’arbres itératifs

`walk_tree` (`src/tree_walk.h`) remplace la récursion. Sans ça : pas de
MOVE d’arbre, DELETE enrichi ni SYNC plus profond.

- [ ] **Relecture d’arbre avant suppression de source** — avec le chantier 4.
- [ ] **Très grands répertoires** — étendre les scénarios restants.

## 3. Trous de préservation

Dette 0.8.x : [DATA-SAFETY.md](docs/DATA-SAFETY.md). Une erreur de lecture,
métadonnées ou fermeture n’est ni une EOF ni un chemin libre.

- [ ] **Conversions** — comparer le résultat relu, pas seulement les
  écritures.
- [ ] **Pannes combinées** — fermeture + collision + annulation ; taille
  périmée ; échecs de renommage, restauration et nettoyage.
- [ ] **Autres chemins** — avant suppression ou remplacement, y compris
  restauration.

## 4. MOVE d’arbre entre volumes

Dossiers marqués : copie relue, source intacte si le lot s’arrête. Même
volume = réécriture d’entrée.

- [ ] **Dossier sous le curseur, autre volume** — le menu MOVE renvoie
  encore vers V ; le marquer suffit.

## 5. FIXIT : plan, zéro écriture

VOLINFO scanne. D’abord un plan choisi par l’utilisateur ; les
corrections viennent après.

- [ ] **Diagnostic** — allocation, références, pointeurs, compteurs, blocs
  perdus ; signaler sans modifier.
- [ ] **Corrections** — après le plan : conserver l’original, confirmer,
  vérifier chaque écriture.

## 6. Plugins et petites surcouches

DELETE, COPY, IMGFS et ATTR n’ont plus de marge. Extraire un service
partagé dans le résident seulement le jour où l’une d’elles change.

- [ ] **Contrats** — buffers, AUX, restauration, erreurs ; uniformiser
  ouverture et sortie des visualiseurs.
- [ ] **Respiration** — viser de la marge dans chaque petite surcouche
  **modifiée**. OPEN ne doit pas retomber à quelques octets.

## 7. Preuves de séquences (continu)

Vérifier états, ressources et octets, pas seulement le code de retour.

- [ ] **Séquences** — image → musique → copie ; annulation → reprise ;
  changement de disque.
- [ ] **`bench/goto.py`** — écarter GOTO.TMP entre deux échecs de
  renommage ; relire les autres bancs de `bench/plugins.py`.
- [ ] **Mutations** — `tools/fuzz_images.py` : UNSHRINK, BINARY2, IMGFS,
  DOS33 ; intégrer à la CI.
- [ ] **Images XL** — `bench/run.py` sur 6502 et 65C02.
- [ ] **Banc //c** — session, pile, disquette, souris.
- [ ] **💾 IIgs** — premier boot (SmartPort, `$C000`) ; documenter Disk II.

Le banc de session tape la commande de retour que RUN épelle et exige
A2FC de retour sur ses panneaux (14 septembre 2026) : verdict entier.

## 8. 💾 NIBCOPY

Copie 5¼ 16 secteurs standard faite. Les bancs POM2 ne valent pas le fer.

- [ ] **Qualification** — IIe et //c, un et deux lecteurs, 300 tr/min et
  accélérateur.
- [ ] **Un seul gain** — reprise de piste **ou** images `.NIB`. Pas les
  deux. Pas de 3½ avant le 5¼ mesuré sur fer.

## 9. 💾 ADTPro

Dépend de 1–3. Le nibble après le 8.

- [ ] **Client blocs** — dossiers, envoi/réception, CRC, NAK.
- [ ] **Mode nibble** — après le parcours blocs et le gain du 8.

## 10. LAUNCHER

GOTO a les dossiers ; il manque les programmes.

- [x] **Retour fiable à A2FC** (14 septembre 2026) — le défaut de la
  session était une consigne fausse, pas le lanceur : depuis la 0.8.0 RUN
  pose le préfixe sur le dossier du programme (ses fichiers de données),
  donc le `-A2FILE.SYSTEM` nu promis par le HELLO de démonstration donnait
  `PATH NOT FOUND`. La confirmation de RUN épelle la commande absolue
  (`Back: -/VOL/A2FILE.SYSTEM`), le HELLO renvoie vers `BYE` et le
  sélecteur ProDOS 2.4.3, le banc de session tape la commande lue à
  l’écran : 3/3 retours en 2,9 s, scénario réintégré. Un retour
  *automatique* n’existe pas avec BASIC.SYSTEM (fin de programme = invite
  `]`) ; INTBASIC.SYSTEM revient déjà au sélecteur.
- [x] **`SYNTAX ERROR` après `HOME` sur //e non amélioré** — signalé sur
  `bench/extras.py` ; non reproduit le 14 septembre 2026 (3/3, retour par
  le chemin absolu après `HOME`, puis session complète 73/73). Clos.

**Chantier clos le 14 septembre 2026.** Les favoris de programmes passent
dans « Plus tard » : une liste comme GOTO pour les dossiers, sans écraser la
configuration ni le préfixe, quand le besoin se présente.

## Plus tard

Pas avant la clôture de 1–4, et seulement si 5 est clos ou si 8/9/10
n’est pas déjà ouvert.

**Favoris de programmes** — une liste de programmes à lancer, comme GOTO
pour les dossiers, sans écraser la configuration ni le préfixe.

**Médias** — cadence PT3 à 1 MHz, effets multiples, autres puces AY ;
a2dgrx ; Purplesoft GLOAD 16 Ko ; Fantavision ; ANIMATE ; MACPAINT / BMP /
GIF / SHAPES / SLIDESHOW / SHR ; DUET / SAMPLE ; reconnaissance élargie ;
ADB / ASP / AWRITER / CALC / TOKENIZE ; corpus (dont le `$D5` de
`SAMPLE.MEDIA`). Référence : `~/src/pom2/hdv/GISTDATA.hdv`,
[SAMPLE-MEDIA.md](docs/SAMPLE-MEDIA.md).

**Disques** — journal de coupure (étudier, ne pas promettre l’atomicité) ;
reprise DISKIMG ; 💾 VERIFY CERTIFY ; 💾 DIRSORT (après FIXIT) ; 💾 nibble
3½ ; 💾 DRIVESPD ; BACKUP ; DOS33W / DOS33FMT ; PASCALFS / CPMFS ; écriture
dans une image ouverte ; défragmentation ; archives SHRINK.

**Transferts** — TERM / XMODEM ; SPLIT ; VDrive (après ADTPro si 9) ;
TFTP / NTP.

**Confort** — DATE ; TAGPAT ; PASSWORD, LCASE, PLGINFO, PRINT, SETUP,
SYSINFO ; liens du manuel et PDF ; outils Python en anglais, TODO en
français.

## Livraison

[AGENTS.md](AGENTS.md), [DATA-SAFETY.md](docs/DATA-SAFETY.md). Toute
destruction de `/RAM` : avertir et confirmer **avant**. Essais destructifs
sur supports jetables. Deux CPU, pile, BSS, overlays. Plugins dans
[config/packages.mk](config/packages.mk).

Avant livraison : `make test`, sept supports, `tools/check_images.py`,
échanges de catégories (`bench/extras.py`). Une coupure physique peut
encore laisser deux entrées sur les mêmes blocs ; la restauration traite
les erreurs **signalées**, pas la perte d’alimentation.
