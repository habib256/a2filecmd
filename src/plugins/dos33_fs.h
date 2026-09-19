/* dos33_fs.h -- one DOS 3.3 volume, read and written the same way by the
 * overlays that touch one: DOSWRITE (copy a ProDOS file in), DOSIMAGE (the
 * same inside a disk image) and DOS33W (delete, rename, replace).
 *
 * Two builds from the same lines. Without DOS_IMAGE the sectors come from a
 * real Disk II through READ_BLOCK/WRITE_BLOCK, two DOS sectors to a ProDOS
 * block, in the DOS 3.3 physical order; with it they come from a file the
 * caller opened, at image_base. Every write is read back before the next
 * one, and a physical write is never retried: a second attempt on a drive
 * that has already failed is how a neighbouring sector gets destroyed.
 *
 * audit() is the gate in front of every write. It walks the whole catalog
 * and every track/sector list, locked files included, and refuses the
 * volume on anything it cannot explain: a VTOC that is not a VTOC, a boot
 * track or a catalog track marked free, a catalog chain that loops, a link
 * off the disk, a sector claimed twice, a live sector marked free in the
 * bitmap, a sector count that disagrees with the chain. A disk we do not
 * fully understand is a disk we do not write to.
 *
 * With DOS33_FIND the same walk also looks for one entry. With a
 * `want_track` of its own it looks for it by `want_track`/`want_sector`,
 * the first track/sector list -- not by name. The panel shows a DOS name
 * made into a ProDOS one (lower case raised, anything but a letter or a
 * digit turned into a period, fifteen characters at most, a letter forced
 * first), so several DOS files can appear under one panel name and none of
 * them can be found back by it. The link is exact, and unique: two entries
 * sharing it would have failed claim() and the volume with it.
 * `hit_cat`/`hit_slot` say where the entry is, `hit_type` what it is and
 * `hit_count` how many sectors it claims. `name_taken` says whether some
 * OTHER entry already carries `name`, which is what a rename must refuse.
 * With `want_track` left at zero it looks for `name` instead, which is what
 * replacing a file wants: the copy coming in knows the name it must take
 * over, not where that file happens to live. Zero is free as a sentinel --
 * a live entry never starts on track 0, the boot track.
 *
 * Without DOS33_FIND, a name already present simply refuses the volume,
 * which is what a copy creating a new name wants.
 */

/* DOS bitmap: sectors 0..7 in the second byte, 8..15 in the first. */
static unsigned char mask(unsigned int s) { return 1U<<(s&7); }
static unsigned int bitpos(unsigned int s) {return 0x38+(s/16)*4+((s&15)<8);}
static unsigned char free_sector(unsigned int s) {return vtoc[bitpos(s)]&mask(s);}

#ifdef DOS_IMAGE
static unsigned char read_sector(unsigned int s,unsigned char* out) {
 return s<560 && !RF(fseek)(image,image_base+(unsigned long)s*256,SEEK_SET) &&
  RF(fread)(out,1,256,image)==256 && !ferror(image);
}
#else
static const unsigned char order[16]={0,14,13,12,11,10,9,8,7,6,5,4,3,2,1,15};
static unsigned char read_sector(unsigned int s,unsigned char* out) {
 unsigned char code=order[s&15];
 if(s>=560 || readblk(unit,(s/16)*8+(code>>1),buf))return 0;
 RF(memcpy)(out,buf+((code&1)?256:0),256);return 1;
}
#endif
/* Read-modify-write preserves the neighbouring DOS sector. Verify all 512
 * bytes, including that neighbour; never retry a failed physical write. */
