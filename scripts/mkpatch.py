#!/usr/bin/env python

# Copyright (C) 2004 Andrea Arcangeli <andrea@suse.de> SUSE
# $Id: mkpatch.py,v 1.9 2004/11/25 02:43:07 andrea Exp $

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

# You can copy or symlink this script into ~/bin and
# your ~/.signedoffby file should contain a string like this:
# "Signed-off-by: Andrea Arcangeli <andrea@suse.de>"

# Usage is intuitive like this:
#	./mkpatch.py # without parameter search the backup in current dir
#	./mkpatch.py dir2 # this search the backups in dir2
#	./mkpatch.py dir1 dir2
#	./mkpatch.py dir2 destination-patchfile
#	./mkpatch.py dir1 dir2 destination-patchfile
#	./mkpatch.py destination-patchfile # this will only parse patchfile

# There are three options: -n, -s, -a (alias respectively to
# --no-signoff, --signoff and --acked). If you're only rediffing
# the patch you can use '-n' to avoid altering the signoff list.
# If you're instead only reviewing the patch you can use '-a'
# to add an Acked-by, instead of a Signed-off-by. You can use
# bash alias with bash 'alias mkpatch.py=mkpatch.py -a' if you
# only review patches, or you can use -n instead if you only
# regenerate patches without even reviewing them. You can always
# force a signoff by using -a or -s. The last option mode overrides
# any previous signoff mode. The default is '-s' (aka '--signoff').

# If you miss the ~/.signedoffby file, '-n' (aka '--no-signoff')
# behaviour will be forced.

import sys, os, re, readline, getopt

TAGS = (
	'From',
	'Subject',
	'Patch-mainline',
	'Suse-bugzilla',
	)

DIFF_CMD = 'diff -urNp --exclude CVS --exclude BitKeeper --exclude {arch} --exclude .arch-ids --exclude .svn'
SIGNOFF_FILE = '~/.signedoffby'

class signoff_mode_class(object):
	signedoffby = 'Signed-off-by: '
	ackedby = 'Acked-by: '

	def __init__(self):
		self.mode = 0
		self.my_signoff = None
	def signoff(self):
		self.mode = 0
	def no_signoff(self):
		self.mode = 1
	def acked(self):
		self.mode = 2
	def is_acked(self):
		return self.mode == 2
	def is_signingoff(self):
		return self.mode == 0
	def is_enabled(self):
		return self.is_signingoff() or self.is_acked()
	def change_prefix(self, prefix, signoff):
		if self.my_signoff is None:
			return prefix
		if self.is_signingoff():
			if signoff == self.my_signoff:
				return self.signedoffby
		elif self.is_acked():
			if signoff == self.my_signoff:
				return self.ackedby
		return prefix

class tag_class(object):
	def __init__(self, name):
		self.name = name
		self.regexp = re.compile(name + r': (.*)', re.I)
		self.value = ''

	def parse(self, line):
		m = self.regexp.match(line)
		if m:
			self.value = m.group(1)
			return 1

	def ask_value(self):
		self.value = raw_input('%s: ' % self.name)

