#!/usr/bin/env python
""" RFID reader """

import os
import sys
import logging
import time
import io
from datetime import datetime
import threading
from evdev import InputDevice, categorize #, _ecodes
from evdev.ecodes import EV_KEY
from sig_app import Application
from pg_app import PGapp
import log_app

RFID_NAME = 'RFID'
DEV_DIR = '/dev/input'
SQL_INSERT = """INSERT INTO rep.rfid_history(card_num) VALUES('{}');"""

class StoppableThread(threading.Thread):
    """Thread class with a stop() method. The thread itself has to check
    regularly for the stopped() condition."""

    def __init__(self, *args, **kwargs):
        super(StoppableThread, self).__init__(*args, **kwargs)
        self._stop_event = threading.Event()

    def stop(self):
        """ stop thread """
        self._stop_event.set()

    def stopped(self):
        """ check if stopped """
        return self._stop_event.is_set()


class CSVWriter(PGapp):
    """ Monitor csv dir and write found files to PG """
    # def __init__(self, pg_host, pg_user, config):
    def __init__(self, config):
        self.config = config
        #super(CSVWriter, self).__init__(pg_host, pg_user)
        super(CSVWriter, self).__init__(self.config['PG']['pg_host'],\
                self.config['PG']['pg_user'])
        if self.pg_connect():
            self.set_session(autocommit=True)
        if 'base_dir' in self.config['DIRS'].keys():
            self.base_dir = self.config['DIRS']['base_dir']
        else:
            self.base_dir = os.path.dirname(__file__)
        self.csv_dir = '{}/{}'.format(self.base_dir, self.config['DIRS']['csv_dir'])
        self.arch_dir = '{}/{}'.format(self.base_dir, self.config['DIRS']['arch_dir'])
        self.failed_dir = '{}/{}'.format(self.base_dir, self.config['DIRS']['failed_dir'])
        self.csv_list = []
        self.do_loop = True

    # def chk_csv_dir(self, csv_dir, arch_dir, failed_dir, stop):
    def chk_csv_dir(self, stop):
        """ Read "csv_dir" everey chk_period and write found files to PG
        """
        csv_str = ''
        chk_period = 5
        logging.debug('listdir of %s', self.csv_dir)
        while self.do_loop:
            fcsv_list = sorted(os.listdir(self.csv_dir))
            logging.debug('fcsv_list=%s', fcsv_list)
            self.csv_list.clear()
            for fcsv in fcsv_list:
                logging.debug('reading csv file %s', fcsv)
                with open('{}/{}'.format(self.csv_dir, fcsv), 'r') as csv:
                    csv_str = csv.readline()[:-1]
                if csv_str:
                    self.csv_list.append(csv_str)
                    csv_str = ''
            if self.csv_list:
                logging.info('Found: csv_list=%s', self.csv_list)
                csv_io = io.StringIO('\n'.join(self.csv_list))
                res = self.copy_from(csv_io, 'rep.rfid_history', sep='^', \
                        columns=('card_num', 'dt_read'), reconnect=True)
                if res == 1:
                    # move csv to 99-archive
                    for fcsv in fcsv_list:
                        os.rename('{}/{}'.format(self.csv_dir, fcsv), \
                                '{}/{}'.format(self.arch_dir, fcsv))
                elif res == 2: # reconnect done but not copied
                    pass # copy in the next loop
                else:
                    for fcsv in fcsv_list:
                        os.rename('{}/{}'.format(self.csv_dir, fcsv), \
                                '{}/{}'.format(self.failed_dir, fcsv))

            logging.debug('Sleeping for %s...', chk_period)
            time.sleep(chk_period)
            self.do_loop = not stop()

    def _db_write(self):
        """ write to table rep.rfid_history """
        if not self.conn:
            logging.info('DB not connected. Try to re-connect.')
            if self.pg_connect():
                self.set_session(autocommit=True)

        card_num = ''  # read from 02-csv/*csv
        if self.do_query(SQL_INSERT.format(card_num)):
            logging.info('Saved to DB')

