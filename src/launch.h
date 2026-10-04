/* RUN owns this scratch after the panel/tag backup. ConfigState uses only
 * $3000-$33FF; launch paths survive save_config and shared path buffers.
 * Writes: configuration via its recoverable save, then MAIN program memory
 * and ProDOS prefix via chain_load, which also sets the reset vector to the
 * monitor's OLDRST ($FF59): A2FC's own ($400C) would be the launched
 * program's bytes. No AUX /RAM storage is borrowed here.
 * The launched program takes control and may perform its own disk writes.
 */
struct LaunchState {
    char runtime[PATH_LEN], command[PATH_LEN];
    char backdrop[NAME_LEN];            /* a movie's marked backdrop, or "" */
};
typedef char launch_state_fits[0x400 - sizeof(struct LaunchState)];
typedef char launch_config_separate[0x400 - sizeof(struct ConfigState)];
#ifndef LAUNCH_STATE
#define LAUNCH_STATE ((struct LaunchState*)0x3400)
#endif
#define LS LAUNCH_STATE
extern unsigned int chain_size;
#pragma rodata-name(push, "LC")
static const char run_pick[] = "Select a ProDOS program.";
static const char run_types[] = "SYS, BIN, BAS or INT only.";
#pragma rodata-name(pop)
static const char run_bad[] = "Invalid program/runtime.";
static const char run_ask[] = "Run %s? No return to A2FC.";
/* The way back, spelt out: BASIC.SYSTEM keeps the prefix on the program's
 * directory (its data files live there), so the bare -A2FILE.SYSTEM only
 * resolves from A2FC's own directory. Up to 40 characters of that directory
 * keep the question within 79 columns. */
static const char run_back[] = "Run %s? Back: -%s/A2FILE.SYSTEM";
static const char run_basic[] = "/BASIC.SYSTEM";
static const char run_integer[] = "/INTBASIC.SYSTEM";
#pragma rodata-name(push, "LC")
static const char run_err[] = "Run";
static const char run_prefix[] = "Prefix";
#pragma rodata-name(pop)
static const char run_cfgwarn[] = "Configuration warning. Run anyway?";
/* Fantavision movies play in FANTA.SYSTEM, beside the overlays; it comes
 * back by the A2FILE.SYSTEM of the prefix it was started with. */
static const char run_fanta[] = "/A2FILE/FANTA.SYSTEM";
static const char run_nohome[] = "A2FC's own directory is unknown.";
static const char run_onebd[] = "Mark one hi-res picture as the backdrop.";
static const char run_bdname[] = ",";
/* Take 1 movies play in TAKE1.SYSTEM, given the movie's DOS 3.3 disk image
 * and the track/sector of its first T/S list, a real DOS 3.3 disk by its
 * ProDOS unit, or the extracted MV. file (docs/TAKE1-FORMAT.md). */
static const char run_take1[] = "/A2FILE/TAKE1.SYSTEM";
static const char run_t1mv[] = "MV.";
static const char run_t1ts[] = ",%04X";
static const char run_t1unit[] = "%%%02X,%04X";
static const char run_t1where[] = "Take 1 plays from a folder, a DOS 3.3 disk or image.";

/* 1 found, 0 genuinely absent, -1 lookup error. Never
 * reinterpret an unreadable runtime as a request to try another disk. */
static signed char runtime_probe(const char* path)
{
    if (!file_info(path)) {
        if (_oserror == 0x46) return 0;
        report_error(run_err); return -1;
    }
    strcpy(LS->runtime, path);
    return 1;
}

static void runtime_root(const char* path, const char* suffix)
{
    char* slash;
    strcpy(full, path);
    slash = strchr(full + 1, '/');
    if (slash) *slash = 0;
    strcat(full, suffix);  /* root <= 16 bytes, suffix <= 16 */
}

static unsigned char basic_path(const char* suffix)
{
    signed char found;
    runtime_root(pan_at(active)->path, suffix);
    found = runtime_probe(full);
    if (found) return found > 0;
    if (cfg_path[0]) {
        runtime_root(cfg_path, suffix);
        found = runtime_probe(full);
        if (found) return found > 0;
    }
    for (;;) {
        if (companion_path(suffix)) {
            found = runtime_probe(other_full);
            if (found) return found > 0;
        }
        if (!ask_disk(suffix + 1)) return 0;
    }
}

