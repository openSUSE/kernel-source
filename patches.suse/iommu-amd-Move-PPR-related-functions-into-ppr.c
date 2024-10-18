From: Suravee Suthikulpanit <suravee.suthikulpanit@amd.com>
Date: Thu, 18 Apr 2024 10:33:49 +0000
Subject: iommu/amd: Move PPR-related functions into ppr.c
Git-commit: e08fcd901c4301c150a8212df28df7f4d4811988
Patch-mainline: v6.10-rc1
References: jsc#PED-10968

In preparation to subsequent PPR-related patches, and also remove static
declaration for certain helper functions so that it can be reused in other
files.

Also rename below functions:
  alloc_ppr_log        -> amd_iommu_alloc_ppr_log
  iommu_enable_ppr_log -> amd_iommu_enable_ppr_log
  free_ppr_log         -> amd_iommu_free_ppr_log
  iommu_poll_ppr_log   -> amd_iommu_poll_ppr_log

Signed-off-by: Suravee Suthikulpanit <suravee.suthikulpanit@amd.com>
Co-developed-by: Vasant Hegde <vasant.hegde@amd.com>
Signed-off-by: Vasant Hegde <vasant.hegde@amd.com>
Reviewed-by: Jason Gunthorpe <jgg@nvidia.com>
Link: https://lore.kernel.org/r/20240418103400.6229-5-vasant.hegde@amd.com
Signed-off-by: Joerg Roedel <jroedel@suse.de>
---
 drivers/iommu/amd/Makefile    |   2 +-
 drivers/iommu/amd/amd_iommu.h |  17 +++++--
 drivers/iommu/amd/init.c      |  65 ++++--------------------
 drivers/iommu/amd/iommu.c     |  55 +-------------------
 drivers/iommu/amd/ppr.c       | 114 ++++++++++++++++++++++++++++++++++++++++++
 5 files changed, 139 insertions(+), 114 deletions(-)

diff --git a/drivers/iommu/amd/Makefile b/drivers/iommu/amd/Makefile
index f454fbb1569e..93b11b6d764f 100644
--- a/drivers/iommu/amd/Makefile
+++ b/drivers/iommu/amd/Makefile
@@ -1,3 +1,3 @@
 # SPDX-License-Identifier: GPL-2.0-only
-obj-$(CONFIG_AMD_IOMMU) += iommu.o init.o quirks.o io_pgtable.o io_pgtable_v2.o
+obj-$(CONFIG_AMD_IOMMU) += iommu.o init.o quirks.o io_pgtable.o io_pgtable_v2.o ppr.o
 obj-$(CONFIG_AMD_IOMMU_DEBUGFS) += debugfs.o
diff --git a/drivers/iommu/amd/amd_iommu.h b/drivers/iommu/amd/amd_iommu.h
index 98aa3ce8473f..159e9a43aa61 100644
--- a/drivers/iommu/amd/amd_iommu.h
+++ b/drivers/iommu/amd/amd_iommu.h
@@ -17,10 +17,16 @@ irqreturn_t amd_iommu_int_thread_pprlog(int irq, void *data);
 irqreturn_t amd_iommu_int_thread_galog(int irq, void *data);
 irqreturn_t amd_iommu_int_handler(int irq, void *data);
 void amd_iommu_apply_erratum_63(struct amd_iommu *iommu, u16 devid);
+void amd_iommu_restart_log(struct amd_iommu *iommu, const char *evt_type,
+			   u8 cntrl_intr, u8 cntrl_log,
+			   u32 status_run_mask, u32 status_overflow_mask);
 void amd_iommu_restart_event_logging(struct amd_iommu *iommu);
 void amd_iommu_restart_ga_log(struct amd_iommu *iommu);
 void amd_iommu_restart_ppr_log(struct amd_iommu *iommu);
 void amd_iommu_set_rlookup_table(struct amd_iommu *iommu, u16 devid);
+void iommu_feature_enable(struct amd_iommu *iommu, u8 bit);
+void *__init iommu_alloc_4k_pages(struct amd_iommu *iommu,
+				  gfp_t gfp, size_t size);
 
 #ifdef CONFIG_AMD_IOMMU_DEBUGFS
 void amd_iommu_debugfs_setup(struct amd_iommu *iommu);
@@ -49,6 +55,14 @@ int amd_iommu_set_gcr3(struct iommu_dev_data *dev_data,
 		       ioasid_t pasid, unsigned long gcr3);
 int amd_iommu_clear_gcr3(struct iommu_dev_data *dev_data, ioasid_t pasid);
 
