# -*- coding:utf-8 -*-
"""
SiTCP RBCP pseudo server

Copyright (c) 2018, Bee Beans Technologies Co.,Ltd.
"""


from __future__ import print_function

import argparse
from contextlib import closing
import copy
from logging import getLogger, StreamHandler, INFO
import os
import select
import socket
import struct
import threading
import time
import traceback

from sitcpy import to_bytearray
import sitcpy
from sitcpy.cui import DataHandler, SessionThread, CuiServer, CommandHandler


LOGGER = getLogger(__name__)
HANDLER = StreamHandler()
HANDLER.setLevel(INFO)
LOGGER.setLevel(INFO)
LOGGER.addHandler(HANDLER)


class VirtualRegisterOutOfRange(Exception):
    """
    Exception for Virtual Memory Access Error
    """
    pass


def _make_header(read_write, packet_id, register_address, length):
    """
    Make the RBCP Header bytes.
    """
    command_type = 0
    if read_write == "r":
        command_type = 0xc8
    elif read_write == "w":
        command_type = 0x88
    elif read_write == "re":  # bus error
        command_type = 0xc9
    elif read_write == "we":  # bus error
        command_type = 0x89

    ret = struct.pack("8B", 0xff,
                      command_type,
                      packet_id,
                      length,
                      ((register_address & 0xff000000) >> 24) & 0xff,
                      ((register_address & 0x00ff0000) >> 16) & 0xff,
                      ((register_address & 0x0000ff00) >> 8) & 0xff,
                      ((register_address & 0x000000ff) >> 0) & 0xff)

    return ret


