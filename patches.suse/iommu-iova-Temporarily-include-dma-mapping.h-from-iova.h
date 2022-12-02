From: Joerg Roedel <jroedel@suse.de>
Date: Mon, 20 Dec 2021 13:34:48 +0100
Subject: iommu/iova: Temporarily include dma-mapping.h from iova.h
Git-commit: aade40b62745cf0b4e8a17d43652c5faff354e6b
Patch-mainline: v5.17-rc1
References: bsc#1205701

Some users of iova.h still expect that dma-mapping.h is also included.
Re-add the include until these users are updated to fix compile
failures in the iommu tree.

Acked-by: Robin Murphy <robin.murphy@arm.com>
Link: https://lore.kernel.org/r/20211220123448.19996-1-joro@8bytes.org
Signed-off-by: Joerg Roedel <jroedel@suse.de>
---
 include/linux/iova.h | 1 +
 1 file changed, 1 insertion(+)

diff --git a/include/linux/iova.h b/include/linux/iova.h
index 0abd48c5e622..cea79cb9f26c 100644
--- a/include/linux/iova.h
+++ b/include/linux/iova.h
@@ -12,6 +12,7 @@
 #include <linux/types.h>
 #include <linux/kernel.h>
 #include <linux/rbtree.h>
+#include <linux/dma-mapping.h>
 
 /* iova structure */
 struct iova {

