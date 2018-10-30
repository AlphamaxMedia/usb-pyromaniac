#!/bin/bash

# example: ./compute-md5.sh directory_of_images manifest
# first arg is name of image file
# second optional arg is name of manifest file

MANIFEST=manifest.md5

if [ "$#" -eq 2 ] && [ -d "$1" ]; then
    MANIFEST=$2
elif [ "$#" -ne 1 ] || ! [ -d "$1" ];  then
    echo "Usage: sudo $0 TARGET_DIR [MANIFEST]" >&2
    echo "  TARGET_DIR contains the images to md5"
    echo "  MANIFEST contains name of manifest, defaults to manifest.md5"
    exit 1
fi

cd $1

rm -f $MANIFEST

for filename in *; do
    [ -e "$filename" ] || continue
    if [[ "$filename" != *.gz ]]; then
	printf "Computing md5sum of %s\n" $filename
	time md5sum $filename >> $MANIFEST
    fi
done

printf "Final operation: gzipping part2.ext4\n"
gzip -c part2.ext4 > part2.ext4.gz

# after this command is run, build the gzip file for upload
# gzip -c part2.ext4 > part2.ext4.gz

# note that it's ok to have both part2.ext4 and part2.ext4.gz on the web server
# the client only downloads the .gz version and unzips it before checking the
# manifest

# BUT the manifest fire should *not* have the .gz version in it!
