#!/usr/bin/env python
# ksyms.py
# 
# Extracts symbols from kernel and kernel modules
# and creates 3 lists: used, unused, unresolved.
# Operates on installed kernels or RPMs for the collection.
# The --quickcollect mode does basically only extract the
# symvers file.
# Optionally can be used to test additional modules to test
# whether they can be loaded into a kernel (RPM).
#
# (c) Kurt Garloff <garloff@suse.de>, 2005-06-22, GNU GPL
#
# $Id: ksyms.py,v 1.6 2005/06/23 09:39:50 garloff Exp $

import os, sys, re, getopt, shutil

# Helper functions
def rmv_left(str, sub):
	"If str starts with sub, remove it"
	ln = len(sub)
	if str[:ln] == sub:
		return str[ln:]
	else:
		return str

def rmv_right(str, sub):
	"If str ends with sub, remove it"
	ln = len(sub)
	if str[-ln:] == sub:
		return str[:-ln]
	else:
		return str

def rmv_re_left(str, regexp):
	"If regexp matches the left end of str, remove match"
	match = regexp.match(str)
	if match:
		return str[len(match.group(0)):]
	else:
		return str

def rmv_re_right(str, regexp):
	"If regexp matches the right end of str, remove match"
	match = regexp.search(str)
	if match:
		return str[:-len(match.group(0))]
	else:
		return str

def match_left(str1, str2):
	"Tests whether str1 starts with str2"
	if str1[:len(str2)] == str2:
		return True 
	else:
		return False

def match_right(str1, str2):
	"Tests whether str1 ends with str2"
	if str1[-len(str2):] == str2:
		return True 
	else:
		return False

# Conversion of kernel vs rpm versions
def parse_rver(rver):
	"Extracts kernel flavour and version no from rpmname"
	rver = rver.strip()
	kver = rmv_re_left(rver, re.compile(r'.*/kernel-'))
	kver = rmv_re_right(kver, re.compile(r'\.[^\.]*.rpm$'))
	kvnum = rmv_re_left(kver, re.compile(r'[^-]*-'))
	kvflav = kver[:-len(kvnum)-1]
	return (kvflav, kvnum)

def parse_kver(kver):
	"Extracts kernel flavour and version no from kernel version"
	kver = kver.strip()
	rvnum = rmv_re_right(kver, re.compile(r'-[^0-9][^-]*$'))
	rvflav = kver[len(rvnum)+1:]
	return (rvflav, rvnum)
	
def rpmver_to_kver(rver):
	"Convert rpmname to kernelver"
	(kvflav, kvnum) = parse_rver(rver)
	return kvnum + '-' + kvflav

def kver_to_rpmver(kver):
	"Shuffles kernel version to make it an rpm name component"
	(rvflav, rvnum) = parse_kver(kver)
	return rvflav + '-' + rvnum

# Remove unneeded filename components
def sanitize_name(str):
	"Shorten path names for kernel modules and image"
	str = rmv_left(str, '/boot/')
	str = rmv_left(str, '/lib/modules/')
	str = rmv_re_left(str, re.compile(r'[0-9]*\.[^/]*/'))
	str = rmv_right(str, '.ko')
	str = rmv_right(str, '.o')
	return str

def test_access(fname, mode = os.R_OK):
	"Tests whether a file can be accessed"
	if not os.access(fname, mode):
		m = 'r'
		if mode != os.R_OK:
			m = 'w'
		try:
			fd = open(fname, m)
		except IOError, err:
			print >>sys.stderr, "access(\"%s\"): %s" % \
				(fname, err.strerror)
			raise 

def get_tmpdir(exist_ok = 0):
	import random, time
	if os.environ.has_key('TMPDIR'):
		tmpdir = os.environ['TMPDIR']
	else:
		tmpdir = '/tmp'
	test_access(tmpdir, os.W_OK)
	random.seed(time.time() + os.getpid())
	tmpdir += "/ksyms-%i" % random.randint(100000,999999)
	if not exist_ok and os.access(tmpdir, os.R_OK):
		try:
			unlink(tmpdir)
		except:
			pass
		try:
			shutil.rmtree(tmpdir)
			#rmdir(tmpdir)
		except:
			pass
	if not exist_ok and os.access(tmpdir, os.R_OK):
		print >>sys.stderr, "Can't remove %s, bailing out" % tmpdir
		sys.exit(4)
	try:	
		os.mkdir(tmpdir, 0755)
	except:
		pass
	return tmpdir

