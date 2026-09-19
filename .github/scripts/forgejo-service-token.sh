#!/usr/bin/env bash
# =============================================================================
# forgejo-service-token.sh — keep the Forgejo Access service token alive
# across a rebuild teardown (#892)
# =============================================================================
# The Cloudflare Access service token for Forgejo lives in the stack state,
# and `Lifecycle: Teardown` runs an untargeted `tofu destroy`. So every
# teardown destroyed the token and the next spin-up minted a replacement with
# a new client_id and client_secret. Anything outside the stack that
# authenticates to Forgejo with that pair — Nexus-Conductor, for one — stopped
# working at that moment, and stopped working silently: Access answers an
# unauthenticated call with a 302 to its login page, which reads like a URL
# problem rather than an authentication failure (#893).
#
# The token is a management-plane credential. Its lifetime is the relationship
# between the two systems, not the lifetime of a server. So it is taken out of
# the state before the destroy and put back on the next spin-up — the same
# trick `setup-control-plane.yaml` uses for the KV namespace.
#
# Only the REBUILD lifecycle needs this. `teardown-snapshot.yml` destroys
# `-target=hcloud_server.main` and nothing else, so the token was never at
# risk there.
#
# Usage:
#   forgejo-service-token.sh preserve   # in tofu/stack, before `tofu destroy`
#   forgejo-service-token.sh adopt      # in tofu/stack, before `tofu apply`
#   forgejo-service-token.sh purge      # anywhere, after a full destroy
#
# Environment:
#   DOMAIN                        the token's name is derived from it, exactly
#                                 as `local.resource_prefix` does in main.tf
#   CLOUDFLARE_API_TOKEN          adopt, purge
#   CLOUDFLARE_ACCOUNT_ID         adopt, purge
#   ENABLE_FORGEJO_SERVICE_TOKEN  adopt — "true" when the feature is on
#
# `preserve` and `adopt` expect the working directory to be `tofu/stack`, with
# OpenTofu initialised and the R2 backend credentials exported. `purge` talks
# only to the Cloudflare API and runs anywhere.
#
# WHAT THIS CANNOT RESTORE: the client_secret. Cloudflare returns it once, at
# creation — the provider's own documentation says an imported token "will not
# have the client_secret available in the state for use". That is not a gap
# here, because the point is that nobody needs a new one: the external system
# keeps the pair it was given. It does mean that after the first teardown,
# Infisical holds `forgejo_service_token_id` and no secret. `_filter_empty` in
# infisical.py drops the empty value rather than pushing a blank over the real
# one.
# =============================================================================
set -euo pipefail

RESOURCE='cloudflare_zero_trust_access_service_token.forgejo[0]'
API="https://api.cloudflare.com/client/v4"

ACTION="${1:-}"
case "$ACTION" in
  preserve | adopt | purge) ;;
  *)
    echo "❌ usage: forgejo-service-token.sh <preserve|adopt|purge>" >&2
    exit 1
    ;;
esac

# The name main.tf gives the token: "${local.resource_prefix}-forgejo-token",
# where resource_prefix is "nexus-${replace(var.domain, ".", "-")}".
token_name() {
  : "${DOMAIN:?forgejo-service-token.sh: DOMAIN is not set}"
  printf 'nexus-%s-forgejo-token' "${DOMAIN//./-}"
}

# Is the resource in the OpenTofu state? Read into a variable first: a
# `tofu state list | grep -q` pipeline would kill the writer with SIGPIPE
# under `pipefail` (#883).
in_state() {
  local state
  if ! state=$(tofu state list 2>&1); then
    echo "❌ Could not read the OpenTofu state:" >&2
    echo "   ${state:-(no output)}" >&2
    exit 1
  fi
  grep -qFx -- "$RESOURCE" <<< "$state"
}

# Every service token of that name, one id per line. Never prints the
# response: it carries the client_id of every token in the account.
token_ids() {
  : "${CLOUDFLARE_API_TOKEN:?forgejo-service-token.sh: CLOUDFLARE_API_TOKEN is not set}"
  : "${CLOUDFLARE_ACCOUNT_ID:?forgejo-service-token.sh: CLOUDFLARE_ACCOUNT_ID is not set}"
  local name body code
  name=$(token_name)
  body=$(mktemp)
  # The status goes in a variable of its own. A curl that fails while
  # writing nothing would otherwise be indistinguishable from an empty
  # list, and this function's emptiness is what decides whether a token
  # gets created.
  if ! code=$(curl -sS -o "$body" -w '%{http_code}' \
    -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
    "$API/accounts/${CLOUDFLARE_ACCOUNT_ID}/access/service_tokens?per_page=1000"); then
    rm -f "$body"
    echo "❌ Could not list Access service tokens (no HTTP status)." >&2
    exit 1
  fi
  if [ "$code" != "200" ]; then
    rm -f "$body"
    echo "❌ Listing Access service tokens returned HTTP $code." >&2
    echo "   The token needs Account > Access: Service Tokens > Read." >&2
    exit 1
  fi
  # Success and selection as two questions, rather than one filter that has
  # to encode a failure as a value: a 200 whose body says `"success": false`
  # would otherwise read as "no tokens", and a stack with a preserved token
  # would quietly mint a second one.
  if ! jq -e '.success == true' "$body" > /dev/null 2>&1; then
    rm -f "$body"
    echo "❌ Cloudflare returned 200 but did not report success for the token list." >&2
    exit 1
  fi
  local ids
  if ! ids=$(jq -r --arg n "$name" '[.result[]? | select(.name == $n) | .id] | .[]' "$body"); then
    rm -f "$body"
    echo "❌ Could not parse the Access service token list." >&2
    exit 1
  fi
  rm -f "$body"
  printf '%s' "$ids"
}

