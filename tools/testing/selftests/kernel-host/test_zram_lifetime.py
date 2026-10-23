# SPDX-License-Identifier: GPL-2.0
"""Exercise production compressor/name ownership on reset and setup failure."""
from test_helpers import function_body, run_c, ROOT
import re

path = 'drivers/block/zram/zram_drv.c'
run_c(r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
typedef uint32_t u32;
#define ZRAM_PRIMARY_COMP 0U
#define ZRAM_SECONDARY_COMP 1U
#define ZRAM_MAX_COMPS 4U
struct zcomp {int id;};
struct disk {int part0;};
struct zram {int init_lock;unsigned long limit_pages,disksize;struct disk *disk;struct zcomp *comps[4];const char *comp_algs[4];u32 num_active_comps;struct {long n;}stats;};
static const char *default_compressor="lz4";
static int frees,destroys,meta_frees,resets;
static bool held;
static void kfree(const void *p) {assert(p!=default_compressor);if(p)frees++;free((void *)p);}
static void zcomp_destroy(struct zcomp *c) {destroys++;free(c);}
static void down_write(int *lock) {assert(!held);held=true;}
static void up_write(int *lock) {assert(held);held=false;}
static bool init_done(struct zram *z) {return z->disksize!=0;}
static void set_capacity(struct disk *d,unsigned long n) {assert(held&&n==0);}
#define part_stat_set_all(...) ((void)0)
static void zram_meta_free(struct zram *z,unsigned long n) {assert(held&&n);meta_frees++;}
static void reset_bdev(struct zram *z) {assert(held);resets++;}
static void comp_algorithm_set(struct zram *zram,u32 prio,const char *alg)
''' + function_body(path,'comp_algorithm_set') + r'''
static void zram_destroy_comps(struct zram *zram)
''' + function_body(path,'zram_destroy_comps') + r'''
static void zram_reset_device(struct zram *zram)
''' + function_body(path,'zram_reset_device') + r'''
int main(void) {
 struct disk d={0};struct zram z={.disk=&d};
 z.comp_algs[0]=default_compressor;z.comp_algs[1]=strdup("zstd");
 zram_reset_device(&z);
 assert(frees==1&&!destroys&&!meta_frees&&resets==1&&!held);
 assert(z.comp_algs[0]==default_compressor&&!z.comp_algs[1]);
 z.comp_algs[0]=strdup("lz4hc");z.comp_algs[1]=strdup("zstd");
 for(int i=0;i<2;i++){z.comps[i]=calloc(1,sizeof(struct zcomp));z.num_active_comps++;}
 z.disksize=4096;zram_reset_device(&z);
 assert(frees==3&&destroys==2&&meta_frees==1&&!z.num_active_comps&&!z.disksize&&!held);
 assert(z.comp_algs[0]==default_compressor&&!z.comp_algs[1]);
 /* The same helper handles a partially constructed compressor list. */
 z.comp_algs[0]=strdup("lz4hc");z.comp_algs[1]=strdup("zstd");
 z.comps[0]=calloc(1,sizeof(struct zcomp));z.num_active_comps=1;
 zram_destroy_comps(&z);
 assert(frees==5&&destroys==3&&!z.num_active_comps);
 assert(z.comp_algs[0]==default_compressor&&!z.comp_algs[1]);
 zram_reset_device(&z);assert(frees==5&&destroys==3);
 puts("PASS: ZRAM reset frees uninitialized and partial compressor sets and restores a safe primary");
}
''')

# The enum must fit in a 32-bit flags word even with 64 KiB pages.
source = (ROOT / 'drivers/block/zram/zram_drv.h').read_text()
enum = re.search(r'enum zram_pageflags\s*\{.*?\};', source, re.S).group()
run_c('#include <stdio.h>\n#define PAGE_SHIFT 16\n#define ZRAM_FLAG_SHIFT (PAGE_SHIFT + 1)\n'
      + enum + '\n_Static_assert(__NR_ZRAM_PAGEFLAGS <= 32, "flags overflow on 32-bit");\n'
      + 'int main(void) {puts("PASS: ZRAM size, flags and codec identity fit a 32-bit word");}\n')


run_c(r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdarg.h>
#include <string.h>
#include <sys/types.h>
typedef uint32_t u32;
#define PAGE_SIZE 4096
#define ZRAM_SECONDARY_COMP 1U
#define ZRAM_MAX_COMPS 4U
struct zram {int init_lock;const char *comp_algs[4];};
struct device {struct zram *z;};
struct device_attribute {int unused;};
static bool held;
static struct zram *dev_to_zram(struct device *d) {return d->z;}
static void down_read(int *l) {assert(!held);held=true;}
static void up_read(int *l) {assert(held);held=false;}
static int scnprintf(char *buf,size_t n,const char *format,...) {
 assert(held);va_list args;va_start(args,format);int ret=vsnprintf(buf,n,format,args);va_end(args);return ret;
}
static ssize_t zcomp_available_show(const char *alg,char *buf) {assert(held&&alg);return snprintf(buf,64,"[%s]\n",alg);}
static ssize_t __comp_algorithm_show(struct zram *z,u32 prio,char *buf) {down_read(&z->init_lock);ssize_t n=zcomp_available_show(z->comp_algs[prio],buf);up_read(&z->init_lock);return n;}
static ssize_t recomp_algorithm_show(struct device *dev,struct device_attribute *attr,char *buf)
''' + function_body(path,'recomp_algorithm_show') + r'''
int main(void) {
 struct zram z={.comp_algs={"lz4","zstd",NULL,"lz4hc"}};struct device d={&z};char buf[PAGE_SIZE];
 assert(recomp_algorithm_show(&d,NULL,buf)>0&&!held);
 assert(strstr(buf,"#1: [zstd]")&&strstr(buf,"#3: [lz4hc]"));
 puts("PASS: ZRAM secondary algorithm enumeration keeps name ownership locked");
}
''')
