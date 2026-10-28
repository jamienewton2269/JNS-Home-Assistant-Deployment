FROM ghcr.io/home-assistant/base:3.24
RUN apk --no-cache add python3
COPY probe.py /opt/jns/probe.py
COPY run.sh /run.sh
RUN chmod 0755 /run.sh
CMD ["/run.sh"]
