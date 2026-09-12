/* Resident ProDOS diagnostics, included while CODE and RODATA target LC.
 * Named strings keep cc65 literals out of MAIN. No file or volume writes;
 * report_error updates the MAIN error counter and the 80-column text screen
 * (MAIN/AUX $0400-$07FF) through conio, without touching ProDOS /RAM storage.
 * Shared by all overlays: must remain resident, never load another overlay.
 */
static const char pdE27[] = "disk I/O error";
static const char pdE2B[] = "the disk is write-protected";
static const char pdE2F[] = "no disk in the drive";
static const char pdE40[] = "invalid file name";
static const char pdE44[] = "directory not found";
static const char pdE45[] = "volume not found";
static const char pdE46[] = "file not found";
static const char pdE47[] = "name already in use";
static const char pdE48[] = "the disk is full";
static const char pdE49[] = "the directory is full";
static const char pdE4E[] = "the file is locked";
static const char pdE52[] = "not a ProDOS disk";

static const unsigned char pd_codes[] = {
    0x27, 0x2B, 0x2F, 0x40, 0x44, 0x45, 0x46, 0x47, 0x48, 0x49, 0x4E, 0x52
};
static const char* const pd_messages[] = {
    pdE27, pdE2B, pdE2F, pdE40, pdE44, pdE45,
    pdE46, pdE47, pdE48, pdE49, pdE4E, pdE52
};

static const char* prodos_error(unsigned char e)
{
    unsigned char i;
    for (i = 0; i < sizeof pd_codes; ++i)
        if (pd_codes[i] == e) return pd_messages[i];
    return 0;
}

static const char re_fmt1[] = "%s failed: %s.";
static const char re_fmt2[] = "%s failed (ProDOS $%02X, errno %d).";
static void report_error(const char* what)
{
    const char* why = prodos_error(_oserror);
    ++a2fc_errors;
    clear_row(22);
    gotoxy(0, 22);
    if (why)
        cprintf(re_fmt1, what, why);
    else
        cprintf(re_fmt2, what, _oserror, errno);
}
