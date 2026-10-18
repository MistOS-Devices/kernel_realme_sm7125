#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Check suspend sync failures reach sysfs as errors, not byte counts."""
from test_helpers import function_body, run_c

code = r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <errno.h>
#include <sys/types.h>
#define OPLUS_BUG_STABILITY 1
#define PM_SUSPEND_ON 0
#define PM_SUSPEND_TO_IDLE 1
#define PM_SUSPEND_MEM 3
#define PM_SUSPEND_MAX 4
#define TEST_FREEZER 1
#define trace_suspend_resume(...) ((void)0)
#define pm_pr_dbg(...) ((void)0)
typedef int suspend_state_t;
struct kobject {};
struct kobj_attribute {};
static int pm_mutex, mem_sleep_current = PM_SUSPEND_MEM;
static int sync_error, device_error, prepares, finishes;
static bool events_check_enabled;
static bool valid_state(int state) { return state == PM_SUSPEND_MEM; }
static bool mutex_trylock(int *lock) { assert(!*lock); *lock = 1; return true; }
static void mutex_unlock(int *lock) { assert(*lock); *lock = 0; }
static void s2idle_begin(void) {}
static int sys_sync_queue(void) { return sync_error; }
static void pm_suspend_clear_flags(void) {}
static int suspend_prepare(int state) { prepares++; return 0; }
static bool suspend_test(int level) { return false; }
static void pm_restrict_gfp_mask(void) {}
static void pm_restore_gfp_mask(void) {}
static int suspend_devices_and_enter(int state) { return device_error; }
static void suspend_finish(void) { finishes++; }
static int pm_autosleep_lock(void) { return 0; }
static void pm_autosleep_unlock(void) {}
static int pm_autosleep_state(void) { return PM_SUSPEND_ON; }
static int decode_state(const char *buf, size_t n) { return PM_SUSPEND_MEM; }
static int hibernate(void) { return -EOPNOTSUPP; }
static int enter_state(suspend_state_t state)
'''
code += function_body('kernel/power/suspend.c', 'enter_state')
code += r'''
static int pm_suspend(suspend_state_t state) { return enter_state(state); }
static ssize_t state_store(struct kobject *kobj, struct kobj_attribute *attr,
                           const char *buf, size_t n)
'''
code += function_body('kernel/power/main.c', 'state_store')
code += r'''
int main(void) {
    sync_error = -EAGAIN;
    assert(state_store(NULL, NULL, "mem", 3) == -EAGAIN);
    assert(!pm_mutex && prepares == 0 && finishes == 0);
    sync_error = 0;
    assert(state_store(NULL, NULL, "mem", 3) == 3);
    assert(!pm_mutex && prepares == 1 && finishes == 1);
    device_error = -EBUSY;
    assert(state_store(NULL, NULL, "mem", 3) == -EBUSY);
    assert(!pm_mutex && prepares == 2 && finishes == 2);
    puts("PASS: suspend sync abort, successful write and device error");
}
'''
run_c(code)