+/* PPR */
+int __init amd_iommu_alloc_ppr_log(struct amd_iommu *iommu);
+void __init amd_iommu_free_ppr_log(struct amd_iommu *iommu);
+void amd_iommu_enable_ppr_log(struct amd_iommu *iommu);
+void amd_iommu_poll_ppr_log(struct amd_iommu *iommu);
+int amd_iommu_complete_ppr(struct pci_dev *pdev, u32 pasid,
+			   int status, int tag);
+
 /*
  * This function flushes all internal caches of
  * the IOMMU used by this driver.
@@ -74,9 +88,6 @@ static inline int amd_iommu_create_irq_domain(struct amd_iommu *iommu)
 }
 #endif
 
-int amd_iommu_complete_ppr(struct pci_dev *pdev, u32 pasid,
-			   int status, int tag);
-
 static inline bool is_rd890_iommu(struct pci_dev *pdev)
 {
 	return (pdev->vendor == PCI_VENDOR_ID_ATI) &&
diff --git a/drivers/iommu/amd/init.c b/drivers/iommu/amd/init.c
index 5687c19825d7..269446717818 100644
--- a/drivers/iommu/amd/init.c
+++ b/drivers/iommu/amd/init.c
@@ -419,7 +419,7 @@ static void iommu_set_device_table(struct amd_iommu *iommu)
 }
 
 /* Generic functions to enable/disable certain features of the IOMMU. */
-static void iommu_feature_enable(struct amd_iommu *iommu, u8 bit)
+void iommu_feature_enable(struct amd_iommu *iommu, u8 bit)
 {
 	u64 ctrl;
 
@@ -746,9 +746,9 @@ static int __init alloc_command_buffer(struct amd_iommu *iommu)
  * Interrupt handler has processed all pending events and adjusted head
  * and tail pointer. Reset overflow mask and restart logging again.
  */
-static void amd_iommu_restart_log(struct amd_iommu *iommu, const char *evt_type,
-				  u8 cntrl_intr, u8 cntrl_log,
-				  u32 status_run_mask, u32 status_overflow_mask)
+void amd_iommu_restart_log(struct amd_iommu *iommu, const char *evt_type,
+			   u8 cntrl_intr, u8 cntrl_log,
+			   u32 status_run_mask, u32 status_overflow_mask)
 {
 	u32 status;
 
@@ -789,17 +789,6 @@ void amd_iommu_restart_ga_log(struct amd_iommu *iommu)
 			      MMIO_STATUS_GALOG_OVERFLOW_MASK);
 }
 
-/*
- * This function restarts ppr logging in case the IOMMU experienced
- * PPR log overflow.
- */
-void amd_iommu_restart_ppr_log(struct amd_iommu *iommu)
-{
-	amd_iommu_restart_log(iommu, "PPR", CONTROL_PPRINT_EN,
-			      CONTROL_PPRLOG_EN, MMIO_STATUS_PPR_RUN_MASK,
-			      MMIO_STATUS_PPR_OVERFLOW_MASK);
-}
-
 /*
  * This function resets the command buffer if the IOMMU stopped fetching
  * commands from it.
@@ -848,8 +837,8 @@ static void __init free_command_buffer(struct amd_iommu *iommu)
 	free_pages((unsigned long)iommu->cmd_buf, get_order(CMD_BUFFER_SIZE));
 }
 
-static void *__init iommu_alloc_4k_pages(struct amd_iommu *iommu,
-					 gfp_t gfp, size_t size)
+void *__init iommu_alloc_4k_pages(struct amd_iommu *iommu, gfp_t gfp,
+				  size_t size)
 {
 	int order = get_order(size);
 	void *buf = (void *)__get_free_pages(gfp, order);
@@ -904,42 +893,6 @@ static void __init free_event_buffer(struct amd_iommu *iommu)
 	free_pages((unsigned long)iommu->evt_buf, get_order(EVT_BUFFER_SIZE));
 }
 
-/* allocates the memory where the IOMMU will log its events to */
-static int __init alloc_ppr_log(struct amd_iommu *iommu)
-{
-	iommu->ppr_log = iommu_alloc_4k_pages(iommu, GFP_KERNEL | __GFP_ZERO,
-					      PPR_LOG_SIZE);
-
-	return iommu->ppr_log ? 0 : -ENOMEM;
-}
-
-static void iommu_enable_ppr_log(struct amd_iommu *iommu)
-{
-	u64 entry;
-
-	if (iommu->ppr_log == NULL)
-		return;
-
-	iommu_feature_enable(iommu, CONTROL_PPR_EN);
-
-	entry = iommu_virt_to_phys(iommu->ppr_log) | PPR_LOG_SIZE_512;
-
-	memcpy_toio(iommu->mmio_base + MMIO_PPR_LOG_OFFSET,
-		    &entry, sizeof(entry));
-
-	/* set head and tail to zero manually */
-	writel(0x00, iommu->mmio_base + MMIO_PPR_HEAD_OFFSET);
-	writel(0x00, iommu->mmio_base + MMIO_PPR_TAIL_OFFSET);
-
-	iommu_feature_enable(iommu, CONTROL_PPRLOG_EN);
-	iommu_feature_enable(iommu, CONTROL_PPRINT_EN);
-}
-
-static void __init free_ppr_log(struct amd_iommu *iommu)
-{
-	free_pages((unsigned long)iommu->ppr_log, get_order(PPR_LOG_SIZE));
-}
-
 static void free_ga_log(struct amd_iommu *iommu)
 {
 #ifdef CONFIG_IRQ_REMAP
@@ -1683,7 +1636,7 @@ static void __init free_iommu_one(struct amd_iommu *iommu)
 	free_cwwb_sem(iommu);
 	free_command_buffer(iommu);
 	free_event_buffer(iommu);
-	free_ppr_log(iommu);
+	amd_iommu_free_ppr_log(iommu);
 	free_ga_log(iommu);
 	iommu_unmap_mmio_space(iommu);
 }
