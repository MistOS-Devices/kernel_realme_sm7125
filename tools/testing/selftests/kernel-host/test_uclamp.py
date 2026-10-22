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
static bool sched_uclamp_used;
static void static_branch_enable(bool *key) { *key = true; }
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
    assert(uclamp_validate(&p, &a) == 0 && sched_uclamp_used);
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
