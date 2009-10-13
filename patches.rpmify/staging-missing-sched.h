From: Jeff Mahoney <jeffm@suse.com>
Subject: [PATCH] staging: Complete sched.h removal from interrupt.h

 Commit d43c36dc removed sched.h from interrupt.h and distributed sched.h
 to users which needed it. Since make all{mod,yes}config skips staging,
 these drivers were missed.

Signed-off-by: Jeff Mahoney <jeffm@suse.com>
---
 drivers/staging/b3dfg/b3dfg.c              |    1 +
 drivers/staging/hv/osd.c                   |    1 +
 drivers/staging/iio/industrialio-core.c    |    2 ++
 drivers/staging/poch/poch.c                |    1 +
 drivers/staging/rt2860/common/cmm_info.c   |    1 +
 drivers/staging/rt2860/rt_linux.c          |    1 +
 drivers/staging/rt3090/common/cmm_info.c   |    1 +
 drivers/staging/rt3090/rt_linux.c          |    1 +
 drivers/staging/sep/sep_driver.c           |    1 +
 drivers/staging/vme/bridges/vme_ca91cx42.c |    1 +
 drivers/staging/vme/bridges/vme_tsi148.c   |    1 +
 11 files changed, 12 insertions(+)

--- a/drivers/staging/b3dfg/b3dfg.c
+++ b/drivers/staging/b3dfg/b3dfg.c
@@ -33,6 +33,7 @@
 #include <linux/cdev.h>
 #include <linux/list.h>
 #include <linux/poll.h>
+#include <linux/sched.h>
 #include <linux/wait.h>
 #include <linux/mm.h>
 #include <linux/uaccess.h>
--- a/drivers/staging/hv/osd.c
+++ b/drivers/staging/hv/osd.c
@@ -30,6 +30,7 @@
 #include <linux/ioport.h>
 #include <linux/irq.h>
 #include <linux/interrupt.h>
+#include <linux/sched.h>
 #include <linux/wait.h>
 #include <linux/spinlock.h>
 #include <linux/workqueue.h>
--- a/drivers/staging/iio/industrialio-core.c
+++ b/drivers/staging/iio/industrialio-core.c
@@ -19,6 +19,8 @@
 #include <linux/interrupt.h>
 #include <linux/poll.h>
 #include <linux/cdev.h>
+#include <linux/sched.h>
+#include <linux/wait.h>
 #include "iio.h"
 #include "trigger_consumer.h"
 
--- a/drivers/staging/poch/poch.c
+++ b/drivers/staging/poch/poch.c
@@ -20,6 +20,7 @@
 #include <linux/init.h>
 #include <linux/ioctl.h>
 #include <linux/io.h>
+#include <linux/sched.h>
 
 #include "poch.h"
 
--- a/drivers/staging/rt2860/common/cmm_info.c
+++ b/drivers/staging/rt2860/common/cmm_info.c
@@ -25,6 +25,7 @@
  *************************************************************************
 */
 
+#include <linux/sched.h>
 #include "../rt_config.h"
 
 INT	Show_SSID_Proc(
--- a/drivers/staging/rt2860/rt_linux.c
+++ b/drivers/staging/rt2860/rt_linux.c
@@ -25,6 +25,7 @@
  *************************************************************************
  */
 
+#include <linux/sched.h>
 #include "rt_config.h"
 
 ULONG	RTDebugLevel = RT_DEBUG_ERROR;
--- a/drivers/staging/rt3090/common/cmm_info.c
+++ b/drivers/staging/rt3090/common/cmm_info.c
@@ -34,6 +34,7 @@
     ---------    ----------    ----------------------------------------------
  */
 
+#include <linux/sched.h>
 #include "../rt_config.h"
 
 
--- a/drivers/staging/rt3090/rt_linux.c
+++ b/drivers/staging/rt3090/rt_linux.c
@@ -25,6 +25,7 @@
  *************************************************************************
  */
 
+#include <linux/sched.h>
 #include "rt_config.h"
 
 ULONG	RTDebugLevel = RT_DEBUG_ERROR;
--- a/drivers/staging/sep/sep_driver.c
+++ b/drivers/staging/sep/sep_driver.c
@@ -38,6 +38,7 @@
 #include <linux/mm.h>
 #include <linux/poll.h>
 #include <linux/wait.h>
+#include <linux/sched.h>
 #include <linux/pci.h>
 #include <linux/firmware.h>
 #include <asm/ioctl.h>
--- a/drivers/staging/vme/bridges/vme_ca91cx42.c
+++ b/drivers/staging/vme/bridges/vme_ca91cx42.c
@@ -25,6 +25,7 @@
 #include <linux/poll.h>
 #include <linux/interrupt.h>
 #include <linux/spinlock.h>
+#include <linux/sched.h>
 #include <asm/time.h>
 #include <asm/io.h>
 #include <asm/uaccess.h>
--- a/drivers/staging/vme/bridges/vme_tsi148.c
+++ b/drivers/staging/vme/bridges/vme_tsi148.c
@@ -25,6 +25,7 @@
 #include <linux/dma-mapping.h>
 #include <linux/interrupt.h>
 #include <linux/spinlock.h>
+#include <linux/sched.h>
 #include <asm/time.h>
 #include <asm/io.h>
 #include <asm/uaccess.h>
