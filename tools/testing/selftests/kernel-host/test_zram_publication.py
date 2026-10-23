# SPDX-License-Identifier: GPL-2.0
"""Invoke production add with sysfs access occurring at device publication."""
from test_helpers import function_body, run_c

run_c(r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <errno.h>
#include <limits.h>
typedef uint32_t u32;
#define GFP_KERNEL 0
#define PAGE_SIZE 4096
#define ZRAM_LOGICAL_BLOCK_SIZE 4096
#define ZRAM_PRIMARY_COMP 0
#define QUEUE_FLAG_NONROT 0
#define QUEUE_FLAG_ADD_RANDOM 1
#define QUEUE_FLAG_DISCARD 2
#define BDI_CAP_STABLE_WRITES 1
#define BDI_CAP_SYNCHRONOUS_IO 2
#define pr_err(...) ((void)0)
#define pr_info(...) ((void)0)
#define blk_queue_make_request(...) ((void)0)
#define blk_queue_physical_block_size(...) ((void)0)
#define blk_queue_logical_block_size(...) ((void)0)
#define blk_queue_io_min(...) ((void)0)
#define blk_queue_io_opt(...) ((void)0)
#define blk_queue_max_discard_sectors(...) ((void)0)
#define blk_queue_max_write_zeroes_sectors(...) ((void)0)
#define queue_flag_set_unlocked(...) ((void)0)
#define queue_flag_clear_unlocked(...) ((void)0)
struct backing_dev_info {unsigned long capabilities;};
struct request_queue {void *queuedata;struct {unsigned long discard_granularity;}limits;struct backing_dev_info *backing_dev_info;};
struct device {const void *groups;};
struct gendisk {int major,first_minor;const void *fops;struct request_queue *queue;void *private_data;char disk_name[16];struct device dev;};
struct zram {int init_lock;struct gendisk *disk;const char *comp_algs[4];};
static const char *default_compressor="lz4";
static const int zram_devops,zram_major=252;
static const int zram_disk_attr_groups[1]={0};
static int zram_index_idr;
static struct backing_dev_info bdi;
static struct zram *created;
static void *kzalloc(size_t n,int flags) {return calloc(1,n);}
static void kfree(const void *p) {assert(p!=default_compressor);free((void *)p);}
static int idr_alloc(int *idr,struct zram *z,int lo,int hi,int flags) {created=z;return 2;}
static void idr_remove(int *idr,int id) {}
static void init_rwsem(int *l) {}
static struct request_queue *blk_alloc_queue(int flags) {struct request_queue *q=calloc(1,sizeof(*q));q->backing_dev_info=&bdi;return q;}
static void blk_cleanup_queue(struct request_queue *q) {free(q);}
static struct gendisk *alloc_disk(int n) {return calloc(1,sizeof(struct gendisk));}
static void set_capacity(struct gendisk *d,unsigned long n) {}
static struct device *disk_to_dev(struct gendisk *d) {return &d->dev;}
static void add_disk(struct gendisk *d) {
 struct zram *z=d->private_data;
 assert(z->comp_algs[0]&&!strcmp(z->comp_algs[0],"lz4"));
 /* A sysfs write immediately after publication must survive add completion. */
 z->comp_algs[0]=strdup("lz4hc");
}
static void zram_debugfs_register(struct zram *z) {}
static void comp_algorithm_set(struct zram *zram,u32 prio,const char *alg)
''' + function_body('drivers/block/zram/zram_drv.c','comp_algorithm_set') + r'''
static int zram_add(void)
''' + function_body('drivers/block/zram/zram_drv.c','zram_add') + r'''
int main(void) {
 assert(zram_add()==2);
 assert(!strcmp(created->comp_algs[0],"lz4hc"));
 kfree(created->comp_algs[0]);blk_cleanup_queue(created->disk->queue);free(created->disk);free(created);
 puts("PASS: ZRAM initializes its primary before sysfs publication and retains early configuration");
}
''')
