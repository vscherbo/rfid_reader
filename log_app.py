#!/usr/bin/env python3
""" A template of a logging application
"""

import sys
import logging
import argparse
import configparser

class LogApp():
    """ A logging application """
    #log_format = '[%(filename)-21s:%(lineno)4s - %(funcName)20s()] \
    #        %(levelname)-7s | %(asctime)-15s | %(message)s'

    def __init__(self, args, description='Logging application'):
        self.args = args
        self.config = None
        logging.getLogger(__name__).addHandler(logging.NullHandler())
        numeric_level = getattr(logging, self.args.log_level, None)
        if not isinstance(numeric_level, int):
            raise ValueError('Invalid log level: %s' % numeric_level)

        self.set_log_format()
        if self.args.log_file == 'stdout':
            logging.basicConfig(stream=sys.stdout, format=self.log_format, level=numeric_level)
        else:
            logging.basicConfig(filename=self.args.log_file, format=self.log_format, \
                    level=numeric_level)

    def set_log_format(self, log_format='[%(filename)-21s:%(lineno)4s - %(funcName)20s()] \
            %(levelname)-7s | %(asctime)-15s | %(message)s'):
        """ Set logging format """
        self.log_format = log_format

    def get_config(self, conf_name='', allow_no_value=True):
        """ initialize and read config """
        self.config = configparser.ConfigParser(allow_no_value=allow_no_value)
        #logging.info('Config "%s" reading', self.args.conf)
        if self.args.conf:
            logging.info('Config %s reading', self.args.conf)
            conf_name = self.args.conf
        self.config.read(conf_name)


CONF_FILE_NAME = ""
PARSER = argparse.ArgumentParser()
PARSER.add_argument('--conf', type=str, default=CONF_FILE_NAME, help='conf file')
PARSER.add_argument('--log_file', type=str, default='stdout', help='log destination')
PARSER.add_argument('--log_level', type=str, default="DEBUG", help='log level')
