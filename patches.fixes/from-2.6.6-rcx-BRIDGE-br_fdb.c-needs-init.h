#date: 2004-04-16
#id: 1.1371.1.467
#tag: other
#time: 15:55:37
#title: [BRIDGE]: br_fdb.c needs init.h
#who: davem@nuts.davemloft.net
#
# ChangeSet
#   1.1371.1.467 04/04/16 15:55:37 davem@nuts.davemloft.net +1 -0
#   [BRIDGE]: br_fdb.c needs init.h
#
# net/bridge/br_fdb.c +1 -0
#
diff -Nru a/net/bridge/br_fdb.c b/net/bridge/br_fdb.c
--- a/net/bridge/br_fdb.c	Wed Apr 28 00:44:18 2004
+++ b/net/bridge/br_fdb.c	Wed Apr 28 00:44:18 2004
@@ -14,6 +14,7 @@
  */
 
 #include <linux/kernel.h>
+#include <linux/init.h>
 #include <linux/spinlock.h>
 #include <linux/if_bridge.h>
 #include <linux/times.h>