# data structure for symbol lists (dicts)
# key = name, value = pair of version and src file 
def collect_syms_from_obj26file(fname, defd, undefd, path = ''):
	"Get symbol versions from a .ko file"
	test_access(fname)
	shortnm = sanitize_name(rmv_left(fname, path))
	tmpdir = ''
	if match_right(fname, ".gz"):
		tmpdir = get_tmpdir(1)
		shutil.copyfile(fname, "%s/%s" % (tmpdir, shortnm))
		fd = os.popen('gunzip %s/%s' % (tmpdir, shortnm))
		fd.close()
		shortnm = rmv_right(shortnm, ".gz")
		fd = os.popen('nm %s/%s' % (tmpdir, shortnm))
		rmname = shortnm
		shortnm = rmv_re_right(shortnm, re.compile(r'-2\..*'))
	else:	
		fd = os.popen('nm %s' % fname, 'r')
	# crc=$(echo "$syms" | grep __crc_ | sed "s%^\(00000000\|\)\([0-9a-f]*\) . __crc_\(.*\)$%\3\t\2\t${name}%")
	crc = re.compile(r'([0-9a-fA-F]*) A __crc_(.*)$')
	need = re.compile(r' *[uU] (.*)$')
	#need=$(echo "$syms" | grep '^ *[uU]' | sed "s%^ *[uU] \(.*\)$%\1%")

	miss = []
	for ln in fd.readlines():
		ln = ln.strip()
		match = crc.match(ln)
		if match:
			sym = match.group(2)
			ver = match.group(1)
			#ver = '00000000' + rmv_left(ver, '0x')
			ver = ver[-8:]
			if defd.has_key(sym):
				if defd[sym].has_key(ver):
					if not shortnm in defd[sym][ver].split(','):
						print >>sys.stderr, "WARNING: Symbol %s in both %s and %s" % (sym, defd[sym][ver], shortnm)
						defd[sym][ver] += ',%s' % shortnm
				else:
					print >>sys.stderr, "ERROR: Mismatch for symbol %s" % sym
					for key in defd[sym].keys():
						print >>sys.stderr, " Previous ver %s from %s" \
							% (key, defd[sym][key])
					print >>sys.stderr, " Current  ver %s from %s" \
						% (ver, shortnm)
					defd[sym][ver] = shortnm
			else:
				defd[sym] = {ver: shortnm}
			continue
		match = need.match(ln)
		if match:
			miss.append(match.group(1))
	fd.close()
	# objdump -j __versions -s
	# Records are 64 byte, an unsigned long crc followed by the name
	# much easier: modprobe --dump-modversions
	if miss:
		fd = os.popen('/sbin/modprobe --dump-modversions %s' % fname, 'r')
		for ln in fd.readlines():
			ln = ln.strip()
			(ver, nm) = ln.split()
			ver = '00000000' + rmv_left(ver, '0x')
			ver = ver[-8:]
			if undefd.has_key(nm):
				if undefd[nm].has_key(ver):
					if not shortnm in undefd[nm][ver].split(','):
						undefd[nm][ver] += ',%s' % shortnm
				else:
					print >>sys.stderr, "ERROR: Mismatch for symbol %s" % nm
					for key in undefd[nm].keys():
						print >>sys.stderr, " Ver %s needed by %s" \
						% (key, undefd[nm][key])
					print >>sys.stderr, " Ver %s needed by %s" \
						% (ver, shortnm)
					undefd[nm][ver] = shortnm
			else:
				undefd[nm] = {ver: shortnm}
		fd.close()
	# We could in theory check that we found all symbols from miss,
	# no more and no less
	# We could also take care of not overwriting already existing
	# undefd entries ...
	for sym in miss:
		if not undefd.has_key(sym):
			# Should NOT happen on 2.6, where all syms are versioned
			print >>sys.stderr, 'ERROR: sym %s undefined, but no version found' \
					% sym
			undefd[sym] = {'00000000': shortnm}
	if tmpdir:
		try:
			os.unlink(tmpdir + '/' + rmname)
			os.rmdir(tmpdir)
		except:
			pass

