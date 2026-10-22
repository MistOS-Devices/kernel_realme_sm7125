#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Check mrelease exit eligibility, address-space lifetime and cleanup."""
from test_helpers import ROOT, function_body, run_c

source = (ROOT / 'mm/oom_kill.c').read_text()
start = source.index('SYSCALL_DEFINE2(process_mrelease,')
body = source[source.index('{', start):]
run_c(r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <errno.h>
#define CONFIG_MMU 1
#define MMF_OOM_SKIP 0
#define SIGNAL_GROUP_COREDUMP 1
#define SIGNAL_GROUP_EXIT 2
#define PF_EXITING 1
#define PIDTYPE_TGID 1
#define ERR_PTR(e) ((void *)(intptr_t)(e))
#define PTR_ERR(p) ((intptr_t)(p))
#define IS_ERR(p) ((uintptr_t)(p) >= (uintptr_t)-4095)
struct pid { int refs; } pid_data;
struct signal_struct { int flags; } signal_data;
struct mm_struct { unsigned long flags; int mm_users, mmap_sem; bool notifiers; } mm_data;
struct task_struct {
    struct mm_struct *mm;
    struct signal_struct *signal;
    int refs, flags, tgid;
    bool single;
} task_data, other;
static struct task_struct *processes[2];
static size_t process_count;
static bool dead, no_mm, lock_interrupted;
static int reaped, task_locked, rcu_locked;
static int atomic_read(int *p) { return *p; }
static bool test_bit(int bit, unsigned long *flags) { return *flags & (1ul << bit); }
static bool thread_group_empty(struct task_struct *p) { return p->single; }
static bool same_thread_group(struct task_struct *a, struct task_struct *b) {
    return a->tgid == b->tgid;
}
static bool process_shares_mm(struct task_struct *p, struct mm_struct *mm) {
    return p->mm == mm;
}
#define for_each_process(p) \
    for (size_t k = 0; k < process_count && ((p = processes[k]), 1); k++)
static void rcu_read_lock(void) { rcu_locked++; }
static void rcu_read_unlock(void) { assert(--rcu_locked == 0); }
static struct pid *pidfd_get_pid(unsigned int fd, unsigned int *flags) {
    if (fd != 7) return ERR_PTR(-EBADF);
    pid_data.refs++; *flags = 0; return &pid_data;
}
static struct task_struct *get_pid_task(struct pid *pid, int type) {
    assert(type == PIDTYPE_TGID);
    if (dead) return NULL;
    task_data.refs++; return &task_data;
}
static struct task_struct *find_lock_task_mm(struct task_struct *p) {
    if (no_mm) return NULL;
    task_locked++; return p;
}
static bool mmget_not_zero(struct mm_struct *mm) {
    assert(task_locked == 1);
    if (!mm->mm_users) return false;
    mm->mm_users++; return true;
}
static void task_unlock(struct task_struct *p) { assert(--task_locked == 0); }
static int down_read_killable(int *sem) {
    if (lock_interrupted) return -EINTR;
    assert(++*sem == 1); return 0;
}
static void up_read(int *sem) { assert(--*sem == 0); }
static bool mm_has_notifiers(struct mm_struct *mm) { return mm->notifiers; }
static void __oom_reap_task_mm(struct mm_struct *mm) {
    assert(mm->mmap_sem == 1 && mm->mm_users > 1 && !mm->notifiers);
    reaped++;
}
static void mmput(struct mm_struct *mm) { assert(--mm->mm_users >= 0); }
static void put_task_struct(struct task_struct *p) { assert(--p->refs == 0); }
static void put_pid(struct pid *p) { assert(--p->refs == 0); }
static bool __task_will_free_mem(struct task_struct *task)
''' + function_body('mm/oom_kill.c', '__task_will_free_mem') + r'''
static bool task_will_free_mem(struct task_struct *task)
''' + function_body('mm/oom_kill.c', 'task_will_free_mem') + r'''
static long process_mrelease(int pidfd, unsigned int flags)
''' + body + r'''
static void clean(int users) {
    assert(!pid_data.refs && !task_data.refs && !task_locked && !rcu_locked);
    assert(!mm_data.mmap_sem && mm_data.mm_users == users);
}
int main(void) {
    task_data.mm = &mm_data; task_data.signal = &signal_data; task_data.tgid = 1;
    task_data.single = true; mm_data.mm_users = 1;
    processes[0] = &task_data; process_count = 1;
    assert(process_mrelease(7, 1) == -EINVAL); clean(1);
    assert(process_mrelease(-1, 0) == -EBADF); clean(1);
    dead = true;
    assert(process_mrelease(7, 0) == -ESRCH); clean(1);
    dead = false; no_mm = true;
    assert(process_mrelease(7, 0) == -ESRCH); clean(1);
    no_mm = false;
    assert(process_mrelease(7, 0) == -EINVAL); clean(1); /* Live target. */
    signal_data.flags = SIGNAL_GROUP_COREDUMP | SIGNAL_GROUP_EXIT;
    assert(process_mrelease(7, 0) == -EINVAL); clean(1);
    signal_data.flags = SIGNAL_GROUP_EXIT; lock_interrupted = true;
    assert(process_mrelease(7, 0) == -EINTR); clean(1);
    lock_interrupted = false; mm_data.notifiers = true;
    assert(process_mrelease(7, 0) == -EAGAIN); clean(1);
    mm_data.notifiers = false; mm_data.mm_users = 0;
    assert(process_mrelease(7, 0) == 0); clean(0);
    mm_data.mm_users = 1; mm_data.flags = 1ul << MMF_OOM_SKIP;
    assert(process_mrelease(7, 0) == 0); clean(1);
    mm_data.flags = 0;
    struct signal_struct other_signal = {0};
    other = (struct task_struct){.mm = &mm_data, .signal = &other_signal, .tgid = 2};
    processes[1] = &other; process_count = 2; mm_data.mm_users = 2;
    assert(process_mrelease(7, 0) == -EINVAL); clean(2); /* Live CLONE_VM peer. */
    assert(reaped == 0);
    other_signal.flags = SIGNAL_GROUP_EXIT;
    assert(process_mrelease(7, 0) == 0); clean(2);
    assert(reaped == 1);
    process_count = 1; mm_data.mm_users = 1; signal_data.flags = 0;
    task_data.flags = PF_EXITING;
    assert(process_mrelease(7, 0) == 0); clean(1);
    assert(reaped == 2);
    puts("PASS: process_mrelease rejects live/shared-live/coredump targets and preserves mm lifetime");
}
''')

run_c(r'''
#include <assert.h>
#include <errno.h>
static long process_mrelease(int pidfd, unsigned int flags)
''' + body + r'''
int main(void) {
    assert(process_mrelease(-1, 0) == -ENOSYS);
    assert(process_mrelease(7, 1) == -ENOSYS);
}
''')
