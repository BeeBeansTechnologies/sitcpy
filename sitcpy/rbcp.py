# -*- coding:utf-8 -*-
"""
SiTCP RBCP library

Copyright (c) 2018, Bee Beans Technologies Co.,Ltd.
"""

from __future__ import print_function

import select
import socket
import struct

from sitcpy import is_int, to_bytearray, to_bytes


class RbcpError(Exception):
    """
    SiTCP RBCP Error Exception class.
    """
    pass


class RbcpBusError(RbcpError):
    """
    SiTCP RBCP Bus Error.
    This exception is raised when the RBCP Reply message with Bus Error Flag was set.
    Check Rbcp.read/write address and length value is valid.
    """

    def __init__(self, message=None):
        """
        :type message: str or None
        :param message: Displayed as Exception message. for None, default message is displayed.
        """
        if message is None:
            message = "SiTCP RBCP Bus Error. Check Device Address and Length for read/write"

        super(RbcpBusError, self).__init__(message)


class RbcpTimeout(RbcpError):
    """
    SiTCP RBCP Timeout.
    This exception is raised when no reply message was received from the device.
    Check Rbcp ip_address and udp_port was set correctly.
    """

    def __init__(self, message=None):
        """
        :type message: str or None
        :param message: Displayed as Exception message. for None, default message is displayed.
        """
        if message is None:
            message = "SiTCP RBCP Timeout. Check Device IP and UDP Port."

        super(RbcpTimeout, self).__init__(message)


HEADER_SIZE = 8  # Size of RBCP packet.
HEADER_READ = 0  # Read mode.
HEADER_WRITE = 1  # Write mode.
HEADER_VERTYPE = 0xff  # RBCP version type.


class Rbcp(object):
    """
    SiTCP RBCP Class.
    Send UDP/RBCP packet to read/write SiTCP device Registers.
    """

    SOCKET_TIMEOUT = 3000  # milliseconds

    def __init__(self, device_ip="192.168.10.16", udp_port=4660, timeout=SOCKET_TIMEOUT):
        """
        Constructor.

        :type device_ip: str
        :param device_ip: SiTCP Device IP Address.

        :type udp_port: int
        :param udp_port: SiTCP Device RBCP(UDP) Port.

        :type timeout: int
        :param timeout: The number of milliseconds that the socket times out.
        """
        self._address = (device_ip, udp_port)
        self._packet_id = 0
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket_timeout = timeout / 1000.0
        self._sock.settimeout(self._socket_timeout)

    @staticmethod
    def _make_header(read_write, register_address, length, packet_id):
        """
        Make RBCP Header.

        :type register_address: int
        :type length: int
        :type packet_id: int
        :rtype: bytes
        """
        if not is_int(register_address):
            raise ValueError("Register address must be an int.")
        if not is_int(length):
            raise ValueError("Register address must be an int.")

        if register_address < 0 or register_address > 0xffffffff:
            raise ValueError("Invalid register address.")
        if length < 0 or length > 255:
            raise ValueError("Specify a value between 0 and 255 for SiTCP read/write length.")
        if register_address + length > 0xffffffff:
            raise ValueError("Invalid register address.")

        command_type = 0xc0 if read_write == HEADER_READ else 0x80
        ret = struct.pack("8B",
                          HEADER_VERTYPE,
                          command_type,
                          packet_id,
                          length,
                          ((register_address & 0xff000000) >> 24) & 0xff,
                          ((register_address & 0x00ff0000) >> 16) & 0xff,
                          ((register_address & 0x0000ff00) >> 8) & 0xff,
                          ((register_address & 0x000000ff) >> 0) & 0xff)
        return ret

    def read(self, register_address, length):
        """
        Read SiTCP Device Register.

        :type register_address: int
        :param register_address: register address to read.

        :type length: int
        :param length: Read length in bytes. max 255.

        :rtype: bytearray
        :return: Received packet data.
        """
        header = self._make_header(
            HEADER_READ, register_address, length, self._packet_id)
        wait_id = self._packet_id
        self._packet_id += 1
        if self._packet_id == 256:
            self._packet_id = 0
        packet_data = b""
        rbcp_packet = header + packet_data
        return self._rbcp_send_recv(rbcp_packet, wait_id)

    def write(self, register_address, packet_data):
        """
        Write to SiTCP Device Register.

        :type register_address: int
        :param register_address: Register address to write.

        :type packet_data: bytes or bytearray or str
        :param packet_data: Write data (Python byte like object).

        :rtype: bytearray
        :return: Received packet data.
        """
        packet_data = to_bytes(packet_data)

        header = self._make_header(
            HEADER_WRITE, register_address, len(packet_data), self._packet_id)
        wait_id = self._packet_id
        self._packet_id += 1
        if self._packet_id == 256:
            self._packet_id = 0
        rbcp_packet = header + packet_data
        # , len(packet_data))
        return self._rbcp_send_recv(rbcp_packet, wait_id)

    @staticmethod
    def _check_packet(packet, wait_id):
        """
        Check packet data is valid.

        :type packet: bytearray

        :type wait_id: int
        :param wait_id: Waiting packet ID.
        """
        len_packet = len(packet)
        if len_packet < HEADER_SIZE:
            raise RbcpError("RBCP header too short(%d/%d)" %
                            (len_packet, HEADER_SIZE))
        if packet[0] != HEADER_VERTYPE:
            raise RbcpError("RBCP Header Version Mismatch")
        if (packet[1] & 0x1) == 1:
            raise RbcpBusError()
        if packet[2] != wait_id:
            raise RbcpError("RBCP Packet ID Mismatch")

    def _recv_packet(self):
        """
        Receive RBCP Reply Packet, from device.

        :rtype: bytearray
        :return: Received packet.
        """
        read_list = [self._sock]
        reply_data = b""
        try:
            readable, _, _ = select.select(read_list, [], [], self._socket_timeout)
            if not readable:
                raise RbcpTimeout()
            if self._sock in readable:
                reply_data, _addr = self._sock.recvfrom(
                    HEADER_SIZE + 256)
                if not reply_data:
                    raise RbcpError(
                        "RBCP:Receive Data Length was zero.")
        except RbcpError as exc:
            raise exc
        except Exception as exc:
            raise RbcpError(
                "RBCP:Exception when receiving packet [%s]" % str(exc))
        return to_bytearray(reply_data)

    def _rbcp_send_recv(self, rbcp_packet, wait_id):
        """
        Send request RBCP Packet and Receive Reply, Check it and returns Packet data

        :param rbcp_packet: RBCP Packet(header + data).
        :param wait_id: Waiting Packet ID defined in RBCP Header.

        :rtype: bytearray
        :return: Received Packet data.
        """
        try:
            sent_size = 0
            send_size = len(rbcp_packet)
            while sent_size < send_size:
                res = self._sock.sendto(
                    rbcp_packet[sent_size:], self._address)
                if res < 0:
                    raise RbcpError(
                        "RBCP Socket send_packet sendto returns negative(%d)" % res)
                sent_size += res
        except RbcpError as exc:
            raise exc
        except Exception as exc:
            raise RbcpError(
                "RBCP Socket Error on send_packet %s" % str(exc))
        receive_packet = self._recv_packet()
        self._check_packet(receive_packet, wait_id)
        return receive_packet[HEADER_SIZE:]
