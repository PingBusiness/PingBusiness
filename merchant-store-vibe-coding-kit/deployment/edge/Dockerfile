ARG CADDY_IMAGE=caddy:2.11.4-alpine
FROM ${CADDY_IMAGE}

COPY Caddyfile.platform /etc/caddy/Caddyfile
COPY Caddyfile.compose /etc/caddy/Caddyfile.compose
COPY routes.caddy /etc/caddy/routes.caddy
WORKDIR /etc/caddy

EXPOSE 8080 80 443 443/udp
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -q -O - http://127.0.0.1:8080/edge-health | grep -q '^ok$' || exit 1

CMD ["caddy", "run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"]
