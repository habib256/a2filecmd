/* One walk for the three tree operations, without recursion. The level
 * being visited is lv_base/lv_n/lv_i[d] (its entries in the pool, their
 * number, the one in hand); a directory entry lists its contents right
 * after the current level's and pushes a frame, a finished level pops its
 * frame and its "/name" from the paths. Refuses, without a message in
 * WALK_COUNT, a tree that overflows the pool, the path or TREE_DEPTH:
 * 0xFFFF, before any write for the callers that count first. Otherwise
 * WALK_COUNT returns the number of files (directories excluded); WALK_COPY
 * copies the contents of `full` into `other_full`, which exists,
 * subdirectories included (one already present is filled in, not
 * recreated); WALK_DELETE removes each file, then the directory, and adds
 * every level's entries to progress_total as it is discovered. These two
 * return 1, or 0 once an error has been reported or Escape pressed. */
enum { WALK_COUNT, WALK_COPY, WALK_DELETE };
static unsigned char walk_mode;
static unsigned char push_paths(const char* name)
{
    return push_name(full, name) && (walk_mode != WALK_COPY || push_name(other_full, name));
}
static void pop_paths(void)
{
    pop_name(full);
    if (walk_mode == WALK_COPY) pop_name(other_full);
}
static unsigned int walk_tree(unsigned char mode)
{
    unsigned char d = 0, i, n, dir;
    const struct Mini* m;
    unsigned int files = 0;
    walk_mode = mode;
    if (!list_dir(full, 0, &n)) goto unreadable;
    lv_base[0] = 0; lv_n[0] = n; lv_i[0] = 0;
    if (mode == WALK_DELETE) progress_total += n;
    for (;;) {
        i = lv_i[d];
        if (i >= lv_n[d]) {                       /* this level is done */
            if (mode == WALK_DELETE) {
                if (rmdir(full)) { report_error("Delete"); return 0; }
                ++a2fc_ops; ++progress_done;
            }
            if (!d) break;
            --d;
            pop_paths();
            ++lv_i[d];
            continue;
        }
        m = pool + lv_base[d] + i;
        dir = m->type == 0x0F;
        if (mode == WALK_COUNT) {
            if (!dir) { ++files; ++lv_i[d]; continue; }
        } else {
            if (mode == WALK_DELETE) progress_bar(m->name, progress_done, progress_total);
            if (abort_key()) return 0;
        }
        if (!push_paths(m->name)) {
            if (mode != WALK_COUNT) too_long();
            return dir ? 0xFFFF : 0;
        }
        if (dir) {                                /* its entries follow this level's in the pool */
            if (d + 1 >= TREE_DEPTH) goto unreadable;
            if (mode == WALK_COPY && !exists(other_full) && mkdir(other_full)) { report_error("Mkdir"); return 0; }
            n = lv_base[d] + lv_n[d];
            if (!list_dir(full, n, &i)) goto unreadable;
            ++d;
            lv_base[d] = n; lv_n[d] = i; lv_i[d] = 0;
            if (mode == WALK_DELETE) progress_total += i;
            continue;
        }
        if (mode == WALK_COPY) { if (!copy_file(m->name, m->type, m->aux)) return 0; }
        else if (remove(full)) { report_error("Delete"); return 0; }
        else { ++a2fc_ops; ++progress_done; }
        pop_paths();
        ++lv_i[d];
    }
    return mode == WALK_COUNT ? files : 1;
unreadable:
    if (mode != WALK_COUNT) dir_fail();
    return 0xFFFF;
}
