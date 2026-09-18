# Fiche de recette : la qualification sur matériel

POM2 prouve le code, le lecteur prouve la machine. `make qualify` joue
quatre-vingt-dix-sept pas dans un émulateur ; cette fiche décrit ce qu'aucun
émulateur ne remplace, dans l'ordre où le TODO les place. Elle est faite pour
être imprimée et cochée à côté de l'Apple II.

Chaque séance suit la même forme : **ce qu'on prépare**, **ce qu'on tape**,
**ce qu'on doit voir**, **ce qu'on note**. Les images d'essai et ce que
chaque contrôle doit afficher viennent des mêmes oracles que les bancs :

```sh
python3 tools/hw_media.py --out dist/hw          # les trois disquettes
python3 tools/hw_media.py --out dist/hw --big    # plus le volume de 20 000 blocs
```

| Image | Ce qu'elle porte |
|---|---|
| `HW-CLEAN.dsk` | volume ProDOS de 280 blocs, sain : FIXIT ne doit rien trouver |
| `HW-BROKEN.dsk` | le même, cassé en quatre endroits que REPAIR sait remettre |
| `HW-DOS33.dsk` | disquette DOS 3.3 : GREETINGS (texte), BINARY, HELLO |
| `HW-BIG.po` | volume de 20 000 blocs cassé au-delà de la première page de bitmap |

`dist/hw/EXPECTED.json` porte, pour chaque image cassée, les constats que
FIXIT doit nommer et leur nombre. **Un écran qui dit autre chose est le
résultat de la séance** : le noter tel quel, c'est ce qu'on est venu
chercher.

Les disquettes se gravent comme d'habitude (ADTPro, Floppy Emu, CFFA…) ;
cette fiche ne prescrit pas le transfert, seulement ce qu'on fait ensuite.

## Avant de commencer

- Les disquettes publiées de la version à qualifier, gravées : `BOOT`,
  `FILES`, `MEDIA`, `DISKTOOLS`, `DEVTOOLS`, et la Mini DOS 3.3.
- **Aucun disque personnel dans un lecteur.** Tout ce que ces séances
  écrivent est jetable ; un disque irremplaçable n'a rien à faire dans la
  machine pendant une recette.
