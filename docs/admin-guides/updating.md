---
title: "Updating to a New Release"
description: "Move a stack to a newer Nexus-Stack release: tear down, update the code, spin up"
order: 8
---

# Updating to a New Release

A stack runs the code of its own repository. To move it to a newer
Nexus-Stack release, you tear the stack down, update the code, and spin it
up again. A running stack is never updated in place.

**Before you start**, read the release notes of every release between your
version and the target, on the
[releases page](https://github.com/stefanko-ch/Nexus-Stack/releases). A
release can change a stack in a way that matters for your data. Deciding
whether to update, and when, is yours; the workflow does not interpret the
notes.

**Once:** create the secret `UPSTREAM_UPDATE_TOKEN`:

1. **GitHub** → **Settings** → **Developer settings** → **Personal access tokens** → **Fine-grained tokens** → **Generate new token**
2. **Repository access**: only this stack's repository
3. **Repository permissions**: **Contents** → *Read and write*, **Workflows** → *Read and write*
4. Save it as the repository secret `UPSTREAM_UPDATE_TOKEN`

It needs *Workflows* because every release changes files under
`.github/workflows/`, which GitHub does not let the default workflow token
change. The same permission lets its holder rewrite any workflow, and
through that reach every secret of the repository, so keep it in this one
secret and do not reuse it elsewhere.

**Each update:**

1. Run **Lifecycle: Teardown** and wait for it to succeed.
2. Run **Ops: Update from Upstream**. Leave *ref* empty for the latest
   release, or give a tag such as `v0.81.1`. The workflow:
   - refuses unless the most recent lifecycle run is a successful teardown
     (or destroy-all);
   - moves `main` to the release by a fast-forward. It never merges,
     rebases or force-pushes;
   - runs **Setup: Control Plane** on the new code and waits for it. That
     brings the Worker, the D1 schema and the list of stacks up to date.
     After a destroy-all it only moves the code, and the next Initial Setup
     builds the Control Plane from it.
3. Run **Lifecycle: Spin Up** when you are ready.

The workflow stops with a message, and changes nothing, when:

| Message | Meaning |
|---|---|
| *The stack is running* | Tear it down first. |
| *main has commits that … does not contain* | Your repository has its own changes. Changes of your own are yours to carry: merge them yourself, or remove them. |
| *main and … share no history* | Your repository was created as a copy. See below. |
| *The push was refused* | `main` changed during the run, or the token lacks *Workflows* write. |

An older release than the one you run is never applied: the workflow
reports that `main` already contains it.

**The first update.** The workflow exists in your repository only from the
release that introduced it on. If your repository is older, fast-forward it
by hand once, with the stack torn down:

```bash
git clone https://github.com/<you>/<your-repo>.git && cd <your-repo>
git fetch --no-tags https://github.com/stefanko-ch/Nexus-Stack.git tag vX.Y.Z
git merge --ff-only FETCH_HEAD
git push origin main
```

Then run **Setup: Control Plane**, and spin up.

**A repository created as a copy** (for example with the former "Use this
template" button) starts with a commit of its own and shares no history
with Nexus-Stack. It has to adopt that history once. This replaces `main`,
so do it with the stack torn down, and only if `main` holds nothing of your
own that you want to keep:

```bash
git clone https://github.com/<you>/<your-repo>.git && cd <your-repo>
git log --oneline            # check: nothing of your own you still need
git fetch --no-tags https://github.com/stefanko-ch/Nexus-Stack.git tag vX.Y.Z
git push --force origin "vX.Y.Z^{commit}:refs/heads/main"
```

The `^{commit}` matters: a release tag is an annotated tag, and a branch
can only point at the commit behind it.

Branch protection on `main` refuses the forced push; lift it for this one
step. Secrets, variables and past Actions runs are settings of the
repository and are not affected. Then run **Setup: Control Plane**, and spin
up. From then on the update workflow works.

The workflow runs on GitHub only. A stack whose repository lives on a
Forgejo instance, as Nexus-Conductor's user stacks do, is updated by the
system that manages it.
