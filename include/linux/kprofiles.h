/* SPDX-License-Identifier: GPL-2.0 */
#ifndef _LINUX_KPROFILES_H
#define _LINUX_KPROFILES_H
#include <linux/errno.h>
#include <linux/kernel.h>

#ifdef CONFIG_KPROFILES
int kp_active_mode(void);
int kp_set_mode(unsigned int level);
#else
static inline int kp_active_mode(void) { return 0; }
static inline int kp_set_mode(unsigned int level) { return -ENODEV; }
#endif
/* Scale only new input votes; leave explicit max/wake boosts untouched. */
static inline unsigned int kp_input_boost_duration(unsigned int duration_ms)
{
	unsigned int half = duration_ms / 2 + (duration_ms & 1);
	int mode = kp_active_mode();

	if (mode == 1)
		return half;
	if (mode == 3)
		return half > UINT_MAX - duration_ms ? UINT_MAX : duration_ms + half;
	return duration_ms;
}
#endif
