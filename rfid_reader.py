#!/usr/bin/env python
""" RFID reader """

import os
from evdev import InputDevice, categorize #, _ecodes
from evdev.ecodes import EV_KEY
from sig_app import Application
from pg_app import PGapp

SQL_INSERT = """INSERT INTO rep.rfid_history(card_num) VALUES('{}');"""

class RFIDReader(Application, PGapp):
    """ RFID Reader loop app """

    def __init__(self, pg_host, pg_user):
        self.do_read_one = True
        self.card_num_list = []
        self.c_ev = {}
        super(RFIDReader, self).__init__()
        PGapp.__init__(self, pg_host=pg_host, pg_user=pg_user)

    def _signal_handler(self):
        print('RFID signal_handler')
        self.do_read_one = False
        super(RFIDReader, self)._signal_handler()

    def _write_card_num(self):
        """ Write card_num to PG and csv """
        card_num = ''.join(self.card_num_list)
        print(card_num)
        with open(RFID_CSV_FILE, 'a') as csv:
            csv.write(card_num + '\n')
        if not self.do_query(SQL_INSERT.format(card_num)):
            print('DB Error')
            # write to local CSV file

    def _proc_until_enter(self):
        """ recognize pressed key """
        res = False
        if self.c_ev.keystate == 0:  # key UP
            #print(c_ev, type(c_ev))
            print('st={}, code={}'.format(self.c_ev.keystate, self.c_ev.keycode))
            if self.c_ev.keycode != 'KEY_ENTER':  # and c_ev.keystate == 0:
                self.card_num_list.append(self.c_ev.keycode.replace('KEY_', ''))
            else:
                print('ENTER detected. Exiting...')
                res = True
        return res


    def _main(self):
        """ Just main """

        #print(READER.capabilities())
        #cp = READER.capabilities(verbose=True)
        #print(cp)
        """
        for cp_k, cp_v in CP[('EV_KEY', 1)]:
            print(cp_k, cp_v)
        """
        while not self.terminated:
            self.card_num_list = []
            #for event in READER.read_loop():
            self.do_read_one = True
            while self.do_read_one:
                event = READER.read_one()
                if event and event.type == EV_KEY:
                    self.c_ev = categorize(event)
                    if self._proc_until_enter():
                        self._write_card_num()
                        break



if __name__ == '__main__':
    # move to conf
    RFID_NAME = 'RFID'
    DEV_DIR = '/dev/input'
    DEV_ID_DIR = '%s/by-id' % DEV_DIR
    RFID_CSV_FILE = 'card_history.csv'

    for inp in os.listdir(DEV_ID_DIR):
        if RFID_NAME in inp:
            dev_link = os.readlink('%s/%s' % (DEV_ID_DIR, inp))
            dev_file = '%s/%s' % (DEV_DIR, dev_link.replace('../', ''))
            #print(dev_file)

    READER = InputDevice(dev_file)
    READER.grab()

    APP = RFIDReader(pg_host='vm-pg-devel.arc.world', pg_user='arc_energo')
    APP.wait_pg_connect()
    APP.set_session(autocommit=True)
    APP.main_loop()

    READER.ungrab()
    READER.close()
