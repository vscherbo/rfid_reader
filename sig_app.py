#!/usr/bin/env python
""" Application with signal handler
"""
import time
import signal

class Application:
    """ class for apps with signal handle """
    def __init__(self):
        signal.signal(signal.SIGINT, lambda signal, frame: self._signal_handler())
        self.terminated = False

    def _signal_handler(self):
        self.terminated = True
        print('signal_handler')

    def _main(self):
        print("I'm %s", self.__dict__)
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