class patch_class(object):
	def __init__(self, patchfile, signoff_mode):
		self.patchfile = patchfile
		self.signoff_mode = signoff_mode
		self.prepare()
		self.read()

	def prepare(self):
		readline.add_history(os.path.basename(self.patchfile))
		readline.add_history('yes'); readline.add_history('no')

		my_signoff = None
		self.re_signoff = re.compile(self.signoff_mode.signedoffby + r'(.*)', re.I)
		self.re_ackedby = re.compile(self.signoff_mode.ackedby + r'(.*)', re.I)
		try:
			signoff = file(os.path.expanduser(SIGNOFF_FILE)).readline()
		except IOError:
			pass
		else:
			m = self.re_signoff.search(signoff)
			if m:
				my_signoff = m.group(1)
				readline.add_history(my_signoff)

		if not my_signoff:
			self.signoff_mode.no_signoff()
		else:
			self.signoff_mode.my_signoff = my_signoff

		self.tags = []
		for tag in TAGS:
			self.tags.append(tag_class(tag))

		self.signedoffby = self.signoff_mode.signedoffby
		self.ackedby = self.signoff_mode.ackedby

	def parse_metadata(self, line):
		# grab bk metadata and convert into valid header
		m = self.re_signoff.search(line)
		prefix = self.signedoffby
		if not m:
			prefix = self.ackedby
			m = self.re_ackedby.search(line)
		if m:
			this_signoff = m.group(1)
			if this_signoff not in self.signoff:
				self.signoff[this_signoff] = prefix
			return

		for tag in self.tags:
			if tag.parse(line):
				return 1

	def read(self):
		self.metadata = ''
		self.signoff = {}
		self.signoff_order = []
		self.__payload = ''

		try:
			patch = file(self.patchfile, 'r')
		except IOError:
			pass
		else:
			re_index = re.compile(r'Index: .*')
			re_bk = re.compile(r'=====.*vs.*=====')
			re_diff = re.compile(r'diff .*')
			re_plus = re.compile(r'--- .*')
			re_empty = re.compile(r'^\s*$')

			re_signoff = self.re_signoff
			re_ackedby = self.re_ackedby

			emptylines = ''
			first = 1
			state = 'is_metadata'
			while 1:
				line = patch.readline()
				if not line:
					break

				if re_diff.match(line) or re_plus.match(line) or \
				       re_index.match(line) or re_bk.match(line):
					state = 'is_payload'
				elif state == 'is_metadata' and (re_signoff.match(line) or
								 re_ackedby.match(line)):
					state = 'is_signoff'

				if state == 'is_metadata':
					if re_empty.search(line):
						emptylines += '\n'
					else:
						if not self.parse_metadata(line):
							if first:
								emptylines = ''
								first = 0
							self.metadata += emptylines + line
							emptylines = ''
				elif state == 'is_signoff':
					m = self.re_signoff.match(line)
					prefix = self.signedoffby
					if not m:
						prefix = self.ackedby
						m = self.re_ackedby.match(line)
					if m:
						this_signoff = m.group(1)
						if this_signoff not in self.signoff:
							self.signoff[this_signoff] = prefix
							self.signoff_order.append(this_signoff)
				elif state == 'is_payload':
					self.__payload += line
				else:
					raise 'unknown state'

	def ask_empty_tags(self):
		for tag in self.tags:
			if not tag.value:
				tag.ask_value()

	def get_tags(self):
		ret = ''
		for tag in self.tags:
			if tag.value:
				ret += tag.name + ': ' + tag.value + '\n'
		return ret

	def get_signoff(self):
		ret = ''
		for signoff in self.signoff_order:
			prefix = self.signoff[signoff]
			prefix = self.signoff_mode.change_prefix(prefix, signoff)
			ret += prefix + signoff + '\n'
		my_signoff = self.signoff_mode.my_signoff
		if self.signoff_mode.is_enabled() and \
		       my_signoff and my_signoff not in self.signoff:
			prefix = self.signoff_mode.change_prefix(None, my_signoff)
			ret += prefix + my_signoff + '\n'
		return ret

	def write(self):
		tags = self.get_tags()
		if tags:
			tags += '\n'
		metadata = self.metadata
		if metadata:
			metadata += '\n'
		signoff = self.get_signoff()
		if signoff:
			signoff += '\n'
		payload = self.payload
		try:
			os.unlink(self.patchfile) # handle links
		except OSError:
			pass
		file(self.patchfile, 'w').write(tags + metadata + signoff + payload)

	def get_payload(self):
		return self.__payload

	def set_payload(self, value):
		if value is not None:
			self.__payload = cleanup_patch(value)

	payload = property(get_payload, set_payload)

