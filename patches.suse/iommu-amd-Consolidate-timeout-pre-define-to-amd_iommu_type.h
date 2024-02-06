From: Suravee Suthikulpanit <suravee.suthikulpanit@amd.com>
Date: Thu, 21 Sep 2023 09:21:35 +0000
Subject: iommu/amd: Consolidate timeout pre-define to amd_iommu_type.h
Git-commit: 75e6d7edfdcc540fc59d7bb289bd8b68ca11aa1c
Patch-mainline: v6.7-rc1
References: jsc#PED-7779 jsc#PED-7780

To allow inclusion in other files in subsequent patches.

Signed-off-by: Suravee Suthikulpanit <suravee.suthikulpanit@amd.com>
Signed-off-by: Vasant Hegde <vasant.hegde@amd.com>
Reviewed-by: Jason Gunthorpe <jgg@nvidia.com>
Reviewed-by: Jerry Snitselaar <jsnitsel@redhat.com>
Link: https://lore.kernel.org/r/20230921092147.5930-3-vasant.hegde@amd.com
Signed-off-by: Joerg Roedel <jroedel@suse.de>
---
 drivers/iommu/amd/amd_iommu_types.h |  4 ++++
 drivers/iommu/amd/init.c            | 10 ++++------
 drivers/iommu/amd/iommu.c           |  2 --
 3 files changed, 8 insertions(+), 8 deletions(-)

diff --git a/drivers/iommu/amd/amd_iommu_types.h b/drivers/iommu/amd/amd_iommu_types.h
index 081d8d0f29d5..a8d264026f7f 100644
--- a/drivers/iommu/amd/amd_iommu_types.h
+++ b/drivers/iommu/amd/amd_iommu_types.h
@@ -451,6 +451,10 @@
 #define PD_IOMMUV2_MASK		BIT(3) /* domain has gcr3 table */
 #define PD_GIOV_MASK		BIT(4) /* domain enable GIOV support */
 
+/* Timeout stuff */
+#define LOOP_TIMEOUT		100000
+#define MMIO_STATUS_TIMEOUT	2000000
+
 extern bool amd_iommu_dump;
 #define DUMP_printk(format, arg...)				\
 	do {							\
diff --git a/drivers/iommu/amd/init.c b/drivers/iommu/amd/init.c
index 45efb7e5d725..852e40b13d20 100644
--- a/drivers/iommu/amd/init.c
+++ b/drivers/iommu/amd/init.c
@@ -83,8 +83,6 @@
 #define ACPI_DEVFLAG_LINT1              0x80
 #define ACPI_DEVFLAG_ATSDIS             0x10000000
 
-#define LOOP_TIMEOUT	2000000
-
 #define IVRS_GET_SBDF_ID(seg, bus, dev, fn)	(((seg & 0xffff) << 16) | ((bus & 0xff) << 8) \
 						 | ((dev & 0x1f) << 3) | (fn & 0x7))
 
@@ -985,14 +983,14 @@ static int iommu_ga_log_enable(struct amd_iommu *iommu)
 	iommu_feature_enable(iommu, CONTROL_GAINT_EN);
 	iommu_feature_enable(iommu, CONTROL_GALOG_EN);
 
-	for (i = 0; i < LOOP_TIMEOUT; ++i) {
+	for (i = 0; i < MMIO_STATUS_TIMEOUT; ++i) {
 		status = readl(iommu->mmio_base + MMIO_STATUS_OFFSET);
 		if (status & (MMIO_STATUS_GALOG_RUN_MASK))
 			break;
 		udelay(10);
 	}
 
-	if (WARN_ON(i >= LOOP_TIMEOUT))
+	if (WARN_ON(i >= MMIO_STATUS_TIMEOUT))
 		return -EINVAL;
 
 	return 0;
@@ -2900,14 +2898,14 @@ static void enable_iommus_vapic(void)
 		 * Need to set and poll check the GALOGRun bit to zero before
 		 * we can set/ modify GA Log registers safely.
 		 */
-		for (i = 0; i < LOOP_TIMEOUT; ++i) {
+		for (i = 0; i < MMIO_STATUS_TIMEOUT; ++i) {
 			status = readl(iommu->mmio_base + MMIO_STATUS_OFFSET);
 			if (!(status & MMIO_STATUS_GALOG_RUN_MASK))
 				break;
 			udelay(10);
 		}
 
-		if (WARN_ON(i >= LOOP_TIMEOUT))
+		if (WARN_ON(i >= MMIO_STATUS_TIMEOUT))
 			return;
 	}
 
diff --git a/drivers/iommu/amd/iommu.c b/drivers/iommu/amd/iommu.c
index 95bd7c25ba6f..6fa6a0527d7b 100644
--- a/drivers/iommu/amd/iommu.c
+++ b/drivers/iommu/amd/iommu.c
@@ -44,8 +44,6 @@
 
 #define CMD_SET_TYPE(cmd, t) ((cmd)->data[1] |= ((t) << 28))
 
-#define LOOP_TIMEOUT	100000
-
 /* IO virtual address start page frame number */
 #define IOVA_START_PFN		(1)
 #define IOVA_PFN(addr)		((addr) >> PAGE_SHIFT)

