From: Christoph Hellwig <hch@lst.de>
Date: Thu, 17 Feb 2022 15:10:54 +0100
Subject: x86: remove cruft from <asm/dma-mapping.h>
Git-commit: 3cb4503a330159dc5cf2f8382181ccbabbbaa5b2
Patch-mainline: v5.19-rc1
References: jsc#PED-3259

<asm/dma-mapping.h> gets pulled in by all drivers using the DMA API.
Remove x86 internal variables and unnecessary includes from it.

Signed-off-by: Christoph Hellwig <hch@lst.de>
Reviewed-by: Konrad Rzeszutek Wilk <konrad.wilk@oracle.com>
Tested-by: Boris Ostrovsky <boris.ostrovsky@oracle.com>
Acked-by: Joerg Roedel <jroedel@suse.de>
---
 arch/x86/include/asm/dma-mapping.h | 11 -----------
 arch/x86/include/asm/iommu.h       |  2 ++
 2 files changed, 2 insertions(+), 11 deletions(-)

diff --git a/arch/x86/include/asm/dma-mapping.h b/arch/x86/include/asm/dma-mapping.h
index 256fd8115223..1c66708e3062 100644
--- a/arch/x86/include/asm/dma-mapping.h
+++ b/arch/x86/include/asm/dma-mapping.h
@@ -2,17 +2,6 @@
 #ifndef _ASM_X86_DMA_MAPPING_H
 #define _ASM_X86_DMA_MAPPING_H
 
-/*
- * IOMMU interface. See Documentation/core-api/dma-api-howto.rst and
- * Documentation/core-api/dma-api.rst for documentation.
- */
-
-#include <linux/scatterlist.h>
-#include <asm/io.h>
-
-extern int iommu_merge;
-extern int panic_on_overflow;
-
 extern const struct dma_map_ops *dma_ops;
 
 static inline const struct dma_map_ops *get_arch_dma_ops(struct bus_type *bus)
diff --git a/arch/x86/include/asm/iommu.h b/arch/x86/include/asm/iommu.h
index dba89ed40d38..0bef44d30a27 100644
--- a/arch/x86/include/asm/iommu.h
+++ b/arch/x86/include/asm/iommu.h
@@ -8,6 +8,8 @@
 
 extern int force_iommu, no_iommu;
 extern int iommu_detected;
+extern int iommu_merge;
+extern int panic_on_overflow;
 
 #ifdef CONFIG_SWIOTLB
 extern bool x86_swiotlb_enable;

