From: Max Gurtovoy <mgurtovoy@nvidia.com>
Date: Thu, 26 Aug 2021 13:39:05 +0300
Subject: vfio/pci: Split the pci_driver code out of vfio_pci_core.c
Git-commit: ff53edf6d6ab0970f86595b3f5d179df51848723
Patch-mainline: v5.15-rc1
References: bsc#1205701

Split the vfio_pci driver into two logical parts, the 'struct
pci_driver' (vfio_pci.c) which implements "Generic VFIO support for any
PCI device" and a library of code (vfio_pci_core.c) that helps
implementing a struct vfio_device on top of a PCI device.

vfio_pci.ko continues to present the same interface under sysfs and this
change should have no functional impact.

Following patches will turn vfio_pci and vfio_pci_core into a separate
module.

This is a preparation for allowing another module to provide the
pci_driver and allow that module to customize how VFIO is setup, inject
its own operations, and easily extend vendor specific functionality.

At this point the vfio_pci_core still contains a lot of vfio_pci
functionality mixed into it. Following patches will move more of the
large scale items out, but another cleanup series will be needed to get
everything.

Signed-off-by: Max Gurtovoy <mgurtovoy@nvidia.com>
Signed-off-by: Jason Gunthorpe <jgg@nvidia.com>
Reviewed-by: Christoph Hellwig <hch@lst.de>
Signed-off-by: Yishai Hadas <yishaih@nvidia.com>
Link: https://lore.kernel.org/r/20210826103912.128972-7-yishaih@nvidia.com
Signed-off-by: Alex Williamson <alex.williamson@redhat.com>
Acked-by: Joerg Roedel <jroedel@suse.de>
---
 drivers/vfio/pci/Makefile        |   2 +-
 drivers/vfio/pci/vfio_pci.c      | 223 ++++++++++++++++++++++++++++++++
 drivers/vfio/pci/vfio_pci_core.c | 271 ++++++++-------------------------------
 drivers/vfio/pci/vfio_pci_core.h |  23 ++++
 4 files changed, 304 insertions(+), 215 deletions(-)

diff --git a/drivers/vfio/pci/Makefile b/drivers/vfio/pci/Makefile
index 66a40488e967..8aa517b4b671 100644
--- a/drivers/vfio/pci/Makefile
+++ b/drivers/vfio/pci/Makefile
@@ -1,6 +1,6 @@
 # SPDX-License-Identifier: GPL-2.0-only
 
-vfio-pci-y := vfio_pci_core.o vfio_pci_intrs.o vfio_pci_rdwr.o vfio_pci_config.o
+vfio-pci-y := vfio_pci.o vfio_pci_core.o vfio_pci_intrs.o vfio_pci_rdwr.o vfio_pci_config.o
 vfio-pci-$(CONFIG_VFIO_PCI_IGD) += vfio_pci_igd.o
 vfio-pci-$(CONFIG_S390) += vfio_pci_zdev.o
 
