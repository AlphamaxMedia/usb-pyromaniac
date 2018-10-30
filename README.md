# usb-pyromaniac
_"burn baby burn"_

usb-pyromaniac is a tool for the mass burning of firmware images. It's
optimized for Raspberry Pi images but can be adapted to handle multiple
partitions of almost any type.

## Usage
Before using usb-pyromaniac, you need to do two things:

1. Create a map of USB ports to names using usb-mapping (https://github.com/AlphamaxMedia/usb-mapping)
2. Prepare your disk image files

usb-pyromaniac makes the assumption that your base image is basically
empty space, e.g. you may have a 16GB drive but you only need to load
4GB of data onto it. Rather than doing a dd of the full 16GB, the procedure
here will dd an image of just the size it needs to be and then resizes
it to use the whole disk.

One other minor advantage of using the rsync technique is that
if you need to update the master image, you can mount the existing
image and just re-run the rsync command and save a lot of time.

### Mapping USB ports
The USB port mapping is necessary because if an image burn fails
you want to know which one is bad. A dev node (/dev/sdb) doesn't
tell you which physical disk it is. 

Run usb-mapping; basically, you type a memorable name to describe
a USB port (ideally you label each one with a unique number, for
example), and then plug in any mass storage device. usb-mapping
will pick up the udev event and associate it with a physical hub
address. Rinse lather repeat, quit the program and a file
called usb_map.pkl will be generated. Copy this to the usb-pyromaniac
directory.

### Preparing the disk image directory

There's a script called mkimage-rpi.sh which walks through the steps
listed below automatically, including building the partition.txt
descriptor file. It makes some assumptions about mount
point availability, but is otherwise fairly generic. It takes
as arguments the device node of the drive to image, the size of
the rootfs image to create in MiB, and a type prefix which is
a free-form string to help specify the directory into which an
image should go. In general, the rootfs image size should be
about +1,000 MiB over the used disk space reported by the df tool.
On a typical image this will result in only a couple hundred
MB of actual free space in the imaged partition, due to losses
in filesystem overhead.

There's also a script called sanitize-rootfs.sh which takes
some steps to remove keys and history from the rootfs image. It
doesn't clear things like chrome caches or desktop preferences.
The sanitize-rootfs script is separate from the imaging because
there are instances where this shouldn't be run (for example,
imaging an RPi image destined to run factory test infrastruture).

Here's the steps to create an image manually:

Image each partition individually. This script is customized for
the Rpi scenario, where you have a small FAT32 boot partition
and a large EXT4 root partition. 

Image the boot partition wis a simple dd. It's small enough and
you can't resize FAT32:

```bash
  sudo dd if=/dev/sdb1 of=part1.img bs=1M  
```

The root partition needs to be rsync'd to a file. First figure
out how much data you have on the disk. Let's say it's 4GB, so
we'll build the disk image to be 4.5GB:

```bash
  sudo dd if=/dev/zero of=part2.ext4 count=4608 bs=1M
  sudo mkfs -t ext4 part2.ext4
```

Now mount the disk image as a loopback, mount the source
root disk, and rsync the data over:

```bash
  sudo mount -t ext4 -o loop part2.ext4 /mnt/loop
  sudo mount /dev/sdb2 /mnt/part2
  sudo rsync -aAXv --exclude={"/dev/*","/proc/*","/sys/*","/tmp/*","/run/*","/mnt/*","/media/*","/lost+found"} /mnt/part2/ /mnt/loop/
  sudo umount /mnt/loop
```
Note that you can run the series of commands above to
also quickly update the image as well if you have made changes
to it.

To improve image copying speed, you'll want to fsck it
and also adjust the UUID if you want it to match exactly
to the source image:

```bash
  sudo e2fsck -f -y part2.ext4
  sudo blkid /dev/sdb2   # determine the UUID of the source root partition
  sudo tune2fs part2.ext4 -U INSERT-UUID-HERE
```

Run an `e2fsk` again just to make sure the image is clean,
otherwise the burner will be running `e2fsk` post-duplication.

Finally, you need to make a "partition.txt" file to describe
where stuff goes. The format looks like this:

```text
part1  8192  93802    85611      fat32
part2  98304 31116287 31017984   ext4
partid 0xd81061a1
uuid   efb77116-2573-474b-931a-33b2e14cf331
``` 

The first 3 lines you can basically extract directly from fdisk,
as seen below:

```text
Disk /dev/sdb: 14.9 GiB, 15987638272 bytes, 31225856 sectors
Units: sectors of 1 * 512 = 512 bytes
Sector size (logical/physical): 512 bytes / 512 bytes
I/O size (minimum/optimal): 512 bytes / 512 bytes
Disklabel type: dos
Disk identifier: 0xf6104fb5

Device     Boot Start      End  Sectors  Size Id Type
/dev/sdb1        8192    93802    85611 41.8M  c W95 FAT32 (LBA)
/dev/sdb2       98304 31116287 31017984 14.8G 83 Linux

Building a "user image" blank

Command (m for help):
```

The last one comes from the `blkid` command.

The image directory should now have these three files: part1.img, part2.ext4, and partition.txt

### Invoking the burner

usb-pyromaniac must be invoked with sudo to access the disks.

usb-pyromaniac will implicitly look for the usb_map.pkl file in the 
invocation directory, but you can also specify it with -u

usb-pyromaniac also requires one argument, -i IMAGE_DIRECTORY. 
This argument is the directory where the image above was prepared.

Once it starts, you will see a UI a bit like this:

```text
     ┌──────────────────────────────────────────────────────────────────────────────┐
     │ Action:                                                                      │
     │ Sysname:                                                                     │
     │ Device:                                                                      │
     │                                                                              │
     │ USB0:Insert drive...                                                         │
     │ USB1:Insert drive...                                                         │
     │ USB2:Insert drive...                                                         │
     │ USB3:Insert drive...                                                         │
     │ USB4:Insert drive...                                                         │
     │ USB5:Insert drive...                                                         │
     │ USB6:Insert drive...                                                         │
     │                                                                              │
     │                                                                              │
     │                                                                              │
     │                                                                              │
     │                                                                              │
     │                                                                              │
     Insert drives, then press shift-B to start mass burn, or shift-Q to quit...
       PYRO> 
```

The script will automatically pick up when a drive is inserted,
once you've loaded all the drives you want to burn (not all have
to be populated), hit B to start the burning. Capital letters
are specified to prevent fat-fingered operators from accidentally
starting or quitting a burn before intended.

The script will run until completion and then play a tone to
notify the operator, at which point all the drives can be removed
and the script returns to the idle state above. Rinse lather repeat.

On an ASUS NUC with a Celeron N3150 CPU (1.6GHz 4-thread) and a USB3.0 
port replicator, performance peaks out at 4 simultaneous drives, inserting more 
causes the CPU to thrash and overall write speed to go down. 

### Pycharm integration
This script requires root access to modify partition tables, etc. 

To give the script root in Pycharm, I followed this guide:
https://esmithy.net/2015/05/05/rundebug-as-root-in-pycharm/

The python-sudo.sh script is also checked in for reference.

### Dev notes
Arguments: 
* directory where source images are located.
* location of pickle file for USB port mappings

Source image directory should contain the following files:
* part1.img -- dd image of boot partition
* part2.ext4 -- ext4 image of user partition
* partition.txt -- partition table and UUID, PTUUID specifiers

Partition.txt format as follows:
```text
part1  8192  93802    85611      fat32
part2  98304 31116287 31017984   ext4
partid 0xd81061a1
uuid   efb77116-2573-474b-931a-33b2e14cf331
``` 
Whitespace can be variable/tabs. Numbers are decimal unless with 0x in front then hex
First item is the description identifier. This allows the descriptions to go out
of order. However, only part1, part2, partid, and uuid are defined, anything else
is ignored.

For part*, the format is "part  start end sectors"
Basically, it's a copy of the fdisk output plus blkid

### States

This is what the UI should look like:

State 1: Plug in drives
```text
USB0  Insert drive...
USB1  Media found at /dev/sdf
USB2  Media found at /dev/sdb
USB3  Insert drive...
USB4  Media found at /dev/sdc
USB5  Insert drive...
USB6  Insert drive...

PYRO> Hit enter to start batch burn... 
```

State 2: Burning
```text
USB0  []
USB1  Finalizing...
USB2  Partitioning...
USB3  []
USB4  Copying boot...
USB5  []
USB6  []

PYRO> Burning... 
```
When state 2 is done, play an audible tone.

State 3: Remove drives
```text
USB0  []
USB1  PASS
USB2  FAIL: Drive out of space
USB3  []
USB4  PASS
USB5  []
USB6  []

PYRO> Remove media...
```

Once all drives removed, state goes back to State 1