@@ -2099,7 +2052,7 @@ static int __init iommu_init_pci(struct amd_iommu *iommu)
 			amd_iommu_max_glx_val = min(amd_iommu_max_glx_val, glxval);
 	}
 
-	if (check_feature(FEATURE_PPR) && alloc_ppr_log(iommu))
+	if (check_feature(FEATURE_PPR) && amd_iommu_alloc_ppr_log(iommu))
 		return -ENOMEM;
 
 	if (iommu->cap & (1UL << IOMMU_CAP_NPCACHE)) {
@@ -2845,7 +2798,7 @@ static void enable_iommus_v2(void)
 	struct amd_iommu *iommu;
 
 	for_each_iommu(iommu)
-		iommu_enable_ppr_log(iommu);
+		amd_iommu_enable_ppr_log(iommu);
 }
 
 static void enable_iommus_vapic(void)
diff --git a/drivers/iommu/amd/iommu.c b/drivers/iommu/amd/iommu.c
index a22ecd8479db..0decab958106 100644
--- a/drivers/iommu/amd/iommu.c
+++ b/drivers/iommu/amd/iommu.c
@@ -818,59 +818,6 @@ static void iommu_poll_events(struct amd_iommu *iommu)
 	writel(head, iommu->mmio_base + MMIO_EVT_HEAD_OFFSET);
 }
 
-static void iommu_poll_ppr_log(struct amd_iommu *iommu)
-{
-	u32 head, tail;
-
-	if (iommu->ppr_log == NULL)
-		return;
-
-	head = readl(iommu->mmio_base + MMIO_PPR_HEAD_OFFSET);
-	tail = readl(iommu->mmio_base + MMIO_PPR_TAIL_OFFSET);
-
-	while (head != tail) {
-		volatile u64 *raw;
-		u64 entry[2];
-		int i;
-
-		raw = (u64 *)(iommu->ppr_log + head);
-
-		/*
-		 * Hardware bug: Interrupt may arrive before the entry is
-		 * written to memory. If this happens we need to wait for the
-		 * entry to arrive.
-		 */
-		for (i = 0; i < LOOP_TIMEOUT; ++i) {
-			if (PPR_REQ_TYPE(raw[0]) != 0)
-				break;
-			udelay(1);
-		}
-
-		/* Avoid memcpy function-call overhead */
-		entry[0] = raw[0];
-		entry[1] = raw[1];
-
-		/*
-		 * To detect the hardware errata 733 we need to clear the
-		 * entry back to zero. This issue does not exist on SNP
-		 * enabled system. Also this buffer is not writeable on
-		 * SNP enabled system.
-		 */
-		if (!amd_iommu_snp_en)
-			raw[0] = raw[1] = 0UL;
-
-		/* Update head pointer of hardware ring-buffer */
-		head = (head + PPR_ENTRY_SIZE) % PPR_LOG_SIZE;
-		writel(head, iommu->mmio_base + MMIO_PPR_HEAD_OFFSET);
-
-		/* TODO: PPR Handler will be added when we add IOPF support */
-
-		/* Refresh ring-buffer information */
-		head = readl(iommu->mmio_base + MMIO_PPR_HEAD_OFFSET);
-		tail = readl(iommu->mmio_base + MMIO_PPR_TAIL_OFFSET);
-	}
-}
-
 #ifdef CONFIG_IRQ_REMAP
 static int (*iommu_ga_log_notifier)(u32);
 
@@ -991,7 +938,7 @@ irqreturn_t amd_iommu_int_thread_pprlog(int irq, void *data)
 {
 	amd_iommu_handle_irq(data, "PPR", MMIO_STATUS_PPR_INT_MASK,
 			     MMIO_STATUS_PPR_OVERFLOW_MASK,
-			     iommu_poll_ppr_log, amd_iommu_restart_ppr_log);
+			     amd_iommu_poll_ppr_log, amd_iommu_restart_ppr_log);
 
 	return IRQ_HANDLED;
 }
