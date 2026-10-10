# Prospecting delivery operations

Prospecting uses the organization's existing SMTP sender/configuration and existing signed Resend webhook. It does not store another SMTP password or webhook secret and does not change M3 procurement outreach.

## Celery Beat requirement

The application defines `prospecting.process_due_messages` on a five-minute Beat schedule. The existing production worker does not schedule periodic tasks by itself. Before enabling automatic Prospecting follow-ups, install a dedicated Beat service deliberately:

The template uses the established `bbdeploy` account, production backend environment, backend virtualenv, and a persistent schedule under `/var/lib/bb-builders` created by systemd.

Install it once after the application deployment:

```sh
sudo cp /opt/bb-builders/app/infra/systemd/bb-builders-celery-beat.service.template /etc/systemd/system/bb-builders-celery-beat.service
sudo systemctl daemon-reload
sudo systemctl enable --now bb-builders-celery-beat.service
systemctl is-active bb-builders-celery-beat.service
sudo journalctl -u bb-builders-celery-beat.service -n 100 --no-pager
```

The normal deployment workflow intentionally does not require or restart this service yet. Until installation, an Admin may use **Process due sends now**, or an operator may run `python manage.py process_due_prospecting --limit 50` in the production environment. Both paths use the same bounded, idempotent delivery service.

Never run more than one Beat scheduler against the same schedule. Workers may run concurrently because due processing uses durable message/attempt identities, row locking where supported, and suppression checks before delivery.

## Enablement checklist

- Existing organization SMTP configuration and sender identity are enabled.
- Existing Resend webhook and signing secret are configured for delivery, engagement, complaint, bounce, and received-email events.
- `FRONTEND_ORIGIN` is the public HTTPS application origin used for unsubscribe links.
- Prospecting Settings contains business identity, contact footer, conservative hourly/daily limits, timezone, and sending window.
- Prospecting is enabled only after a controlled test campaign has been manually validated.

## Resend production setup

1. Create or select the production Resend API key.
2. Save it through **Settings → Integrations → Resend Email & Tracking**; the credential is encrypted and never returned.
3. Configure an enabled, verified sender identity.
4. Copy the HTTPS BB Builders webhook endpoint displayed in Settings into Resend.
5. Subscribe to sent, delivered, delivery delayed, opened, clicked, bounced, failed, complained, and received events.
6. Copy the Resend `whsec_` signing secret into BB Builders and enable verified webhook handling.
7. Enable open tracking in the Resend domain configuration if required.
8. Enable click tracking in the Resend domain configuration if required.
9. Run the explicit SMTP connection test.
10. Send one explicitly addressed controlled test email.
11. Confirm the first signed provider event changes tracking health from awaiting events to active.

Opening Settings is read-only and never contacts Resend. M3 Outreach and Prospecting deliberately share the same encrypted organization SMTP/API credential, sender identity, and signed webhook configuration.

The product provides technical suppression and unsubscribe controls. It does not claim legal compliance; campaign content and audience remain a human/business responsibility.

## Production worker topology

The normal `bb-builders-celery` worker consumes only the `celery` queue using the default prefork pool, concurrency 3. AI page processing is isolated in `bb-builders-celery-analysis.service` with the threads pool, concurrency 6, prefetch multiplier 1, and queues `analysis-pages,analysis-synthesis`. Its template sets `AI_PAGE_CONCURRENCY=6`, loads `/opt/bb-builders/secrets/backend.env`, restarts on failure, and is enabled at boot. Install it once using the same copy/daemon-reload/enable pattern as Beat.

The analysis and Beat units are `PartOf=bb-builders-celery.service`, so restarting the main worker also restarts installed companion units. The GitHub deployment intentionally restarts only services already permitted by production sudoers; it must not be expanded until sudoers explicitly permits the companion units.
