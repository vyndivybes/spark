# Capability 02 — WhatsApp messaging: options, costs and risks

Status: **implemented (consent-gated, disabled by default) — live send NOT verified.**
Verified live sending requires the founder's own credentials and explicit
consent recorded at runtime (`spark_messaging_hub.MessagingHub.approve_outbound`).

## Path A — Official Meta WhatsApp Business Cloud API (`whatsapp`)

* Requires: a Meta Business account, an approved phone number, and a
  Cloud API access token (`access_token`, `phone_number_id` config keys).
* Cost reality: Cloud API conversation pricing is **not free** at general
  scale; service/utility/marketing conversations are billed by Meta, and the
  free tier for user-initiated (service) conversations has changed repeatedly.
  Eligibility is size and geography dependent. SPARK therefore refuses to
  send until the user stores `understood_pricing: true` in the channel
  configuration, and the status display never claims zero-cost WhatsApp
  messaging.
* Inbound: requires an owner-controlled webhook endpoint registered with
  Meta. SPARK polls nothing and fabricates no inbound events; `receive()`
  fails with an explicit "configure a webhook" error.

## Path B — Unofficial bridge, e.g. Baileys-based open-source bridges (`whatsapp_bridge`)

* Requires: a self-hosted bridge process on the user's machine
  (`bridge_url`) and explicit informed opt-in (`understood_risks: true`).
* Security/account risks assumed by the user under this option:
  - linked-device sessions can be banned by WhatsApp;
  - unofficial bridges are against WhatsApp's terms of service;
  - session tokens live in the bridge process and can be exfiltrated;
  - message delivery/encryption guarantees are not Meta-backed.
* SPARK treats the bridge adapter as an informed-only experiment;
  inbound via bridge is deliberately not implemented.

## What the hub enforces regardless of path

1. Sender/recipient allowlist per channel; unknown senders are audited and
   flagged, never actioned automatically.
2. Every outbound message needs an exact, single-use owner approval with a
   10-minute TTL, recorded in the local approval ledger before any transport
   call, then marked used.
3. Rate limit: 50 accepted sends per channel per hour, sliding window.
4. Full local audit: direction, IDs, recipient, state, error and time for
   every attempt (including rejections and auth failures).
5. Status vocabulary: `configured, untested` → `connected` only after a
   verified successful send; failures accumulate and set `failed`.

## Accepted live testing evidence (when performed)

To move this capability from implemented/unverified to verified, run a real
send to the founder's own number with recorded approval ID, provider message
ID and timestamp, plus one deliberate failure case (revoked token) captured
by the audit. Post the observable JSON from `hub_history` for that date.
