From: Jason Gunthorpe <jgg@nvidia.com>
Date: Mon, 11 Apr 2022 16:13:59 +0200
Subject: vfio/mdev: Remove vfio_mdev.c
Git-commit: 6c7f98b334a32df5cac8abac8983ac4ce17cab57
Patch-mainline: v5.19-rc1
References: bsc#1205701

Now that all mdev drivers directly create their own mdev_device driver and
directly register with the vfio core's vfio_device_ops this is all dead
code.

Delete vfio_mdev.c and the mdev_parent_ops members that are connected to
it.

Signed-off-by: Jason Gunthorpe <jgg@nvidia.com>
Signed-off-by: Christoph Hellwig <hch@lst.de>
Signed-off-by: Zhi Wang <zhi.a.wang@intel.com>
Link: http://patchwork.freedesktop.org/patch/msgid/20220411141403.86980-31-hch@lst.de
Reviewed-by: Kirti Wankhede <kwankhede@nvidia.com>
Reviewed-by: Zhi Wang <zhi.a.wang@intel.com>
Acked-by: Joerg Roedel <jroedel@suse.de>
---
 Documentation/driver-api/vfio-mediated-device.rst |   3 -
 drivers/vfio/mdev/Makefile                        |   2 +-
 drivers/vfio/mdev/mdev_core.c                     |  40 +-----
 drivers/vfio/mdev/mdev_driver.c                   |  10 --
 drivers/vfio/mdev/mdev_private.h                  |   2 -
 drivers/vfio/mdev/vfio_mdev.c                     | 152 ----------------------
 include/linux/mdev.h                              |  48 +------
 7 files changed, 6 insertions(+), 251 deletions(-)

diff --git a/Documentation/driver-api/vfio-mediated-device.rst b/Documentation/driver-api/vfio-mediated-device.rst
index 9f26079cacae..5a6e18a651a1 100644
--- a/Documentation/driver-api/vfio-mediated-device.rst
+++ b/Documentation/driver-api/vfio-mediated-device.rst
@@ -138,9 +138,6 @@ The structures in the mdev_parent_ops structure are as follows:
 * supported_config: attributes to define supported configurations
 * device_driver: device driver to bind for mediated device instances
 
-The mdev_parent_ops also still has various functions pointers.  Theses exist
-for historical reasons only and shall not be used for new drivers.
-
 When a driver wants to add the GUID creation sysfs to an existing device it has
 probe'd to then it should call::
 
diff --git a/drivers/vfio/mdev/Makefile b/drivers/vfio/mdev/Makefile
index ff9ecd802125..7c236ba1b90e 100644
--- a/drivers/vfio/mdev/Makefile
+++ b/drivers/vfio/mdev/Makefile
@@ -1,5 +1,5 @@
 # SPDX-License-Identifier: GPL-2.0-only
 
-mdev-y := mdev_core.o mdev_sysfs.o mdev_driver.o vfio_mdev.o
+mdev-y := mdev_core.o mdev_sysfs.o mdev_driver.o
 
 obj-$(CONFIG_VFIO_MDEV) += mdev.o
diff --git a/drivers/vfio/mdev/mdev_core.c b/drivers/vfio/mdev/mdev_core.c
index b314101237fe..8b1e86b9e8bc 100644
--- a/drivers/vfio/mdev/mdev_core.c
+++ b/drivers/vfio/mdev/mdev_core.c
@@ -89,17 +89,10 @@ void mdev_release_parent(struct kref *kref)
 static void mdev_device_remove_common(struct mdev_device *mdev)
 {
 	struct mdev_parent *parent = mdev->type->parent;
-	int ret;
 
 	mdev_remove_sysfs_files(mdev);
 	device_del(&mdev->dev);
 	lockdep_assert_held(&parent->unreg_sem);
-	if (parent->ops->remove) {
-		ret = parent->ops->remove(mdev);
-		if (ret)
-			dev_err(&mdev->dev, "Remove failed: err=%d\n", ret);
-	}
-
 	/* Balances with device_initialize() */
 	put_device(&mdev->dev);
 }
