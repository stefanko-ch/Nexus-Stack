---
title: "Entropy Data"
---

## Entropy Data

![Entropy Data](https://img.shields.io/badge/Entropy_Data-111827?logoColor=white)

**Registry for data products and data contracts**

Entropy Data, formerly Data Contract Manager, is the web registry for data products and the data contracts between them, in the [Open Data Contract Standard](https://bitol-io.github.io/open-data-contract-standard/). It comes from the makers of datacontract.com. Teams publish data products with their output ports. Consumers request access, and each agreement is a contract that the Data Contract CLI can test.

It is the shared place for what the [Data Contract Editor](datacontract-editor.md) and the [Data Contract CLI API](datacontract-api.md) work on locally.

| Setting | Value |
|---------|-------|
| URL | `https://entropy-data.<domain>` |
| Login | Your own account, created on the first visit |
| Admin | The stack user's email (Admin Console) |
| Persistence | Docker volume `entropy-data-db-data` |
| Licence | Entropy Data Community License — proprietary, not an OSI licence |
| Website | [entropy-data.com](https://www.entropy-data.com) |

### First steps

1. Open `https://entropy-data.<domain>`. It shows the sign-up page.
2. Create your account with **the same email as the stack user**. That email is in `APPLICATION_SUPERADMINS`, so the account gets the **Admin Console**.
3. Create your organization. Some vanity URLs are reserved: `test` was refused with "This vanity URL is not available" although no organization existed yet, so pick another name. Then create a team, a data product and a data contract. The contract editor accepts ODCS YAML. The [Data Contract CLI](datacontract-api.md) can test a contract against the data, for example in the [Postgres](postgres.md) stack.

**Signing up accepts Entropy Data's terms of use.** That is why the stack does not create the account for you.

### Accounts and access

- **Who can sign up:** anyone who gets past Cloudflare Access can create an account. Access is the gate.
- **Permissions:** in the Community Edition every user can edit every data product and contract (per Entropy Data's README). Use it as a shared workspace, not as a permission model.
- **Email:** sign-up sends a verification email. The account works without verifying it.
- **Where mail goes:** to a Mailpit inside the stack (`entropy-data-mail`), so sign-up does not fail on a missing SMTP server and no mail leaves the server. Invitations sent from the app land there too, so they cannot be delivered.

Tested:
- a fresh sign-up was logged in straight away;
- the super-admin email reached the Admin Console;
- the login worked after a restart;
- a wrong password was refused.

### Licence and telemetry

Entropy Data CE is under Entropy Data's [Community License](https://www.entropy-data.com/COMMUNITY-LICENSE.txt). It is royalty-free and forbids reverse engineering and working around its licence key. It is not an OSI licence.

The image ships an OpenTelemetry agent that is switched off (`OTEL_JAVAAGENT_ENABLED=false`). The pages served locally loaded no third-party scripts.

### Resources

The app used about 1 GB and its PostgreSQL (with pgvector) about 35 MB. The container limit is 2 GB.

### Persistence

Organizations, users, data products and contracts are in PostgreSQL (`entropy-data-db-data`).

- **`rebuild` (default): they do not survive a teardown.** Entropy Data is not in the R2 backup list. Contracts kept as YAML in Git survive regardless.
- **`snapshot`: they survive**, because the whole disk is imaged.
