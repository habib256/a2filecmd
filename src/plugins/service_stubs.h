/* Compact direct service stubs keep protection code below the track buffer.
 * The final argument is 16 bits in every stub; trampoline restores A/X. */
#ifndef PLUGIN_HOST
#include <stddef.h>
#pragma optimize(push, off)
static void service_tramp(void) {
    asm("sta tmp1"); asm("stx tmp2"); asm("jsr incsp2");
    asm("lda #<%v", SERVICE_API); asm("sta ptr1");
    asm("lda #>%v", SERVICE_API); asm("sta ptr1+1");
    asm("lda (ptr1),y"); asm("sta jmpvec+1");
    asm("iny"); asm("lda (ptr1),y"); asm("sta jmpvec+2");
    asm("lda tmp1"); asm("ldx tmp2"); asm("jmp jmpvec");
}
#define SERVICE(field) { asm("ldy #%b", offsetof(struct A2fcApi, field)); asm("jmp %v", service_tramp); }
static FILE* __fastcall__ r_fopen(const char* p, const char* mode) SERVICE(fopen)
static int __fastcall__ r_fclose(FILE* f) SERVICE(fclose)
static size_t __fastcall__ r_fread(void* p, size_t s, size_t n, FILE* f) SERVICE(fread)
static size_t __fastcall__ r_fwrite(const void* p, size_t s, size_t n, FILE* f) SERVICE(fwrite)
static int __fastcall__ r_fseek(FILE* f, long off, int origin) SERVICE(fseek)
static unsigned char __fastcall__ r_mli(unsigned char cmd, void* p) SERVICE(mli)
static int __fastcall__ r_remove(const char* p) SERVICE(remove)
static char* __fastcall__ r_strcpy(char* d, const char* s) SERVICE(strcpy)
static int __fastcall__ r_strcmp(const char* a, const char* b) SERVICE(strcmp)
static size_t __fastcall__ r_strlen(const char* p) SERVICE(strlen)
static void* __fastcall__ r_memcpy(void* d, const void* s, size_t n) SERVICE(memcpy)
static unsigned char __fastcall__ r_confirm(const char* p) SERVICE(confirm)
static void __fastcall__ r_message(const char* p) SERVICE(message)
#pragma optimize(pop)
#define RF(name) r_##name
#else
#define RF(name) SERVICE_API.name
#endif
