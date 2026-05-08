#!/usr/bin/env bash
# notify.sh "<subject>" "<body>"
# Sends an email alert via msmtp using SMTP creds from /opt/letsencrypt-renew/.env.
set -euo pipefail

ENV_FILE="/opt/letsencrypt-renew/.env"
[[ -f "$ENV_FILE" ]] && source "$ENV_FILE"

SUBJECT="${1:-(no subject)}"
BODY="${2:-(no body)}"
TO="${ALERT_TO:-adeomoboya@googlemail.com}"
FROM="${ALERT_FROM:-noreply@chatcraft.cc}"

if [[ -z "${SMTP_HOST:-}" || -z "${SMTP_USER:-}" || -z "${SMTP_PASS:-}" ]]; then
    logger -t letsencrypt-notify "SMTP not configured — would have sent: $SUBJECT"
    exit 0
fi

# Write a short-lived msmtprc rather than passing the password on the command line
# (so it never appears in the process listing) and remove it on exit.
TMPCFG=$(mktemp)
chmod 600 "$TMPCFG"
trap 'rm -f "$TMPCFG"' EXIT

cat > "$TMPCFG" <<EOF
defaults
auth           on
tls            on
tls_starttls   on
tls_certcheck  on

account        default
host           ${SMTP_HOST}
port           ${SMTP_PORT:-587}
from           ${FROM}
user           ${SMTP_USER}
password       ${SMTP_PASS}
EOF

{
    echo "From: $FROM"
    echo "To: $TO"
    echo "Subject: [chatcraft-prod] $SUBJECT"
    echo "Date: $(date -R)"
    echo
    echo "Host: $(hostname)"
    echo "Time: $(date -Is)"
    echo
    echo "$BODY"
} | msmtp --file="$TMPCFG" "$TO" \
    || logger -t letsencrypt-notify "msmtp failed for: $SUBJECT"
