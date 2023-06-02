# https://hub.docker.com/r/opensuse/leap/
FROM opensuse/leap:15.4 AS base

RUN zypper -n ref

FROM base AS packages

RUN zypper -n in git python3 python3-dbm rcs

RUN git config --global user.email "you@example.com"
RUN git config --global user.name "Your Name"

COPY Kernel.gpg /tmp
RUN rpmkeys --import /tmp/Kernel.gpg
RUN zypper -n ar -f https://download.opensuse.org/repositories/Kernel:/tools/SLE_15_SP4/Kernel:tools.repo
RUN zypper -n in python3-pygit2 quilt

FROM packages

VOLUME /scripts

WORKDIR /scripts/git_sort

CMD python3 -m unittest discover -v