def collect_syms_from_obj24file(fname, defd, undefd, path = ''):
	"Get symbol versions from a .o file"
	test_access(fname)
	shortnm = sanitize_name(rmv_left(fname, path))
	tmpdir = ''
	if match_right(fname, ".gz"):
		tmpdir = get_tmpdir(1)
		shutil.copyfile(fname, "%s/%s" % (tmpdir, shortnm))
		fd = os.popen('gunzip %s/%s' % (tmpdir, shortnm))
		fd.close()
		shortnm = rmv_right(shortnm, ".gz")
		fd = os.popen('nm %s/%s' % (tmpdir, shortnm))
		rmname = shortnm
		shortnm = rmv_re_right(shortnm, re.compile(r'-2\..*'))
	else:	
		fd = os.popen('nm %s' % fname, 'r')
	# crc=$(echo "$syms" | grep __crc_ | sed "s%^\(00000000\|\)\([0-9a-f]*\) . __crc_\(.*\)$%\3\t\2\t${name}%")
	strtab = re.compile(r'[0-9a-fA-F]* R __kstrtab_(.*)$')
	versre = re.compile(r'(.*)_R([0-9a-fA-F]*)$')
	need   = re.compile(r' *[uU] (.*)$')
	#need=$(echo "$syms" | grep '^ *[uU]' | sed "s%^ *[uU] \(.*\)$%\1%")

	for ln in fd.readlines():
		ln = ln.strip()
		match = strtab.match(ln)
		if match:
			sym = match.group(1)
			m2 = versre.match(sym)
			if m2:
				sym = m2.group(1)
				ver = m2.group(2)
			else:
				ver = '00000000'
			#ver = '00000000' + rmv_left(ver, '0x')
			#ver = ver[-8:]
			if defd.has_key(sym):
				if defd[sym].has_key(ver):
					if not shortnm in defd[sym][ver].split(','):
						print >>sys.stderr, "WARNING: Symbol %s in both %s and %s" % (sym, defd[sym][ver], shortnm)
						defd[sym][ver] += ',%s' % shortnm
				else:
					print >>sys.stderr, "ERROR: Mismatch for symbol %s" % sym
					for key in defd[sym].keys():
						print >>sys.stderr, " Previous ver %s from %s" \
							% (key, defd[sym][key])
					print >>sys.stderr, " Current  ver %s from %s" \
						% (ver, shortnm)
					defd[sym][ver] = shortnm
			else:
				defd[sym] = {ver: shortnm}
			continue
		match = need.match(ln)
		if match:
			sym = match.group(1)
			m2 = versre.match(sym)
			if m2:
				sym = m2.group(1)
				ver = m2.group(2)
			else:
				ver = '00000000'
			if undefd.has_key(sym):
				if undefd[sym].has_key(ver):
					if not shortnm in undefd[sym][ver].split(','):
						undefd[sym][ver] += ',%s' % shortnm
				else:
					print >>sys.stderr, "ERROR: Mismatch for symbol %s" % sym
					for key in undefd[sym].keys():
						print >>sys.stderr, " Ver %s needed by %s" \
						% (key, undefd[sym][key])
					print >>sys.stderr, " Ver %s needed by %s" \
						% (ver, shortnm)
					undefd[sym][ver] = shortnm
			else:
				undefd[sym] = {ver: shortnm}
	fd.close()
	if tmpdir:
		try:
			os.unlink(tmpdir + '/' + rmname)
			os.rmdir(tmpdir)
		except:
			pass


