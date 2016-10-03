#!/usr/bin/env python
"""
xen-port-patches.py [git dir]
Create custom patches for xen from custom patches that affect x86.
Turned out to be a little functional programming exercise for the author.
(c) 2005-04-06, Kurt Garloff <garloff@suse.de>
"""

import re, glob, sys, os, filecmp

# List of replacement rules
replrules = [(r"(.*)-xen(\.[^/\s])", r"\1\2"),
	   (r"include/asm-([^/\s]+86[^/\s]*)/mach-xen/asm/", r"include/asm-\1/"),
	   (r"arch/([^/\s]+86[^/\s]*)/include/mach-xen/asm/", r"arch/\1/include/asm/")]
# List of compiled rules (speed reasons)
#comprules = map(lambda(x): (x[0], x[1], re.compile(x[0])), replrules)
comprules = [ (x[0], x[1], re.compile(x[0])) for x in replrules ]

def applCorrFwd(path):
	"Try to apply replrules, return void elem if none applied, otherwise \
	 corresponding old and new name"
	# Maximal functional programming obfusc^W elegance
		# Drop element 2 from each tupel
	return map(lambda(x): (x[0], x[1]), \
		# Filter out non-matched path combinations
		filter(lambda(x): x[2], \
		# Try all replacement rules
		map(lambda(x): (path, 
			re.sub(x[0], x[1], path), x[2].search(path)),
			comprules)))


def createReplList(patch):
	"Creates a list of files to watch and their corresp xen file names"
	pfile = open(patch, "r")
	srch = re.compile(r"^\+\+\+ [^/\s]+/([\S]*)")
	# Again illegi^W beautiful functional programming
	# return matched string no 1
	matches = map(lambda(m): m.group(1), \
		# filter out non-matches
		filter(lambda(m): m, \
		# find matches
		map(lambda(line): srch.search(line), pfile)))
	pfile.close()
	#print matches
	# Try path replacements, drop empty elements and one nesting level
	return map(lambda(x): (x[0][0], x[0][1]), \
			filter(lambda(x): x, map(applCorrFwd, matches)))

def findPatchFiles(kgit):
	"Returns a list of all files in patches.*/ on below kgit"
	list = glob.glob(kgit + "/patches.*/*")
	# Avoid patches in patches.xen, backup files
	filterout = re.compile("(patches\.xen|~$|\.#)")
	return filter(lambda(x): not filterout.search(x), list)

def writePatch(fname, hdr, body):
	"Create xen patch corresponding to other patch"
	xenrepl = re.compile(r"^.*\/([^\/]*)$")
	xenfname = re.sub(xenrepl, r"xen3-\1", fname)
	shortrepl = re.compile(r"^.*\/([^\/]*\/[^\/]*)$")
	shortname = re.sub(shortrepl, r"\1", fname)
	origname = ".".join([xenfname, "orig"])
	print "%s -> %s" % (shortname, xenfname)
	if os.access(xenfname, os.F_OK):
		os.rename(xenfname, origname)
	pfile = open(xenfname, "w")
	pfile.write(hdr)
	pfile.write("Automatically created from \"%s\" by " \
			"xen-port-patches.py\n\n" % shortname)
	pfile.write(body)
	pfile.close()
	if os.access(origname, os.F_OK):
		if filecmp.cmp(xenfname, origname):
			os.remove(xenfname)
	else:
		ser = open("xen3-series.conf", "a")
		ser.write("\t\t%s\n" % xenfname)
		ser.close()

def decorateSubject(subject):
	m = re.search(r"^(Subject:\s*(?:\[.*\])?\s*)(.*)", subject);
	if not m:
		return subject
	if re.search(r"^[^\s]*:[^:]*$", m.group(2)):
		# subsystem: text -> xen/subsystem: text
		tag = "xen/"
	else:
		# text -> xen: text
		tag = "xen: "
	return m.group(1) + tag + m.group(2) + "\n"

def mayCreatePatch(fname, repls):
	"Try to apply the replacement rules to fname"
	if fname.endswith(".gz"):
		decomp ="gzip"
	elif fname.endswith(".bz2"):
		decomp = "bzip2"
	elif fname.endswith(".xz"):
		decomp = "xz"
	else:
		decomp = ""
	if decomp == "":
		pfile = open(fname, "r")
	else:
		pfile = os.popen(" ".join([decomp, "-dc", fname]), "r")
		parts = fname.split(".")
		del parts[-1]
		fname = ".".join(parts)
	# Again an unelegant loop with an ugly state machine
	active = 0; header = 0
	patch = ""; rule = ()
	patchheader = ""; pheaderactive = 1
	endmarker = re.compile(r"^(Index|diff|CVS|RCS|\-\-\-|\+\+\+|===)")
	subj = re.compile(r"^Subject:\s")
	commit = re.compile(r"^Git-[Cc]ommit:\s")
	mainline = re.compile(r"^Patch-[Mm]ainline:\s")
	for line in pfile:
		hmark = endmarker.search(line)
		if pheaderactive:
			if hmark:
				pheaderactive = 0
			else:
				if subj and subj.search(line):
					subj = None
					line = decorateSubject(line)
				elif commit.search(line):
					continue
				elif mainline.search(line):
					line = "Patch-mainline: Never, SUSE-Xen specific\n"
				patchheader += line
				continue
		# If we get here, we're past the patch file header
		if active:
			if header:
				if not hmark:
					header = 0
				#else:
				patch += re.sub(rule[1], rule[0], line)
			else:
				if hmark:
					active = 0
				else:
					patch += line
		# else is no good, need to test again
		if not active and hmark:
			matches = filter(lambda(x): x[2],
				map(lambda(x): (x[0], x[1], x[2].search(line)), repls))
			if matches:
				active = 1; header = 1
				# There should never be more than one match ...
				rule = (matches[0][0], matches[0][1])
				patch += re.sub(rule[1], rule[0], line)
	pfile.close()
	if patch:
		writePatch(fname, patchheader, patch)

def createXenPatches(filelist, repls):
	"For each file in the list, find hunks that may be needed for Xen"
	# We could do this again with functional programming, but the
	# memory requirements may be significant, so let's create a
	# loop on the per patchfile level.
	for pfile in filelist:
		mayCreatePatch(pfile, repls)

def main(args):
	"Main program"
	# Allow overriding kernel git dir
	if len(args) > 1 and args[1] != ".":
		kerngit = args[1]
	else:
		kerngit = re.sub(r"^(.*)/[^/]+/[^/]+$", r"\1", os.path.abspath(args[0]))
	print "Using kernel git at '%s'" % (kerngit)
	# Create list of replacements
	repllist = createReplList(kerngit + "/patches.xen/xen3-auto-xen-arch.diff")
	#print repllist
	# ... and compile
	complrepl = map(lambda(x): (x[0], x[1], re.compile(x[1])), repllist)
	# Create a list of patch files
	patchfiles = findPatchFiles(kerngit)
	#print patchfiles
	createXenPatches(patchfiles + args[2:], complrepl)

# Entry point
if __name__ == '__main__':
	main(sys.argv)

