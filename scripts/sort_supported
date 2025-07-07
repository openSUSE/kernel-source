#!/usr/bin/ruby

def max x, y
	(x >= y) ? x : y
end

class String
	def tablen
		(length + 8) / 8
	end
	def tabfill tabs
		self + "\t" * (tabs - (length / 8))
	end
	def ** other
		star = nil
		star = length - 1 if self[length - 1] == '*'
		star = other.length - 1 if other[other.length - 1] == '*'
		if star then
			if self[0...star] == other[0...star] then
				return 1 if star == length - 1
				return -1
			end
		end
		return self <=> other
	end
end

header = []
supported = []
maxtabs = [0,0]
maxlen = [0,0]

File.open("supported.conf"){|f|
	f.each_line{|l|
		l.chomp!
		l.gsub! %r<//>, '/'
		split = (l.match %r<^([^[:blank:]/]*)[[:blank:]]+(?:([^[:blank:]/]+)[[:blank:]]+)?(?:([^[:blank:]/]+)[[:blank:]]+)?([^[:blank:]]+/[^[:blank:]]+)(?:[[:blank:]]+(.*))?$>)
		if ! split then
			header << l
		else
			# [[flag, ..],module,comment,is_kmp]
			s = [[]]
			slash = false
			split[1..-1].each{|e|
				if slash then
					raise l + split.inspect if s[2]
					s[2] = e
				else
					if e =~ %r</> then
						slash = true
						s[1] = e
					else
						s[0] << e if e
						s[3] = true if e =~ /-kmp/
					end
				end
			}
			supported << s
			maxtabs[0] = max(maxtabs[0], s[0].join(" ").tablen)
			maxlen[0] = max(maxlen[0], s[0].join(" ").length)
			if s[2] then
				maxtabs[1] = max(maxtabs[1], s[1].tablen)
				maxlen[1] = max(maxlen[1], s[1].length)
			end
		end
	}
}

supported = supported.sort{|s1,s2|
	cmp = 0
	if s1[3] then
		if s2[3] then
			cmp = s1[0] <=> s2[0]
		else
			cmp = -1
		end
	elsif s2[3]
		cmp = 1
	end
	cmp != 0 ? cmp : s1[1] ** s2[1]
}

File.open("supported.conf",'wb'){|f|
	header.each{|l| f.puts l }
	supported.each{|s|
		f.puts s[0].join(" ").tabfill(maxtabs[0]) + (s[2] ? s[1].tabfill(maxtabs[1]) : s[1]) + s[2].to_s
	}
}
#STDERR.puts (0..maxlen[1]).each{|n| STDERR.puts ("a"*n).tabfill(maxtabs[1]) + "|"}