diff --git a/drivers/vfio/pci/vfio_pci.c b/drivers/vfio/pci/vfio_pci.c
new file mode 100644
index 000000000000..4e31bd3001ad
--- /dev/null
+++ b/drivers/vfio/pci/vfio_pci.c
@@ -0,0 +1,223 @@
+// SPDX-License-Identifier: GPL-2.0-only
+/*
+ * Copyright (c) 2021, NVIDIA CORPORATION & AFFILIATES. All rights reserved
+ *
+ * Copyright (C) 2012 Red Hat, Inc.  All rights reserved.
+ *     Author: Alex Williamson <alex.williamson@redhat.com>
+ *
+ * Derived from original vfio:
+ * Copyright 2010 Cisco Systems, Inc.  All rights reserved.
+ * Author: Tom Lyon, pugs@cisco.com
+ */
+
+#define pr_fmt(fmt) KBUILD_MODNAME ": " fmt
+
+#include <linux/device.h>
+#include <linux/eventfd.h>
+#include <linux/file.h>
+#include <linux/interrupt.h>
+#include <linux/iommu.h>
+#include <linux/module.h>
+#include <linux/mutex.h>
+#include <linux/notifier.h>
+#include <linux/pm_runtime.h>
+#include <linux/slab.h>
+#include <linux/types.h>
+#include <linux/uaccess.h>
+
+#include "vfio_pci_core.h"
+
+#define DRIVER_AUTHOR   "Alex Williamson <alex.williamson@redhat.com>"
+#define DRIVER_DESC     "VFIO PCI - User Level meta-driver"
+
+static char ids[1024] __initdata;
+module_param_string(ids, ids, sizeof(ids), 0);
+MODULE_PARM_DESC(ids, "Initial PCI IDs to add to the vfio driver, format is \"vendor:device[:subvendor[:subdevice[:class[:class_mask]]]]\" and multiple comma separated entries can be specified");
+
+static bool enable_sriov;
+#ifdef CONFIG_PCI_IOV
+module_param(enable_sriov, bool, 0644);
+MODULE_PARM_DESC(enable_sriov, "Enable support for SR-IOV configuration.  Enabling SR-IOV on a PF typically requires support of the userspace PF driver, enabling VFs without such support may result in non-functional VFs or PF.");
+#endif
+
+static bool disable_denylist;
+module_param(disable_denylist, bool, 0444);
+MODULE_PARM_DESC(disable_denylist, "Disable use of device denylist. Disabling the denylist allows binding to devices with known errata that may lead to exploitable stability or security issues when accessed by untrusted users.");
+
+static bool vfio_pci_dev_in_denylist(struct pci_dev *pdev)
+{
+	switch (pdev->vendor) {
+	case PCI_VENDOR_ID_INTEL:
+		switch (pdev->device) {
+		case PCI_DEVICE_ID_INTEL_QAT_C3XXX:
+		case PCI_DEVICE_ID_INTEL_QAT_C3XXX_VF:
+		case PCI_DEVICE_ID_INTEL_QAT_C62X:
+		case PCI_DEVICE_ID_INTEL_QAT_C62X_VF:
+		case PCI_DEVICE_ID_INTEL_QAT_DH895XCC:
+		case PCI_DEVICE_ID_INTEL_QAT_DH895XCC_VF:
+			return true;
+		default:
+			return false;
+		}
+	}
+
+	return false;
+}
+
+static bool vfio_pci_is_denylisted(struct pci_dev *pdev)
+{
+	if (!vfio_pci_dev_in_denylist(pdev))
+		return false;
+
+	if (disable_denylist) {
+		pci_warn(pdev,
+			 "device denylist disabled - allowing device %04x:%04x.\n",
+			 pdev->vendor, pdev->device);
+		return false;
+	}
+
+	pci_warn(pdev, "%04x:%04x exists in vfio-pci device denylist, driver probing disallowed.\n",
+		 pdev->vendor, pdev->device);
+
+	return true;
+}
+
+static const struct vfio_device_ops vfio_pci_ops = {
+	.name		= "vfio-pci",
+	.open_device	= vfio_pci_core_open_device,
+	.close_device	= vfio_pci_core_close_device,
+	.ioctl		= vfio_pci_core_ioctl,
+	.read		= vfio_pci_core_read,
+	.write		= vfio_pci_core_write,
+	.mmap		= vfio_pci_core_mmap,
+	.request	= vfio_pci_core_request,
+	.match		= vfio_pci_core_match,
+};
+
+static int vfio_pci_probe(struct pci_dev *pdev, const struct pci_device_id *id)
+{
+	struct vfio_pci_core_device *vdev;
+	int ret;
+
+	if (vfio_pci_is_denylisted(pdev))
+		return -EINVAL;
+
+	vdev = kzalloc(sizeof(*vdev), GFP_KERNEL);
+	if (!vdev)
+		return -ENOMEM;
+	vfio_pci_core_init_device(vdev, pdev, &vfio_pci_ops);
+
+	ret = vfio_pci_core_register_device(vdev);
+	if (ret)
+		goto out_free;
+	return 0;
+
+out_free:
+	vfio_pci_core_uninit_device(vdev);
+	kfree(vdev);
+	return ret;
+}
+
+static void vfio_pci_remove(struct pci_dev *pdev)
+{
+	struct vfio_pci_core_device *vdev = dev_get_drvdata(&pdev->dev);
+
+	vfio_pci_core_unregister_device(vdev);
+	vfio_pci_core_uninit_device(vdev);
+	kfree(vdev);
+}
+
+static int vfio_pci_sriov_configure(struct pci_dev *pdev, int nr_virtfn)
+{
+	if (!enable_sriov)
+		return -ENOENT;
+
+	return vfio_pci_core_sriov_configure(pdev, nr_virtfn);
+}
+
+static struct pci_driver vfio_pci_driver = {
+	.name			= "vfio-pci",
+	.id_table		= NULL, /* only dynamic ids */
+	.probe			= vfio_pci_probe,
+	.remove			= vfio_pci_remove,
+	.sriov_configure	= vfio_pci_sriov_configure,
+	.err_handler		= &vfio_pci_core_err_handlers,
+};
+
+static void __init vfio_pci_fill_ids(void)
+{
+	char *p, *id;
+	int rc;
+
+	/* no ids passed actually */
+	if (ids[0] == '\0')
+		return;
+
+	/* add ids specified in the module parameter */
+	p = ids;
+	while ((id = strsep(&p, ","))) {
+		unsigned int vendor, device, subvendor = PCI_ANY_ID,
+			subdevice = PCI_ANY_ID, class = 0, class_mask = 0;
+		int fields;
+
+		if (!strlen(id))
+			continue;
+
+		fields = sscanf(id, "%x:%x:%x:%x:%x:%x",
+				&vendor, &device, &subvendor, &subdevice,
+				&class, &class_mask);
+
+		if (fields < 2) {
+			pr_warn("invalid id string \"%s\"\n", id);
+			continue;
+		}
+
+		rc = pci_add_dynid(&vfio_pci_driver, vendor, device,
+				   subvendor, subdevice, class, class_mask, 0);
+		if (rc)
+			pr_warn("failed to add dynamic id [%04x:%04x[%04x:%04x]] class %#08x/%08x (%d)\n",
+				vendor, device, subvendor, subdevice,
+				class, class_mask, rc);
+		else
+			pr_info("add [%04x:%04x[%04x:%04x]] class %#08x/%08x\n",
+				vendor, device, subvendor, subdevice,
+				class, class_mask);
+	}
+}
+
+static int __init vfio_pci_init(void)
+{
+	int ret;
+
+	ret = vfio_pci_core_init();
+	if (ret)
+		return ret;
+
+	/* Register and scan for devices */
+	ret = pci_register_driver(&vfio_pci_driver);
+	if (ret)
+		goto out;
+
+	vfio_pci_fill_ids();
+
+	if (disable_denylist)
+		pr_warn("device denylist disabled.\n");
+
+	return 0;
+
+out:
+	vfio_pci_core_cleanup();
+	return ret;
+}
+module_init(vfio_pci_init);
+
+static void __exit vfio_pci_cleanup(void)
+{
+	pci_unregister_driver(&vfio_pci_driver);
+	vfio_pci_core_cleanup();
+}
+module_exit(vfio_pci_cleanup);
+
+MODULE_LICENSE("GPL v2");
+MODULE_AUTHOR(DRIVER_AUTHOR);
+MODULE_DESCRIPTION(DRIVER_DESC);
diff --git a/drivers/vfio/pci/vfio_pci_core.c b/drivers/vfio/pci/vfio_pci_core.c
index 94f062818e0c..c0d71f72d4f1 100644
--- a/drivers/vfio/pci/vfio_pci_core.c
+++ b/drivers/vfio/pci/vfio_pci_core.c
@@ -8,8 +8,6 @@
  * Author: Tom Lyon, pugs@cisco.com
  */
 
