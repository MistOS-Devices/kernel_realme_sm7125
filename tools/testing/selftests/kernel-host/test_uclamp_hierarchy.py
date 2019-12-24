#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Run production group creation and propagation over a small CSS hierarchy."""
from test_helpers import function_body, run_c
code = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#define CONFIG_UCLAMP_TASK_GROUP 1
#define UCLAMP_BUCKET_DELTA 205
#define UCLAMP_BUCKETS 5
#define SCHED_CAPACITY_SCALE 1024
#define min_t(type,a,b) ((type)(a) < (type)(b) ? (type)(a) : (type)(b))
#define min(a,b) ((a) < (b) ? (a) : (b))
enum uclamp_id {UCLAMP_MIN, UCLAMP_MAX, UCLAMP_CNT};
#define for_each_clamp_id(id) for ((id)=0; (id)<2; (id)++)
struct uclamp_se {unsigned int value, bucket_id; bool active, user_defined;};
struct task_group;
struct cgroup_subsys_state {struct task_group *tg; struct cgroup_subsys_state *parent, *next;};
struct task_group {struct task_group *parent; struct cgroup_subsys_state css; struct uclamp_se uclamp[2], uclamp_req[2];};
#define css_tg(c) ((c) ? (c)->tg : NULL)
#define css_for_each_descendant_pre(c,top) for ((c)=(top); (c); (c)=(c)->next)
static struct cgroup_subsys_state *css_rightmost_descendant(struct cgroup_subsys_state *c) {
    while (c->next) c=c->next; return c;
}
static int updates;
static void uclamp_update_active_tasks(struct cgroup_subsys_state *c) { updates++; }
static void sched_online_group(struct task_group *tg, struct task_group *parent) { tg->parent=parent; }
'''
for sig, name in [
 ('unsigned int uclamp_bucket_id(unsigned int clamp_value)', 'uclamp_bucket_id'),
 ('enum uclamp_id uclamp_none(enum uclamp_id clamp_id)', 'uclamp_none'),
 ('void uclamp_se_set(struct uclamp_se *uc_se, unsigned int value, bool user_defined)', 'uclamp_se_set'),
 ('void alloc_uclamp_sched_group(struct task_group *tg, struct task_group *parent)', 'alloc_uclamp_sched_group'),
 ('void cpu_util_update_eff(struct cgroup_subsys_state *css)', 'cpu_util_update_eff'),
 ('int cpu_cgroup_css_online(struct cgroup_subsys_state *css)', 'cpu_cgroup_css_online'),
]:
 code += '\nstatic '+sig+'\n'+function_body('kernel/sched/core.c', name)
code += r'''
int main(void) {
 struct task_group root={0}, parent={0}, child={0};
 root.css.tg=&root; parent.css.tg=&parent; child.css.tg=&child;
 parent.css.parent=&root.css; child.css.parent=&parent.css;
 for (int id=0;id<2;id++) uclamp_se_set(&root.uclamp[id],1024,false);
 alloc_uclamp_sched_group(&parent,&root);
 assert(cpu_cgroup_css_online(&parent.css)==0);
 assert(parent.uclamp[0].value==0 && parent.uclamp[1].value==1024);
 uclamp_se_set(&parent.uclamp_req[0],128,false);
 uclamp_se_set(&parent.uclamp_req[1],800,false);
 cpu_util_update_eff(&parent.css);
 alloc_uclamp_sched_group(&child,&parent);
 assert(cpu_cgroup_css_online(&child.css)==0);
 assert(child.uclamp[0].value==0 && child.uclamp[1].value==800);
 parent.css.next=&child.css;
 uclamp_se_set(&child.uclamp_req[0],256,false);
 cpu_util_update_eff(&child.css);
 assert(child.uclamp[0].value==128);
 uclamp_se_set(&parent.uclamp_req[1],64,false);
 cpu_util_update_eff(&parent.css);
 assert(parent.uclamp[0].value==64 && child.uclamp[0].value==64);
 assert(child.uclamp[1].value==64 && child.uclamp[1].bucket_id==uclamp_bucket_id(64));
 int before=updates; cpu_util_update_eff(&parent.css); assert(updates==before);
 puts("PASS: new groups default to no floor, hierarchy limits and unchanged subtree propagation");
}
'''
run_c(code)
