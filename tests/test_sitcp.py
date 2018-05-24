# -*- coding:utf-8 -*-
"""
Unit test for sitcp module.

Copyright (c) 2018, Bee Beans Technologies Co.,Ltd.
"""

from __future__ import print_function

import datetime
import sys
from threading import Thread
import time
from unittest import TestCase
import unittest

from sitcpy import to_str, to_bytes, to_bytearray, total_seconds, is_unicode,\
    PY2, State


class StateTest(TestCase):

    def setUp(self):
        pass

    def tearDown(self):
        pass

    def test_init(self):
        state = State()
        self.assertEqual(state.state, 0)
        self.assertEqual(state(), 0)

        state = State(10)
        self.assertEqual(state.state, 10)
        self.assertEqual(state(), 10)

    def test_transit(self):
        state = State()
        self.assertEqual(state.state, 0)
        self.assertEqual(state(), 0)

        self.assertTrue(state.transit(1))
        self.assertEqual(state.state, 1)
        self.assertEqual(state(), 1)

        self.assertTrue(state.transit(5))
        self.assertEqual(state.state, 5)
        self.assertEqual(state(), 5)

        self.assertFalse(state.transit(5))
        self.assertEqual(state.state, 5)
        self.assertEqual(state(), 5)

        self.assertFalse(state.transit(2))
        self.assertEqual(state.state, 5)
        self.assertEqual(state(), 5)

    def test_wait(self):

        state = State()

        def run():
            time.sleep(1)
            state.transit(10)
        Thread(target=run).start()

        self.assertTrue(state.wait(5))
        self.assertTrue(state.wait(10))
        self.assertFalse(state.wait(11, 1))


class MethodTest(TestCase):

    def setUp(self):
        pass

    def tearDown(self):
        pass

    STR1 = "abcあdef"
    UNI1 = u"abcあdef"
    BYTES1 = b"abc\xe3\x81\x82def"

    STR2 = "ghiいjkl"
    UNI2 = u"ghiいjkl"
    BYTES2 = b"ghi\xe3\x81\x84jkl"

    def check_equal(self, val1, val2):
        self.assertEqual(type(val1), type(val2))
        self.assertEqual(val1, val2)

    def check_not_equal(self, val1, val2):
        self.assertTrue(type(val1) != type(val2) or val1 != val2)

    def test_is_unicode(self):

        if PY2:
            self.assertFalse(is_unicode("abc"))
            self.assertTrue(is_unicode(u"abc"))
        else:
            self.assertTrue(is_unicode("abc"))
            self.assertTrue(is_unicode(u"abc"))

    def test_to_str(self):

        for val in (self.STR1,
                    self.UNI1,
                    bytes(self.BYTES1),
                    bytearray(self.BYTES1)):
            self.check_equal(self.STR1, to_str(val))
            self.check_not_equal(self.STR2, to_str(val))

        self.assertRaises(ValueError, to_str, 100)
        self.assertRaises(ValueError, to_str, True)
        self.assertRaises(ValueError, to_str, None)

    def test_to_bytes(self):

        for val in (self.STR1,
                    self.UNI1,
                    bytes(self.BYTES1),
                    bytearray(self.BYTES1)):
            self.check_equal(bytes(self.BYTES1), to_bytes(val))
            self.check_not_equal(bytes(self.BYTES2), to_bytes(val))

        self.assertRaises(ValueError, to_bytes, 100)
        self.assertRaises(ValueError, to_bytes, True)
        self.assertRaises(ValueError, to_bytes, None)

    def test_to_bytearray(self):

        for val in (self.STR1,
                    self.UNI1,
                    bytes(self.BYTES1),
                    bytearray(self.BYTES1)):
            self.check_equal(bytearray(self.BYTES1), to_bytearray(val))
            self.check_not_equal(bytearray(self.BYTES2), to_bytearray(val))

        self.assertRaises(ValueError, to_bytearray, 100)
        self.assertRaises(ValueError, to_bytearray, True)
        self.assertRaises(ValueError, to_bytearray, None)

    def test_total_seconds(self):

        dt1 = datetime.datetime(2018, 1, 1, 0, 0)
        dt2 = datetime.datetime(2018, 1, 2, 0, 0)
        self.assertEqual(round(total_seconds(dt2 - dt1)), 60 * 60 * 24)

        dt2 = datetime.datetime(2018, 1, 1, 0, 0, 0, 123456)
        self.assertEqual(
            round(total_seconds(dt2 - dt1) * 10**6),
            round(0.123456 * 10**6)
        )


if __name__ == "__main__":
    print("python version: {0}.{1}.{2}".format(sys.version_info[0],
                                               sys.version_info[1],
                                               sys.version_info[2]))
    print("default encoding: {0}".format(sys.getdefaultencoding()))
    print()
    unittest.main()
