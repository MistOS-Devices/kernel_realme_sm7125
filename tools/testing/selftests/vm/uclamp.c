// SPDX-License-Identifier: GPL-2.0
#define _GNU_SOURCE
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <unistd.h>

#define RESET_ON_FORK 0x01
#define KEEP_POLICY 0x08
#define KEEP_PARAMS 0x10
#define UTIL_MIN 0x20
#define UTIL_MAX 0x40
#define KEEP_ALL (KEEP_POLICY | KEEP_PARAMS)
struct attr {
	uint32_t size, policy;
	uint64_t flags;
	int32_t nice;
	uint32_t priority;
	uint64_t runtime, deadline, period;
	uint32_t min, max;
};

static void check(int ok, const char *what)
{
	if (!ok) {
		fprintf(stderr, "FAIL: %s (errno=%d)\n", what, errno);
		exit(1);
	}
}

static struct attr get(void)
{
	struct attr a = {0};
	check(syscall(__NR_sched_getattr, 0, &a, sizeof(a), 0) == 0, "sched_getattr");
	return a;
}

static long set(struct attr *a)
{
	return syscall(__NR_sched_setattr, 0, a, 0);
}

static void child_check(uint32_t min, uint32_t max)
{
	int status;
	pid_t pid = fork();
	check(pid >= 0, "fork");
	if (!pid) {
		struct attr a = get();
		_exit(a.min != min || a.max != max);
	}
	check(waitpid(pid, &status, 0) == pid && WIFEXITED(status) &&
	      WEXITSTATUS(status) == 0, "fork clamp inheritance/reset");
}

int main(void)
{
	struct attr original = get(), current;
	struct attr a = {.size = sizeof(a), .flags = KEEP_ALL | UTIL_MIN | UTIL_MAX,
			.nice = -20, .priority = 99, .min = 256, .max = 768};
	long ret;

	if (original.size < sizeof(a)) {
		puts("SKIP: running kernel has no uclamp ABI");
		return 4;
	}
	errno = 0;
	ret = set(&a);
	if (ret == -1 && errno == EOPNOTSUPP) {
		puts("SKIP: running kernel disabled uclamp");
		return 4;
	}
	check(ret == 0, "HAL KEEP_ALL flags with ignored priority/nice");
	current = get();
	check(current.policy == original.policy && current.nice == original.nice &&
	      current.priority == original.priority, "scheduling parameters preserved");
	check(current.min == 256 && current.max == 768, "clamps applied");
	a.min = 769;
	errno = 0;
	check(set(&a) == -1 && errno == EINVAL, "inverted clamps rejected");
	a.min = 0; a.max = 1025;
	errno = 0;
	check(set(&a) == -1 && errno == EINVAL, "out of range rejected");
	a.flags = KEEP_ALL | UTIL_MAX; a.max = 128;
	errno = 0;
	check(set(&a) == -1 && errno == EINVAL, "partial clamp validation");
	a.flags = KEEP_ALL | UTIL_MIN; a.min = 128;
	check(set(&a) == 0, "partial minimum update");
	current = get();
	check(current.min == 128 && current.max == 768, "maximum preserved");
	a.size = 48;
	errno = 0;
	check(set(&a) == -1 && errno == EINVAL, "short clamping attribute rejected");
	child_check(128, 768);
	a = current;
	a.size = sizeof(a);
	a.flags = RESET_ON_FORK | KEEP_PARAMS | UTIL_MIN | UTIL_MAX;
	check(set(&a) == 0, "enable reset-on-fork");
	child_check(0, 1024);
	puts("PASS: native/compat uclamp ABI, HAL flags, bounds, partial updates and fork/reset");
	return 0;
}
