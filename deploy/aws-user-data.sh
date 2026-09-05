#!/bin/bash
set -Eeuxo pipefail

exec > >(tee /var/log/aamsx-deploy.log | logger -t aamsx-deploy -s 2>/dev/console) 2>&1
trap 'touch /var/lib/aamsx-deploy-failed' ERR

# Amazon Linux already includes curl-minimal, which provides the curl command.
# Installing the full curl package conflicts with it on a fresh AL2023 image.
dnf install -y docker tar
systemctl enable --now docker

# A small server keeps the recurring bill low. Swap gives dependency compilation
# some temporary breathing room without paying for a larger instance every hour.
fallocate -l 2G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
printf '%s\n' '/swapfile none swap sw 0 0' >> /etc/fstab

install -d -m 0755 /opt/aamsx
BUNDLE_URL="$(printf '%s' '__BUNDLE_URL_B64__' | base64 -d)"
curl --fail --location --retry 5 --retry-delay 3 \
  --output /tmp/aamsx-deploy.tar.gz "$BUNDLE_URL"
tar -xzf /tmp/aamsx-deploy.tar.gz -C /opt/aamsx
rm -f /tmp/aamsx-deploy.tar.gz

install -d -m 0755 /opt/aamsx/reports/out
chown -R 10001:10001 /opt/aamsx/data /opt/aamsx/reports/out

cd /opt/aamsx
docker build --tag aamsx-api:aws .
docker build --build-arg VITE_API_BASE=/api --tag aamsx-web:aws ./web
docker network create aamsx

docker run --detach \
  --name api \
  --network aamsx \
  --restart unless-stopped \
  --volume /opt/aamsx/data:/data \
  --volume /opt/aamsx/reports/out:/data/reports \
  --env AAMSX_DATA_DIR=/data \
  --env AAMSX_REPORTS_DIR=/data/reports \
  --env AAMSX_ALLOW_NETWORK=false \
  --env 'AAMSX_CORS_ORIGINS=[]' \
  aamsx-api:aws

for attempt in $(seq 1 90); do
  if [ "$(docker inspect --format '{{.State.Health.Status}}' api 2>/dev/null || true)" = "healthy" ]; then
    break
  fi
  sleep 2
done

if [ "$(docker inspect --format '{{.State.Health.Status}}' api)" != "healthy" ]; then
  docker logs api
  exit 1
fi

docker run --detach \
  --name web \
  --network aamsx \
  --restart unless-stopped \
  --publish 80:80 \
  aamsx-web:aws

for attempt in $(seq 1 30); do
  if curl --fail --silent http://127.0.0.1/api/health >/dev/null; then
    touch /var/lib/aamsx-deploy-ready
    exit 0
  fi
  sleep 2
done

docker logs web
exit 1
