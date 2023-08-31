# http://registry.suse.de/
FROM registry.suse.de/suse/containers/sle-server/12-sp4/containers/suse/sles12sp4:latest AS base

RUN rpm -e container-suseconnect
RUN zypper -n ar -f http://download.suse.de/ibs/SUSE:/SLE-12:/GA/standard/SUSE:SLE-12:GA.repo
RUN zypper -n ar -f http://download.suse.de/ibs/SUSE:/SLE-12:/Update/standard/SUSE:SLE-12:Update.repo
RUN zypper -n ar -f http://download.suse.de/install/SLP/SLE-12-SP4-Server-GM/$(rpm -E %_arch)/DVD1/ DVD1
RUN zypper -n ar -f http://download.suse.de/install/SLP/SLE-12-SP4-Server-GM/$(rpm -E %_arch)/DVD2/ DVD2
RUN zypper -n ar -f http://download.suse.de/install/SLP/SLE-12-SP4-Server-GM/$(rpm -E %_arch)/DVD3/ DVD3
# RUN zypper -n ar -G http://updates.suse.de/SUSE/Products/SLE-SDK/12-SP4/$(rpm -E %_arch)/product/ SDK
RUN zypper -n ar -f http://download.suse.de/update/build.suse.de/SUSE/Updates/SLE-SERVER/12-SP4/$(rpm -E %_arch)/update/SUSE:Updates:SLE-SERVER:12-SP4:$(rpm -E %_arch).repo

FROM base AS packages

RUN zypper -n in git-core python3 python3-dbm rcs

RUN git config --global user.email "you@example.com"
RUN git config --global user.name "Your Name"

COPY Kernel.gpg /tmp
RUN rpmkeys --import /tmp/Kernel.gpg
RUN zypper -n ar -f https://download.opensuse.org/repositories/Kernel:/tools/SLE_12_SP4/Kernel:tools.repo
RUN zypper -n in python3-pygit2 quilt

FROM packages

VOLUME /scripts

WORKDIR /scripts/git_sort

CMD python3 -m unittest discover -v
