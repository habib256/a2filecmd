# Écrire une surcouche pour A2 File Cmd

Une **surcouche** (plugin) est un fichier `A2FILE/NOM.PLG` qu'A2 File Cmd
charge en `$1B00` à la demande et lance sur l'entrée sous le curseur. Les
commandes du programme en sont (voir `src/overlay.s`), et un tiers peut en
ajouter sans toucher au programme ni le recompiler : sa surcouche paraît dans
le menu des surcouches (touche `!`) et s'exécute sur la sélection.

Une surcouche d'un tiers ne connaît **rien** d'A2 File Cmd que le fichier
[`../src/a2fc_plugin.h`](../src/a2fc_plugin.h) : aucune adresse du programme,
aucune de ses fonctions liée. Tout passe par la **table de services**
(`struct A2fcApi`) que le noyau donne à son point d'entrée. Cette table est
l'ABI stable : ses champs ne changent pas de place, il ne s'en ajoute qu'à la
fin, et `api->version` le dit. C'est ce qui permet à une surcouche compilée
une fois de survivre aux versions suivantes du programme.

## Le modèle : `hello.c`

[`hello.c`](hello.c) est une surcouche complète. Elle a trois parties :

1. **L'en-tête** `struct Overlay` (ici `struct PluginHeader`), rangé dans le
   segment `OVLHDR` pour qu'il soit **en tête** de la surcouche (`$1B00`) :
   - la **signature** `PLUGIN_MAGIC` — le noyau reconnaît ainsi une surcouche
     d'un tiers et refuse un `.PLG` d'une autre construction du programme ;
   - un octet de **drapeaux** — `0` pour une petite surcouche (`$1B00-$1FFF`,
     1 280 octets), `OVERLAY_BIG` pour une grande, qui prend aussi la page
     graphique `$2000-$3FFF` (monter alors `RAM` à `$2500` dans le `.cfg`) ;
   - l'**adresse du point d'entrée** ;
   - trois octets réservés, puis une **description** d'une ligne, affichée
     dans le menu (51 caractères au plus).
2. **Le point d'entrée** `void __fastcall__ plugin_entry(const struct A2fcApi*)`.
   Le noyau l'appelle sur la sélection. `api->panels[*api->active]` est le
   panneau actif, `api->selected` l'entrée sous le curseur (copiée hors des
   tables, `name[0] == 0` si le panneau est vide), `api->full` son chemin
   ProDOS complet, `api->arg` la touche qui a appelé (`0` depuis le menu).
3. **Les appels à la table** : `api->message`, `api->confirm`, `api->prompt`,
   `api->fopen`/`fread`/`fwrite`, `api->dir_open`/`dir_next`, `api->mli`, et
   des fonctions C usuelles (`sprintf`, `memcpy`, `strcpy`...). La liste
   complète est dans `struct A2fcApi`.

## Compiler

    ./build.sh sdk/hello.c HELLO       # -> build/HELLO.PLG

`build.sh` compile le C avec la cible cc65 `apple2enh` (la même qu'A2FC : les
adresses zéro-page et la pile C coïncident), puis lie avec `ld65` sur
[`plugin.cfg`](plugin.cfg) et la bibliothèque `apple2enh` — **sans** crt0 :
une surcouche n'est pas un programme, elle est appelée dans le contexte cc65
qu'A2FC tient déjà. Le résultat est un BIN brut à poser sous
`A2FILE/HELLO.PLG` (type ProDOS `$06`, adresse `$1B00`), à côté d'`A2FILE.CODE`.
Depuis la racine du dépôt, `make example` fait la même chose.

## Les règles à tenir

- **Pas de statique non initialisée qui doit valoir zéro** : rien ne met à
  zéro la fenêtre de surcouche. Pour de l'état, prendre `api->copy_buf` (512
  octets prêtés) ou `api->input`, ou la pile C (variables locales). Une
  statique **initialisée** (`DATA`) est chargée depuis le fichier et convient.
- **Ne pas dépasser la fenêtre** : `$1B00-$1FFF` pour une petite surcouche.
  `ld65` le signale si le code déborde `RAM`.
- **Ne compiler ni avec `--all-cdecl`** : `cprintf` et `sprintf` sont
  variadiques (cdecl), tout le reste de la table est en `fastcall`.
- **Tester** : `python3 bench/plugin.py` construit `hello.c`, le pose sur une
  disquette, l'ouvre par `!` et vérifie qu'il tourne dans POM2.