/* Check the real file, not a possibly stale panel entry: its length, its
 * type (`type`: $FF for a system program or an interpreter, $06 for a
 * binary) and, for a binary, the load address, its aux type on disk, given
 * back in *addr. The chain thunk's I/O buffer begins at $BB00. Interpreters
 * must advertise enough space for the ProDOS path at +6 before we write
 * into that header. */
static unsigned char launch_check(unsigned int* addr, unsigned char interpreter, unsigned char type)
{
    FILE* f;
    long size;
    unsigned char bad;
    if (!file_info(LS->runtime)) { report_error(run_err); return 0; }
    if (gfi[7] < 1 || gfi[7] > 3 || !(gfi[3] & 1) || gfi[4] != type) { message(run_bad); return 0; }
    if (type == 0x06) *addr = gfi[5] | (gfi[6] << 8);
    f = fopen(LS->runtime, cfg_rb);
    if (!f) { report_error(run_err); return 0; }
    bad = 0;
    if (interpreter) {
        if (fread(copy_buf, 1, 7, f) != 7 || ferror(f)) bad = 1;
        else if (copy_buf[0] != 0x4C || copy_buf[3] != 0xEE || copy_buf[4] != 0xEE ||
                 copy_buf[5] < 47) bad = 1;
    }
    if (fseek(f, 0, SEEK_END)) bad = 1;
    size = ftell(f);
    if (size <= 0 || *addr < 0x0800 || *addr >= 0xBB00 || (unsigned long)size > 0xBB00 - *addr ||
        (interpreter && size < 53)) bad = 1;
    if (fclose(f)) bad = 1;
    if (bad) message(run_bad);
    else chain_size = (unsigned int)size;
    return !bad;
}

/* An interpreter beside the overlays (FANTA.SYSTEM, TAKE1.SYSTEM), given
 * LS->command, with the prefix on A2FC's own directory -- where it finds
 * A2FILE.SYSTEM to come back. Read-only; no question: the way back is
 * automatic. */
static void launch_interp(const char* sys)
{
    unsigned int addr = 0x2000;
    unsigned char addr_len = strlen(cfg_path);   /* "/VOL/.../A2FILE/A2FILE.CFG": 18 past the directory */
    if (addr_len <= 18 || addr_len + 2 >= PATH_LEN) { message(run_nohome); return; }
    if (strlen(LS->command) > 46) { too_long(); return; }
    memcpy(other_full, cfg_path, addr_len - 18);
    other_full[addr_len - 18] = 0;
    strcpy(LS->runtime, other_full);
    strcat(LS->runtime, sys);
    if (!launch_check(&addr, 1, 0xFF)) return;
    if (!save_config() && !confirm(run_cfgwarn)) return;
    /* save_config may reuse other_full: the directory again, from the
     * runtime path LaunchState keeps. */
    memcpy(other_full, LS->runtime, addr_len - 18);
    other_full[addr_len - 18] = 0;
    if (chdir(other_full)) { report_error(run_prefix); return; }
    chain_command(LS->command);
    chain_addr = addr;
    clrscr();
    chain_load(LS->runtime);
}

/* A Take 1 movie (MV.x, BIN $8029 or aux 0 -- OPEN's rule): the command for
 * TAKE1.SYSTEM, whatever the panel shows -- a DOS 3.3 image, a real DOS 3.3
 * disk, or a ProDOS folder holding the extracted files. */
static void run_take1_movie(const struct Entry* e)
{
    const struct Panel* pan = pan_at(active);
    if (pan->fs == FS_DOS33) {
        if (pan->img_len) {
            if (pan->img_len > 41) { too_long(); return; }
            memcpy(LS->command, pan->path, pan->img_len);
            sprintf(LS->command + pan->img_len, run_t1ts, e->mdate);
        } else sprintf(LS->command, run_t1unit, (unsigned char)pan->dir_key, e->mdate);
    } else if (pan->fs || !pan->path[0]) { message(run_t1where); return; }
    else if (!build_full(LS->command, pan, e)) { too_long(); return; }
    launch_interp(run_take1);
}