-#define pr_fmt(fmt) KBUILD_MODNAME ": " fmt
-
 #include <linux/device.h>
 #include <linux/eventfd.h>
 #include <linux/file.h>
@@ -29,14 +27,6 @@
 
 #include "vfio_pci_core.h"
 
-#define DRIVER_VERSION  "0.2"
-#define DRIVER_AUTHOR   "Alex Williamson <alex.williamson@redhat.com>"
-#define DRIVER_DESC     "VFIO PCI - User Level meta-driver"
-
-static char ids[1024] __initdata;
-module_param_string(ids, ids, sizeof(ids), 0);
-MODULE_PARM_DESC(ids, "Initial PCI IDs to add to the vfio driver, format is \"vendor:device[:subvendor[:subdevice[:class[:class_mask]]]]\" and multiple comma separated entries can be specified");
-
 static bool nointxmask;
 module_param_named(nointxmask, nointxmask, bool, S_IRUGO | S_IWUSR);
 MODULE_PARM_DESC(nointxmask,
@@ -53,16 +43,6 @@ module_param(disable_idle_d3, bool, S_IRUGO | S_IWUSR);
 MODULE_PARM_DESC(disable_idle_d3,
 		 "Disable using the PCI D3 low power state for idle, unused devices");
 
-static bool enable_sriov;
-#ifdef CONFIG_PCI_IOV
-module_param(enable_sriov, bool, 0644);
-MODULE_PARM_DESC(enable_sriov, "Enable support for SR-IOV configuration.  Enabling SR-IOV on a PF typically requires support of the userspace PF driver, enabling VFs without such support may result in non-functional VFs or PF.");
-#endif
-
-static bool disable_denylist;
-module_param(disable_denylist, bool, 0444);
-MODULE_PARM_DESC(disable_denylist, "Disable use of device denylist. Disabling the denylist allows binding to devices with known errata that may lead to exploitable stability or security issues when accessed by untrusted users.");
-
 static inline bool vfio_vga_disabled(void)
 {
 #ifdef CONFIG_VFIO_PCI_VGA
@@ -72,44 +52,6 @@ static inline bool vfio_vga_disabled(void)
 #endif
 }
 
-static bool vfio_pci_dev_in_denylist(struct pci_dev *pdev)
-{
-	switch (pdev->vendor) {
-	case PCI_VENDOR_ID_INTEL:
-		switch (pdev->device) {
-		case PCI_DEVICE_ID_INTEL_QAT_C3XXX:
-		case PCI_DEVICE_ID_INTEL_QAT_C3XXX_VF:
-		case PCI_DEVICE_ID_INTEL_QAT_C62X:
-		case PCI_DEVICE_ID_INTEL_QAT_C62X_VF:
-		case PCI_DEVICE_ID_INTEL_QAT_DH895XCC:
-		case PCI_DEVICE_ID_INTEL_QAT_DH895XCC_VF:
-			return true;
-		default:
-			return false;
-		}
-	}
-
-	return false;
-}
-
-static bool vfio_pci_is_denylisted(struct pci_dev *pdev)
-{
-	if (!vfio_pci_dev_in_denylist(pdev))
-		return false;
-
-	if (disable_denylist) {
-		pci_warn(pdev,
-			 "device denylist disabled - allowing device %04x:%04x.\n",
-			 pdev->vendor, pdev->device);
-		return false;
-	}
-
-	pci_warn(pdev, "%04x:%04x exists in vfio-pci device denylist, driver probing disallowed.\n",
-		 pdev->vendor, pdev->device);
-
-	return true;
-}
-
 /*
  * Our VGA arbiter participation is limited since we don't know anything
  * about the device itself.  However, if the device is the only VGA device
@@ -495,8 +437,6 @@ static void vfio_pci_disable(struct vfio_pci_core_device *vdev)
 		vfio_pci_set_power_state(vdev, PCI_D3hot);
 }
 
-static struct pci_driver vfio_pci_driver;
-
 static struct vfio_pci_core_device *get_pf_vdev(struct vfio_pci_core_device *vdev)
 {
 	struct pci_dev *physfn = pci_physfn(vdev->pdev);
@@ -509,7 +449,7 @@ static struct vfio_pci_core_device *get_pf_vdev(struct vfio_pci_core_device *vde
 	if (!pf_dev)
 		return NULL;
 
-	if (pci_dev_driver(physfn) != &vfio_pci_driver) {
+	if (pci_dev_driver(physfn) != pci_dev_driver(vdev->pdev)) {
 		vfio_device_put(pf_dev);
 		return NULL;
 	}
@@ -532,7 +472,7 @@ static void vfio_pci_vf_token_user_add(struct vfio_pci_core_device *vdev, int va
 	vfio_device_put(&pf_vdev->vdev);
 }
 
-static void vfio_pci_core_close_device(struct vfio_device *core_vdev)
+void vfio_pci_core_close_device(struct vfio_device *core_vdev)
 {
 	struct vfio_pci_core_device *vdev =
 		container_of(core_vdev, struct vfio_pci_core_device, vdev);
@@ -553,7 +493,7 @@ static void vfio_pci_core_close_device(struct vfio_device *core_vdev)
 	mutex_unlock(&vdev->igate);
 }
 
-static int vfio_pci_core_open_device(struct vfio_device *core_vdev)
+int vfio_pci_core_open_device(struct vfio_device *core_vdev)
 {
 	struct vfio_pci_core_device *vdev =
 		container_of(core_vdev, struct vfio_pci_core_device, vdev);
@@ -726,8 +666,8 @@ int vfio_pci_register_dev_region(struct vfio_pci_core_device *vdev,
 	return 0;
 }
 
-static long vfio_pci_core_ioctl(struct vfio_device *core_vdev,
-			   unsigned int cmd, unsigned long arg)
+long vfio_pci_core_ioctl(struct vfio_device *core_vdev, unsigned int cmd,
+		unsigned long arg)
 {
 	struct vfio_pci_core_device *vdev =
 		container_of(core_vdev, struct vfio_pci_core_device, vdev);
@@ -1301,8 +1241,8 @@ static ssize_t vfio_pci_rw(struct vfio_pci_core_device *vdev, char __user *buf,
 	return -EINVAL;
 }
 
-static ssize_t vfio_pci_core_read(struct vfio_device *core_vdev, char __user *buf,
-			     size_t count, loff_t *ppos)
+ssize_t vfio_pci_core_read(struct vfio_device *core_vdev, char __user *buf,
+		size_t count, loff_t *ppos)
 {
 	struct vfio_pci_core_device *vdev =
 		container_of(core_vdev, struct vfio_pci_core_device, vdev);
@@ -1313,8 +1253,8 @@ static ssize_t vfio_pci_core_read(struct vfio_device *core_vdev, char __user *bu
 	return vfio_pci_rw(vdev, buf, count, ppos, false);
 }
 
-static ssize_t vfio_pci_core_write(struct vfio_device *core_vdev, const char __user *buf,
-			      size_t count, loff_t *ppos)
+ssize_t vfio_pci_core_write(struct vfio_device *core_vdev, const char __user *buf,
+		size_t count, loff_t *ppos)
 {
 	struct vfio_pci_core_device *vdev =
 		container_of(core_vdev, struct vfio_pci_core_device, vdev);
@@ -1532,7 +1472,7 @@ static const struct vm_operations_struct vfio_pci_mmap_ops = {
 	.fault = vfio_pci_mmap_fault,
 };
 
-static int vfio_pci_core_mmap(struct vfio_device *core_vdev, struct vm_area_struct *vma)
+int vfio_pci_core_mmap(struct vfio_device *core_vdev, struct vm_area_struct *vma)
 {
 	struct vfio_pci_core_device *vdev =
 		container_of(core_vdev, struct vfio_pci_core_device, vdev);
@@ -1603,7 +1543,7 @@ static int vfio_pci_core_mmap(struct vfio_device *core_vdev, struct vm_area_stru
 	return 0;
 }
 
-static void vfio_pci_core_request(struct vfio_device *core_vdev, unsigned int count)
+void vfio_pci_core_request(struct vfio_device *core_vdev, unsigned int count)
 {
 	struct vfio_pci_core_device *vdev =
 		container_of(core_vdev, struct vfio_pci_core_device, vdev);
@@ -1719,7 +1659,7 @@ static int vfio_pci_validate_vf_token(struct vfio_pci_core_device *vdev,
 
 #define VF_TOKEN_ARG "vf_token="
 
-static int vfio_pci_core_match(struct vfio_device *core_vdev, char *buf)
+int vfio_pci_core_match(struct vfio_device *core_vdev, char *buf)
 {
 	struct vfio_pci_core_device *vdev =
 		container_of(core_vdev, struct vfio_pci_core_device, vdev);
@@ -1769,18 +1709,6 @@ static int vfio_pci_core_match(struct vfio_device *core_vdev, char *buf)
 	return 1; /* Match */
 }
 
