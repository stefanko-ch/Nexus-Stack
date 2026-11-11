#!/bin/bash
# =============================================================================
# Write values into tofu/stack/config.tfvars as data
# =============================================================================
# Usage:
#   tfvars-write.sh stack <file>          write the stack settings, from the
#                                         environment (see below)
#   tfvars-write.sh set <file> <key> <value>
#                                         append one `key = "value"` line
#
# Why this exists (#772). The action used to build config.tfvars by putting
# GitHub expressions straight into an unquoted heredoc. An expression is
# substituted textually before bash parses the line, so a value was source
# code, not data: a Docker Hub token containing a dollar sign was silently
# truncated, a backtick aborted the heredoc, and a quote became shell syntax.
#
# Here every value arrives in the environment or as an argument, which bash
# never re-expands, and is written as an HCL string literal with the
# characters HCL treats specially escaped. A value therefore reaches OpenTofu
# byte for byte.
#
# Environment read by `stack`:
#   SERVER_TYPE SERVER_LOCATION SERVER_IMAGE DOMAIN ADMIN_EMAIL USER_EMAIL
#   GUEST_EMAILS SUBDOMAIN_SEPARATOR GITHUB_OWNER GITHUB_REPO
#   ENABLE_FORGEJO_SERVICE_TOKEN DOCKERHUB_USERNAME DOCKERHUB_TOKEN
# =============================================================================

set -euo pipefail

# An HCL quoted string literal for "$1".
#   backslash and double quote are escaped with a backslash
#   dollar-brace and percent-brace start a template sequence in HCL and are
#   doubled
#   newline, carriage return and tab become their escapes
hcl_string() {
  local v=$1
  v=${v//\\/\\\\}
  v=${v//\"/\\\"}
  v=${v//\$\{/\$\$\{}
  v=${v//%\{/%%\{}
  v=${v//$'\n'/\\n}
  v=${v//$'\r'/\\r}
  v=${v//$'\t'/\\t}
  printf '"%s"' "$v"
}

# One `key = "value"` line. Keys are fixed strings from this repository, never
# input, and are checked anyway so a typo cannot write a malformed line.
tfvars_line() {
  local key=$1 value=$2 width=${3:-0}
  if ! [[ $key =~ ^[a-z][a-z0-9_]*$ ]]; then
    echo "❌ tfvars-write: not a valid variable name: '$key'" >&2
    return 1
  fi
  printf '%-*s = %s\n' "$width" "$key" "$(hcl_string "$value")"
}

write_stack() {
  local file=$1
  {
    echo "# Stack config (emails from secrets)"
    tfvars_line server_type "${SERVER_TYPE-}" 15
    tfvars_line server_location "${SERVER_LOCATION-}" 15
    tfvars_line server_image "${SERVER_IMAGE-}" 15
    echo
    # The tilde is written literally; OpenTofu expands it with pathexpand().
    # shellcheck disable=SC2088
    tfvars_line ssh_public_key_path "~/.ssh/id_ed25519.pub" 20
    # shellcheck disable=SC2088
    tfvars_line ssh_private_key_path "~/.ssh/id_ed25519" 20
    echo
    tfvars_line domain "${DOMAIN-}" 20
    tfvars_line admin_email "${ADMIN_EMAIL-}" 20
    tfvars_line user_email "${USER_EMAIL-}" 20
    tfvars_line guest_emails "${GUEST_EMAILS-}" 20
    tfvars_line subdomain_separator "${SUBDOMAIN_SEPARATOR-}" 20
    tfvars_line github_owner "${GITHUB_OWNER-}" 20
    tfvars_line github_repo "${GITHUB_REPO-}" 20
    # Compared against the literal 'true' rather than passed through: the
    # variable is typed bool in OpenTofu, and an unset repository variable
    # would otherwise write an empty string, which fails the plan instead of
    # meaning "off".
    if [ "${ENABLE_FORGEJO_SERVICE_TOKEN-}" = "true" ]; then
      echo 'enable_forgejo_service_token = true'
    else
      echo 'enable_forgejo_service_token = false'
    fi
    # Docker Hub credentials are optional, and only written as a pair.
    if [ -n "${DOCKERHUB_USERNAME-}" ] && [ -n "${DOCKERHUB_TOKEN-}" ]; then
      tfvars_line dockerhub_username "$DOCKERHUB_USERNAME" 18
      tfvars_line dockerhub_token "$DOCKERHUB_TOKEN" 18
    fi
  } > "$file"
}

case "${1-}" in
  stack)
    [ $# -eq 2 ] || { echo "usage: tfvars-write.sh stack <file>" >&2; exit 2; }
    write_stack "$2"
    ;;
  set)
    [ $# -eq 4 ] || { echo "usage: tfvars-write.sh set <file> <key> <value>" >&2; exit 2; }
    tfvars_line "$3" "$4" >> "$2"
    ;;
  *)
    echo "usage: tfvars-write.sh stack <file> | set <file> <key> <value>" >&2
    exit 2
    ;;
esac
