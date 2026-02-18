#!/usr/bin/env python
""" RFID reader """

import io
import logging
import os
import sys
import threading
import time
from datetime import datetime

import log_app
import pg_app
from evdev import InputDevice, categorize  # , _ecodes
from evdev.ecodes import EV_KEY
from sig_app import Application

RFID_NAME = 'RFID'
DEV_DIR = '/dev/input'
SQL_INSERT = """INSERT INTO rep.rfid_history(card_num) VALUES('{}');"""
DOOR_LOCK_LINE = 68
# 3 system and Alex
SYSTEM_CARDS = ['0014966852', '0014952315', '0014951743', '0001597675', '1528324331']

SEL_CARD = "SELECT * FROM rep.rfid_emp_name WHERE card_num=%s;"


class StoppableThread(threading.Thread):
    """Thread class with a stop() method. The thread itself has to check
    regularly for the stopped() condition."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._stop_event = threading.Event()

    def stop(self):
        """ stop thread """
        self._stop_event.set()

    def stopped(self):
        """ check if stopped """
        return self._stop_event.is_set()


class CSVWriter(pg_app.PGapp):
    """ Monitor csv dir and write found files to PG """
    # def __init__(self, pg_host, pg_user, config):

    def __init__(self, config):
        self.config = config
        # super(CSVWriter, self).__init__(pg_host, pg_user)
        super().__init__(self.config['PG']['pg_host'],
                         self.config['PG']['pg_user'])
        if self.pg_connect():
            self.set_session(autocommit=True)
        if 'base_dir' in self.config['DIRS'].keys():
            self.base_dir = self.config['DIRS']['base_dir']
        else:
            self.base_dir = os.path.dirname(__file__)
        # self.csv_dir = '{}/{}'.format(self.base_dir, self.config['DIRS']['csv_dir'])
        # self.arch_dir = '{}/{}'.format(self.base_dir, self.config['DIRS']['arch_dir'])
        # self.failed_dir = '{}/{}'.format(self.base_dir, self.config['DIRS']['failed_dir'])
        self.csv_dir = f'{self.base_dir}/{self.config["DIRS"]["csv_dir"]}'
        self.arch_dir = f'{self.base_dir}/{self.config["DIRS"]["arch_dir"]}'
        self.failed_dir = f'{self.base_dir}/{self.config["DIRS"]["failed_dir"]}'
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
            if len(fcsv_list) > 0:
                logging.debug('fcsv_list=%s', fcsv_list)
            self.csv_list.clear()
            for fcsv in fcsv_list:
                logging.debug('reading csv file %s', fcsv)
                with open(f'{self.csv_dir}/{fcsv}', 'r', encoding='utf8') as csv:
                    csv_str = csv.readline()[:-1]
                if csv_str:
                    self.csv_list.append(csv_str)
                    csv_str = ''
            if self.csv_list:
                logging.info('Found: csv_list=%s', self.csv_list)
                csv_io = io.StringIO('\n'.join(self.csv_list))
                res = self.copy_from(csv_io, 'rep.rfid_history', sep='^',
                                     columns=('card_num', 'dt_read'), reconnect=True)
                if res == 1:
                    # move csv to 99-archive
                    for fcsv in fcsv_list:
                        os.rename(f'{self.csv_dir}/{fcsv}', f'{self.arch_dir}/{fcsv}')
                elif res == 2:  # reconnect done but not copied
                    pass  # copy in the next loop
                else:
                    for fcsv in fcsv_list:
                        os.rename(f'{self.csv_dir}/{fcsv}', f'{self.failed_dir}/{fcsv}')

            # logging.debug('Sleeping for %s...', chk_period)
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

    def check_card_num_simple(self, card_num):
        """ lookup card_num in PG """
        if card_num in SYSTEM_CARDS:
            logging.info('SYSTEM card %s detected', card_num)
            res = True
        else:
            # lookup in PG
            res = card_num  # DEBUG
            res = False  # DEBUG
            logging.info('NOT system card %s detected', card_num)
        return res

    def check_card_num(self, card_num):
        """ lookup card_num in PG """
        if card_num in SYSTEM_CARDS:
            logging.info('SYSTEM card %s detected', card_num)
            res = True
        else:
            # lookup in PG
            # PROD:
            res = False
            # DEBUG only: res = True
            # self.pg_connect(cursor_factory=pg_app.psycopg2.extras.RealDictCursor)
            self.curs_dict = self.conn.cursor(cursor_factory=pg_app.psycopg2.extras.RealDictCursor)
            try:
                sql = self.curs.mogrify(SEL_CARD, (card_num,))
                logging.debug('curs sql=%s', sql)
                sql = self.curs_dict.mogrify(SEL_CARD, (card_num,))
                logging.debug('curs_dict sql=%s', sql)
                if self.do_query(sql, reconnect=True, dict_mode=True):
                    rec = self.curs_dict.fetchone()
                    logging.debug('curs_dict rec=%s', rec)
                    # rec = self.curs.fetchone()
                    if rec:
                        try:
                            logging.debug('rec[card_num]=%s, rec[Имя]=%s, card_num=%s', rec['card_num'],
                                          rec['Имя'],
                                          card_num)
                            res = rec['card_num'] == card_num
                        except Exception as excp:
                            logging.error('An exception excp=%s', str(excp))
            except Exception as excp:
                logging.error('An exception excp=%s', str(excp))
            if res:
                # logging.info('Detected user=%s, card=%s', rec['Имя'], card_num)
                logging.info('Debug PG query, card=%s', card_num)
            else:
                logging.warning('NOT registered card %s detected', card_num)
        logging.debug('Exiting with res=%s', res)

        # DEBUG only res = True
        return res


class RFIDReader(Application, log_app.LogApp):
    """ RFID Reader loop app """
    # pylint: disable=too-many-instance-attributes
    # dev_id_dir = '%s/by-id' % DEV_DIR
    dev_id_dir = f'{DEV_DIR}/by-id'

    def __init__(self, args):
        self.do_read_one = True
        self.card_num_list = []
        log_app.LogApp.__init__(self, args=args)
        script_name = os.path.splitext(os.path.basename(__file__))[0]
        self.get_config(f'{script_name}.conf')
        super().__init__()
        self.reader = InputDevice(self.dev_file)
        self.reader.grab()

        self.csv_writer = CSVWriter(self.config)
        logging.debug('base_dir=%s', self.base_dir)
        # self.tmp_dir = ''
        # self.csv_dir = ''
        self.card_num = None
        self.chip = gpiod.Chip('gpiochip0')
        self.line = self.chip.get_line(DOOR_LOCK_LINE)
        self.line.request(consumer='rfid_reader', type=gpiod.LINE_REQ_DIR_OUT)

    @ property
    def base_dir(self):
        """ base_dir from conf file if present """
        if 'base_dir' in self.config['DIRS'].keys():
            loc_dir = self.config['DIRS']['base_dir']
        else:
            loc_dir = os.path.dirname(__file__)
        return loc_dir

    @ property
    def tmp_dir(self):
        """ tmp_dir from conf file """
        return f"{self.base_dir}/{self.config['DIRS']['tmp_dir']}"

    @ property
    def csv_dir(self):
        """ csv_dir from conf file """
        return f"{self.base_dir}/{self.config['DIRS']['csv_dir']}"

    @ property
    def dev_file(self):
        """ Find RFID reader in /dev/input """

        dev_file = None
        for inp in os.listdir(self.dev_id_dir):
            if RFID_NAME in inp:
                # dev_link = os.readlink('%s/%s' % (self.dev_id_dir, inp))
                # dev_file = '%s/%s' % (DEV_DIR, dev_link.replace('../', ''))
                dev_link = os.readlink(f'{self.dev_id_dir}/{inp}')
                dev_file = f'{DEV_DIR}/{dev_link.replace("../", "")}'
                logging.info('RFID device found=%s', dev_file)
                break
        if not dev_file:
            raise NameError(f'RFID [{RFID_NAME}] reader not found')
        return dev_file

    def _signal_handler(self):
        logging.info('RFID signal_handler')
        self.do_read_one = False
        super()._signal_handler()

    def _write_card_num(self):
        """ Write card_num to CSV """
        logging.info('Try to save card_num=%s', self.card_num)
        csv_str = f'{self.card_num}^{datetime.now()}'

        tmp_file = f'{self.tmp_dir}/{int(time.time())}-{self.card_num}.tmp'
        with open(tmp_file, 'w', encoding='utf8') as tmp:
            try:
                tmp.write(csv_str + '\n')
            except IOError as err:
                logging.error('Cannot write csv=[%s] to tmp_file. err=%s', csv_str, err)
            except BaseException:
                logging.error("Unexpected error:%s", sys.exc_info()[0])
                raise
            else:
                logging.info('Written to tmp:%s', tmp_file)
                csv_file = f'{self.csv_dir}/{os.path.splitext(os.path.basename(tmp_file))[0]}.csv'
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
                self.card_num = ''.join(self.card_num_list)
                res = True
        return res

    def open_door(self):
        """ open door if self.card_num found in DB """
        # if self.csv_writer.check_card_num(self.card_num):
        logging.debug('start with card_num=%s', self.card_num)
        loc_res = self.csv_writer.check_card_num(self.card_num)
        logging.debug('loc_res=%s', loc_res)

        if loc_res:
            self.line.set_value(1)  # HIGH
            time.sleep(0.1)
            self.line.set_value(0)  # LOW

    @ property
    def _missed_dirs(self):
        missed_dirs = []
        for i_dir in self.config['DIRS'].values():
            logging.debug('check config dir=%s', i_dir)
            loc_dir = f'{self.base_dir}/{i_dir}'
            if not os.path.exists(loc_dir):
                logging.error('missed loc_dir=%s', loc_dir)
                missed_dirs.append(i_dir)
        return missed_dirs

    def _main(self):
        """ Just main """

        self.terminated = self._missed_dirs
        if self.terminated:
            return

        # self.tmp_dir = '{}/{}'.format(self.base_dir, self.config['DIRS']['tmp_dir'])
        # self.csv_dir = '{}/{}'.format(self.base_dir, self.config['DIRS']['csv_dir'])

        th_csv = StoppableThread(target=self.csv_writer.chk_csv_dir,
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
            # for event in READER.read_loop():
            self.do_read_one = True
            logging.debug('DB Thread is_alive=%s', th_csv.is_alive())
            while self.do_read_one:
                event = self.reader.read_one()
                if event and event.type == EV_KEY:  # read completed and EV_KEY
                    if self._proc_until_enter(event):
                        self._write_card_num()
                        try:
                            self.open_door()  # with checking self.card_num
                        except Exception as excp:
                            logging.error('open_door exception=%s', str(excp))
                        break
        if th_csv:
            th_csv.stop()

    def close(self):
        """ Close everything """
        self.reader.ungrab()
        self.reader.close()
        self.line.release()
        self.chip.close()
        self.csv_writer.pg_close()


#        with open(self.config['FILES']['RFID_CSV_FILE'], 'a') as csv:


if __name__ == '__main__':
    sys.path.append('/usr/lib/python3/dist-packages')
    import gpiod
    ARGS = log_app.PARSER.parse_args()
    APP = RFIDReader(args=ARGS)  # , pg_host='vm-pg-restore.arc.world', pg_user='arc_energo')
    APP.main_loop()
    APP.close()
