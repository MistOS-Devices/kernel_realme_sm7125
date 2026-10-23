# SPDX-License-Identifier: GPL-2.0
"""Verify production metadata allocation publishes the sender before spam checks."""
from test_helpers import function_body, run_c

run_c(r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>
#include <stdio.h>
#include <errno.h>
#define PAGE_SIZE 4096UL
#define PAGE_MASK (~(PAGE_SIZE-1))
#define PAGE_ALIGN(v) (((v)+PAGE_SIZE-1)&PAGE_MASK)
#define min(a,b) ((a)<(b)?(a):(b))
#define unlikely(x) (x)
#define BUG_ON(x) assert(!(x))
#define WARN_ON(x) assert(!(x))
#define ERR_PTR(e) ((void *)(intptr_t)(e))
#define binder_alloc_debug(...) ((void)0)
#define pr_err(...) ((void)0)
#define rb_entry(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
struct rb_node {struct rb_node *rb_left,*rb_right;};
struct rb_root {struct rb_node *rb_node;};
struct list_head {int unused;};
struct binder_buffer {struct rb_node rb_node;struct list_head entry;unsigned long user_data;size_t span;int free,allow_user_free,async_transaction,oneway_spam_suspect,pid;};
struct binder_alloc {struct rb_root free_buffers,allocated_buffers;size_t buffer_size,free_async_space;int pid;bool oneway_spam_detected;};
struct task {int tgid;};
static struct task sender={123};
#define current (&sender)
static size_t binder_alloc_buffer_size(struct binder_alloc *a,struct binder_buffer *b) {return b->span;}
static void list_add(struct list_head *n,struct list_head *head) {}
static void binder_insert_free_buffer(struct binder_alloc *a,struct binder_buffer *b) {assert(!"unexpected split");}
static void rb_erase(struct rb_node *n,struct rb_root *root) {assert(root->rb_node==n);root->rb_node=NULL;}
static void binder_insert_allocated_buffer_locked(struct binder_alloc *a,struct binder_buffer *b) {a->allocated_buffers.rb_node=&b->rb_node;}
static void binder_lru_freelist_del(struct binder_alloc *a,unsigned long lo,unsigned long hi) {}
static void debug_no_space_locked(struct binder_alloc *a) {}
static struct rb_node *rb_first(struct rb_root *root) {return root->rb_node;}
static struct rb_node *rb_next(struct rb_node *n) {return NULL;}
static bool debug_low_async_space_locked(struct binder_alloc *alloc)
''' + function_body('drivers/android/binder_alloc.c','debug_low_async_space_locked') + r'''
static void kfree(void *p) {free(p);}
static struct binder_buffer *binder_alloc_new_buf_locked(struct binder_alloc *alloc,struct binder_buffer *new_buffer,size_t size,int is_async)
''' + function_body('drivers/android/binder_alloc.c','binder_alloc_new_buf_locked') + r'''
int main(void) {

 for(int old_pid=0;old_pid<1000;old_pid+=999) {
  struct binder_buffer b={.user_data=4096,.span=300*1024,.free=1,.pid=old_pid};
  struct binder_alloc a={.free_buffers={&b.rb_node},.free_async_space=380*1024,.buffer_size=1024*1024};
  struct binder_buffer *next=calloc(1,sizeof(*next));
  assert(binder_alloc_new_buf_locked(&a,next,300*1024,1)==&b);
  assert(b.oneway_spam_suspect&&a.oneway_spam_detected&&b.pid==123&&a.free_async_space==80*1024);
 }
 puts("PASS: Binder spam accounting sees the current sender when a buffer is reused");
}
''')