class RFIDReader(Application, log_app.LogApp):
    """ RFID Reader loop app """

    dev_id_dir = '%s/by-id' % DEV_DIR
    def __init__(self, args):
        self.do_read_one = True
        self.card_num_list = []
        self.postponed = False
        log_app.LogApp.__init__(self, args=args)
        script_name = os.path.splitext(os.path.basename(__file__))[0]
        self.get_config('{}.conf'.format(script_name))
        super(RFIDReader, self).__init__()
        self.reader = InputDevice(self.dev_file)
        self.reader.grab()

        self.csv_writer = CSVWriter(self.config)
        logging.debug('base_dir=%s', self.base_dir)
        #self.tmp_dir = ''
        #self.csv_dir = ''

    @property
    def base_dir(self):
        """ base_dir from conf file if present """
        if 'base_dir' in self.config['DIRS'].keys():
            loc_dir = self.config['DIRS']['base_dir']
        else:
            loc_dir = os.path.dirname(__file__)
        return loc_dir

    @property
    def tmp_dir(self):
        """ tmp_dir from conf file """
        return '{}/{}'.format(self.base_dir, self.config['DIRS']['tmp_dir'])

    @property
    def csv_dir(self):
        """ csv_dir from conf file """
        return '{}/{}'.format(self.base_dir, self.config['DIRS']['csv_dir'])

    @property
    def dev_file(self):
        """ Find RFID reader in /dev/input """

        dev_file = None
        for inp in os.listdir(self.dev_id_dir):
            if RFID_NAME in inp:
                dev_link = os.readlink('%s/%s' % (self.dev_id_dir, inp))
                dev_file = '%s/%s' % (DEV_DIR, dev_link.replace('../', ''))
                logging.info('RFID device found=%s', dev_file)
                break
        if not dev_file:
            raise NameError('RFID [{}] reader not found'. format(RFID_NAME))
        return dev_file

    def _signal_handler(self):
        logging.info('RFID signal_handler')
        self.do_read_one = False
        super(RFIDReader, self)._signal_handler()


    def _write_card_num(self):
        """ Write card_num to CSV """
        card_num = ''.join(self.card_num_list)
        logging.info('Try to save card_num=%s', card_num)
        csv_str = '{}^{}'.format(card_num, datetime.now())

        tmp_file = '{}/{}-{}.tmp'.format(self.tmp_dir, int(time.time()), card_num)
        with open(tmp_file, 'w') as tmp:
            try:
                tmp.write(csv_str + '\n')
            except IOError as err:
                logging.error('Cannot write csv=[%s] to tmp_file. err=%s', csv_str, err)
            except:
                logging.error("Unexpected error:%s", sys.exc_info()[0])
                raise
            else:
                logging.info('Written to tmp:%s', tmp_file)
                csv_file = '{}/{}.csv'.format(self.csv_dir, \
                        os.path.splitext(os.path.basename(tmp_file))[0])
                os.rename(tmp_file, csv_file)

    def _proc_until_enter(self, arg_event):
        """ recognize pressed key """
        res = False
        c_ev = categorize(arg_event)
        if c_ev.keystate == 0:  # key UP
            logging.debug('st=%s, code=%s', c_ev.keystate, c_ev.keycode)
            if c_ev.keycode != 'KEY_ENTER':  # and c_ev.keystate == 0:
                self.card_num_list.append(c_ev.keycode.replace('KEY_', ''))
            else:
                logging.debug('ENTER detected. Exiting...')
                res = True
        return res

    @property
    def _missed_dirs(self):
        missed_dirs = []
        for i_dir in self.config['DIRS'].values():
            logging.debug('check config dir=%s', i_dir)
            loc_dir = '{}/{}'.format(self.base_dir, i_dir)
            if not os.path.exists(loc_dir):
                logging.error('missed loc_dir=%s', loc_dir)
                missed_dirs.append(i_dir)
        return missed_dirs

    def _main(self):
        """ Just main """

        self.terminated = self._missed_dirs
        if self.terminated:
            return

        #self.tmp_dir = '{}/{}'.format(self.base_dir, self.config['DIRS']['tmp_dir'])
        #self.csv_dir = '{}/{}'.format(self.base_dir, self.config['DIRS']['csv_dir'])

        th_csv = StoppableThread(target=self.csv_writer.chk_csv_dir, \
                kwargs={"stop": lambda: self.terminated})
        """
        th_csv = StoppableThread(target=self.csv_writer.chk_csv_dir, \
                kwargs={"csv_dir": self.config['DIRS']['csv_dir'],
                        "arch_dir": self.config['DIRS']['arch_dir'],
                        "failed_dir": self.config['DIRS']['failed_dir'],
                        "stop": lambda: self.terminated})
        """
        th_csv.start()

        while not self.terminated:
            self.card_num_list = []
            #for event in READER.read_loop():
            self.do_read_one = True
            logging.debug('DB Thread is_alive=%s', th_csv.is_alive())
            while self.do_read_one:
                event = self.reader.read_one()
                if event and event.type == EV_KEY:  # read completed and EV_KEY
                    if self._proc_until_enter(event):
                        self._write_card_num()
                        break
        if th_csv:
            th_csv.stop()

    def close(self):
        """ Close everything """
        self.reader.ungrab()
        self.reader.close()
        self.csv_writer.pg_close()


#        with open(self.config['FILES']['RFID_CSV_FILE'], 'a') as csv:


if __name__ == '__main__':
    ARGS = log_app.PARSER.parse_args()
    APP = RFIDReader(args=ARGS)  #, pg_host='vm-pg-restore.arc.world', pg_user='arc_energo')
    APP.main_loop()
    APP.close()