class VirtualRegister(object):
    """
    Virtual memory for RBCP Registers
    """

    def __init__(self, memory_size=65535, start_address=0):
        """
        :type memory_size: int
        :param memory_size: Virtual register size.

        :type start_address: int
        :param start_address: Start address of this virtual register
        """
        self._memory = bytearray(memory_size)
        self._memory_size = memory_size
        self._start_address = start_address
        self._read_callbacks = {}  # address:callback
        self._write_callbacks = {}  # address:callback

    def __repr__(self):
        return "Virtual Register %08X-%08X:%d bytes" % (
            self._start_address, self._start_address + self._memory_size - 1,
            self._memory_size)

    def set_initial_data(self, initial_data):
        """
        Setup initial memory image
        """
        self._memory = initial_data
        self._memory_size = len(initial_data)

    def get_memory(self):
        """
        Returns memory of this register.(byte_array)
        """
        return self._memory

    def get_register_info(self):
        """
        Returns register start address, end address and size.
        """
        return self._start_address, self._start_address + self._memory_size, self._memory_size

    def _is_intersect(self, register):
        """
        Return True is register is intersect with self.
        """
        start_address, end_address, memory_size = register.get_register_info()
        if self._start_address <= start_address:
            if self._start_address + self._memory_size > start_address:
                LOGGER.debug("path 2 %s %s - %s %s", self._start_address,
                             self._memory_size, start_address, memory_size)
                return True
        else:
            if end_address > self._start_address:
                LOGGER.debug("path 2 %s %s - %s %s", self._start_address,
                             self._memory_size, start_address, memory_size)
                return True
        return False

    def _is_neighbor(self, register):
        """
        Return True is register is neighbor os self.
        """
        start_address, end_address, _memory_size = register.get_register_info()

        if self._start_address + self._memory_size == start_address:
            return True
        if end_address == self._start_address:
            return True
        return False

    def merge(self, register):
        """
        Merge neighbor or intersect register

        :type register: VirtualRegister
        :param register: Virtual Register instance.

        :rtype: bool
        :return: True if register was merged, or False for not merged.
        """

        r_start_address, r_end_address, _r_memory_size = register.get_register_info()

        if self._is_neighbor(register) or self._is_intersect(register):
            LOGGER.debug("register merged: %s with %s", str(self), str(register))
            start_address = min(self._start_address, r_start_address)
            memory_size = max(self._start_address + self._memory_size,
                              r_end_address) - start_address
            LOGGER.info("register merged: start %08X size %d bytes", start_address, memory_size)
            merged = VirtualRegister(memory_size, start_address)
            merged.write_bytes(self._start_address, self._memory)
            merged.write_bytes(r_start_address, register.get_memory())
            del self._memory
            self._start_address = start_address
            self._memory = copy.deepcopy(merged.get_memory())
            self._memory_size = len(self._memory)
            del merged
            return True
        else:
            print("not merged intersect:%s neighbor:%s" %
                  (self._is_neighbor(register), self._is_intersect(register)))
            return False

    @staticmethod
    def create(start_address, initial_data):
        """
        Create new VirtualRegister from start address and initial byte data

        :param start_address: Register start address.
        :param initial_data: Byte object for initialize registers.
        """
        virtual_register = VirtualRegister(len(initial_data), start_address)
        virtual_register.set_initial_data(initial_data)
        return virtual_register

    @staticmethod
    def _init_binary_file(initial_file_path):
        """
        Parses binary file image. address initialized by filename and
        returns virtual register image dictionary.
        {`<address>`:bytearray1,,,}
        """
        file_name = os.path.basename(initial_file_path)
        file_base_name, _ext = os.path.splitext(file_name)
        ret = None
        try:
            initial_address = int(file_base_name, 16)
            ret = {initial_address: bytearray()}
            with open(initial_file_path, "rb") as binary_file:
                ret[initial_address] = binary_file.read(65536)
                return ret
        except OSError as exc:
            LOGGER.error("initialization error binary_file %s %s",
                         initial_file_path, exc)
        return ret

    @staticmethod
    def _init_simple_text(initial_file_path):
        """
        Parses simple text byte image with hex separated by space per each bytes.
        Returns virtual register image dictionary.
        {`<address>`:bytearray1,,,}
        """
        file_name = os.path.basename(initial_file_path)
        file_base_name, _ext = os.path.splitext(file_name)
        ret = None
        try:
            initial_address = int(file_base_name, 16)
            ret = {initial_address: bytearray()}
            with open(initial_file_path, "r") as simple_file:
                all_lines = simple_file.readlines()
                for each_line in all_lines:
                    try:
                        line_data = each_line.split("#")[0].split(" ")
                        for byte_data in line_data:
                            ret[initial_address] += int(byte_data,
                                                        16).to_bytes(1, "big")
                    except ValueError as exc:
                        LOGGER.error(
                            "initialization value error binary_file %s %s",
                            initial_file_path, exc)
                return ret
        except OSError as exc:
            LOGGER.error("initialization error simple text file %s %s",
                         initial_file_path, exc)
        return ret

    @staticmethod
    def _init_address_text(initial_file_path):
        """
        Parses address with text byte image with hex separated by space per each bytes.
        Address field must be separated by colon per each line.
        Returns virtual register image dictionary.
        {`<address>`:bytearray1,,,}
        """
        try:
            ret = {}
            with open(initial_file_path, "r") as simple_file:
                all_lines = simple_file.readlines()
                for each_line in all_lines:
                    try:
                        address_data = each_line.split("#")[0].split(":")
                        initial_address = int(address_data[0], 16)
                        if len(address_data) > 1:
                            line_data = address_data[1]
                            if initial_address not in ret:
                                ret[initial_address] = bytearray()
                            for byte_data in line_data.split(" "):
                                ret[initial_address] += int(byte_data,
                                                            16).to_bytes(1, "big")
                        else:
                            pass  # comment only line?
                    except ValueError as exc:
                        LOGGER.error(
                            "initialization value error address_text %s %s",
                            initial_file_path, exc)
                return ret
        except OSError as exc:
            LOGGER.error("initialization error address text file %s %s",
                         initial_file_path, exc)
            ret = None
        return ret

    @staticmethod
    def init_file_type_parser(initial_file_path):
        """
        Returns initial file parser per initial file types.
        """
        file_name = os.path.basename(initial_file_path)
        file_base_name, ext = os.path.splitext(file_name)
        if ext == ".bin":
            return VirtualRegister._init_binary_file
        else:
            try:
                int(file_base_name, 16)
                return VirtualRegister._init_simple_text
            except ValueError:
                return VirtualRegister._init_address_text

    # def initialize(self, initial_file_path):
    #     """
    #     Initialize register from initial_file_path.
    #
    #     :param initial_file_path: A initial value file path.
    #     when False, it will processes as ascii format like "00 11 22 33"
    #     """
    #     # TODO: pydoc の when False, が何を指しているのか
    #     try:
    #         initial_parser = self.init_file_type_parser(initial_file_path)
    #         initial_data = initial_parser(initial_file_path)
    #         # TODO: PyCharm 警告あり。initialize()自体が未使用
    #         for address in initial_data:
    #             self.write_bytes(address, initial_data[address])
    #     except ValueError as exc:
    #         LOGGER.error("virtual register initialization value error %s %s",
    #                      initial_file_path, exc)
    #         raise

    def register_write_callback(self, address, write_callback):
        """
        Sets the callback to be called when writing to a specific address.
        write_callback( address, value )
        """
        if self.check_address_range(address, 1):
            self._write_callbacks[address] = write_callback

    def register_read_callback(self, address, read_callback):
        """
        Sets the callback to be called when reading to a specific address.
        read_callback( address )
        """
        if self.check_address_range(address, 1):
            self._read_callbacks[address] = read_callback

    def check_address_range(self, address, length):
        """
         When the address_check_enable, check the address range and return the results.

         :return: True for good address range, False for Bus Error.
         if address_range is not initialized(by initialize, with binary file), return always True
        """
        if self._start_address <= address:
            if (self._start_address + self._memory_size) >= (address + length):
                return True
        return False

    def write_bytes(self, address, data_bytes):
        """
        Write bytes to the address. this is for initialize.

        :param address: Write.address.
        :param data_bytes: Write data bytes(python byte like objects).
        """
        #             address = address - self._offset
        byte_length = len(data_bytes)
        if self.check_address_range(address, byte_length):
            for write_address in range(address, address + byte_length):
                if write_address in self._write_callbacks.keys():
                    self._write_callbacks[write_address](
                        write_address, data_bytes[write_address - self._start_address])
            self._memory[address - self._start_address:address -
                         self._start_address + byte_length] = data_bytes
        else:
            raise VirtualRegisterOutOfRange(
                "read_bytes error 0x%08X %d bytes" % (address, byte_length))

    def read_bytes(self, address, byte_length):
        """
        Read bytes from the address.

        :param address: Read address.
        :param byte_length: Read length in bytes.
        :rtype: bytearray
        """
        if self.check_address_range(address, byte_length):
            for read_address in range(address, address + byte_length):
                if read_address in self._read_callbacks:
                    self._read_callbacks[read_address](read_address)
            address = address - self._start_address
            return self._memory[address:address + byte_length]
        else:
            raise VirtualRegisterOutOfRange(
                "read_bytes error 0x%08X %d bytes" % (address, byte_length))

    def dump(self, start=-1, end=-1, address=True):
        """
        Dump the memory.

        :param start: Start address.
        :param end: End address.
        :param address: If True, print address information.
        """
        if start < 0:
            start = self._start_address
        if end < 0:
            end = start + self._memory_size
        dump_line = ""
        for read_address in range(start, end + 1, 16):
            read_size = min(end - read_address, 16)
            read_bytes = self.read_bytes(read_address, read_size)
            line = ""
            for read_byte in read_bytes:
                line += "%02X " % read_byte
            if line:
                if address:
                    line = "%08X:%s" % (read_address, line)
                print("%s" % line)
                dump_line += "%s\n" % line
        return dump_line


