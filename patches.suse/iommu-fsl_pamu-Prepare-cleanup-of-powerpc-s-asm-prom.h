From: Christophe Leroy <christophe.leroy@csgroup.eu>
Date: Sat, 2 Apr 2022 12:08:38 +0200
Subject: iommu/fsl_pamu: Prepare cleanup of powerpc's asm/prom.h
Git-commit: cae8d1f5e34e5b2604a52d705218a6b2d288365f
Patch-mainline: v5.19-rc1
References: bsc#1205701

powerpc's asm/prom.h brings some headers that it doesn't
need itself.

In order to clean it up, first add missing headers in
users of asm/prom.h

Signed-off-by: Christophe Leroy <christophe.leroy@csgroup.eu>
Link: https://lore.kernel.org/r/06862cca930068e8fa4fdd0b20d74872d3b929d6.1648833431.git.christophe.leroy@csgroup.eu
Signed-off-by: Joerg Roedel <jroedel@suse.de>
---
 drivers/iommu/fsl_pamu.c        | 3 +++
 drivers/iommu/fsl_pamu_domain.c | 1 +
 2 files changed, 4 insertions(+)

diff --git a/drivers/iommu/fsl_pamu.c b/drivers/iommu/fsl_pamu.c
index fc38b1fba7cf..0d03f837a5d4 100644
--- a/drivers/iommu/fsl_pamu.c
+++ b/drivers/iommu/fsl_pamu.c
@@ -11,6 +11,9 @@
 #include <linux/fsl/guts.h>
 #include <linux/interrupt.h>
 #include <linux/genalloc.h>
+#include <linux/of_address.h>
+#include <linux/of_irq.h>
+#include <linux/platform_device.h>
 
 #include <asm/mpc85xx.h>
 
diff --git a/drivers/iommu/fsl_pamu_domain.c b/drivers/iommu/fsl_pamu_domain.c
index 69a4a62dc3b9..94b4589dc67c 100644
--- a/drivers/iommu/fsl_pamu_domain.c
+++ b/drivers/iommu/fsl_pamu_domain.c
@@ -9,6 +9,7 @@
 
 #include "fsl_pamu_domain.h"
 
+#include <linux/platform_device.h>
 #include <sysdev/fsl_pci.h>
 
 /*

