# -*- coding:utf-8 -*-
"""
Copyright (c) 2018, Bee Beans Technologies Co.,Ltd.
"""

from __future__ import print_function

import shutil
import sys
from unittest import TestCase
import unittest
from sitcpy import command


PROJECT_NAME = "__mycuiproject__"


class CommandTest(TestCase):

    def setUp(self):
        shutil.rmtree(PROJECT_NAME, ignore_errors=True)

    def tearDown(self):
        shutil.rmtree(PROJECT_NAME, ignore_errors=True)

    def test_command(self):

        try:
            command.main(["-h"])
            self.fail()
        except SystemExit as exc:
            self.assertEqual(exc.code, 0)

        try:
            command.main(["--help"])
            self.fail()
        except SystemExit as exc:
            self.assertEqual(exc.code, 0)

        try:
            command.main(["xxx"])
            self.fail()
        except SystemExit as exc:
            print("exc:", exc)
            self.assertEqual(exc.code, 2)

        try:
            command.main(["createcuiproject"])
            self.fail()
        except SystemExit as exc:
            self.assertEqual(exc.code, 2)

        try:
            command.main(["createcuiproject", "-h"])
            self.fail()
        except SystemExit as exc:
            self.assertEqual(exc.code, 0)

        try:
            command.main(["createcuiproject", "--help"])
            self.fail()
        except SystemExit as exc:
            self.assertEqual(exc.code, 0)

        try:
            command.main(["createcuiproject", ""])
            self.fail()
        except SystemExit as exc:
            self.assertEqual(exc.code, 1)

        try:
            command.main(["createcuiproject", PROJECT_NAME])
        except SystemExit:
            self.fail()

        try:
            command.main(["createcuiproject", PROJECT_NAME])
            self.fail()
        except SystemExit as exc:
            self.assertEqual(exc.code, 1)


if __name__ == "__main__":
    print("python version: {0}.{1}.{2}".format(sys.version_info[0],
                                               sys.version_info[1],
                                               sys.version_info[2]))
    print("default encoding: {0}".format(sys.getdefaultencoding()))
    print()
    unittest.main()