- De quoi noter : la version (`A2 FILE CMD x.y.z` en haut de l'écran), la
  machine, le slot et le lecteur de chaque disque.
- En cas d'écran faux : photographier l'écran **avant** de toucher une
  touche, et garder la disquette telle quelle. Une image relue ensuite sur
  le Mac (`python3 tools/prodos_check.py IMAGE.po`) dit si le disque ou
  l'affichage est en cause.

---

## 1. Mini sur Apple II+ 48 Ko 💾

Un défaut d'écran a déjà été vu sur machine ; les écritures ne sont pas
qualifiées du tout.

**Préparer** : `A2FC-MINI-DOS33-<version>.dsk` et `HW-DOS33.dsk`.

**Taper et voir**

1. Amorcer la Mini. Les deux panneaux s'affichent en 40 colonnes.
   *Noter la page de titre mot pour mot, et tout caractère faux.*
2. Parcourir le catalogue avec les flèches, ouvrir un texte (Retour).
   *Le défilement ne laisse pas de traces : une ligne modifiée n'en
   redessine qu'une.*
3. Mettre `HW-DOS33.dsk` en lecteur 2, `Tab`, lire GREETINGS.
4. **Copie** : marquer GREETINGS, `C` vers le lecteur 1. Attendre la fin,
   puis `Tab` et vérifier que le nom est apparu, à la bonne taille.
5. Retirer la disquette cible, tenter la même copie : le refus doit arriver
   **avant** toute écriture (protection en écriture, disquette absente).
6. `Q` puis relancer A2FC depuis DOS (`BRUN` de son binaire) : les panneaux
   reviennent.

**Noter** : la version affichée, chaque caractère faux, et pour la copie la
taille relue côté Mac après coup.

---

## 2. DOSWRITE sur disque réel 💾

Écrire du ProDOS vers une vraie disquette DOS 3.3, dans un vrai lecteur.

**Préparer** : `FILES` (ou XL) gravée, `HW-DOS33.dsk` gravée, et une
disquette DOS 3.3 **jetable** de plus, formatée.

**Taper et voir**

1. Amorcer A2FC. Panneau gauche : un fichier TXT de la disquette (ou du
   disque dur). Panneau droit : ouvrir la disquette DOS 3.3 (`/` puis le
   lecteur).
2. `C` sur le fichier sélectionné : DOSWRITE annonce le slot et le lecteur
   choisis. *Aucune écriture avant la confirmation.*
3. Confirmer. À la fin, le catalogue DOS montre le nom, avec sa taille en
   secteurs.
4. Recommencer avec le **même nom** : le refus doit être explicite et la
   source intacte.
5. Recommencer sur une disquette **protégée en écriture** : refus avant
   écriture.
6. Relire la disquette sur le Mac et comparer les octets du fichier copié
   avec l'original.

**Noter** : le slot utilisé, le message exact de chaque refus, et le
résultat de la comparaison d'octets.

---

## 3. FIXIT et REPAIR sur une disquette réellement abîmée 💾

**Préparer** : `DISKTOOLS` gravée, `HW-CLEAN.dsk` et `HW-BROKEN.dsk`
gravées, `dist/hw/EXPECTED.json` ouvert à côté.

**Taper et voir**

1. Amorcer A2FC, insérer `HW-CLEAN`. `!` → Disks → **FIXIT**, le volume
   sain. Verdict attendu : aucun constat, `consistent`.
   *Si FIXIT trouve quelque chose sur la disquette saine, c'est la gravure
   ou le lecteur qu'il faut mettre en cause d'abord : relire l'image sur le
   Mac avant de conclure.*
2. Insérer `HW-BROKEN`. **FIXIT** de nouveau : quatre constats, un par
   ligne, avec leur compteur et leur premier bloc —
   `FILE_COUNT`, `DIR_EOF`, `DIR_PARENT`, `BM_LOST`.
   *Les noms et les nombres sont ceux d'`EXPECTED.json`.*
3. `R` : le même parcours rend exactement les mêmes lignes.
4. `!` → Disks → **REPAIR** sur la même disquette. Le plan annonce
   `Plan: 4 corrections over N blocks. Nothing written yet.`
5. `F`, puis taper `FIX` en entier. Résultat attendu :
   `Applied N of N blocks; rescan clean: repaired.`
6. **FIXIT** une troisième fois : plus aucun constat.
7. Relire la disquette sur le Mac : `python3 tools/prodos_check.py` la
   déclare saine, et seuls les blocs que REPAIR a nommés ont changé
   (comparer avec `dist/hw/HW-BROKEN.po`).

**Noter** : les quatre lignes de FIXIT telles qu'elles s'affichent, le
nombre de blocs du plan, et le verdict final.

---

## 4. FIXIT et REPAIR en mémoire auxiliaire, au-delà de 4 096 blocs 💾

C'est le chemin où les réclamations vivent en AUX et où `/RAM` peut être
perdu : il n'a jamais tourné ailleurs que dans l'émulateur.

**Préparer** : `HW-BIG.po` (20 000 blocs) sur un support de masse réel
(CFFA, Floppy Emu, disque SmartPort…), et de quoi vérifier `/RAM` : y
copier **avant** un fichier reconnaissable.

**Taper et voir**

1. Amorcer A2FC sur un IIe 128 Ko. Copier un fichier dans `/RAM`.
2. `!` → Disks → **FIXIT** sur `HWBIG`. La question de profondeur arrive :
   `Q` (rapide, dossiers seulement) puis `F` (complet).
3. La question `/RAM` arrive ensuite : répondre **N** une première fois.
   *Attendu : « Scan cancelled », et le fichier de `/RAM` toujours là.*
4. Recommencer, répondre **Y** : le parcours va jusqu'au bout et nomme
   `FILE_COUNT` et `BM_LOST` (voir `EXPECTED.json`). `/RAM` est alors
   annoncé refait à neuf.
5. **REPAIR** : plan de 2 corrections, `F`, `FIX`, verdict `repaired`.
6. Refaire la même séance sur un **//c**.
7. Relire le volume sur le Mac : sain, et seuls les blocs nommés ont bougé.

**Noter** : le temps qu'a pris le parcours complet, la réponse à chaque
question, l'état de `/RAM` après un refus puis après un accord.

---

## 5. Apple IIgs : premier amorçage 💾

Aucun IIgs n'a encore démarré A2FC.

**Préparer** : la XL `.2mg` sur un support SmartPort, et la disquette BOOT.

**Taper et voir**

1. Amorcer la XL. *Le lanceur refuse une machine qui ne convient pas en 40
   colonnes : s'il refuse ici, noter le message exact, c'est le contrôle de
   machine qu'il faudra revoir.*
2. Panneaux, navigation, `?` (aide), `!` (menu) : les surcouches se
   chargent.
3. Ouvrir une image HGR puis une DHGR, feuilleter avec les flèches.
   *Entre deux images, l'écran ne porte que le nom en cours de chargement.*
4. Amorcer ensuite la disquette BOOT dans un Disk II, s'il y en a un :
   noter ce qui marche et ce qui ne marche pas (le IIgs n'est pas encore
   documenté côté Disk II).
5. `Q` : retour à ProDOS, préfixe conservé.

**Noter** : la vitesse ressentie (le IIgs tourne plus vite), tout écran qui
diffère du IIe, et l'état du Disk II.

---

## Après la séance

- Reporter le résultat dans `TODO.md` : une ligne 💾 ne se coche que si la
  séance est allée jusqu'au bout, pas parce qu'elle a commencé.
- Un défaut trouvé se rejoue d'abord dans POM2 (`bench/all.py --only <banc>`)
  avec la même image : s'il s'y reproduit, il devient un banc ; s'il ne s'y
  reproduit pas, la fiche le dit et la ligne 💾 reste ouverte.
- Les images d'essai de `dist/hw/` sont jetables : les regraver au besoin,
  elles se reconstruisent en une fraction de seconde.
