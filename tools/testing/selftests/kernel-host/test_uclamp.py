#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Check production clamp validation and boundary bucket indices."""
from test_helpers import function_body, run_c
import re

bucket = function_body('kernel/sched/core.c', 'uclamp_bucket_id')
validate = function_body('kernel/sched/core.c', 'uclamp_validate')
run_c(r'''
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <errno.h>
#define SCHED_CAPACITY_SCALE 1024
#define SCHED_FLAG_UTIL_CLAMP_MIN 0x20
#define SCHED_FLAG_UTIL_CLAMP_MAX 0x40
#define UCLAMP_MIN 0
#define UCLAMP_MAX 1
static unsigned int buckets = 5;
#define UCLAMP_BUCKETS buckets
#define UCLAMP_BUCKET_DELTA ((1024 + buckets / 2) / buckets)
#define min_t(type, a, b) ((type)(a) < (type)(b) ? (type)(a) : (type)(b))
struct uclamp_se { unsigned int value; };
struct task_struct { struct uclamp_se uclamp_req[2]; };
struct sched_attr { unsigned long sched_flags; unsigned int sched_util_min, sched_util_max; };
static unsigned int uclamp_bucket_id(unsigned int clamp_value)
''' + bucket + r'''
static int uclamp_validate(struct task_struct *p, const struct sched_attr *attr)
''' + validate + r'''
int main(void) {
    for (buckets = 5; buckets <= 20; buckets++)
        for (unsigned int v = 0; v <= 1024; v++)
            assert(uclamp_bucket_id(v) < buckets);
    struct task_struct p = {.uclamp_req = {{0}, {1024}}};
    struct sched_attr a = {.sched_flags = 0x60, .sched_util_min = 256,
                           .sched_util_max = 768};
    assert(uclamp_validate(&p, &a) == 0);
    a.sched_util_min = 769;
    assert(uclamp_validate(&p, &a) == -EINVAL);
    a.sched_util_min = 0; a.sched_util_max = 1025;
    assert(uclamp_validate(&p, &a) == -EINVAL);
    a.sched_flags = SCHED_FLAG_UTIL_CLAMP_MIN; a.sched_util_min = 1024;
    assert(uclamp_validate(&p, &a) == 0);
    p.uclamp_req[UCLAMP_MIN].value = 512;
    a.sched_flags = SCHED_FLAG_UTIL_CLAMP_MAX; a.sched_util_max = 511;
    assert(uclamp_validate(&p, &a) == -EINVAL);
    a.sched_util_max = 512;
    assert(uclamp_validate(&p, &a) == 0);
    puts("PASS: uclamp bucket bounds and partial min/max attribute validation");
}
''')

gate = re.search(r'if \(attr->sched_flags &\s*~[^;]+;\s*',
                 function_body('kernel/sched/core.c', '__sched_setscheduler')).group()
run_c(r'''
#include <assert.h>
#include <errno.h>
#define SCHED_FLAG_RESET_ON_FORK 0x01
#define SCHED_FLAG_RECLAIM 0x02
#define SCHED_FLAG_KEEP_POLICY 0x08
#define SCHED_FLAG_KEEP_PARAMS 0x10
#define SCHED_FLAG_UTIL_CLAMP_MIN 0x20
#define SCHED_FLAG_UTIL_CLAMP_MAX 0x40
#define SCHED_FLAG_KEEP_ALL 0x18
#define SCHED_FLAG_UTIL_CLAMP 0x60
#define SCHED_FLAG_ALL 0x7b
struct sched_attr { unsigned long sched_flags; };
static int check_flags(struct sched_attr *attr) {
''' + gate + r'''
    return 0;
}
int main(void) {
    struct sched_attr a = {.sched_flags = SCHED_FLAG_KEEP_ALL | SCHED_FLAG_UTIL_CLAMP};
    assert(check_flags(&a) == 0);
    a.sched_flags |= 0x04;
    assert(check_flags(&a) == -EINVAL);
}
''')

