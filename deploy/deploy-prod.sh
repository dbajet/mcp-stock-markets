#!/usr/bin/env bash
# Blue/green deploy — runs ON THE SERVER from the git clone, as the clone's
# owner. It fast-forwards the checked-out branch itself, so production always
# runs an exact pushed commit. Trigger it from the
# laptop with deploy-from-local.sh, which passes DEPLOY_BRANCH and DEPLOY_COMMIT
# after checking CI. Run by hand without DEPLOY_COMMIT, nothing has checked CI, so
# it refuses unless DEPLOY_WITHOUT_CI_CHECK=yes says so explicitly.
#
# The body is one main() invoked on the last line: bash reads a script
# incrementally, and the fast-forward in step 1 may replace this very file.
# When it does, main() re-executes the new file once, so a fix to this script
# applies to the deploy that brought it.
set -euo pipefail
cd "$(dirname "$0")/.."

main() {
APP="mcp_stock_markets"
# Overridable only so a test can run this script against a scratch file.
NGINX_CONF="${NGINX_CONF:-/etc/nginx/sites-enabled/${APP}.conf}"
# Every request has a deadline: a hung endpoint must fail the deploy, not stall it.
CURL=(curl -fsS --max-time 5)

# .env files are data — never sourced: sourcing runs them as code and leaves their
# secrets exported to every later command. The format is restricted to what this
# reads the same way Compose does: KEY=value, the last line for a key wins, a value
# either quoted whole ("…" or '…', no escapes; a # inside is data) or unquoted
# (a # after whitespace starts a comment).
env_value() {  # KEY FILE
    local raw
    raw="$(sed -n "s/^$1=//p" "$2" | tail -n 1)"
    case "${raw}" in
        \"*) raw="${raw#\"}"; printf '%s\n' "${raw%%\"*}" ;;
        \'*) raw="${raw#\'}"; printf '%s\n' "${raw%%\'*}" ;;
        *) printf '%s\n' "${raw}" | sed -e 's/[[:space:]]\{1,\}#.*$//' ;;
    esac
}
refuse_placeholder() {  # NAME VALUE FILE
    case "$2" in
        ""|CHANGE_ME*|change-me|placeholder)
            echo "❌ $1 in $3 is empty or a placeholder"; exit 1 ;;
    esac
}
# /healthz on stdin must report ok AND the commit being deployed: an old container
# still answering on the port would otherwise pass as the new one. The commit, not
# APP_VERSION — two branches can share a date and a commit count.
healthz_matches() {
    python3 -c 'import json, sys
body = json.load(sys.stdin)
sys.exit(0 if body.get("ok") is True and body.get("commit") == sys.argv[1] else 1)' "${APP_COMMIT}"
}
# The live proxy_pass ports, comments ignored, one per line.
proxied_ports() {
    sed -e 's/#.*$//' "${NGINX_CONF}" | grep -o 'proxy_pass http://127\.0\.0\.1:[0-9]*;' \
        | sed -e 's/.*://' -e 's/;$//' | sort -u
}
healthy_at() {  # URL ATTEMPTS [CURL_ARGS...]
    for _ in $(seq 1 "$2"); do
        if "${CURL[@]}" "${@:3}" "$1" 2>/dev/null | healthz_matches 2>/dev/null; then
            return 0
        fi
        sleep 2
    done
    return 1
}

echo "🔎 Step 1: preconditions — committed, pushed code only"
# Owner first, before any git command: a clone owned by someone else is
# "dubious" to git, which then fails in ways that look like a missing clone.
REPO_OWNER="$(stat -c %U .)"
[ "$(id -un)" = "${REPO_OWNER}" ] || {
    echo "❌ this clone belongs to '${REPO_OWNER}' but you are '$(id -un)'"
    echo "   sudo -u ${REPO_OWNER} bash -c 'cd $(pwd) && bash deploy/deploy-prod.sh'"; exit 1; }
