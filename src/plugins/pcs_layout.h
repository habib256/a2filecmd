/* Shared PCS object bounds. Identification and preflight write MAIN only. */
static unsigned char pc_object_valid(unsigned char type,unsigned char color,unsigned char points,unsigned char length){
 return type>=1 && type<=10 && color<=16 && !(color&1) &&
        points>=3 && points<=64 && (unsigned int)length>=3U+2U*points;
}
