/* Resident routing identities. Zero means a probe error, never a fallback.
 * IDs 1 through MEDIA_COUNT participate in foreground browsing.
 * No plugin ABI values or AUX access are changed by these internal IDs. */
enum {
    V_ERROR, V_MUSIC, V_PT3, V_EXT, V_PACK, V_PAINT, V_DGR,
    V_FONT, V_LZ, V_PS, V_PURPLE, V_HEX, V_RAW, V_TEXT, V_AWP, V_RUN
};
#define MEDIA_COUNT V_PURPLE
static const char* const media_names[] = {
    0, /* V_ERROR: no viewer may be launched after a failed probe. */
    "MUSIC","PT3","EXTASIE","PACKFOT","PAINT816","DGRVIEW",
    "FONTVIEW","LZ4FH","PRINTSHOP","PURPLE","HEX","IMAGE","TEXT","AWP","RUN"
};
