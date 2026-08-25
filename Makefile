# @(#)$KimmoSuominen$
#
# Install src/man-cgi on oxygene: dist-qa for the QA vhost, dist-prod
# for production. See docs/deployment.md for the steps around them.
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

.PHONY: help dist-qa dist-prod

help:
	@echo 'Targets:'
	@echo '  dist-qa    install ${SCRIPT} on the QA vhost, ${DIST_HOST}:${QA_DIR}'
	@echo '  dist-prod  install ${SCRIPT} in production, ${DIST_HOST}:${PROD_DIR}'

dist-qa:
	${RSYNC} ${SCRIPT} ${DIST_HOST}:${QA_DIR}/

dist-prod:
	${RSYNC} ${SCRIPT} ${DIST_HOST}:${PROD_DIR}/
