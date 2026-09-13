/* Image transaction around DOSWRITE. No AUX access. */
#define UTIL_STUBS
#define UTIL_INFO
#define UTIL_CREATE
#include "util.h"
#include <string.h>
void __fastcall__ plugin_entry(const struct A2fcApi*);
struct Header { unsigned int magic; unsigned char flags;
 void __fastcall__ (*entry)(const struct A2fcApi*); unsigned char r[3]; char desc[52]; };
#ifndef PLUGIN_HOST
#pragma rodata-name(push,"OVLHDR")
#endif
const struct Header __plugin_header={PLUGIN_MAGIC,OVERLAY_BIG,plugin_entry,{0,0,0},
 "Prepare and safely install a DOS 3.3 image copy"};
#ifndef PLUGIN_HOST
#pragma rodata-name(pop)
#endif
static FILE* source;
static unsigned char verify[256];
#include "dosimage_path.h"
#include "dosimage_io.h"
void __fastcall__ plugin_entry(const struct A2fcApi* api) {
 init(api);source=NULL;
 if(pan->fs || other->fs!=FS_DOS33 || !other->img_len || !image_path()) {
  a.input[0]=0;note("Use C with a DOS 3.3 image opposite.");return;
 }
 RF(strcpy)(a.reselect,a.selected->name);
 if(a.arg=='P') {a.input[0]=0;image_prepare();}
 else if(a.arg=='F' || a.arg=='X')image_finish();
 else note("Use C to copy into the opposite DOS image.");
}
