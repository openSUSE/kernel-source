From 5b3761954dac2d1393beef8210eb8cee81d16b8d Mon Sep 17 00:00:00 2001
From: Takashi Iwai <tiwai@suse.de>
Date: Wed, 7 Nov 2012 10:32:47 +0100
Subject: [PATCH] ALSA: hda - Fix empty DAC filling in patch_via.c
Git-commit: 5b3761954dac2d1393beef8210eb8cee81d16b8d
Patch-mainline: 3.7-rc5
References: FATE#314310

In via_auto_fill_adc_nids(), the parser tries to fill dac_nids[] at
the point of the current line-out (i).  When no valid path is found
for this output, this results in dac = 0, thus it creates a hole in
dac_nids[].  This confuses is_empty_dac() and trims the detected DAC
in later reference.

This patch fixes the bug by appending DAC properly to dac_nids[] in
via_auto_fill_adc_nids().

Reported-by: Massimo Del Fedele <max@veneto.com>
Cc: <stable@vger.kernel.org>
Signed-off-by: Takashi Iwai <tiwai@suse.de>

---
 sound/pci/hda/patch_via.c |   11 ++++-------
 1 file changed, 4 insertions(+), 7 deletions(-)

--- a/sound/pci/hda/patch_via.c
+++ b/sound/pci/hda/patch_via.c
@@ -1825,11 +1825,11 @@ static int via_auto_fill_dac_nids(struct
 {
 	struct via_spec *spec = codec->spec;
 	const struct auto_pin_cfg *cfg = &spec->autocfg;
-	int i, dac_num;
+	int i;
 	hda_nid_t nid;
 
+	spec->multiout.num_dacs = 0;
 	spec->multiout.dac_nids = spec->private_dac_nids;
-	dac_num = 0;
 	for (i = 0; i < cfg->line_outs; i++) {
 		hda_nid_t dac = 0;
 		nid = cfg->line_out_pins[i];
@@ -1840,16 +1840,13 @@ static int via_auto_fill_dac_nids(struct
 		if (!i && parse_output_path(codec, nid, dac, 1,
 					    &spec->out_mix_path))
 			dac = spec->out_mix_path.path[0];
-		if (dac) {
-			spec->private_dac_nids[i] = dac;
-			dac_num++;
-		}
+		if (dac)
+			spec->private_dac_nids[spec->multiout.num_dacs++] = dac;
 	}
 	if (!spec->out_path[0].depth && spec->out_mix_path.depth) {
 		spec->out_path[0] = spec->out_mix_path;
 		spec->out_mix_path.depth = 0;
 	}
-	spec->multiout.num_dacs = dac_num;
 	return 0;
 }
 
