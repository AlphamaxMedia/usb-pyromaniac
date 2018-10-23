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

Disk = namedtuple("Disk", "part1 part2 partid uuid")
Partition = namedtuple("Partition", "start end sectors id")

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
prompt = "Insert drives, then press B to start mass burn, or q to quit..."
replprompt = "PYRO> "
inputstr = ""

win = None
winLock = threading.RLock()

name_to_phys = {}     # mapping of physical port name to device node, e.g. {'USB0':'2-4:1.0'}
phys_to_mount = {}    # mapping of device node to mount point, e.g. {'2-4:1.0':'/dev/sdc1'}
name_to_status = {}    # mapping of physical port name to status messages, e.g. {'USB0':'Insert Drive...'}
name_to_thread = {}   # physical port name to mapping of burner threads, e.g. {'USB0':<Thread:0x234ea7>}
image_dir = ''

state = 'WAIT_INSERT'

def log_event(action, device):
    global portname
    global name_to_phys
    global prompt

    with winLock:
        win.move(nc_action[1],nc_action[0])
        win.clrtoeol()
        win.addnstr(nc_action[1], nc_action[0], 'Action: ' + action, width)
        if device.device_type == 'partition':
            win.move(nc_devpath[1],nc_devpath[0])
            win.clrtoeol()
            win.addnstr(nc_devpath[1], nc_devpath[0], 'Device: ' + device.device_node, width) # "mount" mapping
        else:
            win.move(nc_sysname[1],nc_sysname[0])
            win.clrtoeol()
            win.addnstr(nc_sysname[1], nc_sysname[0], 'Sysname: ' + device.sys_name, width) # "phys" mapping

        if state == 'WAIT_INSERT':
            if device.device_type == 'usb_interface' and action == 'add':
                if device.sys_name in phys_to_mount:
                    phys_to_mount[device.sys_name] = 'pending'

            phys_to_name = {v: k for k, v in name_to_phys.items()}  # this inverts the dictionary
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

        win.refresh()

class BurnThread(threading.Thread):
    def __init__(self, name, mountpoint):
        threading.Thread.__init__(self)
        self.mountpoint = mountpoint
        self.name = name

    def run(self):
        sd = parted.getDevice(self.mountpoint)
        print(sd.model)

class readable_dir(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        prospective_dir=values
        if not os.path.isdir(prospective_dir):
            raise argparse.ArgumentTypeError("readable_dir:{0} is not a valid path".format(prospective_dir))
        if os.access(prospective_dir, os.R_OK):
            setattr(namespace,self.dest,prospective_dir)
        else:
            raise argparse.ArgumentTypeError("readable_dir:{0} is not a readable dir".format(prospective_dir))

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

    while(True):
        with winLock:
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

        if c == ord('q') or c == ord('Q'):
            observer.stop()
            return
        elif c in(curses.KEY_BACKSPACE, curses.KEY_DL, 127, curses.erasechar()):
            win.delch(nc_input[1], nc_input[0] + len(inputstr) + len(replprompt))
            inputstr = inputstr[:-1]
        elif c == ord('\n'):
            inputstr = ''
        elif c == ord('B'):
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
                        name_to_thread[keys] = BurnThread(name="BurnThread{}".format(mount),mountpoint=mount)

                for keys in name_to_thread:
                    name_to_thread[keys].start()

            else:
                prompt = 'Please be patient...'
            inputstr = ''
        elif c != curses.ERR:
            inputstr = inputstr + chr(c)


def main():
    wrapper(progmain)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='usb-pyromaniac')
    parser.add_argument('-i', '--image_directory', action=readable_dir, help='Directory of image files', required=True)
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
                    part1 = Partition(start=line[1], end=line[2], sectors=line[3], id=int(line[4], 0))
                elif line[0] == 'part2':
                    part2 = Partition(start=line[1], end=line[2], sectors=line[3], id=int(line[4], 0))
                elif line[0] == 'partid':
                    partid = int(line[1], 0)
                elif line[0] == 'uuid':
                    uuid = line[1]
                else:
                    print('WARN: ignoring unknown partition.txt line: ')
                    print(*line)

    disk = Disk(part1, part2, partid, uuid)

    main()