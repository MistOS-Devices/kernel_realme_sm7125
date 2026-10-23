# SPDX-License-Identifier: GPL-2.0
"""Keep optional inactive-only reclaim from selecting hot MGLRU pages."""
from test_helpers import ROOT, run_c

source = (ROOT / 'mm/process_mm_reclaim.c').read_text()
start = source.index('if (rp->inactive_lru')
end = source.index('\n\t\t/*\n\t\t * MADV_FREE', start)
run_c(r'''
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
struct page { bool active, unevictable, hot, lru; };
struct reclaim_param { bool inactive_lru; };
#define PageActive(p) ((p)->active)
#define PageUnevictable(p) ((p)->unevictable)
static int isolate_lru_page(struct page *p) { p->active=p->hot; p->lru=false; return 0; }
static void putback_lru_page(struct page *p) { p->lru=true; }
static int scan(struct page *pages, struct reclaim_param *rp) {
 int taken=0;
 for (int i=0;i<2;i++) {
  struct page *page=&pages[i];
''' + source[start:end] + r'''
  taken++;
 }
 return taken;
}
int main(void) {
 struct page pages[2]={{.hot=true,.lru=true},{.hot=false,.lru=true}};
 struct reclaim_param rp={.inactive_lru=true};
 assert(scan(pages,&rp)==1 && pages[0].lru && !pages[1].lru);
 rp.inactive_lru=false; pages[0].active=false;
 assert(scan(pages,&rp)==2);
 puts("PASS: inactive-only process reclaim preserves young generation pages");
}
''')
