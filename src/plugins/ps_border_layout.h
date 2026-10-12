/* Print Shop border profiles shared by identification and the reader.
 * No writes; only exact physical lengths qualify, never panel estimates. */
static unsigned char ps_border_layout(unsigned int aux,unsigned int length,unsigned char modern){
 if(modern)return aux==0x2000 && length==264;
 return (aux&0xCFFF)==0x4800 && (length==144 || length==148);
}
