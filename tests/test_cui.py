# -*- coding:utf-8 -*-
"""
Copyright (c) 2018, Bee Beans Technologies Co.,Ltd.
"""

from __future__ import print_function

import json
import os
import sys
import time
from unittest import TestCase
import unittest

from sitcpy import is_unicode, to_bytes
import sitcpy
from sitcpy.cui import CommandHandler, CuiServer, SessionThread, TextHandler,\
    CommandClient


PROMPT = "$ "
PORT = 18888


class DataHandlerTest(TestCase):

    class Handler(CommandHandler):

        def __init__(self, prompt, seps=" "):
            super(DataHandlerTest.Handler, self).__init__(prompt, seps)
            self._count = 0

        def create_stat_list(self):
            """
            :rtype: list[str]
            :return: Stat list.
            """
            self._count += 1
            return ["stat count=%s" % self._count]

    def setUp(self):
        self.server = CuiServer(SessionThread,
                                DataHandlerTest.Handler(PROMPT), PORT)

    def tearDown(self):
        self.server.stop()
        try:
            self.server.join()
        except RuntimeError:
            pass

    def test_text_handler(self):

        handler = TextHandler()

        self.assertEqual(handler.find_delimiter_position(b"abc\r\ndef"), 5)
        self.assertEqual(handler.linesep, "\r\n")

        self.assertEqual(handler.find_delimiter_position(b"abc\ndef"), 4)
        self.assertEqual(handler.linesep, "\n")

        self.assertEqual(handler.find_delimiter_position(b"abc\rdef"), 4)
        self.assertEqual(handler.linesep, "\r")

        self.assertEqual(handler.find_delimiter_position(b""), -1)
        self.assertEqual(handler.find_delimiter_position(b" abc def "), -1)

        handler.reply_text(SessionThread(self.server,
                                         handler,
                                         None,
                                         "localhost"),
                           "abc")

        self.server.start()
        cli = CommandClient(PROMPT, "localhost", PORT)
        cli.send_command("stat")
        cli.close()

    def test_command_handler(self):
        handler = CommandHandler("$ ")
        session = SessionThread(self.server, handler, None, "localhost")

        print("\n=== help command ===")
        self.assertTrue(handler.on_data(session, b"help"))

        print("\n=== xxx command ===")
        self.assertTrue(handler.on_data(session, b"xxx"))

        class CommandHandlerEx(CommandHandler):
            def on_cmd_xxx(self, _session, _cmd_list):
                raise ValueError("Test: Some error occured.")

        print("\n=== CommandHandlerEx ===")
        handler = CommandHandlerEx("$ ")
        print("\n=== help command ===")
        self.assertTrue(handler.on_data(session, b"help"))
        print("\n=== xxx command ===")
        self.assertFalse(handler.on_data(session, b"xxx"))

    def test_on_command(self):
        self.server.start()

        cli = CommandClient(PROMPT, "localhost", PORT)

        res = cli.send_command("unknown_command")
        self.assertTrue(res.startswith("NG:Unknown command"))

        cli.close()

    def test_on_cmd_help(self):
        self.server.start()

        cli = CommandClient(PROMPT, "localhost", PORT)

        # all command help
        res = cli.send_command("help")
        self.assertTrue(len(res.splitlines()) > 5)

        # close command help
        res = cli.send_command("help close")
        self.assertTrue(res.startswith("close:"))

        # close and exit command help
        res = cli.send_command("help close exit")
        cmd_list = ["close:", "exit:"]
        self.assertEqual(len(res.splitlines()), len(cmd_list))
        for line in res.splitlines():
            for cmd in cmd_list:
                if line.startswith(cmd):
                    cmd_list.remove(cmd)
                    break
                self.fail("Unknown command help.")
        self.assertFalse(cmd_list)

        # unknown command help
        res = cli.send_command("help unknown_command")
        self.assertTrue(res.startswith("NG:Unknown command"))

        cli.close()

    def test_on_cmd_state(self):
        self.server.start()

        cli = CommandClient(PROMPT, "localhost", PORT)

        res = cli.send_command("state")
        print(self, res)
        self.assertTrue(res.startswith("Sever address:"))

        cli.close()

        handler = CommandHandler(PROMPT)
        # noinspection PyTypeChecker
        session = SessionThread(None, None, None, None)
        self.assertTrue(handler.on_cmd_state(session, ["state"]))

    def test_on_cmd_close(self):
        self.server.start()

        cli = CommandClient(PROMPT, "localhost", PORT)

        self.assertEqual(len(self.server._sessions), 1)
        cli.send_command("close")
        time.sleep(1)
        self.assertEqual(len(self.server._sessions), 0)

        cli.close()

    def test_on_cmd_exit(self):
        self.server.start()

        cli = CommandClient(PROMPT, "localhost", PORT)

        self.assertEqual(self.server.state, sitcpy.THREAD_RUNNING)
        self.assertEqual(len(self.server._sessions), 1)
        cli.send_command("exit")
        time.sleep(1)
        self.assertEqual(self.server.state, sitcpy.THREAD_STOPPED)
        self.assertEqual(len(self.server._sessions), 0)

        cli.close()

    def test_on_cmd_stat(self):
        self.server.start()

        cli = CommandClient(PROMPT, "localhost", PORT)

        res = cli.send_command("stat")
        print(self, res)
        self.assertTrue(res)
        for line in res.splitlines():
            key_name = line.split("=", 1)
            self.assertTrue(key_name[0].strip())
            self.assertTrue(len(key_name) == 2)

        res = cli.send_command("stat j")
        print(self, res)
        jsn = json.loads(res)
        self.assertTrue(isinstance(jsn, dict))
        for key, val in jsn.items():
            self.assertTrue(is_unicode(key))
            self.assertTrue(key)
            self.assertTrue(is_unicode(val))

        res = cli.send_command("stat unknown-param")
        print(self, res)
        self.assertTrue(res.startswith("NG:Unknown argument"))

        cli.close()

    def test_on_cmd_pwd(self):
        self.server.start()

        cli = CommandClient(PROMPT, "localhost", PORT)
        print("=====")
        res = cli.send_command("pwd")
        print(res)

        self.assertFalse(res.startswith("NG:"))
        print("=====")
        res = cli.send_command("pwd ../")
        print(res)
        self.assertTrue(res.startswith("NG:"))
        print("=====")

        cli.close()

    def test_on_cmd_ls(self):
        self.server.start()

        cli = CommandClient(PROMPT, "localhost", PORT)

        res = cli.send_command("ls")
        print(self, res)
        files = res.splitlines()
        self.assertTrue(files.count("sitcpy"))
        self.assertTrue(files.count("tests"))
        self.assertTrue(files.count("README.md"))

        res = cli.send_command("ls sitcpy")
        print(self, res)
        files = res.splitlines()
        self.assertTrue(files.count("cui.py"))
        self.assertTrue(files.count("rbcp.py"))

        res = cli.send_command("ls arg1 arg2")
        print(self, res)
        self.assertTrue(res.startswith("NG:Too many arguments"))

        res = cli.send_command("ls file_is_not_found")
        print(self, res)
        self.assertTrue(res.startswith("NG:Error occurred"))

        cli.close()

