# SPDX-License-Identifier: GPL-2.0
"""Exercise production recompression and stored-compressor readback with codec fixtures."""
from test_helpers import function_body, run_c

path = 'drivers/block/zram/zram_drv.c'
run_c(r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <errno.h>
typedef uint32_t u32;
#define PAGE_SIZE 4096
#define ZRAM_MAX_COMPS 4
#define ZRAM_PRIMARY_COMP 0
#define ZRAM_COMP_PRIORITY_MASK 3UL
#define ZRAM_COMP_PRIORITY_BIT1 20
#define ZRAM_HUGE 17
#define ZRAM_IDLE 18
#define ZRAM_INCOMPRESSIBLE 19
#define ZRAM_SAME 14
#define __GFP_KSWAPD_RECLAIM 0
#define __GFP_NOWARN 0
#define __GFP_HIGHMEM 0
#define __GFP_MOVABLE 0
#define ZS_MM_WO 0
#define ZS_MM_RO 0
#define IS_ERR_VALUE(v) ((uintptr_t)(v)>=(uintptr_t)-4095)
#define PTR_ERR(v) ((intptr_t)(v))
#define atomic64_add(n,p) (*(p)+=(n))
#define atomic64_inc(p) (++*(p))
struct page {unsigned char data[PAGE_SIZE];};
struct zram_entry {unsigned char data[PAGE_SIZE];};
struct zcomp_strm {unsigned char buffer[PAGE_SIZE];int id;};
struct zcomp {struct zcomp_strm stream;};
struct zram_table_entry {struct zram_entry *entry;unsigned long flags;unsigned int size;};
struct zram {struct zram_table_entry table[1];void *mem_pool;struct zcomp *comps[4];bool use_dedup;u32 num_active_comps;struct {long compr_data_size,pages_stored,huge_pages;}stats;};
static unsigned int lengths[4]={3000,1000,500,400};
static int stream_held=-1,compress_error,read_error,frees,allocs,last_decoder=-1;
static bool alloc_fail;
static unsigned char original[PAGE_SIZE];
static bool zram_dedup_enabled(struct zram *z) {return z->use_dedup;}
static struct zram_entry *zram_get_entry(struct zram *z,u32 i) {return z->table[i].entry;}
static void zram_set_entry(struct zram *z,u32 i,struct zram_entry *e) {z->table[i].entry=e;}
static unsigned long zram_entry_handle(struct zram *z,struct zram_entry *e) {return (unsigned long)e;}
static unsigned long zram_get_handle(struct zram *z,u32 i) {return (unsigned long)zram_get_entry(z,i);}
static void zram_set_handle(struct zram *z,u32 i,unsigned long h) {zram_set_entry(z,i,(void *)h);}
static unsigned int zram_get_obj_size(struct zram *z,u32 i) {return z->table[i].size;}
static void zram_set_obj_size(struct zram *z,u32 i,unsigned int n) {z->table[i].size=n;}
static void zram_set_flag(struct zram *z,u32 i,int f) {z->table[i].flags|=1UL<<f;}
static void zram_clear_flag(struct zram *z,u32 i,int f) {z->table[i].flags&=~(1UL<<f);}
static bool zram_test_flag(struct zram *z,u32 i,int f) {return z->table[i].flags&(1UL<<f);}
static void *kmap_atomic(struct page *p) {return p->data;}
static void kunmap_atomic(void *p) {}
static void zram_fill_page(void *p,size_t size,unsigned long value) {for(size_t i=0;i<size/sizeof(value);i++)((unsigned long *)p)[i]=value;}
static unsigned long zram_get_element(struct zram *z,u32 i) {return (unsigned long)z->table[i].entry;}
static struct zcomp_strm *zcomp_stream_get(struct zcomp *c) {assert(stream_held==-1);stream_held=c->stream.id;return &c->stream;}
static void zcomp_stream_put(struct zcomp *c) {assert(stream_held==c->stream.id);stream_held=-1;}
/* Deterministic codec fixture verifies routing and exact decoded bytes. */
static int zcomp_compress(struct zcomp_strm *s,void *src,unsigned int *len) {
 assert(!memcmp(src,original,PAGE_SIZE));
 if(compress_error)return compress_error;
 *len=lengths[s->id];memset(s->buffer,s->id,*len);return 0;
}
static int zcomp_decompress(struct zcomp_strm *s,void *src,unsigned int size,void *dst) {
 assert(((unsigned char *)src)[0]==s->id);last_decoder=s->id;
 if(read_error)return read_error;
 memcpy(dst,original,PAGE_SIZE);return 0;
}
static unsigned long zs_malloc(void *pool,unsigned int n,int flags) {allocs++;return alloc_fail?0:(unsigned long)calloc(1,sizeof(struct zram_entry));}
static struct zram_entry *zram_entry_alloc(struct zram *z,unsigned int n,int flags) {assert(!z->use_dedup);return (void *)zs_malloc(z->mem_pool,n,flags);}
static void *zs_map_object(void *pool,unsigned long h,int mode) {assert(h);return (void *)h;}
static void zs_unmap_object(void *pool,unsigned long h) {}
static unsigned int zs_lookup_class_index(void *pool,unsigned int n) {return (n+255)/256;}
static void zram_free_page(struct zram *z,size_t i) {
 frees++;free(z->table[i].entry);z->stats.compr_data_size-=z->table[i].size;
 z->stats.pages_stored--;if(zram_test_flag(z,i,ZRAM_HUGE))z->stats.huge_pages--;
 memset(&z->table[i],0,sizeof(z->table[i]));
}
static void zram_set_priority(struct zram *zram,u32 index,u32 prio)
''' + function_body(path,'zram_set_priority') + r'''
static u32 zram_get_priority(struct zram *zram,u32 index)
''' + function_body(path,'zram_get_priority') + r'''
static int zram_read_from_zspool(struct zram *zram,struct page *page,u32 index)
''' + function_body(path,'zram_read_from_zspool') + r'''
static int zram_recompress(struct zram *zram,u32 index,struct page *page,u32 threshold,u32 prio,u32 prio_max)
''' + function_body(path,'zram_recompress') + r'''
static void setup(struct zram *z,struct zcomp *comps) {
 memset(z,0,sizeof(*z));z->num_active_comps=4;
 for(int i=0;i<4;i++){comps[i].stream.id=i;z->comps[i]=&comps[i];}
 z->table[0].entry=calloc(1,sizeof(struct zram_entry));z->table[0].size=3000;
 z->stats.compr_data_size=3000;z->stats.pages_stored=1;frees=allocs=0;
}
int main(void) {
 struct zram z;struct zcomp comps[4];struct page page,decoded;
 for(size_t i=0;i<PAGE_SIZE;i++)original[i]=(unsigned char)(i*37);
 setup(&z,comps);void *old=z.table[0].entry;
 alloc_fail=true;
 assert(zram_recompress(&z,0,&page,0,1,2)==-ENOMEM);
 assert(z.table[0].entry==old&&z.table[0].size==3000&&!frees&&stream_held==-1);
 alloc_fail=false;compress_error=-EIO;
 assert(zram_recompress(&z,0,&page,0,1,2)==-EIO);
 assert(z.table[0].entry==old&&!frees&&stream_held==-1);compress_error=0;
 read_error=-EIO;assert(zram_recompress(&z,0,&page,0,1,2)==-EIO);
 assert(z.table[0].entry==old&&!frees&&stream_held==-1);read_error=0;
 lengths[1]=2999;
 assert(zram_recompress(&z,0,&page,0,1,2)==0);
 assert(z.table[0].entry==old&&!frees&&stream_held==-1);
 zram_clear_flag(&z,0,ZRAM_INCOMPRESSIBLE);lengths[1]=1000;
 assert(zram_recompress(&z,0,&page,0,1,2)==0);
 assert(frees==1&&z.table[0].size==1000&&zram_get_priority(&z,0)==1);
 assert(z.stats.pages_stored==1&&z.stats.compr_data_size==1000&&stream_held==-1);
 assert(zram_read_from_zspool(&z,&decoded,0)==0&&last_decoder==1);
 assert(!memcmp(decoded.data,original,PAGE_SIZE));
 assert(zram_recompress(&z,0,&page,0,1,2)==0&&frees==1);
 assert(zram_recompress(&z,0,&page,0,1,4)==0&&frees==2&&zram_get_priority(&z,0)==2);
 assert(zram_read_from_zspool(&z,&decoded,0)==0&&last_decoder==2);
 assert(!memcmp(decoded.data,original,PAGE_SIZE));
 zram_free_page(&z,0);assert(!zram_get_priority(&z,0)&&!z.stats.pages_stored);
 puts("PASS: ZRAM recompression retains old data on failure and reads with the stored compressor");
}
''')
