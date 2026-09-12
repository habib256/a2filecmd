# Prise en charge de SAMPLE.MEDIA

Le corpus `/GISTDATA/SAMPLE.MEDIA` contient 52 polices MGTK, DIP.CHIPS
(FOT LZ4FH), BBROS.MINI (Print Shop) et deux programmes Integer BASIC.
Entrée sélectionne leurs lecteurs ; I sélectionne aussi les trois lecteurs
visuels. Les originaux du corpus restent en lecture seule pendant les essais.

Les trois nouvelles surcouches écrivent uniquement la page HGR principale
`$2000–$3FFF` et le tampon partagé de 512 octets. Leur code et leur BSS sont
bornés par l'éditeur de liens à `$1B00–$1FFF`, sur les deux processeurs.
Elles n'écrivent aucun fichier et ne détruisent pas le disque ProDOS RAM.
Les erreurs de lecture et de fermeture empêchent l'affichage du résultat.

Références utilisées pour une implémentation propre aux contraintes d'A2FC :

- [LZ4FH dans CiderPress II](https://github.com/fadden/CiderPress2/blob/main/FileConv/Gfx/HiRes_LZ4FH.cs) : offsets absolus dans la sortie, extension de longueur sur un octet, marqueurs 253 et 254.
- [Print Shop, notes CiderPress II](https://github.com/fadden/CiderPress2/blob/main/FileConv/Gfx/PrintShop-notes.md) : bitmap monochrome 88 × 52, bit de poids fort à gauche, agrandissement 2 × 3.
- [Lecture des polices MGTK dans Apple II Desktop](https://github.com/a2stuff/a2d/blob/main/bin/dump_font.pl) : en-tête de trois octets, largeurs puis plans rangés par ligne, colonne de sept pixels et caractère.

`tools/test_sample_media.py` exécute les entrées C avec des données valides,
tronquées et malformées ainsi que des erreurs d'ouverture, lecture et fermeture.
Ses rendus hôtes servent de référence ; `bench/sample_media.py` contrôle aussi
les vrais rendus assembleur dans POM2, pour chaque fichier du corpus.
La validation matérielle signalée avant ces ajouts ne les couvre pas encore.

PT3 est disponible pour `AUTUMN.PT3` (restauré dans `/SAMPLE.MEDIA`) et pour
le corpus ZX Spectrum dans [`media/pt3/MUSIC/`](../media/pt3/MUSIC/) : trois
voix Mockingboard, lecture au premier plan, pause/reprise et arrêt à la fin
du morceau ou par Escape. Le module et les tables restent en mémoire
principale. La détection matérielle n'installe pas le lecteur AUX de MB1.
Les limites de taille et de commandes du lecteur sont détaillées dans le
manuel et dans [`pt3lib/README.md`](../src/plugins/pt3lib/README.md).
Le volume ProDOS `media/pt3/A2FC-PT3.po` garde les huit fichiers de départ
sous des noms de 15 caractères, type `$00`. Entrée sur un `.PT3` ouvre le
lecteur s'il tient dans 65 535 octets et passe les contrôles d'en-tête.

## Validation du 12 septembre 2026

- Compilations 6502 et 65C02 : contrôles de disposition mémoire conservés.
- Suite hôte complète : 351 tests réussis.
- Sept images de distribution relues : catalogues et surcouches conformes.
- Corpus visuel : 114/114 contrôles POM2 sur chacun des deux processeurs,
  dont les pages HGR complètes des 52 polices et la préservation d'AUX.
- PT3 : lecture complète d'AUTUMN.PT3, contrôle des registres AY, pause/reprise,
  silence et désactivation des interruptions VIA à la sortie, refus des
  pointeurs invalides/boucles/effets multiples, puis lecture MB1 conservée.
  Le //c émulé sans Mockingboard refuse clairement la lecture.

## Modules PT3 ZX Spectrum (12 septembre 2026)

Le corpus ProTracker 3 / Vortex Tracker, trois voix AY, a été téléchargé
depuis ZX-Art (9 644 fiches PT3) et des archives auteurs zxtunes, puis
filtré avec le même contrôle que le chargeur A2FC (`valid()` dans
`src/plugins/pt3.c`) : taille ≤ 4 608 octets (ancien plafond, corpus non régénéré), signature `ProTracker 3.`
ou `Vortex Tracker`, tables 0–3 (table 1 seule pour les modules antérieurs
à 3.4), pointeurs d'ordre et d'échantillons présents, pas d'effets
différés multiples sur une même note. **5 507** modules distincts restent,
rangés par artiste (noms ProDOS, 15 caractères) :

- hôte : [`media/pt3/MUSIC/<ARTISTE>/`](../media/pt3/MUSIC/)
- volume : `/GISTDATA/MUSIC/<ARTISTE>/` (449 dossiers)
- index des sources : [`media/pt3/MUSIC/SOURCES.TXT`](../media/pt3/MUSIC/SOURCES.TXT)

`AUTUMN.PT3` (4 461 octets, table ST) est de nouveau dans
`/SAMPLE.MEDIA` ; le même fichier se trouve aussi sous `KENOTRON`
(`KENOTRONAUT.PT3`, AuTumn'99). Les neuf `.PT3` déjà présents à la racine
de `/MUSIC` n'ont pas été remplacés. Les dossiers `IMG`, `APPS`, `CODE`
et le reste de `SAMPLE.MEDIA` n'ont pas été touchés.

Huit modules de départ restent aussi à la racine de
[`media/pt3/`](../media/pt3/) et sur `/A2FCPT3` (`A2FC-PT3.po`) :

| Fichier | Auteur | Module | Octets |
|---|---|---|---|
| `ABSTRACT.PT3` | Ra | ABSTRACT (1999) | 3 284 |
| `ANA.NG.PT3` | reprise dos33fsprogs | ana_ng | 2 053 |
| `DH2020RT.PT3` | EA | dh2020rt (2020) | 1 454 |
| `MA2E.3.PT3` | mA2E | mA2E_3 | 1 475 |
| `MUSIC.VAD.PT3` | VAD | Music (2002) | 4 501 |
| `OLDSKOOL.PT3` | EA | Old Skool For Demodulation (2020) | 3 195 |
| `REALTIME.PT3` | EA | realtime blast (2026) | 2 877 |
| `YAZZIE.PT3` | nq | Yazzie: final theme (2019) | 2 057 |

Artistes les plus représentés dans `/MUSIC` : nq (227), MmcM (207),
luchibobra (206), C-Echo (185), riskej (183), Macros (128), S.A.V (127),
EA (124), C-Jeff (122).

Pages et téléchargements d'origine :

- [ABSTRACT, Ra, ZX-Art](https://zxart.ee/tune/77827) · [fichier PT3](https://zxart.ee/file/id:77827/)
- [ana_ng.pt3, dos33fsprogs](https://github.com/deater/dos33fsprogs/blob/master/graphics/dgr/animations/tmbg/music/ana_ng.pt3) · [brut](https://raw.githubusercontent.com/deater/dos33fsprogs/master/graphics/dgr/animations/tmbg/music/ana_ng.pt3)
- [dh2020rt, EA, ZX-Art](https://zxart.ee/tune/325794) · [fichier PT3](https://zxart.ee/file/id:325794/)
- [mA2E_3.pt3, dos33fsprogs](https://github.com/deater/dos33fsprogs/blob/master/graphics/gr/animations/grongy_roads/music/mA2E_3.pt3) · [brut](https://raw.githubusercontent.com/deater/dos33fsprogs/master/graphics/gr/animations/grongy_roads/music/mA2E_3.pt3)
- [Music, VAD, ZX-Art](https://zxart.ee/tune/82459) · [fichier PT3](https://zxart.ee/file/id:82459/)
- [Old Skool For Demodulation, EA, ZX-Art](https://zxart.ee/tune/357249) · [fichier PT3](https://zxart.ee/file/id:357249/)
- [realtime blast, EA, ZX-Art](https://zxart.ee/tune/588679) · [fichier PT3](https://zxart.ee/file/id:588679/)
- [Yazzie: final theme, nq, ZX-Art](https://zxart.ee/eng/authors/n/nq/yazzie-final-theme/) · [fichier PT3](https://zxart.ee/file/id:325585/)
- [Vortex Tracker II (format PT3)](https://bulba.untergrund.net/vortex_e.htm)
- [ZX-Art, catalogue AY / PT3](https://zxart.ee/)
- [ZX-Art, API PT3](https://zxart.ee/api/types:zxMusic/export:zxMusic/language:eng/start:0/limit:1/filter:zxMusicFormat=PT3;)
- [zxtunes.com, liste d'auteurs](https://zxtunes.com/authors_list.php?letter=A&lm=200&ln=eng)
- [zxtunes.com, archive Macros](https://zxtunes.com/en/authors/macros)
- [zxtunes.com, archive Korund](https://zxtunes.com/en/authors/korund)
- [pt3_lib Apple II, Vince Weaver](https://github.com/deater/dos33fsprogs/tree/master/music/pt3_lib)
