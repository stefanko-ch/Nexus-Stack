---
title: "Firewall"
description: "Open TCP ports directly on the Hetzner server (bypasses Cloudflare Tunnel)"
order: 6
---

# Firewall

Most traffic reaches your stack through the **Cloudflare Tunnel**, which means zero open ports on the server itself. A few services — think a database client, a Kafka producer, or a Spark worker connecting over raw TCP — need direct port access. The Firewall page is where you allow that, carefully.

![Firewall page header warning that opened ports bypass the Cloudflare Tunnel security model](./assets/firewall-header.png)

> **Warning:** Opening a port exposes a service directly to the internet, bypassing Cloudflare Access and the Tunnel security model. Use this only when there's no way to go through the tunnel, and always constrain the source IP range.

## Configuring a rule

Each enabled stack that exposes TCP ports appears as a card. Each port entry has:

- **Toggle** — Enable or disable that specific port. Disabling a port removes the rule.
- **Source IPs** — CIDR range of allowed sources. Use `0.0.0.0/0` only if you really mean "anyone on the internet". Prefer restricting to your own IP.
- **Save** — Stages the change (not yet live). A change to the source IPs alone shows neither **STAGED** nor **PENDING** — those marks only appear when a port is switched on or off — but it still needs **Apply & Spin Up**; until then the previous range stays in force.

![Firewall card for a single-port service, with controls for enabling the port, entering a Source IPs CIDR range, and staging the change via Save](./assets/firewall-rule-single.png)

Services with multiple TCP ports (e.g. Redpanda with `kafka` and `schema-registry`) show each port as a separate entry in the same card, with the hostname the port is reached at. A port whose setting has changed, switched on or off, is marked **STAGED** until the change is applied. The card header carries two separate badges: **PENDING** whenever a port in the card has a staged change, and a count of how many ports are switched on (e.g. `1/2 OPEN`), shown only while at least one is. Switching off the last port therefore leaves **PENDING** without a count. The count is of the configuration you have staged, not of what is reachable right now: until **Apply & Spin Up** has run, the server still has the rules from before.

![Redpanda firewall card with two TCP ports (kafka, schema-registry), the kafka port marked STAGED, and a PENDING badge reading "1/2 OPEN" in the header](./assets/firewall-rule-multiple.png)

## Applying rules

Staged changes are not live until you click **Apply & Spin Up**. This triggers a GitHub Actions workflow that updates the Hetzner firewall and restarts the stack with the new rules.

![The Refresh and Apply & Spin Up buttons above the firewall cards; Apply & Spin Up commits staged rules and restarts the stack](./assets/firewall-apply.png)

Use **Refresh** to reload the current firewall state from the server.

## Rules reset on Teardown

Every Teardown resets all custom rules. This is a **safety feature**: if you forgot a wide-open port before tearing down, it won't silently re-appear on the next Spin Up. You have to re-add the rule deliberately.

## What's always allowed

- Outbound: all traffic (so the server can reach Docker Hub, Infisical, Cloudflare, etc.)
- Inbound: nothing, except what you add here

The Cloudflare Tunnel does not use inbound TCP — it's an outbound tunnel — so the tunnel keeps working even with zero rules.
