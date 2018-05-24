# -*- coding:utf-8 -*-
"""
Copyright (c) 2018, Bee Beans Technologies Co.,Ltd.
"""


from __future__ import print_function

import os
import shutil
import sys
import time
from unittest import TestCase
import unittest

from sitcpy.cui import CuiServer, SessionThread, CommandClient
from sitcpy.rbcp_server import default_pseudo_arg_parser, RbcpServer,\
    PseudoDevice
from sitcpy.templates.cui_project import daq
from sitcpy.templates.cui_project.daq import DaqCommandHandler
from sitcpy.templates.cui_project.pseudo import PseudoDataGenerator,\
    PseudoRbcpCommandHandler


PROMPT = "daq$ "


class DaqTest(TestCase):

    def setUp(self):
        # pseudo
        args = default_pseudo_arg_parser().parse_args([])

        command_port = args.port
        data_port = args.dataport

        rbcp_server = RbcpServer()
        data_generator = PseudoDataGenerator()
        rbcp_command_handler = PseudoRbcpCommandHandler("pdev$ ")
        rbcp_command_handler.bind(rbcp_server, data_generator)
        self.pdev = PseudoDevice(rbcp_command_handler, data_generator,
                                 rbcp_server, command_port, data_port)
        self.pdev.start()

        # daq
        self.run_no_txt_path = os.path.join(
            os.path.dirname(daq.__file__), "run_no.txt")
        if os.path.isfile(self.run_no_txt_path):
            os.remove(self.run_no_txt_path)

        self.log_dir = "log"
        shutil.rmtree(self.log_dir, ignore_errors=True)

        self.handler = DaqCommandHandler(PROMPT)
        self.server = CuiServer(SessionThread, self.handler, 5050)
        self.server.start()
        self.cli = CommandClient(PROMPT, "localhost", 5050)

    def tearDown(self):
        self.cli.close()
        self.server.stop()
        self.server.join()

        self.pdev.stop()

        if os.path.isfile(self.run_no_txt_path):
            os.remove(self.run_no_txt_path)

        shutil.rmtree(self.log_dir, ignore_errors=True)

    def test_commands(self):

        res = self.cli.send_command("reload").strip()
        self.assertTrue(res.startswith("OK:"))

        res = self.cli.send_command("reload _file_not_found_error_").strip()
        self.assertTrue(res.startswith("NG:"))

        # stat
        res = self.cli.send_command("stat").strip()
        self.assertTrue(len(res.splitlines()) > 5)
        for val in res.splitlines():
            if val:
                self.assertEqual(len(val.split("=", 1)), 2)

        # rawsave
        res = self.cli.send_command("rawsave").strip()
        self.assertEqual(res, "off")

        res = self.cli.send_command("rawsave off").strip()
        self.assertEqual(res, "OK:off")

        res = self.cli.send_command("rawsave").strip()
        self.assertEqual(res, "off")

        res = self.cli.send_command("rawsave on").strip()
        self.assertEqual(res, "OK:on")

        res = self.cli.send_command("rawsave").strip()
        self.assertEqual(res, "on")

        # runno
        res = self.cli.send_command("runno 1").strip()
        self.assertEqual(res, "OK:1")

        res = self.cli.send_command("runno").strip()
        self.assertEqual(res, "1")

        res = self.cli.send_command("runno 2").strip()
        self.assertEqual(res, "OK:2")

        # exit
        res = self.cli.send_command("exit")
        self.assertTrue(res is None)

    def test_daq(self):

        self.assertFalse(os.path.isdir(self.log_dir))

        self.cli.send_command("rawsave on")

        res = self.cli.send_command("stat").strip()
        print("===== stat before daq")
        print(res)
        print("/=====")

        res = self.cli.send_command("run 100").strip()
        self.assertTrue(res.startswith("NG:"))

        res = self.cli.send_command("run").strip()
        print("=====")
        print(res)
        print("/=====")

        time.sleep(1)
        res = self.cli.send_command("stat").strip()
        print("===== stat during daq")
        print(res)
        print("/=====")

        res = self.cli.send_command("run").strip()
        self.assertTrue(res.startswith("NG:"))

        time.sleep(1)

        res = self.cli.send_command("stop 100").strip()
        self.assertTrue(res.startswith("NG:"))

        res = self.cli.send_command("stop").strip()
        print("=====")
        print(res)
        print("/=====")

        res = self.cli.send_command("stat").strip()
        print("===== stat after daq")
        print(res)
        print("/=====")

        self.assertTrue(os.path.isdir(self.log_dir))


if __name__ == "__main__":
    print("python version: {0}.{1}.{2}".format(sys.version_info[0],
                                               sys.version_info[1],
                                               sys.version_info[2]))
    print("default encoding: {0}".format(sys.getdefaultencoding()))
    print()
    unittest.main()
