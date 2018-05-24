# -*- coding:utf-8 -*-
"""
Unit test for the RBCP protocol class.

Copyright (c) 2018, Bee Beans Technologies Co.,Ltd.
"""

from __future__ import print_function

import os
import sys
import time
from traceback import print_exc
from unittest import TestCase
import unittest

import sitcpy
from sitcpy.rbcp import RbcpBusError, RbcpTimeout, Rbcp, RbcpError
from sitcpy.rbcp_server import RbcpServer


TEST_DATA_PATH0 = os.path.join(
    os.path.dirname(sitcpy.__file__), "../tests/test_data/data1/0.bin")
TEST_DATA_PATH256 = os.path.join(
    os.path.dirname(sitcpy.__file__), "../tests/test_data/data1/100.bin")


class RbcpTest(TestCase):
    """
    Test RBCP Module with RbcpServer.
    NOTE: This test starts RbcpServer.
    """

    def setUp(self):
        """
        run RbcpServer with test memory initialized by test_data/0.bin
        """
        self._rbcp_server = RbcpServer()
        try:
            self._rbcp_server.initialize_registers(TEST_DATA_PATH0)
        except ValueError:
            print_exc()
            print("register initialization failure")
        print("Register info: %s" % self._rbcp_server.get_register_info())
        self._rbcp_server.start()
        time.sleep(0.1)

    def tearDown(self):
        """
        stop the RBCP Server
        """
        self._rbcp_server.stop()

    def test_exc(self):  # pylint: disable=no-self-use
        """
        test constructor of SiTCP exceptions.
        """
        RbcpBusError()
        RbcpBusError("Message.")

        RbcpTimeout()
        RbcpTimeout("Message.")

    def test_memory_read(self):
        """
        test RBCP memory read.
        """
        rbcp = Rbcp("127.0.0.1")

        data = rbcp.read(0x00000000, 255)
        self.assertEqual(len(data), 255)

        data = rbcp.read(0xffffff00, 255)
        self.assertEqual(len(data), 255)

        data = rbcp.read(0xffffffff, 0)
        self.assertEqual(len(data), 0)

        self.assertRaises(ValueError, rbcp.read, 1.1, 255)
        self.assertRaises(ValueError, rbcp.read, -1, 255)
        self.assertRaises(ValueError, rbcp.read, 0xffffff01, 255)

        rbcp.read(0x00000000, 0)
        rbcp.read(0x00000000, 255)
        self.assertRaises(ValueError, rbcp.read, 0x00000000, 1.1)
        self.assertRaises(ValueError, rbcp.read, 0x00000000, -1)
        self.assertRaises(ValueError, rbcp.read, 0x00000000, 256)

        for _ in range(256):  # For coverage of clear code of _packet_id.
            rbcp.read(0x00000000, 255)

    def test_memory_write(self):
        """
        test RBCP memory write.
        """
        rbcp = Rbcp("127.0.0.1")

        rbcp.write(0xffffff00, b"")
        rbcp.write(0xffffff00, b"0123")
        rbcp.write(0xffffff00, bytearray(255))

        self.assertRaises(ValueError, rbcp.write, 0xffffff00, bytearray(256))
        self.assertRaises(ValueError, rbcp.write, -1, bytearray(256))
        self.assertRaises(ValueError, rbcp.write, 0xffffff01, bytearray(255))
        self.assertRaises(ValueError, rbcp.write, 1.1, bytearray(255))

        for _ in range(256):  # For coverage of clear code of _packet_id.
            rbcp.write(0xffffff00, bytearray(255))

    def test_memory_read_write(self):
        """
        test RBCP memory read/write.
        """
        rbcp = Rbcp("127.0.0.1")

        # Generate test data.for write.
        send_data = bytearray(0xff)
        for num in range(0xff):
            send_data[num] = num + 1

        # Read initial data of register.
        print("initial")
        read_data = rbcp.read(0xffffff00, 255)
        print(read_data)

        # Write.
        rbcp.write(0xffffff00, send_data)

        # Read written data and compare with initial data.
        print("written")
        read_data = rbcp.read(0xffffff00, 255)
        print(read_data)
        self.assertEqual(send_data, read_data)

    def test_bus_error(self):
        """
        test for detecting BUS error.
        """
        rbcp = Rbcp("127.0.0.1")
        self.assertRaises(RbcpBusError, rbcp.read, 0xfe, 4)

    def test_port_setting_error(self):
        """
        test for port setting error
        """
        rbcp = Rbcp("127.0.0.1", 4661)
        self.assertRaises(RbcpError, rbcp.read, 0xffffff00, 255)

    def test_check_packet(self):
        """
        test for _check_packet.
        """
        # pylint: disable=protected-access

        rbcp = Rbcp("127.0.0.1", 4661)

        self.assertRaises(RbcpError, rbcp._check_packet, b"", 0)

        valid_packet = bytearray(sitcpy.rbcp.HEADER_SIZE)
        valid_packet[0] = sitcpy.rbcp.HEADER_VERTYPE
        valid_packet[1] = 0xc8  # read

        packet = bytearray(valid_packet)
        rbcp._check_packet(packet, 0)

        packet = bytearray(valid_packet)
        packet[0] = 0
        self.assertRaises(RbcpError, rbcp._check_packet, packet, 0)

        packet = bytearray(valid_packet)
        packet[1] = 0x88  # write
        rbcp._check_packet(packet, 0)

        packet = bytearray(valid_packet)
        packet[1] = 0xc9  # read error
        self.assertRaises(RbcpError, rbcp._check_packet, packet, 0)

        packet = bytearray(valid_packet)
        packet[1] = 0x89  # write error
        self.assertRaises(RbcpError, rbcp._check_packet, packet, 0)

        packet = bytearray(valid_packet)
        packet[2] = 1  # packet id
        self.assertRaises(RbcpError, rbcp._check_packet, packet, 0)


if __name__ == "__main__":
    print("python version: {0}.{1}.{2}".format(sys.version_info[0],
                                               sys.version_info[1],
                                               sys.version_info[2]))
    print("default encoding: {0}".format(sys.getdefaultencoding()))
    print()
    unittest.main()
