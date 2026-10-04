/* file_viewer_ref.c -- the C text of OPEN's classifier, as it was until
 * src/open.s replaced it (2026-09-26), kept as the specification that
 * tools/test_file_viewers.py holds the assembly to: both must answer the
 * same viewer for every entry, file content, `pictures` and I/O failure.
 * A new rule goes into both. It uses a2fc.c's own tables (fv_*,
 * image_viewers), sliced in by the test with the rest of the resident
 * code it needs (image_kind, named_kind's stand-in, fopen & co). */
static const char open_dgr[] = "DGR";
static const char* fv_name;
static unsigned char fv_len;
/* The viewer the name ends for, with something before the suffix. One walk:
 * split in two, the length of each suffix was measured twice. */
static unsigned char by_suffix(void)
{
    const char* s = fv_ext;
    unsigned char i = 0, k;
    for (; *s; s += k + 1, ++i) {
        k = strlen(s);
        if (fv_len > k && !strcmp(fv_name + fv_len - k, s)) return fv_ids[i];
    }
    return 0;
}
/* A Graphics Magician picture's first bytes (docs/GRAPHICS-MAGICIAN-FORMAT.md,
 * section 3): the first command $2x/$4x/$6x/$8x/$Ax; each command that
 * starts in the bytes read has an argument nibble within its limit; the end
 * byte $00 comes before the end of a file shorter than 8 bytes. A picture
 * that ends in the bytes read obeys rules 4 and 5: it draws ($Ax, $Cx or
 * $Ex: the highest nibble is $A or more), and lines alone need a line
 * start ($8x). One that goes on does not open on its first three bytes
 * repeated at once (a command written twice in a row, a run of a 1-byte
 * command: tables, data, text). Arguments are not looked at: GMAGIC
 * checks the whole picture. */
