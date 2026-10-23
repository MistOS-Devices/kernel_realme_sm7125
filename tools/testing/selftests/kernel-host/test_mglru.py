# SPDX-License-Identifier: GPL-2.0
"""Exercise cold-advice admission against the production pagevec path."""
from test_helpers import function_body, run_c

run_c(r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
struct page { bool lru, active, unevictable, compound; int refs; };
struct pagevec { int count; } lru_deactivate_pvecs;
static bool enabled;
#define PageLRU(p) ((p)->lru)
#define PageActive(p) ((p)->active)
#define PageUnevictable(p) ((p)->unevictable)
#define PageCompound(p) ((p)->compound)
#define get_cpu_var(v) (v)
#define put_cpu_var(v) ((void)0)
static bool lru_gen_enabled(void) { return enabled; }
static void get_page(struct page *p) { p->refs++; }
static bool pagevec_add(struct pagevec *v, struct page *p) { v->count++; return true; }
static void lru_deactivate_fn(void) {}
static void pagevec_lru_move_fn(struct pagevec *v, void (*fn)(void), void *arg) {}
static void deactivate_page(struct page *page)
''' + function_body('mm/swap.c', 'deactivate_page') + r'''
int main(void) {
 struct page p = {.lru=true};
 enabled=true;
 deactivate_page(&p);
 assert(lru_deactivate_pvecs.count == 1 && p.refs == 1);
 p.unevictable=true;
 deactivate_page(&p);
 assert(lru_deactivate_pvecs.count == 1);
 p.unevictable=false; p.lru=false;
 deactivate_page(&p);
 assert(lru_deactivate_pvecs.count == 1);
 enabled=false; p.lru=true;
 deactivate_page(&p);
 assert(lru_deactivate_pvecs.count == 1);
 p.active=true;
 deactivate_page(&p);
 assert(lru_deactivate_pvecs.count == 2 && p.refs == 2);
 puts("PASS: cold advice queues evictable MGLRU pages and preserves classic filtering");
}
''')

run_c(r'''
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
struct mem_cgroup { int id; };
struct task_struct { int alloc_lock; };
struct mm_struct { struct task_struct *owner; struct { struct mem_cgroup *memcg; int list; } lru_gen; };
static bool disabled;
static int additions, deletions;
static struct mem_cgroup *destination;
#define lockdep_assert_held(p) ((void)0)
#define VM_BUG_ON_MM(x,mm) assert(!(x))
static bool mem_cgroup_disabled(void) { return disabled; }
static void rcu_read_lock(void) {}
static void rcu_read_unlock(void) {}
static bool list_empty(int *list) { return !*list; }
static struct mem_cgroup *mem_cgroup_from_task(struct task_struct *owner) { return destination; }
static void lru_gen_del_mm(struct mm_struct *mm) { deletions++; mm->lru_gen.memcg=NULL; }
static void lru_gen_add_mm(struct mm_struct *mm) { additions++; mm->lru_gen.memcg=destination; }
static void lru_gen_migrate_mm(struct mm_struct *mm)
''' + function_body('mm/vmscan.c', 'lru_gen_migrate_mm') + r'''
int main(void) {
 struct task_struct owner={0}; struct mem_cgroup old={0},new={1};
 struct mm_struct mm={.owner=&owner};
 destination=&new;
 lru_gen_migrate_mm(&mm);
 assert(!additions && !deletions);
 mm.lru_gen.memcg=&old; mm.lru_gen.list=1; disabled=true;
 lru_gen_migrate_mm(&mm);
 assert(!additions && !deletions);
 disabled=false; destination=&old;
 lru_gen_migrate_mm(&mm);
 assert(!additions && !deletions);
 destination=&new;
 lru_gen_migrate_mm(&mm);
 assert(additions==1 && deletions==1 && mm.lru_gen.memcg==&new);
 puts("PASS: MGLRU cgroup migration before mm addition and unchanged ownership");
}
''')

# These fixtures use real generation/LRU helpers, including runtime list conversion.
code = r'''
#pragma GCC diagnostic ignored "-Wsign-compare"
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#define BIT(n) (1UL << (n))
#define READ_ONCE(x) (x)
#define WRITE_ONCE(x,v) ((x)=(v))
#define VM_BUG_ON(x) assert(!(x))
#define VM_BUG_ON_PAGE(x,p) assert(!(x))
#define MAX_NR_GENS 4U
#define MAX_NR_ZONES 2
#define LRU_GEN_ANON 0
#define LRU_GEN_PGOFF 16
#define LRU_GEN_MASK (7UL << LRU_GEN_PGOFF)
#define LRU_REFS_MASK (3UL << 20)
#define LRU_REFS_FLAGS (BIT(PG_referenced) | BIT(PG_workingset))
#define MAX_LRU_BATCH 2
enum { PG_active, PG_referenced, PG_reclaim, PG_workingset, PG_unevictable,
       PG_swapcache, PG_dirty, PG_writeback, PG_lru };
enum lru_list { LRU_INACTIVE_ANON, LRU_ACTIVE_ANON, LRU_INACTIVE_FILE,
                LRU_ACTIVE_FILE, LRU_UNEVICTABLE };
#define LRU_ACTIVE 1
struct list_head { struct list_head *next, *prev; };
static void init_list(struct list_head *h) { h->next=h->prev=h; }
static bool list_empty(struct list_head *h) { return h->next == h; }
static void list_add(struct list_head *n, struct list_head *h) {
 n->next=h->next; n->prev=h; h->next->prev=n; h->next=n;
}
static void list_add_tail(struct list_head *n, struct list_head *h) { list_add(n,h->prev); }
static void list_del(struct list_head *n) { n->prev->next=n->next; n->next->prev=n->prev; }
struct page { unsigned long flags; bool file; int zone, pages; struct list_head lru; };
struct lru_gen_struct {
 unsigned long max_seq, min_seq[2]; bool enabled;
 long nr_pages[4][2][2]; struct list_head lists[4][2][2];
};
struct lruvec { struct lru_gen_struct lrugen; struct list_head lists[5]; long sizes[5]; };
#define PageActive(p) (!!((p)->flags & BIT(PG_active)))
#define PageReferenced(p) (!!((p)->flags & BIT(PG_referenced)))
#define PageUnevictable(p) (!!((p)->flags & BIT(PG_unevictable)))
#define PageSwapCache(p) (!!((p)->flags & BIT(PG_swapcache)))
#define PageReclaim(p) (!!((p)->flags & BIT(PG_reclaim)))
#define PageDirty(p) (!!((p)->flags & BIT(PG_dirty)))
#define PageWriteback(p) (!!((p)->flags & BIT(PG_writeback)))
#define PageLRU(p) (!!((p)->flags & BIT(PG_lru)))
#define PageTail(p) false
#define ClearPageActive(p) ((p)->flags &= ~BIT(PG_active))
#define ClearPageReferenced(p) ((p)->flags &= ~BIT(PG_referenced))
#define page_is_file_cache(p) ((p)->file)
#define page_zonenum(p) ((p)->zone)
#define hpage_nr_pages(p) ((p)->pages)
#define for_each_evictable_lru(l) for ((l)=0; (l)<LRU_UNEVICTABLE; (l)++)
#define for_each_gen_type_zone(g,t,z) for ((g)=0;(g)<4;(g)++) for ((t)=0;(t)<2;(t)++) for ((z)=0;(z)<2;(z)++)
#define is_file_lru(l) ((l)>=LRU_INACTIVE_FILE)
#define is_active_lru(l) ((l)&1)
#define lru_to_page(h) ((struct page *)((char *)(h)->prev - offsetof(struct page,lru)))
#define prefetchw_prev_lru_page(p,h,f) ((void)0)
#define PGDEACTIVATE 0
static int deactivated;
static bool enabled=true;
static bool lru_gen_enabled(void) { return enabled; }
static void __count_vm_events(int e,int n) { deactivated+=n; }
static void update_page_reclaim_stat(struct lruvec *v,int file,int rotated) {}
static unsigned long cmpxchg(unsigned long *p,unsigned long old,unsigned long new) {
 unsigned long actual=*p; if(actual==old)*p=new; return actual;
}
static void update_lru_size(struct lruvec *v,enum lru_list l,int z,int n) { v->sizes[l]+=n; }
'''
for path, signature, name in [
    ('include/linux/mm_inline.h', 'static enum lru_list page_lru(struct page *page)', 'page_lru'),
    ('include/linux/mm_inline.h', 'static int lru_gen_from_seq(unsigned long seq)', 'lru_gen_from_seq'),
    ('include/linux/mm_inline.h', 'static bool lru_gen_is_active(struct lruvec *lruvec,int gen)', 'lru_gen_is_active'),
    ('include/linux/mm_inline.h', 'static void lru_gen_update_size(struct lruvec *lruvec,struct page *page,int old_gen,int new_gen)', 'lru_gen_update_size'),
    ('include/linux/mm_inline.h', 'static bool lru_gen_add_page(struct lruvec *lruvec,struct page *page,bool reclaiming)', 'lru_gen_add_page'),
    ('include/linux/mm_inline.h', 'static bool lru_gen_del_page(struct lruvec *lruvec,struct page *page,bool reclaiming)', 'lru_gen_del_page'),
    ('include/linux/mm_inline.h', 'static void add_page_to_lru_list(struct page *page,struct lruvec *lruvec)', 'add_page_to_lru_list'),
    ('include/linux/mm_inline.h', 'static void del_page_from_lru_list(struct page *page,struct lruvec *lruvec)', 'del_page_from_lru_list'),
    ('mm/swap.c', 'static void lru_deactivate_fn(struct page *page,struct lruvec *lruvec,void *arg)', 'lru_deactivate_fn'),
    ('mm/vmscan.c', 'static int page_lru_gen(struct page *page)', 'page_lru_gen'),
    ('mm/vmscan.c', 'static bool fill_evictable(struct lruvec *lruvec)', 'fill_evictable'),
    ('mm/vmscan.c', 'static bool drain_evictable(struct lruvec *lruvec)', 'drain_evictable'),
]:
    code += signature + '\n' + function_body(path, name) + '\n'
run_c(code + r'''
int main(void) {
 struct lruvec v={.lrugen={.max_seq=7,.min_seq={4,4},.enabled=true}};
 for(int l=0;l<5;l++)init_list(&v.lists[l]);
 for(int g=0;g<4;g++)for(int t=0;t<2;t++)for(int z=0;z<2;z++)init_list(&v.lrugen.lists[g][t][z]);
 struct page p={.flags=BIT(PG_active)|BIT(PG_referenced)|BIT(PG_lru),.file=true,.zone=1,.pages=4};
 add_page_to_lru_list(&p,&v);
 assert(page_lru_gen(&p)==3 && !PageActive(&p));
 assert(v.lrugen.nr_pages[3][1][1]==4 && v.sizes[LRU_ACTIVE_FILE]==4);
 lru_deactivate_fn(&p,&v,NULL);
 assert(page_lru_gen(&p)==0 && !PageActive(&p) && !PageReferenced(&p));
 assert(v.lrugen.nr_pages[3][1][1]==0 && v.lrugen.nr_pages[0][1][1]==4);
 assert(v.sizes[LRU_ACTIVE_FILE]==0 && v.sizes[LRU_INACTIVE_FILE]==4 && deactivated==4);
 del_page_from_lru_list(&p,&v);
 assert(v.sizes[LRU_INACTIVE_FILE]==0 && v.lrugen.nr_pages[0][1][1]==0);
 /* Cold anonymous pages without a swap slot retain one extra generation. */
 p.file=false; p.flags=BIT(PG_lru); p.pages=1; p.zone=0;
 add_page_to_lru_list(&p,&v);
 assert(page_lru_gen(&p)==1 && v.sizes[LRU_INACTIVE_ANON]==1);
 del_page_from_lru_list(&p,&v);
 /* Convert more than one batch in each direction; unevictable pages stay put. */
 struct page pages[5];
 enabled=v.lrugen.enabled=false;
 for(int i=0;i<5;i++) {
  pages[i]=(struct page){.flags=BIT(PG_lru)|(i==4?BIT(PG_unevictable):0),.file=i&1,.pages=1};
  add_page_to_lru_list(&pages[i],&v);
 }
 assert(v.sizes[LRU_INACTIVE_ANON]==2 && v.sizes[LRU_INACTIVE_FILE]==2 && v.sizes[LRU_UNEVICTABLE]==1);
 enabled=v.lrugen.enabled=true;
 int batches=0; while(!fill_evictable(&v))batches++;
 assert(batches==2 && !list_empty(&v.lists[LRU_UNEVICTABLE]));
 for(int l=0;l<4;l++)assert(list_empty(&v.lists[l]));
 enabled=v.lrugen.enabled=false;
 batches=0; while(!drain_evictable(&v))batches++;
 assert(batches==2 && v.sizes[LRU_INACTIVE_ANON]==2 && v.sizes[LRU_INACTIVE_FILE]==2 && v.sizes[LRU_UNEVICTABLE]==1);
 for(int i=0;i<5;i++)del_page_from_lru_list(&pages[i],&v);
 for(int l=0;l<5;l++)assert(v.sizes[l]==0 && list_empty(&v.lists[l]));
 puts("PASS: MGLRU cold demotion, compound accounting and batched classic-list round trips");
}
''')
