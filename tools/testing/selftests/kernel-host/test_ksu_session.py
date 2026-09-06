#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Exercise scoped su descriptors, permission boundaries and exec handoff."""
import re
from test_helpers import ROOT, function_body, run_c

base = 'drivers/kernelsu/'
supercall = base + 'supercall/supercall.c'
dispatch = base + 'supercall/dispatch.c'
source = (ROOT / supercall).read_text()
table = (ROOT / dispatch).read_text().split(
    'static const struct ksu_ioctl_cmd_map ksu_ioctl_handlers[] = ', 1)[1].split(
    '// clang-format on', 1)[0]
commands = re.findall(r'\.cmd = (KSU_IOCTL_\w+)', table)
handlers = set(re.findall(r'\.handler = (\w+)', table)) - {'NULL'}
permissions = set(re.findall(r'\.perm_check = (\w+)', table)) - {'NULL'}
code = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#define __user
#define GFP_KERNEL 0
#define pr_info(...) ((void)0)
#define pr_warn(...) ((void)0)
#define pr_err(...) ((void)0)
#define IS_ERR(p) ((intptr_t)(p) < 0 && (intptr_t)(p) >= -4095)
#define PTR_ERR(p) ((intptr_t)(p))
struct inode {};
struct file { void *private_data; };
static struct file installed;
static int alloc_error, fd_error, inode_error, allocated, reserved, installs;
static bool permitted;
static int anon_ksu_fops;
static void *kzalloc(size_t size, int flags) {
    if (alloc_error) return NULL;
    allocated++;
    return calloc(1, size);
}
static void kfree(void *p) { if (p) { allocated--; free(p); } }
static int get_unused_fd_flags(unsigned int flags) {
    assert(flags == O_CLOEXEC);
    if (fd_error) return -EMFILE;
    reserved++;
    return 7;
}
static void put_unused_fd(int fd) { assert(fd == 7); reserved--; }
static struct file *anon_inode_getfile(const char *name, void *ops,
                                      void *data, int flags) {
    assert(flags == O_RDWR);
    assert(!strcmp(name, "[ksu_driver]") || !strcmp(name, "[ksu_driver_su]"));
    if (inode_error) return (void *)(intptr_t)-ENOMEM;
    installed.private_data = data;
    return &installed;
}
static void fd_install(int fd, struct file *f) { reserved--; installs++; }
'''
code += source[source.index('#define KSU_DRIVER_PERMISSION_SU_SESSION'):
               source.index('static int anon_ksu_release')]
for signature, name in [
    ('static int anon_ksu_release(struct inode *inode, struct file *filp)', 'anon_ksu_release'),
    ('static int ksu_install_fd_with_permissions(unsigned int fd_flags, unsigned long permissions)', 'ksu_install_fd_with_permissions'),
    ('int ksu_install_fd(void)', 'ksu_install_fd'),
    ('int ksu_install_su_fd(void)', 'ksu_install_su_fd'),
    ('bool ksu_is_su_session_fd(const struct file *filp)', 'ksu_is_su_session_fd'),
]:
    code += signature + function_body(supercall, name)
code += (ROOT / (base + 'supercall/supercall.h')).read_text().split(
    '// IOCTL handler types', 1)[1].split('// Install KSU fd', 1)[0]
for name in permissions:
    code += f'static bool {name}(void) {{ return permitted; }}\n'
for name in handlers:
    code += f'static int {name}(void *arg) {{ return 123; }}\n'
code += 'enum { ' + ', '.join(commands) + ' };\n'
code += 'static const struct ksu_ioctl_cmd_map ksu_ioctl_handlers[] = ' + table
code += 'long ksu_supercall_handle_ioctl(const struct file *filp, unsigned int cmd, void *argp)'
code += function_body(dispatch, 'ksu_supercall_handle_ioctl')
code += r'''
int main(void) {
    struct file empty = {0};
    assert(!ksu_is_su_session_fd(&empty));
    alloc_error = 1;
    assert(ksu_install_su_fd() == -ENOMEM);
    alloc_error = 0; fd_error = 1;
    assert(ksu_install_su_fd() == -EMFILE);
    fd_error = 0; inode_error = 1;
    assert(ksu_install_su_fd() == -ENOMEM);
    assert(!allocated && !reserved && !installs);
    inode_error = 0;
    assert(ksu_install_fd() == 7);
    assert(!ksu_is_su_session_fd(&installed));
    assert(ksu_supercall_handle_ioctl(&installed, KSU_IOCTL_GET_WRAPPER_FD, NULL) == -EPERM);
    anon_ksu_release(NULL, &installed);
    assert(ksu_install_su_fd() == 7);
    assert(ksu_is_su_session_fd(&installed));
    for (int i = 0; ksu_ioctl_handlers[i].handler; i++) {
        unsigned int cmd = ksu_ioctl_handlers[i].cmd;
        bool scoped = cmd == KSU_IOCTL_GET_WRAPPER_FD || cmd == KSU_IOCTL_DISABLE_ESCAPE_TO_ROOT;
        assert(ksu_supercall_handle_ioctl(&installed, cmd, NULL) == (scoped ? 123 : -EPERM));
        permitted = true;
        assert(ksu_supercall_handle_ioctl(&installed, cmd, NULL) == 123);
        permitted = false;
    }
    assert(ksu_supercall_handle_ioctl(&installed, ~0U, NULL) == -ENOTTY);
    anon_ksu_release(NULL, &installed);
    assert(!allocated && !reserved);
    puts("PASS: KernelSU scoped descriptors preserve permission boundaries and cleanup");
}
'''
run_c(code)

code = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <errno.h>
#include <stdio.h>
#define CONFIG_KSU 1
#define CONFIG_KSU_MANUAL_HOOK 1
#define unlikely(x) (x)
#define likely(x) (x)
#define IS_ERR(p) ((intptr_t)(p) < 0 && (intptr_t)(p) >= -4095)
#define IS_ERR_OR_NULL(p) (!(p) || IS_ERR(p))
#define pr_info(...) ((void)0)
#define pr_warn(...) ((void)0)
#define pr_err(...) ((void)0)
#define ksu_sulog_emit(...) ((void)0)
#define SU_PATH "/system/bin/su"
#define KSUD_PATH "/data/adb/ksud"
struct filename { char name[128]; };
struct user_arg_ptr { int unused; };
struct uid { unsigned int val; };
static struct uid current_uid(void) { return (struct uid){2000}; }
static bool allowed, ksu_su_compat_enabled = true;
static int profile_error, profile_calls, exec_error, exec_calls, installs, puts_count, install_error;
static bool ksu_is_allow_uid_for_current(unsigned int uid) { return allowed; }
static int escape_with_root_profile(void) { profile_calls++; return profile_error; }
static void putname(struct filename *f) { puts_count++; }
static int ksu_install_su_fd(void) { assert(exec_calls); installs++; return install_error ? -EMFILE : 7; }
static int __do_execve_file(int fd, struct filename *name, struct user_arg_ptr argv,
                           struct user_arg_ptr envp, int flags, void *file) {
    exec_calls++;
    putname(name);
    return exec_error;
}
static int ksu_handle_execveat_sucompat(int *fd, struct filename **filename_ptr,
                                      void *__never_use_argv, void *__never_use_envp,
                                      int *__never_use_flags)
'''
code += function_body(base + 'feature/sucompat.c', 'ksu_handle_execveat_sucompat')
code += r'''
static int ksu_handle_execveat(int *fd, struct filename **name, void *argv, void *envp, int *flags) {
    assert(fd && *fd == -100 && flags && !*flags);
    return ksu_handle_execveat_sucompat(fd, name, argv, envp, flags);
}
static int do_execveat_common(int fd, struct filename *filename,
                              struct user_arg_ptr argv, struct user_arg_ptr envp, int flags)
'''
code += function_body('fs/exec.c', 'do_execveat_common')
code += r'''
static int execute(const char *path) {
    struct filename name;
    strcpy(name.name, path);
    return do_execveat_common(-100, &name, (struct user_arg_ptr){0}, (struct user_arg_ptr){0}, 0);
}
int main(void) {
    assert(execute(SU_PATH) == 0 && !installs && !profile_calls);
    allowed = true;
    assert(execute("/system/bin/sh") == 0 && !installs && !profile_calls);
    ksu_su_compat_enabled = false;
    assert(execute(SU_PATH) == 0 && !installs && !profile_calls);
    ksu_su_compat_enabled = true;
    profile_error = -EPERM;
    assert(execute(SU_PATH) == -EPERM && !installs && exec_calls == 3);
    profile_error = 0; exec_error = -ENOENT;
    assert(execute(SU_PATH) == -ENOENT && !installs && exec_calls == 4);
    exec_error = 0;
    assert(execute(SU_PATH) == 0 && puts_count == 6);
#ifdef CONFIG_KSU_MANUAL_HOOK
    assert(installs == 1);
    install_error = 1;
    assert(execute(SU_PATH) == 0 && installs == 2);
#else
    assert(!installs);
#endif
    assert(ksu_handle_execveat_sucompat(NULL, NULL, NULL, NULL, NULL) == 0);
    struct filename *bad = (void *)(intptr_t)-ENOENT;
    assert(ksu_handle_execveat_sucompat(NULL, &bad, NULL, NULL, NULL) == 0);
    puts("PASS: KernelSU grants scoped access only after authorized successful exec");
}
'''
run_c(code)

run_c(code.replace("#define CONFIG_KSU_MANUAL_HOOK 1", ""))
