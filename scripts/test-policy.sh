#!/usr/bin/env bash
# Run the policy gate over the synthetic requests in policy_cases.toml, inside the agent pod, and report
# what plain rules catch and what the decision model adds. Takes no parameters.
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh" || exit 1
in_agent < "$ROOT/scripts/policy_test.py"
