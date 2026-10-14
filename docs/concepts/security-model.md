---
title: "Security model"
description: "Why zero open ports is a property rather than a slogan, and what it does not protect you from"
order: 4
---

# Security model

The headline claim is that a deployed Nexus Stack server has **no open ports**. It
is worth taking that apart, because the useful part is not the claim itself but the
mechanism behind it — and the parts it does not cover.

## What "zero open ports" actually means

The Hetzner firewall attached to the server (`hcloud_firewall.main` in
`tofu/stack/main.tf`) is created with **no inbound rules at all**. Not a narrow
allow-list — an empty one. Inbound rules exist only when you deliberately add them
from the Control Plane's Firewall page.

Traffic still reaches your services because `cloudflared` on the server opens an
**outbound** connection to Cloudflare and requests arrive back down it. A connection
the server established itself needs no inbound rule, which is what makes an empty
firewall compatible with a working website.

So the security property is not "we closed the ports". It is that there was never a
path in from the outside to close.

## The SSH exception, and how it closes

A brand-new server cannot install a tunnel over a tunnel that does not exist yet.
The first minutes therefore look different:

1. A separate firewall opening port 22 is attached to the server through the Hetzner
   API — only for this window.
2. OpenTofu connects over SSH and installs the Cloudflare Tunnel connector.
3. Once the tunnel is up, the SSH firewall is detached again.

From then on SSH goes through the tunnel — `ssh nexus` works, and port 22 is not
reachable from the internet. That detached state is a normal part of the lifecycle,
not an anomaly, which is exactly why the empty inbound rule set matters: it is the
only thing standing in front of a published container port.

## Who gets in

Every private service sits behind a Cloudflare Access application with an email
one-time-password policy, created by OpenTofu from the service list. Practically:

- **You never administer per-service users.** Access decides whether a request ever
  reaches the container. The list of allowed emails is deployment-wide.
- **Sessions are time-boxed** — 24 hours for ordinary services, one hour for Wetty,
  which is a shell in a browser.
- **Headless access uses service tokens**, not passwords, so CI and automation can
  reach what they need without a human at an inbox. One exists for SSH (paired with
  short-lived certificates), one for Infisical, and one — opt-in, off by default —
  for Forgejo's API, so an external management plane can call it server-to-server.
  Each is scoped to a single Access application; there is no general-purpose token
  that opens everything.
- **`public: true` opts a service out** of Access entirely, and it then answers to
  the whole internet with only its own authentication. Exactly one shipped stack
  does this, and adding a second one deserves a hard look.

### The Control Plane checks for itself

The Control Plane is not a container behind the tunnel — it is a Cloudflare Pages
project, and that makes it the one component where "Access is in front of it" is
not a complete answer.

A Pages project answers on more than its custom domain: also on
`<project>.pages.dev`, and on one hostname per preview deployment. OpenTofu creates
the Access application for `control.<domain>`, and an Access application covers the
hostname it names. So the Control Plane does three things in its own code rather
than relying on what sits in front of it:

- **It answers on one hostname.** A request that arrives on any other hostname gets
  a 404 — not a redirect, which would confirm which hostname is the real one. The
  check derives the expected hostname from the deployment's own configuration, so it
  covers hostnames nobody has enumerated.
- **It verifies the Access token** rather than reading the identity header Cloudflare
  adds. The RS256 signature is checked against the JWKS your Access team publishes,
  along with the issuer, the application's AUD tag and the expiry. An identity header
  is something a caller can set; a signature is not.
- **It authorizes per endpoint**, in three tiers. Access answers *whether*
  someone reaches the Control Plane; it does not distinguish the admin from a
  student. So destroying infrastructure and opening firewall ports require the
  admin identity; starting the stack and reading secret values require the admin
  or one of the configured user addresses; and the reads every role is meant to
  have — status, the stack list, logs — require a verified Access session for
  this application without comparing the identity to a list, because guest
  addresses go to the Access policy and are never pushed to the Control Plane.
  Endpoints with no identity requirement at all — the health check and the
  version banner — are listed as such in a test that fails if a new one appears.

