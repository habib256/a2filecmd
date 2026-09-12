/* RUN owns this scratch after the panel/tag backup. ConfigState uses only
 * $3000-$33FF; launch paths survive save_config and shared path buffers.
 * Writes: configuration via its recoverable save, then MAIN program memory
 * and ProDOS prefix via chain_load. No AUX /RAM storage is borrowed here.
 * The launched program takes control and may perform its own disk writes.
 */
struct LaunchState {
    char runtime[PATH_LEN], command[PATH_LEN];
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
static const char run_basic[] = "/BASIC.SYSTEM";
static const char run_integer[] = "/INTBASIC.SYSTEM";
#pragma rodata-name(push, "LC")
static const char run_err[] = "Run";
static const char run_prefix[] = "Prefix";
#pragma rodata-name(pop)
static const char run_cfgwarn[] = "Configuration warning. Run anyway?";

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
    runtime_root(panels[active].path, suffix);
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

/* Check the real file length, not a possibly stale panel size. The chain
 * thunk's I/O buffer begins at $BB00. Interpreters must advertise enough
 * space for the ProDOS path at +6 before we write into that header. */
static unsigned char launch_check(unsigned int addr, unsigned char interpreter)
{
    FILE* f;
    long size;
    unsigned char bad;
    if (!file_info(LS->runtime)) { report_error(run_err); return 0; }
    if (gfi[7] < 1 || gfi[7] > 3 || !(gfi[3] & 1) ||
        (interpreter && gfi[4] != 0xFF)) { message(run_bad); return 0; }
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
    if (size <= 0 || addr < 0x0800 || addr >= 0xBB00 || size > (unsigned int)(0xBB00 - addr) ||
        (interpreter && size < 53)) bad = 1;
    if (fclose(f)) bad = 1;
    if (bad) message(run_bad);
    else chain_size = (unsigned int)size;
    return !bad;
}

static void run_selected(const struct Entry* e)
{
    unsigned int addr;
    unsigned char bas;
    if (is_dir(e) || !panels[active].path[0] || panels[active].fs) { message(run_pick); return; }
    bas = e->type == 0xFA || e->type == 0xFC;
    if (!bas && e->type != 0xFF && e->type != 0x06) { message(run_types); return; }
    if (!build_full(LS->command, &panels[active], e)) { too_long(); return; }
    if (bas) {
        if (!basic_path(e->type == 0xFA ? run_integer : run_basic)) return;
        /* Long absolute paths use the source directory as prefix. */
        if (strlen(LS->command) > 46) strcpy(LS->command, e->name);
        addr = 0x2000;
    } else {
        strcpy(LS->runtime, LS->command);
        LS->command[0] = 0;
        addr = e->type == 0xFF ? 0x2000 : e->aux;
    }
    if (!launch_check(addr, bas)) return;
    sprintf(question, run_ask, e->name);
    if (!confirm(question)) return;
    if (!save_config() && !confirm(run_cfgwarn)) return;
    if (chdir(panels[active].path)) { report_error(run_prefix); return; }
    /* Shared buffers and configuration I/O cannot alter either path now. */
    chain_command(LS->command);
    chain_addr = addr;
    clrscr();
    chain_load(LS->runtime);
}
