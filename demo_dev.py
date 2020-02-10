#!/usr/bin/env python
""" Test RFID reader """

#import logging
import signal
import os
#from evdev.ecodes import ecodes
from evdev import InputDevice, categorize #, _ecodes
from evdev.ecodes import EV_KEY
#from evdev.ecodes import KEY_ENTER

def signal_handler(arg_signal, arg_frame):
    """ Stop reader loop """
    #logging.info('Catched signal %s', arg_signal)
    #global do_read
    print('Catched signal %s, (%s)' % (arg_signal, arg_frame))
    READER.close()
    #do_read = False

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGHUP, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGUSR1, signal_handler)

def main():
    """ Just main """

    #print(READER.capabilities())
    #cp = READER.capabilities(verbose=True)
    #print(cp)
    """
    for cp_k, cp_v in CP[('EV_KEY', 1)]:
        print(cp_k, cp_v)
    """
    do_read = True
    while do_read:
        card_num = []
        for event in READER.read_loop():
            if event.type == EV_KEY:
                c_ev = categorize(event)
                if c_ev.keystate == 0:
                    #print(c_ev, type(c_ev))
                    print('st={}, code={}'.format(c_ev.keystate, c_ev.keycode))
                    if c_ev.keycode != 'KEY_ENTER':  # and c_ev.keystate == 0:
                        card_num.append(c_ev.keycode.replace('KEY_', ''))
                    else:
                        print('ENTER detected. Exiting...')
                        break

        print(''.join(card_num))



if __name__ == '__main__':
    DEV_DIR = '/dev/input'
    DEV_ID_DIR = '%s/by-id' % DEV_DIR
    for inp in os.listdir(DEV_ID_DIR):
        if 'RFID' in inp:
            dev_link = os.readlink('%s/%s' % (DEV_ID_DIR, inp))
            dev_file = '%s/%s' % (DEV_DIR, dev_link.replace('../', ''))
            #print(dev_file)


    READER = InputDevice(dev_file)
    READER.grab()
    main()
    READER.ungrab()
    READER.close()
