#!/usr/bin/env bash
# Deploy from the laptop: nothing is copied. The script checks that what you
# see is what the server will get and that CI passed on it, then runs
# deploy-prod.sh over ssh, naming the branch and the exact commit so the server
# refuses to deploy anything else.
# Run from anywhere inside the repository.
set -euo pipefail
cd "$(dirname "$0")/.."

APP="mcp_stock_markets"
# Where production lives is not in the repository: deploy/local.env (gitignored,
# see deploy/local.env.example) holds SERVER, SSH_KEY and GITHUB_TOKEN_FILE. It is
# read as data, never sourced; an environment variable of the same name wins.
local_value() {  # KEY
    if [ -r deploy/local.env ]; then
        sed -n "s/^$1=//p" deploy/local.env | tail -n 1
    fi
}
SERVER="${SERVER:-$(local_value SERVER)}"
SSH_KEY="${SSH_KEY:-$(local_value SSH_KEY)}"
SSH_KEY="${SSH_KEY/#\~/${HOME}}"
[ -n "${SERVER}" ] || { echo "❌ no SERVER — set it in deploy/local.env (copy deploy/local.env.example)"; exit 1; }
SSH_OPTS=(-o IdentitiesOnly=yes)
if [ -n "${SSH_KEY}" ]; then
    SSH_OPTS+=(-i "${SSH_KEY}")
fi
REMOTE_DIR="/opt/${APP}"
# Fine-grained GitHub token, read-only: this repository, "Actions: Read" (Metadata:
# Read comes with it). Kept in a file, never in the script or the shell history.
TOKEN_FILE="${GITHUB_TOKEN_FILE:-$(local_value GITHUB_TOKEN_FILE)}"
TOKEN_FILE="${TOKEN_FILE/#\~/${HOME}}"
TOKEN_FILE="${TOKEN_FILE:-${HOME}/.config/${APP}/github-ci-token}"

BRANCH="$(git rev-parse --abbrev-ref HEAD)"
[ "${BRANCH}" != "HEAD" ] || { echo "❌ detached HEAD — check out the branch to deploy"; exit 1; }
# The name travels inside the remote command line: refuse anything a shell would
# read as syntax (git allows quotes, $ and ; in branch names).
[[ "${BRANCH}" =~ ^[A-Za-z0-9._/-]+$ ]] || {
    echo "❌ branch '${BRANCH}' has characters outside [A-Za-z0-9._/-] — rename it to deploy it"; exit 1; }
[ -z "$(git status --porcelain)" ] || echo "⚠️  uncommitted changes here will NOT be deployed (the server pulls origin/${BRANCH})"
git fetch -q origin "${BRANCH}"
COMMIT="$(git rev-parse HEAD)"
[ "${COMMIT}" = "$(git rev-parse "origin/${BRANCH}")" ] || {
    echo "❌ local ${BRANCH} differs from origin/${BRANCH} — push (or pull) first"; exit 1; }
# CI is the gate: what ships is a commit whose checks passed.
[ -r "${TOKEN_FILE}" ] || {
    echo "❌ no GitHub token at ${TOKEN_FILE} — a fine-grained token, this repo only, Actions: Read"; exit 1; }
SLUG="$(git remote get-url origin | sed -E 's#^(git@github\.com:|https://github\.com/)##; s#\.git$##')"
# The token goes through curl's stdin config, never its arguments: no `ps` shows it.
CI="$(printf 'header = "Authorization: Bearer %s"\n' "$(cat "${TOKEN_FILE}")" \
    | curl -fsS --max-time 10 --config - \
        -H "Accept: application/vnd.github+json" -H "X-GitHub-Api-Version: 2022-11-28" \
        "https://api.github.com/repos/${SLUG}/actions/runs?head_sha=${COMMIT}&per_page=100" \
    | python3 -c 'import json, sys
runs = [run for run in json.load(sys.stdin)["workflow_runs"] if run["path"] == ".github/workflows/ci.yml"]
print(max(runs, key=lambda run: run["run_number"])["conclusion"] or "pending" if runs else "none")' \
    || echo "unreachable")"
[ "${CI}" = "success" ] || {
    echo "❌ CI has not passed on ${COMMIT:0:7} (latest ci.yml run: ${CI}) — https://github.com/${SLUG}/actions"; exit 1; }
if [ "${BRANCH}" != "main" ]; then
    read -r -p "⚠️  deploy branch '${BRANCH}' (not main) to production? [y/N] " answer
    case "${answer}" in y|Y|yes|YES) ;; *) echo "aborted"; exit 1 ;; esac
fi

echo "🚀 deploying origin/${BRANCH} (${COMMIT:0:7}) on ${SERVER}:${REMOTE_DIR}"
ssh "${SSH_OPTS[@]}" "${SERVER}" "DEPLOY_BRANCH=${BRANCH} DEPLOY_COMMIT=${COMMIT} bash ${REMOTE_DIR}/deploy/deploy-prod.sh"