@@ -131,7 +124,7 @@ int mdev_register_device(struct device *dev, const struct mdev_parent_ops *ops)
 	/* check for mandatory ops */
 	if (!ops || !ops->supported_type_groups)
 		return -EINVAL;
-	if (!ops->device_driver && (!ops->create || !ops->remove))
+	if (!ops->device_driver)
 		return -EINVAL;
 
 	dev = get_device(dev);
@@ -297,18 +290,10 @@ int mdev_device_create(struct mdev_type *type, const guid_t *uuid)
 		goto out_put_device;
 	}
 
-	if (parent->ops->create) {
-		ret = parent->ops->create(mdev);
-		if (ret)
-			goto out_unlock;
-	}
-
 	ret = device_add(&mdev->dev);
 	if (ret)
-		goto out_remove;
+		goto out_unlock;
 
-	if (!drv)
-		drv = &vfio_mdev_driver;
 	ret = device_driver_attach(&drv->driver, &mdev->dev);
 	if (ret)
 		goto out_del;
@@ -325,9 +310,6 @@ int mdev_device_create(struct mdev_type *type, const guid_t *uuid)
 
 out_del:
 	device_del(&mdev->dev);
-out_remove:
-	if (parent->ops->remove)
-		parent->ops->remove(mdev);
 out_unlock:
 	up_read(&parent->unreg_sem);
 out_put_device:
@@ -370,28 +352,14 @@ int mdev_device_remove(struct mdev_device *mdev)
 
 static int __init mdev_init(void)
 {
-	int rc;
-
-	rc = mdev_bus_register();
-	if (rc)
-		return rc;
-	rc = mdev_register_driver(&vfio_mdev_driver);
-	if (rc)
-		goto err_bus;
-	return 0;
-err_bus:
-	mdev_bus_unregister();
-	return rc;
+	return bus_register(&mdev_bus_type);
 }
 
 static void __exit mdev_exit(void)
 {
-	mdev_unregister_driver(&vfio_mdev_driver);
-
 	if (mdev_bus_compat_class)
 		class_compat_unregister(mdev_bus_compat_class);
-
-	mdev_bus_unregister();
+	bus_unregister(&mdev_bus_type);
 }
 
 subsys_initcall(mdev_init)
diff --git a/drivers/vfio/mdev/mdev_driver.c b/drivers/vfio/mdev/mdev_driver.c
index 7927ed4f1711..9c2af59809e2 100644
--- a/drivers/vfio/mdev/mdev_driver.c
+++ b/drivers/vfio/mdev/mdev_driver.c
@@ -74,13 +74,3 @@ void mdev_unregister_driver(struct mdev_driver *drv)
 	driver_unregister(&drv->driver);
 }
 EXPORT_SYMBOL(mdev_unregister_driver);