def collect_syms_from_symverfile(fname, defd, undefd):
	"Parse symvers file"
	import gzip
	kver = ''
	test_access(fname)
	if match_right(fname, '.gz'):
		fd = gzip.GzipFile(fname, 'r')
	else:
		fd = open(fname, 'r')
	tagged = re.compile(r'([^:]*): *(.*)$')
	lst = defd
	for ln in fd.readlines():
		ln = ln.strip()
		match = tagged.match(ln)
		if match:
			if match.group(1) == 'Kernel':
				kver = match.group(2)
			elif match.group(1) == 'Used symbols':
				lst = defd
			elif match.group(1) == 'Unused symbols':
				lst = defd
			elif match.group(1) == 'Unresolved symbols':
				lst = undefd
			continue	
		(ver, sym, loc) = ln.split()
		ver = '00000000' + rmv_left(ver, '0x')
		ver = ver[-8:]
		# for modules, we lack the kernel/ part of the
		# path, readd it, where appropriate
		# not needed if reading our own output files
		if not kver:
			locopy = loc
			loc = ''
			for lo in locopy.split(','):
				if match_left(lo, 'vmlinu') \
				or match_left(lo, 'extra') \
				or match_left(lo, 'misc') \
				or match_left(lo, 'pcmcia') \
				or match_left(lo, 'update') \
				or match_left(lo, 'override') \
				or match_left(lo, 'ncs') \
				or match_left(lo, 'nss'):
					loc += '%s,' % lo
				else:
					loc += 'kernel/%s,' % lo
			loc = rmv_right(loc, ',')
		
		if lst.has_key(sym):
			if lst[sym].has_key(ver):
				lst[sym][ver] += ',%s' % loc
			else:
				print >>sys.stderr, "ERROR: Mismatch for symbol %s:" % sym
				for key in lst[sym].keys():
					print >>sys.stderr, " Previous ver %s from %s" \
						% (key, lst[sym][key])
				print >>sys.stderr, " Current  ver %s from %s" \
						% (ver, shortnm)
				lst[sym][ver] = loc
		else:
			lst[sym] = {ver: loc}
	fd.close()
	return kver

def collect_installed_kernel26(version, defd, undefd, path = '', quick = 0):
	"Get symbol versions for a 2.6 kernel"
	import glob
	global modules
	modules = 0
	(verflav, vernum) = parse_kver(version)
	symverfile = path + '/boot/symvers-%s*-%s*' % (vernum, verflav)
	symverfiles = glob.glob(symverfile)
	if len(symverfiles) != 1:
		print >>sys.stderr, "ERROR: Expected one match for %s" % symverfile
		print >>sys.stderr, " Found %s" % symverfiles
		sys.exit(1)
	collect_syms_from_symverfile(symverfiles[0], defd, undefd)

	if quick:
		return modules

	if 0:
		collect_syms_from_obj26file(path + '/boot/vmlinux-%s-%s.gz' % (vernum, verflav),
			defd, undefd, path)

	test_access('%s/lib/modules/%s' % (path, version))
	fd = os.popen('find %s/lib/modules/%s -name *.ko' % (path, version), 'r')
	for nm in fd.readlines():
		nm = nm.strip()
		collect_syms_from_obj26file(nm, defd, undefd, path)
		modules += 1
	fd.close()
	return modules

def collect_installed_kernel24(version, defd, undefd, path = '', quick = 0):
	"Get symbol versions for a 2.4 kernel"
	import glob
	global modules
	modules = 0
	(verflav, vernum) = parse_kver(version)
	# FIXME: There is probably no symvers in 2.4
	if 0:
		symverfile = path + '/boot/symvers-%s*-%s*' % (vernum, verflav)
		symverfiles = glob.glob(symverfile)
		if len(symverfiles) != 1:
			print >>sys.stderr, "ERROR: Expected one match for %s" % symverfile
			print >>sys.stderr, " Found %s" % symverfiles
			sys.exit(1)
		collect_syms_from_symverfile(symverfiles[0], defd, undefd)
	# FIXME: We should scan the kernel now ...
	collect_syms_from_obj24file(path + '/boot/vmlinux-%s-%s.gz' % (vernum, verflav),
			defd, undefd, path)

	# FIXME: Quick does not make sense on 2.4
	if quick:
		return modules
	test_access('%s/lib/modules/%s' % (path, version))
	fd = os.popen('find %s/lib/modules/%s -name *.o' % (path, version), 'r')
	for nm in fd.readlines():
		nm = nm.strip()
		collect_syms_from_obj24file(nm, defd, undefd, path)
		modules += 1
	fd.close()
	return modules

