#date: 2004-04-13
#id: 1.1371.1.409
#tag: other
#time: 18:28:29
#title: zero 'hw_regs_t hw' allocated from stack in ide.c and ide-cs.c
#who: B.Zolnierkiewicz@elka.pw.edu.pl[torvalds]
#
# ChangeSet
#   1.1371.1.409 04/04/13 18:28:29 B.Zolnierkiewicz@elka.pw.edu.pl[torvalds] +2 -0
#   [PATCH] zero 'hw_regs_t hw' allocated from stack in ide.c and ide-cs.c
#
# drivers/ide/legacy/ide-cs.c +1 -0
# drivers/ide/ide.c +1 -0
#
diff -Nru a/drivers/ide/ide.c b/drivers/ide/ide.c
--- a/drivers/ide/ide.c	Tue Apr 27 23:13:45 2004
+++ b/drivers/ide/ide.c	Tue Apr 27 23:13:45 2004
@@ -1574,6 +1574,7 @@
 			if (!capable(CAP_SYS_RAWIO)) return -EACCES;
 			if (copy_from_user(args, (void *)arg, 3 * sizeof(int)))
 				return -EFAULT;
+			memset(&hw, 0, sizeof(hw));
 			ide_init_hwif_ports(&hw, (unsigned long) args[0],
 					    (unsigned long) args[1], NULL);
 			hw.irq = args[2];
diff -Nru a/drivers/ide/legacy/ide-cs.c b/drivers/ide/legacy/ide-cs.c
--- a/drivers/ide/legacy/ide-cs.c	Tue Apr 27 23:13:45 2004
+++ b/drivers/ide/legacy/ide-cs.c	Tue Apr 27 23:13:45 2004
@@ -213,6 +213,7 @@
 static int idecs_register(unsigned long io, unsigned long ctl, unsigned long irq)
 {
     hw_regs_t hw;
+    memset(&hw, 0, sizeof(hw));
     ide_init_hwif_ports(&hw, io, ctl, NULL);
     hw.irq = irq;
     hw.chipset = ide_pci;
