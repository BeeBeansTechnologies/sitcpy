# -*- coding:utf-8 -*-
"""
Copyright (c) 2018, Bee Beans Technologies Co.,Ltd.
"""


from __future__ import print_function

import os
import sys
from unittest import TestCase
import unittest

import sitcpy
from sitcpy.cui import CuiServer, SessionThread, CommandClient
from sitcpy.rbcp_server import default_pseudo_arg_parser, RbcpServer, \
    PseudoDevice, DataGenerator, RbcpCommandHandler, VirtualRegisterOutOfRange
from sitcpy.templates.cui_project.daq import DaqCommandHandler


PROMPT = "daq$ "


TEST_DATA_PATH0 = os.path.join(
    os.path.dirname(sitcpy.__file__), "../tests/test_data/data1/0.bin")
TEST_DATA_PATH256 = os.path.join(
    os.path.dirname(sitcpy.__file__), "../tests/test_data/data1/100.bin")


class RbcpServerTest(TestCase):

    def setUp(self):
        # pseudo
        args = default_pseudo_arg_parser().parse_args([])

        command_port = args.port
        data_port = args.dataport

        self.rbcp_server = RbcpServer()
        data_generator = DataGenerator()
        rbcp_command_handler = RbcpCommandHandler("pdev$ ")
        rbcp_command_handler.bind(self.rbcp_server, data_generator)
        self.pdev = PseudoDevice(rbcp_command_handler, data_generator,
                                 self.rbcp_server, command_port, data_port)
        self.pdev.start()

        # daq
        # self.run_no_txt_path = os.path.join(
        #     os.path.dirname(daq.__file__), "run_no.txt")
        # if os.path.isfile(self.run_no_txt_path):
        #     os.remove(self.run_no_txt_path)

        # self.log_dir = "/tmp/sitcpdaq"
        # shutil.rmtree(self.log_dir, ignore_errors=True)

        self.handler = DaqCommandHandler(PROMPT)
        self.server = CuiServer(SessionThread, self.handler, 5050)
        self.server.start()
        self.cli = CommandClient(PROMPT, "localhost", 5050)

    def tearDown(self):
        self.cli.close()
        self.server.stop()
        self.server.join()
        self.pdev.stop()

        # if os.path.isfile(self.run_no_txt_path):
        #     os.remove(self.run_no_txt_path)

        # self.log_dir = "/tmp/sitcpdaq"
        # shutil.rmtree(self.log_dir, ignore_errors=True)

    def test_register(self):
        res = self.rbcp_server.read_registers(0xFFFF0000, 8)
        self.assertEqual(res, bytearray(b"\0\0\0\0\0\0\0\0"))

        self.rbcp_server.write_registers(0xFFFF0000, b"\1\1\1\1\1\1\1\1")
        res = self.rbcp_server.read_registers(0xFFFF0000, 8)
        self.assertEqual(res, bytearray(b"\1\1\1\1\1\1\1\1"))

        self.rbcp_server.write_registers(0xFFFF0004, b"\2\2\2\2")
        res = self.rbcp_server.read_registers(0xFFFF0000, 8)
        self.assertEqual(res, bytearray(b"\1\1\1\1\2\2\2\2"))

        try:
            self.rbcp_server.read_registers(0x00000000, 8)
        except VirtualRegisterOutOfRange:
            pass
        else:
            self.fail()

        try:
            self.rbcp_server.read_registers(0xFFFF0000, 65536)
        except VirtualRegisterOutOfRange:
            self.fail()

        try:
            self.rbcp_server.read_registers(0xFFFF0000, 65537)
        except VirtualRegisterOutOfRange:
            pass
        else:
            self.fail()

        try:
            self.rbcp_server.write_registers(0xFFFF0000, bytearray(65536))
        except VirtualRegisterOutOfRange:
            self.fail()

        try:
            self.rbcp_server.write_registers(0xFFFF0000, bytearray(65537))
        except VirtualRegisterOutOfRange:
            pass
        else:
            self.fail()

    def test_initialize_registers(self):

        self.assertEqual(len(self.rbcp_server.registers), 1)
        self.rbcp_server.merge_registers()  # do noting.

        res = self.rbcp_server.initialize_registers(TEST_DATA_PATH0)
        self.assertEqual(res.strip(), "00000000:256 bytes")
        self.assertEqual(len(self.rbcp_server.registers), 2)

        res = self.rbcp_server.initialize_registers(TEST_DATA_PATH256)
        self.assertEqual(res.strip(), "00000100:256 bytes")
        self.assertEqual(len(self.rbcp_server.registers), 3)

        self.rbcp_server.merge_registers()
        self.assertEqual(len(self.rbcp_server.registers), 2)

        res = self.rbcp_server.get_register_info()
        self.assertEqual(len(res), 2)

    def test_dump_registers(self):
        res = self.rbcp_server.dump_registers()

        print(res)
        pass


if __name__ == "__main__":
    print("python version: {0}.{1}.{2}".format(sys.version_info[0],
                                               sys.version_info[1],
                                               sys.version_info[2]))
    print("default encoding: {0}".format(sys.getdefaultencoding()))
    print()
    unittest.main()
