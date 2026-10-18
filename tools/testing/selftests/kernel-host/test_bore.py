#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Check BORE weights across idle policy and nice changes."""
import re
from test_helpers import ROOT, function_body, run_c

source = (ROOT / 'kernel/sched/core.c').read_text()
weights = re.search(r'const int sched_prio_to_weight\[40\] = \{.*?\};',
                    source, re.S).group()
code = r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
typedef int s32;
#define CONFIG_SCHED_BORE 1
#define MAX_RT_PRIO 100
#define PF_KTHREAD 1
#define min(a, b) ((a) < (b) ? (a) : (b))
#define scale_load(a) (a)
#define WEIGHT_IDLEPRIO 3
#define WMULT_IDLEPRIO 1431655765
struct load_weight { unsigned long weight, inv_weight; };
struct sched_entity {
    unsigned int burst_score, burst_penalty;
    struct load_weight load;
    bool group;
};
struct task_struct {
    struct sched_entity se;
    int static_prio, flags, policy;
};
static unsigned long sched_prio_to_wmult[40];
static int sched_burst_exclude_kthreads = 1;
static bool idle_policy(int policy) { return policy == 5; }
#define entity_is_task(se) (!(se)->group)
#define task_of(se) ((struct task_struct *)((char *)(se) - \
                    offsetof(struct task_struct, se)))
'''
code += weights
code += r'''
static void reweight_task(struct task_struct *p, int prio) {
    p->se.load.weight = sched_prio_to_weight[prio];
    p->se.load.inv_weight = sched_prio_to_wmult[prio];
}
static void set_load_weight(struct task_struct *p)
'''
code += function_body('kernel/sched/core.c', 'set_load_weight')
code += '\nstatic void update_burst_score(struct sched_entity *se)\n'
code += function_body('kernel/sched/fair.c', 'update_burst_score')
code += r'''
int main(void) {
    for (int i = 0; i < 40; i++)
        sched_prio_to_wmult[i] = 100 + i;
    struct task_struct p = { .static_prio = 120, .policy = 5 };
    set_load_weight(&p);
    p.se.burst_penalty = 4;
    update_burst_score(&p.se);
    assert(p.se.load.weight == WEIGHT_IDLEPRIO);
    assert(p.se.load.inv_weight == WMULT_IDLEPRIO);
    /* Idle tasks still track their penalty for a later normal policy. */
    assert(p.se.burst_score == 1);
    p.policy = 0;
    set_load_weight(&p);
    assert(p.se.load.weight == sched_prio_to_weight[21]);
    p.se.burst_penalty = 20;
    update_burst_score(&p.se);
    assert(p.se.load.weight == sched_prio_to_weight[25]);
    p.static_prio = 121; /* Same operation as the nice-change path. */
    set_load_weight(&p);
    update_burst_score(&p.se);
    assert(p.se.load.weight == sched_prio_to_weight[26]);
    assert(p.se.load.inv_weight == sched_prio_to_wmult[26]);
    p.static_prio = 139;
    set_load_weight(&p);
    assert(p.se.load.weight == sched_prio_to_weight[39]);
    p.policy = 5;
    set_load_weight(&p);
    p.se.burst_penalty = 0;
    update_burst_score(&p.se);
    assert(p.se.load.weight == WEIGHT_IDLEPRIO);
    p.policy = 0; p.flags = PF_KTHREAD; p.static_prio = 120;
    set_load_weight(&p);
    p.se.burst_penalty = 40;
    update_burst_score(&p.se);
    assert(p.se.burst_score == 0 && p.se.load.weight == 1024);
    p.se.group = true;
    update_burst_score(&p.se);
    assert(p.se.burst_score == 0);
    puts("PASS: BORE idle policy, nice changes, priority cap and exclusions");
}
'''
run_c(code)
