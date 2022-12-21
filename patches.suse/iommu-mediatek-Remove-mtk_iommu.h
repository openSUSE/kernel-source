From: Yong Wu <yong.wu@mediatek.com>
Date: Tue, 3 May 2022 15:14:18 +0800
Subject: iommu/mediatek: Remove mtk_iommu.h
Git-commit: 6a513de3efe099976fc5924082e48b79c467664f
Patch-mainline: v5.19-rc1
References: bsc#1205701

Currently there is a suspend structure in the header file. It's no need
to keep a header file only for this. Move these into the c file and rm
this header file.

Signed-off-by: Yong Wu <yong.wu@mediatek.com>
Reviewed-by: AngeloGioacchino Del Regno <angelogioacchino.delregno@collabora.com>
Reviewed-by: Matthias Brugger <matthias.bgg@gmail.com>
Link: https://lore.kernel.org/r/20220503071427.2285-28-yong.wu@mediatek.com
Signed-off-by: Joerg Roedel <jroedel@suse.de>
---
 drivers/iommu/mtk_iommu.c    | 14 +++++++++++++-
 drivers/iommu/mtk_iommu.h    | 32 --------------------------------
 drivers/iommu/mtk_iommu_v1.c | 11 ++++++++---
 3 files changed, 21 insertions(+), 36 deletions(-)

diff --git a/drivers/iommu/mtk_iommu.c b/drivers/iommu/mtk_iommu.c
index 7383a5df6021..349640bcbd01 100644
--- a/drivers/iommu/mtk_iommu.c
+++ b/drivers/iommu/mtk_iommu.c
@@ -14,6 +14,7 @@
 #include <linux/io.h>
 #include <linux/iommu.h>
 #include <linux/iopoll.h>
+#include <linux/io-pgtable.h>
 #include <linux/list.h>
 #include <linux/mfd/syscon.h>
 #include <linux/module.h>
@@ -30,7 +31,7 @@
 #include <asm/barrier.h>
 #include <soc/mediatek/smi.h>
 
-#include "mtk_iommu.h"
+#include <dt-bindings/memory/mtk-memory-port.h>
 
 #define REG_MMU_PT_BASE_ADDR			0x000
 #define MMU_PT_ADDR_MASK			GENMASK(31, 7)
@@ -166,6 +167,17 @@ struct mtk_iommu_iova_region {
 	unsigned long long	size;
 };
 
+struct mtk_iommu_suspend_reg {
+	u32			misc_ctrl;
+	u32			dcm_dis;
+	u32			ctrl_reg;
+	u32			int_control0;
+	u32			int_main_control;
+	u32			ivrp_paddr;
+	u32			vld_pa_rng;
+	u32			wr_len_ctrl;
+};
+
 struct mtk_iommu_plat_data {
 	enum mtk_iommu_plat	m4u_plat;
 	u32			flags;
diff --git a/drivers/iommu/mtk_iommu.h b/drivers/iommu/mtk_iommu.h
deleted file mode 100644
index 305243e18aa9..000000000000
--- a/drivers/iommu/mtk_iommu.h
+++ /dev/null
@@ -1,32 +0,0 @@
-/* SPDX-License-Identifier: GPL-2.0-only */
-/*
- * Copyright (c) 2015-2016 MediaTek Inc.
- * Author: Honghui Zhang <honghui.zhang@mediatek.com>
- */
-
-#ifndef _MTK_IOMMU_H_
-#define _MTK_IOMMU_H_
-
-#include <linux/device.h>
-#include <linux/io.h>
-#include <linux/io-pgtable.h>
-#include <linux/iommu.h>
-#include <linux/spinlock.h>
-#include <soc/mediatek/smi.h>
-#include <dt-bindings/memory/mtk-memory-port.h>
-
-struct mtk_iommu_suspend_reg {
-	union {
-		u32			standard_axi_mode;/* v1 */
-		u32			misc_ctrl;/* v2 */
-	};
-	u32				dcm_dis;
-	u32				ctrl_reg;
-	u32				int_control0;
-	u32				int_main_control;
-	u32				ivrp_paddr;
-	u32				vld_pa_rng;
-	u32				wr_len_ctrl;
-};
-
-#endif
diff --git a/drivers/iommu/mtk_iommu_v1.c b/drivers/iommu/mtk_iommu_v1.c
index 6d1c09c91e1f..3d1f0897d1cc 100644
--- a/drivers/iommu/mtk_iommu_v1.c
+++ b/drivers/iommu/mtk_iommu_v1.c
@@ -7,7 +7,6 @@
  *
  * Based on driver/iommu/mtk_iommu.c
  */
-#include <linux/memblock.h>
 #include <linux/bug.h>
 #include <linux/clk.h>
 #include <linux/component.h>
@@ -28,10 +27,9 @@
 #include <linux/spinlock.h>
 #include <asm/barrier.h>
 #include <asm/dma-iommu.h>
-#include <linux/init.h>
+#include <dt-bindings/memory/mtk-memory-port.h>
 #include <dt-bindings/memory/mt2701-larb-port.h>
 #include <soc/mediatek/smi.h>
-#include "mtk_iommu.h"
 
 #define REG_MMU_PT_BASE_ADDR			0x000
 
@@ -87,6 +85,13 @@
  */
 #define M2701_IOMMU_PGT_SIZE			SZ_4M
 
+struct mtk_iommu_suspend_reg {
+	u32			standard_axi_mode;
+	u32			dcm_dis;
+	u32			ctrl_reg;
+	u32			int_control0;
+};
+
 struct mtk_iommu_data {
 	void __iomem			*base;
 	int				irq;

