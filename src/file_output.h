/* Resident exclusive output reservation. Included by a2fc.c only; every
 * writer reserves, then opens "wb" itself. Contract: docs/FILE-SERVICES.md.
 *
 * One MLI CREATE ($C0), nothing else. cc65's open(O_CREAT | O_EXCL) issued
 * CREATE then OPEN and, when OPEN failed (too many open files, an I/O
 * error), returned -1 without destroying the entry it had just made: a
 * 0-byte A2FC.COPY, A2FC.EDIT or A2MOVE.LST stayed behind and every later
 * copy into that directory was refused -- "Failed; source kept." -- with
 * nothing to name the leftover (bug hunt 2). A CREATE that fails creates
 * nothing; one that succeeds is the whole reservation.
 * The parameter block is gfi[], which GET_FILE_INFO shares the first eight
 * bytes of (count, pathname, access, type, auxtype, storage); create date
 * and time follow, 0 for the clock's. _filetype and _auxtype are what
 * cc65's open() gave the entry too. Host harnesses define FO_CREATE to
 * their own file system (tools/host_reserve.h). */
#ifndef FO_CREATE
#define FO_CREATE(p) mli_call(0xC0, p)
#endif
#define OUTPUT_RESERVED 1

/* gfi_path <- path as a ProDOS (counted) name, gfi[0] <- the parameter
 * count, gfi[1-2] <- its address: file_info and reserve_output share it. */
static void __fastcall__ gfi_prepare(const char* path, unsigned char count)
{
    unsigned char len = strlen(path);
    gfi_path[0] = len;
    memcpy(gfi_path + 1, path, len);
    gfi[0] = count;
    gfi[1] = (unsigned char)((unsigned)gfi_path & 0xFF);
    gfi[2] = (unsigned char)((unsigned)gfi_path >> 8);
}

/* Zero grants no ownership: the entry exists already ($47), the directory
 * is full, the volume is locked or failed. OUTPUT_RESERVED owns the new
 * entry and permits reopening it for writing. No cleanup here: BATCH must
 * retain ownership if its attempted cleanup fails. */
static unsigned char reserve_output(const char* path)
{
    gfi_prepare(path, 7);
    gfi[3] = 0xC3;              /* destroy, rename, write, read */
    gfi[4] = _filetype;
    gfi[5] = (unsigned char)_auxtype;
    gfi[6] = (unsigned char)(_auxtype >> 8);
    gfi[7] = 1;                 /* a seedling */
    memset(gfi + 8, 0, 4);
    return !FO_CREATE(gfi);
}
