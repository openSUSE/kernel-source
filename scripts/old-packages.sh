#! /bin/bash

for arch in $(scripts/arch-symbols --list) ; do
    symbols="$(scripts/arch-symbols $arch)"
    for config in $(scripts/guards $symbols < config.conf) ; do
	config=${config#config/}
	flavor=${config#*/}
	echo "kernel-$flavor ($arch)"
	echo Provides:  $(scripts/guards $symbols $flavor p \
					 < rpm/old-packages.conf)
	echo Obsoletes: $(scripts/guards $symbols $flavor o \
					 < rpm/old-packages.conf)
	echo
    done
done
