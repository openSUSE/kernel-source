VER = 2.0
DIR = kernel-build-howto-$(VER)

FILES = tar -cf - --exclude=CVS --exclude='.*.flags' --exclude='*.o' hello
all : $(DIR).tar.gz

$(DIR).tar.gz : dir
	tar cfz $@ --exclude=CVS --exclude='.*.flags' --exclude='*.o' \
		$(DIR)/README.SUSE $(DIR)/hello

dir:
	rm -f $(DIR)
	ln -s . $(DIR)

clean:
	rm -f $(DIR) $(DIR).tar.gz
