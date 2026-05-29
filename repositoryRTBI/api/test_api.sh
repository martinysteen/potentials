#!/bin/bash
# Basic API smoke tests. Usage: bash test_api.sh <api-key> [base-url]
# Example: bash test_api.sh mysecretkey https://innovia.dk/rtbi-api

KEY="${1:?Usage: $0 <api-key> [base-url]}"
BASE="${2:-https://innovia.dk/rtbi-api}"

PASS=0
FAIL=0

pass() { echo "  PASS  $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL  $1"; FAIL=$((FAIL + 1)); }

check() {
    local label="$1" expected="$2" actual="$3"
    if echo "$actual" | grep -q "$expected"; then
        pass "$label"
    else
        fail "$label (expected '$expected' in response)"
        echo "        got: ${actual:0:200}"
    fi
}

echo "=== RTBI API tests against $BASE ==="
echo

# 1. No key → 403
echo "--- Auth ---"
R=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/files")
[ "$R" = "403" ] && pass "no key → 403" || fail "no key → expected 403, got $R"

# 2. Wrong key → 403
R=$(curl -s -o /dev/null -w "%{http_code}" -H "X-API-Key: wrong" "$BASE/files")
[ "$R" = "403" ] && pass "wrong key → 403" || fail "wrong key → expected 403, got $R"

# 3. List files → 200 + JSON array
echo
echo "--- Endpoints ---"
R=$(curl -s -H "X-API-Key: $KEY" "$BASE/files")
HTTP=$(curl -s -o /dev/null -w "%{http_code}" -H "X-API-Key: $KEY" "$BASE/files")
[ "$HTTP" = "200" ] && pass "GET /files → 200" || fail "GET /files → expected 200, got $HTTP"
check "GET /files returns array" "\[" "$R"

# 4. Pick first CSV from file list and test download + query
FIRST_CSV=$(echo "$R" | python3 -c "
import sys, json
files = json.load(sys.stdin)
if files:
    print(files[0]['path'])
" 2>/dev/null)

if [ -z "$FIRST_CSV" ]; then
    echo "  SKIP  no CSV files found yet (sync not run?)"
else
    echo "        Testing with: $FIRST_CSV"

    # Download
    HTTP=$(curl -s -o /dev/null -w "%{http_code}" -H "X-API-Key: $KEY" "$BASE/files/$FIRST_CSV")
    [ "$HTTP" = "200" ] && pass "GET /files/$FIRST_CSV → 200" || fail "GET /files/$FIRST_CSV → expected 200, got $HTTP"

    # Query (first 3 rows)
    R=$(curl -s -H "X-API-Key: $KEY" "$BASE/data/$FIRST_CSV?limit=3")
    HTTP=$(curl -s -o /dev/null -w "%{http_code}" -H "X-API-Key: $KEY" "$BASE/data/$FIRST_CSV?limit=3")
    [ "$HTTP" = "200" ] && pass "GET /data/$FIRST_CSV?limit=3 → 200" || fail "GET /data/$FIRST_CSV?limit=3 → expected 200, got $HTTP"
    check "query returns array" "\[" "$R"

    # Unknown column → 400
    HTTP=$(curl -s -o /dev/null -w "%{http_code}" -H "X-API-Key: $KEY" "$BASE/data/$FIRST_CSV?nonexistent_col=x")
    [ "$HTTP" = "400" ] && pass "unknown column filter → 400" || fail "unknown column filter → expected 400, got $HTTP"
fi

# 5. Non-existent file → 404
HTTP=$(curl -s -o /dev/null -w "%{http_code}" -H "X-API-Key: $KEY" "$BASE/files/does_not_exist.csv")
[ "$HTTP" = "404" ] && pass "missing file → 404" || fail "missing file → expected 404, got $HTTP"

echo
echo "=== Results: $PASS passed, $FAIL failed ==="
[ $FAIL -eq 0 ] && exit 0 || exit 1
