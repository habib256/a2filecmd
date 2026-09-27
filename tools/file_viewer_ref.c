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
         * starts with). No test of n: an empty file, with a byte left by an
         * earlier probe, can only show DOCVIEW's empty page for TEXT's. */
        else if (type == 4 && (copy_buf[0] | 0xA0) == 0xFF) kind = 9;
        /* I supplies the missing intent for an unmarked lo-res screen or
         * pixmap. Return must not mistake every small BIN for a sprite. */
        else if (!kind && pictures && (type == 0x06 || type == 0x08) &&
                 e->size && e->size <= 2048) kind = 5;
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