def extract_rpm(rpm, quick):
	import random, time
	test_access(rpm)
	tmpdir = get_tmpdir()
	cwd = os.getcwd()
	os.chdir(tmpdir)
	if quick:
		reg = re.compile(r'boot/symvers\-')
		fd = os.popen('rpm2cpio %s | cpio -t' % rpm, 'r')
		fn = ''
		for ln in fd.readlines():
			match = reg.search(ln)
			if match:
				fn = ln.strip()
		fd.close()
		if not fn:
			print >>sys.stderr, "ERROR: boot/symvers-* not found"
			return tmpdir
		stat = os.system('rpm2cpio %s | cpio -i -d -u -m %s' \
				% (rpm, fn))
		if stat:
			print >>sys.stderr, "ERROR: Extracting %s from %s failed (%i)" \
				% (fn, rpm, stat)
	else:	
		stat = os.system('rpm2cpio %s | cpio -i -d -u -m' % rpm)
		if stat:
			print >>sys.stderr, "ERROR: Extracting %s failed (%i)" \
				% (rpm, stat)
	return tmpdir

def deep_copy(defd, unused):
	"Deep copy of a dict of dicts"
	unused.update(defd)
	for sym in unused.keys():
		unused[sym] = defd[sym].copy()

def app_sym_ver(src, tgt, sym, ver):
	"Copy a dict key in a two level dict"
	if tgt.has_key(sym):
		tgt[sym][ver] = src[sym][ver]
	else:
		tgt[sym] = {ver: src[sym][ver]}

def del_sym_ver(tgt, sym, ver):
	"Del a dict key in a two level dict"
	del tgt[sym][ver]
	if not tgt[sym]:
		del tgt[sym]

def consolidate_syms(defd, undefd, used, unused, unresolved):
	"Create used, unused, unresolved lists from defd, undefd"
	deep_copy(defd, unused)
	for sym in undefd.keys():
		if defd.has_key(sym):
			for ver in undefd[sym].keys():
				if defd[sym].has_key(ver):
					app_sym_ver(defd, used, sym, ver)
					del_sym_ver(unused, sym, ver)
				else:
					app_sym_ver(undefd, unresolved, sym, ver)
		else:
			unresolved[sym] = undefd[sym].copy()

def output(dict, stripkern = 0):
	"Output sorted symbol list"
	ssyms = dict.keys()
	ssyms.sort()
	for sym in ssyms:
		svers = dict[sym].keys()
		svers.sort()
		for ver in svers:
			if stripkern:
				str = ''
				lst = dict[sym][ver].split(',')
				for nm in lst:
					str += rmv_left(nm, 'kernel/') + ','
				str = rmv_right(str, ',')
			else:
				str = dict[sym][ver]
			print "0x%s\t%s\t%s" % (ver, sym, str)

def count(dict):
	"Count symbols _and_ versions"
	ctr = 0
	for sym in dict.keys():
		for ver in dict[sym].keys():
			ctr += 1
	return ctr

def usage():
	"Print help"
	print "Usage: ksyms.py --collect={kversion, krpm}"
	print "       ksyms.py --quickcollect={kversion, krpm}"
	print "                Print a list of symbols, collected from an installed"
	print "                kernel specified by kversion or from a kernelrpm."
	print "                --collect scans all modules for used/unused and"
	print "                unresolved symbol versions; --quickcollect only"
	print "                collects the defined symbols from symvers, the"
	print "                output fmt is then the symvers fmt."
	print "                Unresolved symbol versions are considered an error"
	print "                and reflected in the exit code.\n"
	print "       ksyms.py --symbols=symlistfile --testmodule module[s]"
	print "       ksyms.py --[quick]collect={kversion, krpm} --testmodule module[s]"
	print "                Check for unresolved symbol versions in module[s]."
	print "                When specifying --symbols, it uses the symlistfile that"
	print "                has been generated and saved before by --[quick]collect"
	print "                before. It can also generate the list on the fly using"
	print "                --[quick]collect."
	print "                Unresolved symbols in module[s] will be considered an error"
	print "                which will be reflected by the exit code."
	print "                When the (non-quick) --collect option is used, unresolved"
	print "                symbols in other modules will also be considered an error."
	print "                Use --ignoreothermod to suppress this."
	print "Shortcuts: -c(ollect), -q(uickcollect), -s(symbols), -t(testmodule),"
	print "           -i(gnoreothermod)"
	sys.exit(2)


