/* Resident routing identities. Zero means a probe error, never a fallback.
 * IDs 1 through MEDIA_COUNT participate in foreground browsing.
 * No plugin ABI values or AUX access are changed by these internal IDs. */
enum {
    V_ERROR, V_MUSIC, V_PT3, V_DUET, V_EXT, V_PACK, V_PAINT, V_DGR,
    V_FONT, V_LZ, V_PS, V_NEWS, V_PURPLE, V_ARL, V_MAC, V_GM, V_HEX, V_RAW, V_TEXT, V_AWP, V_AWD, V_UNWRAP, V_SCII, V_SHAPES,
    V_UNSQ, V_BASLIST, V_RUN, V_DOC, V_VISI
};
#define MEDIA_COUNT V_GM
/* Out of MAIN, which has no room left for the name. */
#if defined(__CC65__) && !defined(__SIM6502__) && !defined(__SIM65C02__)
#pragma rodata-name (push, "LC")
#endif
static const char media_visicalc[] = "VISICALC";
static const char media_gmagic[] = "GMAGIC";
#if defined(__CC65__) && !defined(__SIM6502__) && !defined(__SIM65C02__)
#pragma rodata-name (pop)
#endif
/* Not static: open.s's open_entry reads it. */
const char* const media_names[] = {
    0, /* V_ERROR: no viewer may be launched after a failed probe. */
    "MUSIC","PT3","DUET","EXTASIE","PACKFOT","PAINT816","DGRVIEW",
    "FONTVIEW","LZ4FH","PRINTSHOP","NEWSROOM","PURPLE","ARLEQUIN","MACPAINT", media_gmagic /* "GMAGIC" */,"HEX","IMAGE","TEXT","AWP","AWDATA","UNWRAP","SCIIBIN","SHAPES",
    "UNSQ","BASLIST","RUN","DOCVIEW", media_visicalc /* "VISICALC" */
};
