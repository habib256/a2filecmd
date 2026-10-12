/* The supported DPC profile has 560 columns and 192 rows. */
static unsigned char dg_point_valid(unsigned int x,unsigned char y){
 return x<560 && y<192;
}
