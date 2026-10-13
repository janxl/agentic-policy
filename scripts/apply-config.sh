#!/usr/bin/env bash
# Publish the config files to the cluster as the `app-config` ConfigMap:
#   policies.toml      the data policies the policy gate checks every request against
#   policy_cases.toml  synthetic requests for `make test-policy`
# Usage: scripts/apply-config.sh            (make up and make config call this for you)
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh" || exit 1
set -euo pipefail

FILES="policies.toml policy_cases.toml"
for f in $FILES; do [ -f "$ROOT/$f" ] || { echo "no $f at the repo root" >&2; exit 1; }; done
# Fail here, on your machine, if a file is not valid TOML, instead of in a crash-looping pod.
python3 - "$ROOT" $FILES <<'EOF'
import re, sys, tomllib
root, names = sys.argv[1], sys.argv[2:]
for name in names:
    try:
        with open(f"{root}/{name}", "rb") as f:
            cfg = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        sys.exit(f"{name} is not valid TOML: {e}")
    if name == "policies.toml":
        for p in cfg.get("policies", []):
            if p.get("action") not in ("local", "block"):
                sys.exit(f"policies.toml: policy {p.get('id')!r} needs action = \"local\" or \"block\"")
            for pat in p.get("patterns", []):
                try:
                    re.compile(pat)
                except re.error as e:
                    sys.exit(f"policies.toml: policy {p['id']!r} has a bad pattern {pat!r}: {e}")
EOF
args=""
for f in $FILES; do args="$args --from-file=$f=$ROOT/$f"; done
$KUBECTL -n "$NS" create configmap app-config $args --dry-run=client -o yaml | $KUBECTL apply -f -
