#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Exercise production rq aggregation, idle transitions and fork state."""
from test_helpers import function_body, run_c

code = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#define SCHED_CAPACITY_SCALE 1024
#define UCLAMP_BUCKETS 5
#define UCLAMP_BUCKET_DELTA 205
#define UCLAMP_FLAG_IDLE 1
#define min_t(type, a, b) ((type)(a) < (type)(b) ? (type)(a) : (type)(b))
#define likely(x) (x)
#define unlikely(x) (x)
#define READ_ONCE(x) (x)
#define WRITE_ONCE(x, v) ((x) = (v))
#define SCHED_WARN_ON(x) assert(!(x))
#define lockdep_assert_held(p) assert(*(p))
enum uclamp_id {UCLAMP_MIN, UCLAMP_MAX, UCLAMP_CNT};
#define for_each_clamp_id(id) for ((id) = 0; (id) < UCLAMP_CNT; (id)++)
struct uclamp_se {unsigned int value, bucket_id; bool active, user_defined;};
struct uclamp_bucket {unsigned int value, tasks;};
struct uclamp_rq {unsigned int value; struct uclamp_bucket bucket[5];};
struct rq {struct uclamp_rq uclamp[2]; unsigned int uclamp_flags; int lock;} rq_data;
struct task_struct {struct uclamp_se uclamp[2], uclamp_req[2]; bool sched_reset_on_fork;};
struct rq_flags {int unused;};
static struct uclamp_se uclamp_default[2];
static struct rq *task_rq_lock(struct task_struct *p, struct rq_flags *rf) {
    assert(!rq_data.lock); rq_data.lock = 1; return &rq_data;
}
static void task_rq_unlock(struct rq *rq, struct task_struct *p, struct rq_flags *rf) {
    assert(rq->lock); rq->lock = 0;
}
'''
functions = [
    ('unsigned int uclamp_bucket_id(unsigned int clamp_value)', 'uclamp_bucket_id'),
    ('enum uclamp_id uclamp_none(enum uclamp_id clamp_id)', 'uclamp_none'),
    ('void uclamp_se_set(struct uclamp_se *uc_se, unsigned int value, bool user_defined)', 'uclamp_se_set'),
    ('unsigned int uclamp_idle_value(struct rq *rq, enum uclamp_id clamp_id, unsigned int clamp_value)', 'uclamp_idle_value'),
    ('void uclamp_idle_reset(struct rq *rq, enum uclamp_id clamp_id, unsigned int clamp_value)', 'uclamp_idle_reset'),
    ('enum uclamp_id uclamp_rq_max_value(struct rq *rq, enum uclamp_id clamp_id, unsigned int clamp_value)', 'uclamp_rq_max_value'),
    ('struct uclamp_se uclamp_tg_restrict(struct task_struct *p, enum uclamp_id clamp_id)', 'uclamp_tg_restrict'),
    ('struct uclamp_se uclamp_eff_get(struct task_struct *p, enum uclamp_id clamp_id)', 'uclamp_eff_get'),
    ('void uclamp_rq_inc_id(struct rq *rq, struct task_struct *p, enum uclamp_id clamp_id)', 'uclamp_rq_inc_id'),
    ('void uclamp_rq_dec_id(struct rq *rq, struct task_struct *p, enum uclamp_id clamp_id)', 'uclamp_rq_dec_id'),
    ('void uclamp_update_active(struct task_struct *p)', 'uclamp_update_active'),
    ('void uclamp_fork(struct task_struct *p)', 'uclamp_fork'),
    ('void init_uclamp_rq(struct rq *rq)', 'init_uclamp_rq'),
]
for signature, name in functions:
    code += '\nstatic ' + signature + '\n' + function_body('kernel/sched/core.c', name)
code += r'''
static void enqueue(struct task_struct *p) {
    rq_data.lock = 1;
    uclamp_rq_inc_id(&rq_data, p, UCLAMP_MIN);
    uclamp_rq_inc_id(&rq_data, p, UCLAMP_MAX);
    rq_data.uclamp_flags &= ~UCLAMP_FLAG_IDLE;
    rq_data.lock = 0;
}
static void dequeue(struct task_struct *p) {
    rq_data.lock = 1;
    uclamp_rq_dec_id(&rq_data, p, UCLAMP_MIN);
    uclamp_rq_dec_id(&rq_data, p, UCLAMP_MAX);
    rq_data.lock = 0;
}
int main(void) {
    uclamp_se_set(&uclamp_default[0], 1024, false);
    uclamp_se_set(&uclamp_default[1], 1024, false);
    init_uclamp_rq(&rq_data);
    struct task_struct a = {0}, b = {0}, untracked = {0};
    uclamp_se_set(&a.uclamp_req[0], 256, true);
    uclamp_se_set(&a.uclamp_req[1], 512, true);
    uclamp_se_set(&b.uclamp_req[0], 768, true);
    uclamp_se_set(&b.uclamp_req[1], 1024, true);
    enqueue(&a);
    assert(rq_data.uclamp[0].value == 256 && rq_data.uclamp[1].value == 512);
    enqueue(&b);
    assert(rq_data.uclamp[0].value == 768 && rq_data.uclamp[1].value == 1024);
    dequeue(&untracked); /* A task enqueued before the static key was enabled. */
    assert(rq_data.uclamp[0].value == 768);
    dequeue(&b);
    assert(rq_data.uclamp[0].value == 256 && rq_data.uclamp[1].value == 512);
    uclamp_se_set(&a.uclamp_req[1], 600, true);
    uclamp_update_active(&a);
    assert(a.uclamp[1].value == 600 && rq_data.uclamp[1].value == 600);
    assert(!(rq_data.uclamp_flags & UCLAMP_FLAG_IDLE));
    dequeue(&a);
    assert(rq_data.uclamp[0].value == 0 && rq_data.uclamp[1].value == 600);
    assert(rq_data.uclamp_flags & UCLAMP_FLAG_IDLE);
    enqueue(&a);
    struct task_struct child = a;
    uclamp_fork(&child);
    assert(!child.uclamp[0].active && !child.uclamp[1].active);
    assert(child.uclamp_req[0].value == 256 && child.uclamp_req[1].value == 600);
    child.sched_reset_on_fork = true;
    uclamp_fork(&child);
    assert(child.uclamp_req[0].value == 0 && child.uclamp_req[1].value == 1024);
    assert(!child.uclamp_req[0].user_defined && !child.uclamp_req[1].user_defined);
    dequeue(&a);
    for (int id = 0; id < 2; id++)
        for (int k = 0; k < 5; k++)
            assert(!rq_data.uclamp[id].bucket[k].tasks);
    puts("PASS: uclamp aggregation, active updates, idle retention and fork/reset");
}
'''
run_c(code)
