#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Check VMA exclusions and the production active-to-inactive LRU move."""
from test_helpers import function_body, run_c

run_c(r'''
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#define VM_LOCKED 1
#define VM_HUGETLB 2
#define VM_PFNMAP 4
#define LRU_ACTIVE 2
#define PGDEACTIVATE 0
struct vm_area_struct { unsigned long vm_flags; };
struct page { bool lru, active, unevictable, referenced, file; int pages; };
struct lruvec { int active, inactive; };
static int events, reclaim_updates;
#define PageLRU(p) ((p)->lru)
#define PageActive(p) ((p)->active)
#define PageUnevictable(p) ((p)->unevictable)
#define ClearPageActive(p) ((p)->active = false)
#define ClearPageReferenced(p) ((p)->referenced = false)
#define hpage_nr_pages(p) ((p)->pages)
static int page_is_file_cache(struct page *p) { return p->file; }
static int page_lru_base_type(struct page *p) { return p->file; }
static void del_page_from_lru_list(struct page *p, struct lruvec *v, int lru) {
    assert(lru == page_lru_base_type(p) + LRU_ACTIVE); v->active -= p->pages;
}
static void add_page_to_lru_list(struct page *p, struct lruvec *v, int lru) {
    assert(lru == page_lru_base_type(p)); v->inactive += p->pages;
}
static void __count_vm_events(int type, int pages) { events += pages; }
static void update_page_reclaim_stat(struct lruvec *v, int file, int rotated) {
    reclaim_updates++;
}
static bool can_madv_lru_vma(struct vm_area_struct *vma)
''' + function_body('mm/madvise.c', 'can_madv_lru_vma') + r'''
static void lru_deactivate_fn(struct page *page, struct lruvec *lruvec, void *arg)
''' + function_body('mm/swap.c', 'lru_deactivate_fn') + r'''
int main(void) {
    for (int flags = 0; flags < 8; flags++) {
        struct vm_area_struct vma = {flags};
        assert(can_madv_lru_vma(&vma) == (flags == 0));
    }
    for (int file = 0; file < 2; file++) {
        struct page p = {true, true, false, true, file, 4};
        struct lruvec v = {4, 0};
        lru_deactivate_fn(&p, &v, NULL);
        assert(!p.active && !p.referenced && v.active == 0 && v.inactive == 4);
        lru_deactivate_fn(&p, &v, NULL);
        assert(v.active == 0 && v.inactive == 4);
    }
    for (int kind = 0; kind < 3; kind++) {
        struct page p = {kind != 0, kind != 1, kind == 2, true, false, 1};
        struct lruvec v = {1, 0};
        lru_deactivate_fn(&p, &v, NULL);
        assert(p.referenced && v.active == 1 && v.inactive == 0);
    }
    assert(events == 8 && reclaim_updates == 2);
    puts("PASS: reclaim advice excludes locked/special VMAs and deactivates eligible LRU pages");
}
''')
