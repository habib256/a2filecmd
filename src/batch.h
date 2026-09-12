/* BATCH code ends below $3000. Its caller snapshots the active entry table
 * at $3000 before loading it. Only the exclusively created destination
 * A2MOVE.LST is written here; MOVE owns each actual transfer. No AUX use. */
#ifndef BATCH_ENTRIES
#define BATCH_ENTRIES ((struct Entry*)0x3000)
#endif
static const char batch_leaf[] = "A2MOVE.LST";
static const char batch_bad[] = "Move list read/write failed; remaining sources kept.";
static const char batch_kept[] = "A2MOVE.LST kept in destination; check it before retrying.";

static const char bt_s0[] = "Cannot batch move directories or A2MOVE.LST.";
static const char bt_s1[] = "Move %u to %s?";
static const char bt_s2[] = "Cannot reserve A2MOVE.LST; no file moved.";
static const char bt_s3[] = "wb";
static const char bt_s4[] = "rb";
static const char bt_s5[] = "Panel directory changed; batch stopped.";
static const char bt_s6[] = "Source missing, locked or changed; batch stopped.";
static const char bt_s7[] = "%u/%u moved. %.60s";

static unsigned int batch_crc(const struct Entry* e)
{
    unsigned char i, bit;
    unsigned int crc = 0xFFFF;
    const unsigned char* p = (const unsigned char*)e;
    for (i = 0; i < sizeof(struct Entry); ++i) {
        crc ^= (unsigned int)p[i] << 8;
        for (bit = 0; bit < 8; ++bit) crc = (crc << 1) ^ ((crc & 0x8000) ? 0x1021 : 0);
    }
    return crc;
}

static unsigned char batch_record(FILE* f)
{
    unsigned char crc[2], i;
    unsigned int sum;
    if (fread(&selected, 1, sizeof selected, f) != sizeof selected || fread(crc, 1, 2, f) != 2) return 0;
    sum = batch_crc(&selected);
    if (crc[0] != (unsigned char)sum || crc[1] != (unsigned char)(sum >> 8)) return 0;
    for (i = 0; i < NAME_LEN && selected.name[i]; ++i)
        if (!((selected.name[i] >= 'A' && selected.name[i] <= 'Z') ||
              (i && ((selected.name[i] >= '0' && selected.name[i] <= '9') || selected.name[i] == '.')))) return 0;
    return i && i <= 15 && selected.type != 0x0F;
}

static unsigned char batch_close(FILE* f, unsigned char bad)
{
    if (ferror(f)) bad = 1;
    if (fclose(f)) bad = 1;
    return !bad;
}

static void batch_discard(void)
{
    if (MB->owned && remove(MB->list)) strcpy(note, batch_kept);
    else MB->owned = 0;
}

