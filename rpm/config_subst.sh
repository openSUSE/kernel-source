# Substitute CONFIG_ variables
config_subst() {
    awk '
	function subst(force)
	{
	    if (!done || force) {
		if (has_value)
		    print symbol "=" value
		else
		    print "# " symbol " is not set"
	    }
	    done=1
	}

	BEGIN           { symbol = ARGV[1]
			 if (ARGC == 3) {
			     has_value=1
			     value = ARGV[2]
			 }
			 split("", ARGV)
		        }
	match($0, "\\<" symbol "\\>") \
		        { subst(1) ; next }
		        { print }
	END             { subst(0) }
    ' "$@"
}
