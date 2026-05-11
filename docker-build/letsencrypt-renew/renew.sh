#!/usr/bin/env bash
# Renew api.chatcraft.cc cert via lego.
# Idempotent — no-op if cert is not within 30 days of expiry.
# Invoked by letsencrypt-renew.service every 12h.
set -euo pipefail

DOMAIN="api.chatcraft.cc"
EMAIL="adebola@factorialsystems.io"
LEGO_PATH="/opt/bitnami/letsencrypt"
LEGO_BIN="${LEGO_PATH}/lego"
CTL="/opt/bitnami/ctlscript.sh"
LOG_TAG="letsencrypt-renew"
RENEW_LOG="/var/log/letsencrypt-renew.log"

log()  { logger -t "$LOG_TAG" -- "$*"; echo "$(date -Is) $*" | tee -a "$RENEW_LOG"; }
fail() { log "ERROR: $*"; /opt/letsencrypt-renew/notify.sh "RENEW FAILED: $DOMAIN" "$*"; exit 1; }

# Bitnami's ctlscript briefly holds a per-service lock after `stop` returns,
# so an immediate `start` races with "Other action already in progress".
# Retry with backoff — total budget ~30s.
start_nginx() {
    local attempts=0
    while (( attempts < 15 )); do
        if "$CTL" start nginx; then
            return 0
        fi
        attempts=$((attempts + 1))
        log "nginx start contended (attempt $attempts/15), retrying in 2s"
        sleep 2
    done
    return 1
}

log "Starting renewal check for $DOMAIN"

BEFORE=$(openssl x509 -enddate -noout -in "${LEGO_PATH}/certificates/${DOMAIN}.crt" 2>/dev/null | cut -d= -f2 || echo "missing")

# Lego needs to bind 443 for TLS-ALPN-01; stop nginx briefly.
"$CTL" stop nginx || fail "Failed to stop nginx"

# Ensure nginx restarts even if lego crashes. If even the retried start fails,
# alert loudly — silent nginx-down is the worst outcome.
trap 'start_nginx || /opt/letsencrypt-renew/notify.sh "RENEW CRITICAL: $DOMAIN — nginx down" "renew.sh exited and could not restart nginx after 30s of retries. Check the host immediately."' EXIT

if ! "$LEGO_BIN" --tls --email="$EMAIL" --domains="$DOMAIN" --path="$LEGO_PATH" \
        renew --days 30 --no-random-sleep 2>&1 | tee -a "$RENEW_LOG"; then
    fail "lego renew exited non-zero"
fi

trap - EXIT
start_nginx || fail "Failed to start nginx after renewal (retried 15× over 30s)"

AFTER=$(openssl x509 -enddate -noout -in "${LEGO_PATH}/certificates/${DOMAIN}.crt" | cut -d= -f2)

if [[ "$BEFORE" != "$AFTER" ]]; then
    log "Cert renewed. Old expiry: $BEFORE  New expiry: $AFTER"
    /opt/letsencrypt-renew/notify.sh "Cert renewed: $DOMAIN" "Old expiry: $BEFORE"$'\n'"New expiry: $AFTER"
else
    log "No renewal needed (expiry unchanged: $AFTER)"
fi
