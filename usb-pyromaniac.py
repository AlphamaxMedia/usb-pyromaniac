#!/usr/bin/python3

import pyudev
import time
import curses
from curses import wrapper
import threading
import pickle

import argparse
import os
import parted  # from pyparted

from collections import namedtuple
import struct
import subprocess

## Disk abstractions
Disk = namedtuple("Disk", "part1 part2 partid uuid")
Partition = namedtuple("Partition", "start end sectors id")

## UI absrtactions
begin_x = 5
begin_y = 3
height = 20
width = 80

# these are x, y coordinates
nc_action = [2, 1]
nc_sysname = [2, 2]
nc_devpath = [2, 3]
nc_portarray = [2, 5]
nc_input = [2, height - 1]
nc_prompt = [0, height - 2]
prompt = "Insert drives, then press shift-B to start mass burn, or shift-Q to quit..."
replprompt = "PYRO> "
inputstr = ""

win = None
winLock = threading.RLock()

## State abstractions
name_to_phys = {}     # mapping of physical port name to device node, e.g. {'USB0':'2-4:1.0'}
phys_to_mount = {}    # mapping of device node to mount point, e.g. {'2-4:1.0':'/dev/sdc1'}
name_to_status = {}    # mapping of physical port name to status messages, e.g. {'USB0':'Insert Drive...'}
name_to_thread = {}   # physical port name to mapping of burner threads, e.g. {'USB0':<Thread:0x234ea7>}
image_dir = ''

state = 'WAIT_INSERT'

action_status = ''
device_status = ''
sysname_status = ''

# udev callback
def log_event(action, device):
    global portname
    global name_to_phys
    global prompt
    global action_status, device_status, sysname_status

    action_status = action
    if device.device_type == 'partition':
        device_status = device.device_node # "mount" mapping
    else:
        sysname_status = device.sys_name # "phys" mapping

    phys_to_name = {v: k for k, v in name_to_phys.items()}  # this inverts the dictionary
    if state == 'WAIT_INSERT':
        if device.device_type == 'usb_interface' and action == 'add':
            if device.sys_name in phys_to_mount:
                phys_to_mount[device.sys_name] = 'pending'

        if device.device_type == 'partition' and action == 'add':
            numfound = 0
            for keys in phys_to_mount:
                if phys_to_mount[keys] == 'pending':
                    phys_to_mount[keys] = ''.join([i for i in device.device_node if not i.isdigit()]) # remove any numbers inside the device node description
                    numfound = numfound + 1
                    name_to_status[phys_to_name[keys]] = 'Media found at ' + phys_to_mount[keys]
            assert numfound == 1 or numfound == 0, 'Number of udev partition mappings unexpected (should be 1): %r' % numfound

    # always update remove status regardless of state
    if device.device_type == 'usb_interface' and action == 'remove' and device.driver == None:
        if device.sys_name in phys_to_mount:
            phys_to_mount[device.sys_name] = 'none'
            name_to_status[phys_to_name[device.sys_name]] = 'Insert drive...'



