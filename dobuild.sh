#!/bin/sh

# Make a temporary file and try to sign it, so the gpg passphrase lives in the gpg-agent
TMPFILE=`tempfile`
gpg --clearsign ${TMPFILE}
rm -f "${TMPFILE}"
rm -f "${TMPFILE}.asc"
rm -f "${TMPFILE}.sig"

./autobuilder all

rsync -av /root/repository/* root@bob.openpanel.com:/srv/openpanel_repository --exclude "db/" --exclude "conf/"
