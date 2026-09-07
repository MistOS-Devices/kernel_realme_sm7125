#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Check Manager API negotiation and bundled-module information."""
import re
from test_helpers import ROOT, function_body, run_c

header = (ROOT / 'drivers/kernelsu/include/uapi/supercall.h').read_text()
code = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <errno.h>
#include <stdio.h>
#define __user
#define pr_err(...) ((void)0)
#define KERNEL_SU_VERSION 33476
#define KSU_FEATURE_MAX 20
#define EXPECTED_SIZE2 1
typedef uint32_t __u32;
static bool ksu_bundled, manager, ksu_late_loaded;
static unsigned int ksuver_override;
static int copy_error;
static bool is_manager(void) { return manager; }
static int copy_to_user(void *dst, const void *src, size_t size) {
    if (copy_error) return 1;
    memcpy(dst, src, size);
    return 0;
}
'''
code += '\n'.join(re.findall(r'static const __u32 (?:KERNEL_SU_UAPI_VERSION|KSU_GET_INFO_FLAG_\w+) = [^;]+;', header))
for name in ['ksu_get_info_cmd', 'ksu_get_info_legacy_cmd']:
    code += re.search(r'struct ' + name + r' \{.*?\};', header, re.S).group()
for name in ['do_get_info', 'do_get_info_legacy']:
    code += f'static int {name}(void *arg)'
    code += function_body('drivers/kernelsu/supercall/dispatch.c', name)
code += r'''
int main(void) {
    assert(KERNEL_SU_UAPI_VERSION >= 4);
    assert(KSU_GET_INFO_FLAG_LKM == 1 && KSU_GET_INFO_FLAG_BUNDLED == 16);
    struct ksu_get_info_cmd info;
    struct ksu_get_info_legacy_cmd legacy;
    for (unsigned int bits = 0; bits < 8; bits++) {
        manager = bits & 1;
        ksu_bundled = bits & 2;
        ksu_late_loaded = bits & 4;
        unsigned int flags = KSU_GET_INFO_FLAG_PR_BUILD;
        if (manager) flags |= KSU_GET_INFO_FLAG_MANAGER;
        if (ksu_late_loaded) flags |= KSU_GET_INFO_FLAG_LATE_LOAD;
#ifdef MODULE
        flags |= KSU_GET_INFO_FLAG_LKM;
        if (ksu_bundled) flags |= KSU_GET_INFO_FLAG_BUNDLED;
#endif
        assert(do_get_info(&info) == 0 && info.flags == flags);
        assert(do_get_info_legacy(&legacy) == 0 && legacy.flags == flags);
        assert(info.version == KERNEL_SU_VERSION && legacy.version == KERNEL_SU_VERSION);
        assert(info.features == KSU_FEATURE_MAX && legacy.features == KSU_FEATURE_MAX);
#ifdef CONFIG_KSU_MANUAL_HOOK
        assert(info.uapi_version == KERNEL_SU_UAPI_VERSION);
#else
        assert(info.uapi_version == 2);
#endif
    }
    ksuver_override = 123;
    assert(do_get_info(&info) == 0 && info.version == 123);
    copy_error = 1;
    assert(do_get_info(&info) == -EFAULT && do_get_info_legacy(&legacy) == -EFAULT);
    puts("PASS: KernelSU reports API and bundled status for the actual hook/build mode");
}
'''
for defines in ['#define CONFIG_KSU_MANUAL_HOOK 1\n', '', '#define MODULE 1\n']:
    run_c(defines + code)