class RbcpServer(threading.Thread):
    """
    pseudo sitcp RBCP server for test
from sitcpy.rbcp_server import RbcpServer
prs = RbcpServer()
prs._memory.initialize("sitcpy/vm_init")
prs.run()
    """

    def __init__(self, udp_port=4660, available_host="0.0.0.0"):
        """
        :param udp_port: RBCP server port.
        :param available_host: Used to restrict the communication client, if necessary.
        """
        super(RbcpServer, self).__init__()

        self._state = sitcpy.State(sitcpy.THREAD_NOT_STARTED)

        self._udp_port = udp_port
        self._available_host = available_host
        self._error_short_message = 0
        self._registers = []  # VirtualRegister(65536 * 2)
        # SiTCP Reserved.
        self._registers.append(VirtualRegister(65536, 0xFFFF0000))

    def read_registers(self, address, length):
        """
        Read byte data from designated address/length.

        :param address: Address of registers.
        :param length: Length to read.
        :rtype: bytearray
        :return: byte data (byte array object).
        """
        for register in self._registers:
            try:
                read_data = register.read_bytes(address, length)
                return read_data
            except VirtualRegisterOutOfRange:
                pass
        raise VirtualRegisterOutOfRange()

    def write_registers(self, address, write_data):
        """
        Write byte data from designated address/length.

        :type address: int
        :param address: Write address.

        :type write_data: bytes or bytearray
        :param write_data: Data to write.

        :rtype: bytearray
        :return: read_data after write.
        """
        for register in self._registers:
            try:
                register.write_bytes(address, write_data)
                return register.read_bytes(address, len(write_data))
            except VirtualRegisterOutOfRange:
                pass
        raise VirtualRegisterOutOfRange()

    @property
    def registers(self):
        """
        :rtype: list[VirtualRegister]
        """
        return self._registers

    def initialize_registers(self, initial_file_path):
        """
        Initialize register from initial_file_path.

        :param initial_file_path: A initial value file path.
        """
        try:
            message = ""
            initial_parser = VirtualRegister.init_file_type_parser(
                initial_file_path)
            initial_data = initial_parser(initial_file_path)
            for address, data in initial_data.items():
                self._registers.append(
                    VirtualRegister.create(address, data))
                message += "%08X:%s bytes\n" % (address,
                                                len(initial_data[address]))
            return message
        except ValueError as exc:
            LOGGER.error("virtual register initialization value error %s %s",
                         initial_file_path, exc)
            raise

    def merge_registers(self):
        """
        Merge intersect or neighbor VirtualRegisters.
        """
        if len(self._registers) <= 1:
            return

        for index1, register1 in enumerate(self._registers):
            for index2 in range(index1 + 1, len(self._registers)):
                register2 = self._registers[index2]
                if register1.merge(register2):
                    del self._registers[index2]
                    self.merge_registers()
                    return

    def dump_registers(self):
        """
        Create dump string image of registers
        """
        dump_register = ""
        for register in self._registers:
            dump_register += register.dump()
        return dump_register

    def get_register_info(self):
        """
        Returns list of start_address, end_address, size tuple of registers
        """
        ret = []
        for register in self._registers:
            ret.append(register.get_register_info())
        return ret

    def start(self):
        super(RbcpServer, self).start()
        self._state.transit(sitcpy.THREAD_STARTING)
        self._state.wait(sitcpy.THREAD_RUNNING)

    def stop(self):
        """
        Exit RbcpServer thread
        """
        self._state.transit(sitcpy.THREAD_STOPPING)
        self.join(2)

    def run(self):
        """
        Start server thread
        """
        try:
            server_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            read_list = [server_sock]

            buffer_size = 4096
            with closing(server_sock):
                try:
                    server_sock.bind((self._available_host, self._udp_port))
                except OSError as exc:
                    LOGGER.error("RbcpServer:error %s @ %s UDP:%s", str(exc), self._available_host, self._udp_port)
                    LOGGER.debug(traceback.format_exc())
                    raise

                self._state.transit(sitcpy.THREAD_RUNNING)
                while self._state() == sitcpy.THREAD_RUNNING:
                    try:
                        readable, _, _ = select.select(read_list, [], [], 0.1)
                        for read_sock in readable:
                            rbcp_msg, remote_address = read_sock.recvfrom(buffer_size)
                            rbcp_msg = to_bytearray(rbcp_msg)

                            if len(rbcp_msg) < 8:
                                self._error_short_message += 1
                                continue
                            if rbcp_msg[0] != 0xff:
                                continue

                            if rbcp_msg[1] == 0xc0:  # READ
                                packet_read = True
                            elif rbcp_msg[1] == 0x80:  # WRITE
                                packet_read = False
                            else:  # ERROR
                                print("unknown packet_type %s" % str(rbcp_msg[1]))
                                continue

                            packet_id = rbcp_msg[2]
                            packet_length = rbcp_msg[3]
                            packet_address = struct.unpack(">I", bytes(rbcp_msg[4:8]))[0]
                            packet_data = rbcp_msg[8:]

                            if packet_read:
                                try:
                                    packet_data = self.read_registers(
                                        packet_address, packet_length)
                                    reply = _make_header(
                                        "r", packet_id, packet_address, packet_length) + packet_data
                                except VirtualRegisterOutOfRange:
                                    packet_length = len(packet_data)
                                    reply = _make_header("re", packet_id, packet_address, packet_length) + packet_data
                                    LOGGER.error(("reply(bus error) address:%08X-length:%x " %
                                                  (packet_address, packet_length)) + str(reply))
                                server_sock.sendto(reply, remote_address)
                            else:
                                try:
                                    self.write_registers(packet_address, packet_data[0:packet_length])
                                    reply = _make_header("w", packet_id, packet_address, packet_length) + packet_data
                                except VirtualRegisterOutOfRange:
                                    packet_length = len(packet_data)
                                    reply = _make_header("we", packet_id, packet_address, packet_length) + packet_data
                                    print("reply(bus error):" + str(reply))
                                server_sock.sendto(reply, remote_address)
                    except OSError as exc:
                        LOGGER.error("Pseudo server Exception %s", exc)
                        LOGGER.debug(traceback.format_exc())
        finally:
            self._state.transit(sitcpy.THREAD_STOPPED)


