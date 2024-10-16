FROM registry.opensuse.org/kernel/tools/images/sle_15_sp6/kernel-scripts:latest AS base

RUN git config --global user.email "you@example.com"
RUN git config --global user.name "Your Name"

FROM base

VOLUME /scripts

WORKDIR /scripts/python

CMD python3 -m unittest discover -v
