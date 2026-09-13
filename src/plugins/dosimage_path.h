/* Rebuild after each overlay load (the loader uses other_full). */
#define image_temp a.other_full
static unsigned char image_path(void) {
 unsigned char n=RF(strlen)(other->path);
 if(n>=PATH_LEN || n!=other->img_len)return 0;
 while(n && other->path[n]!='/')--n;
 if(!n || n+10>=PATH_LEN)return 0;
 RF(memcpy)(image_temp,other->path,n+1);RF(strcpy)(image_temp+n+1,"A2FC.DOS");return 1;
}
