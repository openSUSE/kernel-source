From: Max Gurtovoy <mgurtovoy@nvidia.com>
Date: Thu, 26 Aug 2021 13:39:04 +0300
Subject: vfio/pci: Include vfio header in vfio_pci_core.h
Git-commit: c39f8fa76cdd0c96f82fa785a0d6c92afe8f4a77
Patch-mainline: v5.15-rc1
References: bsc#1205701

The vfio_device structure is embedded into the vfio_pci_core_device
structure, so there is no reason for not including the header file in
the vfio_pci_core header as well.

Signed-off-by: Max Gurtovoy <mgurtovoy@nvidia.com>
Reviewed-by: Christoph Hellwig <hch@lst.de>
Signed-off-by: Yishai Hadas <yishaih@nvidia.com>
Link: https://lore.kernel.org/r/20210826103912.128972-6-yishaih@nvidia.com
Signed-off-by: Alex Williamson <alex.williamson@redhat.com>
Acked-by: Joerg Roedel <jroedel@suse.de>
---
 drivers/vfio/pci/vfio_pci_core.c | 1 -
 drivers/vfio/pci/vfio_pci_core.h | 1 +
 2 files changed, 1 insertion(+), 1 deletion(-)

diff --git a/drivers/vfio/pci/vfio_pci_core.c b/drivers/vfio/pci/vfio_pci_core.c
index ee5c8fe2a324..94f062818e0c 100644
--- a/drivers/vfio/pci/vfio_pci_core.c
+++ b/drivers/vfio/pci/vfio_pci_core.c
@@ -23,7 +23,6 @@
 #include <linux/slab.h>
 #include <linux/types.h>
 #include <linux/uaccess.h>
-#include <linux/vfio.h>
 #include <linux/vgaarb.h>
 #include <linux/nospec.h>
 #include <linux/sched/mm.h>
diff --git a/drivers/vfio/pci/vfio_pci_core.h b/drivers/vfio/pci/vfio_pci_core.h
index 2ceaa6e4ca25..17ad048752b6 100644
--- a/drivers/vfio/pci/vfio_pci_core.h
+++ b/drivers/vfio/pci/vfio_pci_core.h
@@ -10,6 +10,7 @@
 
 #include <linux/mutex.h>
 #include <linux/pci.h>
+#include <linux/vfio.h>
 #include <linux/irqbypass.h>
 #include <linux/types.h>
 #include <linux/uuid.h>

