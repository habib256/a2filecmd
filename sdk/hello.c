/* hello.c -- une surcouche d'exemple pour A2 File Cmd, compilée HORS de
 * l'arbre du programme, pour prouver que l'ABI (struct A2fcApi) tient et
 * servir de modèle à un tiers.
 *
 * Elle ne connaît RIEN d'A2 File Cmd que src/a2fc_plugin.h : pas une seule
 * adresse du programme, aucune fonction de lui liée. Tout passe par la table
 * de services que le noyau donne à son point d'entrée. On la lance par la
 * touche `!` (le menu des surcouches), sur l'entrée sous le curseur.
 *
 * Ce qu'elle fait : lire l'entrée sélectionnée dans le panneau actif et en
 * afficher le nom, le type et le chemin en ligne de message -- juste assez
 * d'appels (message, sprintf, la lecture de panels/active/selected) pour
 * montrer les deux sens de l'échange. Voir sdk/README.md et sdk/build.sh.
 *
 * Compilé avec la cible apple2enh, comme A2FC ; SANS --all-cdecl (cprintf et
 * sprintf sont variadiques cdecl, tout le reste fastcall). */

#include "../src/a2fc_plugin.h"

/* Le point d'entrée : le noyau l'appelle avec la table de services. */
void __fastcall__ plugin_entry(const struct A2fcApi* api);

/* L'en-tête struct Overlay, EN TÊTE de la surcouche ($1B00). La signature
 * PLUGIN_MAGIC dit « surcouche d'un tiers » ; le noyau la reconnaît et
 * n'appelle rien d'autre que par la table. `desc` s'affiche dans le menu. */
struct PluginHeader {
    unsigned int signature;
    unsigned char flags;
    void __fastcall__ (*entry)(const struct A2fcApi*);
    unsigned char r0, r1, r2;
    char desc[52];      /* le menu en lit 51 au plus */
};

#pragma rodata-name (push, "OVLHDR")
const struct PluginHeader __plugin_header = {
    PLUGIN_MAGIC,
    0,                       /* petite surcouche ; OVERLAY_BIG pour $2000-$3FFF */
    plugin_entry,
    0, 0, 0,
    "Example third-party plugin: names the file"
};
#pragma rodata-name (pop)

void __fastcall__ plugin_entry(const struct A2fcApi* api)
{
    const struct Panel* pan = &api->panels[*api->active];
    char* buf = (char*)api->copy_buf;          /* 512 octets de travail prêtés */

    if (api->selected->name[0])
        api->sprintf(buf, "Plugin: \"%s\", type $%02X, in %s",
                     api->selected->name,
                     (unsigned)api->selected->type,
                     pan->path[0] ? pan->path : "the volume list");
    else
        api->sprintf(buf, "Plugin: nothing selected, in %s",
                     pan->path[0] ? pan->path : "the volume list");

    api->message(buf);       /* ligne 22 ; la table a fait tout le travail */
}