static void batch_write(void)
{
    struct Panel* pan = &panels[active];
    struct Entry* e;
    FILE* f;
    int fd;
    unsigned char i, bad = 0, crc[2];
    unsigned int sum;
    memset(MB, 0, sizeof *MB);
    if (pan->fs || panels[!active].fs || !target_check()) return;
    strcpy(MB->source, pan->path); strcpy(MB->target, panels[!active].path);
    strcpy(MB->list, MB->target);
    if (!push_name(MB->list, batch_leaf)) { too_long(); return; }
    for (i = 0; i < pan->count; ++i) if (tagged(pan, i)) {
        e = &BATCH_ENTRIES[i];
        if (is_dir(e) || !strcmp(e->name, batch_leaf)) {
            strcpy(note, bt_s0); return;
        }
        ++MB->count;
    }
    if (!MB->count) return;
    sprintf(note, bt_s1, MB->count, MB->target);
    /* Keep the question within 79 columns even for a long target path. */
    note[79] = 0;
    if (!confirm(note)) { note[0] = 0; return; }
    _filetype = 0x06; _auxtype = 0;
    fd = open(MB->list, O_WRONLY | O_CREAT | O_EXCL);
    if (fd < 0) { strcpy(note, bt_s2); return; }
    MB->owned = 1;
    if (close(fd)) { strcpy(note, batch_bad); batch_discard(); return; }
    f = fopen(MB->list, bt_s3);
    if (!f) { strcpy(note, batch_bad); batch_discard(); return; }
    for (i = 0; i < pan->count && !bad; ++i) if (tagged(pan, i)) {
        e = &BATCH_ENTRIES[i]; sum = batch_crc(e);
        crc[0] = sum; crc[1] = sum >> 8;
        bad = fwrite(e, 1, sizeof *e, f) != sizeof *e || fwrite(crc, 1, 2, f) != 2;
    }
    if (!batch_close(f, bad)) bad = 1;
    if (!bad) {
        f = fopen(MB->list, bt_s4);
        if (!f) bad = 1;
        else {
            for (i = 0; i < pan->count && !bad; ++i) if (tagged(pan, i))
                if (!batch_record(f) || memcmp(&selected, &BATCH_ENTRIES[i], sizeof selected)) bad = 1;
            if (!bad && fread(copy_buf, 1, 1, f)) bad = 1;
            if (!batch_close(f, bad)) bad = 1;
        }
    }
    if (bad) { strcpy(note, batch_bad); batch_discard(); return; }
    memset(panels[0].tags, 0, sizeof panels[0].tags);
    memset(panels[1].tags, 0, sizeof panels[1].tags);
    keep_tags(1);
    MB->ready = 1; note[0] = 0;
}

static void batch_read(void)
{
    FILE* f;
    unsigned char bad;
    MB->ready = 0;
    if (strcmp(panels[active].path, MB->source) || strcmp(panels[!active].path, MB->target)) {
        strcpy(note, bt_s5); return;
    }
    f = fopen(MB->list, bt_s4);
    if (!f) { strcpy(note, batch_bad); return; }
    bad = fseek(f, (unsigned long)MB->index * (sizeof selected + 2), SEEK_SET) != 0;
    if (!bad && !batch_record(f)) bad = 1;
    if (!batch_close(f, bad)) { strcpy(note, batch_bad); return; }
    if (!build_full(full, &panels[active], &selected) || !file_info(full) ||
        (gfi[3] & 0x81) != 0x81 || gfi[7] < 1 || gfi[7] > 3 || gfi[4] != selected.type ||
        (gfi[5] | ((unsigned int)gfi[6] << 8)) != selected.aux) {
        strcpy(note, bt_s6); return;
    }
    MB->ready = 1;
}

static void batch_finish(void)
{
    FILE* f;
    unsigned char i, j, bad = 0;
    struct Panel* pan = &panels[active];
    memset(panels[0].tags, 0, sizeof panels[0].tags);
    memset(panels[1].tags, 0, sizeof panels[1].tags);
    f = fopen(MB->list, bt_s4);
    if (!f) bad = 1;
    else {
        for (i = 0; i < MB->count && !bad; ++i) {
            if (!batch_record(f)) { bad = 1; break; }
            if (i >= MB->index && !strcmp(pan->path, MB->source))
                for (j = 0; j < pan->count; ++j)
                    if (!strcmp(selected.name, BATCH_ENTRIES[j].name)) { set_tag(pan, j, 1); break; }
        }
        if (!bad && fread(copy_buf, 1, 1, f)) bad = 1;
        if (!batch_close(f, bad)) bad = 1;
    }
    keep_tags(1); /* overlay_run restores these exact-name marks after rereading */
    sprintf(note, bt_s7, MB->index, MB->count, MB->reason);
    if (bad) strcpy(note, batch_kept);
    else batch_discard();
}

void __fastcall__ batch_entry(const struct A2fcApi* a)
{
    MB->ready = 0;
    if (a->arg == 'W') batch_write();
    else if (a->arg == 'R') batch_read();
    else batch_finish();
}
