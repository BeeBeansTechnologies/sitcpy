# -*- coding:utf-8 -*-
"""
UnitTest Case for RbcpServer with nose.

Copyright (c) 2018, Bee Beans Technologies Co.,Ltd.
"""

from __future__ import print_function

from logging import getLogger, StreamHandler, DEBUG
import sys
import time
from unittest import TestCase
import unittest

from sitcpy.cui import CommandClient
from sitcpy.daq_client import DaqHandler, DaqClient
from sitcpy.rbcp_server import RbcpServer, RbcpCommandHandler, DataGenerator,\
    PseudoDevice


LOGGER = getLogger(__name__)
HANDLER = StreamHandler()
HANDLER.setLevel(DEBUG)
LOGGER.setLevel(DEBUG)
LOGGER.addHandler(HANDLER)


class TestPseudoRbcp(TestCase):
    """
    unittests for pseudo RBCP server.
    """

    PROMPT = "pdev$ "
    COMMAND_PORT = 18888
    DATA_PORT = 24242

    def setUp(self):
        """
        setup pseudo device.
        """
        rbcp_server = RbcpServer()
        data_generator = DataGenerator()
        rbcp_command_handler = RbcpCommandHandler(self.PROMPT)
        rbcp_command_handler.bind(rbcp_server, data_generator)

        self._pdev = PseudoDevice(rbcp_command_handler, data_generator,
                                  rbcp_server, self.COMMAND_PORT,
                                  self.DATA_PORT)
        self._pdev.start()

        LOGGER.info("TestPseudoRbcp.setup Started pseudo device")

        # check pseudo device started with connecting command client.
        retry = 10
        while retry > 0:
            try:
                command_client = CommandClient(
                    self.PROMPT, "localhost", self.COMMAND_PORT)
                command_client.close()
                break
            except Exception:
                retry -= 1
                if retry == 0:
                    raise
                time.sleep(0.5)

        LOGGER.info("setup. command client tested.")

    def tearDown(self):
        """
        stop the pseudo device
        """
        if self._pdev is not None:
            self._pdev.stop()
            LOGGER.info("TestPseudoRbcp.tearDown:stopped pseudo device")
        else:
            LOGGER.info("TestPseudoRbcp.tearDown:pseudo device is None")

    def test_start_stop(self):
        """
        this test checks setup/tearDown is working correctly.
        """
        print("wait 5minutes self %s pseudo_device %s" %
              (self, self._pdev))

        time.sleep(5)

    def test_debug_command(self):
        """
        using the simple commands commands.
        """
        command_client = CommandClient(
            self.PROMPT, "localhost", self.COMMAND_PORT)
        reply = command_client.send_command("help")
        print(reply)
        reply = command_client.send_command("help read")
        print(reply)

        commands = ["stat", "state", "pwd", "ls",
                    "pwd pwd pwd", "ls ..", "", ";"]
        for command in commands:
            print(command_client.send_command(command))

        ng_commands = ["unknown", "pwd no args", "help unknown"]
        for command in ng_commands:
            reply = command_client.send_command(command)
            self.assertTrue(reply[0:3] == "NG:")

        reply = command_client.send_command(
            "write ffffff00 01 02 03 04 05 06 07 08")
        print(reply)
        reply = command_client.send_command("read ffffff00 8")
        print(reply)
        self.assertTrue(reply.strip() == "01 02 03 04 05 06 07 08")

        reply = command_client.send_command(
            "write ffffff00 01 02 03 04 05 06 07 08 09 10 11 12")
        print(reply)
        reply = command_client.send_command("read ffffff00 12")
        print(reply)
        lines = [val.strip() for val in reply.splitlines()]
        self.assertEqual(lines[0], "01 02 03 04 05 06 07 08")
        self.assertEqual(lines[1], "09 10 11 12")

    def test_daq_client(self):
        """
        Tests the DAQ thread with pseudo device.
        """
        data_handler = DaqHandler()
        daq_client = DaqClient(data_handler, "localhost", self.DATA_PORT)
        daq_client.start()
        time.sleep(5)
        daq_client.stop()
        print(data_handler.create_stat_list())


if __name__ == "__main__":
    print("python version: {0}.{1}.{2}".format(sys.version_info[0],
                                               sys.version_info[1],
                                               sys.version_info[2]))
    print("default encoding: {0}".format(sys.getdefaultencoding()))
    print()
    unittest.main()
