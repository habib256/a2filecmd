/* Install a fully written temporary file without destroying the old entry.
 * Caller owns tmp; failed commits retain it for recovery. T is the API.
 * ProDOS RENAME refuses an existing destination (unlike POSIX rename).
 * REPLACE_* reports publication and recovery separately; never use truthiness.
 * Caller bounds paths, owns tmp, and has verified its closed contents. */
#define REPLACE_FAILED 0
#define REPLACE_DONE 1
#define REPLACE_BACKUP 2
#define REPLACE_RESTORE_FAILED 3
#ifndef RF
#define RF(name) T.name
#endif
#ifndef replace_backup
static char replace_backup[PATH_LEN];
#endif
static struct { unsigned char n; unsigned char *old, *newpath; } replace_rn;
static struct { unsigned char n; unsigned char* path; unsigned char result[15]; } replace_ip;
/* Only for an entry created by this operation, never after a failed CREATE.
 * Failure leaves an output of uncertain completeness; do not claim removal. */
static unsigned char replace_discard(const char* path)
{
    if (!RF(remove)(path)) return 1;
    RF(strcpy)(T.note, "Cleanup failed; output retained. Check destination.");
    return 0;
}
static unsigned char replace_rename(const char* from, const char* to)
{
    T.copy_buf[0] = RF(strlen)(from);
    RF(strcpy)((char*)T.copy_buf + 1, from);
    T.copy_buf[128] = RF(strlen)(to);
    RF(strcpy)((char*)T.copy_buf + 129, to);
    replace_rn.n = 2; replace_rn.old = T.copy_buf; replace_rn.newpath = T.copy_buf + 128;
    return RF(mli)(0xC2, &replace_rn);
}
static unsigned char replace_info(const char* path)
{
    T.copy_buf[0] = RF(strlen)(path); RF(strcpy)((char*)T.copy_buf + 1, path);
    replace_ip.n = 10; replace_ip.path = T.copy_buf;
    return RF(mli)(0xC4, &replace_ip);
}
#define FI_RENAME replace_rename
#include "file_install.h"
static unsigned char replace_commit(const char* tmp, const char* target)
{
    unsigned char i = RF(strlen)(target);
    while (i && target[i] != '/') --i;
    if (!i || i + 10 >= PATH_LEN) return 0;
    RF(memcpy)(replace_backup, target, i + 1);
    RF(strcpy)(replace_backup + i + 1, "A2FC.BAK");
    if (replace_info(replace_backup) != 0x46 || replace_info(target) ||
        (replace_ip.result[0] & 0xC2) != 0xC2 || replace_ip.result[4] > 3) return 0;
    i = file_install(tmp, target, replace_backup, 1);
    if (i == FILE_RESTORE_FAILED) return REPLACE_RESTORE_FAILED;
    if (i != FILE_INSTALLED) return REPLACE_FAILED;
    return RF(remove)(replace_backup) ? REPLACE_BACKUP : REPLACE_DONE;
}
