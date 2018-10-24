# usb-pyromaniac

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
uuid "efb77116-2573-474b-931a-33b2e14cf331"
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
