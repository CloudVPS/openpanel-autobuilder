#!/bin/sh

# Make a temporary file and try to sign it, so the gpg passphrase lives in the gpg-agent
TMPFILE=`tempfile`
gpg --clearsign ${TMPFILE}
rm -f "${TMPFILE}"
rm -f "${TMPFILE}.asc"
rm -f "${TMPFILE}.sig"

./autobuilder all

for pkg in `rsync -av /root/repository/* root@bob.openpanel.com:/srv/openpanel_repository --exclude "db/" --exclude "conf/" | 
    grep -oe '^pool/.*\.deb' |
    grep -v '+tip_'`; do
    
    pkg=${pkg##*/}
    echo -n "OpenPanel Builder just uploaded $pkg" | nc -uq0 krakras.office.xl-is.net 18000
done

./autobuilder --force-tip
rsync -av /root/repository/* 'root@bob.openpanel.com:/srv/openpanel_repository' --exclude "db/" --exclude "conf/" |
    grep -oe '^pool/.*\.deb' | 
    grep "+tip_" | 
    sed 's%pool/.*/\([a-z0-9.-]*\)_.*%\1%' | 
    sort -u |
    xargs -s 200 echo "New TIP for: " | 
    nc -uq0 krakras.office.xl-is.net 18000


