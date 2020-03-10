#!/usr/bin/env python
""" Application with signal handler
"""
import time
import signal
import logging

class Application:
    """ class for apps with signal handle """
    def __init__(self):
        logging.getLogger(__name__).addHandler(logging.NullHandler())
        signal.signal(signal.SIGINT, lambda signal, frame: self._signal_handler())
        self.terminated = False

    def _signal_handler(self):
        self.terminated = True
        logging.debug('%s signal_handler', __name__)

    def _main(self):
        logging.debug("Default _main() proc: %s", self.__dict__)
        time.sleep(3)


    def main_loop(self):
        """ loop while not terminated """
        while not self.terminated:
            self._main()

    def method_1(self):
        """ some method """

if __name__ == '__main__':
    APP = Application()
    APP.main_loop()

    print("The app is terminated, exiting ...")
