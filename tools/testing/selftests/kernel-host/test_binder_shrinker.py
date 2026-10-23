# SPDX-License-Identifier: GPL-2.0
"""Exercise production shrinker lock order, VMA checks and all cleanup paths."""
from test_helpers import function_body, run_c

run_c(r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#define PAGE_SIZE 4096
#define container_of(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
#define trace_binder_unmap_kernel_start(...) ((void)0)
#define trace_binder_unmap_kernel_end(...) ((void)0)
#define trace_binder_unmap_user_start(...) ((void)0)
#define trace_binder_unmap_user_end(...) ((void)0)
typedef int spinlock_t;
struct list_head {int unused;};
struct list_lru_one {int unused;};
struct page {int unused;};
struct mm_struct {int mmap_sem;};
struct vm_area_struct {unsigned long vm_start;};
struct binder_alloc;
struct binder_lru_page {struct list_head lru;struct page *page_ptr;struct binder_alloc *alloc;};
struct binder_alloc {spinlock_t lock;struct mm_struct *vma_vm_mm;struct vm_area_struct *vma;struct binder_lru_page *pages;unsigned long buffer;};
enum lru_status {LRU_SKIP,LRU_REMOVED_RETRY};
static bool list_held,alloc_held,mmap_held,mm_alive=true,mmap_busy,alloc_busy;
static int refs,frees,zaps,isolates;
static spinlock_t list_lock;
static struct vm_area_struct *found_vma;
static struct binder_alloc *active;
static bool mmget_not_zero(struct mm_struct *mm) {assert(list_held&&!alloc_held&&!mmap_held);if(!mm_alive)return false;refs++;return true;}
static void mmput_async(struct mm_struct *mm) {assert(!alloc_held&&!mmap_held&&refs==1);refs--;}
static bool down_read_trylock(int *l) {assert(!alloc_held&&!mmap_held&&refs==1);if(mmap_busy)return false;mmap_held=true;return true;}
static void up_read(int *l) {assert(mmap_held&&!alloc_held);mmap_held=false;}
static bool spin_trylock(spinlock_t *l) {assert(l==&active->lock&&mmap_held&&!alloc_held);if(alloc_busy)return false;alloc_held=true;return true;}
static void spin_unlock(spinlock_t *l) {
 if(l==&list_lock){assert(list_held&&!alloc_held);list_held=false;}
 else{assert(l==&active->lock&&alloc_held);alloc_held=false;}
}
static void spin_lock(spinlock_t *l) {assert(l==&list_lock&&!list_held&&!alloc_held&&!mmap_held);list_held=true;}
static struct vm_area_struct *find_vma(struct mm_struct *mm,unsigned long addr) {assert(mmap_held&&alloc_held);return found_vma;}
static struct vm_area_struct *binder_alloc_get_vma(struct binder_alloc *a) {return a->vma;}
static void list_lru_isolate(struct list_lru_one *l,struct list_head *item) {assert(list_held&&alloc_held&&mmap_held);isolates++;}
static void zap_page_range(struct vm_area_struct *v,unsigned long addr,unsigned long len) {assert(!list_held&&!alloc_held&&mmap_held&&len==PAGE_SIZE);zaps++;}
static void __free_page(struct page *p) {assert(p&&!list_held&&!alloc_held&&!mmap_held&&!refs);frees++;}
enum lru_status binder_alloc_free_page(struct list_head *item,struct list_lru_one *lru,spinlock_t *lock,void *cb_arg)
''' + function_body('drivers/android/binder_alloc.c','binder_alloc_free_page') + r'''
int main(void) {
 struct mm_struct mm={0};struct page p={0};struct vm_area_struct v={.vm_start=4096},other={.vm_start=4096};
 struct binder_lru_page page;struct binder_alloc a={.vma_vm_mm=&mm,.vma=&v,.pages=&page,.buffer=4096};
 struct list_lru_one lru={0};active=&a;
 for(int scenario=0;scenario<8;scenario++) {
  page.alloc=&a;page.page_ptr=&p;found_vma=&v;list_held=true;
  mm_alive=scenario!=0;mmap_busy=scenario==1;alloc_busy=scenario==2;
  if(scenario==3)page.page_ptr=NULL;
  if(scenario==4)found_vma=&other;
  if(scenario==5){other.vm_start=8192;found_vma=&other;}
  if(scenario==6)found_vma=NULL;
  frees=zaps=isolates=0;
  enum lru_status ret=binder_alloc_free_page(&page.lru,&lru,&list_lock,NULL);
  assert(list_held&&!alloc_held&&!mmap_held&&!refs);
  if(scenario<5)assert(ret==LRU_SKIP&&!frees&&!zaps&&!isolates);
  else assert(ret==LRU_REMOVED_RETRY&&frees==1&&isolates==1&&!page.page_ptr&&zaps==(scenario==7));
 }
 puts("PASS: Binder shrinker takes mmap before allocator lock and unmaps/frees unlocked with balanced cleanup");
}
''')
