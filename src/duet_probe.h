/* Read-only structural probe; a match without a name/type hint is only
 * compatible, never permission to change attributes. Accept up to 255 bytes
 * of legacy DOS sector padding after a complete terminating record. */
#ifndef DP_READ
#define DP_READ fread
#endif
#ifndef DP_ERROR
#define DP_ERROR ferror
#endif
#ifndef DP_GET
static FILE* dp_file;
static unsigned char* dp_buffer;
static unsigned int dp_pos, dp_len;
static int dp_get(void)
{
    if (dp_pos == dp_len) {
        dp_pos = 0;
        dp_len = DP_READ(dp_buffer, 1, 512, dp_file);
        if (!dp_len) return -1;
    }
    return dp_buffer[dp_pos++];
}
#define DP_GET() dp_get()
#define DP_START(f,b) (dp_file=(f),dp_buffer=(b),dp_pos=dp_len=0)
#endif
static unsigned char duet_probe(FILE* f, unsigned char* b)
{
    unsigned int total = 0, tail = 0;
    unsigned char phase = 0, duration = 0, audible = 0, notes = 0, ended = 0;
    int c;
    DP_START(f,b);
    while ((c = DP_GET()) >= 0) {
        if (++total > 7168) return 0;
        if (ended) { if (++tail > 255) return 0; continue; }
        if (!phase) { duration = c; audible = 0; }
        else {
            if (duration == 1 && c > 8) return 0;
            audible |= c != 0;
        }
        if (++phase == 3) {
            phase = 0;
            if (!duration) ended = 1;
            else if (duration > 1 && audible && notes < 4) ++notes;
        }
    }
    if (DP_ERROR(f)) return 2;
    return ended && notes == 4;
}
