---
title: "What is Nexus Stack?"
description: "The short answer: what Nexus Stack deploys, who it is for, and what it deliberately is not"
order: 0
---

# What is Nexus Stack?

Nexus Stack deploys a working set of self-hosted services — databases, streaming,
orchestration, notebooks, BI, AI tooling — onto a single Hetzner Cloud server, puts
every one of them behind Cloudflare Zero Trust, and gives you a web UI to switch
them on and off. The whole thing is driven from GitHub Actions: you never run a
deploy command on your own machine.

Two properties are worth stating up front, because most of the design follows from
them:

- **The server has no open ports.** Not "the ports are firewalled" — the firewall
  ships with zero inbound rules and all traffic arrives through an outbound
  Cloudflare Tunnel. See [Security model](./security-model.md).
- **The infrastructure is disposable, the data is not.** Tearing down destroys the
  server; spinning up rebuilds it and restores the data. This is a normal daily
  operation, not a disaster path. See [Lifecycle](./lifecycle.md).

## The problem it solves

Running your own data or development environment usually forces a choice between
two bad options:

- **Rent a VPS and become its sysadmin.** You now own reverse proxies, TLS
  certificates, firewall rules, per-service logins, container updates, backups, and
  the open SSH port that everyone on the internet is scanning.
- **Pay per seat for managed SaaS.** Cheaper in effort, expensive per person, and
  your data lives somewhere you do not control.

Nexus Stack targets the case in between: you want a real environment — Postgres,
Kafka-compatible streaming, a pipeline orchestrator, notebooks, a BI tool — that
exists for a project, a class, or an evening, and that you can destroy and rebuild
without ceremony.

## What you get after one deploy

- A Hetzner Cloud server running Docker, provisioned by OpenTofu.
- A Cloudflare Tunnel, one subdomain per enabled service, TLS handled by Cloudflare.
- Cloudflare Access in front of every private service — email one-time-password
  login, no per-service user administration.
- A **Control Plane** web UI to enable and disable services, spin up and tear down
  the infrastructure, open TCP ports deliberately, and read generated credentials.
- 80+ optional service stacks to choose from — see the
  [stack catalogue](/docs/stacks/).
- Generated service passwords stored centrally in Infisical, never in the
  repository.
- No open ports, no public IP to defend, no manual TLS.

## What running it looks like

1. Fork or clone the repository and add your Hetzner, Cloudflare and Resend
   credentials as repository secrets.
2. Run the **Initial Setup** workflow. It deploys the Control Plane and the first
   server.
3. Open the Control Plane, enable the stacks you want, and let it redeploy.
4. Use the services at `https://<service>.yourdomain.com`, logging in with an email
   OTP.
5. Tear down when you are done — manually, or on a schedule. Spin up again when you
   need it.

The [Setup Guide](../admin-guides/setup-guide.md) is the step-by-step version.

## Who it is for

- **Self-hosters** who want a serious stack without becoming a full-time operator.
- **Teachers and workshop hosts** who need identical environments for a group, and
  who do not want to pay for them overnight.
- **Data and platform engineers** who want a disposable playground with the real
  tools rather than a laptop-sized imitation of them.

## What Nexus Stack is not

- **Not a managed service.** You own the Hetzner and Cloudflare accounts, the
  domain, and the bill. Nobody is on call for you.
- **Not multi-tenant.** One deployment is one environment for one group of trusted
  people. Isolating users from each other means giving each of them their own
  instance — that is what the companion project *Nexus-Stack for Education* does.
- **Not for your own hardware.** Provisioning depends on the Hetzner Cloud API. A
  homelab box cannot be a target.
- **Not Kubernetes.** Each service is a Docker Compose stack on one server. The
  scaling story is a bigger server, not a cluster.
- **Not a backup product**, although the persistence layer gives you most of one as
  a side effect.

## Where to go next

| You want to | Read |
|---|---|
| Understand how the pieces fit together | [Architecture](./architecture.md) |
| Understand teardown, spin-up, and what survives | [Lifecycle](./lifecycle.md) |
| Understand what a "stack" actually is | [Stacks and services](./stacks.md) |
| Understand the zero-open-ports claim | [Security model](./security-model.md) |
| Actually deploy it | [Setup Guide](../admin-guides/setup-guide.md) |
| Use a deployed instance | [Control Plane](../user-guides/control-plane.md) |
