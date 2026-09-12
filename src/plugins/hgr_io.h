/* Compact service calls; A is the entry API pointer. */
#include <stddef.h>
#ifndef PLUGIN_HOST
#pragma optimize (push, off)
static void tramp(void)
{
    asm("sta tmp1");
    asm("stx tmp2");
    asm("jsr incsp2");              /* the argument the stub's prologue pushed */
    asm("lda %v", A);
    asm("sta ptr1");
    asm("lda %v+1", A);
    asm("sta ptr1+1");
    asm("lda (ptr1),y");
    asm("sta jmpvec+1");
    asm("iny");
    asm("lda (ptr1),y");
    asm("sta jmpvec+2");
    asm("lda tmp1");
    asm("ldx tmp2");
    asm("jmp jmpvec");
}
#define STUB(field) { asm("ldy #%b", offsetof(struct A2fcApi, field)); asm("jmp %v", tramp); }
static char* __fastcall__ scpy(char* d, const char* s) STUB(strcpy)
static FILE* __fastcall__ fopn(const char* path, const char* mode) STUB(fopen)
static unsigned int __fastcall__ frd(void* p, unsigned int sz, unsigned int n, FILE* f) STUB(fread)
static int __fastcall__ fcls(FILE* f) STUB(fclose)
static char __fastcall__ getkey(unsigned int unused) STUB(media_wait)
#pragma optimize(pop)
#else
#define scpy A->strcpy
#define fopn A->fopen
#define frd A->fread
#define fcls A->fclose
#define getkey(unused) A->media_wait()
#endif
