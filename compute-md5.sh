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
    printf "Computing md5sum of %s\n" $filename
    time md5sum $filename >> $MANIFEST
done
