/* Foreground media coordination. MAIN only; directory/file probes are read-only.
 * AUX consent lasts only for the current overlay_run browsing session. */
#include "viewer_ids.h"
static unsigned char media_request;
static unsigned char media_kind;      /* the media overlay running, or 0 */
static unsigned int media_first[2];
static unsigned char file_viewer(const struct Entry*, unsigned char);

static unsigned char media_type(const char* name)
{
    unsigned char i=MEDIA_COUNT;
    do { if (!strcmp(name,media_names[i])) return i; } while (--i);
    return 0;
}

static unsigned char media_prepare(unsigned char kind)
{
    struct Panel* pan=&panels[active];
    unsigned int first=pan->first;
    unsigned char cursor=pan->cursor, top=pan->top, dir, i, changed=0;
    unsigned char viewer, ok=1;
    const struct Entry* e;
    album[0][0]=album[1][0]=0;
    media_request=0;
    /* overlay_run calls us only for a recognized media ID. */
    if (pan->fs || !pan->path[0]) return 1;
    if (!pan->count || !overlay("OPEN")) return 0;
    keep_tags(1);
    if(kind==V_PURPLE) {
        strcpy(selected.name,pan->e[cursor].name);
        selected.name[strlen(selected.name)-1]='1';
    }
    /* A failed read in another window still goes through the restore below:
     * returning from there would leave the panel on that window, the cursor
     * on another file and the marks forgotten. */
    for(dir=0;dir<2 && ok;++dir) {
        i=cursor;
        for(;;) {
            if (dir) {
                if (++i>=pan->count) {
                    if (!pan->more || pan->first>65535U-WINDOW) break;
                    pan->first+=WINDOW; changed=1;
                    if (!read_panel(active)) { ok=0; break; }
                    if (!pan->count) break;
                    i=0;
                }
            } else {
                if (!i) {
                    if (!pan->first) break;
                    pan->first-=WINDOW; changed=1;
                    if (!read_panel(active)) { ok=0; break; }
                    if (!pan->count) break;
                    i=pan->count;
                }
                --i;
            }
            e=&pan->e[i];
            if (is_dir(e)) continue;
            if (!build_full(full,pan,e)) break;
            viewer=file_viewer(e,kind<4?kind+1:0);
            if (!viewer) break; /* An I/O error is not evidence of another type. */
            if (viewer==kind) {
                if (kind==V_PURPLE && (e->name[strlen(e->name)-1]=='2' || !strcmp(e->name,selected.name))) continue;
                strcpy(album[dir],e->name);media_first[dir]=pan->first;break;
            }
        }
        if (changed) {
            pan->first=first;
            /* A panel fallen back to the volume list gets no marks back. */
            if (!pan->path[0] || !read_panel(active) || pan->first!=first || cursor>=pan->count) return 0;
            keep_tags(0);
        }
        pan->cursor=cursor;pan->top=top;
    }
    return ok;
}

/* The screen a picture is loaded behind: the name being read and nothing
 * else. The panels are never part of it -- neither between two images of
 * an album nor while the first one is decoding, which is the same wait
 * seen from the same place. In MAIN, not in the language card below: the
 * card had the smaller reserve of the two, and both callers reach here. */
static void loading_screen(const char* name)
{
    prepare_text();clrscr();cputs("Loading ");cputs(name);
}

#pragma code-name(push, "LC")
static void media_loading(unsigned char dir)
{
    /* Entry tables are still covered by the running viewer. Only text RAM
     * may be prepared before its cleanup can reveal the loading screen.
     * A lo-res picture lives in that very RAM: it stays on the air until
     * its neighbour is drawn over it (overlay_run keeps graphics on). */
    if(media_kind==V_DGR)return;
    loading_screen(album[dir]);
}
static unsigned char media_key(unsigned char key)
{
    /* cc65 marks Open-Apple/PB0 with bit 7, including Escape. */
    key &= 127;
    if(key==KEY_ESC)return 1;
    if((key==KEY_LEFT || key==KEY_RIGHT) && album[key==KEY_RIGHT][0]) {
        media_request=key;
        media_loading(key==KEY_RIGHT);
        return 1;
    }
    return 0;
}
static char media_wait(void)
{
    char key;
    do key=cgetc(); while(!media_key(key));
    return key;
}

#pragma code-name(pop)

/* Header fields are fixed-width, never C strings. No module or AUX writes. */
static void media_credit(const unsigned char* p, const char* fallback)
{
    unsigned char i,n=32;
    while(n && (p[n-1]<=32 || p[n-1]>=127))--n;
    for(i=0;i<n && (p[i]<=32 || p[i]>=127);++i){}
    if(i==n){cputs(fallback);return;}
    for(;i<n;++i)cputc(p[i]>=32 && p[i]<127?p[i]:' ');
}
static void music_info(const unsigned char* header)
{
    clrscr();cputs("ProTracker 3 - ");cputs(selected.name);
    cputs("\r\nTitle: ");media_credit(header+30,selected.name);
    cputs("\r\nArtist / module credit: ");media_credit(header+66,"Not specified");
    cputs("\r\nPlayer: Vince Weaver - A2FC adapter\r\n\r\nLeft/Right Track  P Pause/resume  ESC Back");
}
