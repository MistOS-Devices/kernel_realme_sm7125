#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Exercise boost updates before probe and after devfreq removal."""
from test_helpers import ROOT, function_body, run_c

path = 'drivers/devfreq/devfreq_boost.c'
body = function_body(path, 'devfreq_update_boosts')
# Accommodate the old state argument while testing the same production body.
old_signature = 'unsigned long state)' in (ROOT / path).read_text().split(
    'static void devfreq_update_boosts', 1)[1].split('{', 1)[0]
code = r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#define BIT(n) (1UL << (n))
#define READ_ONCE(x) (x)
#define WRITE_ONCE(x, value) ((x) = (value))
#define min(a, b) ((a) < (b) ? (a) : (b))
enum { SCREEN_OFF, INPUT_BOOST, MAX_BOOST };
enum df_device { DEVFREQ_CPU_LLCC_DDR_BW, DEVFREQ_MAX };
struct mutex { bool held; };
static void mutex_lock(struct mutex *m) { assert(!m->held); m->held = true; }
static void mutex_unlock(struct mutex *m) { assert(m->held); m->held = false; }
static struct mutex devfreq_boost_lock;
struct devfreq_dev_profile { unsigned long *freq_table; };
struct devfreq {
    struct mutex lock;
    struct devfreq_dev_profile *profile;
    unsigned long min_freq, max_freq, boost_min_freq;
    bool max_boost, is_boost_device;
};
struct boost_dev { struct devfreq *df; unsigned long state, boost_freq; };
struct df_boost_drv { struct boost_dev devices[DEVFREQ_MAX]; };
static struct df_boost_drv df_boost_drv_g;
static int updates;
static void update_devfreq(struct devfreq *df) {
    assert(df->lock.held && devfreq_boost_lock.held);
    updates++;
}
'''
args = ', unsigned long state' if old_signature else ''
code += 'static void devfreq_update_boosts(struct boost_dev *b' + args + ')\n'
code += body
if not old_signature:
    code += '\nvoid devfreq_register_boost_device(enum df_device device, struct devfreq *df)\n'
    code += function_body(path, 'devfreq_register_boost_device')
    code += '\nvoid devfreq_unregister_boost_device(struct devfreq *df)\n'
    code += function_body(path, 'devfreq_unregister_boost_device')
call = 'devfreq_update_boosts(b, b->state)' if old_signature else 'devfreq_update_boosts(b)'
code += r'''
int main(void) {
    struct boost_dev *b = &df_boost_drv_g.devices[0];
    b->state = BIT(SCREEN_OFF);
''' + call + r''';
    assert(updates == 0);
'''
if not old_signature:
    code += r'''
    unsigned long table[] = { 1144, 3879, 8137 };
    struct devfreq_dev_profile profile = { table };
    struct devfreq df = { .profile = &profile, .max_freq = 8137 };
    b->boost_freq = 3879;
    devfreq_register_boost_device(DEVFREQ_CPU_LLCC_DDR_BW, &df);
    assert(b->df == &df && updates == 1 && !df.max_boost);
    b->state = BIT(INPUT_BOOST) | BIT(MAX_BOOST);
    devfreq_update_boosts(b);
    assert(updates == 2 && df.max_boost);
    struct devfreq other = { 0 };
    devfreq_unregister_boost_device(&other);
    assert(b->df == &df);
    devfreq_unregister_boost_device(&df);
    assert(!b->df);
    b->state = BIT(SCREEN_OFF);
    devfreq_update_boosts(b);
    assert(updates == 2);
    devfreq_register_boost_device(DEVFREQ_CPU_LLCC_DDR_BW, &df);
    assert(updates == 3 && !df.max_boost);
    assert(!devfreq_boost_lock.held && !df.lock.held);
'''
code += 'puts("PASS: boost probe, absent device, unregister and reprobe");\n}\n'
run_c(code)
remove = function_body('drivers/devfreq/devfreq_devbw.c', 'devfreq_remove_devbw')
assert remove.index('devfreq_unregister_boost_device') < remove.index('msm_bus_scale_unregister_client')
assert remove.index('devfreq_unregister_boost_device') < remove.index('devfreq_remove_device')
