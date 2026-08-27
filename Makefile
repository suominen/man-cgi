# @(#)$KimmoSuominen$
#
# Test src/man-cgi, install it on oxygene (dist-qa for the QA vhost,
# dist-prod for production) and smoke-check the live tiers. See
# docs/deployment.md for the steps around these.
#
# 20260825  Kimmo Suominen
#

SCRIPT=		src/man-cgi

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

.PHONY: help test test-browser dist-qa dist-prod smoke-qa smoke-prod

help:
	@echo 'Targets:'
	@echo '  test          run the suite (on ${TEST_REMOTE} unless NetBSD)'
	@echo '  test-browser  drive the inline script in headless Chromium'
	@echo '  dist-qa       install ${SCRIPT} to ${DIST_HOST}:${QA_DIR}'
	@echo '  dist-prod     install ${SCRIPT} to ${DIST_HOST}:${PROD_DIR}'
	@echo '  smoke-qa      smoke-check ${QA_SERVER} (origin headers too)'
	@echo '  smoke-prod    smoke-check ${PROD_SERVER} through Fastly'

test:
	@if [ "$$(uname -s)" = NetBSD ]; \
	then \
	    sh tests/run-tests; \
	else \
	    MANCGI_TEST_REMOTE=${TEST_REMOTE} \
	    MANCGI_TEST_IDENTITY=${TEST_IDENTITY} \
	    sh tests/run-remote; \
	fi

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
