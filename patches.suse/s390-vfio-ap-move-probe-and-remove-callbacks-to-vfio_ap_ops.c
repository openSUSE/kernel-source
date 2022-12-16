From: Tony Krowiak <akrowiak@linux.ibm.com>
Date: Wed, 14 Oct 2020 15:34:49 -0400
Subject: s390/vfio-ap: move probe and remove callbacks to vfio_ap_ops.c
Git-commit: 260f3ea141382386e97611e7c2029bc013088ab1
Patch-mainline: v6.0-rc1
References: bsc#1205701

Let's move the probe and remove callbacks into the vfio_ap_ops.c
file to keep all code related to managing queues in a single file. This
way, all functions related to queue management can be removed from the
vfio_ap_private.h header file defining the public interfaces for the
vfio_ap device driver.

Signed-off-by: Tony Krowiak <akrowiak@linux.ibm.com>
Reviewed-by: Halil Pasic <pasic@linux.ibm.com>
Signed-off-by: Alexander Gordeev <agordeev@linux.ibm.com>
Acked-by: Joerg Roedel <jroedel@suse.de>
---
 drivers/s390/crypto/vfio_ap_drv.c     | 118 +---------------------------------
 drivers/s390/crypto/vfio_ap_ops.c     |  99 +++++++++++++++++++++++++++-
 drivers/s390/crypto/vfio_ap_private.h |   5 +-
 3 files changed, 102 insertions(+), 120 deletions(-)

diff --git a/drivers/s390/crypto/vfio_ap_drv.c b/drivers/s390/crypto/vfio_ap_drv.c
index 4ac9c6521ec1..1ff6e3dbbffe 100644
--- a/drivers/s390/crypto/vfio_ap_drv.c
+++ b/drivers/s390/crypto/vfio_ap_drv.c
@@ -18,9 +18,6 @@
 
 #define VFIO_AP_ROOT_NAME "vfio_ap"
 #define VFIO_AP_DEV_NAME "matrix"
-#define AP_QUEUE_ASSIGNED "assigned"
-#define AP_QUEUE_UNASSIGNED "unassigned"
-#define AP_QUEUE_IN_USE "in use"
 
 MODULE_AUTHOR("IBM Corporation");
 MODULE_DESCRIPTION("VFIO AP device driver, Copyright IBM Corp. 2018");
@@ -46,120 +43,9 @@ static struct ap_device_id ap_queue_ids[] = {
 	{ /* end of sibling */ },
 };
 