class DataGenerator(DataHandler):
    """
    Data Generator for pseudo SiTCP device.
    SessionThreadGen(send created data to the session.)
        <---(inclusion relation)<--DataGenerator(create generation data)
    """

    def __init__(self):
        """
        Data Handler for binary(byte object)
        """
        super(DataGenerator, self).__init__()

        self._data_unit = 8
        self._count = 0
        self._data_unit_count = 2  # burst data_unit counts to generate

    def on_start(self, session):
        """
        Ignore send prompt
        """
        pass

    def on_data(self, session, byte_data):
        """
        Ignore received data
        """
        pass

    @property
    def data_unit_count(self):
        """
        This property is referenced from the SessionThreadGen class.
        The SessionThread class calls create_data (data_unit_count) with the return value.
        When data_unit_count is increased, burst data from this emulator is generated.
        Specify a multiple of data_unit. When data_unit = 8 and data_unit_count = 2 is returned,
        16 bytes of data are burst transferred.

        :rtype: int
        :return: data_unit_count of create_data.
        """
        return self._data_unit_count

    @data_unit_count.setter
    def data_unit_count(self, val):
        """
        Set the data_unit_count parameter. See data_unit_count property for details.

        :type val: int
        """
        self._data_unit_count = val

    def create_data(self, data_unit_count):
        """
        Create unit data

        :rtype: bytearray
        """
        data = bytearray(self._data_unit * data_unit_count)
        # print("DEBUG:create data count %d size %d" %
        #       (data_unit_count, self._data_unit * data_unit_count))
        for data_unit in range(0, data_unit_count - 1):
            count_bytes = struct.pack(">L", self._count)
            data[self._data_unit * data_unit] = 0xa5  # struct.pack("B", 0xa5)
            index = self._data_unit * data_unit + 4
            for count_byte in count_bytes:
                data[index] = count_byte
                index += 1
            self._count += 1
            if self._count == 0xffffffff:
                self._count = 0
        return data