def cleanup_patch(patch):
	diffline = re.compile(DIFF_CMD + r'.*')
	ret = ''
	for line in re.split('\n', patch):
		if line and not diffline.match(line):
			ret += line + '\n'
	return ret

def replace_diff(diff, patchfile, signoff_mode):
	patch = patch_class(patchfile, signoff_mode)
	patch.payload = diff
	patch.ask_empty_tags()
	patch.write()

def mkpatch(*args):
	# parse opts
	try:
		opts, args = getopt.getopt(args, 'nas', ( 'no-signoff', 'acked', 'signoff', ))
	except getopt.GetoptError:
		raise 'EINVAL'
	signoff_mode = signoff_mode_class()
	for opt, arg in opts:
		if opt in ('-n', '--no-signoff', ):
			signoff_mode.no_signoff()
		elif opt in ('-a', '--acked', ):
			signoff_mode.acked()
		elif opt in ('-s', '--signoff', ):
			signoff_mode.signoff()

	# parse args
	nr_args = len(args)
	def cleanup_path(args):
		return map(os.path.normpath, map(os.path.expanduser, args))
	if nr_args > 3:
		raise 'EINVAL'
	elif nr_args == 0:
		olddir = None
		newdir = '.'
		patchfile = None
	elif nr_args == 1:
		olddir = None
		newdir, = cleanup_path(args)
		patchfile = None
	elif nr_args == 2:
		olddir = None
		newdir, patchfile = cleanup_path(args)
	elif nr_args == 3:
		olddir, newdir, patchfile = cleanup_path(args)

	#print olddir, newdir, patchfile
	if olddir and not os.path.isdir(olddir):
		print >>sys.stderr, 'olddir must be a directory'
		raise 'EINVAL'
	elif not os.path.isdir(newdir):
		if not os.path.isfile(newdir):
			print >>sys.stderr, 'newdir must be a directory or a file'
			raise 'EINVAL'
		olddir, newdir, patchfile = (None, None, newdir, )
	elif patchfile and os.path.isdir(patchfile):
		olddir = newdir
		newdir = patchfile
		patchfile = None
	#print olddir, newdir, patchfile

	diff = None
	if not olddir and newdir:
		# use backup files
		print >>sys.stderr, 'Searching backup files in %s ...' % newdir,
		find = os.popen('find %s -type f -name \*~ 2>/dev/null' % newdir, 'r')
		files = find.readlines()
		if files:
			print >>sys.stderr, 'done.'
		else:
			print >>sys.stderr, 'none found.'

		diff = ''
		for backup_f in files:
			new_f = None
			backup_f = backup_f[:-1]
			if backup_f[-4:] == '.~1~':
				new_f = backup_f[:-4]
			elif backup_f[-1:] == '~':
				new_f = backup_f[:-1]
			if not os.path.isfile(new_f):
				continue

			if new_f:
				print >>sys.stderr, 'Diffing %s...' % new_f,
				diff += os.popen(DIFF_CMD + ' %s %s' % (backup_f, new_f) + ' 2>/dev/null').read()
				print >>sys.stderr, 'done.'
	elif olddir and newdir:
		# use two directories
		print >>sys.stderr, 'Creating diff between %s and %s ...' % (olddir, newdir),
		diff = os.popen(DIFF_CMD + ' %s %s' % (olddir, newdir) + ' 2>/dev/null', 'r').read()
		print >>sys.stderr, 'done.'

	if patchfile:
		replace_diff(diff, patchfile, signoff_mode)
		os.execvp('vi', ('vi', '-c', 'set tw=72', patchfile, ))
	else:
		if diff:
			print cleanup_patch(diff),

if __name__ == '__main__':
	try:
		mkpatch(*sys.argv[1:])
	except 'EINVAL':
		print >>sys.stderr, 'Usage:', sys.argv[0], \
		      '[-a|--acked] [-n|--no-signoff] [-s|--signoff] [olddir] [newdir] [patch]'
