From: Max Gurtovoy <mgurtovoy@nvidia.com>
Date: Thu, 26 Aug 2021 13:39:01 +0300
Subject: vfio/pci: Rename vfio_pci_private.h to vfio_pci_core.h
Git-commit: 9a389938695a068a3149c2d21a16c34b63ca002f
Patch-mainline: v5.15-rc1
References: bsc#1205701

This is a preparation patch for separating the vfio_pci driver to a
subsystem driver and a generic pci driver. This patch doesn't change any
logic.

Signed-off-by: Max Gurtovoy <mgurtovoy@nvidia.com>
Reviewed-by: Christoph Hellwig <hch@lst.de>
Signed-off-by: Yishai Hadas <yishaih@nvidia.com>
Link: https://lore.kernel.org/r/20210826103912.128972-3-yishaih@nvidia.com
Signed-off-by: Alex Williamson <alex.williamson@redhat.com>
Acked-by: Joerg Roedel <jroedel@suse.de>
---
 drivers/vfio/pci/vfio_pci_config.c  |   2 +-
 drivers/vfio/pci/vfio_pci_core.c    |   2 +-
 drivers/vfio/pci/vfio_pci_core.h    | 208 ++++++++++++++++++++++++++++++++++++
 drivers/vfio/pci/vfio_pci_igd.c     |   2 +-
 drivers/vfio/pci/vfio_pci_intrs.c   |   2 +-
 drivers/vfio/pci/vfio_pci_private.h | 208 ------------------------------------
 drivers/vfio/pci/vfio_pci_rdwr.c    |   2 +-
 drivers/vfio/pci/vfio_pci_zdev.c    |   2 +-
 8 files changed, 214 insertions(+), 214 deletions(-)

diff --git a/drivers/vfio/pci/vfio_pci_config.c b/drivers/vfio/pci/vfio_pci_config.c
index 70e28efbc51f..0bc269c0b03f 100644
--- a/drivers/vfio/pci/vfio_pci_config.c
+++ b/drivers/vfio/pci/vfio_pci_config.c
@@ -26,7 +26,7 @@
 #include <linux/vfio.h>
 #include <linux/slab.h>
 
-#include "vfio_pci_private.h"
+#include "vfio_pci_core.h"
 
 /* Fake capability ID for standard config space */
 #define PCI_CAP_ID_BASIC	0
diff --git a/drivers/vfio/pci/vfio_pci_core.c b/drivers/vfio/pci/vfio_pci_core.c
index a4f44ea52fa3..2a5dca0823c4 100644
--- a/drivers/vfio/pci/vfio_pci_core.c
+++ b/drivers/vfio/pci/vfio_pci_core.c
@@ -28,7 +28,7 @@
 #include <linux/nospec.h>
 #include <linux/sched/mm.h>
 
-#include "vfio_pci_private.h"
+#include "vfio_pci_core.h"
 
 #define DRIVER_VERSION  "0.2"
 #define DRIVER_AUTHOR   "Alex Williamson <alex.williamson@redhat.com>"
