#date: 2004-04-06
#id: 1.1371.687.1
#tag: other
#time: 08:32:07
#title: Support newer revisions of broadcoms in b44.c
#who: pavel@ucw.cz
#
# ChangeSet
#   1.1371.687.1 04/04/06 08:32:07 pavel@ucw.cz +3 -0
#   [PATCH] Support newer revisions of broadcoms in b44.c
#   
#   This adds support for newer revisions of the chips. The
#   b44_disable_ints at the beggining actually kills machine with newer
#   revision, but its removal has no ill effects.
#
# #
diff -Nru a/drivers/net/b44.c b/drivers/net/b44.c
--- a/drivers/net/b44.c	Wed Apr 28 00:21:24 2004
+++ b/drivers/net/b44.c	Wed Apr 28 00:21:24 2004
@@ -2,6 +2,8 @@
  *
  * Copyright (C) 2002 David S. Miller (davem@redhat.com)
  * Fixed by Pekka Pietikainen (pp@ee.oulu.fi)
+ *
+ * Distribute under GPL.
  */
 
 #include <linux/kernel.h>
@@ -25,8 +27,8 @@
 
 #define DRV_MODULE_NAME		"b44"
 #define PFX DRV_MODULE_NAME	": "
-#define DRV_MODULE_VERSION	"0.92"
-#define DRV_MODULE_RELDATE	"Nov 4, 2003"
+#define DRV_MODULE_VERSION	"0.93"
+#define DRV_MODULE_RELDATE	"Mar, 2004"
 
 #define B44_DEF_MSG_ENABLE	  \
 	(NETIF_MSG_DRV		| \
@@ -83,6 +85,10 @@
 static struct pci_device_id b44_pci_tbl[] = {
 	{ PCI_VENDOR_ID_BROADCOM, PCI_DEVICE_ID_BCM4401,
 	  PCI_ANY_ID, PCI_ANY_ID, 0, 0, 0UL },
+	{ PCI_VENDOR_ID_BROADCOM, PCI_DEVICE_ID_BCM4401B0,
+	  PCI_ANY_ID, PCI_ANY_ID, 0, 0, 0UL },
+	{ PCI_VENDOR_ID_BROADCOM, PCI_DEVICE_ID_BCM4401B1,
+	  PCI_ANY_ID, PCI_ANY_ID, 0, 0, 0UL },
 	{ }	/* terminate list with empty entry */
 };
 
@@ -1178,7 +1184,6 @@
 {
 	u32 val;
 
-	b44_disable_ints(bp);
 	b44_chip_reset(bp);
 	b44_phy_reset(bp);
 	b44_setup_phy(bp);
diff -Nru a/drivers/net/b44.h b/drivers/net/b44.h
--- a/drivers/net/b44.h	Wed Apr 28 00:21:24 2004
+++ b/drivers/net/b44.h	Wed Apr 28 00:21:24 2004
@@ -1,8 +1,9 @@
 #ifndef _B44_H
 #define _B44_H
 
-/* Register layout. */
+/* Register layout. (These correspond to struct _bcmenettregs in bcm4400.) */
 #define	B44_DEVCTRL	0x0000UL /* Device Control */
+#define  DEVCTRL_MPM		0x00000040 /* Magic Packet PME Enable (B0 only) */
 #define  DEVCTRL_PFE		0x00000080 /* Pattern Filtering Enable */
 #define  DEVCTRL_IPP		0x00000400 /* Internal EPHY Present */
 #define  DEVCTRL_EPR		0x00008000 /* EPHY Reset */
@@ -24,6 +25,7 @@
 #define  WKUP_LEN_P3_SHIFT	24
 #define  WKUP_LEN_D3		0x80000000
 #define B44_ISTAT	0x0020UL /* Interrupt Status */
+#define  ISTAT_LS		0x00000020 /* Link Change (B0 only) */
 #define  ISTAT_PME		0x00000040 /* Power Management Event */
 #define  ISTAT_TO		0x00000080 /* General Purpose Timeout */
 #define  ISTAT_DSCE		0x00000400 /* Descriptor Error */
@@ -41,6 +43,8 @@
 #define B44_IMASK	0x0024UL /* Interrupt Mask */
 #define  IMASK_DEF		(ISTAT_ERRORS | ISTAT_TO | ISTAT_RX | ISTAT_TX)
 #define B44_GPTIMER	0x0028UL /* General Purpose Timer */
+#define B44_ADDR_LO	0x0088UL /* ENET Address Lo (B0 only) */
+#define B44_ADDR_HI	0x008CUL /* ENET Address Hi (B0 only) */
 #define B44_FILT_ADDR	0x0090UL /* ENET Filter Address */
 #define B44_FILT_DATA	0x0094UL /* ENET Filter Data */
 #define B44_TXBURST	0x00A0UL /* TX Max Burst Length */
diff -Nru a/include/linux/pci_ids.h b/include/linux/pci_ids.h
--- a/include/linux/pci_ids.h	Wed Apr 28 00:21:24 2004
+++ b/include/linux/pci_ids.h	Wed Apr 28 00:21:24 2004
@@ -1837,6 +1837,8 @@
 #define PCI_DEVICE_ID_TIGON3_5901	0x170d
 #define PCI_DEVICE_ID_TIGON3_5901_2	0x170e
 #define PCI_DEVICE_ID_BCM4401		0x4401
+#define PCI_DEVICE_ID_BCM4401B0		0x4402
+#define PCI_DEVICE_ID_BCM4401B1		0x170c
 
 #define PCI_VENDOR_ID_ENE		0x1524
 #define PCI_DEVICE_ID_ENE_1211		0x1211
