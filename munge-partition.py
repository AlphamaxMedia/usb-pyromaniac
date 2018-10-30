#!/usr/bin/python3

import sys
from sys import stdin

with open(sys.argv[1], "w") as f:
    for line in stdin:
        if "Disk identifier:" in line:
            f.write("partid " + line.split()[2] + "\n")
            
        if line.startswith("/dev/sd"):
            noboot = line.replace("\*", "") # remove the "*" if it's there for the boot flag
            splitline = noboot.split()
            if splitline[5] == 'b':
                fstype = 'fat32'
            elif splitline[5] == 'c':
                fstype = 'fat32'
            elif splitline[5] == '83':
                fstype = 'ext4'
            f.write("part" + splitline[0][-1] + "  " + splitline[1] + " " + splitline[2] + " " + splitline[3] + " " + fstype + "\n")

f.close()

    
