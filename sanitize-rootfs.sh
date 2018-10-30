#!/bin/bash

# example: sudo ./sanitize-rootfs image-name
# first arg is name of image file

if [ "$#" -ne 1 ] || ! [ -f "$1" ];  then
    echo "Usage: sudo $0 IMAGE_FILE" >&2
    echo "  IMAGE_FILE is an ext4 image file to sanitize"
    exit 1
fi

DESC=$(file $1)
# echo $DESC
if [[ $DESC == *"ext4 filesystem"* ]]; then
    CONT=1
else
    CONT=0
fi

if [ $CONT == 0 ]; then
    printf "Specified file is not an ext4 image file\n"
    exit 1
fi

####
mount $1 /mnt/part2

if [ $? != 0 ]; then
    printf "Can't mount the partition at the specified mount point, aborting\n"
    exit 1
fi

####
printf "Removing ssh keys\n"
rm -f /mnt/part2/home/pi/.ssh/*

printf "Removing bash history\n"
rm -f /mnt/part2/home/pi/.bash_history

printf "Removing gitconfig\n"
rm -f /mnt/part2/home/pi/.gitconfig

printf "Resetting wpa_supplicant.conf (removes stored wifi passwords)\n"
cat > /mnt/part2/etc/wpa_supplicant/wpa_supplicant.conf <<EOF
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1
country=US

EOF

###
umount /mnt/part2

printf "Sanitization done\n"
