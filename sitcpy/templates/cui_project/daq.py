# -*- coding:utf-8 -*-
"""
SiTCP DAQ server

Copyright (c) 2018, Bee Beans Technologies Co.,Ltd.
"""

from __future__ import print_function

import datetime
import json
from logging import getLogger, StreamHandler, INFO
import os

from sitcpy.cui import CommandHandler, CuiServer, cui_main
from sitcpy.daq_client import DaqHandler, DaqClient


LOGGER = getLogger(__name__)
HANDLER = StreamHandler()
HANDLER.setLevel(INFO)
LOGGER.setLevel(INFO)
LOGGER.addHandler(HANDLER)


CONFIG_JSON = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "config.json")

RUN_NO = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "run_no.txt")


class DaqCommandHandler(CommandHandler):
    """
    Sample handler for a CUI server.
    Override the stat command.
    Respond with world for hello command.
    """
    DAQ_RUNNING = "Running"
    DAQ_STOP = "Stop"

    def __init__(self, prompt, daq_handler=None, seps=" "):
        super(DaqCommandHandler, self).__init__(prompt, seps)

        self._config = None
        """:type : dict[str, str]"""
        self._run_no = -1
        """:type : int"""
        self._daq_handler = daq_handler or DaqHandler()
        """:type : DaqHandler"""
        self._daq_client = None
        """:type : DaqClient"""
        self._daq_status = DaqCommandHandler.DAQ_STOP
        """:type : str"""
        self._raw_save_dir_format = "raw%06u_%s"
        """:type : str"""
        self._raw_save = False
        """:type : bool"""

        try:
            self._reload_config()
        except (IOError, ValueError) as exc:
            LOGGER.error("daq.py initialization error (%s)", exc)
            raise

    def _save_run_no(self, run_no=None):
        """
        :type run_no: int or None
        """
        assert isinstance(run_no, (int, type(None)))
        run_no = run_no or self._run_no
        with open(RUN_NO, "w") as run_no_file:
            run_no_file.write(str(run_no))

    def _reload_config(self, config_path=None):
        """
        Reload config.json

        :type config_path: str or None
        :param config_path: Config file path.
        """
        config_path = config_path or CONFIG_JSON
        with open(config_path) as config_file:
            self._config = json.load(config_file)

        if os.path.isfile(RUN_NO):
            try:
                with open(RUN_NO) as run_no_file:
                    self._run_no = int(run_no_file.read(128))
            except (ValueError, OSError) as exc:
                LOGGER.error("Could not initialize run no from %s. %s", RUN_NO, exc)
        if self._run_no < 0:
            self._run_no = 1
            self._save_run_no()

        self._logging_dir = self._config["system"]["logging_dir"]
        self._data_unit = self._config["system"]["data_unit"]  # TODO: 未使用
        LOGGER.info("run no initialized as %s", self._run_no)
        LOGGER.info("logging directory is %s", self._logging_dir)

        self._connect_to = self._config["daq"]["connect"]
        self._ip = self._config["targets"][self._connect_to]["ip"]
        self._tcp = self._config["targets"][self._connect_to]["tcp"]
        self._udp = self._config["targets"][self._connect_to]["udp"]

    def on_cmd_reload(self, session, cmd_list):
        """
        :usage: reload [config_file_path]: Reload config.json
        """
        config_path = None
        if len(cmd_list) == 2:
            config_path = cmd_list[1]
        if len(cmd_list) <= 2:
            try:
                self._reload_config(config_path)
                self.reply_text(session, "OK:Config reloaded")
            except (KeyError, IOError) as exc:
                message = "NG:Could not reload config %s" % exc
                LOGGER.error(message)
                self.reply_text(session, message)
        else:
            LOGGER.error("Too many arguments for reload %s", cmd_list)
        return True

    def create_stat_list(self):
        """
        :rtype: list[str]
        :return: Stat list. The elements of the list are strings like "<key>=<value>".
        """
        result = super(DaqCommandHandler, self).create_stat_list()

        if self._daq_client is None:
            result.append("daq=stop")
        elif self._daq_client.error:
            result.append("daq=error")
            result.append("error='%s'" % str(self._daq_client.error))
        else:
            result.append("daq=running")
        result.append("run no=%d" % self._run_no)

        result.extend(self._daq_handler.create_stat_list())

        return result

    def on_cmd_rawsave(self, session, cmd_list):
        """
        :usage: rawsave [on|off]: Set the raw event data save function on/off
        """
        if len(cmd_list) == 1:
            self.reply_text(session, "on" if self._raw_save else "off")
        elif len(cmd_list) == 2:
            if cmd_list[1].lower() == "on":
                # run_dir = self._raw_save_dir_format%(self._run_no, datetime.datetime.now(
                # ).strftime("%Y%m%d"))# %H%M%S"))
                # raw_save_dir = os.path.join(self._logging_dir, run_dir)
                try:
                    if not os.path.exists(self._logging_dir):
                        os.makedirs(self._logging_dir)
                    os.chmod(self._logging_dir, 0o777)
                    self._daq_handler.set_raw_save(True, self._run_no, self._logging_dir)
                    self._raw_save = True
                    self.reply_text(session, "OK:on")
                except OSError as exc:
                    message = "NG:Could not create logging dir %s. %s" % (self._logging_dir, str(exc))
                    LOGGER.error(message)
                    self.reply_text(session, message)
                    return True
            else:
                self._daq_handler.set_raw_save(False, self._run_no, None)
                self._raw_save = False
                self.reply_text(session, "OK:off")
        return True

    def on_cmd_run(self, session, cmd_list):
        """
        Run the daq.

        :usage: run: Run daq.
        """
        if len(cmd_list) == 1:
            if self._daq_client is None:
                try:
                    if self._raw_save:
                        run_dir = self._raw_save_dir_format % (self._run_no, datetime.datetime.now().strftime("%Y%m%d"))
                        raw_save_dir = os.path.join(self._logging_dir, run_dir)
                        try:
                            os.makedirs(raw_save_dir, False)
                            os.chmod(raw_save_dir, 0o777)
                            self._daq_handler.set_raw_save(True, self._run_no, raw_save_dir)
                        except OSError as exc:
                            message = "NG:Could not create raw data save directory %s (%s)" % (raw_save_dir, exc)
                            LOGGER.error(message)
                            self.reply_text(session, message)
                            return True

                    self._daq_client = DaqClient(self._daq_handler, self._ip, self._tcp)
                    self._daq_client.start()
                    self._daq_status = self.DAQ_RUNNING
                except Exception as exc:
                    LOGGER.error("NG:Could not start daq. %s", exc)
                    self._daq_client.stop()
                    self._daq_client = None
                    self._daq_status = self.DAQ_STOP
            else:
                message = "NG:Run command status mismatch"
                self.reply_text(session, message)
                LOGGER.error(message)
        else:
            self.reply_text(session, "NG:Too many arguments")
        return True

    def on_cmd_stop(self, session, cmd_list):
        """
        Stop the daq and increment run no

        :usage: stop: Stop current run.
        """
        if len(cmd_list) == 1:
            if self._daq_client is not None:
                if self._raw_save:
                    self.reply_text(session, "waiting for raw data writing...")
                self._daq_client.stop()
                self._daq_client = None
                self._daq_status = self.DAQ_STOP
                self._run_no += 1
                self._save_run_no()
            else:
                LOGGER.error("stop command status mismatch")
        else:
            self.reply_text(session, "NG:Too many arguments")
        return True

    def on_cmd_runno(self, session, cmd_list):
        """
        Set the run no.

        :usage: runno [runno]: Set/show the run number.
        """
        if len(cmd_list) == 1:
            self.reply_text(session, "%s" % self._run_no)
        elif len(cmd_list) == 2:
            try:
                run_no = int(cmd_list[1])
                self._run_no = run_no
                self._save_run_no()
                self.reply_text(session, "OK:%s" % run_no)
            except ValueError as exc:
                LOGGER.error("runno command error %s", str(exc))
                self.reply_text(session, "NG:Error occurred (%s)" % str(exc))
        return True

    def on_cmd_exit(self, session, cmd_list):
        """
        Exit daq.
        """
        if self._daq_client is not None:
            self._daq_client.stop()
            self._daq_client = None
        return super(DaqCommandHandler, self).on_cmd_exit(session, cmd_list)


def main():
    """
    Start the CUI server MySiTcp
    """
    cui_main(CuiServer, DaqCommandHandler("daq$ "))


if __name__ == "__main__":
    main()
