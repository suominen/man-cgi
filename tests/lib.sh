# @(#)$KimmoSuominen$
#
# Harness library for man-cgi tests. Sourced by the scripts in t/;
# callers must set TESTS_DIR (absolute path of the tests directory)
# before sourcing, then call test_init.
#
# 20260809  Kimmo Suominen
#

MANCGI="${MANCGI:-${TESTS_DIR}/../src/man-cgi}"
MANROOT="${TESTS_DIR}/fixtures/manroot"

# Expected Last-Modified values for fixture files; setup_fixtures()
# stamps the files to match (times are UTC).
LM_LS1='Fri, 02 Jan 2026 13:14:15 GMT'
LM_APM4='Sat, 03 Jan 2026 14:15:16 GMT'
LM_BUILD='Sun, 04 Jan 2026 15:16:17 GMT'
# Collection stamps (tmac/mdoc.local): the validator for 404s and
# multi-match menus. Deliberately distinct from the build stamps,
# so an assertion cannot pass against the wrong file.
LM_MDOC='Wed, 28 Jan 2026 09:10:11 GMT'
LM_BR_MDOC='Thu, 29 Jan 2026 10:11:12 GMT'
LM_REL_MDOC='Fri, 30 Jan 2026 11:12:13 GMT'
LM_CPUCTL4='Tue, 06 Jan 2026 17:18:19 GMT'
LM_BOOT8_X86='Mon, 12 Jan 2026 13:14:15 GMT'
LM_BOOT8='Tue, 13 Jan 2026 14:15:16 GMT'
LM_STAT1='Wed, 14 Jan 2026 15:16:17 GMT'
LM_STAT2='Thu, 15 Jan 2026 16:17:18 GMT'
LM_MUX8='Fri, 16 Jan 2026 17:18:19 GMT'
LM_MUX4_I386='Sat, 17 Jan 2026 18:19:20 GMT'
LM_MUX4_X86='Sun, 18 Jan 2026 19:20:21 GMT'
LM_BR_BOOT8='Mon, 19 Jan 2026 10:11:12 GMT'
LM_BR_BOOT8_X86='Tue, 20 Jan 2026 11:12:13 GMT'
LM_ZAP0='Wed, 21 Jan 2026 12:13:14 GMT'
LM_ZAP1='Thu, 22 Jan 2026 13:14:15 GMT'
LM_ZIT1='Fri, 23 Jan 2026 14:15:16 GMT'
LM_ZIT0='Sat, 24 Jan 2026 15:16:17 GMT'
LM_ZIT3F='Sun, 25 Jan 2026 16:17:18 GMT'
LM_ZIT9LUA='Mon, 26 Jan 2026 17:18:19 GMT'
LM_BOOT8_CATS='Tue, 27 Jan 2026 18:19:20 GMT'
LM_BR_LS1='Mon, 05 Jan 2026 16:17:18 GMT'
LM_BR_BUILD='Wed, 07 Jan 2026 18:19:20 GMT'
LM_REL_LS1='Thu, 08 Jan 2026 19:20:21 GMT'
LM_ARCHLIST='Sat, 10 Jan 2026 11:12:13 GMT'
LM_COLLLIST='Sun, 11 Jan 2026 12:13:14 GMT'

