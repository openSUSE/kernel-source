From 81c0a78b644f0e265a01d5a5f5ab397b791bad08 Mon Sep 17 00:00:00 2001
From: Wang Shaoyan <wangshaoyan.pt@taobao.com>
Date: Fri, 5 Aug 2011 18:51:29 +0800
Subject: [PATCH] ALSA: hda - Fix a complile warning in patch_via.c
Git-commit: 81c0a78b644f0e265a01d5a5f5ab397b791bad08
Patch-mainline: 3.1-rc2
References: FATE#314106

  sound/pci/hda/patch_via.c:2087: warning: 'dac' may be used uninitialized in this function

Signed-off-by: Wang Shaoyan <wangshaoyan.pt@taobao.com>
Signed-off-by: Takashi Iwai <tiwai@suse.de>

---
 sound/pci/hda/patch_via.c |    2 +-
 1 file changed, 1 insertion(+), 1 deletion(-)

--- a/sound/pci/hda/patch_via.c
+++ b/sound/pci/hda/patch_via.c
@@ -2084,7 +2084,7 @@ static int via_auto_create_speaker_ctls(
 	struct via_spec *spec = codec->spec;
 	struct nid_path *path;
 	bool check_dac;
-	hda_nid_t pin, dac;
+	hda_nid_t pin, dac = 0;
 	int err;
 
 	pin = spec->autocfg.speaker_pins[0];