static void run_selected(const struct Entry* e)
{
    unsigned int addr;
    unsigned char bas, addr_len;
    if (e->type == 0x06 && (e->aux == 0x8029 || !e->aux) && !strncmp(e->name, run_t1mv, 3)) {
        run_take1_movie(e);
        return;
    }
    if (is_dir(e) || !pan_at(active)->path[0] || pan_at(active)->fs) { message(run_pick); return; }
    bas = e->type == 0xFA || e->type == 0xFC;
    if (!bas && e->type != 0xFF && e->type != 0x06) { message(run_types); return; }
    /* A movie's backdrop: the one hi-res page (8,184 or 8,192 bytes) marked
     * in its panel. Looked up first, in the entries RUN was given at $3000
     * (a big overlay covers the table at $2000): LaunchState at $3400 is
     * written over the rest of that snapshot below, the name last. */
    {
        const struct Panel* pan = pan_at(active);
        unsigned char i, bd = 0xFF;
        if (named_kind(e) == 8)
            for (i = 0; i < pan->count; ++i)
                if (tagged(pan, i) && page_size(&ENTRY_SNAPSHOT[i].size)) {
                    if (bd != 0xFF) { message(run_onebd); return; }
                    bd = i;
                }
        /* LaunchState lies over the snapshot: the name moves only now,
         * with memmove (the two may overlap). */
        if (bd != 0xFF) memmove(LS->backdrop, ENTRY_SNAPSHOT[bd].name, NAME_LEN);
        else LS->backdrop[0] = 0;
    }
    if (!build_full(LS->command, pan_at(active), e)) { too_long(); return; }
    addr = 0x2000;              /* a binary's own address comes from launch_check */
    addr_len = strlen(cfg_path);           /* "/VOL/.../A2FILE/A2FILE.CFG": 18 past the directory */
    if (named_kind(e) == 8) {
        /* A Fantavision movie: FANTA.SYSTEM, an interpreter, is given its
         * full path, with the prefix on A2FC's own directory -- where it
         * finds A2FILE.SYSTEM to come back. Read-only; no question: the
         * way back is automatic. */
        if (addr_len <= 18 || addr_len + 2 >= PATH_LEN) { message(run_nohome); return; }
        /* The backdrop found above goes by name after a comma
         * (FANTA.SYSTEM reads it from the movie's directory). None marked:
         * FANTA.SYSTEM looks for NAME beside M.NAME itself. The chain
         * thunk's 46 characters are checked before anything is appended:
         * LS->command holds PATH_LEN, a name 15 more. */
        {
            unsigned char n = strlen(LS->command);
            if (n > 46 || (LS->backdrop[0] && n + 1 + strlen(LS->backdrop) > 46)) { too_long(); return; }
            if (LS->backdrop[0]) {
                strcat(LS->command, run_bdname);
                strcat(LS->command, LS->backdrop);
            }
        }
        launch_interp(run_fanta);
        return;
    }
    if (bas) {
        if (!basic_path(e->type == 0xFA ? run_integer : run_basic)) return;
        /* Long absolute paths use the source directory as prefix. */
        if (strlen(LS->command) > 46) strcpy(LS->command, e->name);
    } else {
        strcpy(LS->runtime, LS->command);
        LS->command[0] = 0;
    }
    if (!launch_check(&addr, bas, bas ? 0xFF : e->type)) return;
    if (addr_len > 18 && addr_len <= 18 + 40) {
        memcpy(other_full, cfg_path, addr_len - 18);
        other_full[addr_len - 18] = 0;
        sprintf(question, run_back, e->name, other_full);
    } else sprintf(question, run_ask, e->name);
    if (!confirm(question)) return;
    if (!save_config() && !confirm(run_cfgwarn)) return;
    if (chdir(pan_at(active)->path)) { report_error(run_prefix); return; }
    /* Shared buffers and configuration I/O cannot alter either path now. */
    chain_command(LS->command);
    chain_addr = addr;
    clrscr();
    chain_load(LS->runtime);
}
