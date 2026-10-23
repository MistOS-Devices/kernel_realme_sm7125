Multi-Gen LRU on ShadowBladeX
============================

This kernel adapts Yu Zhao's page-based MGLRU v9 series through the
Stratosphere Android 4.14 backport. It replaces active/inactive reclaim
with generations while retaining classic reclaim as a runtime fallback.
The atoll configuration enables MGLRU by default, disables extended
historical statistics, and leaves min_ttl_ms at zero. No device frequency,
thermal, ZRAM, or LMK-TNG thresholds are changed by this integration.

Runtime verification
--------------------

After booting the rebuilt kernel, run these checks from a root shell::

    cat /sys/kernel/mm/lru_gen/enabled
    cat /sys/kernel/mm/lru_gen/min_ttl_ms
    cat /proc/pressure/memory

The enabled bitmask must have bit 0 set; min_ttl_ms should initially be 0.
Other bits control page-table walking optimizations and depend on hardware
support. See the original series for their definitions:
https://lore.kernel.org/r/20220309021230.721028-1-yuzhao@google.com/

Compare the same app-switching workload with classic reclaim and MGLRU::

    echo 0 > /sys/kernel/mm/lru_gen/enabled
    # Run the fixed workload and collect measurements.
    echo y > /sys/kernel/mm/lru_gen/enabled
    # Repeat the workload under the same conditions.

Record app reloads, frame-time distribution, memory PSI, reclaim/refault
counters in /proc/vmstat, LMK kills, temperature and power. List conversion
preserves pages but does not reset caches, so repeat with alternating order
and comparable initial state. Restore the desired enabled mask afterwards.
Do not infer battery improvement from a successful build or sysfs read.

Run the process_madvise, process_mrelease and uclamp tests under
tools/testing/selftests/vm on the device. Also stress fork/exec/exit and
cgroup movement while switching between the two reclaim implementations;
watch kernel logs for bad-page reports, list corruption and hung tasks.
The kernel-host suite covers selected production generation helpers and
compatibility paths, not concurrent execution of the complete MM subsystem.

Limits
------

This is a historical page-based backport, not current mainline MGLRU.
Secondary-MMU aging improvements from later upstream kernels are not
included. The atoll configuration does not enable KVM; enabling it or
adding secondary-MMU users needs a separate notifier/aging review.
LMK-TNG remains enabled and can kill applications independently of MGLRU.
Device boot, sustained memory-pressure testing, and battery/frame-time
measurements are required before treating this as a measured improvement.
