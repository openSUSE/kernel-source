#!/usr/bin/env python
""" 
# Mangles duplicate functions that are ifdef'd
# Useful to simplify include/linux/security.h (LSM hooks).
# 
# (c) Kurt Garloff <garloff@suse.de>, 2005-06-26, GNU GPL
"""
__revision__ = '$Id: mangle-ifdef.py,v 1.5 2005/07/03 15:45:19 garloff Exp $'


import os, sys, re

indentifdef = 1

def usage():
	"Help"
	print >> sys.stderr, "Usage: mangle-ifdef.py [-n] INFILE OUTFILE"
	print >> sys.stderr, " This tool tries to put implementations of the same function"
	print >> sys.stderr, " with different preprocessor conditional next to each other"
	print >> sys.stderr, " for consolidation. Used for include/linux/security.h"
	print >> sys.stderr, " -n switches off the indentation of the ifdefs."
	sys.exit(2)


def indent(num):
	"ifdef indentation"
	if indentifdef:
		return ' '*num
	else:
		return ''

def writeendifs(outf, number, old):
	"Write #endifs to output file"
	for num in range(len(old)-1, len(old)-1-number, -1):
		outf.write('#%sendif /* %s */\n' 
			% (indent(num), old[num][0]))

def writeelse(outf, which, old):
	"Write #else to output file"
	outf.write('#%selse /* %s */\n'
		% (indent(which), old[which][0]))

def writeifdefs(outf, number, new):
	"Write #if(n)def to output file"
	for cno in range(len(new)-number, len(new)):
		if new[cno][1] == 1:
			outf.write('#%sifdef %s\n'
				% (indent(cno), new[cno][0]))
		elif new[cno][1] == 0:
			outf.write('#%sifndef %s\n'
				% (indent(cno), new[cno][0]))
		else:
			outf.write('#%sif %s\n'
				% (indent(cno), new[cno][0]))

lastelse = ''
def changeifdefs(outf, olddefs, newdefs):
	"""When the conditions for the line changed, put necessary
	   conditionals in the output file"""
	global lastelse
	mln = min(len(olddefs), len(newdefs))
	diff = mln
	#print "Changedefs: %s -> %s" % (olddefs, newdefs)
	for num in range(0, mln):
		if newdefs[num] != olddefs[num]:
			diff = num
			break
	toclose = len(olddefs) - diff
	toopen = len(newdefs) - diff
	if diff < mln and newdefs[diff][0] == olddefs[diff][0] \
			and newdefs[diff][0] != lastelse:
		writeendifs(outf, toclose-1, olddefs)
		writeelse(outf, diff, olddefs)
		lastelse = newdefs[diff][0]
		writeifdefs(outf, toopen-1,  newdefs)
	else:
		writeendifs(outf, toclose, olddefs)
		writeifdefs(outf, toopen,  newdefs)
		lastelse = ''


def lookahead(outl, lno):
	"Reads ahead until next ';' or '}' or '{'"
	rstr = ''
	for (line, cond) in outl[lno:]:
		rstr += line
		if '}' in line or ';' in line or '{' in line or '*/' in line:
			return rstr

def skipcomm(outl, lno):
	"Skip over defines and empty lines"
	if outl[lno][0][0] == '#':
		while lno < len(outl) and outl[lno][0].strip()[-1] == '\\':
			lno += 1
		return lno+1
	#if '/*' in outl[lno][0]:
	#	while lno < len(outl) and '*/' lnot in outl[lno][0]:
	#		lno += 1
	#	return lno
	while lno < len(outl) and not outl[lno][0].strip():
		lno += 1
	return lno

def searchaltfn(outl, lno, fname):
	"Search for (alnother) definition of function fname"
	while lno < len(outl):
		lno = skipcomm(outl, lno)
		parsestr = lookahead(outl, lno)
		if not parsestr:
			lno += 1
			continue
		if '{' in parsestr:
			fnm = searchfnname(parsestr)
			if fnm == fname:
				endln = findendfn(outl, lno)
				return (lno, endln)
		lno += 1
	
	return (0, 0)

def searchfnname(line):
	"Extract function name from concatenated line"
	func = re.compile(r'\b(\w*)[ 	]*\(')
	fmatch = func.search(line)
	if fmatch and not line[0] == '#':
		return fmatch.group(1)
		
		
def findendfn(outl, lno):
	"Find end of function starting in line lno"
	elno = lno
	ilevel = 0
	body = 0
	while elno < len(outl):
		ilevel += outl[elno][0].count('{')
		if ilevel:
			body = 1
		ilevel -= outl[elno][0].count('}')
		elno += 1
		if body and ilevel <= 0:
			return elno
			
	print >> sys.stderr, "Unbalanced braces"
	sys.exit(4)

