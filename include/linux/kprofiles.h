/* SPDX-License-Identifier: GPL-2.0 */
#ifndef _LINUX_KPROFILES_H
#define _LINUX_KPROFILES_H
#include <linux/errno.h>

#ifdef CONFIG_KPROFILES
int kp_active_mode(void);
int kp_set_mode(unsigned int level);
#else
static inline int kp_active_mode(void) { return 0; }
static inline int kp_set_mode(unsigned int level) { return -ENODEV; }
#endif
#endif
