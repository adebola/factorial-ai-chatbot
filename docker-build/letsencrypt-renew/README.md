# Let's Encrypt auto-renewal — production EC2 (Bitnami nginx)

Automated cert renewal for `api.chatcraft.cc` on the production Bitnami EC2 host. Replaces manual `lego` renewals that were causing silent expiry → API outages.

## What it does

Two systemd timers:

| Unit | Cadence | Job |
|------|---------|-----|
| `letsencrypt-renew.timer` | every 12h (+30min jitter) | Runs `lego renew --days 30`. No-op if cert isn't due. Stops nginx briefly (~5–10s), renews, starts nginx. Emails on success or failure. |
| `letsencrypt-watchdog.timer` | daily | Reads cert expiry directly. Emails an alert if < 14 days remain — defence-in-depth in case the renewer silently fails. |

Renewal uses the **TLS-ALPN-01** challenge (`lego --tls`), which matches Bitnami's `bncert` behaviour and requires no nginx config changes.

## File layout (on EC2 host)

```
/opt/letsencrypt-renew/
├── renew.sh
├── watchdog.sh
├── notify.sh
└── .env                   # SMTP creds, mode 0600, root-owned (NOT committed)

/etc/systemd/system/
├── letsencrypt-renew.service
├── letsencrypt-renew.timer
├── letsencrypt-watchdog.service
└── letsencrypt-watchdog.timer

/var/log/letsencrypt-renew.log    # script output (also goes to journald)
```

## Install

From this directory, on the EC2 host (or via your deploy pipeline):

```bash
sudo apt-get update && sudo apt-get install -y msmtp ca-certificates

sudo mkdir -p /opt/letsencrypt-renew
sudo install -m 0750 -o root -g root renew.sh watchdog.sh notify.sh /opt/letsencrypt-renew/

# .env must be created out-of-band — never commit real creds.
# Copy .env.example, fill in SMTP_USER / SMTP_PASS, then:
sudo install -m 0600 -o root -g root .env /opt/letsencrypt-renew/.env

sudo install -m 0644 \
    letsencrypt-renew.service letsencrypt-renew.timer \
    letsencrypt-watchdog.service letsencrypt-watchdog.timer \
    /etc/systemd/system/

sudo systemctl daemon-reload
sudo systemctl enable --now letsencrypt-renew.timer letsencrypt-watchdog.timer
```

## Verification

```bash
# Both timers should appear with a NEXT time in the future
systemctl list-timers --all | grep letsencrypt

# Dry-run the renewer (no-op if cert is fresh, but exercises the whole path)
sudo systemctl start letsencrypt-renew.service
sudo journalctl -u letsencrypt-renew.service -n 50 --no-pager

# Confirm nginx is up and cert is intact
sudo systemctl status nginx || /opt/bitnami/ctlscript.sh status nginx
openssl x509 -enddate -noout -in /opt/bitnami/letsencrypt/certificates/api.chatcraft.cc.crt

# Force the watchdog to fire (set THRESHOLD_DAYS=999 temporarily) and confirm email arrives
sudo /opt/letsencrypt-renew/watchdog.sh
```

## Troubleshooting

- **Renewer fails, no email received:** check `/opt/letsencrypt-renew/.env` perms (`stat /opt/letsencrypt-renew/.env` should show `0600`). Run `sudo /opt/letsencrypt-renew/notify.sh "test" "test"` manually and watch `journalctl -t letsencrypt-notify`.
- **Lego fails to bind 443:** something other than nginx is holding the port. `sudo ss -tlnp | grep :443`.
- **Cert renewed but nginx still serves the old one:** the `start nginx` step failed. Check `journalctl -u letsencrypt-renew.service` and `/opt/bitnami/nginx/logs/error.log`.

## Notes

- The 12h cadence is Let's Encrypt's recommended check frequency. With `--days 30`, an actual renewal happens ~6× a year; the other ~700 invocations are no-ops.
- `RandomizedDelaySec=30min` spreads ACME requests across hosts so we don't hit Let's Encrypt rate-limits if multiple hosts ever share an account.
- For Docker-based deployments (banking-demo style), use a `certbot/certbot` sidecar container instead — same idea, different mechanism. Out of scope for this directory.