-static struct ap_matrix_mdev *vfio_ap_mdev_for_queue(struct vfio_ap_queue *q)
-{
-	struct ap_matrix_mdev *matrix_mdev;
-	unsigned long apid = AP_QID_CARD(q->apqn);
-	unsigned long apqi = AP_QID_QUEUE(q->apqn);
-
-	list_for_each_entry(matrix_mdev, &matrix_dev->mdev_list, node) {
-		if (test_bit_inv(apid, matrix_mdev->matrix.apm) &&
-		    test_bit_inv(apqi, matrix_mdev->matrix.aqm))
-			return matrix_mdev;
-	}
-
-	return NULL;
-}
-
-static ssize_t status_show(struct device *dev,
-			   struct device_attribute *attr,
-			   char *buf)
-{
-	ssize_t nchars = 0;
-	struct vfio_ap_queue *q;
-	struct ap_matrix_mdev *matrix_mdev;
-	struct ap_device *apdev = to_ap_dev(dev);
-
-	mutex_lock(&matrix_dev->lock);
-	q = dev_get_drvdata(&apdev->device);
-	matrix_mdev = vfio_ap_mdev_for_queue(q);
-
-	if (matrix_mdev) {
-		if (matrix_mdev->kvm)
-			nchars = scnprintf(buf, PAGE_SIZE, "%s\n",
-					   AP_QUEUE_IN_USE);
-		else
-			nchars = scnprintf(buf, PAGE_SIZE, "%s\n",
-					   AP_QUEUE_ASSIGNED);
-	} else {
-		nchars = scnprintf(buf, PAGE_SIZE, "%s\n",
-				   AP_QUEUE_UNASSIGNED);
-	}
-
-	mutex_unlock(&matrix_dev->lock);
-
-	return nchars;
-}
-
-static DEVICE_ATTR_RO(status);
-
-static struct attribute *vfio_queue_attrs[] = {
-	&dev_attr_status.attr,
-	NULL,
-};
-
-static const struct attribute_group vfio_queue_attr_group = {
-	.attrs = vfio_queue_attrs,
-};
-
-/**
- * vfio_ap_queue_dev_probe: Allocate a vfio_ap_queue structure and associate it
- *			    with the device as driver_data.
- *
- * @apdev: the AP device being probed
- *
- * Return: returns 0 if the probe succeeded; otherwise, returns an error if
- *	   storage could not be allocated for a vfio_ap_queue object or the
- *	   sysfs 'status' attribute could not be created for the queue device.
- */
-static int vfio_ap_queue_dev_probe(struct ap_device *apdev)
-{
-	int ret;
-	struct vfio_ap_queue *q;
-
-	q = kzalloc(sizeof(*q), GFP_KERNEL);
-	if (!q)
-		return -ENOMEM;
-
-	mutex_lock(&matrix_dev->lock);
-	dev_set_drvdata(&apdev->device, q);
-	q->apqn = to_ap_queue(&apdev->device)->qid;
-	q->saved_isc = VFIO_AP_ISC_INVALID;
-
-	ret = sysfs_create_group(&apdev->device.kobj, &vfio_queue_attr_group);
-	if (ret) {
-		dev_set_drvdata(&apdev->device, NULL);
-		kfree(q);
-	}
-
-	mutex_unlock(&matrix_dev->lock);
-
-	return ret;
-}
-
-/**
- * vfio_ap_queue_dev_remove: Free the associated vfio_ap_queue structure.
- *
- * @apdev: the AP device being removed
- *
- * Takes the matrix lock to avoid actions on this device while doing the remove.
- */
-static void vfio_ap_queue_dev_remove(struct ap_device *apdev)
-{
-	struct vfio_ap_queue *q;
-
-	mutex_lock(&matrix_dev->lock);
-	sysfs_remove_group(&apdev->device.kobj, &vfio_queue_attr_group);
-	q = dev_get_drvdata(&apdev->device);
-	vfio_ap_mdev_reset_queue(q, 1);
-	dev_set_drvdata(&apdev->device, NULL);
-	kfree(q);
-	mutex_unlock(&matrix_dev->lock);
-}
-
 static struct ap_driver vfio_ap_drv = {
-	.probe = vfio_ap_queue_dev_probe,
-	.remove = vfio_ap_queue_dev_remove,
+	.probe = vfio_ap_mdev_probe_queue,
+	.remove = vfio_ap_mdev_remove_queue,
 	.ids = ap_queue_ids,
 };
 
diff --git a/drivers/s390/crypto/vfio_ap_ops.c b/drivers/s390/crypto/vfio_ap_ops.c
index 634e23ae8912..32d276c85079 100644
--- a/drivers/s390/crypto/vfio_ap_ops.c
+++ b/drivers/s390/crypto/vfio_ap_ops.c
@@ -26,6 +26,10 @@
 #define VFIO_AP_MDEV_TYPE_HWVIRT "passthrough"
 #define VFIO_AP_MDEV_NAME_HWVIRT "VFIO AP Passthrough Device"
 
+#define AP_QUEUE_ASSIGNED "assigned"
+#define AP_QUEUE_UNASSIGNED "unassigned"
+#define AP_QUEUE_IN_USE "in use"
+
 static int vfio_ap_mdev_reset_queues(struct ap_matrix_mdev *matrix_mdev);
 static struct vfio_ap_queue *vfio_ap_find_queue(int apqn);
 static const struct vfio_device_ops vfio_ap_matrix_dev_ops;
@@ -1294,8 +1298,8 @@ static struct vfio_ap_queue *vfio_ap_find_queue(int apqn)
 	return q;
 }
 