[ -f .env ] || { echo "❌ .env is missing"; exit 1; }
[ -f .env.backup ] || { echo "❌ .env.backup is missing"; exit 1; }
for file in .env .env.backup; do
    [ "$(stat -c %a "${file}")" = "600" ] || { echo "❌ ${file} is readable by others — chmod 600 ${file}"; exit 1; }
done
[ -d .git ] || { echo "❌ not a git clone — git clone <this repository> $(pwd)"; exit 1; }
# One deploy per app at a time: two would pick the same idle color and race on it.
exec 9>.git/deploy.lock
flock -n 9 || { echo "❌ another ${APP} deploy is running"; exit 1; }
# The version number counts the day's commits: a shallow clone counts wrong.
[ "$(git rev-parse --is-shallow-repository)" != "true" ] || { echo "❌ shallow clone — git fetch --unshallow"; exit 1; }
BRANCH="$(git rev-parse --abbrev-ref HEAD)"
[ "${BRANCH}" != "HEAD" ] || { echo "❌ detached HEAD — git checkout <branch>"; exit 1; }
# The caller names the branch it verified as pushed; deploying another one
# would look green while shipping other code.
[ -z "${DEPLOY_BRANCH:-}" ] || [ "${DEPLOY_BRANCH}" = "${BRANCH}" ] || {
    echo "❌ the clone is on '${BRANCH}' but the deploy asked for '${DEPLOY_BRANCH}' — git checkout ${DEPLOY_BRANCH}"; exit 1; }
# A fast-forward alone would not catch an edit made on the server when the
# branch has nothing new: "already up to date", and the build takes the edit.
# Ignored files (.env, .env.backup) do not count.
[ -z "$(git status --porcelain)" ] || { echo "❌ the clone has local changes — git status"; exit 1; }
SCRIPT_BEFORE="$(git rev-parse HEAD:deploy/deploy-prod.sh)"
git fetch -q origin "${BRANCH}"
# Fast-forward only: a diverged server branch stops the deploy here rather
# than quietly merging into something nobody reviewed.
git merge -q --ff-only "origin/${BRANCH}" || { echo "❌ cannot fast-forward onto origin/${BRANCH} — git status"; exit 1; }
# A clean clone AHEAD of origin is "up to date" for a fast-forward: it would ship
# a commit that was never pushed, so the two must be identical.
[ "$(git rev-parse HEAD)" = "$(git rev-parse "origin/${BRANCH}")" ] || {
    echo "❌ the clone holds commits origin/${BRANCH} does not — git log origin/${BRANCH}..HEAD"; exit 1; }
# The caller names the exact commit whose CI it checked; a push landing in
# between must not ship in its place.
if [ -n "${DEPLOY_COMMIT:-}" ]; then
    [ "${DEPLOY_COMMIT}" = "$(git rev-parse HEAD)" ] || {
        echo "❌ origin/${BRANCH} is $(git rev-parse --short HEAD), not the requested ${DEPLOY_COMMIT:0:7} — deploy again"; exit 1; }
elif [ "${DEPLOY_WITHOUT_CI_CHECK:-}" = "yes" ]; then
    echo "⚠️  run by hand: CI was NOT checked for $(git rev-parse --short HEAD)"
else
    echo "❌ no DEPLOY_COMMIT, so nothing checked CI — use deploy-from-local.sh, or check CI yourself and set DEPLOY_WITHOUT_CI_CHECK=yes"
    exit 1
fi
if [ "$(git rev-parse HEAD:deploy/deploy-prod.sh)" != "${SCRIPT_BEFORE}" ] && [ -z "${DEPLOY_REEXEC:-}" ]; then
    echo "   deploy-prod.sh changed — re-running the new version"
    exec env DEPLOY_REEXEC=1 bash deploy/deploy-prod.sh "$@"
fi
echo "   deploying ${BRANCH} @ $(git log -1 --format='%h %s')"