static const unsigned char gm_lim[16] = { 0, 2, 8, 1, 8, 1, 1, 0, 2, 0, 2, 0, 2, 0, 2, 0 };
static unsigned char gm_prefix(unsigned char n)
{
    unsigned char x = 0, b, top = 0, start = 0;
    if ((unsigned char)(copy_buf[0] - 0x20) >= 0x90 || (copy_buf[0] & 0x10)) return 0;
    for (;;) {
        if (x >= n) return n >= 8 && memcmp(copy_buf, copy_buf + 3, 3);
        b = copy_buf[x];
        if (!b) return top > 10 || (top == 10 && start);
        if ((b & 15) >= gm_lim[b >> 4]) return 0;
        if (b >> 4 > top) top = b >> 4;
        if (b >> 4 == 8) start = 1;
        x += (gm_lim[b >> 4] & 3) + 1;
    }
}
/* The bytes read are all high-bit (Bank Street Writer's text), at least one. */
static unsigned char high_text(unsigned char n)
{
    unsigned char i;
    for (i = 0; i < n; ++i) if (!(copy_buf[i] & 0x80)) return 0;
    return n != 0;
}
unsigned char ref_file_viewer(const struct Entry* e, unsigned char pictures)
{
    unsigned char kind = image_kind(e);
    FILE* f;
    /* The type, once: every e->type is a load of e off the C stack. */
    unsigned char type = e->type;
    unsigned int aux = e->aux;
    unsigned char n = strlen(e->name), failed, music, named;
    unsigned char candidate = type==6 && e->name[0]=='M' && e->name[1]=='.';
    fv_name = e->name; fv_len = n;
    named = by_suffix();
    /* .SET / .FONT: an HRCG font only as a BIN of 768 or 1,024 bytes. */
    if (named == V_FONT && !(type == 6 && (e->size == 768 || e->size == 1024))) named = 0;
    music = named <= V_DUET ? named : 0;
    if (type==0xD5 && aux==0xD0E7) music=V_DUET;
    /* Album scans can reject unrelated names without opening every file. */
    if (pictures >= 2) {
        if (music != pictures-1 && !(pictures==4 && candidate)) return V_HEX;
        pictures = 0;
    }
    if (type == 7) return V_FONT;
    if (type == 8 && aux == 0x8066) return V_LZ;
    if (type == 6 && (aux & 0xCFFF) == 0x4800 &&
        (e->size == 572 || e->size == 576)) return V_PS;
    if (!pictures && type == 0xFA) return V_RUN;
    /* A Take 1 movie MV.x (BIN $8029 once extracted, aux 0 in a DOS 3.3
     * catalog): RUN hands it to TAKE1.SYSTEM. */
    if (!pictures && type == 6 && (aux == 0x8029 || !aux)
        && e->name[0] == 'M' && e->name[1] == 'V' && e->name[2] == '.') return V_RUN;
    if (named > V_DUET) return named;
    if (!pictures && music>=V_PT3) return music;
    /* Probe only in main-RAM copy_buf, never in a graphics/AUX bank.
     * Explicit packed metadata wins; the other formats can identify
     * themselves even without a filename suffix or a ProDOS image type.
     * A partial DGR signature still belongs to DGRVIEW's validation. */
    if (kind < 2) {
        f = fopen(full, "rb");
        if (!f) return 0;
        n = fread(copy_buf, 1, 8, f);
        failed = ferror(f) != 0;
        if (fclose(f)) failed = 1;
        if (failed) return 0;
        if (candidate && n==8 && copy_buf[0] && copy_buf[3]) music=V_DUET;
        if (n >= 3 && !memcmp(copy_buf, open_dgr, 3)) kind = 5;
        /* An Arlequin picture: type $F8 and "gs" after its size. */
        else if (type == 0xF8 && n >= 4 && copy_buf[2] == 'g' && copy_buf[3] == 's') kind = 6;
        else if (n == 8 && (!memcmp(copy_buf, "HGRR\1\0\0\x20", 8) ||
                           !memcmp(copy_buf, "DHRR\1\0\0\x40", 8))) kind = 1;
        /* An Epistole document opens on a `_` command, a Papyrus or
         * HomeWord one on a $FF code: DOCVIEW lays them out. OR $A0 makes
         * both $FF in one test (DEL and a high-bit _ too, which no text
         * starts with). Not an empty file: copy_buf[0] is then whatever
         * the last reader left there (VISICALC reads into copy_buf, and
         * its `>` sent an empty text file to VISICALC); it is TEXT's. */
        else if (type == 4 && n && (copy_buf[0] | 0xA0) == 0xFF) kind = 9;
        /* A VisiCalc worksheet (/SS): a text file whose first line is
         * `>A1:...`, in either form of `>` ($3E, $BE). VISICALC checks
         * the rest and sends anything else back to T. */
        else if (type == 4 && n && (copy_buf[0] | 0xA0) == 0xBE) kind = 10;
        /* A Bank Street Writer document: a BIN at $0840 or $63D0 (DOS 3.3
         * editions) or at 0 (ProDOS ones), high-bit text from its first
         * byte: DOCVIEW lays it out too. Not a page-sized BIN or an .RLE
         * (kind 1): a hi-res picture whose top row starts with eight bytes
         * of $80 or more (white, a palette-bit black) stays a picture, as
         * I and IMAGE's album already took it. */
        else if (!kind && !pictures && type == 6 && (aux == 0x0840 || aux == 0x63D0 || !aux) && high_text(n)) kind = 9;
        /* I supplies the missing intent for an unmarked lo-res screen or
         * pixmap. Return must not mistake every small BIN for a sprite. */
        else if (!kind && pictures && (type == 0x06 || type == 0x08) &&
                 e->size && e->size <= 2048) kind = 5;
        /* Return on a BIN that starts like a Graphics Magician picture. */
        else if (!kind && !pictures && type == 0x06 && gm_prefix(n)) kind = 11;
    }
    if (kind) return image_viewers[kind];
    if (pictures) return V_RAW; /* I may explicitly try an untyped raw file. */
    if (music) return music;
    if (type == 0xE0 && aux == 1) return V_UNWRAP;      /* AppleSingle */
    /* The types, as a table: written out, each one cost fourteen bytes of
     * OPEN, the tightest window of the program. */
    for (n = 0; n < sizeof fv_types; ++n) if (type == fv_types[n]) return fv_tids[n];
    return V_HEX;
}

/* OPEN's entry point, as it was in a2fc.c before open.s took it over: the
 * viewer of the selection, its overlay name into input; input stays "" for a
 * directory, an empty panel or a path too long, and after a probe error,
 * which is reported. */
void ref_open_entry(const struct A2fcApi* a)
{
    unsigned char viewer;
    input[0] = 0;
    if (selected.name[0] && !is_dir(&selected) && full[0]) {
        viewer = ref_file_viewer(&selected, a->arg);
        if (viewer) strcpy(input, media_names[viewer]);
        else report_error(selected.name);      /* "NAME failed (...)" */
    }
}