class SessionThreadGen(SessionThread):
    """
    SessionThread class for data generation.
from sitcpy.cuisvr import CuiSvr
from sitcpy.rbcp_server import SessionThreadGen, DataGenerator
srv = CuiSvr(8888,SessionThreadGen, DataGenerator())
srv.run()
    """

    def __init__(self, server, data_generator, sock, client_address, max_buff=1024 * 1024):
        """
        Constructor.

        :type server: CuiServer
        :param server: The server that owns this session.

        :type data_generator: DataGenerator
        :param data_generator: Pass the received data to this data generator.

        :type sock: socket.socket or None
        :param sock: Client socket.

        :type client_address: str
        :param client_address: Client IP address.

        :type max_buff: int
        :param max_buff: maximum receive buffer for sock.recv().
        """
        super(SessionThreadGen, self).__init__(server, data_generator, sock, client_address, max_buff)

    def run(self):
        """
        Send generated data by the DataGenerator to the session
        """
        # pylint: disable=unused-variable
        try:
            print("starting session from client " + str(self._client_address))
            self._data_handler.on_start(self)
            write_list = [self._sock]

            self._state.transit(sitcpy.THREAD_RUNNING)
            while self._state() == sitcpy.THREAD_RUNNING:
                data_count = self._data_handler.data_unit_count
                try:
                    _, writable, _ = select.select([], write_list, [], 0.1)
                    if self._sock in writable:
                        self._sock.send(self._data_handler.create_data(data_count))
                except (OSError, socket.error) as exc:
                    LOGGER.debug("Exception at SessionThreadGen.run : %s" %
                                 str(exc))
                    LOGGER.debug("Pseudo Data Session Closed")
                    break

            self._state.transit(sitcpy.THREAD_STOPPING)
            del write_list[:]
            self.close()
        finally:
            self._state.transit(sitcpy.THREAD_STOPPED)


