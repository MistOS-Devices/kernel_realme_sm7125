// SPDX-License-Identifier: GPL-2.0
/*
 * Copyright (C) 2021-2025 Dakkshesh <dakkshesh5@gmail.com>
 * Manual-only adaptation of beakthoven/Kprofiles commit
 * 82441dbf8131527c90048f46be58ae9cdb463df3 for ShadowBladeX.
 * Automatic, override and notifier APIs are intentionally not provided.
 */
#include <linux/kernel.h>
#include <linux/kobject.h>
#include <linux/kprofiles.h>
#include <linux/module.h>
#include <linux/sysfs.h>

static unsigned int kp_mode = CONFIG_KP_DEFAULT_MODE;
static struct kobject *kp_kobj;

int kp_active_mode(void)
{
	return READ_ONCE(kp_mode);
}
EXPORT_SYMBOL_GPL(kp_active_mode);

int kp_set_mode(unsigned int level)
{
	if (level > 3)
		return -EINVAL;
	WRITE_ONCE(kp_mode, level);
	return 0;
}
EXPORT_SYMBOL_GPL(kp_set_mode);

static ssize_t kp_mode_show(struct kobject *kobj,
			    struct kobj_attribute *attr, char *buf)
{
	return scnprintf(buf, PAGE_SIZE, "%u\n", kp_active_mode());
}

static ssize_t kp_mode_store(struct kobject *kobj,
			     struct kobj_attribute *attr,
			     const char *buf, size_t count)
{
	unsigned int new_mode;
	int ret;

	ret = kstrtouint(buf, 10, &new_mode);
	if (ret)
		return ret;
	ret = kp_set_mode(new_mode);
	if (ret)
		return ret;
	return count;
}

static struct kobj_attribute kp_mode_attribute =
	__ATTR(kp_mode, 0660, kp_mode_show, kp_mode_store);

static struct attribute *kp_attrs[] = {
	&kp_mode_attribute.attr,
	NULL,
};
static const struct attribute_group kp_attr_group = {
	.attrs = kp_attrs,
};

static int __init kp_init(void)
{
	int ret;

	kp_kobj = kobject_create_and_add("kprofiles", kernel_kobj);
	if (!kp_kobj)
		return -ENOMEM;
	ret = sysfs_create_group(kp_kobj, &kp_attr_group);
	if (ret)
		kobject_put(kp_kobj);
	return ret;
}
module_init(kp_init);

static void __exit kp_exit(void)
{
	sysfs_remove_group(kp_kobj, &kp_attr_group);
	kobject_put(kp_kobj);
}
module_exit(kp_exit);
MODULE_LICENSE("GPL v2");
MODULE_DESCRIPTION("Manual KernelSpace Profiles");
MODULE_AUTHOR("Dakkshesh <dakkshesh5@gmail.com>");
