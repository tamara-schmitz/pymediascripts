FROM registry.opensuse.org/opensuse/tumbleweed

ENV ZYPPER_PACKAGES="ImageMagick pngcrush \
                     python3 python3-img2pdf"

RUN	zypper --gpg-auto-import-keys ref && zypper --non-interactive dup --allow-vendor-change --allow-downgrade && \
	zypper --non-interactive install --recommends --allow-vendor-change --allow-downgrade $ZYPPER_PACKAGES && \
	zypper clean -a

ADD imagesToPdf.py /

ENTRYPOINT	["/imagesToPdf.py"]
CMD		["-h"]