class RbcpCommandHandler(CommandHandler):
    """
    Command Handler for PseudoDevice
    """

    def __init__(self, prompt, seps=" "):
        super(RbcpCommandHandler, self).__init__(prompt, seps)

        self._data_generator = None
        self._rbcp_server = None

    def bind(self, rbcp_server, data_generator):
        """
        Set rbcp_server and data_generator for manipulate.

        :type rbcp_server: RbcpServer
        :type data_generator: DataGenerator
        """
        self._rbcp_server = rbcp_server
        self._data_generator = data_generator

    def on_cmd_read(self, session, cmd_list):
        """
        Read RBCP Memory

        :usage: read <address in hexadecimal> <length in decimal>
        """
        if len(cmd_list) == 3:
            try:
                address = int(cmd_list[1], 16)
                length = int(cmd_list[2])
                read_data = self._rbcp_server.read_registers(address, length)
                reply_text = ""
                for index, data in enumerate(read_data):
                    if index != 0 and index % 8 == 0:
                        self.reply_text(session, reply_text)
                        reply_text = ""
                    reply_text += "%02X " % data
                if reply_text:  # len(reply_text) != 0: PEP8 len-as-condition
                    self.reply_text(session, reply_text)
            except ValueError as exc:
                session.repy("NG:Invalid argument %s" % str(exc))
            except VirtualRegisterOutOfRange:
                self.reply_text(session, "NG:Bus error")
        else:
            self.print_help(session, cmd_list[0], True)

        return True

    def on_cmd_write(self, session, cmd_list):
        """
        Write RBCP Memory

        :usage: write <address in hexadecimal> <write data in hexadecimal 1byte> \
         [<write data in hexadecimal 1byte> .. ]
        """
        if len(cmd_list) >= 3:
            address = int(cmd_list[1], 16)
            write_data = cmd_list[2:]
            try:
                write_bytes = bytearray()
                for data in write_data:
                    write_bytes.append(int(data, 16))
                read_back_data = self._rbcp_server.write_registers(
                    address, write_bytes)
                if read_back_data == write_bytes:
                    self.reply_text(session, "write %d bytes." % len(write_data))
                else:
                    self.reply_text(session,
                                    "write %d bytes. NOTE:read back data not equal to write data" % len(write_data))
            except VirtualRegisterOutOfRange:
                self.reply_text(session, "NG:Bus error")
        else:
            self.print_help(session, cmd_list[0], True)

        return True

    def on_cmd_initreg(self, session, cmd_list):
        """
        :usage: initreg <file_path>
        <file_path> file or directory for initialize registers.
        directory - initialize files in the directory. files should be formatted listed beneath.
        binary file - binary register image with the file name like "<address in hexadecimal>.bin"
        simple text file - text hexadecimal byte data with file name like "<address in hexadecimal>.txt"
        addressed text file - address:<hex_data> <hex_data. ...<CR> format with none hexadecimal file name.
        """
        messages = None
        if len(cmd_list) == 1:
            self.print_help(session, cmd_list[0], True)
        elif len(cmd_list) == 2:
            try:
                if os.path.isdir(cmd_list[1]):
                    file_list = os.listdir(cmd_list[1])
                    messages = ""
                    for initial_file in file_list:
                        messages += self._rbcp_server.initialize_registers(
                            os.path.join(cmd_list[1], initial_file))
                else:
                    messages = self._rbcp_server.initialize_registers(cmd_list[
                        1])
            except OSError as exc:
                self.reply_text(session, "NG:%s" % str(exc))
        else:
            self.reply_text(session, "NG:Too many arguments")
        if messages is not None:
            self.reply_text(session, "address area initialized")
            for message in messages.split("\n"):
                self.reply_text(session, message)

        return True

    def on_cmd_dataunitcount(self, session, cmd_list):
        """
        :usage: dataunitcount: Set data unit count to generate.
        """
        if len(cmd_list) == 1:
            if self._data_generator is not None:
                self.reply_text(session, str(self._data_generator.data_unit_count))
            else:
                self.reply_text(session, "NG:Data generator is not set")
        elif len(cmd_list) == 2:
            try:
                data_unit_count = int(cmd_list[1])
                self._data_generator.data_unit_count = data_unit_count
                self.reply_text(session, "set data unit count %d = %d" % (
                    data_unit_count, self._data_generator.data_unit_count))
            except ValueError as exc:
                self.reply_text(session, "NG:%s" % str(exc))
        else:
            self.reply_text(session, "too many arguments")
        return True

    def on_cmd_dump(self, session, _cmd_list):
        """
        :usage: dump: Dump virtual registers.
        """
        dump_registers = self._rbcp_server.dump_registers()
        for dump in dump_registers.split("\n"):
            self.reply_text(session, dump)
        return True


