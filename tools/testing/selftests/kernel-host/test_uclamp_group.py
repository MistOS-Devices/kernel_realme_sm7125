#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Exercise production group restrictions, including explicit ADPF requests."""
from test_helpers import function_body, run_c

code = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#define CONFIG_UCLAMP_TASK_GROUP 1
#define UCLAMP_BUCKET_DELTA 205
#define UCLAMP_BUCKETS 5
#define min_t(type, a, b) ((type)(a) < (type)(b) ? (type)(a) : (type)(b))
#define clamp(v, lo, hi) ((v) < (lo) ? (lo) : ((v) > (hi) ? (hi) : (v)))
#define WARN_ON_ONCE(x) assert(!(x))
enum uclamp_id {UCLAMP_MIN, UCLAMP_MAX, UCLAMP_CNT};
struct uclamp_se {unsigned int value, bucket_id; bool active, user_defined;};
struct task_group {struct uclamp_se uclamp[2]; bool autogroup;};
struct task_struct {struct task_group *group; struct uclamp_se uclamp_req[2];};
static struct task_group root_task_group;
#define task_group(p) ((p)->group)
#define task_group_is_autogroup(g) ((g)->autogroup)
'''
for signature, name in [
    ('unsigned int uclamp_bucket_id(unsigned int clamp_value)', 'uclamp_bucket_id'),
    ('void uclamp_se_set(struct uclamp_se *uc_se, unsigned int value, bool user_defined)', 'uclamp_se_set'),
    ('struct uclamp_se uclamp_tg_restrict(struct task_struct *p, enum uclamp_id clamp_id)', 'uclamp_tg_restrict'),
]:
    code += '\nstatic ' + signature + '\n' + function_body('kernel/sched/core.c', name)
code += r'''
int main(void) {
    struct task_group group = {0};
    struct task_struct p = {.group = &group};
    uclamp_se_set(&group.uclamp[0], 128, false);
    uclamp_se_set(&group.uclamp[1], 1024, false);
    uclamp_se_set(&p.uclamp_req[0], 0, false);
    uclamp_se_set(&p.uclamp_req[1], 1024, false);
    assert(uclamp_tg_restrict(&p, UCLAMP_MIN).value == 128);
    uclamp_se_set(&p.uclamp_req[0], 768, true);
    assert(uclamp_tg_restrict(&p, UCLAMP_MIN).value == 768);
    group.uclamp[0].value = 0;
    assert(uclamp_tg_restrict(&p, UCLAMP_MIN).value == 768);
    group.uclamp[1].value = 512;
    assert(uclamp_tg_restrict(&p, UCLAMP_MAX).value == 512);
    assert(uclamp_tg_restrict(&p, UCLAMP_MIN).value == 512);
    assert(uclamp_tg_restrict(&p, UCLAMP_MIN).bucket_id == uclamp_bucket_id(512));
    group.uclamp[0].value = 384;
    uclamp_se_set(&p.uclamp_req[1], 128, true);
    assert(uclamp_tg_restrict(&p, UCLAMP_MAX).value == 384);
    assert(uclamp_tg_restrict(&p, UCLAMP_MAX).bucket_id == uclamp_bucket_id(384));
    p.group = &root_task_group;
    assert(uclamp_tg_restrict(&p, UCLAMP_MIN).value == 768);
    group.autogroup = true; p.group = &group;
    assert(uclamp_tg_restrict(&p, UCLAMP_MIN).value == 768);
    puts("PASS: group minimum protects tasks and preserves higher ADPF requests");
}
'''
run_c(code)
# Build the same production helper with group support disabled.
run_c(code.replace('#define CONFIG_UCLAMP_TASK_GROUP 1', '').split('int main(void)')[0] + r'''
int main(void) {
    struct task_struct p = {.group = &root_task_group};
    uclamp_se_set(&p.uclamp_req[0], 768, true);
    assert(uclamp_tg_restrict(&p, UCLAMP_MIN).value == 768);
    puts("PASS: group-disabled restriction preserves per-task requests");
}
''')
