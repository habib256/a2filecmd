/* Resident exclusive output reservation. Included by a2fc.c only; every
 * writer reserves, then opens "wb" itself. Contract: docs/FILE-SERVICES.md. */
#define OUTPUT_RESERVED 1
#define OUTPUT_CLOSE_FAILED 2
/* Zero grants no ownership. Both nonzero results own the new entry, but
 * only OUTPUT_RESERVED permits reopening it for writing. No cleanup here:
 * BATCH must retain ownership if its attempted cleanup fails. */
static unsigned char reserve_output(const char* path)
{
    int fd = open(path, O_WRONLY | O_CREAT | O_EXCL);
    if (fd < 0) return 0;
    return close(fd) ? OUTPUT_CLOSE_FAILED : OUTPUT_RESERVED;
}