# Pinned MINLASTMOD floor for the suite (see t/minlastmod): fixed,
# and below every fixture stamp above so file mtimes stay the
# operative validators throughout the suite.
MINLASTMOD_EPOCH=1767261600
LM_MINLASTMOD='Thu, 01 Jan 2026 10:00:00 GMT'

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
    # Multi-match fixtures (t/multi-match): boot(8) exists both
    # machine-independently and in the x86 machine class, stat
    # exists in sections 1 and 2, and mux resolves to three files
    # under i386. The machine-independent boot page is stamped
    # *newer* than the x86 page that shadows it, so a served page's
    # own mtime is distinguishable from the newest match's.
    TZ=UTC touch -t 202601121314.15 "${MANROOT}/NetBSD-current/man8/x86/boot.8"
    TZ=UTC touch -t 202601131415.16 "${MANROOT}/NetBSD-current/man8/boot.8"
    TZ=UTC touch -t 202601141516.17 "${MANROOT}/NetBSD-current/man1/stat.1"
    TZ=UTC touch -t 202601151617.18 "${MANROOT}/NetBSD-current/man2/stat.2"
    TZ=UTC touch -t 202601161718.19 "${MANROOT}/NetBSD-current/man8/mux.8"
    TZ=UTC touch -t 202601171819.20 "${MANROOT}/NetBSD-current/man4/i386/mux.4"
    TZ=UTC touch -t 202601181920.21 "${MANROOT}/NetBSD-current/man4/x86/mux.4"
    TZ=UTC touch -t 202601191011.12 "${MANROOT}/NetBSD-9.x-BRANCH/man8/boot.8"
    TZ=UTC touch -t 202601201112.13 "${MANROOT}/NetBSD-9.x-BRANCH/man8/x86/boot.8"
    # Preformatted fixtures: zap exists in both forms (one page,
    # two files), zit only as source in section 1 and only
    # preformatted in section 5.
    TZ=UTC touch -t 202601211213.14 "${MANROOT}/NetBSD-current/cat1/zap.0"
    TZ=UTC touch -t 202601221314.15 "${MANROOT}/NetBSD-current/man1/zap.1"
    TZ=UTC touch -t 202601231415.16 "${MANROOT}/NetBSD-current/man1/zit.1"
    TZ=UTC touch -t 202601241516.17 "${MANROOT}/NetBSD-current/cat5/zit.0"
    # zit also covers the section directories that are not just
    # man plus a digit, and cats covers an arch whose name would
    # be swallowed by a cat* section pattern.
    TZ=UTC touch -t 202601251617.18 "${MANROOT}/NetBSD-current/man3f/zit.3f"
    TZ=UTC touch -t 202601261718.19 "${MANROOT}/NetBSD-current/man9lua/zit.9lua"
    TZ=UTC touch -t 202601271819.20 "${MANROOT}/NetBSD-current/man8/cats/boot.8"
    TZ=UTC touch -t 202601041516.17 "${MANROOT}/NetBSD-current/build"
    # The branch build file gets a stamp distinct from the branch
    # ls.1 so Last-Modified assertions can tell them apart.
    TZ=UTC touch -t 202601071819.20 "${MANROOT}/NetBSD-9.x-BRANCH/build"
    TZ=UTC touch -t 202601051617.18 "${MANROOT}/NetBSD-9.x-BRANCH/man1/ls.1"
    TZ=UTC touch -t 202601081920.21 "${MANROOT}/NetBSD-10.1/man1/ls.1"
    TZ=UTC touch -t 202601101112.13 "${MANROOT}/archlist"
    TZ=UTC touch -t 202601111213.14 "${MANROOT}/colllist"
    # NetBSD-10.1 has no build file on purpose: frozen releases do
    # not get one, only NetBSD-current and the branches do.
    TZ=UTC touch -t 202601280910.11 "${MANROOT}/NetBSD-current/tmac/mdoc.local"
    TZ=UTC touch -t 202601291011.12 "${MANROOT}/NetBSD-9.x-BRANCH/tmac/mdoc.local"
    TZ=UTC touch -t 202601301112.13 "${MANROOT}/NetBSD-10.1/tmac/mdoc.local"
}

# Run the CGI with PATH_INFO="${1}". Optional request parameters come
# from CGI_METHOD, CGI_QUERY, CGI_IMS, CGI_BODY (POST input),
# CGI_MANROOT, CGI_MINLASTMOD (overrides the pinned MINLASTMOD
# floor), and CGI_GATEWAY (GATEWAY_INTERFACE, unset by default
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
	"MANCGI_MINLASTMOD=${CGI_MINLASTMOD:-${MINLASTMOD_EPOCH}}" \
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

# Assert that the first body line matching the first pattern comes
# before the first line matching the second: greps are unordered,
# and some markup is only correct in one order.
assert_body_before()
{
    local first second
    first=$(grep -n -e "${1}" "${TESTTMP}/body" | sed -e 1q | cut -d: -f1)
    second=$(grep -n -e "${2}" "${TESTTMP}/body" | sed -e 1q | cut -d: -f1)

    if [ -n "${first}" ] && [ -n "${second}" ] && [ "${first}" -lt "${second}" ]
    then
	tap_pass "body matches ${1} before ${2}"
    else
	tap_fail "body matches ${1} before ${2}"
	diag "${TESTTMP}/body"
    fi
}

assert_no_body()
{
    if [ -s "${TESTTMP}/body" ]
    then
	tap_fail 'body is empty'
	diag "${TESTTMP}/body"
    else
	tap_pass 'body is empty'
    fi
}

test_done()
{
    echo "1..${TAP_N}"
    [ "${TAP_FAIL}" -eq 0 ]
}
