/* Resident exclusive output reservation. Included by a2fc.c only.
 * Contract and remaining cleanup limits: docs/FILE-SERVICES.md. */
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
/* Reserve a new directory entry before any truncating open. A failed
 * lookup never grants permission to overwrite an existing file. */
static FILE* new_output(const char* path)
{
    FILE* f;
    switch (reserve_output(path)) {
    case 0: return NULL;
    case OUTPUT_RESERVED:
        f = fopen(path, "wb");
        if (f) return f;
    }
    remove(path);                   /* only the entry just created */
    return NULL;
}
