/* Shared Movie Maker bitmap bounds; MAIN scalars only. */
static unsigned char mv_plane_valid(unsigned int length,unsigned int start){
 return length>=2 && length<=8194 && start<=8192 && length-2<=8192-start;
}
