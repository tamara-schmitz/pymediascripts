FROM registry.opensuse.org/opensuse/tumbleweed

ENV ZYPPER_PACKAGES="python3 libjxl-tools"

RUN	zypper --non-interactive dup && \
	zypper --non-interactive install --recommends $ZYPPER_PACKAGES && \
	zypper clean -a

ADD picturebatchconverter.py /

ENTRYPOINT	["/picturebatchconverter.py"]
CMD		["-h"]