diff --git a/drivers/vfio/pci/vfio_pci_core.h b/drivers/vfio/pci/vfio_pci_core.h
new file mode 100644
index 000000000000..ef26e781961d
--- /dev/null
+++ b/drivers/vfio/pci/vfio_pci_core.h
@@ -0,0 +1,208 @@
+/* SPDX-License-Identifier: GPL-2.0-only */
+/*
+ * Copyright (C) 2012 Red Hat, Inc.  All rights reserved.
+ *     Author: Alex Williamson <alex.williamson@redhat.com>
+ *
+ * Derived from original vfio:
+ * Copyright 2010 Cisco Systems, Inc.  All rights reserved.
+ * Author: Tom Lyon, pugs@cisco.com
+ */
+
+#include <linux/mutex.h>
+#include <linux/pci.h>
+#include <linux/irqbypass.h>
+#include <linux/types.h>
+#include <linux/uuid.h>
+#include <linux/notifier.h>
+
+#ifndef VFIO_PCI_CORE_H
+#define VFIO_PCI_CORE_H
+
+#define VFIO_PCI_OFFSET_SHIFT   40
+
+#define VFIO_PCI_OFFSET_TO_INDEX(off)	(off >> VFIO_PCI_OFFSET_SHIFT)
+#define VFIO_PCI_INDEX_TO_OFFSET(index)	((u64)(index) << VFIO_PCI_OFFSET_SHIFT)
+#define VFIO_PCI_OFFSET_MASK	(((u64)(1) << VFIO_PCI_OFFSET_SHIFT) - 1)
+
+/* Special capability IDs predefined access */
+#define PCI_CAP_ID_INVALID		0xFF	/* default raw access */
+#define PCI_CAP_ID_INVALID_VIRT		0xFE	/* default virt access */
+
+/* Cap maximum number of ioeventfds per device (arbitrary) */
+#define VFIO_PCI_IOEVENTFD_MAX		1000
+
+struct vfio_pci_ioeventfd {
+	struct list_head	next;
+	struct vfio_pci_device	*vdev;
+	struct virqfd		*virqfd;
+	void __iomem		*addr;
+	uint64_t		data;
+	loff_t			pos;
+	int			bar;
+	int			count;
+	bool			test_mem;
+};
+
+struct vfio_pci_irq_ctx {
+	struct eventfd_ctx	*trigger;
+	struct virqfd		*unmask;
+	struct virqfd		*mask;
+	char			*name;
+	bool			masked;
+	struct irq_bypass_producer	producer;
+};
+
+struct vfio_pci_device;
+struct vfio_pci_region;
+
+struct vfio_pci_regops {
+	ssize_t	(*rw)(struct vfio_pci_device *vdev, char __user *buf,
+		      size_t count, loff_t *ppos, bool iswrite);
+	void	(*release)(struct vfio_pci_device *vdev,
+			   struct vfio_pci_region *region);
+	int	(*mmap)(struct vfio_pci_device *vdev,
+			struct vfio_pci_region *region,
+			struct vm_area_struct *vma);
+	int	(*add_capability)(struct vfio_pci_device *vdev,
+				  struct vfio_pci_region *region,
+				  struct vfio_info_cap *caps);
+};
+
+struct vfio_pci_region {
+	u32				type;
+	u32				subtype;
+	const struct vfio_pci_regops	*ops;
+	void				*data;
+	size_t				size;
+	u32				flags;
+};
+
+struct vfio_pci_dummy_resource {
+	struct resource		resource;
+	int			index;
+	struct list_head	res_next;
+};
+
+struct vfio_pci_vf_token {
+	struct mutex		lock;
+	uuid_t			uuid;
+	int			users;
+};
+
+struct vfio_pci_mmap_vma {
+	struct vm_area_struct	*vma;
+	struct list_head	vma_next;
+};
+
+struct vfio_pci_device {
+	struct vfio_device	vdev;
+	struct pci_dev		*pdev;
+	void __iomem		*barmap[PCI_STD_NUM_BARS];
+	bool			bar_mmap_supported[PCI_STD_NUM_BARS];
+	u8			*pci_config_map;
+	u8			*vconfig;
+	struct perm_bits	*msi_perm;
+	spinlock_t		irqlock;
+	struct mutex		igate;
+	struct vfio_pci_irq_ctx	*ctx;
+	int			num_ctx;
+	int			irq_type;
+	int			num_regions;
+	struct vfio_pci_region	*region;
+	u8			msi_qmax;
+	u8			msix_bar;
+	u16			msix_size;
+	u32			msix_offset;
+	u32			rbar[7];
+	bool			pci_2_3;
+	bool			virq_disabled;
+	bool			reset_works;
+	bool			extended_caps;
+	bool			bardirty;
+	bool			has_vga;
+	bool			needs_reset;
+	bool			nointx;
+	bool			needs_pm_restore;
+	struct pci_saved_state	*pci_saved_state;
+	struct pci_saved_state	*pm_save;
+	int			ioeventfds_nr;
+	struct eventfd_ctx	*err_trigger;
+	struct eventfd_ctx	*req_trigger;
+	struct list_head	dummy_resources_list;
+	struct mutex		ioeventfds_lock;
+	struct list_head	ioeventfds_list;
+	struct vfio_pci_vf_token	*vf_token;
+	struct notifier_block	nb;
+	struct mutex		vma_lock;
+	struct list_head	vma_list;
+	struct rw_semaphore	memory_lock;
+};
+
+#define is_intx(vdev) (vdev->irq_type == VFIO_PCI_INTX_IRQ_INDEX)
+#define is_msi(vdev) (vdev->irq_type == VFIO_PCI_MSI_IRQ_INDEX)
+#define is_msix(vdev) (vdev->irq_type == VFIO_PCI_MSIX_IRQ_INDEX)
+#define is_irq_none(vdev) (!(is_intx(vdev) || is_msi(vdev) || is_msix(vdev)))
+#define irq_is(vdev, type) (vdev->irq_type == type)
+
+extern void vfio_pci_intx_mask(struct vfio_pci_device *vdev);
+extern void vfio_pci_intx_unmask(struct vfio_pci_device *vdev);
+
+extern int vfio_pci_set_irqs_ioctl(struct vfio_pci_device *vdev,
+				   uint32_t flags, unsigned index,
+				   unsigned start, unsigned count, void *data);
+
+extern ssize_t vfio_pci_config_rw(struct vfio_pci_device *vdev,
+				  char __user *buf, size_t count,
+				  loff_t *ppos, bool iswrite);
+
+extern ssize_t vfio_pci_bar_rw(struct vfio_pci_device *vdev, char __user *buf,
+			       size_t count, loff_t *ppos, bool iswrite);
+
+extern ssize_t vfio_pci_vga_rw(struct vfio_pci_device *vdev, char __user *buf,
+			       size_t count, loff_t *ppos, bool iswrite);
+
+extern long vfio_pci_ioeventfd(struct vfio_pci_device *vdev, loff_t offset,
+			       uint64_t data, int count, int fd);
+
+extern int vfio_pci_init_perm_bits(void);
+extern void vfio_pci_uninit_perm_bits(void);
+
+extern int vfio_config_init(struct vfio_pci_device *vdev);
+extern void vfio_config_free(struct vfio_pci_device *vdev);
+
+extern int vfio_pci_register_dev_region(struct vfio_pci_device *vdev,
+					unsigned int type, unsigned int subtype,
+					const struct vfio_pci_regops *ops,
+					size_t size, u32 flags, void *data);
+
+extern int vfio_pci_set_power_state(struct vfio_pci_device *vdev,
+				    pci_power_t state);
+
+extern bool __vfio_pci_memory_enabled(struct vfio_pci_device *vdev);
+extern void vfio_pci_zap_and_down_write_memory_lock(struct vfio_pci_device
+						    *vdev);
+extern u16 vfio_pci_memory_lock_and_enable(struct vfio_pci_device *vdev);
+extern void vfio_pci_memory_unlock_and_restore(struct vfio_pci_device *vdev,
+					       u16 cmd);
+
+#ifdef CONFIG_VFIO_PCI_IGD
+extern int vfio_pci_igd_init(struct vfio_pci_device *vdev);
+#else
+static inline int vfio_pci_igd_init(struct vfio_pci_device *vdev)
+{
+	return -ENODEV;
+}
+#endif
+
+#ifdef CONFIG_S390
+extern int vfio_pci_info_zdev_add_caps(struct vfio_pci_device *vdev,
+				       struct vfio_info_cap *caps);
+#else
+static inline int vfio_pci_info_zdev_add_caps(struct vfio_pci_device *vdev,
+					      struct vfio_info_cap *caps)
+{
+	return -ENODEV;
+}
+#endif
+
+#endif /* VFIO_PCI_CORE_H */
diff --git a/drivers/vfio/pci/vfio_pci_igd.c b/drivers/vfio/pci/vfio_pci_igd.c
index aa0a29fd2762..d57c409b4033 100644
--- a/drivers/vfio/pci/vfio_pci_igd.c
+++ b/drivers/vfio/pci/vfio_pci_igd.c
@@ -15,7 +15,7 @@
 #include <linux/uaccess.h>
 #include <linux/vfio.h>
 