-int vfio_ap_mdev_reset_queue(struct vfio_ap_queue *q,
-			     unsigned int retry)
+static int vfio_ap_mdev_reset_queue(struct vfio_ap_queue *q,
+				    unsigned int retry)
 {
 	struct ap_queue_status status;
 	int ret;
@@ -1452,6 +1456,62 @@ static ssize_t vfio_ap_mdev_ioctl(struct vfio_device *vdev,
 	return ret;
 }
 
+static struct ap_matrix_mdev *vfio_ap_mdev_for_queue(struct vfio_ap_queue *q)
+{
+	struct ap_matrix_mdev *matrix_mdev;
+	unsigned long apid = AP_QID_CARD(q->apqn);
+	unsigned long apqi = AP_QID_QUEUE(q->apqn);
+
+	list_for_each_entry(matrix_mdev, &matrix_dev->mdev_list, node) {
+		if (test_bit_inv(apid, matrix_mdev->matrix.apm) &&
+		    test_bit_inv(apqi, matrix_mdev->matrix.aqm))
+			return matrix_mdev;
+	}
+
+	return NULL;
+}
+
+static ssize_t status_show(struct device *dev,
+			   struct device_attribute *attr,
+			   char *buf)
+{
+	ssize_t nchars = 0;
+	struct vfio_ap_queue *q;
+	struct ap_matrix_mdev *matrix_mdev;
+	struct ap_device *apdev = to_ap_dev(dev);
+
+	mutex_lock(&matrix_dev->lock);
+	q = dev_get_drvdata(&apdev->device);
+	matrix_mdev = vfio_ap_mdev_for_queue(q);
+
+	if (matrix_mdev) {
+		if (matrix_mdev->kvm)
+			nchars = scnprintf(buf, PAGE_SIZE, "%s\n",
+					   AP_QUEUE_IN_USE);
+		else
+			nchars = scnprintf(buf, PAGE_SIZE, "%s\n",
+					   AP_QUEUE_ASSIGNED);
+	} else {
+		nchars = scnprintf(buf, PAGE_SIZE, "%s\n",
+				   AP_QUEUE_UNASSIGNED);
+	}
+
+	mutex_unlock(&matrix_dev->lock);
+
+	return nchars;
+}
+
+static DEVICE_ATTR_RO(status);
+
+static struct attribute *vfio_queue_attrs[] = {
+	&dev_attr_status.attr,
+	NULL,
+};
+
+static const struct attribute_group vfio_queue_attr_group = {
+	.attrs = vfio_queue_attrs,
+};
+
 static const struct vfio_device_ops vfio_ap_matrix_dev_ops = {
 	.open_device = vfio_ap_mdev_open_device,
 	.close_device = vfio_ap_mdev_close_device,
@@ -1495,3 +1555,38 @@ void vfio_ap_mdev_unregister(void)
 	mdev_unregister_device(&matrix_dev->device);
 	mdev_unregister_driver(&vfio_ap_matrix_driver);
 }
+
+int vfio_ap_mdev_probe_queue(struct ap_device *apdev)
+{
+	int ret;
+	struct vfio_ap_queue *q;
+
+	ret = sysfs_create_group(&apdev->device.kobj, &vfio_queue_attr_group);
+	if (ret)
+		return ret;
+
+	q = kzalloc(sizeof(*q), GFP_KERNEL);
+	if (!q)
+		return -ENOMEM;
+
+	mutex_lock(&matrix_dev->lock);
+	q->apqn = to_ap_queue(&apdev->device)->qid;
+	q->saved_isc = VFIO_AP_ISC_INVALID;
+	dev_set_drvdata(&apdev->device, q);
+	mutex_unlock(&matrix_dev->lock);
+
+	return 0;
+}
+
+void vfio_ap_mdev_remove_queue(struct ap_device *apdev)
+{
+	struct vfio_ap_queue *q;
+
+	mutex_lock(&matrix_dev->lock);
+	sysfs_remove_group(&apdev->device.kobj, &vfio_queue_attr_group);
+	q = dev_get_drvdata(&apdev->device);
+	vfio_ap_mdev_reset_queue(q, 1);
+	dev_set_drvdata(&apdev->device, NULL);
+	kfree(q);
+	mutex_unlock(&matrix_dev->lock);
+}
diff --git a/drivers/s390/crypto/vfio_ap_private.h b/drivers/s390/crypto/vfio_ap_private.h
index a26efd804d0d..96655f2eb732 100644
--- a/drivers/s390/crypto/vfio_ap_private.h
+++ b/drivers/s390/crypto/vfio_ap_private.h
@@ -116,7 +116,8 @@ struct vfio_ap_queue {
 
 int vfio_ap_mdev_register(void);
 void vfio_ap_mdev_unregister(void);
-int vfio_ap_mdev_reset_queue(struct vfio_ap_queue *q,
-			     unsigned int retry);
+
+int vfio_ap_mdev_probe_queue(struct ap_device *queue);
+void vfio_ap_mdev_remove_queue(struct ap_device *queue);
 
 #endif /* _VFIO_AP_PRIVATE_H_ */

