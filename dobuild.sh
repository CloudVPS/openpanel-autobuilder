#!/bin/sh

# Make a temporary file and try to sign it, so the gpg passphrase lives in the gpg-agent
TMPFILE=`tempfile`
gpg --clearsign ${TMPFILE}
rm -f "${TMPFILE}" "${TMPFILE}.asc" "${TMPFILE}.sig"

./autobuilder --distribution=lenny   all
./autobuilder --distribution=squeeze all
./autobuilder --distribution=lucid   all
./autobuilder --distribution=natty   all

for pkg in `rsync -av /root/repository/* root@bob.openpanel.com:/srv/openpanel_repository --exclude "db/" --exclude "conf/" | 
    grep -oe '^pool/.*\.deb' |
    grep -v '+tip_'`; do
    
    pkg=${pkg##*/}
    echo -n "OpenPanel Builder just uploaded $pkg" | nc -uq0 krakras.office.xl-is.net 18000
done

./autobuilder --force-tip
rsync -av /root/repository/* 'root@bob.openpanel.com:/srv/openpanel_repository' --exclude "db/" --exclude "conf/" |
    grep -oe '^pool/.*\.deb' | 
    grep "+tip" | 
    sed 's%pool/.*/\([a-z0-9.-]*\)_.*%\1%' | 
    sort -u |
    xargs -rs 200 echo "New TIP for: " | 
    nc -uq0 krakras.office.xl-is.net 18000