Access itself covers only `control.<domain>`, the one hostname OpenTofu creates an
application for. The other two kinds are closed by the hostname check, and that
division is deliberate rather than an omission: an Access application for
`<project>.pages.dev` was written and then removed, because owning it means owning
whatever policy an operator already attached to that hostname — and on the first
real deployment that turned out to be a *reusable* account-level policy shared with
other applications, which the plan would have renamed and had its email list
rewritten. Cloudflare refused the update, which is the only reason it did not
happen. The per-deployment preview hostnames could never have been covered by a
single Access application anyway, since their names are not known in advance.

So the hostname check is not a second layer behind Access on these hostnames. It is
the layer. An operator who also wants an Access prompt on `pages.dev` can keep one
in the dashboard, and nothing in this repository will fight them for it.

If the Control Plane cannot verify a token — because `ACCESS_AUD` or
`ACCESS_TEAM_DOMAIN` is missing — it denies every request and names the missing
value. That direction is deliberate: a locked-out operator notices within seconds,
a trusted header does not.

## Two worlds of credentials

Nexus Stack keeps infrastructure credentials and service credentials strictly apart,
and the separation is one of the more important design decisions in the project.

| | Repository secrets | Infisical (on the server) |
|---|---|---|
| Contains | Credentials that *build* infrastructure: Hetzner, Cloudflare, R2, the SSH key | Credentials that *services* use: database passwords, admin logins |
| Read by | The workflow runner | The Control Plane, and the people using the stacks |
| Set by | The operator, before the first run | Generated by OpenTofu on every spin-up |

**No Hetzner or Cloudflare API token is ever written to Infisical or reachable from
the application stacks.** Somebody using a deployed stack — a student, a workshop
participant, a colleague — cannot get from it to the account that pays for it.

One nuance that a strict reading requires: the server does hold a Cloudflare *tunnel
token*, written into the connector's systemd unit, because a tunnel cannot connect
without one. It authorises that single tunnel and nothing else — it cannot read the
account or touch DNS.

The [Setup Guide](../admin-guides/setup-guide.md) has the full table and the exact
list of secrets.

## The real boundary is push access

Repository secrets cannot be read back through the UI or the API, and the runner
masks them in logs. That protects against accidents, not against intent: **anyone
who can push a workflow to the repository can make it print those secrets.**

So the question that decides who controls your infrastructure is not who can view a
settings page. It is who can push to the repository and who can approve a pull
request.

## When you open a port on purpose

TCP services — a Kafka broker, Postgres, an S3 API — cannot be reached through an
HTTP tunnel. Opening one from the Control Plane creates a real inbound firewall rule
and an unproxied DNS `A` record to the server's IP. Three things are then true:

- The service is exposed to the source ranges you allowed, which you have to narrow
  yourself; the rule requires an explicit list rather than silently meaning
  "everyone".
- **Cloudflare Access is not in front of it.** Authentication is whatever that
  service brings.
- The rule is reset on every teardown, so an exception opened for an afternoon does
  not quietly survive for months.

## What this does not protect you from

An honest security page needs this section.

- **A compromised Cloudflare or Hetzner account.** Everything here assumes those
  accounts are yours. Two-factor authentication on both is not optional.
- **Anyone with push access to the repository** — see above.
- **The people you let in.** Access decides *whether* someone reaches a service, not
  what they may do inside it. Everyone on the allowed-email list is effectively an
  administrator of every enabled stack. The Control Plane is the exception —
  it separates the admin from the other operators — but the stacks themselves are
  not role-aware.
- **A stack's own vulnerabilities.** Images are pinned, but pinned is not patched. A
  long-lived deployment needs someone to update them.
- **Containers publishing ports on all host interfaces.** Most stacks bind published
  ports on every interface, so the empty firewall is the only layer between them and
  the internet. It is a single layer that works — and hardening it is tracked in
  [issue #742](https://github.com/stefanko-ch/Nexus-Stack/issues/742).
- **Data you put somewhere ephemeral.** Losing data is a security outcome too; see
  [Lifecycle](./lifecycle.md).

## Related reading

- [Architecture](./architecture.md) — where each piece sits
- [Setup Guide](../admin-guides/setup-guide.md) — secrets, tokens, and what to set where
- [SSH access](../admin-guides/ssh-access.md) — reaching the server through the tunnel
- [Firewall](../user-guides/firewall.md) — opening a TCP port from the Control Plane
