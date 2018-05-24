# -*- coding:utf-8 -*-
"""
A simple thread class that connects to the SiTCP device and receive the data.
Received data passes to the DaqHandler derived class.

Copyright (c) 2018, Bee Beans Technologies Co.,Ltd.
"""

from __future__ import print_function

import datetime
from logging import getLogger, StreamHandler, INFO
import os
import select
import socket
import threading
import time
import traceback

from sitcpy import total_seconds, Queue, Full, Empty
import sitcpy


LOGGER = getLogger(__name__)
HANDLER = StreamHandler()
HANDLER.setLevel(INFO)
LOGGER.setLevel(INFO)
LOGGER.addHandler(HANDLER)


class DaqHandler(object):
    """
    Class for processing the DAQ data.
    Setup to the DaqClient class constructor.
    """

    NOT_STARTED = "---------- --:--:--.------"
    ZERO_DURATION = "0:00:00.000000"

    def __init__(self, data_unit=8):
        """
        Simple rate measurement for the default.
        """
        # TODO: DAQ中以外で意味を持たないフィールドは、1つのオブジェクトにまとめる
        self._start_time = None
        self._end_time = None
        self._current = None  # current time
        self._data_bytes = 0
        # TODO: このレベルのクラスでデータ長を持たせるべきなのか？
        self._data_unit = data_unit

        self._raw_data_queue = None  # raw event data save queue
        self._run_no = 0
        self._raw_no = 0  # raw file divide no.
        self._raw_data_basedir = None
        self._raw_file_prefix = "raw%06u_%03u"  # raw file name format
        self._raw_file_unit = 1024  # file divide unit in Mbytes.(1GB)
        self._raw_file_name = None  # current name
        self._raw_current_size = 0
        # TODO: Stateへ置き換え？
        self._continue_raw_thread = False
        self._raw_save_thread = None

    def get_data_unit(self):
        """
        Returns data unit in bytes
        """
        return self._data_unit

    def on_daq_start(self):
        """
        Called when DAQ is starting.
        """
        LOGGER.debug("DaqHandler.on_daq_start is called.")
        if self._raw_data_queue is not None:
            self._continue_raw_thread = True
            self._raw_no = 0  # #21 reset divided file No.
            self._raw_save_thread = threading.Thread(
                target=self._raw_save_worker)
            self._raw_save_thread.start()
            LOGGER.debug("Started raw event data save worker.")
        else:
            LOGGER.debug("Did not start raw event data save worker.")
        self._current = datetime.datetime.now()
        self._start_time = self._current
        self._end_time = None
        self._data_bytes = 0

    def on_daq_stop(self):
        """
        Called when DAQ is stopping.
        """
        duration = total_seconds(self._current - self._start_time)
        if duration >= 0:
            self._end_time = self._current
            print("DaqHandler.on_daq_stop is called.")
            print("bytes:%s bytes" % self._data_bytes)
            print("duration:%s " % (self._end_time - self._start_time))
            if duration > 0:
                print("MBps:%s " % (self._data_bytes /
                                    duration / 1000000))
                print("Gbps:%s " % (self._data_bytes * 8 /
                                    duration / 1000000000))
                print("Mbps:%s " % (self._data_bytes * 8 /
                                    duration / 1000000))
        if self._raw_data_queue is not None:
            while not self._raw_data_queue.empty():  # 生データ保存用のデータqueueが空になるまで待ちます。
                time.sleep(0.2)
                LOGGER.info("Waiting for raw data writing...%s" % self._raw_data_queue.qsize())
            self._continue_raw_thread = False
            self._raw_save_thread.join(0.2)

    def create_stat_list(self):
        """
        Returns received rate information list
        """
        stat_list = []
        start_time = self.NOT_STARTED
        end_time = self.NOT_STARTED
        duration = self.ZERO_DURATION
        cps = 0.0
        if self._current is not None:
            start_time = str(self._start_time)
            secs = total_seconds(self._current - self._start_time)
            if secs > 0:
                duration = str(self._current - self._start_time)
                cps = (self._data_bytes / self._data_unit) / secs
        if self._end_time is not None:
            end_time = str(self._end_time)
            duration = str(self._end_time - self._start_time)

        stat_list.append("start time=%s" % start_time)
        stat_list.append("end time=%s" % end_time)
        stat_list.append("duration=%s" % duration)
        stat_list.append("events=%s" % str(self._data_bytes / self._data_unit))
        stat_list.append("cps=%g" % cps)
        stat_list.append("bytes=%s" % self._data_bytes)
        if self._raw_data_queue is None:
            stat_list.append("raw data save=off")
        else:
            stat_list.append("raw data queue=%d" %
                             self._raw_data_queue.qsize())

        return stat_list

    def on_daq_running(self):
        """
        Override for DAQ running.
        """
        self._current = datetime.datetime.now()

    def on_daq_data(self, byte_data):
        """
        :type byte_data: bytes
        :param byte_data: Received data.
        """
        self._data_bytes += len(byte_data)
        self._current = datetime.datetime.now()
        self.queue_raw_data(byte_data)  # save raw data if activated.

    def on_daq_error(self, error_exception):
        """
        Called when error detected by the thread class.
        """
        LOGGER.error("DEBUG:daq error %s DAQ error stop. self=%s1",
                     str(error_exception), self)
        self.on_daq_stop()
        LOGGER.info("Daq stop called.")

    def set_raw_save(self, on_off, run_no, base_dir):
        """
        Set raw event data save function on or off.

        :param on_off: True for on, False for off.
        :param run_no: Measurement run no as integer.
        :param base_dir: Base directory to save the files.
        """
        if on_off:
            self._raw_data_basedir = base_dir
            self._run_no = run_no
            # self._raw_file_name = self._raw_file_prefix%(self._run_no, self._raw_no)
            self._raw_data_queue = Queue()
            # self._raw_current_size = 0
            # self._raw_no = 0
        else:
            self._raw_data_queue = None

    def queue_raw_data(self, byte_data):
        """
        Call from on_daq_data().

        :type byte_data: bytes
        """
        if self._raw_data_queue is not None:
            try:
                self._raw_data_queue.put(byte_data, False)
            except Full as exc:
                LOGGER.error("Could not queue raw_data %s", str(exc))

    def _raw_save_worker(self):
        """
        A thread for saving the raw event data to disk.
        Receive raw event data from self._raw_data_queue and write under the
        file on the self._raw_data_basedir.
        """
        LOGGER.debug("Starting raw save worker.")
        if self._raw_data_queue is not None:
            try:
                while self._continue_raw_thread:
                    self._raw_current_size = 0
                    self._raw_file_name = self._raw_file_prefix % (self._run_no, self._raw_no)
                    raw_pathname = os.path.join(self._raw_data_basedir, self._raw_file_name)
                    with open(raw_pathname, "wb") as raw_file:
                        LOGGER.info("Raw data file %s opened.", raw_pathname)
                        while self._continue_raw_thread:
                            try:
                                # TODO: get(False) でいいはず？
                                raw_data = self._raw_data_queue.get(True, 0.01)
                                raw_file.write(raw_data)
                                self._raw_current_size += len(raw_data)
                                del raw_data  # 123
                                raw_data = None  # 123
                                if self._raw_current_size >= self._raw_file_unit * 1024 * 1024:
                                    raw_file.close()
                                    break
                            except Empty:
                                pass
                            except Exception as exc:
                                LOGGER.error("Raw data thread error during dequeue and save: %s", str(exc))
                    self._raw_no += 1
            except Exception as exc:
                LOGGER.error("Raw data thread error during starting: %s", str(exc))


