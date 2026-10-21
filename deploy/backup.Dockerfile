FROM postgres:16-alpine

# aws-cli for S3 upload, age to seal dumps (authenticated) before they touch disk,
# curl to ping the heartbeat monitor.
RUN apk add --no-cache age aws-cli bash curl

# Not root: the image's entrypoint drops privileges only when it starts postgres
# itself, and this container runs bash. A new named volume copies this ownership;
# an existing one needs `chown -R 70:70` once (70 is postgres in the alpine image).
RUN mkdir -p /backups && chown postgres:postgres /backups
COPY backup.sh /backup/backup.sh
USER postgres