echo "🔐 Step 2: refuse development mode and placeholder secrets"
# Compose lets the shell environment override .env when interpolating; this script
# reads .env alone, so the two must not disagree.
unset APP_PORT_BLUE APP_PORT_GREEN DB_NAME DB_USER DB_PASSWORD DB_PORT
# In dev the settings loader only warns about placeholders.
[ "$(env_value APP_ENV .env)" = "production" ] || { echo "❌ APP_ENV in .env is not 'production'"; exit 1; }
for name in DATA_ENCRYPTION_KEY DB_PASSWORD APP_BASE_URL SMTP_USER SMTP_PASSWORD; do
    refuse_placeholder "${name}" "$(env_value "${name}" .env)" .env
done
# The app's .env cannot prove that the sidecar can authenticate or encrypt
# future backups, so its separately scoped file is validated too.
for name in DB_PASSWORD BACKUP_AGE_RECIPIENT AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY S3_BACKUP_BUCKET; do
    refuse_placeholder "${name}" "$(env_value "${name}" .env.backup)" .env.backup
done
# Without a heartbeat monitor yet (the owner's choice, recorded in the audit), an
# empty URL is allowed and shouted about; a placeholder is still refused.
case "$(env_value BACKUP_HEARTBEAT_URL .env.backup)" in
    "") echo "⚠️  BACKUP_HEARTBEAT_URL is empty: nobody is alerted if backups stop" ;;
    CHANGE_ME*|change-me|placeholder) echo "❌ BACKUP_HEARTBEAT_URL in .env.backup is a placeholder — set a URL or leave it empty"; exit 1 ;;
esac
case "$(env_value BACKUP_AGE_RECIPIENT .env.backup)" in
    age1*) ;;
    *) echo "❌ BACKUP_AGE_RECIPIENT in .env.backup is not an age public key (age1…)"; exit 1 ;;
esac
[ "$(env_value DB_PASSWORD .env.backup)" = "$(env_value DB_PASSWORD .env)" ] || {
    echo "❌ backup DB_PASSWORD does not match .env"; exit 1; }
# The public host comes from the server's own .env: the repository names no server.
DOMAIN="$(env_value APP_BASE_URL .env | sed -E 's#^https://##; s#[:/].*$##')"
case "$(env_value APP_BASE_URL .env)" in
    https://?*) ;;
    *) echo "❌ APP_BASE_URL in .env is not an https:// address"; exit 1 ;;
esac

echo "🎨 Step 3: detect the active color"
BLUE_PORT="$(env_value APP_PORT_BLUE .env)"
BLUE_PORT="${BLUE_PORT:-8150}"
GREEN_PORT="$(env_value APP_PORT_GREEN .env)"
GREEN_PORT="${GREEN_PORT:-8151}"
# Every live proxy_pass must name the same color: a mix, or a port that is neither,
# would make the switch rewrite part or nothing and still report success.
PORTS="$(proxied_ports | tr '\n' ' ')"
if [ "${PORTS}" = "${BLUE_PORT} " ]; then
    ACTIVE="blue";  IDLE="green"; ACTIVE_PORT="${BLUE_PORT}";  IDLE_PORT="${GREEN_PORT}"
elif [ "${PORTS}" = "${GREEN_PORT} " ]; then
    ACTIVE="green"; IDLE="blue";  ACTIVE_PORT="${GREEN_PORT}"; IDLE_PORT="${BLUE_PORT}"
else
    echo "❌ ${NGINX_CONF} proxies to [ ${PORTS}] — every live proxy_pass must use one of ${BLUE_PORT} (blue) or ${GREEN_PORT} (green)"
    exit 1
fi
echo "   active=${ACTIVE} → deploying ${IDLE}"

