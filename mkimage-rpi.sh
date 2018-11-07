#!/bin/bash

# example: sudo ./mkimage-rpi.sh /dev/sdb 4500
# first arg is device node
# second arg is size of image in MB
# this command relies on "munge-partition.py" to be in the same directory

#re='^[0-9]+([.][0-9]+)?$'
re='^[0-9]+?$'

if [ "$#" -ne 3 ] || ! [ -b "$1" ] || ! [[ "$2" =~ $re ]] ; then
    echo "Usage: sudo $0 DEVICE_NODE IMAGE_SIZE(in MiB) TYPE_PREFIX" >&2
    echo "  DEVICE_NODE is the base sd, e.g. /dev/sdb"
    echo "  IMAGE_SIZE is the size of the image of the root partition to make, im MB"
    echo "  TYPE_PREFIX is a freefrom string prepended to today's date for the output directory name"
    exit 1
fi

if [[ "$1" == /dev/sda* ]] ; then
    echo "Won't operate on root partition" >& 2
    exit 1
fi

TARGETDIR=images/$3-$(date '+%d-%b-%Y')
mkdir -p $TARGETDIR

####
printf "Record geometries and identifiers\n"
(
    echo p
    echo q
) | fdisk $1 | ./munge-partition.py $TARGETDIR/partition.txt

printf "Extracting UUID\n"
blkid "$1"2  # for some reason this dummy command is necessary to get the next line to work
UUID=$(blkid "$1"2 | grep -P '\bUUID=(\S+)' -o | cut -f2 -d\")
printf "uuid: %s\n" $UUID
printf "uuid   %s\n" $UUID >> $TARGETDIR/partition.txt

# exit 0  # exit here when testing partition.txt scripts
####
printf "Imaging boot partition\n"

dd if="$1"1 of=$TARGETDIR/part1.img bs=1M

####
printf "Making local blank rootfs image\n"

time dd if=/dev/zero of=$TARGETDIR/part2.ext4 count=$2 bs=1M
time mkfs -t ext4 $TARGETDIR/part2.ext4

####
printf "Mount images\n"
mount -t ext4 -o loop $TARGETDIR/part2.ext4 /mnt/loop
mount "$1"2 /mnt/part2

printf "Rsync images\n"
time rsync -aAXv --exclude={"/dev/*","/proc/*","/sys/*","/tmp/*","/run/*","/mnt/*","/media/*","/lost+found"} /mnt/part2/ /mnt/loop/

####
printf "Unmount images\n"
umount /mnt/loop
umount /mnt/part2

####
printf "fsck and adjust partition ID\n"
e2fsck -f -y $TARGETDIR/part2.ext4
tune2fs $TARGETDIR/part2.ext4 -U $UUID
e2fsck -f -y $TARGETDIR/part2.ext4

####

printf "Imaging done, see image in directory %s\n" $TARGETDIR
