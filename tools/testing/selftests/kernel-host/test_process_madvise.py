#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Exercise syscall validation, vector progress and reference cleanup."""
from test_helpers import ROOT, function_body, run_c

source = (ROOT / 'mm/madvise.c').read_text()
body = source[source.index('SYSCALL_DEFINE5(process_madvise,'):]
body = body[body.index('{'):]
run_c(r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <errno.h>
#include <sys/types.h>
#include <sys/uio.h>
#define CONFIG_COMPAT 1
#define __user
#define READ 0
#define UIO_FASTIOV 8
#define UIO_MAXIOV 1024
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
#define MADV_COLD 20
#define MADV_PAGEOUT 21
#define PIDTYPE_PID 0
#define PTRACE_MODE_READ_FSCREDS 9
#define CAP_SYS_NICE 23
#define ERR_PTR(e) ((void *)(intptr_t)(e))
#define PTR_ERR(p) ((intptr_t)(p))
#define IS_ERR(p) ((uintptr_t)(p) >= (uintptr_t)-4095)
#define IS_ERR_OR_NULL(p) (!(p) || IS_ERR(p))
struct pid { int refs; } pid_data;
struct task_struct { int refs; } task_data;
struct mm_struct { int refs; } mm_data;
struct compat_iovec { unsigned int base, len; };
struct iov_iter { const struct iovec *iov; size_t count; };
static bool compat, dead, nice = true, no_mm;
static int mm_error, advice_error, calls, imports, compat_imports, frees;
static int in_compat_syscall(void) { return compat; }
static int import_iovec(int rw, const struct iovec *v, unsigned int n,
                        unsigned int fast, struct iovec **iov, struct iov_iter *i) {
    imports++;
    if (!v && n) return -EFAULT;
    *iov = n ? malloc(n * sizeof(**iov)) : NULL;
    i->iov = *iov; i->count = 0;
    for (unsigned int k = 0; k < n; k++) {
        (*iov)[k] = v[k]; i->count += v[k].iov_len;
    }
    return 0;
}
static int compat_import_iovec(int rw, const struct compat_iovec *v, unsigned int n,
                               unsigned int fast, struct iovec **iov, struct iov_iter *i) {
    struct iovec native[UIO_MAXIOV];
    compat_imports++;
    if (!v && n) return -EFAULT;
    for (unsigned int k = 0; k < n; k++)
        native[k] = (struct iovec){(void *)(uintptr_t)v[k].base, v[k].len};
    return import_iovec(rw, native, n, fast, iov, i);
}
static struct pid *pidfd_get_pid(unsigned int fd, unsigned int *flags) {
    if (fd != 7) return ERR_PTR(-EBADF);
    pid_data.refs++; *flags = 0; return &pid_data;
}
static struct task_struct *get_pid_task(struct pid *p, int type) {
    if (dead) return NULL;
    task_data.refs++; return &task_data;
}
static struct mm_struct *mm_access(struct task_struct *t, unsigned int mode) {
    assert(mode == PTRACE_MODE_READ_FSCREDS);
    if (mm_error) return ERR_PTR(mm_error);
    if (no_mm) return NULL;
    mm_data.refs++; return &mm_data;
}
static bool capable(int cap) { assert(cap == CAP_SYS_NICE); return nice; }
static size_t iov_iter_count(struct iov_iter *i) { return i->count; }
static struct iovec iov_iter_iovec(struct iov_iter *i) { return *i->iov; }
static void iov_iter_advance(struct iov_iter *i, size_t len) {
    i->count -= len; i->iov++;
}
static long do_madvise(struct mm_struct *mm, unsigned long addr, size_t len, int advice) {
    assert(mm == &mm_data && mm->refs == 1);
    assert(advice == MADV_COLD || advice == MADV_PAGEOUT);
    calls++;
    return addr == 0xdead000 ? advice_error : 0;
}
static void mmput(struct mm_struct *mm) { assert(--mm->refs == 0); }
static void put_task_struct(struct task_struct *task) { assert(--task->refs == 0); }
static void put_pid(struct pid *pid) { assert(--pid->refs == 0); }
static void kfree(void *p) { if (p) { frees++; free(p); } }
static bool process_madvise_behavior_valid(int behavior)
''' + function_body('mm/madvise.c', 'process_madvise_behavior_valid') + r'''
static ssize_t process_madvise(int pidfd, const struct iovec *vec,
                               size_t vlen, int behavior, unsigned int flags)
''' + body + r'''
static void check_clean(void) {
    assert(!pid_data.refs && !task_data.refs && !mm_data.refs);
}
int main(void) {
    struct iovec vec[] = {{(void *)0x1000, 4096}, {(void *)0xdead000, 8192}};
    assert(process_madvise(7, vec, 2, MADV_COLD, 1) == -EINVAL);
    assert(process_madvise(7, vec, 1025, MADV_COLD, 0) == -EINVAL);
    assert(process_madvise(7, vec, (size_t)1 << 32, MADV_COLD, 0) == -EINVAL);
    assert(imports == 0);
    assert(process_madvise(7, NULL, 1, MADV_COLD, 0) == -EFAULT);
    assert(process_madvise(-1, vec, 2, MADV_COLD, 0) == -EBADF); check_clean();
    dead = true;
    assert(process_madvise(7, vec, 2, MADV_COLD, 0) == -ESRCH); check_clean();
    dead = false;
    assert(process_madvise(7, vec, 2, 4, 0) == -EINVAL); check_clean();
    mm_error = -EACCES;
    assert(process_madvise(7, vec, 2, MADV_COLD, 0) == -EACCES); check_clean();
    mm_error = 0; no_mm = true;
    assert(process_madvise(7, vec, 2, MADV_COLD, 0) == -ESRCH); check_clean();
    no_mm = false; nice = false;
    assert(process_madvise(7, vec, 2, MADV_COLD, 0) == -EPERM); check_clean();
    assert(calls == 0);
    nice = true;
    assert(process_madvise(7, NULL, 0, MADV_COLD, 0) == 0); check_clean();
    assert(process_madvise(7, vec, 2, MADV_COLD, 0) == 12288); check_clean();
    advice_error = -ENOMEM;
    assert(process_madvise(7, vec, 2, MADV_PAGEOUT, 0) == 4096); check_clean();
    assert(process_madvise(7, vec + 1, 1, MADV_PAGEOUT, 0) == -ENOMEM); check_clean();
    advice_error = 0; compat = true;
    struct compat_iovec cv[] = {{0x1000, 4096}, {0x2000, 8192}};
    assert(process_madvise(7, (void *)cv, 2, MADV_PAGEOUT, 0) == 12288);
    assert(compat_imports == 1); check_clean();
    assert(frees == imports - 2); /* EFAULT and empty import allocate nothing. */
    puts("PASS: process_madvise permissions, native/compat vectors, partial results and cleanup");
}
''')
