# SPDX-License-Identifier: GPL-2.0
# These tests compile extracted kernel functions with a native host compiler.
HOSTCC ?= cc
PYTHON ?= python3
TESTS := test_ext4_flush.py test_bore.py test_sbalance.py \
	test_devfreq_lifetime.py test_devfreq_limits.py test_adrenoboost.py \
	../cpufreq/test_cpu_boost.py

.PHONY: all run_tests
all: run_tests

run_tests:
	@set -e; for test in $(TESTS); do \
		PYTHONDONTWRITEBYTECODE=1 HOSTCC="$(HOSTCC)" $(PYTHON) $$test; \
	done
