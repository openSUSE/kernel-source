KERNEL_BUILD  := /lib/modules/`uname -r`/build

# For building for a specific kernel flavor:
#KERNEL_BUILD := /usr/src/linux-obj/i386/default

# Directory below /lib/modules/`uname -r`/kernel into which to install
# the module(s):
#MOD_SUBDIR = misc

obj-m		:= hello.o
hello-y		+= main.o

# Do not print "Entering directory ..."
MAKEFLAGS += --no-print-directory

# Targets for running make directly in the external module directory:
modules modules_install clean:
	@$(MAKE) -C $(KERNEL_BUILD) M=$(CURDIR) $@
