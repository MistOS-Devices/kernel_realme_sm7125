#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Exercise userspace limits and boosts through production devfreq code."""
from test_helpers import function_body, run_c

code = r'''
#include <assert.h>
#include <stdbool.h>
#include <limits.h>
#include <stdio.h>
#include <sys/types.h>
#define EINVAL 22
#define BIT(n) (1UL << (n))
#define READ_ONCE(x) (x)
#define min(a, b) ((a) < (b) ? (a) : (b))
#define max(a, b) ((a) > (b) ? (a) : (b))
#define WARN(...) ((void)0)
#define dev_err(...) ((void)0)
#define DEVFREQ_FLAG_LEAST_UPPER_BOUND 1
#define DEVFREQ_PRECHANGE 0
#define DEVFREQ_POSTCHANGE 1
typedef unsigned int u32;
enum { SCREEN_OFF, INPUT_BOOST, MAX_BOOST };
struct mutex { bool held; };
static void mutex_lock(struct mutex *m) { assert(!m->held); m->held = true; }
static void mutex_unlock(struct mutex *m) { assert(m->held); m->held = false; }
static bool mutex_is_locked(struct mutex *m) { return m->held; }
static struct mutex devfreq_boost_lock;
struct devfreq;
struct device { struct devfreq *df; struct device *parent; };
struct device_attribute { int unused; };
struct devfreq_dev_profile {
    unsigned long *freq_table;
    int (*get_cur_freq)(struct device *, unsigned long *);
    int (*target)(struct device *, unsigned long *, u32);
};
struct devfreq_governor { int (*get_target_freq)(struct devfreq *, unsigned long *); };
struct devfreq {
    struct mutex lock, event_lock;
    struct device dev;
    struct devfreq_dev_profile *profile;
    struct devfreq_governor *governor;
    unsigned long min_freq, max_freq, boost_min_freq, previous_freq;
    bool max_boost, is_boost_device;
};
struct boost_dev { struct devfreq *df; unsigned long state, boost_freq; };
struct devfreq_freqs { unsigned long old, new; };
#define to_devfreq(dev) ((dev)->df)
static unsigned long demand = 1000, target;
static int get_target(struct devfreq *df, unsigned long *freq) { *freq = demand; return 0; }
static int set_target(struct device *dev, unsigned long *freq, u32 flags) {
    target = *freq; return 0;
}
static void devfreq_notify_transition(struct devfreq *df, struct devfreq_freqs *freqs, int state) {}
static int devfreq_update_status(struct devfreq *df, unsigned long freq) { return 0; }
int update_devfreq(struct devfreq *devfreq)
'''
code += function_body('drivers/devfreq/devfreq.c', 'update_devfreq')
for name in ('min_freq_store', 'max_freq_store'):
    code += f'\nstatic ssize_t {name}(struct device *dev, struct device_attribute *attr, const char *buf, size_t count)\n'
    code += function_body('drivers/devfreq/devfreq.c', name)
code += '\nstatic void devfreq_update_boosts(struct boost_dev *b)\n'
code += function_body('drivers/devfreq/devfreq_boost.c', 'devfreq_update_boosts')
code += r'''
int main(void) {
    unsigned long table[] = { 1144, 2086, 2929, 3879, 8137 };
    struct devfreq_dev_profile profile = { .freq_table = table, .target = set_target };
    struct devfreq_governor governor = { get_target };
    struct devfreq df = { .profile = &profile, .governor = &governor,
                         .min_freq = 1144, .max_freq = 8137, .is_boost_device = true };
    df.dev.df = &df;
    struct boost_dev b = { .df = &df, .boost_freq = 3879 };
    assert(min_freq_store(&df.dev, NULL, "2086", 4) == 4);
    assert(df.min_freq == 2086 && target == 2086);
    b.state = BIT(INPUT_BOOST);
    devfreq_update_boosts(&b);
    assert(df.min_freq == 2086 && target == 3879);
    assert(max_freq_store(&df.dev, NULL, "2929", 4) == 4);
    assert(target == 2929);
    b.state = 0;
    devfreq_update_boosts(&b);
    assert(df.min_freq == 2086 && target == 2086);
    b.state = BIT(MAX_BOOST);
    devfreq_update_boosts(&b);
    assert(target == 2929);
    b.state = BIT(SCREEN_OFF) | BIT(INPUT_BOOST) | BIT(MAX_BOOST);
    devfreq_update_boosts(&b);
    assert(!df.max_boost && df.boost_min_freq == 0 && target == 2086);
    assert(min_freq_store(&df.dev, NULL, "4000", 4) == -EINVAL);
    assert(max_freq_store(&df.dev, NULL, "1000", 4) == -EINVAL);
    assert(min_freq_store(&df.dev, NULL, "bad", 3) == -EINVAL);
    assert(df.min_freq == 2086 && df.max_freq == 2929);
    assert(max_freq_store(&df.dev, NULL, "0", 1) == 1);
    b.state = BIT(INPUT_BOOST);
    devfreq_update_boosts(&b);
    assert(target == 3879); /* Zero means no userspace maximum. */
    assert(min_freq_store(&df.dev, NULL, "0", 1) == 1);
    b.state = 0;
    devfreq_update_boosts(&b);
    assert(df.min_freq == 0 && target == demand);
    assert(!df.lock.held && !df.event_lock.held && !devfreq_boost_lock.held);
    puts("PASS: devfreq user limits, boost expiry, screen-off and maximum caps");
}
'''
run_c(code)