def collect_syms(arg, defd, undefd, quick = 0):
	"Read symbols from RPM or installed kernel"
	path = ''
	if match_right(arg, '.rpm'):
		path = extract_rpm(arg, quick)
		arg = rpmver_to_kver(arg)
	if match_left(arg, '2.4'):
		modules = collect_installed_kernel24(arg, defd, undefd, path, quick)
	else:	
		modules = collect_installed_kernel26(arg, defd, undefd, path, quick)
	if path:
		shutil.rmtree(path)
	return arg

# main
defd = {}; undefd = {}
used = {}; unused = {}; unresolved = {}

if len(sys.argv) < 2:
	usage()

longopts = ('collect=', 'quickcollect=', 'symbols=', 'ignoreothermod', 'testmodule', 'testmodules') 
try:
	(optlist, args) = getopt.getopt(sys.argv[1:], 'c:q:s:it', longopts)
except getopt.GetoptError:	
	usage()

collfile = ''; symfile = '' 
quick = 0; ignother = 0; testmod = 0; modules = 0

for (opt, arg) in optlist:
	if opt in ('-c', '--collect'):
		collfile = arg
		quick = 0
		continue
	if opt in ('-q', '--quickcollect'):
		collfile = arg
		quick = 1
		continue
	if opt in ('-s', '--symbols'):
		symfile = arg
		continue
	if opt in ('-i', '--ignoreothermod'):
		ignother = 1
		continue
	if opt in ('-t', '--testmodule', '--testmodules'):
		testmod = 1
		continue
	print >>sys.stderr, 'ERROR:	Internal option processing error %s' % opt
	sys.exit(2)

if args and not testmod:
	print >>sys.stderr, 'ERROR: Spurious arguments %s' % args
	usage()

if collfile and symfile:
	print >>sys.stderr, 'ERROR: Can\'t read symbols from binaries and list simultaneously'
	usage()

if testmod and not (symfile or collfile):
	print >>sys.stderr, 'ERROR: Need to specify a symbol source for --testmodule'
	usage()

if collfile:
	kver = collect_syms(collfile, defd, undefd, quick)

if symfile:
	kver = collect_syms_from_symverfile(symfile, defd, undefd)
	if not kver:
		quick = 1

if not testmod:
	if not (quick):
		consolidate_syms(defd, undefd, used, unused, unresolved)
		print 'Kernel: %s' % kver
		print 'Modules scanned: %i' % modules
		print 'Needed symbols: %i' % count(undefd)
		print 'Provided symbols: %i' % count(defd)
		print 'Used symbols: %i' % count(used)
		output(used)
		print 'Unused symbols: %i' % count(unused)
		output(unused)
		print 'Unresolved symbols: %i' % count(unresolved)
		output(unresolved)
		sys.exit(len(unresolved))
	else:
		output(defd, 1)
		sys.exit(0)

if ignother:
	undefd = {}

if kver:
	print 'Kernel: %s' % kver
print 'Test modules:',
for mod in args:
	print ' %s' % mod,
	collect_syms_from_obj26file(mod, defd, undefd)

print
consolidate_syms(defd, undefd, used, unused, unresolved)
if ignother or quick or symfile:
	print 'Used symbols: %i' % count(used)
	output(used)
print 'Unresolved symbols: %i' % count(unresolved)
output(unresolved)
sys.exit(len(unresolved))