class PseudoDevice(object):
    """
    Pseudo device with command handler, data generator, and bcp emulator
    """

    def __init__(self, rbcp_command_handler, data_generator, rbcp_server,
                 command_port=9090, data_port=24242):
        """
        Constructor.

        :type rbcp_command_handler: RbcpCommandHandler
        :type data_generator: DataGenerator
        :type rbcp_server: RbcpServer
        :type command_port: int
        :type data_port: int
        """
        self._cuisvr = CuiServer(SessionThread, rbcp_command_handler,
                                 command_port)
        self._rbcp_server = rbcp_server
        self._pseudo_generator = CuiServer(SessionThreadGen, data_generator,
                                           data_port)
        # TODO: Stateへ置き換え
        self._continue = True
        self._thread = None  # for start() -- thread mode.

    def stop(self):
        """
        Stop the Pseudo Device run_loop
        """
        self._continue = False
        if self._thread is not None:
            self._thread.join(2)

        self._cuisvr.stop()
        self._cuisvr.join()

        self._rbcp_server.stop()
        self._rbcp_server.join()
        self._pseudo_generator.stop()

        self._pseudo_generator.join()

    def start(self):
        """
        Start run_loop as thread
        """
        self._thread = threading.Thread(target=self.run_loop)
        self._thread.start()

    def run_loop(self):
        """
        Run the device services.
        """
        self._cuisvr.start()
        self._rbcp_server.start()
        self._pseudo_generator.start()
        print("PseudoDevice.run_loop started cuisvr, rbcp_server, pseudo_generator")
        try:
            while self._continue:
                time.sleep(0.5)
                if self._cuisvr.is_exit():
                    print("exiting pseudo device")
                    break
        except KeyboardInterrupt:
            print("detected CTRL + C. exiting server..")

        self._pseudo_generator.stop()
        self._pseudo_generator.join(1)
        self._rbcp_server.stop()
        self._rbcp_server.join(1)
        self._cuisvr.stop()
        self._cuisvr.join(1)


def default_pseudo_arg_parser():
    """
    Create ArgumentParser for pseudo device.

    :rtype: argparse.ArgumentParser
    :return: Default argument parser.
    """
    arg_parser = argparse.ArgumentParser(
        description="pseudo device main.")
    # arg_parser.add_argument("-a", "--host", type=str, default="0.0.0.0", help="acceptable host")
    arg_parser.add_argument("-p", "--port", type=int,
                            default=9090, help="server port number")
    arg_parser.add_argument("-d", "--dataport", type=int,
                            default=24242, help="emulation data port number")
    # arg_parser.add_argument("-s", "--source", type=open,
    #                         help="initial command file")
    # arg_parser.add_argument(
    #     "-x", "--exec", help="single line initial commands separated with comma")
    return arg_parser


def main():
    """
    Sample pseudo SiTCP Device.
    """
    args = default_pseudo_arg_parser().parse_args()

    command_port = args.port
    data_port = args.dataport

    rbcp_server = RbcpServer()
    data_generator = DataGenerator()
    rbcp_command_handler = RbcpCommandHandler("pdev$ ")
    rbcp_command_handler.bind(rbcp_server, data_generator)
    pdev = PseudoDevice(rbcp_command_handler, data_generator, rbcp_server,
                        command_port, data_port)
    pdev.run_loop()


if __name__ == "__main__":
    main()
