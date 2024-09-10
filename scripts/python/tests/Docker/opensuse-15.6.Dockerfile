# https://hub.docker.com/r/opensuse/leap/
FROM opensuse/leap:15.6 AS base

FROM base AS packages

RUN zypper -n in git python3 python3-dbm python3-requests rcs util-linux gawk python3-pygit2 python3-PyYAML kcov

RUN git config --global user.email "you@example.com"
RUN git config --global user.name "Your Name"

COPY Kernel.gpg /tmp
RUN rpmkeys --import /tmp/Kernel.gpg
RUN zypper -n ar -f https://download.opensuse.org/repositories/Kernel:/tools/SLE_15_SP6/Kernel:tools.repo
RUN zypper -n in --from Kernel_tools quilt

FROM packages

VOLUME /scripts

WORKDIR /scripts/python

CMD python3 -m unittest discover -v
