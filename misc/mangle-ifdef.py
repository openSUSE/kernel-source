#!/usr/bin/env python
# 
# Mangles duplicate functions that are ifdef'd
# Useful to simplify include/linux/security.h (LSM hooks).
# 
# (c) Kurt Garloff <garloff@suse.de>, 2005-06-26, GNU GPL
#
# $Id: mangle-ifdef.py,v 1.5 2005/07/03 15:45:19 garloff Exp $
#

import os, sys, re

def usage():
	"Help"
	print >>sys.stderr, "Usage: mangle-ifdef.py INFILE OUTFILE"
	print >>sys.stderr, " This tool tries to put implementations of the same function"
	print >>sys.stderr, " with different preprocessor conditional next to each other"
	print >>sys.stderr, " for consolidation. Used for include/linux/security.h"
	sys.exit(2)


def writeendifs(outf, number, old):
	"Write #endifs to output file"
	for no in range(len(old)-1, len(old)-1-number, -1):
		outf.write('#%sendif /* %s */\n' 
			% (' '*no, old[no][0]))

def writeelse(outf, which, old):
	"Write #else to output file"
	outf.write('#%selse /* %s */\n'
		% (' '*which, old[which][0]))

def writeifdefs(outf, number, new):
	"Write #if(n)def to output file"
	for no in range(len(new)-number, len(new)):
		if new[no][1] == 1:
			outf.write('#%sifdef %s\n'
				% (' '*no, new[no][0]))
		elif new[no][1] == 0:
			outf.write('#%sifndef %s\n'
				% (' '*no, new[no][0]))
		else:
			outf.write('#%sif %s\n'
				% (' '*no, new[no][0]))

lastelse = ''
def changeifdefs(outf, olddefs, newdefs):
	"""When the conditions for the line changed, put necessary
	   conditionals in the output file"""
	global lastelse
	ln = min(len(olddefs), len(newdefs))
	diff = ln
	#print "Changedefs: %s -> %s" % (olddefs, newdefs)
	for no in range(0, ln):
		if newdefs[no] != olddefs[no]:
			diff = no
			break
	close = len(olddefs) - diff
	open = len(newdefs) - diff
	if diff < ln and newdefs[diff][0] == olddefs[diff][0] \
			and newdefs[diff][0] != lastelse:
		writeendifs(outf, close-1, olddefs)
		writeelse(outf, diff, olddefs)
		lastelse = newdefs[diff][0]
		writeifdefs(outf, open-1, newdefs)
	else:
		writeendifs(outf, close, olddefs)
		writeifdefs(outf, open, newdefs)
		lastelse = ''


def lookahead(outl, no):
	"Reads ahead until next ';' or '}' or '{'"
	str = ''
	for (ln, cond) in outl[no:]:
		str += ln
		if '}' in ln or ';' in ln or '{' in ln or '*/' in ln:
			return str

def skipcomm(outl, no):
	"Skip over defines and empty lines"
	if outl[no][0][0] == '#':
		while no < len(outl) and outl[no][0].strip()[-1] == '\\':
			no += 1
		return no+1
	#if '/*' in outl[no][0]:
	#	while no < len(outl) and '*/' not in outl[no][0]:
	#		no += 1
	#	return no
	while no < len(outl) and not outl[no][0].strip():
		no += 1
	return no

def searchaltfn(outl, no, fname):
	"Search for (another) definition of function fname"
	while no < len(outl):
		no = skipcomm(outl, no)
		parsestr = lookahead(outl, no)
		if not parsestr:
			no += 1
			continue
		if '{' in parsestr:
			fn = searchfnname(parsestr)
			if fn == fname:
				endln = findendfn(outl, no)
				return (no, endln)
		no += 1
	
	return (0,0)

def searchfnname(line):
	"Extract function name from concatenated line"
	fn = re.compile(r'\b(\w*)[ 	]*\(')
	m = fn.search(line)
	if m and not line[0] == '#':
		return m.group(1)
		
		