-static const struct vfio_device_ops vfio_pci_ops = {
-	.name		= "vfio-pci",
-	.open_device	= vfio_pci_core_open_device,
-	.close_device	= vfio_pci_core_close_device,
-	.ioctl		= vfio_pci_core_ioctl,
-	.read		= vfio_pci_core_read,
-	.write		= vfio_pci_core_write,
-	.mmap		= vfio_pci_core_mmap,
-	.request	= vfio_pci_core_request,
-	.match		= vfio_pci_core_match,
-};
-
 static int vfio_pci_bus_notifier(struct notifier_block *nb,
 				 unsigned long action, void *data)
 {
@@ -1795,15 +1723,16 @@ static int vfio_pci_bus_notifier(struct notifier_block *nb,
 		pci_info(vdev->pdev, "Captured SR-IOV VF %s driver_override\n",
 			 pci_name(pdev));
 		pdev->driver_override = kasprintf(GFP_KERNEL, "%s",
-						  vfio_pci_ops.name);
+						  vdev->vdev.ops->name);
 	} else if (action == BUS_NOTIFY_BOUND_DRIVER &&
 		   pdev->is_virtfn && physfn == vdev->pdev) {
 		struct pci_driver *drv = pci_dev_driver(pdev);
 
-		if (drv && drv != &vfio_pci_driver)
+		if (drv && drv != pci_dev_driver(vdev->pdev))
 			pci_warn(vdev->pdev,
-				 "VF %s bound to driver %s while PF bound to vfio-pci\n",
-				 pci_name(pdev), drv->name);
+				 "VF %s bound to driver %s while PF bound to driver %s\n",
+				 pci_name(pdev), drv->name,
+				 pci_dev_driver(vdev->pdev)->name);
 	}
 
 	return 0;
