ARG KEYCLOAK_VERSION=26.7.0
FROM quay.io/keycloak/keycloak:${KEYCLOAK_VERSION} AS builder

ENV KC_DB=postgres \
    KC_HEALTH_ENABLED=true \
    KC_METRICS_ENABLED=true

RUN /opt/keycloak/bin/kc.sh build --db=postgres

ARG KEYCLOAK_VERSION=26.7.0
FROM quay.io/keycloak/keycloak:${KEYCLOAK_VERSION}

COPY --from=builder /opt/keycloak/ /opt/keycloak/
COPY --chown=1000:1000 ESTORE-realm-template.json /opt/keycloak/data/ESTORE-realm-template.json
COPY --chown=1000:1000 container-entrypoint.sh /opt/keycloak/bin/pingbusiness-entrypoint.sh

USER 1000
RUN mkdir -p /opt/keycloak/data/import
EXPOSE 8080 9000
ENTRYPOINT ["/opt/keycloak/bin/pingbusiness-entrypoint.sh"]
CMD ["start", "--optimized", "--import-realm"]
