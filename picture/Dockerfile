FROM registry.opensuse.org/opensuse/tumbleweed

ENV ZYPPER_PACKAGES="python3 libjxl-tools"

RUN	zypper --gpg-auto-import-keys ref && zypper --non-interactive dup --allow-vendor-change --allow-downgrade && \
	zypper --non-interactive install --recommends --allow-vendor-change --allow-downgrade $ZYPPER_PACKAGES && \
	zypper clean -a

ADD picturebatchconverter.py /

ENTRYPOINT	["/picturebatchconverter.py"]
CMD		["-h"]