class BurnThread(threading.Thread):
    def __init__(self, name, mountpoint, namedport):
        threading.Thread.__init__(self)
        self.mountpoint = mountpoint
        self.name = name
        self.namedport = namedport

    def run(self):
        global name_to_status

        if '/dev/sda' in self.mountpoint:
            name_to_status[self.namedport] = self.mountpoint + ": Refusing to operate on /dev/sda. Burner script error"
            return  # refuse to run a burn thread on the root partition

        if not self.mountpoint.startswith('/dev/sd'):
            name_to_status[self.namedport] = self.mountpoint + ": Invalid mountpoint. Burning script error"

        sd = parted.getDevice(self.mountpoint)
        name_to_status[self.namedport] = self.mountpoint + ": Partitioning " + sd.model
        sd.clobber()
        sd_disk = parted.freshDisk(sd, 'msdos')

        geometry1 = parted.Geometry(start=disk.part1.start, end=disk.part1.end, device=sd)
        filesystem1 = parted.FileSystem(type=disk.part1.id, geometry=geometry1)
        partition1 = parted.Partition(disk=sd_disk, type=parted.PARTITION_NORMAL, fs=filesystem1, geometry=geometry1)
        sd_disk.addPartition(partition1, constraint=sd.optimalAlignedConstraint)
        sd_disk.commit()

        geometry2 = parted.Geometry(start=disk.part2.start, end=sd.length, device=sd)
        filesystem2 = parted.FileSystem(type=disk.part2.id, geometry=geometry2)
        partition2 = parted.Partition(disk=sd_disk, type=parted.PARTITION_NORMAL, fs=filesystem2, geometry=geometry2)
        sd_disk.addPartition(partition2, constraint=sd.optimalAlignedConstraint)
        sd_disk.commit()

        # set the disk identifier by blasting in the four bytes manually...
        with open(self.mountpoint, 'wb') as p:
            p.seek(0x1b8)
            p.write(struct.pack("<I", disk.partid))

        #### PARTITION 1 COPY
        name_to_status[self.namedport] = self.mountpoint + ": Copying partition 1..."
        p = subprocess.Popen(["dd", "if=" + image_dir + "/part1.img", "of=" + self.mountpoint + "1", "bs=1M"], stderr=subprocess.PIPE)
        for lines in p.stderr:
            if 'copied' in lines.decode("utf-8"):
                name_to_status[self.namedport] = self.mountpoint + ": " + lines.decode("utf-8")

        p.wait()
        if p.returncode != 0:
            name_to_status[self.namedport] = self.mountpoint + " ERROR: " + lines.decode("utf-8")
            return

        time.sleep(3)
        ##### PARTITION 2 COPY
        name_to_status[self.namedport] = self.mountpoint + ": Copying partition 2..."
        p = subprocess.Popen(["dd", "if=" + image_dir + "/part2.ext4", "of=" + self.mountpoint + "2", "bs=1M"], stderr=subprocess.PIPE)
        for lines in p.stderr:
            if 'copied' in lines.decode("utf-8"):
                name_to_status[self.namedport] = self.mountpoint + ": " + lines.decode("utf-8")

        p.wait()
        if p.returncode != 0:
            name_to_status[self.namedport] = self.mountpoint + " ERROR: " + lines.decode("utf-8")
            return

        time.sleep(3)
        ##### FSCK PARTITION 2 -- allow a couple iterations to get a "clean" fsck
        returncode = 1
        iters = 0
        while returncode != 0 and iters < 4:
            name_to_status[self.namedport] = self.mountpoint + ": fsck partition 2..."
            p = subprocess.Popen(["e2fsck", "-y", "-f", self.mountpoint + "2"], stderr=subprocess.PIPE, stdout=subprocess.PIPE)
            for lines in p.stderr:
                name_to_status[self.namedport] = self.mountpoint + ": " + lines.decode("utf-8")

            p.wait()
            returncode = p.returncode
            iters = iters + 1

        if iters >= 3:
            name_to_status[self.namedport] = self.mountpoint + " ERROR: " + lines.decode("utf-8")
            return

        ##### RESIZE PARTITION 2
        name_to_status[self.namedport] = self.mountpoint + ": resize partition 2..."
        p = subprocess.Popen(["resize2fs", self.mountpoint + "2"], stderr=subprocess.PIPE, stdout=subprocess.PIPE)
        for lines in p.stderr:
            name_to_status[self.namedport] = self.mountpoint + ": " + lines.decode("utf-8")

        p.wait()
        if p.returncode != 0:
            name_to_status[self.namedport] = self.mountpoint + " ERROR: " + lines.decode("utf-8")
            return

        ##### SET BLKID PARTITION 2 -- actually, this can be done in the source image!
        #name_to_status[self.namedport] = self.mountpoint + ": set blkid partition 2..."
        #p = subprocess.Popen(["tune2fs", self.mountpoint + "2", "-U", disk.uuid], stderr=subprocess.PIPE, stdout=subprocess.PIPE)
        #for lines in p.stderr:
        #    name_to_status[self.namedport] = self.mountpoint + ": " + lines.decode("utf-8")

        #p.wait()
        #if p.returncode != 0:
        #    name_to_status[self.namedport] = self.mountpoint + " ERROR: " + lines.decode("utf-8")
        #    return

        ##### SET PASS STATE
        name_to_status[self.namedport] = self.mountpoint + " FINISHED"
        return


