/* Exclusive ProDOS reservation shared by service overlays.
 * FC_PATH is a borrowed Pascal-path buffer; FC_PREPARE fills it from path.
 * RF selects the caller's API/stubs. No overlay load or AUX access.
 * Caller bounds path before entry. All state is set even with dirty BSS.
 * Zero alone grants ownership: only then may the caller open wb or clean up.
 * Any nonzero MLI error (including collision) leaves existing files alone.
 * Creation is not proof of written/closed/verified contents.
 * FC_ACCESS, $C3 unless the caller says otherwise, is the initial access
 * (GOTO keeps $E3, its backup bit set). */
#ifndef FC_ACCESS
#define FC_ACCESS 0xC3
#endif
struct Create { unsigned char n; unsigned char* path; unsigned char access,type;
    unsigned int aux; unsigned char storage; unsigned int date,time; };
static struct Create create;
static unsigned char newfile(const char* path,unsigned char type,unsigned int aux,unsigned char storage) {
    FC_PREPARE(path); create.n=7; create.path=FC_PATH; create.access=FC_ACCESS; create.type=type;
    create.aux=aux; create.storage=storage; create.date=create.time=0;
    return RF(mli)(0xC0,&create);
}
#undef FC_PATH
#undef FC_PREPARE
#undef FC_ACCESS