def copyrange(outl, st1, en1, st2, en2):
	"""Copy function at location st2:en2 right after st1:en1.
	   Additionally, if head or tail of function are identical,
	   consolidate."""
	lns = outl[st2:en2]
	del outl[st2:en2]
	outl[en1:en1] = lns
	
	# Consolidation 
	ln1 = en1-st1
	ln2 = en2-st2
	cond1 = outl[st1][1]
	cond2 = outl[en1][1]
	# Only do consolidation, if we are at the same conditional
	# level (otherwise, we'll not find a common condition ...)
	if len(cond1) != len(cond2):
		return en1+ln2
	# Build common condition
	conddiff = 0
	commcond = []
	for cdno in range(0, len(cond1)):
		if cond1[cdno] == cond2[cdno]:
			commcond.append(cond1[cdno])
		elif cond1[cdno][0] == cond2[cdno][0]:
			conddiff += 1
		else:
			return en1+ln2
	if conddiff != 1:
		return en1+ln2
	# Find identical lines at beginning	
	diffst = 0
	while diffst < ln1:
		if outl[st1+diffst][0].strip() != outl[en1+diffst][0].strip() \
		or outl[st1+diffst][1] != cond1	\
		or outl[en1+diffst][1] != cond2 :
			#print "DIFF @ %i: %s vs %s" \
			#	% (diffst, outl[st1+diffst][0], outl[en1+diffst][0]),
			break
		diffst += 1
	# Find identical lines at end
	diffen = 0
	while diffen < ln1:
		if outl[en1-1-diffen][0].strip() != outl[en1+ln2-1-diffen][0].strip() \
		or outl[en1-1-diffen][1] != cond1 \
		or outl[en1+ln2-1-diffen][1] != cond2 :
			break
		diffen += 1
	if not diffst and not diffen > 1:
		return en1+ln2
	# Debug
	if 0:	
		print "Performing consolidation: %s, %s -> %s, st %i en %i" \
			% (cond1, cond2, commcond, diffst, diffen)
		for lno in range(st1, en1+ln2):
			if lno < st1+diffst:
				print 'C:',
			elif en1-diffen <= lno < en1:
				print 'c:',
			elif st1 <= lno < en1:
				print '1:',
			elif en1 <= lno < en1+diffst:
				print 'C:',
			elif en1+ln2-diffen <= lno:
				print 'c:',
			else:
				print '2:',
			print outl[lno][0],
	# Rewrite common condition
	for lno in range(st1, st1+diffst):
		outl[lno][1] = commcond
	for lno in range(en1-diffen, en1):
		outl[lno][1] = commcond
	# Save different core 2	
	lns = outl[en1+diffst:en1+ln2-diffen]
	# and remove completely
	del outl[en1:en1+ln2]
	# and reinsert at right place
	outl[en1-diffen:en1-diffen] = lns
	# debug
	if 0:
		for lno in range(st1, en1+ln2-diffst-diffen):
			print "   %s" % outl[lno][0],
	return en1+ln2-diffst-diffen


def sortoutlines(outl):
	"""Look for duplicate function defs and put them next
	   to each other."""
	lno = 0
	while lno < len(outl):
		lno = skipcomm(outl, lno)
		parsestr = lookahead(outl, lno)
		if not parsestr:
			lno += 1
			continue
		if '{' in parsestr:
			fnname = searchfnname(parsestr)
			endln = findendfn(outl, lno)
			if not fnname:
				lno = endln
				continue
			(altstartln, altendln) = searchaltfn(outl, endln, fnname)
			if (altendln):
				lno = copyrange(outl, lno, endln, 
						altstartln, altendln)
			else:
				lno = endln
		else:
			lno += 1

def copylist(lst):
	"Deep copy a list of two-element records"
	newlst = []
	for elem in lst:
		newlst.append([elem[0], elem[1]])
	return newlst

def process(innm, outnm):
	"Read infile, parse conditionals #if(n)def, process and write out again"
	infile = open(innm, "r")
	inlines = infile.readlines()
	infile.close()
	outlines = []
	ifdefs = []
	ifdefre = re.compile(r'[ 	]*#[ 	]*ifdef[ 	]*([^/]*)')
	ifndefre = re.compile(r'[ 	]*#[ 	]*ifndef[ 	]*([^/]*)')
	ifre = re.compile(r'[ 	]*#[ 	]*if[ 	]*([^/]*)')
	elsere = re.compile(r'[ 	]*#[ 	]*else')
	endifre = re.compile(r'[ 	]*#[ 	]*endif')
	for line in inlines:
		match = ifdefre.match(line)
		if match:
			ifdefs.append([match.group(1).strip(), 1])
			continue
		match = ifndefre.match(line)
		if match:
			ifdefs.append([match.group(1).strip(), 0])
			continue
		match = ifre.match(line)
		if match:
			ifdefs.append([match.group(1).strip(), -1])
			continue
		if elsere.match(line):
			ifdefs[-1][1] = 1 - ifdefs[-1][1]
			continue
		if endifre.match(line):
			del ifdefs[-1]
			continue
		outlines.append([line, copylist(ifdefs)])
		
	if len(ifdefs):
		print >> sys.stderr, "Unbalanced ifdefs!"
		sys.exit(3)

	sortoutlines(outlines)
	outfile = open(outnm, 'w')
	for lno in range(0, len(outlines)):
		(line, defs) = outlines[lno]
		if ifdefs != defs and not line.strip():
			if len(defs) > len(ifdefs):
				defs = ifdefs
			elif lno < len(outlines)-1:
				defs = outlines[lno+1][1]
		if ifdefs != defs:
			changeifdefs(outfile, ifdefs, defs)
			ifdefs = defs
		outfile.write(line)
	changeifdefs(outfile, ifdefs, [])
	outfile.close()	

# MAIN
def main(args):
	"Parse args and process() them ..."
	global indentifdef
	if len(args) == 4 and args[1] == '-n':
		indentifdef = 0
		ifile = args[2]
		ofile = args[3]
	elif len(args) == 3:
		ifile = args[1]
		ofile = args[2]
	else:
		usage()
		
	if ifile == ofile:
		print >> sys.stderr, "Input and output should be different"
	if not os.access(ifile, os.R_OK):
		print >> sys.stderr, "Can't read from %s" % ifile
		sys.exit(1)
#	if not os.access(ofile, os.W_OK):
#		print >>sys.stderr, "Can't write to  %s" % ofile
#		sys.exit(1)

	process(ifile, ofile)


if __name__ == '__main__':
	main(sys.argv)

