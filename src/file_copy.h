/* Core copy service, included by a2fc.c only. Keep the wrapper resident
 * and the stage/check routines in COPY; never load it from an overlay
 * that must resume. Contract: docs/FILE-SERVICES.md. */
/* Copy state uses the idle text pagination buffer, not the recursive stack.
 * A small overlay leaves both panel tables and the directory pool intact. */
struct CopyState {
    char target[PATH_LEN], backup[PATH_LEN], temp[PATH_LEN];
    const char* name;
    unsigned long size;
    unsigned char type, had_old, owned, ok, bak;
    unsigned int aux;
};
#define CP ((struct CopyState*)text_starts)
/* Fail the build if the borrowed pagination storage becomes too small. */
typedef char copy_state_fits[sizeof text_starts - sizeof(struct CopyState) + 1];

#pragma code-name(push, "COPY")
#pragma rodata-name(push, "COPYRO")
static const char copy_tempname[] = "A2FC.COPY";
static unsigned char may_overwrite(const char* name)
{
    char key;
    if (over_policy == OVERWRITE_ALL) return 1;
    if (over_policy == SKIP_ALL) return 0;
    question_begin();
    cprintf("%s: Overwrite/Skip/All/None? ", name);
    revers(0);
    for (;;) {
        key = cgetc() | 0x20;
        if (key == 'o') return 1;
        if (key == 's') return 0;
        if (key == 'a') { over_policy = OVERWRITE_ALL; return 1; }
        if (key == 'n' || key == (KEY_ESC | 0x20)) { over_policy = SKIP_ALL; return 0; }
    }
}

/* Keep the old entry in place while an exclusively owned sibling is
 * written and verified. No failed lookup grants permission to write. */
static unsigned char copy_stage(void)
{
    FILE *in, *out;
    unsigned int n;
    unsigned long copied = 0;
    CP->had_old = CP->owned = CP->ok = CP->bak = 0;
    if (exists(CP->target)) {
        if (gfi[4] == 15 || !may_overwrite(CP->name)) {
            ++progress_skipped; ++progress_done; return 2;
        }
        if ((gfi[3] & 0xC2) != 0xC2) return 0;
        CP->had_old = 1;
    } else if (_oserror != 0x46) return 0;
    strcpy(CP->temp, CP->target);
    *strrchr(CP->temp, '/') = 0;
    if (!push_name(CP->temp, copy_tempname) || !strcmp(CP->temp, CP->target)) return 0;
    strcpy(CP->backup, CP->temp);
    strcpy(strrchr(CP->backup, '.') + 1, "BAK");
    /* A2FC.BAK only matters when an old entry has to move aside: then a
     * leftover one refuses the copy before its first byte is written. */
    if (CP->had_old && (exists(CP->backup) || _oserror != 0x46)) { CP->bak = 1; return 0; }
    in = fopen(full, "rb");
    if (!in) return 0;
    if (fseek(in, 0, SEEK_END) || (long)(CP->size = ftell(in)) < 0 || fseek(in, 0, SEEK_SET)) {
        fclose(in); return 0;
    }
    _filetype = CP->type; _auxtype = CP->aux;
    CP->owned = reserve_output(CP->temp);
    if (CP->owned != OUTPUT_RESERVED) { fclose(in); return 0; }
    out = fopen(CP->temp, "wb");
    if (!out) { fclose(in); return 0; }
    CP->owned = CP->ok = 1;
    while ((n = fread(copy_buf, 1, 512, in)) != 0) {
        if (fwrite(copy_buf, 1, n, out) != n || abort_key()) { CP->ok = 0; break; }
        copied += n;
        progress_bar(CP->name, copied, CP->size);
    }
    if (ferror(in) || ferror(out) || copied != CP->size) CP->ok = 0;
    if (fclose(in)) CP->ok = 0;
    if (fclose(out)) CP->ok = 0;
    return 0;
}
#pragma rodata-name(pop)
#pragma code-name(pop)

#pragma code-name(push, "COPY")
#pragma rodata-name(push, "COPYRO")
/* Read back both complete streams before a move may delete its source.
 * Half of copy_buf belongs to each stream: no extra disk buffer or heap. */
static void copy_check(void)
{
    FILE *in, *out;
    unsigned int n;
    unsigned long checked = 0;
    if (CP->ok) {
        in = fopen(full, "rb"); out = fopen(CP->temp, "rb");
        if (!in || !out) CP->ok = 0;
        while (CP->ok) {
            n = fread(copy_buf, 1, 256, in);
            if (fread(copy_buf + 256, 1, 256, out) != n ||
                memcmp(copy_buf, copy_buf + 256, n) || abort_key()) { CP->ok = 0; break; }
            checked += n;
            if (n < 256) break;
        }
        if (in) { if (ferror(in)) CP->ok = 0; if (fclose(in)) CP->ok = 0; }
        if (out) { if (ferror(out)) CP->ok = 0; if (fclose(out)) CP->ok = 0; }
        if (checked != CP->size) CP->ok = 0;
    }
}
#pragma rodata-name(pop)
#pragma code-name(pop)

#define FI_RENAME rename
#define FI_STATE CP
#include "plugins/file_install.h"

static const char copy_backup_kept[] = "Check A2FC.COPY / A2FC.BAK; source kept.";
static unsigned char copy_finish(void)
{
    unsigned char installed;
    if (!CP->ok) {
        /* Do not restore over an output whose deletion failed. */
        if (CP->owned && remove(CP->temp)) message("Cleanup failed; check target.");
        else if (!progress_abort) message(CP->bak ? copy_backup_kept : (const char*)"Failed; source kept.");
        return 0;
    }
    installed = FILE_INSTALL_FAILED;
    /* Checked again: the name may have appeared since. A new target sets
     * no old entry aside and never touches A2FC.BAK. */
    if (!CP->had_old || (!exists(CP->backup) && _oserror == 0x46)) installed = file_install();
    if (installed != FILE_INSTALLED) { message(copy_backup_kept); return 0; }
    if (CP->had_old && remove(CP->backup)) {
        message(copy_backup_kept); return 0;
    }
    ++a2fc_ops; ++progress_done;
    return 1;
}
static unsigned char copy_file(const char* name, unsigned char type, unsigned int aux)
{
    unsigned char r = 0;
    strcpy(CP->target, other_full);
    CP->name = name; CP->type = type; CP->aux = aux;
    if (overlay("COPY")) {
        r = copy_stage();
        if (r != 2) { copy_check(); r = copy_finish(); }
    }
    strcpy(other_full, CP->target);
    return r;
}
