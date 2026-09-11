/* Install a fully written temporary file without destroying the old entry.
 * Caller owns tmp; failed commits retain it for recovery. T is the API.
 * ProDOS RENAME refuses an existing destination (unlike POSIX rename).
 * 1 installed, 2 installed with backup retained, 0 not installed. */
#ifndef RF
#define RF(name) T.name
#endif
#ifndef replace_backup
static char replace_backup[PATH_LEN];
#endif
static struct { unsigned char n; unsigned char *old, *newpath; } replace_rn;
static struct { unsigned char n; unsigned char* path; unsigned char result[15]; } replace_ip;
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
static unsigned char replace_commit(const char* tmp, const char* target)
{
    unsigned char i = RF(strlen)(target);
    while (i && target[i] != '/') --i;
    if (!i || i + 10 >= PATH_LEN) return 0;
    RF(memcpy)(replace_backup, target, i + 1);
    RF(strcpy)(replace_backup + i + 1, "A2FC.BAK");
    if (replace_info(replace_backup) != 0x46 || replace_info(target) ||
        (replace_ip.result[0] & 0xC2) != 0xC2 || replace_ip.result[4] > 3) return 0;
    if (replace_rename(target, replace_backup)) return 0;
    if (replace_rename(tmp, target)) {
        replace_rename(replace_backup, target);
        return 0;
    }
    return RF(remove)(replace_backup) ? 2 : 1;
}
