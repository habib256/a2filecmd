/* mini_sim.c -- host side of the sim65 harness for A2FC Mini.
 *
 * Runs the real 6502 catalog and copy modules under sim65. The disks
 * live in the Python driver, which is where faults are injected and
 * where the bytes are checked afterwards; this program only forwards
 * sector requests and calls the routines it is told to.
 *
 * Framing, 6502 to host:
 *   'P'                        give me a command
 *   'S' cmd drive track sector a sector, plus 256 bytes when writing
 *   'R' ...                    the result of the last command
 * Host to 6502:
 *   after 'P': one command byte
 *   after 'S': status, rwts_error, plus 256 bytes on a good read
 */
#include <stdlib.h>
#include <unistd.h>

extern unsigned char track, sector, drive, buffer[256];
unsigned char sim_rwts_error;

unsigned char mini_catalog(void);
unsigned char mini_preview(void);
unsigned char mini_prepare(void);
unsigned char mini_execute(void);
void mini_cancel(void);
unsigned char mini_load(void);
unsigned char mini_create_prepare(void);
unsigned char mini_create_execute(void);
unsigned char mini_delete_prepare(void);
unsigned char mini_delete_execute(void);

static unsigned char msg[5];
static unsigned char scratch[256];

static void put(const unsigned char *p, unsigned int n)
{
    unsigned int done = 0;
    int r;
    while (done < n) {
        r = write(1, p + done, n - done);
        if (r <= 0) exit(70);
        done += r;
    }
}

static void get(unsigned char *p, unsigned int n)
{
    unsigned int done = 0;
    int r;
    while (done < n) {
        r = read(0, p + done, n - done);
        if (r <= 0) exit(71);
        done += r;
    }
}

unsigned char sim_read(void)
{
    msg[0] = 'S';
    msg[1] = 1;
    msg[2] = drive;
    msg[3] = track;
    msg[4] = sector;
    put(msg, 5);
    get(msg, 2);
    sim_rwts_error = msg[1];
    if (msg[0]) return 1;       /* a failure is never an end of file */
    get(buffer, 256);
    return 0;
}

unsigned char sim_write(void)
{
    msg[0] = 'S';
    msg[1] = 2;
    msg[2] = drive;
    msg[3] = track;
    msg[4] = sector;
    put(msg, 5);
    put(buffer, 256);
    get(msg, 2);
    sim_rwts_error = msg[1];
    return msg[0] ? 1 : 0;
}

static void reply(unsigned char value)
{
    msg[0] = 'R';
    msg[1] = value;
    put(msg, 2);
}

int main(void)
{
    unsigned char *p;
    unsigned int n;
    for (;;) {
        msg[0] = 'P';
        put(msg, 1);
        get(msg, 1);
        switch (msg[0]) {
        case 0:
            return 0;
        case 1:
            reply(mini_catalog());
            break;
        case 2:
            reply(mini_preview());
            break;
        case 3:
            reply(mini_prepare());
            break;
        case 4:
            reply(mini_execute());
            break;
        case 5:
            mini_cancel();
            reply(0);
            break;
        case 8:
            reply(mini_load());
            break;
        case 9:
            reply(mini_create_prepare());
            break;
        case 10:
            reply(mini_create_execute());
            break;
        case 11:
            reply(mini_delete_prepare());
            break;
        case 12:
            reply(mini_delete_execute());
            break;
        case 6:                 /* peek: address low, high, length */
            get(msg, 3);
            p = (unsigned char *)(msg[0] | (msg[1] << 8));
            n = msg[2] ? msg[2] : 256;
            scratch[0] = 'R';
            put(scratch, 1);
            put(p, n);
            break;
        case 7:                 /* poke: address low, high, length, bytes */
            get(msg, 3);
            p = (unsigned char *)(msg[0] | (msg[1] << 8));
            n = msg[2] ? msg[2] : 256;
            get(scratch, n);
            while (n--) p[n] = scratch[n];
            reply(0);
            break;
        default:
            return 72;
        }
    }
}
