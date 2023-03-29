FROM ghcr.io/tamara-schmitz/ffmpeg-docker-container

ENV ZYPPER_PACKAGES="python3"

RUN	zypper --gpg-auto-import-keys ref && zypper --non-interactive dup --allow-vendor-change --allow-downgrade && \
	zypper --non-interactive install --recommends --allow-vendor-change --allow-downgrade $ZYPPER_PACKAGES && \
	zypper clean -a

ADD musicbatchconverter.py /

ENTRYPOINT	["/musicbatchconverter.py"]
CMD		["-h"]
