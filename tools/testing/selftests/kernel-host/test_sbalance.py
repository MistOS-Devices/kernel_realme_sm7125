#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Exercise SBalance's production CPU-selection block."""
from test_helpers import function_body, run_c

body = function_body('kernel/irq/sbalance.c', 'balance_irqs')
selection = body[body.index('cpumask_andnot('):
                 body.index('if (unlikely(cpumask_weight')]
run_c(r'''
#include <assert.h>
#include <stdio.h>
typedef unsigned int cpumask_t;
static cpumask_t active, isolated, cpu_exclude_mask;
#define cpu_active_mask (&active)
#define cpu_isolated_mask (&isolated)
static void cpumask_andnot(cpumask_t *dst, const cpumask_t *a,
                          const cpumask_t *b) { *dst = *a & ~*b; }
static cpumask_t select_cpus(void) {
    cpumask_t cpus;
''' + selection + r'''
    return cpus;
}
int main(void) {
    active = 0xff; cpu_exclude_mask = (1U << 5) | (1U << 7);
    isolated = 1U << 4;
    assert(select_cpus() == 0x4f);
    isolated = 0;
    assert(select_cpus() == 0x5f);
    active &= ~(1U << 6);
    assert(select_cpus() == 0x1f);
    isolated = active;
    assert(select_cpus() == 0);
    isolated = active & ~1U;
    assert(select_cpus() == 1);
    puts("PASS: SBalance excludes isolated, offline and configured CPUs");
}
''')
# Selection must remain valid until the IRQ move, including early exits.
assert body.index('cpu_maps_update_begin();') < body.index('rcu_read_lock();')
assert body.index('cpu_maps_update_done();') > body.index('rcu_read_unlock();')
print('PASS: CPU-map lock covers SBalance selection and migration')