def findendfn(outl, no):
	"Find end of function starting in line no"
	eno = no
	ilevel = 0
	body = 0
	while eno < len(outl):
		ilevel += outl[eno][0].count('{')
		if ilevel:
			body = 1
		ilevel -= outl[eno][0].count('}')
		eno += 1
		if body and ilevel <= 0:
			return eno
			
	print >>sys.stderr, "Unbalanced braces"
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
		for ln in range(st1, en1+ln2):
			if ln < st1+diffst:
				print 'C:',
			elif en1-diffen <= ln < en1:
				print 'c:',
			elif st1 <= ln < en1:
				print '1:',
			elif en1 <= ln < en1+diffst:
				print 'C:',
			elif en1+ln2-diffen <= ln:
				print 'c:',
			else:
				print '2:',
			print outl[ln][0],
	# Rewrite common condition
	for ln in range(st1, st1+diffst):
		outl[ln][1] = commcond
	for ln in range(en1-diffen, en1):
		outl[ln][1] = commcond
	# Save different core 2	
	lns = outl[en1+diffst:en1+ln2-diffen]
	# and remove completely
	del outl[en1:en1+ln2]
	# and reinsert at right place
	outl[en1-diffen:en1-diffen] = lns
	# debug
	if 0:
		for ln in range(st1, en1+ln2-diffst-diffen):
			print "   %s" % outl[ln][0],
	return en1+ln2-diffst-diffen


def sortoutlines(outl):
	"""Look for duplicate function defs and put them next
	   to each other."""
	no = 0
	while no < len(outl):
		no = skipcomm(outl, no)
		parsestr = lookahead(outl, no)
		if not parsestr:
			no += 1
			continue
		if '{' in parsestr:
			fnname = searchfnname(parsestr)
			endln = findendfn(outl, no)
			if not fnname:
				no = endln
				continue
			(altstartln, altendln) = searchaltfn(outl, endln, fnname)
			if (altendln):
				no = copyrange(outl, no, endln, altstartln, altendln)
			else:
				no = endln
		else:
			no += 1

def copylist(lst):
	"Deep copy a list of two-element records"
	newlst = []
	for el in lst:
		newlst.append([el[0], el[1]])
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
		m = ifdefre.match(line)
		if m:
			ifdefs.append([m.group(1).strip(), 1])
			continue
		m = ifndefre.match(line)
		if m:
			ifdefs.append([m.group(1).strip(), 0])
			continue
		m = ifre.match(line)
		if m:
			ifdefs.append([m.group(1).strip(), -1])
			continue
		if elsere.match(line):
			ifdefs[-1][1] = 1 - ifdefs[-1][1]
			continue
		if endifre.match(line):
			del ifdefs[-1]
			continue
		outlines.append([line, copylist(ifdefs)])
		
	if len(ifdefs):
		print >>stderr, "Unbalanced ifdefs!"
		sys.exit(3)

	sortoutlines(outlines)
	outfile = open(outnm, 'w')
	for no in range(0, len(outlines)):
		(ln, defs) = outlines[no]
		if ifdefs != defs and not ln.strip():
			if len(defs) > len(ifdefs):
				defs = ifdefs
			elif no < len(outlines)-1:
				defs = outlines[no+1][1]
		if ifdefs != defs:
			changeifdefs(outfile, ifdefs, defs)
			ifdefs = defs
		outfile.write(ln)
	changeifdefs(outfile, ifdefs, [])
	outfile.close()	

# MAIN
if len(sys.argv) != 3:
	usage()
	
if sys.argv[1] == sys.argv[2]:
	print >>sys.stderr, "Input and output should be different"
if not os.access(sys.argv[1], os.R_OK):
	print >>sys.stderr, "Can't read from %s" % sys.argv[1]
	sys.exit(1)
#if not os.access(sys.argv[2], os.W_OK):
#	print >>sys.stderr, "Can't write to  %s" % sys.argv[2]
#	sys.exit(1)
	
process(sys.argv[1], sys.argv[2])
	


