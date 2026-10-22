// SPDX-License-Identifier: GPL-2.0
/* Run after booting the backport; no other process's memory is modified. */
#define _GNU_SOURCE
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/syscall.h>
#include <sys/uio.h>
#include <sys/wait.h>
#include <unistd.h>

#ifndef MADV_COLD
#define MADV_COLD 20
#define MADV_PAGEOUT 21
#endif
#if defined(__aarch64__) || defined(__arm__)
#ifndef __NR_pidfd_open
#define __NR_pidfd_open 434
#endif
#ifndef __NR_process_madvise
#define __NR_process_madvise 440
#endif
#endif

static void check(int ok, const char *what)
{
	if (!ok) {
		fprintf(stderr, "FAIL: %s (errno=%d)\n", what, errno);
		exit(1);
	}
}

int main(void)
{
#if defined(__NR_pidfd_open) && defined(__NR_process_madvise)
	size_t page = sysconf(_SC_PAGESIZE), len = 64 * page;
	unsigned char *memory;
	struct iovec vec[3];
	long ret;
	int fd, ready[2], done[2], status;
	pid_t child;
	char token;

	memory = mmap(NULL, len, PROT_READ | PROT_WRITE,
		      MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
	check(memory != MAP_FAILED, "mmap");
	memset(memory, 0x5a, len);
	errno = 0;
	ret = madvise(memory, len, MADV_COLD);
	if (ret && errno == EINVAL) {
		puts("SKIP: MADV_COLD is not supported by the running kernel");
		munmap(memory, len);
		return 4;
	}
	check(ret == 0, "MADV_COLD");
	check(madvise(memory, len, MADV_PAGEOUT) == 0, "MADV_PAGEOUT");
	for (size_t i = 0; i < len; i++)
		check(memory[i] == 0x5a, "data survives pageout");
	if (mlock(memory, page) == 0) {
		errno = 0;
		check(madvise(memory, page, MADV_COLD) == -1 && errno == EINVAL,
		      "locked VMA rejects reclaim advice");
		check(munlock(memory, page) == 0, "munlock");
	}

	fd = syscall(__NR_pidfd_open, getpid(), 0);
	check(fd >= 0, "pidfd_open");
	vec[0] = (struct iovec){memory, page};
	vec[1] = (struct iovec){NULL, 0};
	vec[2] = (struct iovec){memory + page, len - page};
	errno = 0;
	check(syscall(__NR_process_madvise, -1, vec, 3, MADV_COLD, 0) == -1 &&
	      errno == EBADF, "invalid pidfd rejected");
	errno = 0;
	ret = syscall(__NR_process_madvise, fd, vec, 3, MADV_COLD, 1);
	check(ret == -1 && errno == EINVAL, "nonzero flags rejected");
	errno = 0;
	ret = syscall(__NR_process_madvise, fd, vec, 3, MADV_COLD, 0);
	if (ret == -1 && errno == EPERM) {
		puts("SKIP: process_madvise requires CAP_SYS_NICE; local advice passed");
		close(fd);
		munmap(memory, len);
		return 4;
	}
	check(ret == (long)len, "vector advice including empty vector");
	check(syscall(__NR_process_madvise, fd, vec, 3, MADV_PAGEOUT, 0) == (long)len,
	      "vector pageout");
	for (size_t i = 0; i < len; i++)
		check(memory[i] == 0x5a, "data survives vector pageout");
	vec[1] = (struct iovec){memory + 1, page};
	check(syscall(__NR_process_madvise, fd, vec, 2, MADV_COLD, 0) == (long)page,
	      "return completed bytes before invalid vector");
	errno = 0;
	check(syscall(__NR_process_madvise, fd, vec, 1, MADV_DONTNEED, 0) == -1 &&
	      errno == EINVAL, "destructive remote advice rejected");
	close(fd);
	check(pipe(ready) == 0 && pipe(done) == 0, "pipe");
	child = fork();
	check(child >= 0, "fork");
	if (!child) {
		close(ready[1]);
		close(done[0]);
		if (read(ready[0], &token, 1) != 1)
			_exit(1);
		for (size_t i = 0; i < len; i++)
			if (memory[i] != 0x5a)
				_exit(1);
		if (write(done[1], "x", 1) != 1)
			_exit(1);
		_exit(0);
	}
	close(ready[0]);
	close(done[1]);
	/* This range now exists only in the child, catching current->mm bugs. */
	check(munmap(memory, len) == 0, "unmap parent range");
	fd = syscall(__NR_pidfd_open, child, 0);
	check(fd >= 0, "child pidfd_open");
	vec[0] = (struct iovec){memory, len};
	check(syscall(__NR_process_madvise, fd, vec, 1, MADV_PAGEOUT, 0) == (long)len,
	      "advise child address space");
	check(write(ready[1], "x", 1) == 1, "wake child");
	check(read(done[0], &token, 1) == 1, "child data survived");
	check(waitpid(child, &status, 0) == child && WIFEXITED(status) &&
	      WEXITSTATUS(status) == 0, "child exited successfully");
	close(fd);
	close(ready[1]);
	close(done[0]);
	puts("PASS: local and vector reclaim advice preserve data");
	return 0;
#else
	puts("SKIP: syscall numbers unavailable for this architecture");
	return 4;
#endif
}