def progmain(mainscr):
    global win
    global inputstr
    global portname
    global prompt
    global name_to_phys
    global state
    global phys_to_mount
    global name_to_status
    global disk
    global name_to_thread

    start_time = time.time()
    elapsed_time = time.time() - start_time

    phys_to_name = {v: k for k, v in name_to_phys.items()}  # this inverts the dictionary

    for keys in name_to_phys:
        name_to_status[keys] = 'Insert drive...'

    for keys in phys_to_name:
        phys_to_mount[keys] = 'none'

    mainscr.clear()

    win = curses.newwin(height, width, begin_y, begin_x)
    win.nodelay(1) # non-blocking input

    context = pyudev.Context()
    monitor = pyudev.Monitor.from_netlink(context)
    monitor.filter_by('usb')
    monitor.filter_by('block')

    observer = pyudev.MonitorObserver(monitor, log_event)
    observer.start()

    while True:
        with winLock:
            win.move(nc_action[1], nc_action[0])
            win.clrtoeol()
            win.addnstr(nc_action[1], nc_action[0], 'Action: ' + action_status, width)
            win.move(nc_devpath[1],nc_devpath[0])
            win.clrtoeol()
            win.addnstr(nc_devpath[1], nc_devpath[0], 'Device: ' + device_status, width) # "mount" mapping
            win.move(nc_sysname[1],nc_sysname[0])
            win.clrtoeol()
            win.addnstr(nc_sysname[1], nc_sysname[0], 'Sysname: ' + sysname_status, width) # "phys" mapping

            offset = 0
            for port in sorted(name_to_phys):
                win.move(nc_portarray[1] + offset, nc_portarray[0])
                win.clrtoeol()
                win.addnstr(nc_portarray[1] + offset, nc_portarray[0], port + ":" + name_to_status[port], width)
                offset = offset + 1

            win.border()
            win.move(nc_prompt[1], nc_prompt[0])
            win.clrtobot()
            win.addnstr(nc_prompt[1], nc_prompt[0], prompt, width)
            win.addnstr(nc_input[1], nc_input[0], replprompt, width)
            win.addnstr(nc_input[1], nc_input[0] + len(replprompt), inputstr, width-2)
            win.move(nc_input[1], nc_input[0] + len(inputstr) + len(replprompt))

            win.refresh()

        try:
            c = win.getch()
        except:
            c = ''

        time.sleep(0.05)

        if c == ord('Q') or c == ord('"'):
            observer.stop()
            return
        elif c in(curses.KEY_BACKSPACE, curses.KEY_DL, 127, curses.erasechar()):
            win.delch(nc_input[1], nc_input[0] + len(inputstr) + len(replprompt))
            inputstr = inputstr[:-1]
        elif c == ord('\n'):
            inputstr = ''
        elif c == ord('B') or c == ord('X'):
            if state == 'WAIT_INSERT':
                state = 'BURNING'
                prompt = 'Burning, please wait...'
                name_to_thread.clear()
                for keys in name_to_status:
                    if name_to_status[keys] == 'Insert drive...':
                        name_to_status[keys] = '[]'
                    else:
                        name_to_status[keys] = 'Starting burn...'
                        mount = phys_to_mount[name_to_phys[keys]]
                        name_to_thread[keys] = BurnThread(name="BurnThread{}".format(mount), mountpoint=mount, namedport=keys)
                        time.sleep(1)  # stagger starts to avoid overloading

                for keys in name_to_thread:
                    name_to_thread[keys].start()
            else:
                prompt = 'Please be patient...'
            inputstr = ''
        elif c != curses.ERR:
            inputstr = inputstr + chr(c)

        if state == 'BURNING':
            active_burn = False
            for keys in name_to_thread:
                if name_to_thread[keys].isAlive():
                    active_burn = True

            if not active_burn:
                prompt = "Syncing filesystems..."
                win.move(nc_prompt[1], nc_prompt[0])

                win.clrtobot()
                win.addnstr(nc_prompt[1], nc_prompt[0], prompt, width)
                win.addnstr(nc_input[1], nc_input[0], replprompt, width)
                win.addnstr(nc_input[1], nc_input[0] + len(replprompt), inputstr, width - 2)
                win.move(nc_input[1], nc_input[0] + len(inputstr) + len(replprompt))
                win.refresh()

                p = subprocess.Popen(["sync"], stderr=subprocess.PIPE, stdout=subprocess.PIPE)
                p.wait()

                prompt = "Burn finished, remove disks..."
                state = 'REMOVE'
        elif state == 'REMOVE':
            if elapsed_time > 10:
                start_time = time.time()
                p = subprocess.Popen(["aplay", "alert.wav"], stderr=subprocess.PIPE, stdout=subprocess.PIPE)
                p.wait()

            elapsed_time = time.time() - start_time

            all_removed = True
            for keys in name_to_status:
                if not(name_to_status[keys] == 'Insert drive...' or name_to_status[keys] == '[]'):
                    all_removed = False

            if all_removed:
                for keys in name_to_status:
                    name_to_status[keys] = 'Insert drive...'
                    prompt = "Insert drives, then press B to start mass burn, or Q to quit..."
                    state = 'WAIT_INSERT'


class ReadableDir(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        prospective_dir=values
        if not os.path.isdir(prospective_dir):
            raise argparse.ArgumentTypeError("ReadableDir:{0} is not a valid path".format(prospective_dir))
        if os.access(prospective_dir, os.R_OK):
            setattr(namespace,self.dest,prospective_dir)
        else:
            raise argparse.ArgumentTypeError("ReadableDir:{0} is not a readable dir".format(prospective_dir))


def main():
    wrapper(progmain)  # this is the curses wrapper to clean up terminal state when exiting


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='usb-pyromaniac')
    parser.add_argument('-i', '--image_directory', action=ReadableDir, help='Directory of image files', required=True)
    parser.add_argument('-u', '--usb_map', type=str, help='USB mapping file', default='usb_map.pkl')
    args = parser.parse_args()

    name_to_phys.clear()
    try:
        with open(args.usb_map, 'rb') as f:
            name_to_phys = pickle.load(f)
    except IOError:
        print('usb-pyromaniac needs the file usb_map.pkl to be present in the same directory')

    image_dir = args.image_directory

    with open(image_dir + '/partition.txt') as f:
        for wholeline in f:
            line = wholeline.split()
            if len(line) != 0:
                if line[0] == 'part1':
                    part1 = Partition(start=int(line[1]), end=int(line[2]), sectors=int(line[3]), id=line[4])
                elif line[0] == 'part2':
                    part2 = Partition(start=int(line[1]), end=int(line[2]), sectors=int(line[3]), id=line[4])
                elif line[0] == 'partid':
                    partid = int(line[1], 0)
                elif line[0] == 'uuid':
                    uuid = line[1]
                else:
                    print('WARN: ignoring unknown partition.txt line: ')
                    print(*line)

    disk = Disk(part1, part2, partid, uuid)

    main()
