#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Check the 4.14 wrapper gets a private inode and balances failure cleanup."""
from test_helpers import function_body, run_c

code = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#define KERNEL_VERSION(a,b,c) (((a)<<16)+((b)<<8)+(c))
#define LINUX_VERSION_CODE KERNEL_VERSION(4,14,0)
#define unlikely(x) (x)
#define ERR_PTR(e) ((void *)(intptr_t)(e))
#define PTR_ERR(p) ((intptr_t)(p))
#define IS_ERR(p) ((intptr_t)(p) < 0 && (intptr_t)(p) >= -4095)
#define ERR_CAST(p) ((void *)(p))
#define S_PRIVATE 512
#define OPEN_FMODE(flags) (((flags) + 1) & O_ACCMODE)
#define QSTR_INIT(n,l) { .name = (n), .len = (l) }
struct qstr { const char *name; size_t len; };
struct inode { unsigned int i_flags; void *i_mapping; int sid, mode; };
struct dentry { struct inode *inode; };
struct vfsmount { void *mnt_sb; };
struct path { struct dentry *dentry; struct vfsmount *mnt; };
struct file_operations { void *owner; };
struct file { struct path path; int f_flags; void *private_data, *f_mapping; };
static struct vfsmount mount;
static struct vfsmount *anon_inode_mnt = &mount;
static int module_error, inode_error, dentry_error, file_error;
static int modules, inodes, dentries, mounts;
static bool try_module_get(void *owner) { if (module_error) return false; modules++; return true; }
static void module_put(void *owner) { modules--; }
static struct inode *alloc_anon_inode(void *sb) {
    if (inode_error) return ERR_PTR(-ENOMEM);
    inodes++;
    struct inode *i = calloc(1, sizeof(*i));
    i->i_flags = S_PRIVATE;
    return i;
}
static void iput(struct inode *i) { inodes--; free(i); }
static struct dentry *d_alloc_pseudo(void *sb, const struct qstr *name) {
    if (dentry_error) return NULL;
    dentries++;
    return calloc(1, sizeof(struct dentry));
}
static struct vfsmount *mntget(struct vfsmount *m) { mounts++; return m; }
static void d_instantiate(struct dentry *d, struct inode *i) { d->inode = i; }
static void path_put(const struct path *p) { mounts--; dentries--; iput(p->dentry->inode); free(p->dentry); }
static struct file *alloc_file(const struct path *p, int mode, const struct file_operations *ops) {
    if (file_error) return ERR_PTR(-ENFILE);
    assert(mode == OPEN_FMODE(O_RDWR));
    struct file *f = calloc(1, sizeof(*f));
    f->path = *p;
    return f;
}
static void fput(struct file *f) { path_put(&f->path); module_put(NULL); free(f); }
static struct inode *ksu_anon_inode_make_secure_inode(const char *name, const struct inode *context_inode)
'''
path = 'drivers/kernelsu/infra/file_wrapper.c'
code += function_body(path, 'ksu_anon_inode_make_secure_inode')
code += '''static struct file *ksu_anon_inode_create_getfile_compat(
    const char *name, const struct file_operations *fops, void *priv,
    int flags, const struct inode *context_inode)'''
code += function_body(path, 'ksu_anon_inode_create_getfile_compat')
code += r'''
static struct file *create(void) {
    static const struct file_operations ops = { .owner = (void *)1 };
    return ksu_anon_inode_create_getfile_compat("[ksu_fdwrapper]", &ops, (void *)2, O_RDWR | O_CLOEXEC, NULL);
}
static void check_error(int error) {
    assert(PTR_ERR(create()) == error);
    assert(!modules && !inodes && !dentries && !mounts);
}
int main(void) {
    module_error = 1; check_error(-ENOENT); module_error = 0;
    anon_inode_mnt = NULL; check_error(-ENODEV); anon_inode_mnt = &mount;
    inode_error = 1; check_error(-ENOMEM); inode_error = 0;
    dentry_error = 1; check_error(-ENOMEM); dentry_error = 0;
    file_error = 1; check_error(-ENFILE); file_error = 0;
    struct file *a = create(), *b = create();
    assert(!IS_ERR(a) && !IS_ERR(b));
    assert(a->path.dentry->inode != b->path.dentry->inode);
    assert(!(a->path.dentry->inode->i_flags & S_PRIVATE));
    a->path.dentry->inode->sid = 123;
    a->path.dentry->inode->mode = 456;
    assert(!b->path.dentry->inode->sid && !b->path.dentry->inode->mode);
    assert(a->f_flags == O_RDWR && a->private_data == (void *)2);
    fput(a); fput(b);
    assert(!modules && !inodes && !dentries && !mounts);
    puts("PASS: KernelSU 4.14 wrappers use independent inodes and release every failed allocation");
}
'''
run_c(code)
