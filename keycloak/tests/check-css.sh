#!/usr/bin/env bash
# Cascade guard: gundi.css is shared by Keycloak 11 (PatternFly 3) and 26 (PatternFly 5),
# so it may only use #kc-* ids, element, attribute and pseudo selectors.
# Any framework class selector must live in kc11.css or kc26.css instead.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
file="$here/../themes/gundi/login/resources/css/gundi.css"
pattern='\.(pf-|btn|card-pf|login-pf|form-|alert|checkbox|control-label)'
if grep -nE "$pattern" "$file"; then
  echo "FAIL: framework class selectors found in $file (move them to kc11.css / kc26.css)" >&2
  exit 1
fi
echo "PASS: gundi.css has no framework class selectors"