@@ -1871,15 +1800,39 @@ static void vfio_pci_vga_uninit(struct vfio_pci_core_device *vdev)
 					      VGA_RSRC_LEGACY_MEM);
 }
 
-static int vfio_pci_probe(struct pci_dev *pdev, const struct pci_device_id *id)
+void vfio_pci_core_init_device(struct vfio_pci_core_device *vdev,
+			       struct pci_dev *pdev,
+			       const struct vfio_device_ops *vfio_pci_ops)
 {
-	struct vfio_pci_core_device *vdev;
+	vfio_init_group_dev(&vdev->vdev, &pdev->dev, vfio_pci_ops);
+	vdev->pdev = pdev;
+	vdev->irq_type = VFIO_PCI_NUM_IRQS;
+	mutex_init(&vdev->igate);
+	spin_lock_init(&vdev->irqlock);
+	mutex_init(&vdev->ioeventfds_lock);
+	INIT_LIST_HEAD(&vdev->dummy_resources_list);
+	INIT_LIST_HEAD(&vdev->ioeventfds_list);
+	mutex_init(&vdev->vma_lock);
+	INIT_LIST_HEAD(&vdev->vma_list);
+	init_rwsem(&vdev->memory_lock);
+}
+
+void vfio_pci_core_uninit_device(struct vfio_pci_core_device *vdev)
+{
+	mutex_destroy(&vdev->igate);
+	mutex_destroy(&vdev->ioeventfds_lock);
+	mutex_destroy(&vdev->vma_lock);
+	vfio_uninit_group_dev(&vdev->vdev);
+	kfree(vdev->region);
+	kfree(vdev->pm_save);
+}
+
+int vfio_pci_core_register_device(struct vfio_pci_core_device *vdev)
+{
+	struct pci_dev *pdev = vdev->pdev;
 	struct iommu_group *group;
 	int ret;
 
-	if (vfio_pci_is_denylisted(pdev))
-		return -EINVAL;
-
 	if (pdev->hdr_type != PCI_HEADER_TYPE_NORMAL)
 		return -EINVAL;
 
@@ -1900,24 +1853,6 @@ static int vfio_pci_probe(struct pci_dev *pdev, const struct pci_device_id *id)
 	if (!group)
 		return -EINVAL;
 
-	vdev = kzalloc(sizeof(*vdev), GFP_KERNEL);
-	if (!vdev) {
-		ret = -ENOMEM;
-		goto out_group_put;
-	}
-
-	vfio_init_group_dev(&vdev->vdev, &pdev->dev, &vfio_pci_ops);
-	vdev->pdev = pdev;
-	vdev->irq_type = VFIO_PCI_NUM_IRQS;
-	mutex_init(&vdev->igate);
-	spin_lock_init(&vdev->irqlock);
-	mutex_init(&vdev->ioeventfds_lock);
-	INIT_LIST_HEAD(&vdev->dummy_resources_list);
-	INIT_LIST_HEAD(&vdev->ioeventfds_list);
-	mutex_init(&vdev->vma_lock);
-	INIT_LIST_HEAD(&vdev->vma_list);
-	init_rwsem(&vdev->memory_lock);
-
 	if (pci_is_root_bus(pdev->bus)) {
 		ret = vfio_assign_device_set(&vdev->vdev, vdev);
 	} else if (!pci_probe_reset_slot(pdev->slot)) {
@@ -1931,10 +1866,10 @@ static int vfio_pci_probe(struct pci_dev *pdev, const struct pci_device_id *id)
 	}
 
 	if (ret)
-		goto out_uninit;
+		goto out_group_put;
 	ret = vfio_pci_vf_init(vdev);
 	if (ret)
-		goto out_uninit;
+		goto out_group_put;
 	ret = vfio_pci_vga_init(vdev);
 	if (ret)
 		goto out_vf;
@@ -1966,36 +1901,26 @@ static int vfio_pci_probe(struct pci_dev *pdev, const struct pci_device_id *id)
 		vfio_pci_set_power_state(vdev, PCI_D0);
 out_vf:
 	vfio_pci_vf_uninit(vdev);
-out_uninit:
-	vfio_uninit_group_dev(&vdev->vdev);
-	kfree(vdev->pm_save);
-	kfree(vdev);
 out_group_put:
 	vfio_iommu_group_put(group, &pdev->dev);
 	return ret;
 }
 