# KEEP_PARAMS must discard fields ignored by the target task's policy before
# the 4.14 scheduler's unconditional priority validation.
run_c(r'''
#include <assert.h>
#include <stdio.h>
struct task_struct { int policy, nice; unsigned int rt_priority; };
struct sched_attr { int sched_nice; unsigned int sched_priority; unsigned long sched_runtime; };
static int task_has_dl_policy(struct task_struct *p) { return p->policy == 6; }
static int task_has_rt_policy(struct task_struct *p) { return p->policy == 1 || p->policy == 2; }
static int task_nice(struct task_struct *p) { return p->nice; }
static void __getparam_dl(struct task_struct *p, struct sched_attr *a) { a->sched_runtime = 1000; }
static void get_params(struct task_struct *p, struct sched_attr *attr)
''' + function_body('kernel/sched/core.c', 'get_params') + r'''
int main(void) {
    struct task_struct p = {.policy = 0, .nice = 3};
    struct sched_attr a = {.sched_nice = -20, .sched_priority = 99};
    get_params(&p, &a);
    assert(a.sched_nice == 3 && a.sched_priority == 0);
    p.policy = 2; p.rt_priority = 42;
    get_params(&p, &a);
    assert(a.sched_priority == 42);
    p.policy = 6; p.rt_priority = 0; a.sched_priority = 99;
    get_params(&p, &a);
    assert(a.sched_priority == 0 && a.sched_runtime == 1000);
    puts("PASS: KEEP_PARAMS replaces ignored priority before normal/RT/deadline validation");
}
''')

# Complete another partial update while this caller waits for the rq lock.
# Extract the caller too: testing the validator alone misses the lock order.
scheduler = function_body('kernel/sched/core.c', '__sched_setscheduler')
start = scheduler.index('\n\t}', scheduler.index('retval = security_task_setscheduler')) + len('\n\t}')
end = scheduler.index('\n\t/*\n\t * Changing the policy of the stop threads')
run_c(r'''
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <errno.h>
#define CONFIG_UCLAMP_TASK 1
#define SCHED_CAPACITY_SCALE 1024
#define SCHED_FLAG_UTIL_CLAMP_MIN 0x20
#define SCHED_FLAG_UTIL_CLAMP_MAX 0x40
#define SCHED_FLAG_UTIL_CLAMP 0x60
#define UCLAMP_MIN 0
#define UCLAMP_MAX 1
struct task_struct { struct {unsigned int value;} uclamp_req[2]; };
struct sched_attr {unsigned int sched_flags, sched_util_min, sched_util_max;};
struct rq {bool locked;} rq_data;
struct rq_flags {int unused;};
static bool sched_uclamp_used;
static void static_branch_enable(bool *key) {
    assert(!rq_data.locked); *key = true;
}
static struct rq *task_rq_lock(struct task_struct *p, struct rq_flags *rf) {
    assert(!rq_data.locked);
    p->uclamp_req[UCLAMP_MIN].value = 800;
    rq_data.locked = true;
    return &rq_data;
}
static void task_rq_unlock(struct rq *rq, struct task_struct *p, struct rq_flags *rf) {
    assert(rq->locked); rq->locked = false;
}
static void update_rq_clock(struct rq *rq) { assert(rq->locked); }
static int uclamp_validate(struct task_struct *p, const struct sched_attr *attr)
''' + validate + r'''
static int validate_update(struct task_struct *p, const struct sched_attr *attr) {
    int retval;
    struct rq *rq;
    struct rq_flags rf;
''' + scheduler[start:end] + r'''
    task_rq_unlock(rq, p, &rf);
    return 0;
}
int main(void) {
    struct task_struct p = {.uclamp_req = {{0}, {1024}}};
    struct sched_attr a = {.sched_flags = SCHED_FLAG_UTIL_CLAMP_MAX, .sched_util_max = 600};
    assert(validate_update(&p, &a) == -EINVAL);
    assert(!rq_data.locked && sched_uclamp_used);
    a.sched_util_max = 900;
    assert(validate_update(&p, &a) == 0 && !rq_data.locked);
    a.sched_flags |= SCHED_FLAG_UTIL_CLAMP_MIN; a.sched_util_min = 256; a.sched_util_max = 768;
    assert(validate_update(&p, &a) == 0 && !rq_data.locked);
    a.sched_util_min = 769;
    assert(validate_update(&p, &a) == -EINVAL && !rq_data.locked);
    puts("PASS: partial clamp validation observes updates completed before rq lock acquisition");
}
''')
