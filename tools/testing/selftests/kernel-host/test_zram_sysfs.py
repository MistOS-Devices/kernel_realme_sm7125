# SPDX-License-Identifier: GPL-2.0
"""Run production sysfs parsers and page selection with small kernel fixtures."""
from test_helpers import function_body, run_c

path = 'drivers/block/zram/zram_drv.c'
run_c(r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <errno.h>
#include <ctype.h>
#include <limits.h>
#include <sys/types.h>
typedef uint32_t u32;
#define PAGE_SHIFT 12
#define PAGE_SIZE (1UL<<PAGE_SHIFT)
#define ZRAM_SECONDARY_COMP 1U
#define ZRAM_MAX_COMPS 4U
#define RECOMPRESS_IDLE 1
#define RECOMPRESS_HUGE 2
#define ZRAM_IDLE 0
#define ZRAM_HUGE 1
#define ZRAM_WB 2
#define ZRAM_UNDER_WB 3
#define ZRAM_SAME 4
#define ZRAM_INCOMPRESSIBLE 5
#define GFP_KERNEL 0
#define min(a,b) ((a)<(b)?(a):(b))
struct zram {unsigned long disksize;int init_lock;bool dedup;const char *comp_algs[4];unsigned long flags[8];bool allocated[8];};
struct device {struct zram *z;};
struct device_attribute {int unused;};
struct page {int unused;};
static bool held,locked,alloc_fail;
static int calls,allocations,free_pages,recomp_error,selected[8],last_prio,algorithm_sets;
static struct page page;
static struct zram *dev_to_zram(struct device *d) {return d->z;}
static bool init_done(struct zram *z) {return z->disksize!=0;}
static bool zram_dedup_enabled(struct zram *z) {return z->dedup;}
static void down_read(int *l) {assert(!held);held=true;}
static void up_read(int *l) {assert(held&&!locked);held=false;}
static struct page *alloc_page(int flags) {assert(held);if(alloc_fail)return NULL;allocations++;return &page;}
static void __free_page(struct page *p) {assert(p==&page&&!locked);free_pages++;}
static void zram_slot_lock(struct zram *z,u32 i) {assert(held&&!locked);locked=true;}
static void zram_slot_unlock(struct zram *z,u32 i) {assert(held&&locked);locked=false;}
static bool zram_allocated(struct zram *z,u32 i) {return z->allocated[i];}
static bool zram_test_flag(struct zram *z,u32 i,int f) {return z->flags[i]&(1UL<<f);}
static void cond_resched(void) {assert(!locked);}
static int zram_recompress(struct zram *z,u32 i,struct page *p,u32 threshold,u32 prio,u32 max) {
 assert(held&&locked&&!z->dedup&&prio>=1&&prio<max&&max<=4);
 calls++;selected[i]++;last_prio=prio;return recomp_error;
}
static int __comp_algorithm_store(struct zram *z,u32 prio,const char *algo) {
 assert(prio>=1&&prio<4);if(init_done(z))return -EBUSY;
 if(strcmp(algo,"zstd")&&strcmp(algo,"lz4hc"))return -EINVAL;
 algorithm_sets++;return 0;
}
static char *skip_spaces(const char *p) {while(isspace((unsigned char)*p))p++;return (char *)p;}
static int kstrtouint(const char *p,int base,unsigned int *out) {
 char *end;errno=0;if(*p=='-')return -EINVAL;
 unsigned long n=strtoul(p,&end,base);
 if(errno||n>UINT_MAX)return -ERANGE;
 if(end==p||(*end&&strcmp(end,"\n")))return -EINVAL;
 *out=n;return 0;
}
static int kstrtoint(const char *p,int base,int *out) {
 char *end;errno=0;long n=strtol(p,&end,base);
 if(errno||n>INT_MAX||n<INT_MIN)return -ERANGE;
 if(end==p||(*end&&strcmp(end,"\n")))return -EINVAL;
 *out=n;return 0;
}
static char *next_arg(char *args,char **param,char **val)
''' + function_body('lib/cmdline.c','next_arg') + r'''
static ssize_t recompress_store(struct device *dev,struct device_attribute *attr,const char *buf,size_t len)
''' + function_body(path,'recompress_store') + r'''
static ssize_t recomp_algorithm_store(struct device *dev,struct device_attribute *attr,const char *buf,size_t len)
''' + function_body(path,'recomp_algorithm_store') + r'''
static ssize_t request(struct device *d,const char *s,bool algo) {
 char buf[256];strcpy(buf,s);ssize_t ret=algo?recomp_algorithm_store(d,NULL,buf,strlen(s)):recompress_store(d,NULL,buf,strlen(s));
 assert(!held&&!locked&&allocations==free_pages);return ret;
}
int main(void) {
 struct zram z={.disksize=8*PAGE_SIZE,.comp_algs={"lz4","zstd","lz4hc",NULL}};
 struct device d={&z};
 for(int i=0;i<8;i++)z.allocated[i]=true;
 z.flags[0]=1<<ZRAM_IDLE;z.flags[1]=(1<<ZRAM_IDLE)|(1<<ZRAM_HUGE);
 z.flags[2]=1<<ZRAM_HUGE;z.flags[3]=1<<ZRAM_WB;z.flags[4]=1<<ZRAM_UNDER_WB;
 z.flags[5]=1<<ZRAM_SAME;z.flags[6]=1<<ZRAM_INCOMPRESSIBLE;z.allocated[7]=false;
 z.dedup=true;assert(request(&d,"type=idle",false)==-EOPNOTSUPP&&calls==0);z.dedup=false;
 const char *bad[]={"type","type=","type=typo","typo=idle","threshold=-1","threshold=4294967296","threshold=4096","algo=missing","", "type=idle garbage"};
 for(size_t i=0;i<sizeof(bad)/sizeof(*bad);i++)assert(request(&d,bad[i],false)<0&&calls==0);
 assert(request(&d,"type=idle",false)>0&&calls==2&&selected[0]&&selected[1]);
 memset(selected,0,sizeof(selected));calls=0;
 assert(request(&d,"type=huge_idle algo=lz4hc",false)>0&&calls==1&&selected[1]&&last_prio==2);
 calls=0;assert(request(&d,"type=huge",false)>0&&calls==2);
 calls=0;assert(request(&d,"type=all",false)>0&&calls==3);
 recomp_error=-EIO;assert(request(&d,"type=idle",false)==-EIO);recomp_error=0;
 alloc_fail=true;assert(request(&d,"type=all",false)==-ENOMEM);alloc_fail=false;
 z.disksize=0;assert(request(&d,"type=all",false)==-EINVAL);
 const char *bad_alg[]={"algo","algo=","priority=1","algo=zstd priority=0","algo=zstd priority=4","algo=zstd priority=-1","algo=zstd priority=9999999999999999","algo=zstd typo=1"};
 for(size_t i=0;i<sizeof(bad_alg)/sizeof(*bad_alg);i++)assert(request(&d,bad_alg[i],true)<0&&algorithm_sets==0);
 assert(request(&d,"algo=zstd priority=1",true)>0&&algorithm_sets==1);
 z.disksize=PAGE_SIZE;assert(request(&d,"algo=zstd",true)==-EBUSY);
 puts("PASS: ZRAM parsers reject malformed requests and dedup; selectors and failures release locks/pages");
}
''')