class DaqClient(threading.Thread):
    """
    Connect to the SiTCP device and pass the received data to the associated daq handler.
    """

    def __init__(self, daq_handler, ip_address, tcp_port=24):
        """
        :type daq_handler: DaqHandler
        :param daq_handler: DaqHandler derived class instance.

        :type ip_address: str
        :param ip_address: SiTCP device IP address.

        :type tcp_port: int
        :param tcp_port: SiTCP device TCP port number.
        """
        super(DaqClient, self).__init__()

        self._state = sitcpy.State(sitcpy.THREAD_NOT_STARTED)

        self._ip_address = ip_address
        self._daq_handler = daq_handler
        self._tcp_port = tcp_port
        self._paused = False
        self._data_bytes = 0
        self._data_rest = 0
        self._error = None

    @property
    def error(self):
        """
        :rtype: Exception
        :return: Error object(exception), if thread was stopped by error.
        """
        return self._error

    def start(self):
        super(DaqClient, self).start()
        self._state.transit(sitcpy.THREAD_STARTING)
        self._state.wait(sitcpy.THREAD_RUNNING)

    def stop(self):
        """
        Stop the daq thread
        """
        self._state.transit(sitcpy.THREAD_STOPPING)
        self.join(None)  # raw save thread writing data bytes
        LOGGER.debug("on_data called bytes: %u", self._data_bytes)
        LOGGER.debug("on_data rest bytes: %u", self._data_rest)

    def run(self):
        """
        Connect to the SiTCP device and start DAQ.
        """
        try:
            self._daq_handler.on_daq_start()  # call HANDLER
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2.0)
            self._data_bytes = 0
            self._data_rest = 0
            on_daq_data = self._daq_handler.on_daq_data
            on_running = self._daq_handler.on_daq_running
            on_error = self._daq_handler.on_daq_error
            try:
                sock.connect((self._ip_address, self._tcp_port))
            except (socket.gaierror, socket.timeout, OSError) as exc:
                LOGGER.error("Internal Device Connection Error(%s) %s %s ",
                             str(exc), self._ip_address, self._tcp_port)
                self._error = exc
                on_error(exc)
                return
            read_list = [sock]
            # TODO: 要修正。SessionThreadを参考？bytearrayではなく、bytesを使うようにする
            byte_array = bytearray()
            running = 0

            data_unit = self._daq_handler.get_data_unit()
            max_buff = data_unit * 1024 * 1024

            self._state.transit(sitcpy.THREAD_RUNNING)
            while self._state() == sitcpy.THREAD_RUNNING:
                try:
                    readable, _, _ = select.select(read_list, [], [], 0.01)
                    if sock in readable:
                        byte_array += sock.recv(max_buff)
                        length = len(byte_array)
                        if length >= data_unit:
                            rest = length % data_unit
                            if rest == 0:
                                on_daq_data(byte_array)
                                self._data_bytes += length
                                byte_array = bytearray()
                            else:
                                on_daq_data(byte_array[0:-rest])

                                self._data_bytes += (length - rest)
                                byte_array = byte_array[-rest:]
                    running += 1
                    if running % 2 == 0:
                        on_running()  # call HANDLER
                        running = 0

                except OSError as exc:
                    LOGGER.error("Internal Daq Process Error (%s)", str(exc))
                    LOGGER.debug(traceback.format_exc())
                    break

            self._state.transit(sitcpy.THREAD_STOPPING)
            self._data_rest = len(byte_array)
            self._daq_handler.on_daq_stop()  # call HANDLER
            sock.close()
        finally:
            self._state.transit(sitcpy.THREAD_STOPPED)
