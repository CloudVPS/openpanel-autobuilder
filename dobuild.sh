#!/bin/bash

function repo_alias {
    local from=$1
    local to=$2
    
    reprepro -b "/root/repository" -A "source" listfilter $1 'Section (!=1)' | cut -d' ' -f2 | sort -u > "/tmp/dobuild.$$"
    
    while read pkg ; do
        #echo $pkg
        reprepro -b "/root/repository" copysrc "$to" "$from" "$pkg" 2> /dev/null 1>/dev/null
    done <  "/tmp/dobuild.$$"
    
    rm -f "/tmp/dobuild.$$"
} 

# Make a temporary file and try to sign it, so the gpg passphrase lives in the gpg-agent
TMPFILE=`tempfile`
gpg --clearsign ${TMPFILE}
rm -f "${TMPFILE}" "${TMPFILE}.asc" "${TMPFILE}.sig"

./autobuilder --distribution=lenny  all
./autobuilder --distribution=squeeze core modules openapp
repo_alias squeeze wheezy

./autobuilder --distribution=lucid   all
repo_alias lucid    maverick

./autobuilder --distribution=natty   core modules openapp
repo_alias natty    oneiric
repo_alias oneiric  precise

for pkg in `rsync -av /root/repository/* root@bob.openpanel.com:/srv/openpanel_repository --exclude "db/" --exclude "conf/" | 
    grep -oe '^pool/.*\.deb' |
    grep -v '+tip_'`; do
    
    pkg=${pkg##*/}
    echo -n "OpenPanel Builder just uploaded $pkg" | nc -uq0 krakras.office.xl-is.net 18000
done

./autobuilder --distribution=lenny   --force-tip all
./autobuilder --distribution=squeeze --force-tip core modules openapp
repo_alias squeeze wheezy

./autobuilder --distribution=lucid   --force-tip all
repo_alias lucid    maverick
./autobuilder --distribution=natty --force-tip core modules openapp
repo_alias natty    oneiric
repo_alias oneiric  precise

rsync -av /root/repository/* 'root@bob.openpanel.com:/srv/openpanel_repository' --exclude "db/" --exclude "conf/" |
    grep -oe '^pool/.*\.deb' | 
    grep "+tip" | 
    sed 's%pool/.*/\([a-z0-9.-]*\)_.*%\1%' | 
    sort -u |
    xargs -rs 200 echo "New TIP for: " | 
    nc -uq0 krakras.office.xl-is.net 18000