-
-int mdev_bus_register(void)
-{
-	return bus_register(&mdev_bus_type);
-}
-
-void mdev_bus_unregister(void)
-{
-	bus_unregister(&mdev_bus_type);
-}
diff --git a/drivers/vfio/mdev/mdev_private.h b/drivers/vfio/mdev/mdev_private.h
index afbad7b0a14a..6999c89db7b1 100644
--- a/drivers/vfio/mdev/mdev_private.h
+++ b/drivers/vfio/mdev/mdev_private.h
@@ -37,8 +37,6 @@ struct mdev_type {
 #define to_mdev_type(_kobj)		\
 	container_of(_kobj, struct mdev_type, kobj)
 
-extern struct mdev_driver vfio_mdev_driver;
-
 int  parent_create_sysfs_files(struct mdev_parent *parent);
 void parent_remove_sysfs_files(struct mdev_parent *parent);
 
diff --git a/drivers/vfio/mdev/vfio_mdev.c b/drivers/vfio/mdev/vfio_mdev.c
deleted file mode 100644
index a90e24b0c851..000000000000
--- a/drivers/vfio/mdev/vfio_mdev.c
+++ /dev/null
@@ -1,152 +0,0 @@
-// SPDX-License-Identifier: GPL-2.0-only
-/*
- * VFIO based driver for Mediated device
- *
- * Copyright (c) 2016, NVIDIA CORPORATION. All rights reserved.
- *     Author: Neo Jia <cjia@nvidia.com>
- *             Kirti Wankhede <kwankhede@nvidia.com>
- */
-
-#include <linux/init.h>
-#include <linux/module.h>
-#include <linux/device.h>
-#include <linux/kernel.h>
-#include <linux/slab.h>
-#include <linux/vfio.h>
-#include <linux/mdev.h>
-
-#include "mdev_private.h"
-
-static int vfio_mdev_open_device(struct vfio_device *core_vdev)
-{
-	struct mdev_device *mdev = to_mdev_device(core_vdev->dev);
-	struct mdev_parent *parent = mdev->type->parent;
-
-	if (unlikely(!parent->ops->open_device))
-		return 0;
-
-	return parent->ops->open_device(mdev);
-}
-
-static void vfio_mdev_close_device(struct vfio_device *core_vdev)
-{
-	struct mdev_device *mdev = to_mdev_device(core_vdev->dev);
-	struct mdev_parent *parent = mdev->type->parent;
-
-	if (likely(parent->ops->close_device))
-		parent->ops->close_device(mdev);
-}
-
-static long vfio_mdev_unlocked_ioctl(struct vfio_device *core_vdev,
-				     unsigned int cmd, unsigned long arg)
-{
-	struct mdev_device *mdev = to_mdev_device(core_vdev->dev);
-	struct mdev_parent *parent = mdev->type->parent;
-
-	if (unlikely(!parent->ops->ioctl))
-		return 0;
-
-	return parent->ops->ioctl(mdev, cmd, arg);
-}
-
-static ssize_t vfio_mdev_read(struct vfio_device *core_vdev, char __user *buf,
-			      size_t count, loff_t *ppos)
-{
-	struct mdev_device *mdev = to_mdev_device(core_vdev->dev);
-	struct mdev_parent *parent = mdev->type->parent;
-
-	if (unlikely(!parent->ops->read))
-		return -EINVAL;
-
-	return parent->ops->read(mdev, buf, count, ppos);
-}
-
-static ssize_t vfio_mdev_write(struct vfio_device *core_vdev,
-			       const char __user *buf, size_t count,
-			       loff_t *ppos)
-{
-	struct mdev_device *mdev = to_mdev_device(core_vdev->dev);
-	struct mdev_parent *parent = mdev->type->parent;
-
-	if (unlikely(!parent->ops->write))
-		return -EINVAL;
-
-	return parent->ops->write(mdev, buf, count, ppos);
-}
-
-static int vfio_mdev_mmap(struct vfio_device *core_vdev,
-			  struct vm_area_struct *vma)
-{
-	struct mdev_device *mdev = to_mdev_device(core_vdev->dev);
-	struct mdev_parent *parent = mdev->type->parent;
-
-	if (unlikely(!parent->ops->mmap))
-		return -EINVAL;
-
-	return parent->ops->mmap(mdev, vma);
-}
-
-static void vfio_mdev_request(struct vfio_device *core_vdev, unsigned int count)
-{
-	struct mdev_device *mdev = to_mdev_device(core_vdev->dev);
-	struct mdev_parent *parent = mdev->type->parent;
-
-	if (parent->ops->request)
-		parent->ops->request(mdev, count);
-	else if (count == 0)
-		dev_notice(mdev_dev(mdev),
-			   "No mdev vendor driver request callback support, blocked until released by user\n");
-}
-
-static const struct vfio_device_ops vfio_mdev_dev_ops = {
-	.name		= "vfio-mdev",
-	.open_device	= vfio_mdev_open_device,
-	.close_device	= vfio_mdev_close_device,
-	.ioctl		= vfio_mdev_unlocked_ioctl,
-	.read		= vfio_mdev_read,
-	.write		= vfio_mdev_write,
-	.mmap		= vfio_mdev_mmap,
-	.request	= vfio_mdev_request,
-};
-
-static int vfio_mdev_probe(struct mdev_device *mdev)
-{
-	struct vfio_device *vdev;
-	int ret;
-
-	vdev = kzalloc(sizeof(*vdev), GFP_KERNEL);
-	if (!vdev)
-		return -ENOMEM;
-
-	vfio_init_group_dev(vdev, &mdev->dev, &vfio_mdev_dev_ops);
-	ret = vfio_register_emulated_iommu_dev(vdev);
-	if (ret)
-		goto out_uninit;
-
-	dev_set_drvdata(&mdev->dev, vdev);
-	return 0;
-
-out_uninit:
-	vfio_uninit_group_dev(vdev);
-	kfree(vdev);
-	return ret;
-}
-
-static void vfio_mdev_remove(struct mdev_device *mdev)
-{
-	struct vfio_device *vdev = dev_get_drvdata(&mdev->dev);
-
-	vfio_unregister_group_dev(vdev);
-	vfio_uninit_group_dev(vdev);
-	kfree(vdev);
-}
-
-struct mdev_driver vfio_mdev_driver = {
-	.driver = {
-		.name = "vfio_mdev",
-		.owner = THIS_MODULE,
-		.mod_name = KBUILD_MODNAME,
-	},
-	.probe	= vfio_mdev_probe,
-	.remove	= vfio_mdev_remove,
-};
diff --git a/include/linux/mdev.h b/include/linux/mdev.h
index 15d03f6532d0..192aed656116 100644
--- a/include/linux/mdev.h
+++ b/include/linux/mdev.h
@@ -40,40 +40,7 @@ struct device *mtype_get_parent_dev(struct mdev_type *mtype);
  * @mdev_attr_groups:	Attributes of the mediated device.
  * @supported_type_groups: Attributes to define supported types. It is mandatory
  *			to provide supported types.
- * @create:		Called to allocate basic resources in parent device's
- *			driver for a particular mediated device. It is
- *			mandatory to provide create ops.
- *			@mdev: mdev_device structure on of mediated device
- *			      that is being created
- *			Returns integer: success (0) or error (< 0)
- * @remove:		Called to free resources in parent device's driver for
- *			a mediated device. It is mandatory to provide 'remove'
- *			ops.
- *			@mdev: mdev_device device structure which is being
- *			       destroyed
- *			Returns integer: success (0) or error (< 0)
- * @read:		Read emulation callback
- *			@mdev: mediated device structure
- *			@buf: read buffer
- *			@count: number of bytes to read
- *			@ppos: address.
- *			Retuns number on bytes read on success or error.
- * @write:		Write emulation callback
- *			@mdev: mediated device structure
- *			@buf: write buffer
- *			@count: number of bytes to be written
- *			@ppos: address.
- *			Retuns number on bytes written on success or error.
- * @ioctl:		IOCTL callback
- *			@mdev: mediated device structure
- *			@cmd: ioctl command
- *			@arg: arguments to ioctl
- * @mmap:		mmap callback
- *			@mdev: mediated device structure
- *			@vma: vma structure
- * @request:		request callback to release device
- *			@mdev: mediated device structure
- *			@count: request sequence number
+ *
  * Parent device that support mediated device should be registered with mdev
  * module with mdev_parent_ops structure.
  **/
@@ -83,19 +50,6 @@ struct mdev_parent_ops {
 	const struct attribute_group **dev_attr_groups;
 	const struct attribute_group **mdev_attr_groups;
 	struct attribute_group **supported_type_groups;
-
-	int     (*create)(struct mdev_device *mdev);
-	int     (*remove)(struct mdev_device *mdev);
-	int     (*open_device)(struct mdev_device *mdev);
-	void    (*close_device)(struct mdev_device *mdev);
-	ssize_t (*read)(struct mdev_device *mdev, char __user *buf,
-			size_t count, loff_t *ppos);
-	ssize_t (*write)(struct mdev_device *mdev, const char __user *buf,
-			 size_t count, loff_t *ppos);
-	long	(*ioctl)(struct mdev_device *mdev, unsigned int cmd,
-			 unsigned long arg);
-	int	(*mmap)(struct mdev_device *mdev, struct vm_area_struct *vma);
-	void	(*request)(struct mdev_device *mdev, unsigned int count);
 };
 
 /* interface for exporting mdev supported type attributes */

