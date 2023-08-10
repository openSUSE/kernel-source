# https://hub.docker.com/r/opensuse/tumbleweed/
FROM opensuse/tumbleweed AS base

RUN zypper -n ref

FROM base AS packages

RUN zypper -n in git python3 python3-dbm python3-pygit2 rcs util-linux

RUN git config --global user.email "you@example.com"
RUN git config --global user.name "Your Name"

COPY Kernel.gpg /tmp
RUN rpmkeys --import /tmp/Kernel.gpg
RUN zypper -n ar -f https://download.opensuse.org/repositories/Kernel:/tools/openSUSE_Factory/Kernel:tools.repo
RUN zypper -n in --from Kernel_tools quilt

FROM packages

VOLUME /scripts

WORKDIR /scripts/git_sort

CMD python3 -m unittest discover -v
