#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Check that invalid GPU boost writes leave the previous setting intact."""
from test_helpers import function_body, run_c

run_c(r'''
#include <assert.h>
#include <errno.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>
struct device { int unused; };
struct device_attribute { int unused; };
static unsigned int adrenoboost = 1;
/* Host fixture for the existing kernel parser; exercise its return handling. */
static int kstrtouint(const char *buf, unsigned int base, unsigned int *value) {
    char *end;
    errno = 0;
    unsigned long parsed = strtoul(buf, &end, base);
    if (end == buf || (*end && strcmp(end, "\n")) || buf[0] == '-')
        return -EINVAL;
    if (errno == ERANGE || parsed > UINT_MAX)
        return -ERANGE;
    *value = parsed;
    return 0;
}
static ssize_t adrenoboost_save(struct device *dev, struct device_attribute *attr,
                              const char *buf, size_t count)
''' + function_body('drivers/devfreq/governor_msm_adreno_tz.c', 'adrenoboost_save') + r'''
int main(void) {
    const char *valid[] = { "0", "1\n", "2", "3" };
    for (unsigned int i = 0; i < 4; i++) {
        assert(adrenoboost_save(NULL, NULL, valid[i], strlen(valid[i])) ==
               (ssize_t)strlen(valid[i]));
        assert(adrenoboost == i);
    }
    const char *invalid[] = { "4", "-1", "", "oops", "2oops",
                              "4294967296", "999999999999999999999999" };
    for (unsigned int i = 0; i < sizeof(invalid) / sizeof(invalid[0]); i++) {
        adrenoboost = 2;
        assert(adrenoboost_save(NULL, NULL, invalid[i], strlen(invalid[i])) < 0);
        assert(adrenoboost == 2);
    }
    puts("PASS: GPU boost range, malformed input and overflow preserve state");
}
''')
