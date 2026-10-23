# SPDX-License-Identifier: GPL-2.0
"""Exercise allocator admission, page-install locking and failure cleanup."""
import re
from test_helpers import ROOT, function_body, run_c

source = (ROOT / 'drivers/android/binder_alloc.c').read_text()
match = re.search(r'struct binder_buffer \*binder_alloc_new_buf\([^{};]*\)', source)
signature = match.group()
helper = ('static size_t sanitized_size(size_t data_size, size_t offsets_size, size_t extra_buffers_size)\n'
          + function_body('drivers/android/binder_alloc.c', 'sanitized_size')
          if 'size_t sanitized_size(' in source else '')
call = 'binder_alloc_new_buf(&a,16,8,0,1' + (',123' if 'int pid' in signature else '') + ')'
run_c(r'''
#include <assert.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <errno.h>
#define ALIGN(v,a) (((v)+(a)-1)&~((a)-1))
#define max(a,b) ((a)>(b)?(a):(b))
#define unlikely(x) (x)
#define ERR_PTR(e) ((void *)(intptr_t)(e))
#define PTR_ERR(p) ((intptr_t)(p))
#define IS_ERR(p) ((uintptr_t)(p)>=(uintptr_t)-4095)
#define GFP_KERNEL 0
#define binder_alloc_debug(...) ((void)0)
struct binder_alloc { int mutex,lock,pid; };
struct binder_buffer { size_t data_size,offsets_size,extra_buffers_size; int pid; };
struct task { int tgid; } task={123};
#define current (&task)
static bool held, mapped=true, metadata_fail, buffer_fail;
static int installs,frees,install_error;
static struct binder_buffer result,next;
static void acquire(int *lock) { assert(!held); held=true; }
static void release(int *lock) { assert(held); held=false; }
#define mutex_lock acquire
#define mutex_unlock release
#define spin_lock acquire
#define spin_unlock release
static void *binder_alloc_get_vma(struct binder_alloc *a) { return mapped?&task:NULL; }
static void *kzalloc(size_t size,int flags) { assert(!held); return metadata_fail?NULL:&next; }
static void kfree(void *p) { assert(!held); }
static struct binder_buffer *binder_alloc_new_buf_locked(struct binder_alloc *a,...) {
 assert(held); return buffer_fail?ERR_PTR(-ENOSPC):&result;
}
static int binder_install_buffer_pages(struct binder_alloc *a,struct binder_buffer *b,size_t size) {
 assert(!held && size==24); installs++; return install_error;
}
static void binder_alloc_free_buf(struct binder_alloc *a,struct binder_buffer *b) { assert(!held && b==&result); frees++; }
''' + helper + '\n' + signature + '\n' + function_body('drivers/android/binder_alloc.c', 'binder_alloc_new_buf') + r'''
int main(void) {
 struct binder_alloc a={0}; struct binder_buffer *b;
 b=''' + call + r''';
 assert(b==&result && installs==1 && !frees && !held);
 install_error=-ENOMEM;
 b=''' + call + r''';
 assert(PTR_ERR(b)==-ENOMEM && installs==2 && frees==1 && !held);
 install_error=0; buffer_fail=true;
 b=''' + call + r''';
 assert(PTR_ERR(b)==-ENOSPC && installs==2 && frees==1 && !held);
 buffer_fail=false; metadata_fail=true;
 b=''' + call + r''';
 assert(PTR_ERR(b)==-ENOMEM && installs==2 && !held);
 metadata_fail=false; mapped=false;
 b=''' + call + r''';
 assert(PTR_ERR(b)==-ESRCH && installs==2 && !held);
 puts("PASS: Binder page installation runs unlocked and failures release allocated buffers");
}
''')

run_c(r'''
#include <assert.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#define ALIGN(v,a) (((v)+(a)-1)&~((a)-1))
#define max(a,b) ((a)>(b)?(a):(b))
''' + helper + r'''
int main(void) {
 assert(sanitized_size(0,0,0)==sizeof(void *));
 assert(sanitized_size(1,1,1)==3*sizeof(void *));
 assert(sanitized_size(SIZE_MAX,0,0)==0);
 assert(sanitized_size(0,SIZE_MAX,0)==0);
 assert(sanitized_size(0,0,SIZE_MAX)==0);
 assert(sanitized_size(SIZE_MAX-7,8,0)==0);
 assert(sanitized_size(SIZE_MAX-15,8,8)==0);
 puts("PASS: Binder size validation rejects alignment and sum overflows");
}
''')

run_c(r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define PAGE_SIZE 4096
#define min_t(t,a,b) ((t)(a)<(t)(b)?(t)(a):(t)(b))
typedef size_t binder_size_t;
typedef size_t pgoff_t;
struct binder_alloc {int unused;};
struct binder_buffer {size_t unused;};
struct page {unsigned char data[PAGE_SIZE];};
static struct page pages[2];
static size_t binder_alloc_buffer_size(struct binder_alloc *a,struct binder_buffer *b) {return PAGE_SIZE;}
static struct page *binder_alloc_get_page(struct binder_alloc *a,struct binder_buffer *b,size_t offset,pgoff_t *pgoff) {
 *pgoff=(offset+32)%PAGE_SIZE; return &pages[(offset+32)/PAGE_SIZE];
}
static void *kmap(struct page *p) {assert(!"sleepable kmap under allocator spinlock");return p->data;}
static void kunmap(struct page *p) {}
static void *kmap_atomic(struct page *p) {return p->data;}
static void kunmap_atomic(void *p) {}
static void binder_alloc_clear_buf(struct binder_alloc *alloc,struct binder_buffer *buffer)
''' + function_body('drivers/android/binder_alloc.c','binder_alloc_clear_buf') + r'''
int main(void) {
 struct binder_alloc a;struct binder_buffer b;
 memset(pages,0xa5,sizeof(pages));binder_alloc_clear_buf(&a,&b);
 for(size_t i=0;i<2*PAGE_SIZE;i++) {
  unsigned char expected=i>=32&&i<PAGE_SIZE+32?0:0xa5;
  assert(((unsigned char *)pages)[i]==expected);
 }
 puts("PASS: Binder buffer clearing handles partial pages without sleeping mappings");
}
''')
