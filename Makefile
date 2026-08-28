# @(#)$KimmoSuominen$
#
# Test src/man-cgi, install it on oxygene (dist-qa for the QA vhost,
# dist-prod for production) and smoke-check the live tiers. See
# docs/deployment.md for the steps around these.
#
# 20260825  Kimmo Suominen
#

SCRIPT=		src/man-cgi
PYTHON=		python3

CDN_RANGES=	lib/manno_logreport/data/fastly.cidr

# The log report: LOGDIR holds the access.log*/error.log* copied from
# oxygene, REPORT_DIR receives <window>.html and <window>.json, and
# dist-report copies every HTML file there to where
# https://man.netbsd.org/r/ is served from (the JSON stays local).
LOGDIR?=	${HOME}/tmp/oxygene-nginx-logs
REPORT_DIR?=	${HOME}/tmp/man-report
PUBLISH_DIR=	/p/netbsd/man/htdocs/r
RSYNC_RO=	rsync -pti --chmod=Fa+r

DIST_HOST=	oxygene
QA_DIR=		/p/netbsd/man/qa/cgi-bin
PROD_DIR=	/p/netbsd/man/htdocs/cgi-bin

# The installed script is readable and executable for everyone,
# whatever mode the checkout has.
RSYNC=		rsync -pti --chmod=Fa+rx

# The suite needs NetBSD stat(1), date(1) and man(1): elsewhere it
# runs on the test host through tests/run-remote.
TEST_REMOTE=	kimmo@equinoxe
TEST_IDENTITY=	${HOME}/.ssh/id-kimmo-ai

# ct-check lives in its own repository. Every tier is paced: the QA
# vhost is uncached and shares the fcgiwrap workers with production.
CT_CHECK=	${HOME}/src/ct-check/ct-check
SMOKE_DELAY=	1
QA_SERVER=	man.oxygene.qa.nxrns.org
PROD_SERVER=	man.netbsd.org

.PHONY: help test test-python test-browser dist-qa dist-prod smoke-qa smoke-prod refresh-cdn report dist-report

help:
	@echo 'Targets:'
	@echo '  test          run the suite (on ${TEST_REMOTE} unless NetBSD)'
	@echo '  test-python   run the Python unit tests locally'
	@echo '  test-browser  drive the inline script in headless Chromium'
	@echo '  dist-qa       install ${SCRIPT} to ${DIST_HOST}:${QA_DIR}'
	@echo '  dist-prod     install ${SCRIPT} to ${DIST_HOST}:${PROD_DIR}'
	@echo '  smoke-qa      smoke-check ${QA_SERVER} (origin headers too)'
	@echo '  smoke-prod    smoke-check ${PROD_SERVER} through Fastly'
	@echo '  refresh-cdn   refetch lib/manno_logreport/data/fastly.cidr from Fastly'
	@echo '  report        render ${LOGDIR} into ${REPORT_DIR}/<window>.html'
	@echo '  dist-report   copy ${REPORT_DIR}/*.html to ${DIST_HOST}:${PUBLISH_DIR}'

test:
	@if [ "$$(uname -s)" = NetBSD ]; \
	then \
	    sh tests/run-tests; \
	else \
	    MANCGI_TEST_REMOTE=${TEST_REMOTE} \
	    MANCGI_TEST_IDENTITY=${TEST_IDENTITY} \
	    sh tests/run-remote; \
	fi

test-python:
	PYTHONPATH=lib ${PYTHON} -m unittest discover -s tests/python -p 'test_*.py'

# The / shortcut lives in the inline script, which the suite can
# only grep; this runs it locally (needs chromium and node).
test-browser:
	tests/run-browser

dist-qa:
	${RSYNC} ${SCRIPT} ${DIST_HOST}:${QA_DIR}/

dist-prod:
	${RSYNC} ${SCRIPT} ${DIST_HOST}:${PROD_DIR}/

# The origin checklist only makes sense where the Surrogate headers
# are visible, which Fastly strips toward clients.
smoke-qa:
	${CT_CHECK} --scheme http --server ${QA_SERVER} \
	    --delay ${SMOKE_DELAY} --file tests/smoke.yml
	${CT_CHECK} --scheme http --server ${QA_SERVER} \
	    --delay ${SMOKE_DELAY} --file tests/smoke-origin.yml

smoke-prod:
	${CT_CHECK} --scheme https --server ${PROD_SERVER} \
	    --delay ${SMOKE_DELAY} --file tests/smoke.yml

# curl -sS so a fetch failure says why; the .new file is removed on
# any failure so a later run never picks up a truncated fetch.
refresh-cdn:
	curl -sSf https://api.fastly.com/public-ip-list | \
	    PYTHONPATH=lib ${PYTHON} -m manno_logreport.cdn \
	    > ${CDN_RANGES}.new || { rm -f ${CDN_RANGES}.new; exit 1; }
	mv ${CDN_RANGES}.new ${CDN_RANGES}

report:
	bin/manno-logreport -O ${REPORT_DIR} ${LOGDIR}

dist-report:
	${RSYNC_RO} ${REPORT_DIR}/*.html ${DIST_HOST}:${PUBLISH_DIR}/
