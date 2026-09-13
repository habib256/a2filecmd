/* Publish an owned, closed and verified temporary file. Caller has bounded
 * paths, checked protections/identities and reserved the backup name.
 * FI_RENAME must refuse an existing destination, including on rollback.
 * No cleanup here: retain tmp on failure and backup after installation until
 * the caller's metadata/final checks pass. No overlay load or AUX access. */
#define FILE_INSTALL_FAILED 0
#define FILE_INSTALLED 1
#define FILE_RESTORE_FAILED 2
#ifdef FI_STATE
/* Resident callers may bind persistent state to avoid seven stacked argument
 * bytes. The fields must remain valid through the whole transaction. */
static unsigned char file_install(void)
#define FI_TMP FI_STATE->temp
#define FI_TARGET FI_STATE->target
#define FI_BACKUP FI_STATE->backup
#define FI_EXISTS FI_STATE->had_old
#else
static unsigned char file_install(const char* tmp, const char* target,
                                  const char* backup, unsigned char exists)
#define FI_TMP tmp
#define FI_TARGET target
#define FI_BACKUP backup
#define FI_EXISTS exists
#endif
{
    if (FI_EXISTS && FI_RENAME(FI_TARGET, FI_BACKUP)) return FILE_INSTALL_FAILED;
    if (FI_RENAME(FI_TMP, FI_TARGET)) {
        if (FI_EXISTS && FI_RENAME(FI_BACKUP, FI_TARGET)) return FILE_RESTORE_FAILED;
        return FILE_INSTALL_FAILED;
    }
    return FILE_INSTALLED;
}
#undef FI_RENAME
#undef FI_STATE
#undef FI_TMP
#undef FI_TARGET
#undef FI_BACKUP
#undef FI_EXISTS
