/* Host model of the resident's MLI CREATE in src/file_output.h, for the
 * harnesses that include it. Include it after the harness's own `open` and
 * `close` mocks (they inject the faults) and right before file_output.h.
 * A harness that has its own gfi[] defines HOST_HAS_GFI first. Checks the
 * parameter block the real CREATE gets, then makes the entry with
 * O_CREAT | O_EXCL, closed at once: one call that either creates or does
 * not, as ProDOS's CREATE. A close fault after the create cannot happen on
 * the real machine (there is no open file): the entry stays created and
 * owned, the harness's close result is ignored. A harness that used to
 * fail that close defines HOST_CREATE_FAULT to the same condition: the
 * CREATE then fails and leaves nothing (a ProDOS CREATE is one call). */
#include <fcntl.h>
#include <stdlib.h>
#include <string.h>
#ifndef __fastcall__
#define __fastcall__
#endif
#ifndef HOST_HAS_GFI
static unsigned char gfi[18];
#endif
static unsigned char gfi_path[256];  /* host temp paths exceed PATH_LEN */
static unsigned char host_create(unsigned char* p)
{
    char path[256];
    int fd;
    if (p != gfi || p[0] != 7 || p[1] != (unsigned char)((unsigned)(size_t)gfi_path & 0xFF) || p[2] != (unsigned char)((unsigned)(size_t)gfi_path >> 8) || p[3] != 0xC3 || p[7] != 1 ||
        p[8] || p[9] || p[10] || p[11]) abort();
#ifdef HOST_CREATE_FAULT
    /* the harness's former "reservation close fails" fault: on ProDOS a
     * CREATE that fails (I/O error, full directory) creates nothing */
    if (HOST_CREATE_FAULT) return 0x27;
#endif
    memcpy(path, gfi_path + 1, gfi_path[0]);
    path[gfi_path[0]] = 0;
    fd = open(path, O_WRONLY | O_CREAT | O_EXCL);
    if (fd < 0) return 0x47;
    close(fd);
    return 0;
}
#define FO_CREATE host_create