count_lines() {
  if [ -z "$1" ]; then
    echo 0
  else
    printf '%s\n' "$1" | wc -l | tr -d ' '
  fi
}

case "$ACTION" in
  preserve)
    if ! in_state; then
      echo "ℹ️  No Forgejo service token in the state — nothing to preserve."
      exit 0
    fi
    # Forgetting it, not deleting it: the token stays in Cloudflare, the
    # destroy that follows cannot reach it, and the next spin-up imports it
    # back. `destroy-all.yml` removes it by name, because by then it is
    # exactly this unmanaged object.
    if ! tofu state rm "$RESOURCE"; then
      echo "❌ ERROR: could not remove $RESOURCE from the state." >&2
      echo "   Refusing to continue: the destroy would take the token with it," >&2
      echo "   and every external system authenticating with it would break." >&2
      exit 1
    fi
    echo "✅ Forgejo service token preserved (removed from state, kept in Cloudflare)."
    ;;

  adopt)
    if [ "${ENABLE_FORGEJO_SERVICE_TOKEN:-}" != "true" ]; then
      echo "ℹ️  ENABLE_FORGEJO_SERVICE_TOKEN is not 'true' — nothing to adopt."
      exit 0
    fi
    if in_state; then
      echo "✅ Forgejo service token already in the state."
      exit 0
    fi

    IDS=$(token_ids)
    COUNT=$(count_lines "$IDS")
    case "$COUNT" in
      0)
        echo "ℹ️  No preserved Forgejo service token found — a new one will be minted."
        echo "   Its client id and secret land in Infisical under the forgejo folder;"
        echo "   the external management plane needs both."
        exit 0
        ;;
      1) ;;
      *)
        # Guessing here would hand the Access policy a credential the
        # external system does not hold — the same silent failure this
        # script exists to prevent, one level deeper.
        echo "❌ ERROR: $COUNT Access service tokens are named '$(token_name)'." >&2
        echo "   Refusing to guess which one the external management plane holds." >&2
        echo "   Delete the stale ones in the Cloudflare dashboard (Zero Trust >" >&2
        echo "   Access > Service Auth), leaving the one that is in use." >&2
        exit 1
        ;;
    esac

    if ! tofu import -var-file=config.tfvars "$RESOURCE" "${CLOUDFLARE_ACCOUNT_ID}/${IDS}"; then
      echo "❌ ERROR: could not import the preserved Forgejo service token." >&2
      echo "   Applying now would mint a replacement and silently invalidate" >&2
      echo "   the credential the external management plane holds." >&2
      exit 1
    fi

    # An import that succeeds but does not settle is the failure worth
    # catching: if applying would still replace the token, the credential
    # rotates anyway and nothing says so. `-detailed-exitcode` gives 0 for
    # no changes and 2 for changes; the plan redacts the secret.
    set +e
    PLAN=$(tofu plan -var-file=config.tfvars -target="$RESOURCE" \
      -detailed-exitcode -no-color -input=false 2>&1)
    PLAN_RC=$?
    set -e
    case "$PLAN_RC" in
      0)
        echo "✅ Forgejo service token adopted — unchanged, so the credential the"
        echo "   external management plane holds is still valid. Its secret was"
        echo "   issued once at creation and cannot be read again; Infisical"
        echo "   therefore shows the client id and no secret."
        ;;
      2)
        echo "❌ ERROR: applying would still change the adopted service token." >&2
        echo "   Refusing to continue — that would rotate the credential." >&2
        printf '%s\n' "$PLAN" >&2
        exit 1
        ;;
      *)
        echo "❌ ERROR: could not plan the adopted service token (exit $PLAN_RC)." >&2
        printf '%s\n' "$PLAN" >&2
        exit 1
        ;;
    esac
    ;;

  purge)
    IDS=$(token_ids)
    COUNT=$(count_lines "$IDS")
    if [ "$COUNT" = "0" ]; then
      echo "ℹ️  No Forgejo service token named '$(token_name)' — nothing to remove."
      exit 0
    fi
    # Deliberately deletes every match. This runs in destroy-all, whose
    # subject is "leave nothing behind"; the ambiguity that makes `adopt`
    # refuse is not a problem when the answer is to remove all of them.
    FAILED=0
    while IFS= read -r ID; do
      [ -n "$ID" ] || continue
      if ! CODE=$(curl -sS -o /dev/null -w '%{http_code}' -X DELETE \
        -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
        "$API/accounts/${CLOUDFLARE_ACCOUNT_ID}/access/service_tokens/${ID}"); then
        echo "❌ Deleting service token $ID produced no HTTP status." >&2
        FAILED=1
        continue
      fi
      case "$CODE" in
        200 | 204) echo "  ✅ removed preserved service token $ID" ;;
        404) echo "  ℹ️  service token $ID was already gone" ;;
        *)
          echo "❌ Deleting service token $ID returned HTTP $CODE." >&2
          FAILED=1
          ;;
      esac
    done <<< "$IDS"
    if [ "$FAILED" -ne 0 ]; then
      echo "❌ ERROR: at least one preserved Forgejo service token is still there." >&2
      echo "   Remove it in Zero Trust > Access > Service Auth." >&2
      exit 1
    fi
    ;;
esac