-static void vfio_pci_remove(struct pci_dev *pdev)
+void vfio_pci_core_unregister_device(struct vfio_pci_core_device *vdev)
 {
-	struct vfio_pci_core_device *vdev = dev_get_drvdata(&pdev->dev);
+	struct pci_dev *pdev = vdev->pdev;
 
 	pci_disable_sriov(pdev);
 
 	vfio_unregister_group_dev(&vdev->vdev);
 
 	vfio_pci_vf_uninit(vdev);
-	vfio_uninit_group_dev(&vdev->vdev);
 	vfio_pci_vga_uninit(vdev);
 
 	vfio_iommu_group_put(pdev->dev.iommu_group, &pdev->dev);
 
 	if (!disable_idle_d3)
 		vfio_pci_set_power_state(vdev, PCI_D0);
-
-	mutex_destroy(&vdev->ioeventfds_lock);
-	kfree(vdev->region);
-	kfree(vdev->pm_save);
-	kfree(vdev);
 }
 
 static pci_ers_result_t vfio_pci_aer_err_detected(struct pci_dev *pdev,
@@ -2022,16 +1947,11 @@ static pci_ers_result_t vfio_pci_aer_err_detected(struct pci_dev *pdev,
 	return PCI_ERS_RESULT_CAN_RECOVER;
 }
 
-static int vfio_pci_sriov_configure(struct pci_dev *pdev, int nr_virtfn)
+int vfio_pci_core_sriov_configure(struct pci_dev *pdev, int nr_virtfn)
 {
 	struct vfio_device *device;
 	int ret = 0;
 
-	might_sleep();
-
-	if (!enable_sriov)
-		return -ENOENT;
-
 	device = vfio_device_get_from_dev(&pdev->dev);
 	if (!device)
 		return -ENODEV;
@@ -2046,19 +1966,10 @@ static int vfio_pci_sriov_configure(struct pci_dev *pdev, int nr_virtfn)
 	return ret < 0 ? ret : nr_virtfn;
 }
 
-static const struct pci_error_handlers vfio_err_handlers = {
+const struct pci_error_handlers vfio_pci_core_err_handlers = {
 	.error_detected = vfio_pci_aer_err_detected,
 };
 
-static struct pci_driver vfio_pci_driver = {
-	.name			= "vfio-pci",
-	.id_table		= NULL, /* only dynamic ids */
-	.probe			= vfio_pci_probe,
-	.remove			= vfio_pci_remove,
-	.sriov_configure	= vfio_pci_sriov_configure,
-	.err_handler		= &vfio_err_handlers,
-};
-
 static bool vfio_dev_in_groups(struct vfio_pci_core_device *vdev,
 			       struct vfio_pci_group_info *groups)
 {
@@ -2239,83 +2150,15 @@ static bool vfio_pci_dev_set_try_reset(struct vfio_device_set *dev_set)
 	return true;
 }
 
-static void __exit vfio_pci_cleanup(void)
+/* This will become the __exit function of vfio_pci_core.ko */
+void vfio_pci_core_cleanup(void)
 {
-	pci_unregister_driver(&vfio_pci_driver);
 	vfio_pci_uninit_perm_bits();
 }
 
-static void __init vfio_pci_fill_ids(void)
+/* This will become the __init function of vfio_pci_core.ko */
+int __init vfio_pci_core_init(void)
 {
-	char *p, *id;
-	int rc;
-
-	/* no ids passed actually */
-	if (ids[0] == '\0')
-		return;
-
-	/* add ids specified in the module parameter */
-	p = ids;
-	while ((id = strsep(&p, ","))) {
-		unsigned int vendor, device, subvendor = PCI_ANY_ID,
-			subdevice = PCI_ANY_ID, class = 0, class_mask = 0;
-		int fields;
-
-		if (!strlen(id))
-			continue;
-
-		fields = sscanf(id, "%x:%x:%x:%x:%x:%x",
-				&vendor, &device, &subvendor, &subdevice,
-				&class, &class_mask);
-
-		if (fields < 2) {
-			pr_warn("invalid id string \"%s\"\n", id);
-			continue;
-		}
-
-		rc = pci_add_dynid(&vfio_pci_driver, vendor, device,
-				   subvendor, subdevice, class, class_mask, 0);
-		if (rc)
-			pr_warn("failed to add dynamic id [%04x:%04x[%04x:%04x]] class %#08x/%08x (%d)\n",
-				vendor, device, subvendor, subdevice,
-				class, class_mask, rc);
-		else
-			pr_info("add [%04x:%04x[%04x:%04x]] class %#08x/%08x\n",
-				vendor, device, subvendor, subdevice,
-				class, class_mask);
-	}
-}
-
-static int __init vfio_pci_init(void)
-{
-	int ret;
-
 	/* Allocate shared config space permission data used by all devices */
-	ret = vfio_pci_init_perm_bits();
-	if (ret)
-		return ret;
-
-	/* Register and scan for devices */
-	ret = pci_register_driver(&vfio_pci_driver);
-	if (ret)
-		goto out_driver;
-
-	vfio_pci_fill_ids();
-
-	if (disable_denylist)
-		pr_warn("device denylist disabled.\n");
-
-	return 0;
-
-out_driver:
-	vfio_pci_uninit_perm_bits();
-	return ret;
+	return vfio_pci_init_perm_bits();
 }
-
-module_init(vfio_pci_init);
-module_exit(vfio_pci_cleanup);
-
-MODULE_VERSION(DRIVER_VERSION);
-MODULE_LICENSE("GPL v2");
-MODULE_AUTHOR(DRIVER_AUTHOR);
-MODULE_DESCRIPTION(DRIVER_DESC);
diff --git a/drivers/vfio/pci/vfio_pci_core.h b/drivers/vfio/pci/vfio_pci_core.h
index 17ad048752b6..7dbdd4dda5c0 100644
--- a/drivers/vfio/pci/vfio_pci_core.h
+++ b/drivers/vfio/pci/vfio_pci_core.h
@@ -206,4 +206,27 @@ static inline int vfio_pci_info_zdev_add_caps(struct vfio_pci_core_device *vdev,
 }
 #endif
 
+/* Will be exported for vfio pci drivers usage */
+void vfio_pci_core_cleanup(void);
+int vfio_pci_core_init(void);
+void vfio_pci_core_close_device(struct vfio_device *core_vdev);
+int vfio_pci_core_open_device(struct vfio_device *core_vdev);
+void vfio_pci_core_init_device(struct vfio_pci_core_device *vdev,
+			       struct pci_dev *pdev,
+			       const struct vfio_device_ops *vfio_pci_ops);
+int vfio_pci_core_register_device(struct vfio_pci_core_device *vdev);
+void vfio_pci_core_uninit_device(struct vfio_pci_core_device *vdev);
+void vfio_pci_core_unregister_device(struct vfio_pci_core_device *vdev);
+int vfio_pci_core_sriov_configure(struct pci_dev *pdev, int nr_virtfn);
+extern const struct pci_error_handlers vfio_pci_core_err_handlers;
+long vfio_pci_core_ioctl(struct vfio_device *core_vdev, unsigned int cmd,
+		unsigned long arg);
+ssize_t vfio_pci_core_read(struct vfio_device *core_vdev, char __user *buf,
+		size_t count, loff_t *ppos);
+ssize_t vfio_pci_core_write(struct vfio_device *core_vdev, const char __user *buf,
+		size_t count, loff_t *ppos);
+int vfio_pci_core_mmap(struct vfio_device *core_vdev, struct vm_area_struct *vma);
+void vfio_pci_core_request(struct vfio_device *core_vdev, unsigned int count);
+int vfio_pci_core_match(struct vfio_device *core_vdev, char *buf);
+
 #endif /* VFIO_PCI_CORE_H */

