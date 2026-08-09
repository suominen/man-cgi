# @(#)$KimmoSuominen$
#
# Harness library for man-cgi tests. Sourced by the scripts in t/;
# callers must set TESTS_DIR (absolute path of the tests directory)
# before sourcing, then call test_init.
#
# 20260809  Kimmo Suominen
#

MANCGI="${MANCGI:-${TESTS_DIR}/../../sh/man-cgi}"
MANROOT="${TESTS_DIR}/fixtures/manroot"

# Expected Last-Modified values for fixture files; setup_fixtures()
# stamps the files to match (times are UTC).
LM_LS1='Fri, 02 Jan 2026 13:14:15 GMT'
LM_APM4='Sat, 03 Jan 2026 14:15:16 GMT'
LM_BUILD='Sun, 04 Jan 2026 15:16:17 GMT'
LM_CPUCTL4='Tue, 06 Jan 2026 17:18:19 GMT'
LM_BR_LS1='Mon, 05 Jan 2026 16:17:18 GMT'
LM_REL_LS1='Thu, 08 Jan 2026 19:20:21 GMT'

TAP_N=0
TAP_FAIL=0

test_init()
{
    TESTTMP=$(mktemp -d)
    trap 'rm -rf "${TESTTMP}"' EXIT
    # Signal traps must exit explicitly: POSIX resumes execution
    # after a non-EXIT trap action. The exit runs the EXIT trap.
    trap 'exit 1' INT TERM HUP
    setup_fixtures
}

setup_fixtures()
{
    TZ=UTC touch -t 202601021314.15 "${MANROOT}/NetBSD-current/man1/ls.1"
    TZ=UTC touch -t 202601031415.16 "${MANROOT}/NetBSD-current/man4/i386/apm.4"
    TZ=UTC touch -t 202601061718.19 "${MANROOT}/NetBSD-current/man4/x86/cpuctl.4"
    TZ=UTC touch -t 202601041516.17 "${MANROOT}/NetBSD-current/build"
    # The branch build file gets a stamp distinct from the branch
    # ls.1 so Last-Modified assertions can tell them apart.
    TZ=UTC touch -t 202601071819.20 "${MANROOT}/NetBSD-9.x-BRANCH/build"
    TZ=UTC touch -t 202601051617.18 "${MANROOT}/NetBSD-9.x-BRANCH/man1/ls.1"
    TZ=UTC touch -t 202601091021.22 "${MANROOT}/NetBSD-10.1/build"
    TZ=UTC touch -t 202601081920.21 "${MANROOT}/NetBSD-10.1/man1/ls.1"
}

# Run the CGI with PATH_INFO="${1}". Optional request parameters come
# from CGI_METHOD, CGI_QUERY, CGI_IMS, CGI_BODY (POST input),
# CGI_MANROOT, and CGI_GATEWAY (GATEWAY_INTERFACE, unset by default
# so the MANCGI_* overrides stay honored). Results: CGI_EXIT, plus
# out/err/hdrs/body files under ${TESTTMP}.
run_cgi()
{
    local pi rc
    pi="${1}"
    rc=0

    printf '%s' "${CGI_BODY:-}" |
    env -i \
	"PATH_INFO=${pi}" \
	"QUERY_STRING=${CGI_QUERY:-}" \
	"REQUEST_METHOD=${CGI_METHOD:-GET}" \
	"HTTP_IF_MODIFIED_SINCE=${CGI_IMS:-}" \
	"GATEWAY_INTERFACE=${CGI_GATEWAY:-}" \
	REQUEST_SCHEME=https \
	SERVER_NAME=man.netbsd.org \
	SERVER_PORT=443 \
	SCRIPT_NAME=/cgi-bin/man-cgi \
	DEFAULT_ARCH=NONE \
	DEFAULT_COLLECTION=NetBSD-current \
	"MANCGI_MANROOT=${CGI_MANROOT:-${MANROOT}}" \
	MANCGI_PATH=/usr/bin:/bin \
	sh "${MANCGI}" > "${TESTTMP}/out" 2> "${TESTTMP}/err" ||
    rc=$?

    CGI_EXIT="${rc}"
    awk '/^$/ { exit } { print }' "${TESTTMP}/out" > "${TESTTMP}/hdrs"
    sed -e '1,/^$/d' "${TESTTMP}/out" > "${TESTTMP}/body"
}

diag()
{
    sed -e 's/^/# /' "${1}" 1>&2
}

tap_pass()
{
    TAP_N=$((${TAP_N} + 1))
    echo "ok ${TAP_N} - ${*}"
}

tap_fail()
{
    TAP_N=$((${TAP_N} + 1))
    TAP_FAIL=$((${TAP_FAIL} + 1))
    echo "not ok ${TAP_N} - ${*}"
}

assert_exit()
{
    if [ "${CGI_EXIT}" -eq "${1}" ]
    then
	tap_pass "exit status is ${1}"
    else
	tap_fail "exit status is ${1} (got ${CGI_EXIT})"
	diag "${TESTTMP}/err"
    fi
}

assert_header()
{
    if grep -q -e "${1}" "${TESTTMP}/hdrs"
    then
	tap_pass "header matches: ${1}"
    else
	tap_fail "header matches: ${1}"
	diag "${TESTTMP}/hdrs"
    fi
}

assert_no_header()
{
    if grep -q -e "${1}" "${TESTTMP}/hdrs"
    then
	tap_fail "no header matches: ${1}"
	diag "${TESTTMP}/hdrs"
    else
	tap_pass "no header matches: ${1}"
    fi
}

assert_body()
{
    if grep -q -e "${1}" "${TESTTMP}/body"
    then
	tap_pass "body matches: ${1}"
    else
	tap_fail "body matches: ${1}"
	diag "${TESTTMP}/body"
    fi
}

assert_body_absent()
{
    if grep -q -e "${1}" "${TESTTMP}/body"
    then
	tap_fail "body does not match: ${1}"
	diag "${TESTTMP}/body"
    else
	tap_pass "body does not match: ${1}"
    fi
}

assert_no_body()
{
    if [ -s "${TESTTMP}/body" ]
    then
	tap_fail "body is empty"
	diag "${TESTTMP}/body"
    else
	tap_pass "body is empty"
    fi
}

test_done()
{
    echo "1..${TAP_N}"
    [ "${TAP_FAIL}" -eq 0 ]
}
