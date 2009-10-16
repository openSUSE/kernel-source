From: Jeff Mahoney <jeffm@suse.com>
Subject: [PATCH] staging: Complete sched.h removal from interrupt.h

 Commit d43c36dc removed sched.h from interrupt.h and distributed sched.h
 to users which needed it. Since make all{mod,yes}config skips staging,
 these drivers were missed.

Signed-off-by: Jeff Mahoney <jeffm@suse.com>
---
 drivers/staging/b3dfg/b3dfg.c |    1 +
 1 file changed, 1 insertion(+)

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
