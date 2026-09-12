/* RUN owns $3000-$33FF while saving/loading preferences. No AUX writes.
 * Only A2FILE.CFG and exclusively owned A2FILE.TMP/A2FILE.BAK are changed.
 * Rename is not a power-fail transaction: retain recovery files on ambiguity. */
struct ConfigState {
    char temp[PATH_LEN], backup[PATH_LEN];
    char text[2 * PATH_LEN + 8], read[2 * PATH_LEN + 8];
    unsigned int size;
};
#ifndef CONFIG_STATE
#define CONFIG_STATE ((struct ConfigState*)0x3000)
#endif
#define CF CONFIG_STATE
static const char cfg_format[] = "%s\r%s\rS%uA%u\r";
static const char cfg_failed[] = "Configuration not saved; original kept.";
static const char cfg_recovery[] = "Check A2FILE.CFG, A2FILE.BAK and A2FILE.TMP before saving again.";
static const char cfg_rb[] = "rb";
static const char cfg_wb[] = "wb";

static const char cf_s0[] = "A2FILE.CFG";
static const char cf_s1[] = "A2FILE.TMP";
static const char cf_s2[] = "A2FILE.BAK";

static unsigned char cfg_paths(void)
{
    char* p;
    if (!cfg_path[0] || strlen(cfg_path) >= PATH_LEN) return 0;
    p = strrchr(cfg_path, '/');
    if (!p || strcmp(p + 1, cf_s0)) return 0;
    strcpy(CF->temp, cfg_path); strcpy(CF->backup, cfg_path);
    strcpy(CF->temp + (p - cfg_path) + 1, cf_s1);
    strcpy(CF->backup + (p - cfg_path) + 1, cf_s2);
    return 1;
}

/* Read everything, with a spare byte detecting oversized files. No partial
 * configuration is applied, including on read/close failure. */
static unsigned char cfg_read(const char* path)
{
    FILE* f;
    unsigned int n;
    unsigned char bad;
    f = fopen(path, cfg_rb);
    if (!f) return 0;
    n = fread(CF->read, 1, sizeof CF->read, f);
    bad = ferror(f) || n == sizeof CF->read;
    if (fclose(f)) bad = 1;
    if (bad) return 0;
    CF->read[n] = 0; CF->size = n;
    return 1;
}

static unsigned char cfg_parse(unsigned char apply)
{
    /* Keep a real pointer: cc65 can misoptimize an indexed field of an
     * absolute-address struct, omitting the pointer low-byte reload. */
    char* bytes = CF->read;
    unsigned int i = 0, start;
    unsigned char p, len;
    for (p = 0; p < 2; ++p) {
        start = i;
        while (i < CF->size && bytes[i] != '\r') {
            if ((unsigned char)bytes[i] < 32 || (unsigned char)bytes[i] > 126) return 0;
            ++i;
        }
        len = i - start;
        if (i == CF->size || len >= PATH_LEN || (len && bytes[start] != '/')) return 0;
        ++i;
    }
    if (CF->size - i != 5 || bytes[i] != 'S' || bytes[i+1] < '0' ||
        bytes[i+1] >= '0' + SORT_MODES || bytes[i+2] != 'A' ||
        (bytes[i+3] != '0' && bytes[i+3] != '1') || bytes[i+4] != '\r') return 0;
    if (apply) {
        sort_mode = bytes[i+1] - '0'; active = bytes[i+3] - '0';
        i = 0;
        for (p = 0; p < 2; ++p) {
            start = i;
            while (bytes[i] != '\r') ++i;
            bytes[i++] = 0; strcpy(panels[p].path, bytes + start);
        }
    }
    return 1;
}

static unsigned char cfg_verify(const char* path, unsigned int n)
{
    return cfg_read(path) && CF->size == n && !memcmp(CF->text, CF->read, n);
}

static void cfg_discard(void)
{
    strcpy(note, remove(CF->temp) ? cfg_recovery : cfg_failed);
}

static unsigned char save_config(void)
{
    FILE* f;
    int fd;
    unsigned int n;
    unsigned char old, bad;
    strcpy(note, cfg_failed);
    if (!cfg_paths()) return 0;
    if (file_info(CF->backup) || _oserror != 0x46) { strcpy(note, cfg_recovery); return 0; }
    old = file_info(cfg_path);
    if (!old && _oserror != 0x46) return 0;
    if (old && ((gfi[3] & 0xC3) != 0xC3 || gfi[4] != 0x04 || gfi[7] < 1 || gfi[7] > 3 ||
                !cfg_read(cfg_path) || !cfg_parse(0))) return 0;
    if (strlen(panels[0].path) >= PATH_LEN || strlen(panels[1].path) >= PATH_LEN) return 0;
    n = sprintf(CF->text, cfg_format, panels[0].path, panels[1].path, sort_mode, active);
    /* Validate our own serialization as well (no embedded CR or bad path). */
    memcpy(CF->read, CF->text, n); CF->size = n;
    if (!cfg_parse(0)) return 0;
    _filetype = 0x04; _auxtype = 0;
    fd = open(CF->temp, O_WRONLY | O_CREAT | O_EXCL);
    if (fd < 0) { strcpy(note, cfg_recovery); return 0; }
    if (close(fd)) { cfg_discard(); return 0; }
    f = fopen(CF->temp, cfg_wb);
    if (!f) { cfg_discard(); return 0; }
    bad = fwrite(CF->text, 1, n, f) != n;
    if (ferror(f)) bad = 1;
    if (fclose(f)) bad = 1;
    if (bad || !cfg_verify(CF->temp, n)) { cfg_discard(); return 0; }
    if (old && rename(cfg_path, CF->backup)) { strcpy(note, cfg_recovery); return 0; }
    if (rename(CF->temp, cfg_path)) {
        if (old && rename(CF->backup, cfg_path)) { strcpy(note, cfg_recovery); return 0; }
        /* A failed rename may be ambiguous: preserve TMP and any new CFG. */
        strcpy(note, cfg_recovery); return 0;
    }
    if (!cfg_verify(cfg_path, n)) { strcpy(note, cfg_recovery); return 0; }
    if (old && remove(CF->backup)) { strcpy(note, cfg_recovery); return 0; }
    note[0] = 0; return 1;
}

static void load_config(void)
{
    const char* path = cfg_path;
    if (!cfg_paths()) return;
    if (!file_info(path)) {
        if (_oserror != 0x46) { strcpy(note, cfg_failed); return; }
        path = CF->backup;
        if (!file_info(path)) {
            if (_oserror != 0x46) strcpy(note, cfg_recovery);
            return;
        }
        strcpy(note, cfg_recovery);
    }
    if (gfi[4] != 0x04 || !cfg_read(path) || !cfg_parse(1)) strcpy(note, cfg_recovery);
}
