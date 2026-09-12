/* Resident display-only lookup. No files, AUX storage or overlay loads.
 * Unknown types share a four-byte buffer, as before; callers consume it
 * immediately. Fixed-width rows include their terminator.
 */
static const unsigned char display_types[] = {
    0x04, 0x06, 0x0F, 0x1A, 0xB3, 0xFA, 0xFC, 0xFD, 0xFF
};
static const char display_names[][4] = {
    "TXT", "BIN", "DIR", "AWP", "S16", "INT", "BAS", "VAR", "SYS"
};
static const char* type_name(unsigned char type)
{
    static char hex[4];
    unsigned char i;
    for (i = 0; i < sizeof display_types; ++i)
        if (display_types[i] == type) return display_names[i];
    sprintf(hex, "$%02X", type);
    return hex;
}
