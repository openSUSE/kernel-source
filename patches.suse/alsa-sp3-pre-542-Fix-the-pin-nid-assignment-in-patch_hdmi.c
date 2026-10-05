From 21cd683d318041c63876b4acbebb3f6d9d80597b Mon Sep 17 00:00:00 2001
From: Takashi Iwai <tiwai@suse.de>
Date: Wed, 20 Jun 2012 09:19:32 +0200
Subject: [PATCH] ALSA: hda - Fix the pin nid assignment in patch_hdmi.c
Git-commit: 21cd683d318041c63876b4acbebb3f6d9d80597b
Patch-mainline: 3.6-rc1
References: FATE#313695

This fixes the regression introduced by the commit d0b1252d for
refactoring simple_hdmi*().  The pin NID wasn't assigned correctly.

Reported-by: Annie Liu <annieliu@viatech.com.cn>
Signed-off-by: Takashi Iwai <tiwai@suse.de>

---
 sound/pci/hda/patch_hdmi.c |    2 +-
 1 file changed, 1 insertion(+), 1 deletion(-)

--- a/sound/pci/hda/patch_hdmi.c
+++ b/sound/pci/hda/patch_hdmi.c
@@ -1607,7 +1607,7 @@ static int patch_simple_hdmi(struct hda_
 	spec->num_cvts = 1;
 	spec->num_pins = 1;
 	spec->cvts[0].cvt_nid = cvt_nid;
-	spec->cvts[0].cvt_nid = pin_nid;
+	spec->pins[0].pin_nid = pin_nid;
 	spec->pcm_playback = simple_pcm_playback;
 
 	codec->patch_ops = simple_hdmi_patch_ops;