-#include "vfio_pci_private.h"
+#include "vfio_pci_core.h"
 
 #define OPREGION_SIGNATURE	"IntelGraphicsMem"
 #define OPREGION_SIZE		(8 * 1024)
diff --git a/drivers/vfio/pci/vfio_pci_intrs.c b/drivers/vfio/pci/vfio_pci_intrs.c
index 869dce5f134d..df1e8c8c274c 100644
--- a/drivers/vfio/pci/vfio_pci_intrs.c
+++ b/drivers/vfio/pci/vfio_pci_intrs.c
@@ -20,7 +20,7 @@
 #include <linux/wait.h>
 #include <linux/slab.h>
 
-#include "vfio_pci_private.h"
+#include "vfio_pci_core.h"
 
 /*
  * INTx
diff --git a/drivers/vfio/pci/vfio_pci_private.h b/drivers/vfio/pci/vfio_pci_private.h
deleted file mode 100644
index 70414b6c904d..000000000000
--- a/drivers/vfio/pci/vfio_pci_private.h
+++ /dev/null
@@ -1,208 +0,0 @@
-/* SPDX-License-Identifier: GPL-2.0-only */
-/*
- * Copyright (C) 2012 Red Hat, Inc.  All rights reserved.
- *     Author: Alex Williamson <alex.williamson@redhat.com>
- *
- * Derived from original vfio:
- * Copyright 2010 Cisco Systems, Inc.  All rights reserved.
- * Author: Tom Lyon, pugs@cisco.com
- */
-
-#include <linux/mutex.h>
-#include <linux/pci.h>
-#include <linux/irqbypass.h>
-#include <linux/types.h>
-#include <linux/uuid.h>
-#include <linux/notifier.h>
-
-#ifndef VFIO_PCI_PRIVATE_H
-#define VFIO_PCI_PRIVATE_H
-
-#define VFIO_PCI_OFFSET_SHIFT   40
-
-#define VFIO_PCI_OFFSET_TO_INDEX(off)	(off >> VFIO_PCI_OFFSET_SHIFT)
-#define VFIO_PCI_INDEX_TO_OFFSET(index)	((u64)(index) << VFIO_PCI_OFFSET_SHIFT)
-#define VFIO_PCI_OFFSET_MASK	(((u64)(1) << VFIO_PCI_OFFSET_SHIFT) - 1)
-
-/* Special capability IDs predefined access */
-#define PCI_CAP_ID_INVALID		0xFF	/* default raw access */
-#define PCI_CAP_ID_INVALID_VIRT		0xFE	/* default virt access */
-
-/* Cap maximum number of ioeventfds per device (arbitrary) */
-#define VFIO_PCI_IOEVENTFD_MAX		1000
-
-struct vfio_pci_ioeventfd {
-	struct list_head	next;
-	struct vfio_pci_device	*vdev;
-	struct virqfd		*virqfd;
-	void __iomem		*addr;
-	uint64_t		data;
-	loff_t			pos;
-	int			bar;
-	int			count;
-	bool			test_mem;
-};
-
-struct vfio_pci_irq_ctx {
-	struct eventfd_ctx	*trigger;
-	struct virqfd		*unmask;
-	struct virqfd		*mask;
-	char			*name;
-	bool			masked;
-	struct irq_bypass_producer	producer;
-};
-
-struct vfio_pci_device;
-struct vfio_pci_region;
-
-struct vfio_pci_regops {
-	ssize_t	(*rw)(struct vfio_pci_device *vdev, char __user *buf,
-		      size_t count, loff_t *ppos, bool iswrite);
-	void	(*release)(struct vfio_pci_device *vdev,
-			   struct vfio_pci_region *region);
-	int	(*mmap)(struct vfio_pci_device *vdev,
-			struct vfio_pci_region *region,
-			struct vm_area_struct *vma);
-	int	(*add_capability)(struct vfio_pci_device *vdev,
-				  struct vfio_pci_region *region,
-				  struct vfio_info_cap *caps);
-};
-
-struct vfio_pci_region {
-	u32				type;
-	u32				subtype;
-	const struct vfio_pci_regops	*ops;
-	void				*data;
-	size_t				size;
-	u32				flags;
-};
-
-struct vfio_pci_dummy_resource {
-	struct resource		resource;
-	int			index;
-	struct list_head	res_next;
-};
-
-struct vfio_pci_vf_token {
-	struct mutex		lock;
-	uuid_t			uuid;
-	int			users;
-};
-
-struct vfio_pci_mmap_vma {
-	struct vm_area_struct	*vma;
-	struct list_head	vma_next;
-};
-
-struct vfio_pci_device {
-	struct vfio_device	vdev;
-	struct pci_dev		*pdev;
-	void __iomem		*barmap[PCI_STD_NUM_BARS];
-	bool			bar_mmap_supported[PCI_STD_NUM_BARS];
-	u8			*pci_config_map;
-	u8			*vconfig;
-	struct perm_bits	*msi_perm;
-	spinlock_t		irqlock;
-	struct mutex		igate;
-	struct vfio_pci_irq_ctx	*ctx;
-	int			num_ctx;
-	int			irq_type;
-	int			num_regions;
-	struct vfio_pci_region	*region;
-	u8			msi_qmax;
-	u8			msix_bar;
-	u16			msix_size;
-	u32			msix_offset;
-	u32			rbar[7];
-	bool			pci_2_3;
-	bool			virq_disabled;
-	bool			reset_works;
-	bool			extended_caps;
-	bool			bardirty;
-	bool			has_vga;
-	bool			needs_reset;
-	bool			nointx;
-	bool			needs_pm_restore;
-	struct pci_saved_state	*pci_saved_state;
-	struct pci_saved_state	*pm_save;
-	int			ioeventfds_nr;
-	struct eventfd_ctx	*err_trigger;
-	struct eventfd_ctx	*req_trigger;
-	struct list_head	dummy_resources_list;
-	struct mutex		ioeventfds_lock;
-	struct list_head	ioeventfds_list;
-	struct vfio_pci_vf_token	*vf_token;
-	struct notifier_block	nb;
-	struct mutex		vma_lock;
-	struct list_head	vma_list;
-	struct rw_semaphore	memory_lock;
-};
-
-#define is_intx(vdev) (vdev->irq_type == VFIO_PCI_INTX_IRQ_INDEX)
-#define is_msi(vdev) (vdev->irq_type == VFIO_PCI_MSI_IRQ_INDEX)
-#define is_msix(vdev) (vdev->irq_type == VFIO_PCI_MSIX_IRQ_INDEX)
-#define is_irq_none(vdev) (!(is_intx(vdev) || is_msi(vdev) || is_msix(vdev)))
-#define irq_is(vdev, type) (vdev->irq_type == type)
-
-extern void vfio_pci_intx_mask(struct vfio_pci_device *vdev);
-extern void vfio_pci_intx_unmask(struct vfio_pci_device *vdev);
-
-extern int vfio_pci_set_irqs_ioctl(struct vfio_pci_device *vdev,
-				   uint32_t flags, unsigned index,
-				   unsigned start, unsigned count, void *data);
-
-extern ssize_t vfio_pci_config_rw(struct vfio_pci_device *vdev,
-				  char __user *buf, size_t count,
-				  loff_t *ppos, bool iswrite);
-
-extern ssize_t vfio_pci_bar_rw(struct vfio_pci_device *vdev, char __user *buf,
-			       size_t count, loff_t *ppos, bool iswrite);
-
-extern ssize_t vfio_pci_vga_rw(struct vfio_pci_device *vdev, char __user *buf,
-			       size_t count, loff_t *ppos, bool iswrite);
-
-extern long vfio_pci_ioeventfd(struct vfio_pci_device *vdev, loff_t offset,
-			       uint64_t data, int count, int fd);
-
-extern int vfio_pci_init_perm_bits(void);
-extern void vfio_pci_uninit_perm_bits(void);
-
-extern int vfio_config_init(struct vfio_pci_device *vdev);
-extern void vfio_config_free(struct vfio_pci_device *vdev);
-
-extern int vfio_pci_register_dev_region(struct vfio_pci_device *vdev,
-					unsigned int type, unsigned int subtype,
-					const struct vfio_pci_regops *ops,
-					size_t size, u32 flags, void *data);
-
-extern int vfio_pci_set_power_state(struct vfio_pci_device *vdev,
-				    pci_power_t state);
-
-extern bool __vfio_pci_memory_enabled(struct vfio_pci_device *vdev);
-extern void vfio_pci_zap_and_down_write_memory_lock(struct vfio_pci_device
-						    *vdev);
-extern u16 vfio_pci_memory_lock_and_enable(struct vfio_pci_device *vdev);
-extern void vfio_pci_memory_unlock_and_restore(struct vfio_pci_device *vdev,
-					       u16 cmd);
-
-#ifdef CONFIG_VFIO_PCI_IGD
-extern int vfio_pci_igd_init(struct vfio_pci_device *vdev);
-#else
-static inline int vfio_pci_igd_init(struct vfio_pci_device *vdev)
-{
-	return -ENODEV;
-}
-#endif
-
-#ifdef CONFIG_S390
-extern int vfio_pci_info_zdev_add_caps(struct vfio_pci_device *vdev,
-				       struct vfio_info_cap *caps);
-#else
-static inline int vfio_pci_info_zdev_add_caps(struct vfio_pci_device *vdev,
-					      struct vfio_info_cap *caps)
-{
-	return -ENODEV;
-}
-#endif
-
-#endif /* VFIO_PCI_PRIVATE_H */
diff --git a/drivers/vfio/pci/vfio_pci_rdwr.c b/drivers/vfio/pci/vfio_pci_rdwr.c
index a0b5fc8e46f4..667e82726e75 100644
--- a/drivers/vfio/pci/vfio_pci_rdwr.c
+++ b/drivers/vfio/pci/vfio_pci_rdwr.c
@@ -17,7 +17,7 @@
 #include <linux/vfio.h>
 #include <linux/vgaarb.h>
 
-#include "vfio_pci_private.h"
+#include "vfio_pci_core.h"
 
 #ifdef __LITTLE_ENDIAN
 #define vfio_ioread64	ioread64
diff --git a/drivers/vfio/pci/vfio_pci_zdev.c b/drivers/vfio/pci/vfio_pci_zdev.c
index 7b011b62c766..ecae0c3d95a0 100644
--- a/drivers/vfio/pci/vfio_pci_zdev.c
+++ b/drivers/vfio/pci/vfio_pci_zdev.c
@@ -19,7 +19,7 @@
 #include <asm/pci_clp.h>
 #include <asm/pci_io.h>
 
-#include "vfio_pci_private.h"
+#include "vfio_pci_core.h"
 
 /*
  * Add the Base PCI Function information to the device info region.

