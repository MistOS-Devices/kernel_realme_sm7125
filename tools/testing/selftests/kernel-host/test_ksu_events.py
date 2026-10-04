#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Only one services caller may start per post-fs-data cycle."""
import os
import re
from test_helpers import ROOT, function_body, run_c

code = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <stdatomic.h>
#include <pthread.h>
#include <errno.h>
#include <stdio.h>
#define __user
#define pr_info(...) ((void)0)
#define CONFIG_KSU_SUSFS 1
#define ATOMIC_INIT(v) (v)
typedef _Atomic int atomic_t;
static void atomic_set(atomic_t *p, int value) { atomic_store(p, value); }
static int atomic_xchg(atomic_t *p, int value) { return atomic_exchange(p, value); }
typedef uint32_t __u32;
static int copy_error, post_fs, boot, mounted, monitored;
static bool ksu_late_loaded;
static int copy_from_user(void *dst, const void *src, size_t size) {
    if (copy_error) return 1;
    memcpy(dst, src, size);
    return 0;
}
static void on_post_fs_data(void) { post_fs++; }
static void on_boot_completed(void) { boot++; }
static void on_module_mounted(void) { mounted++; }
static void susfs_start_sdcard_monitor_fn(void) { monitored++; }
'''
header = (ROOT / 'drivers/kernelsu/include/uapi/supercall.h').read_text()
# Use the wire values as integer constants for switch labels on GCC too.
events = re.findall(r'static const __u32 (EVENT_\w+) = (\d+);', header)
code += '\n'.join(f'#define {name} {value}' for name, value in events) + '\n'
code += re.search(r'struct ksu_report_event_cmd \{.*?\};', header, re.S).group()
code += 'static int do_report_event(void *arg)'
code += function_body('drivers/kernelsu/supercall/dispatch.c', 'do_report_event')
code += r'''
static int report(unsigned int event) {
    struct ksu_report_event_cmd cmd = { .event = event };
    return do_report_event(&cmd);
}
static void *start_service(void *result) { *(int *)result = report(EVENT_SERVICES); return NULL; }
int main(void) {
    assert(EVENT_SERVICES == 4);
    copy_error = 1;
    assert(report(EVENT_SERVICES) == -EFAULT);
    copy_error = 0;
    assert(report(EVENT_SERVICES) == 1);
    assert(report(EVENT_SERVICES) == 0);
    assert(report(EVENT_BOOT_COMPLETED) == 0);
    assert(report(EVENT_BOOT_COMPLETED) == 0 && boot == 1 && monitored == 1);
    assert(report(EVENT_MODULE_MOUNTED) == 0 && mounted == 1);
    assert(report(999) == 0 && report(EVENT_SERVICES) == 0);
    for (int cycle = 0; cycle < 8; cycle++) {
        assert(report(EVENT_POST_FS_DATA) == 0);
        pthread_t threads[12];
        int results[12], starts = 0;
        for (int i = 0; i < 12; i++)
            assert(pthread_create(&threads[i], NULL, start_service, &results[i]) == 0);
        for (int i = 0; i < 12; i++) {
            assert(pthread_join(threads[i], NULL) == 0);
            assert(results[i] == 0 || results[i] == 1);
            starts += results[i];
        }
        assert(starts == 1 && post_fs == 1);
    }
    ksu_late_loaded = true;
    assert(report(EVENT_POST_FS_DATA) == 0 && report(EVENT_SERVICES) == 1);
    assert(post_fs == 1);
    puts("PASS: KernelSU services start once, reset on post-fs-data and preserve SUSFS boot handling");
}
'''
os.environ['HOSTCC'] = os.environ.get('HOSTCC', 'cc') + ' -pthread'
run_c(code)
