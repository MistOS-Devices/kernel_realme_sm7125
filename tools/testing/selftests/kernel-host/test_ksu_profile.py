#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Credential setup must fail closed before granting a su session."""
from test_helpers import function_body, run_c

code = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <stdio.h>
#define KERNEL_VERSION(a,b,c) (((a)<<16)+((b)<<8)+(c))
#ifndef LINUX_VERSION_CODE
#define LINUX_VERSION_CODE KERNEL_VERSION(4,14,0)
#endif
#define KSU_MAX_GROUPS 32
#define TIF_KSU_DISABLE_ESCAPE_WITH_ROOT 1
#define FLAG_KSU_NO_NEW_PRIVS 1
#define CAP_DAC_READ_SEARCH 2
#define BUILD_BUG_ON(x) _Static_assert(!(x), "size")
#define pr_warn(...) ((void)0)
#define pr_err(...) ((void)0)
#define KERNEL_SU_CONTEXT "u:r:ksu:s0"
typedef uint32_t u32;
typedef uint64_t u64;
typedef uint64_t kernel_cap_t;
typedef unsigned int gid_t;
typedef unsigned int kgid_t;
struct uid { int val; };
struct user_struct { int unused; };
struct group_info { kgid_t gid[32]; };
struct cred {
    struct uid uid, suid, euid, fsuid, gid, fsgid, sgid, egid;
    int securebits;
    uint64_t cap_effective, cap_permitted, cap_bset;
    struct group_info *group_info;
    struct user_struct *user;
};
struct root_profile {
    int uid, gid;
    u32 groups_count;
    int groups[32];
    struct { uint64_t effective; } capabilities;
    const char *selinux_domain;
    int namespaces;
    uint64_t flags;
};
static struct root_profile selected = { .uid = 2000, .gid = 2000 };
static struct group_info root_groups;
static struct user_struct user;
static struct cred pending;
static int prepare_error, user_error, groups_error, domain_error, ucounts_error;
static int allocated_groups, prepared, profiles, commits, post_commit, initial_euid = 10000;
static bool disabled;
static struct group_info *groups_alloc(u32 n) {
    if (groups_error) return NULL;
    allocated_groups++;
    return calloc(1, sizeof(struct group_info));
}
static struct group_info *get_group_info(struct group_info *g) { return g; }
static void put_group_info(struct group_info *g) {
    if (g != &root_groups) { free(g); allocated_groups--; }
}
static int current_user_ns(void) { return 0; }
static kgid_t make_kgid(int ns, gid_t gid) { return gid; }
static bool gid_valid(kgid_t gid) { return gid != (kgid_t)-1; }
static void groups_sort(struct group_info *g) {}
static void set_groups(struct cred *c, struct group_info *g) {}
static struct cred *prepare_creds(void) {
    if (prepare_error) return NULL;
    memset(&pending, 0, sizeof(pending));
    pending.euid.val = initial_euid;
    prepared++;
    return &pending;
}
static void abort_creds(struct cred *c) { prepared--; }
static void commit_creds(struct cred *c) { prepared--; commits++; }
static bool test_thread_flag(int flag) { return disabled; }
static void set_thread_flag(int flag) { disabled = true; }
static struct root_profile *ksu_get_root_profile(int uid) { profiles++; return &selected; }
static void ksu_put_root_profile(struct root_profile *p) { profiles--; }
static struct user_struct *alloc_uid(struct uid uid) { return user_error ? NULL : &user; }
static void free_uid(struct user_struct *u) {}
static int set_cred_ucounts(struct cred *c) { return ucounts_error; }
static int transive_to_domain(const char *domain, struct cred *c, bool clear) { return domain_error; }
static void disable_seccomp(void) { post_commit++; }
static void setup_mount_ns(int ns) { post_commit++; }
static int setup_groups(struct root_profile *profile, struct cred *cred)
'''
code += function_body('drivers/kernelsu/policy/app_profile.c', 'setup_groups')
code += 'static int setup_selinux(const char *domain, struct cred *cred)'
code += function_body('drivers/kernelsu/selinux/selinux.c', 'setup_selinux')
code += 'int escape_with_root_profile(void)'
code += function_body('drivers/kernelsu/policy/app_profile.c', 'escape_with_root_profile')
code += 'void escape_to_root_for_init(void)'
code += function_body('drivers/kernelsu/policy/app_profile.c', 'escape_to_root_for_init')
code += r'''
static void check_error(int error) {
    assert(escape_with_root_profile() == error);
    assert(!prepared && !profiles && !allocated_groups && !commits && !post_commit);
}
int main(void) {
    prepare_error = 1; check_error(-ENOMEM); prepare_error = 0;
    disabled = true; check_error(-EPERM); disabled = false;
    user_error = 1; check_error(-ENOMEM); user_error = 0;
    groups_error = 1; check_error(-ENOMEM); groups_error = 0;
    selected.groups_count = 33; check_error(-EINVAL);
    selected.groups_count = 1; selected.groups[0] = -1; check_error(-EINVAL);
    selected.groups[0] = 0;
    domain_error = -EINVAL; check_error(-EINVAL);
    escape_to_root_for_init(); assert(!prepared && !commits);
    domain_error = 0;
#if LINUX_VERSION_CODE >= KERNEL_VERSION(5,14,0)
    ucounts_error = -EUSERS; check_error(-EUSERS); ucounts_error = 0;
#endif
    initial_euid = 0;
    assert(escape_with_root_profile() == 0 && !prepared && !commits);
    initial_euid = 10000;
    assert(escape_with_root_profile() == 0 && commits == 1 && post_commit == 2);
    assert(pending.euid.val == 2000 && !profiles && !prepared);
    puts("PASS: KernelSU credential failures abort before commit");
}
'''
run_c(code)
run_c('#define LINUX_VERSION_CODE ((5<<16)+(14<<8))\n' + code)
