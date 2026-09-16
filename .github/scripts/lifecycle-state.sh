#!/usr/bin/env bash
# =============================================================================
# lifecycle-state.sh — is this stack up, torn down, destroyed, or busy?
# =============================================================================
# Reads a JSON document `{"workflow_runs": [...]}`, shaped like the GitHub
# runs API, on stdin, and prints one word:
#
#   busy        a lifecycle run is queued or in progress
#   deployed    the most recent lifecycle run is a successful spin-up or setup
#   torn-down   the most recent lifecycle run is a successful teardown
#   destroyed   the most recent lifecycle run is a successful destroy-all
#   unknown     no lifecycle run at all, the most recent one did not succeed,
#               or runs of different kinds share the most recent start time
#
# The inputs are those of the Control Plane's checkInfraStatus
# (control-plane/worker/src/index.js). The mapping is stricter: that
# function reports a failed spin-up as deployed and a failed teardown as
# deployed too. Here any unsuccessful last run is `unknown`, because the
# caller only proceeds on a state it can be sure of.
#
# Both lifecycle pairs (rebuild and snapshot) are recognised, whichever one
# the stack uses. A snapshot run calls spin-up.yml / teardown.yml as a
# reusable workflow, which does not create a run of its own, so the
# snapshot file names are what appear in the list.
# =============================================================================
set -euo pipefail

jq -r '
  def family:
    (.path // "" | split("/") | last) as $file
    | if   ($file | IN("spin-up.yml", "spin-up-snapshot.yml", "initial-setup.yaml")) then "deployed"
      elif ($file | IN("teardown.yml", "teardown-snapshot.yml")) then "torn-down"
      elif $file == "destroy-all.yml" then "destroyed"
      else null end;

  [ (.workflow_runs // [])[] | select(family != null) | . + {family: family} ] as $runs
  | if ($runs | any(.status != "completed")) then "busy"
    else
      ($runs | sort_by(.created_at) | last) as $last
      | if $last == null then "unknown"
        # Two families started in the same second: which came last is not
        # knowable from the list, so neither answer is trusted.
        elif ([$runs[] | select(.created_at == $last.created_at) | .family] | unique | length) > 1
          then "unknown"
        elif $last.conclusion != "success" then "unknown"
        else $last.family end
    end
'