static unsigned char write_sector(unsigned int s,const unsigned char* in) {
#ifdef DOS_IMAGE
  if(stop() || s>=560 || RF(fseek)(image,image_base+(unsigned long)s*256,SEEK_SET) ||
     RF(fwrite)(in,1,256,image)!=256 || ferror(image))return 0;
  return read_sector(s,verify) && !memcmp(in,verify,256);
#else
 unsigned char code=order[s&15];unsigned int block=(s/16)*8+(code>>1);
 unsigned char *ours,*twin;
 if(stop() || dw_protected(unit) || readblk(unit,block,buf))return 0;
 /* Half of the block belongs to another DOS sector and must come back
  * unchanged. Keeping that half, 256 bytes, says as much as keeping the
  * whole block did and leaves 256 bytes to a window that needed them:
  * what was written is compared with `in`, the neighbour with its copy. */
 ours=buf+((code&1)?256:0);twin=buf+((code&1)?0:256);
 RF(memcpy)(verify,twin,256);
 RF(memcpy)(ours,in,256);
 if(writeblk(unit,block,buf) || readblk(unit,block,buf))return 0;
 return !memcmp(ours,in,256) && !memcmp(twin,verify,256);
#endif
}
#ifdef DOS33_FIND
static unsigned char mine;              /* the walk is inside the found entry */
#endif
static unsigned char claim(unsigned int s) {
 if(s<48 || s>=560 || s/16==17 || free_sector(s) || (seen[s>>3]&mask(s)))return 0;
 seen[s>>3]|=mask(s);
#ifdef DOS33_FIND
 /* Marked here, where the byte and the bit are already in hand: done in
  * the two loops of the walk instead, it cost 169 bytes. */
 if(mine)victim[s>>3]|=mask(s);
#endif
 return 1;
}
/* Complete catalog and T/S walk, including locked files. Cross-links, loops,
 * bad links/offsets, live sectors marked free and inconsistent counts forbid
 * all writes. T/S lists describe successive groups of 122 logical sectors. */
static unsigned char audit(void) {
 unsigned char c,next,j,k,t,s;unsigned int cats=0,cur,count,want,logical;
#ifdef DOS33_FIND
 hit_cat=0;hit_slot=0;hit_type=0;hit_count=0;name_taken=0;
 a.memset(victim,0,sizeof victim);
#endif
 catsector=0;a.memset(seen,0,sizeof seen);
 if(!read_sector(272,vtoc) || vtoc[3]<1 || vtoc[3]>3 || vtoc[1]!=17 ||
    !vtoc[2] || vtoc[2]>15 || vtoc[0x27]!=122 || vtoc[0x34]!=35 ||
    vtoc[0x35]!=16 || rd16(vtoc+0x36)!=256)return 0;
 /* Reserve boot tracks and the entire catalog track even on a dubious
  * bitmap. Two bytes of the map answer for a whole track, so four tracks
  * are eight bytes: the question used to be asked 560 times, each with a
  * division by sixteen inside free_sector and another inside bitpos. */
 for(j=0;j<4;++j) {
  k=(j<3)?j:17;
  if(vtoc[0x38+k*4] || vtoc[0x39+k*4])return 0;
 }
 c=vtoc[2];
 while(c) {
  if(c>15 || (cats&(1U<<c)) || !read_sector(272+c,cat))return 0;
  cats|=1U<<c;
  next=cat[2];if(cat[1]!=(next?17:0))return 0;
  for(j=0;j<7;++j) {
   unsigned char* e=cat+11+j*35;
   if(!e[0] || e[0]==255) {if(!catsector){catsector=c;slot=j;}continue;}
#ifdef DOS33_FIND
   mine=want_track?(e[0]==want_track && e[1]==want_sector):!memcmp(e+3,name,30);
   if(mine) {
    if(hit_cat)return 0;              /* the same file twice: not ours to sort out */
    hit_cat=c;hit_slot=j;hit_type=e[2];hit_count=rd16(e+33);
   } else if(!memcmp(e+3,name,30))name_taken=1;
#else
   if(!memcmp(e+3,name,30))return 0;
#endif
   t=e[0];s=e[1];want=rd16(e+33);count=logical=0;
   while(t) {
    cur=(unsigned int)t*16+s;
    if(s>=16 || !claim(cur) || !read_sector(cur,ts))return 0;
    if(rd16(ts+5)!=logical)return 0;
    logical+=122;
    ++count;t=ts[1];s=ts[2];if(!t && s)return 0;
    /* Indexed, not walked with a pointer: the pointer form measures 26
     * bytes more here, whatever it does in free_chain. */
    for(k=0;k<122;++k) {
     unsigned char dt=ts[12+2*k],ds=ts[13+2*k];
     if(!dt){if(ds)return 0;continue;}
     if(ds>=16 || !claim((unsigned int)dt*16+ds))return 0;
     ++count;
    }
   }
   if(count!=want)return 0;
  }
  c=next;
 }
#ifdef DOS33_FIND
 return 1;                            /* a full catalog is still a good volume */
#else
 return catsector!=0;
#endif
}
#ifdef DOS33_FIND
/* Every sector the found entry owns, back to the bitmap. audit() collected
 * them in `victim` during the one walk it makes; walking the chain again
 * instead cost 330 bytes of code for 70 of map. */
static void free_victim(void) {
 unsigned int s;
 for(s=48;s<560;++s)if(victim[s>>3]&mask(s))vtoc[bitpos(s)]|=mask(s);
}
#endif