echo "🔨 Step 4: build ${IDLE} while ${ACTIVE} still serves"
BUILD_TIME="$(date -u +%Y%m%d-%H%M%SZ)"
CDATE="$(git log -1 --format=%cd --date=format:'%Y-%m-%d')"
APP_VERSION="${CDATE}.$(git log --format=%cd --date=format:'%Y-%m-%d' | grep -c "^${CDATE}$")"
APP_COMMIT="$(git rev-parse HEAD)"
export BUILD_TIME APP_VERSION APP_COMMIT
# Shared services are started when absent, never recreated: a database or backup
# change is applied deliberately (docker compose up -d ${APP}-db ${APP}-backup),
# not as a side effect of an app release.
docker compose up -d --no-recreate "${APP}-db" "${APP}-backup"
if [ "$(docker inspect -f '{{.State.Health.Status}}' "${APP}-backup" 2>/dev/null)" = "unhealthy" ]; then
    echo "⚠️  ${APP}-backup is unhealthy: the last successful backup is overdue — docker logs ${APP}-backup"
fi
docker compose build "${APP}-app-${IDLE}"
docker compose up -d --no-deps --force-recreate "${APP}-app-${IDLE}"

echo "🩺 Step 5: health-check ${IDLE}"
healthy_at "http://127.0.0.1:${IDLE_PORT}/healthz" 40 || {
    echo "❌ ${IDLE} never served ${APP_COMMIT:0:7} healthily — ${ACTIVE} still serves"; exit 1; }

echo "🔀 Step 6: switch nginx to ${IDLE}"
PREVIOUS_CONF="$(mktemp)"
cp "${NGINX_CONF}" "${PREVIOUS_CONF}"
# Puts the previous file back and reloads it; says whether nginx took it, since a
# failed reload leaves nginx on whatever config it last loaded.
restore_nginx() {
    cat "${PREVIOUS_CONF}" > "${NGINX_CONF}"
    if sudo -n nginx -s reload; then
        echo "   ↩️  previous nginx config restored and reloaded — ${ACTIVE} serves"
    else
        echo "   ⚠️  previous config restored on disk, but the reload FAILED — check: sudo nginx -t; systemctl status nginx"
    fi
}
# Written in place (not sed -i): the deploy user owns this file, not its directory.
sed "s/127.0.0.1:${ACTIVE_PORT};/127.0.0.1:${IDLE_PORT};/" "${PREVIOUS_CONF}" > "${NGINX_CONF}"
# An `if`, not `nginx -t && reload`: set -e ignores a failure on the left of &&,
# and step 7 would then stop the color nginx still routes to.
if ! sudo -n nginx -t; then
    cat "${PREVIOUS_CONF}" > "${NGINX_CONF}"
    echo "❌ nginx rejected the new config — previous config restored; ${ACTIVE} still serves"; exit 1
fi
if ! sudo -n nginx -s reload; then
    # The running nginx did not take the new file: put the file back to match it.
    cat "${PREVIOUS_CONF}" > "${NGINX_CONF}"
    echo "❌ nginx -s reload failed — previous config restored on disk; nginx still runs its last loaded config (${ACTIVE})"; exit 1
fi
# Through nginx, as a visitor arrives: proves the reload took and routes to ${IDLE}.
healthy_at "https://${DOMAIN}/healthz" 5 --resolve "${DOMAIN}:443:127.0.0.1" || {
    restore_nginx
    echo "❌ ${DOMAIN} does not serve ${APP_COMMIT:0:7} through nginx"; exit 1; }

echo "🧹 Step 7: stop ${ACTIVE}, prune old images"
# docker stop sends SIGTERM: uvicorn finishes in-flight requests within stop_grace_period.
docker compose stop "${APP}-app-${ACTIVE}"
docker image prune -f --filter "until=168h"

echo "✅ Deployed ${APP_VERSION} (${APP_COMMIT:0:7}) on ${IDLE}"
echo "   rollback: docker compose start ${APP}-app-${ACTIVE}, set proxy_pass back to ${ACTIVE_PORT} in ${NGINX_CONF}, sudo nginx -t && sudo nginx -s reload"
}

main "$@"
