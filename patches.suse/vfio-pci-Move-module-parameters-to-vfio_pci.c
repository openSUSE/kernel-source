From: Yishai Hadas <yishaih@nvidia.com>
Date: Thu, 26 Aug 2021 13:39:07 +0300
Subject: vfio/pci: Move module parameters to vfio_pci.c
Git-commit: c61302aa48f7c46b5c9d893109488af951be12e4
Patch-mainline: v5.15-rc1
References: bsc#1205701

This is a preparation before splitting vfio_pci.ko to 2 modules.

As module parameters are a kind of uAPI they need to stay on vfio_pci.ko
to avoid a user visible impact.

For now continue to keep the implementation of these options in
vfio_pci_core.c. Arguably they are vfio_pci functionality, but further
splitting of vfio_pci_core.c will be better done in another series

Signed-off-by: Yishai Hadas <yishaih@nvidia.com>
Reviewed-by: Christoph Hellwig <hch@lst.de>
Signed-off-by: Jason Gunthorpe <jgg@nvidia.com>
Link: https://lore.kernel.org/r/20210826103912.128972-9-yishaih@nvidia.com
Signed-off-by: Alex Williamson <alex.williamson@redhat.com>
Acked-by: Joerg Roedel <jroedel@suse.de>
---
 drivers/vfio/pci/vfio_pci.c      | 23 +++++++++++++++++++++++
 drivers/vfio/pci/vfio_pci_core.c | 20 ++++++++------------
 drivers/vfio/pci/vfio_pci_core.h |  2 ++
 3 files changed, 33 insertions(+), 12 deletions(-)

diff --git a/drivers/vfio/pci/vfio_pci.c b/drivers/vfio/pci/vfio_pci.c
index 2729b777a56d..163e560c4495 100644
--- a/drivers/vfio/pci/vfio_pci.c
+++ b/drivers/vfio/pci/vfio_pci.c
@@ -34,6 +34,22 @@ static char ids[1024] __initdata;
 module_param_string(ids, ids, sizeof(ids), 0);
 MODULE_PARM_DESC(ids, "Initial PCI IDs to add to the vfio driver, format is \"vendor:device[:subvendor[:subdevice[:class[:class_mask]]]]\" and multiple comma separated entries can be specified");
 
+static bool nointxmask;
+module_param_named(nointxmask, nointxmask, bool, S_IRUGO | S_IWUSR);
+MODULE_PARM_DESC(nointxmask,
+		  "Disable support for PCI 2.3 style INTx masking.  If this resolves problems for specific devices, report lspci -vvvxxx to linux-pci@vger.kernel.org so the device can be fixed automatically via the broken_intx_masking flag.");
+
+#ifdef CONFIG_VFIO_PCI_VGA
+static bool disable_vga;
+module_param(disable_vga, bool, S_IRUGO);
+MODULE_PARM_DESC(disable_vga, "Disable VGA resource access through vfio-pci");
+#endif
+
+static bool disable_idle_d3;
+module_param(disable_idle_d3, bool, S_IRUGO | S_IWUSR);
+MODULE_PARM_DESC(disable_idle_d3,
+		 "Disable using the PCI D3 low power state for idle, unused devices");
+
 static bool enable_sriov;
 #ifdef CONFIG_PCI_IOV
 module_param(enable_sriov, bool, 0644);
@@ -215,6 +231,13 @@ static void __init vfio_pci_fill_ids(void)
 static int __init vfio_pci_init(void)
 {
 	int ret;
+	bool is_disable_vga = true;
+
+#ifdef CONFIG_VFIO_PCI_VGA
+	is_disable_vga = disable_vga;
+#endif
+
+	vfio_pci_core_set_params(nointxmask, is_disable_vga, disable_idle_d3);
 
 	ret = vfio_pci_core_init();
 	if (ret)
diff --git a/drivers/vfio/pci/vfio_pci_core.c b/drivers/vfio/pci/vfio_pci_core.c
index 3b3bf7445367..65eafaafb2e0 100644
--- a/drivers/vfio/pci/vfio_pci_core.c
+++ b/drivers/vfio/pci/vfio_pci_core.c
@@ -28,20 +28,8 @@
 #include "vfio_pci_core.h"
 
 static bool nointxmask;
-module_param_named(nointxmask, nointxmask, bool, S_IRUGO | S_IWUSR);
-MODULE_PARM_DESC(nointxmask,
-		  "Disable support for PCI 2.3 style INTx masking.  If this resolves problems for specific devices, report lspci -vvvxxx to linux-pci@vger.kernel.org so the device can be fixed automatically via the broken_intx_masking flag.");
-
-#ifdef CONFIG_VFIO_PCI_VGA
 static bool disable_vga;
-module_param(disable_vga, bool, S_IRUGO);
-MODULE_PARM_DESC(disable_vga, "Disable VGA resource access through vfio-pci");
-#endif
-
 static bool disable_idle_d3;
-module_param(disable_idle_d3, bool, S_IRUGO | S_IWUSR);
-MODULE_PARM_DESC(disable_idle_d3,
-		 "Disable using the PCI D3 low power state for idle, unused devices");
 
 static inline bool vfio_vga_disabled(void)
 {
@@ -2121,6 +2109,14 @@ static bool vfio_pci_dev_set_try_reset(struct vfio_device_set *dev_set)
 	return true;
 }
 
+void vfio_pci_core_set_params(bool is_nointxmask, bool is_disable_vga,
+			      bool is_disable_idle_d3)
+{
+	nointxmask = is_nointxmask;
+	disable_vga = is_disable_vga;
+	disable_idle_d3 = is_disable_idle_d3;
+}
+
 /* This will become the __exit function of vfio_pci_core.ko */
 void vfio_pci_core_cleanup(void)
 {
diff --git a/drivers/vfio/pci/vfio_pci_core.h b/drivers/vfio/pci/vfio_pci_core.h
index ffaf544f35db..7a2da1e14de3 100644
--- a/drivers/vfio/pci/vfio_pci_core.h
+++ b/drivers/vfio/pci/vfio_pci_core.h
@@ -209,6 +209,8 @@ static inline int vfio_pci_info_zdev_add_caps(struct vfio_pci_core_device *vdev,
 /* Will be exported for vfio pci drivers usage */
 void vfio_pci_core_cleanup(void);
 int vfio_pci_core_init(void);
+void vfio_pci_core_set_params(bool nointxmask, bool is_disable_vga,
+			      bool is_disable_idle_d3);
 void vfio_pci_core_close_device(struct vfio_device *core_vdev);
 void vfio_pci_core_init_device(struct vfio_pci_core_device *vdev,
 			       struct pci_dev *pdev,