#     def test_xxx(self):
#         self.server.start()
#
#         addr = self.server.server_address
#         print(type(addr))
#         self.assertTrue(isinstance(addr, tuple))
#         self.assertEqual(len(addr), 2)
#         self.assertEqual(addr[0], "0.0.0.0")
#         self.assertEqual(addr[1], PORT)
#
#         print("----- server info list -----")
#         print(self.server.get_server_info_list())
#         print("----- /server info list -----")
#
#         cli = CommandClient(PROMPT, "localhost", PORT)
#
#         cli._sock.sendall(to_bytes("st"))
#         time.sleep(1)
#         res = cli.send_command("ate")
#         print("----- response -----")
#         print(res)
#         print("----- /response -----")
#
#         res = cli.send_command("ls")
#         print("----- response -----")
#         print(res)
#         print("----- /response -----")
#
#         res = cli.send_command("state;;stat")
#         print("----- response -----")
#         print(res)
#         print("----- /response -----")
#
#         cli.close()


class SessionThreadTest(TestCase):

    def setUp(self):
        self.server = CuiServer(SessionThread, CommandHandler(PROMPT), PORT)

    def tearDown(self):
        self.server.stop()
        try:
            self.server.join()
        except RuntimeError:
            pass

    def test_separated_cmd(self):
        self.server.start()

        cli = CommandClient(PROMPT, "localhost", PORT)

        cli._sock.sendall(to_bytes("pw"))
        time.sleep(1)
        cli._sock.sendall(to_bytes("d" + os.linesep))
        res = cli._receive()
        print(res)
        self.assertTrue(res)


if __name__ == "__main__":
    print("python version: {0}.{1}.{2}".format(sys.version_info[0],
                                               sys.version_info[1],
                                               sys.version_info[2]))
    print("default encoding: {0}".format(sys.getdefaultencoding()))
    print()
    unittest.main()


class CommandClientTest(TestCase):
    """
    Test RBCP Module with RbcpServer.
    NOTE: This test starts RbcpServer.
    """

    def setUp(self):
        self.server = CuiServer(SessionThread, CommandHandler(PROMPT), PORT)
        self.server.start()

    def tearDown(self):
        self.server.stop()
        try:
            self.server.join()
        except RuntimeError:
            pass

    def test_send_command(self):  # pylint: disable=no-self-use
        cli = CommandClient(PROMPT, "localhost", PORT)
        print("##### ls")
        print(cli.send_command("ls"))
        print("##### stat")
        print(cli.send_command("stat"))
        print("##### help")
        print(cli.send_command("help"))
        print("##### close")
        cli.close()
        print("#####")


if __name__ == "__main__":
    print("python version: {0}.{1}.{2}".format(sys.version_info[0],
                                               sys.version_info[1],
                                               sys.version_info[2]))
    print("default encoding: {0}".format(sys.getdefaultencoding()))
    print()
    unittest.main()
