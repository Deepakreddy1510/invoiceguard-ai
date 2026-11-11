#!/bin/sh
# Run only on the selected VM after access/cost approval. No cloud resources are created.
set -eu
: "${VM_ENV_FILE:?Set an absolute path to the private runtime.env}"
case "$VM_ENV_FILE" in /*) ;; *) echo 'VM_ENV_FILE must be absolute.' >&2; exit 1 ;; esac
repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
cd "$repo_dir"
compose() { docker compose --env-file "$VM_ENV_FILE" -f deploy/vm/compose.yaml "$@"; }
# Prevent two operators from starting overlapping deployment/migration sequences.
exec 9>"${VM_ENV_FILE}.deploy.lock"
flock -n 9 || { echo 'A VM deployment is already running.' >&2; exit 1; }
db_password=$(sed -n 's/^POSTGRES_PASSWORD=//p' "$VM_ENV_FILE")
if ! printf '%s\n' "$db_password" | grep -Eq '^[0-9a-f]{64}$'; then
  echo 'POSTGRES_PASSWORD must be 64 lowercase hex characters.' >&2
  exit 1
fi
unset db_password
compose config --quiet
if ! docker compose version --short | grep -Eq '^v?2\.'; then
  echo 'Docker Compose v2.30+ is required (raw env_file).' >&2
  exit 1
fi
# --quiet validates required values without printing secrets.
# Build before downtime. APP_IMAGE is read without shell evaluation.
app_image=$(sed -n 's/^APP_IMAGE=//p' "$VM_ENV_FILE")
commit=$(git rev-parse HEAD)
if [ "$app_image" != "invoiceguard-ai:$commit" ]; then
  echo 'APP_IMAGE must be invoiceguard-ai:<full checked-out commit>.' >&2
  exit 1
fi
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  echo 'Deploy only a clean committed checkout.' >&2
  exit 1
fi
docker build -t "$app_image" .
compose up -d --wait db
# Stop writers before backup/migration; keep the durable queue and all volumes.
compose stop worker api
backup_dir=$(dirname -- "$VM_ENV_FILE")/backups
umask 077
mkdir -p "$backup_dir"
backup="$backup_dir/pre-deploy-$(date -u +%Y%m%dT%H%M%SZ).dump"
compose exec -T db pg_dump -U invoiceguard -d invoiceguard -Fc > "$backup"
# Do not start services if backup/migrations fail. Inspect privately and use rollback guide.
compose run --rm --no-deps migrate
compose up -d --wait api worker proxy
compose ps
printf 'Deployment started from %s. Run the public acceptance checks; startup is not workflow success.\n' "$commit"
