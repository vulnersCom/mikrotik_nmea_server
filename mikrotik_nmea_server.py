#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  VULNERS OPENSOURCE
#  __________________
#
#  Vulners Project [https://vulners.com]
#  All Rights Reserved.
#
# This is simple server that receives Mikrotik GPS NMEA logs and reserves them in NMEA TCP
# To produce GPS logs export at Mikrotik go to System -> Logging
# Add in Actions new action: "remoteGPS" with mode "remote", IP of your server and port 514
# Add in Rules new rule: topic - GPS, action "remoteGPS"
# It will send UDP Syslog with NMEA data to this server.
# In OpenCPN / Navionics add new connection, server IP address, mode "TCP", port 2000
# Enjoy NMEA0183 GPS data in your applications :)


__author__ = "Kir Ermakov <isox@vulners.com>"
__version__ = "1.0"

import socketserver
import logging
import signal
from threading import Thread, Lock
import queue



# UDP Syslog-style receiver server parameters
RECEIVER_HOST, RECEIVER_PORT = "0.0.0.0", 514
# NMEA TCP server parameters
SERVER_HOST, SERVER_PORT = "0.0.0.0", 2000

class ThreadSafeDict(dict) :
    def __init__(self, * p_arg, ** n_arg) :
        dict.__init__(self, * p_arg, ** n_arg)
        self._lock = Lock()

    def __enter__(self) :
        self._lock.acquire()
        return self

    def __exit__(self, type, value, traceback) :
        self._lock.release()

class ExceptionThread(Thread):

    logger = logging
    _return = None

    def run(self):
        try:
            try:
                if self._target:
                    self._return = self._target(*self._args, **self._kwargs)
            except Exception as e:
                self.logger.exception("Exception catched calling target: %s during ExceptionThread" % self._target)
                self._return = e
        finally:
            del self._target, self._args, self._kwargs

    def join(self, *args):
        Thread.join(self, *args)
        return self._return

class SyslogUDPHandler(socketserver.BaseRequestHandler):
    """
    Decodes syslog data and transforms it to NMEA-compatible format
    """

    def handle(self):
        data = bytes.decode(self.request[0].strip(), encoding="utf-8")
        if data:
            try:
                nmea_string = data.split("gps,raw")[1].strip()
            except:
                logging.error("Received malformed Mikrotik GPS log message: %s" % data)
                return
            for key in clients_data_queue:
                clients_data_queue[key].put(nmea_string)

class NMEAHandler(socketserver.BaseRequestHandler):
    """
    The request handler class for our server.

    It is instantiated once per connection to the server, and must
    override the handle() method to implement communication to the
    client.
    """

    def handle(self):
        while 1:
            address = self.client_address[0]
            if not clients_data_queue.get(address):
                clients_data_queue[address] = queue.Queue(maxsize=50)

            while not clients_data_queue[address].empty():
                data = clients_data_queue[address].get()
                try:
                    self.request.sendall(data.encode('utf-8'))
                    print("Responding %s with :%s" % (address, data))
                except:
                    return

clients_data_queue = ThreadSafeDict()
syslog_server = socketserver.UDPServer((RECEIVER_HOST, RECEIVER_PORT), SyslogUDPHandler)
nmea_server = socketserver.ThreadingTCPServer((SERVER_HOST, SERVER_PORT), NMEAHandler)
syslog_thread = ExceptionThread(target = syslog_server.serve_forever)
nmea_thread = ExceptionThread(target = nmea_server.serve_forever)

def exit_gracefully(signum, frame):
    # restore the original signal handler as otherwise evil things will happen
    # in raw_input when CTRL+C is pressed, and our signal handler is not re-entrant
    signal.signal(signal.SIGINT, original_sigint)
    syslog_server.shutdown()
    nmea_server.shutdown()
    syslog_thread.join()
    nmea_thread.join()
    # restore the exit gracefully handler here
    signal.signal(signal.SIGINT, exit_gracefully)

if __name__ == "__main__":
    original_sigint = signal.getsignal(signal.SIGINT)
    signal.signal(signal.SIGINT, exit_gracefully)
    syslog_thread.start()
    nmea_thread.start()
