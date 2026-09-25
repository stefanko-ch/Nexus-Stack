# Cube data model

Every `.yml` file in this directory is part of the semantic layer. Cube reads
them from `/cube/conf/model`, where this directory is mounted **read-only**,
and `stack-sync` copies it to the server on every spin-up.

That is deliberate: a metric definition belongs in the repository that deploys
the stack, not in a container's filesystem where it drifts on one server and
exists nowhere else. Adding a cube is a commit.

## Adding one

1. Create `<name>.yml` here, next to `example.yml`.
2. Commit it and run a spin-up. `stack-sync` copies the directory; Cube picks
   the model up when its container restarts.
3. Query it through the SQL, REST or GraphQL API — see
   [docs/stacks/cube.md](../../../docs/stacks/cube.md) for how to sign a token.

## Trying something out first

Cube's own Playground would be the obvious place, and this stack does not run
it: it exists only in Cube's development mode, which upstream calls an
authentication bypass and says never to use in production.

To iterate quickly without a spin-up per edit, run Cube locally against the
same model:

```bash
docker run --rm -p 127.0.0.1:4000:4000 \
  -v "$PWD:/cube/conf/model" \
  -e CUBEJS_DEV_MODE=true \
  -e CUBEJS_DB_TYPE=postgres \
  -e CUBEJS_DB_HOST=host.docker.internal \
  -e CUBEJS_DB_NAME=postgres \
  -e CUBEJS_DB_USER=nexus-postgres \
  -e CUBEJS_DB_PASS=... \
  cubejs/cube:v1.7.42
```

The port is bound to `127.0.0.1` on purpose: that command turns development
mode on, which is an authentication bypass, and `-p 4000:4000` would offer the
warehouse behind it to anyone on the same network.

Development mode on a laptop is what upstream recommends it for. The
Playground at `localhost:4000` will also generate a first cube from the tables
it finds, which is a reasonable way to produce a file to commit.
