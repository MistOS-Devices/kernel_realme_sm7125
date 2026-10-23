#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Exercise production DMA-BUF statistics work, failures and object lifetimes."""
import re
from test_helpers import ROOT, function_body, run_c

base = ROOT / 'drivers/dma-buf'
source = (base / 'dma-buf-sysfs-stats.c').read_text()
header = (base / 'dma-buf-sysfs-stats.h').read_text()
strip_includes = lambda s: re.sub(r'^#include[^\n]*\n', '', s, flags=re.M)
run_c(r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include <errno.h>
#include <sys/types.h>
#define CONFIG_DMABUF_SYSFS_STATS 1
#define GFP_KERNEL 0
#define container_of(p, t, m) ((t *)((char *)(p) - offsetof(t, m)))
#define pr_err(...) ((void)0)
#define sysfs_emit(b, ...) snprintf(b, 4096, __VA_ARGS__)
struct kset;
struct kobj_type;
struct attribute { const char *name; unsigned mode; };
struct kobject {
    struct kset *kset;
    struct kobj_type *type;
    unsigned refs;
    bool deleted;
    char name[32];
};
struct sysfs_ops {
    ssize_t (*show)(struct kobject *, struct attribute *, char *);
};
struct kobj_type {
    const struct sysfs_ops *sysfs_ops;
    void (*release)(struct kobject *);
    struct attribute **default_attrs;
};
struct kset { struct kobject kobj; };
struct kset_uevent_ops { int (*filter)(struct kset *, struct kobject *); };
struct work_struct { void (*fn)(struct work_struct *); };
struct file { int refs; struct { unsigned long i_ino; } inode; };
struct dma_buf_sysfs_entry;
struct dma_buf {
    struct file *file;
    const char *exp_name;
    size_t size;
    struct dma_buf_sysfs_entry *sysfs_entry;
};
static int allocations, destroyed, deleted, roots, root_calls, fail_root;
static bool fail_alloc, fail_add;
static struct work_struct *pending;
static struct kobject kernel_object, *kernel_kobj = &kernel_object;
static void *stats_alloc(size_t n) {
    if (fail_alloc) return NULL;
    void *p = malloc(n);
    assert(p);
    memset(p, 0xa5, n);
    allocations++;
    return p;
}
static void stats_free(void *p) {
    assert(p && allocations > 0);
    allocations--;
    free(p);
}
#define kmalloc(n, flags) stats_alloc(n)
#define kfree(p) stats_free(p)
#define file_count(f) ((f)->refs)
#define file_inode(f) (&(f)->inode)
#define INIT_WORK(w, callback) ((w)->fn = (callback))
#define __ATTR_RO(n) { .attr = { #n, 0444 }, .show = n##_show }
static void get_dma_buf(struct dma_buf *b) { assert(b->file->refs > 0); b->file->refs++; }
static void dma_buf_put(struct dma_buf *b);
static bool schedule_work(struct work_struct *w) {
    assert(!pending); pending = w; return true;
}
static void drain_work(void) {
    struct work_struct *w = pending;
    assert(w); pending = NULL; w->fn(w);
}
static struct kset *kset_create_and_add(const char *name,
        const struct kset_uevent_ops *ops, struct kobject *parent) {
    assert(ops && !ops->filter(NULL, NULL));
    root_calls++;
    if (root_calls == fail_root) return NULL;
    struct kset *s = calloc(1, sizeof(*s));
    assert(s); roots++;
    snprintf(s->kobj.name, sizeof(s->kobj.name), "%s", name);
    if (!strcmp(name, "dmabuf")) assert(parent == kernel_kobj);
    else assert(!strcmp(name, "buffers") && !strcmp(parent->name, "dmabuf"));
    return s;
}
static void kset_unregister(struct kset *s) { assert(s && roots); roots--; free(s); }
static int kobject_init_and_add(struct kobject *k, struct kobj_type *t,
                               struct kobject *parent, const char *fmt, ...) {
    assert(!k->refs && !k->type && !k->deleted && k->kset);
    assert(!parent);
    k->type = t; k->refs = 1;
    va_list ap; va_start(ap, fmt);
    vsnprintf(k->name, sizeof(k->name), fmt, ap); va_end(ap);
    return fail_add ? -ENOMEM : 0;
}
static void kobject_del(struct kobject *k) {
    assert(k->refs == 1 && !k->deleted); k->deleted = true; deleted++;
}
static void kobject_put(struct kobject *k) {
    assert(k->refs == 1); k->refs = 0; k->type->release(k);
}
''' + strip_includes(header) + r'''
static void dma_buf_put(struct dma_buf *b) {
    assert(b->file->refs > 0);
    if (!--b->file->refs) { dma_buf_stats_teardown(b); destroyed++; }
}
''' + strip_includes(source) + r'''
int main(void) {
    struct file f = { .refs = 1, .inode = { .i_ino = 12345 } };
    struct dma_buf b = { .file = &f, .exp_name = "ion", .size = (size_t)1 << 40 };
    assert(dma_buf_stats_setup(NULL) == -EINVAL);
    assert(dma_buf_stats_setup(&(struct dma_buf){0}) == -EINVAL);
    fail_root = 1;
    assert(dma_buf_init_sysfs_statistics() == -ENOMEM && roots == 0);
    assert(dma_buf_stats_setup(&b) == -ENODEV);
    root_calls = 0; fail_root = 2;
    assert(dma_buf_init_sysfs_statistics() == -ENOMEM && roots == 0);
    dma_buf_uninit_sysfs_statistics();
    root_calls = 0; fail_root = 0;
    assert(dma_buf_init_sysfs_statistics() == 0 && roots == 2);
    fail_alloc = true;
    assert(dma_buf_stats_setup(&b) == -ENOMEM && !b.sysfs_entry && f.refs == 1);
    fail_alloc = false;
    assert(dma_buf_stats_setup(&b) == 0 && f.refs == 2 && allocations == 1);
    dma_buf_put(&b);
    assert(f.refs == 1 && destroyed == 0);
    drain_work();
    assert(f.refs == 0 && destroyed == 1 && !b.sysfs_entry && !allocations);
    f.refs = 1;
    assert(dma_buf_stats_setup(&b) == 0);
    drain_work();
    assert(f.refs == 1 && b.sysfs_entry && allocations == 1);
    struct kobject *k = &b.sysfs_entry->kobj;
    assert(!strcmp(k->name, "12345"));
    char text[4096];
    assert(exporter_name_attribute.attr.mode == 0444 && size_attribute.attr.mode == 0444);
    assert(dma_buf_stats_attribute_show(k, &exporter_name_attribute.attr, text) == 4);
    assert(!strcmp(text, "ion\n"));
    assert(dma_buf_stats_attribute_show(k, &size_attribute.attr, text) == 14);
    assert(!strcmp(text, "1099511627776\n"));
    b.exp_name = NULL;
    assert(exporter_name_show(&b, &exporter_name_attribute, text) == 8);
    assert(!strcmp(text, "unknown\n"));
    dma_buf_put(&b);
    assert(destroyed == 2 && deleted == 1 && !allocations && !b.sysfs_entry);
    dma_buf_stats_teardown(&b);
    f.refs = 1; fail_add = true;
    assert(dma_buf_stats_setup(&b) == 0);
    drain_work();
    assert(f.refs == 1 && !b.sysfs_entry && !allocations);
    dma_buf_put(&b);
    assert(destroyed == 3);
    dma_buf_uninit_sysfs_statistics();
    assert(roots == 0 && !allocations && !pending);
    puts("PASS: DMA-BUF stats async references, short-lived buffers, sysfs metadata and failure cleanup");
}
''')
run_c('#include <assert.h>\n' + strip_includes(header) + r'''
int main(void) {
    assert(dma_buf_init_sysfs_statistics() == 0);
    assert(dma_buf_stats_setup(0) == 0);
    dma_buf_stats_teardown(0);
    dma_buf_uninit_sysfs_statistics();
}
''')
release = function_body('drivers/dma-buf/dma-buf.c', 'dma_buf_release')
assert release.index('dma_buf_stats_teardown') < release.index('dmabuf->ops->release')
export = function_body('drivers/dma-buf/dma-buf.c', 'dma_buf_export')
assert export.index('dma_buf_ref_init') < export.index('dma_buf_stats_setup')
assert export.index('list_add') < export.index('dma_buf_stats_setup')
