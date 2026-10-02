From 82b1d73f1f22df2c8384cb7cea4aabd9db5273a9 Mon Sep 17 00:00:00 2001
From: Takashi Iwai <tiwai@suse.de>
Date: Tue, 20 Dec 2011 15:53:07 +0100
Subject: [PATCH] ALSA: hda - Fix left-over merge issues in patch_hdmi.c
Git-commit: 82b1d73f1f22df2c8384cb7cea4aabd9db5273a9
Patch-mainline: 3.3-rc1
References: FATE#313695

Signed-off-by: Takashi Iwai <tiwai@suse.de>

---
 sound/pci/hda/patch_hdmi.c |    3 +--
 1 file changed, 1 insertion(+), 2 deletions(-)

--- a/sound/pci/hda/patch_hdmi.c
+++ b/sound/pci/hda/patch_hdmi.c
@@ -805,7 +805,6 @@ static void hdmi_non_intrinsic_event(str
 
 static void hdmi_unsol_event(struct hda_codec *codec, unsigned int res)
 {
-	struct hdmi_spec *spec = codec->spec;
 	int tag = res >> AC_UNSOL_RES_TAG_SHIFT;
 	int subtag = (res & AC_UNSOL_RES_SUBTAG) >> AC_UNSOL_RES_SUBTAG_SHIFT;
 
@@ -1273,7 +1272,7 @@ static int generic_hdmi_build_controls(s
 		if (err < 0)
 			return err;
 
-		hdmi_present_sense(per_pin, false);
+		hdmi_present_sense(per_pin, 0);
 	}
 
 	return 0;
