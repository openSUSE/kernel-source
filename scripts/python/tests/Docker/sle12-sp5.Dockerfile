# http://registry.suse.de/
FROM registry.suse.de/suse/containers/sle-server/12-sp5/containers/suse/sles12sp5:latest AS base

RUN rpm -e container-suseconnect
RUN zypper -n ar -f http://download.suse.de/ibs/SUSE:/SLE-12:/GA/standard/SUSE:SLE-12:GA.repo
RUN zypper -n ar -f http://download.suse.de/ibs/SUSE:/SLE-12:/Update/standard/SUSE:SLE-12:Update.repo
RUN zypper -n ar -f http://download.suse.de/ibs/SUSE:/SLE-12-SP1:/GA/standard/SUSE:SLE-12-SP1:GA.repo
RUN zypper -n ar -f http://download.suse.de/ibs/SUSE:/SLE-12-SP1:/Update/standard/SUSE:SLE-12-SP1:Update.repo
RUN zypper -n ar -f http://download.suse.de/ibs/SUSE:/SLE-12-SP2:/GA/standard/SUSE:SLE-12-SP2:GA.repo
RUN zypper -n ar -f http://download.suse.de/ibs/SUSE:/SLE-12-SP2:/Update/standard/SUSE:SLE-12-SP2:Update.repo
RUN zypper -n ar -f http://download.suse.de/ibs/SUSE:/SLE-12-SP3:/GA/standard/SUSE:SLE-12-SP3:GA.repo
RUN zypper -n ar -f http://download.suse.de/ibs/SUSE:/SLE-12-SP3:/Update/standard/SUSE:SLE-12-SP3:Update.repo
RUN zypper -n ar -f http://download.suse.de/ibs/SUSE:/SLE-12-SP4:/GA/standard/SUSE:SLE-12-SP4:GA.repo
RUN zypper -n ar -f http://download.suse.de/ibs/SUSE:/SLE-12-SP4:/Update/standard/SUSE:SLE-12-SP4:Update.repo
RUN zypper -n ar -f http://download.suse.de/ibs/SUSE:/SLE-12-SP5:/GA/standard/SUSE:SLE-12-SP5:GA.repo
RUN zypper -n ar -f http://download.suse.de/ibs/SUSE:/SLE-12-SP5:/Update/standard/SUSE:SLE-12-SP5:Update.repo

FROM base AS packages

RUN zypper -n in git-core python3 python3-dbm python3-requests rcs util-linux gawk python3-PyYAML

RUN git config --global user.email "you@example.com"
RUN git config --global user.name "Your Name"

COPY Kernel.gpg /tmp
RUN rpmkeys --import /tmp/Kernel.gpg
RUN zypper -n ar -f https://download.opensuse.org/repositories/Kernel:/tools/SLE_12_SP5/Kernel:tools.repo
RUN zypper -n in --from Kernel_tools python3-pygit2 quilt

FROM packages

VOLUME /scripts

WORKDIR /scripts/python

CMD python3 -m unittest discover -v
