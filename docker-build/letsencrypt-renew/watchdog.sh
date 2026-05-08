#!/usr/bin/env bash
# Independent expiry check.
# Alerts if cert is within THRESHOLD_DAYS of expiry, regardless of what renew.sh thinks —
# defence-in-depth so a silently-broken renewer cannot cause another outage.
set -euo pipefail

DOMAIN="api.chatcraft.cc"
CERT="/opt/bitnami/letsencrypt/certificates/${DOMAIN}.crt"
THRESHOLD_DAYS=14

if [[ ! -f "$CERT" ]]; then
    /opt/letsencrypt-renew/notify.sh "WATCHDOG: cert missing for $DOMAIN" "Expected cert at $CERT but file does not exist."
    exit 1
fi

EXPIRY_STR=$(openssl x509 -enddate -noout -in "$CERT" | cut -d= -f2)
EXPIRY_EPOCH=$(date -d "$EXPIRY_STR" +%s)
NOW_EPOCH=$(date +%s)
DAYS_LEFT=$(( (EXPIRY_EPOCH - NOW_EPOCH) / 86400 ))

logger -t "letsencrypt-watchdog" "Cert $DOMAIN has $DAYS_LEFT days remaining (expires $EXPIRY_STR)"

if (( DAYS_LEFT < THRESHOLD_DAYS )); then
    /opt/letsencrypt-renew/notify.sh \
        "WATCHDOG: $DOMAIN expires in $DAYS_LEFT days" \
        "Cert at $CERT expires in $DAYS_LEFT days ($EXPIRY_STR). The auto-renewer may be broken — investigate immediately."
fi
