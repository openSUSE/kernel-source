#!/usr/bin/env python

# Copyright (C) 2004 Andrea Arcangeli <andrea@suse.de> SUSE
# $Id: mkpatch.py,v 1.4 2004/11/23 07:14:38 andrea Exp $

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

import sys, os, re, readline

TAGS = (
	'From',
	'Subject',
	'Patch-mainline',
	'SUSE-Bugzilla-#',
	'SUSE-CVS-branches',
	)

DIFF_CMD = 'diff -urNp --exclude CVS --exclude BitKeeper --exclude {arch} --exclude .arch-ids --exclude .svn'
SIGNOFF_FILE = '~/.signedoffby'

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
	def __init__(self, patchfile):
		self.patchfile = patchfile
		self.prepare()
		self.read()

	def prepare(self):
		self.signedoffby = 'Signed-off-by: '
		self.ackedby = 'Acked-by: '

		readline.add_history(os.path.basename(self.patchfile))
		readline.add_history('HEAD, SLES9_SP1_BRANCH, SL92_BRANCH, SLES9_GA_BRANCH')
		readline.add_history('yes'); readline.add_history('no')

		self.my_signoff = None
		self.re_signoff = re.compile(self.signedoffby + r'(.*)', re.I)
		self.re_ackedby = re.compile(self.ackedby + r'(.*)', re.I)
		try:
			signoff = file(os.path.expanduser(SIGNOFF_FILE)).readline()
		except IOError:
			pass
		else:
			m = self.re_signoff.search(signoff)
			if m:
				self.my_signoff = m.group(1)
				readline.add_history(self.my_signoff)

		self.tags = []
		for tag in TAGS:
			self.tags.append(tag_class(tag))

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
			if signoff == self.my_signoff:
				prefix = self.signedoffby
			ret += prefix + signoff + '\n'
		if self.my_signoff not in self.signoff:
			ret += self.signedoffby + self.my_signoff + '\n'
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
		file(self.patchfile, 'w').write(tags + metadata + signoff + payload)

	def get_payload(self):
		return self.__payload

	def set_payload(self, value):
		self.__payload = cleanup_patch(value)

	payload = property(get_payload, set_payload)

def cleanup_patch(patch):
	diffline = re.compile(DIFF_CMD + r'.*')
	ret = ''
	for line in re.split('\n', patch):
		if line and not diffline.match(line):
			ret += line + '\n'
	return ret

def replace_diff(diff, patchfile):
	patch = patch_class(patchfile)
	patch.payload = diff
	patch.ask_empty_tags()
	patch.write()

def mkpatch(*arg):
	nr_arg = len(arg)
	def cleanup_path(arg):
		return map(os.path.normpath, map(os.path.expanduser, arg))
	if nr_arg > 3:
		raise 'EINVAL'
	elif nr_arg == 0:
		olddir = None
		newdir = os.getcwd()
		patchfile = None
	elif nr_arg == 1:
		olddir = None
		newdir, = cleanup_path(arg)
		patchfile = None
	elif nr_arg == 2:
		olddir = None
		newdir, patchfile = cleanup_path(arg)
	elif nr_arg == 3:
		olddir, newdir, patchfile = cleanup_path(arg)

	if olddir and not os.path.isdir(olddir):
		print >>sys.stderr, 'olddir must be a directory'
		raise 'EINVAL'
	if not os.path.isdir(newdir):
		print >>sys.stderr, 'newdir must be a directory'
		raise 'EINVAL'
	if patchfile and os.path.isdir(patchfile):
		olddir = newdir
		newdir = patchfile
		patchfile = None

	diff = ''
	if not olddir:
		# use backup files

		print >>sys.stderr, 'Searching backup files in %s ...' % newdir,
		find = os.popen('find %s -type f -name \*~ 2>/dev/null' % newdir, 'r')
		files = find.readlines()
		if files:
			print >>sys.stderr, 'done.'
		else:
			print >>sys.stderr, 'none found.'

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
	else:
		print >>sys.stderr, 'Creating diff between %s and %s ...' % (olddir, newdir),
		diff += os.popen(DIFF_CMD + ' %s %s' % (olddir, newdir) + ' 2>/dev/null', 'r').read()
		print >>sys.stderr, 'done.'

	if patchfile:
		replace_diff(diff, patchfile)
		os.execvp('vi', ('vi', '-c', 'set tw=72', patchfile, ))
	else:
		if diff:
			print cleanup_patch(diff),

if __name__ == '__main__':
	try:
		mkpatch(*sys.argv[1:])
	except 'EINVAL':
		print >>sys.stderr, 'Usage:', sys.argv[0], '[olddir] <newdir> [patch]'
