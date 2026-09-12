/* Foreground media coordination. MAIN only; directory/file probes are read-only.
 * AUX consent lasts only for the current overlay_run browsing session. */
static const char* const media_names[] = {"MUSIC","PT3","EXTASIE","PACKFOT","PAINT816","DGRVIEW","FONTVIEW","LZ4FH","PRINTSHOP"};
static unsigned char media_request;
static unsigned int media_first[2];
static const char* file_viewer(const struct Entry*, unsigned char);

static unsigned char media_type(const char* name)
{
    unsigned char i;
    for (i=0;i<9;++i) if (!strcmp(name,media_names[i])) return i+1;
    return 0;
}

static unsigned char media_prepare(unsigned char kind)
{
    struct Panel* pan=&panels[active];
    unsigned int first=pan->first;
    unsigned char cursor=pan->cursor, top=pan->top, dir, i, changed=0;
    const char* viewer;
    album[0][0]=album[1][0]=0;
    media_request=0;
    if (!kind || pan->fs || !pan->path[0]) return 1;
    if (!pan->count || !overlay("OPEN")) return 0;
    keep_tags(1);
    for(dir=0;dir<2;++dir) {
        i=cursor;
        for(;;) {
            if (dir) {
                if (++i>=pan->count) {
                    if (!pan->more || pan->first>65535U-WINDOW) break;
                    pan->first+=WINDOW; changed=1;
                    if (!read_panel(active)) return 0;
                    if (!pan->count) break;
                    i=0;
                }
            } else {
                if (!i) {
                    if (!pan->first) break;
                    pan->first-=WINDOW; changed=1;
                    if (!read_panel(active)) return 0;
                    if (!pan->count) break;
                    i=pan->count;
                }
                --i;
            }
            if (is_dir(&pan->e[i])) continue;
            if (!build_full(full,pan,&pan->e[i])) break;
            viewer=file_viewer(&pan->e[i],kind<3?kind+1:0);
            if (!viewer) break; /* An I/O error is not evidence of another type. */
            if (!strcmp(viewer,media_names[kind-1])) {
                strcpy(album[dir],pan->e[i].name);media_first[dir]=pan->first;break;
            }
        }
        if (changed) {
            pan->first=first;
            if (!read_panel(active) || pan->first!=first || cursor>=pan->count) return 0;
            keep_tags(0);
        }
        pan->cursor=cursor;pan->top=top;
    }
    return 1;
}

#pragma code-name(push, "LC")
static unsigned char media_key(unsigned char key)
{
    /* cc65 marks Open-Apple/PB0 with bit 7, including Escape. */
    key &= 127;
    if(key==KEY_ESC)return 1;
    if((key==KEY_LEFT || key==KEY_RIGHT) && album[key==KEY_RIGHT][0]) {
        media_request=key;return 1;
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
