#!/usr/bin/env python2

from xmodem import XMODEM
import sys,os,os.path
import time
import serial
from docopt import docopt

RESP_ERR = "unexpected response!"
def ERR(msg,ecode=0):
    sys.stderr.write(msg + os.linesep)
    if( ecode!= 0):
        exit(ecode)

def INFO(msg):
    sys.stdout.write(msg + os.linesep)

def CHK(bval, msg, ecode=0):
    if not bval:
        ERR(msg,ecode)

def get_response(ser):
    answer = ""
    resp=ser.read()
    while resp != "":
        answer += resp
        resp = ser.read()
    return answer

def handle_init(resp):
    lines = resp.split("\r\n")
    while '' in lines:
        lines.remove('')

    CHK( "Chip ID" in lines[1], RESP_ERR,3)

    _,_,chip,_,version,_,_,chipid = lines[1].split(" ")
    INFO( "Bootloader '%s' version: '%s' ChipID: '%s'" % (chip,version,chipid) )
    return (version,chipid)

def upload(ser,path,flashsize,bootloadersize,shouldverify=True,destructive=False,runapp=False):
    run = True
    while run:
        try:
            f = open(path,"rb")
        except IOError:
            CHK( False, "'%s': can't open file" % path,5)

        print 'Sending upload command'
        # upload command
        if destructive:
            ser.write('d')
        else:
            ser.write('u')

        def ser_write(msg,timeout=1):
            ser.write_timeout = timeout
            return ser.write(msg)

        def ser_read(size,timeout=1):
            ser.timeout = timeout
            return ser.read(size)

        lines = []
        resp=""
        while len(lines)<3 and not resp.endswith('C'):
            resp+=get_response(ser)
            lines = resp.split('\r\n')
        CHK( lines[1] == 'Ready', RESP_ERR, 3 )

        modem = XMODEM(ser_read, ser_write, pad='\xff')
        print 'Starting XMODEM transfer'
        modem.send(f)
        f.close()

        ser.timeout = 0
        ser.write_timeout = 0

        print 'XMODEM transfer completed'

        if shouldverify:
            print 'Verifying checksum'
            run = not verify(ser,path,flashsize,bootloadersize,destructive)
            if run: #verify failed
                input_ok = False
                while not input_ok:
                    tmp = raw_input( "Verify failed! Retry? [Y|n]" )
                    if  len(tmp) == 0 or tmp.upper() == 'Y':
                        input_ok = True
                    elif tmp.upper() == 'N':
                        input_ok = True
                        CHK( False, "Verify failed! Uploaded programm may be inconsistent!", 6)
        else:
            run = False
    if runapp:
        print 'Starting application'
        ser.write('b')

def verify(ser,path,flashsize,bootloadersize,destructive=False):
    try:
        f = open(path,"rb")
    except IOError:
        CHK( False, "'%s': can't open file" % path,5)
    data = f.read()

    f.close()
    modem = XMODEM(None,None)

    if destructive:
        ser.write('v')
        #no prefixed bytes, since uploading a bootloader
        bootloadersize = 0x0000
    else:
        ser.write('c')

    lines = []
    resp=""
    while len(lines)<3:
        resp+=get_response(ser)
        lines = resp.split('\r\n')
    CHK( lines[1].startswith("CRC:" ), RESP_ERR, 3 )
    testcrc=lines[1][9:]

    crc = int(modem.calc_crc(data))
    # rest of the flash is 0xFF
    for i in xrange( flashsize-len(data)-bootloadersize ):
        crc = modem.calc_crc( '\xFF',crc )

    crc = hex(crc)[2:].upper()
    #extend to 4 chars
    crc = (4-len(crc))*"0"+crc
    print "CRC",crc,testcrc
    if testcrc == crc:
        INFO("Verify OK!")
    return testcrc == crc

def main(args):
    """
    Usage:
        efm32isp [(--verify|--noverify)] [options] <binfile>

    Options:
        -h --help                  Prints this help message
        -d                         Destructive upload, overwrites the bootloader
        -r --run                   Run application after successful upload
        -p <port>, --port=<port>   Sets the UART port, any valid pyserial string is
                                   possible [default: /dev/ttyUSB0].
        -b <port>, --baud=<baud>   Sets the UART baud rate [default: 115200].
        -f <size>, --flashs=<size> Sets the programmflash size of the MCU (needed for
                                   verify) [default: 0x10000]
        -s <size>, --boots=<size>  Sets the size reserved for the bootloader (needed
                                   non destructive verify) [default: 0x4000]
    """
    argp = docopt(main.__doc__,version="efm32isp 2016-11-04")
    try:
        ser = serial.Serial(argp["--port"], argp["--baud"], timeout=0, bytesize=8, parity=serial.PARITY_NONE, stopbits=1)
    except serial.serialutil.SerialException as ex:
        ERR("Couldn't open serial port '" + argp["--port"] + "'" + os.linesep + str(ex),1)
    if not ser.isOpen():
        ERR("Couldn't open serial port '" + argp["--port"] + "'",1)

    sys.stdout.write("Put the chip into bootloader mode!\n")
    sys.stdout.write("Waiting for bootloader to respond ")
    sys.stdout.flush()
    resp = ""
    tries = 10
    while resp == "":
        #trigger auto baud rate configuration
        ser.write("i")
        time.sleep(1.0/10)
        resp = get_response(ser)
        for i in range(5):
            sys.stdout.write(".")
            sys.stdout.flush()
            time.sleep(1.0/10)
        tries -= 1
        if tries < 0:
            INFO(" ERROR")
            ERR("Bootloader not responding!",2)
    INFO("") #newline

    handle_init(resp)
    if argp["--verify"]:
        # only a verify
        verify(
            ser,
            argp["<binfile>"],
            int(argp["--flashs"],16),
            int(argp["--boots"],16),
            argp["-d"])
    else:
        upload(
            ser,
            argp["<binfile>"],
            int(argp["--flashs"],16),
            int(argp["--boots"],16),
            not argp["--noverify"],
            argp["-d"],
            argp["--run"])

if __name__ == "__main__":
    main(sys.argv)