diff --git a/drivers/iommu/amd/ppr.c b/drivers/iommu/amd/ppr.c
new file mode 100644
index 000000000000..1f76ed549ec1
--- /dev/null
+++ b/drivers/iommu/amd/ppr.c
@@ -0,0 +1,114 @@
+// SPDX-License-Identifier: GPL-2.0-only
+/*
+ * Copyright (C) 2023 Advanced Micro Devices, Inc.
+ */
+
+#define pr_fmt(fmt)     "AMD-Vi: " fmt
+#define dev_fmt(fmt)    pr_fmt(fmt)
+
+#include <linux/amd-iommu.h>
+#include <linux/delay.h>
+#include <linux/mmu_notifier.h>
+
+#include <asm/iommu.h>
+
+#include "amd_iommu.h"
+#include "amd_iommu_types.h"
+
+int __init amd_iommu_alloc_ppr_log(struct amd_iommu *iommu)
+{
+	iommu->ppr_log = iommu_alloc_4k_pages(iommu, GFP_KERNEL | __GFP_ZERO,
+					      PPR_LOG_SIZE);
+	return iommu->ppr_log ? 0 : -ENOMEM;
+}
+
+void amd_iommu_enable_ppr_log(struct amd_iommu *iommu)
+{
+	u64 entry;
+
+	if (iommu->ppr_log == NULL)
+		return;
+
+	iommu_feature_enable(iommu, CONTROL_PPR_EN);
+
+	entry = iommu_virt_to_phys(iommu->ppr_log) | PPR_LOG_SIZE_512;
+
+	memcpy_toio(iommu->mmio_base + MMIO_PPR_LOG_OFFSET,
+		    &entry, sizeof(entry));
+
+	/* set head and tail to zero manually */
+	writel(0x00, iommu->mmio_base + MMIO_PPR_HEAD_OFFSET);
+	writel(0x00, iommu->mmio_base + MMIO_PPR_TAIL_OFFSET);
+
+	iommu_feature_enable(iommu, CONTROL_PPRINT_EN);
+	iommu_feature_enable(iommu, CONTROL_PPRLOG_EN);
+}
+
+void __init amd_iommu_free_ppr_log(struct amd_iommu *iommu)
+{
+	free_pages((unsigned long)iommu->ppr_log, get_order(PPR_LOG_SIZE));
+}
+
+/*
+ * This function restarts ppr logging in case the IOMMU experienced
+ * PPR log overflow.
+ */
+void amd_iommu_restart_ppr_log(struct amd_iommu *iommu)
+{
+	amd_iommu_restart_log(iommu, "PPR", CONTROL_PPRINT_EN,
+			      CONTROL_PPRLOG_EN, MMIO_STATUS_PPR_RUN_MASK,
+			      MMIO_STATUS_PPR_OVERFLOW_MASK);
+}
+
+void amd_iommu_poll_ppr_log(struct amd_iommu *iommu)
+{
+	u32 head, tail;
+
+	if (iommu->ppr_log == NULL)
+		return;
+
+	head = readl(iommu->mmio_base + MMIO_PPR_HEAD_OFFSET);
+	tail = readl(iommu->mmio_base + MMIO_PPR_TAIL_OFFSET);
+
+	while (head != tail) {
+		volatile u64 *raw;
+		u64 entry[2];
+		int i;
+
+		raw = (u64 *)(iommu->ppr_log + head);
+
+		/*
+		 * Hardware bug: Interrupt may arrive before the entry is
+		 * written to memory. If this happens we need to wait for the
+		 * entry to arrive.
+		 */
+		for (i = 0; i < LOOP_TIMEOUT; ++i) {
+			if (PPR_REQ_TYPE(raw[0]) != 0)
+				break;
+			udelay(1);
+		}
+
+		/* Avoid memcpy function-call overhead */
+		entry[0] = raw[0];
+		entry[1] = raw[1];
+
+		/*
+		 * To detect the hardware errata 733 we need to clear the
+		 * entry back to zero. This issue does not exist on SNP
+		 * enabled system. Also this buffer is not writeable on
+		 * SNP enabled system.
+		 */
+		if (!amd_iommu_snp_en)
+			raw[0] = raw[1] = 0UL;
+
+		/* Update head pointer of hardware ring-buffer */
+		head = (head + PPR_ENTRY_SIZE) % PPR_LOG_SIZE;
+		writel(head, iommu->mmio_base + MMIO_PPR_HEAD_OFFSET);
+
+		/* TODO: PPR Handler will be added when we add IOPF support */
+
+		/* Refresh ring-buffer information */
+		head = readl(iommu->mmio_base + MMIO_PPR_HEAD_OFFSET);
+		tail = readl(iommu->mmio_base + MMIO_PPR_TAIL_OFFSET);
+	}
+}

