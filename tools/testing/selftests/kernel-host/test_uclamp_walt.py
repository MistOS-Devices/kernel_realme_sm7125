#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Check WALT frequency votes and placement against per-task/rq clamps."""
from test_helpers import function_body, run_c

run_c(r'''
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdint.h>
#define CONFIG_UCLAMP_TASK 1
#define READ_ONCE(x) (x)
#define unlikely(x) (x)
#define max(a,b) ((a) > (b) ? (a) : (b))
#define clamp(v,l,h) ((v) < (l) ? (l) : ((v) > (h) ? (h) : (v)))
#define mult_frac(x,n,d) ((x) * (n) / (d))
#define per_cpu(a,j) (a[j])
#define for_each_cpu(j,cpus) for ((j) = 0; (j) < (unsigned)(cpus); (j)++)
#define SCHED_CPUFREQ_RT_DL 1
#define trace_sched_boost_task(...) ((void)0)
typedef uint64_t u64;
typedef int64_t s64;
enum uclamp_id {UCLAMP_MIN, UCLAMP_MAX};
struct task_struct {unsigned long util, min, max; long boost;};
struct rq {struct {unsigned long value;} uclamp[2];} queues[2];
static bool sched_uclamp_used = true;
static bool static_branch_likely(bool *p) {return *p;}
static unsigned long uclamp_eff_value(struct task_struct *p, enum uclamp_id id) {
    return id == UCLAMP_MIN ? p->min : p->max;
}
static struct rq *cpu_rq(int cpu) {return &queues[cpu];}
static unsigned long task_util_est(struct task_struct *p) {return p->util;}
static long schedtune_task_margin(struct task_struct *p) {return p->boost;}
static unsigned long uclamp_util_with(struct rq *rq, unsigned long util, struct task_struct *p)
''' + function_body('kernel/sched/sched.h', 'uclamp_util_with') + r'''
static bool uclamp_is_used(void) {return sched_uclamp_used;}
struct cpufreq_policy {int cpus; unsigned int min; struct {unsigned int max_freq;} cpuinfo;};
struct sugov_policy {struct cpufreq_policy *policy;};
struct sugov_cpu {
    struct sugov_policy *sg_policy;
    unsigned long util, max, iowait_boost, iowait_boost_max, predicted;
    bool iowait_boost_pending;
    unsigned int flags;
    u64 last_update;
    int cpu;
} sugov_cpu[2];
static s64 stale_ns = 20000;
static void sugov_iowait_boost(struct sugov_cpu *sg_cpu, unsigned long *util, unsigned long *max)
''' + function_body('kernel/sched/cpufreq_schedutil.c', 'sugov_iowait_boost') + r''' 
static void sugov_walt_adjust(struct sugov_cpu *c, unsigned long *u, unsigned long *m) {
    *u = max(*u, c->predicted);
}
static unsigned int get_next_freq(struct sugov_policy *p, unsigned long u, unsigned long m) {
    return u * 1024 / m;
}
static unsigned int sugov_next_freq_shared(struct sugov_cpu *sg_cpu, u64 time)
''' + function_body('kernel/sched/cpufreq_schedutil.c', 'sugov_next_freq_shared') + r'''
static unsigned long boosted_task_util(struct task_struct *task)
''' + function_body('kernel/sched/fair.c', 'boosted_task_util') + r'''
int main(void) {
    struct cpufreq_policy p = {.cpus = 2, .min = 300000, .cpuinfo.max_freq = 1800000};
    struct sugov_policy sp = {&p};
    for (int i = 0; i < 2; i++) {
        sugov_cpu[i] = (struct sugov_cpu){.sg_policy = &sp, .util = 100,
                                        .max = 1024, .last_update = 100, .cpu = i};
        queues[i].uclamp[0].value = 0; queues[i].uclamp[1].value = 1024;
    }
    queues[0].uclamp[0].value = 640;
    assert(sugov_next_freq_shared(&sugov_cpu[0], 100) == 640);
    queues[0].uclamp[0].value = 0; queues[0].uclamp[1].value = 512;
    sugov_cpu[0].predicted = 1024;
    assert(sugov_next_freq_shared(&sugov_cpu[0], 100) == 512);
    sugov_cpu[1].util = 768;
    assert(sugov_next_freq_shared(&sugov_cpu[0], 100) == 768);
    sugov_cpu[1].last_update = 0;
    sugov_cpu[0].last_update = 20001;
    assert(sugov_next_freq_shared(&sugov_cpu[0], 20001) == 512);
    /* Production I/O boost stores kHz; its output must stay in capacity units. */
    struct sugov_cpu *c = &sugov_cpu[0];
    unsigned long util = 100, capacity = 1024;
    c->iowait_boost = 600000; c->iowait_boost_max = 1800000;
    c->iowait_boost_pending = true;
    sugov_iowait_boost(c, &util, &capacity);
    assert(capacity == 1024 && util == 341 && !c->iowait_boost_pending);
    util = 100;
    sugov_iowait_boost(c, &util, &capacity);
    assert(capacity == 1024 && util == 170 && c->iowait_boost == 300000);
    util = 100;
    sugov_iowait_boost(c, &util, &capacity);
    assert(util == 100 && c->iowait_boost == 0);
    c->predicted = 0; c->iowait_boost = 1800000; c->iowait_boost_pending = true;
    assert(sugov_next_freq_shared(c, 20001) == 512);
    queues[0].uclamp[1].value = 1024;
    c->iowait_boost_pending = true;
    assert(sugov_next_freq_shared(c, 20001) == 1024);
    struct task_struct task = {.util = 100, .min = 640, .max = 1024, .boost = 20};
    assert(boosted_task_util(&task) == 640);
    task.min = 0; task.max = 256; task.util = 800;
    assert(boosted_task_util(&task) == 256);
    sched_uclamp_used = false;
    assert(boosted_task_util(&task) == 820);
    puts("PASS: WALT clamp floor/cap, shared-policy peer votes, staleness and task placement");
}
''')
