FROM node:22-alpine AS builder

WORKDIR /app
COPY package*.json ./
RUN npm ci --legacy-peer-deps --no-audit --no-fund
COPY . .
RUN npm run build:prod

FROM httpd:2.4-alpine

COPY --from=builder /app/dist/pingbiz-estore-customer-ui/ /usr/local/apache2/htdocs/
COPY docker/apache-angular.conf /usr/local/apache2/conf/extra/pingbusiness-angular.conf
COPY docker-entrypoint.sh /usr/local/bin/pingbusiness-ui-entrypoint

RUN printf '\nInclude conf/extra/pingbusiness-angular.conf\n' >> /usr/local/apache2/conf/httpd.conf \
 && chmod 0755 /usr/local/bin/pingbusiness-ui-entrypoint

EXPOSE 80
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -q -O /dev/null http://127.0.0.1/healthz || exit 1

ENTRYPOINT ["/usr/local/bin/pingbusiness-ui-entrypoint"]
CMD ["httpd-foreground"]
