# -*- coding:utf-8 -*-
"""
SiTCP device simulator

Copyright (c) 2018, Bee Beans Technologies Co.,Ltd.
"""

from __future__ import print_function

from logging import getLogger, StreamHandler, INFO

from sitcpy.rbcp_server import RbcpCommandHandler, DataGenerator,\
    default_pseudo_arg_parser, RbcpServer, PseudoDevice


LOGGER = getLogger(__name__)
HANDLER = StreamHandler()
HANDLER.setLevel(INFO)
LOGGER.setLevel(INFO)
LOGGER.addHandler(HANDLER)


class PseudoRbcpCommandHandler(RbcpCommandHandler):
    """
    Command handler
    """

    def on_cmd_mycmd(self, session, cmd_list):
        """
        This is sample command. display received arguments.

        :usage: mycmd [arg1 [arg2 ...]]: sample command.
        """
        self.reply_text(session, "mycmd received arguments: %s" % str(cmd_list))
        return True

    def on_cmd_set_generate_mode(self, generate_mode):
        # TODO: 未実装
        pass


class PseudoDataGenerator(DataGenerator):
    """
    Data Generator. create data for emulation
    """

    def __init__(self):
        super(PseudoDataGenerator, self).__init__()

        self._generate_directory = None
        self._generate_modes = ("Fixed Pattern", "All Files", "File")
        self._generate_mode = "Fixed Pattern"
        self._data_unit = 8  # bytes.
        # Fixed Pattern as default.
        self._data_buffer = bytearray(b"F010200001020304")

    @property
    def generate_mode(self):
        """
        :return: Current generate_mode.
        """
        return self._generate_mode

    @property
    def generate_modes(self):
        """
        :return: Selectable generate_modes.
        """
        return self._generate_modes

    def create_fixed_pattern(self, data_unit_count):
        """
        :type data_unit_count: int
        :param data_unit_count: Create data size, the unit is the size of self._data_unit.

        :return: Created fixed pattern data (byte array).
        """
        return self._data_buffer * data_unit_count

    def create_data(self, data_unit_count):
        """
        Create unit data
        """
        return self.create_fixed_pattern(data_unit_count)


def main(args=None):
    """
    Sample pseudo SiTCP Device.
    """
    args = default_pseudo_arg_parser().parse_args(args)

    command_port = args.port
    data_port = args.dataport

    rbcp_server = RbcpServer()
    data_generator = PseudoDataGenerator()
    rbcp_command_handler = PseudoRbcpCommandHandler("pdev$ ")
    rbcp_command_handler.bind(rbcp_server, data_generator)
    pdev = PseudoDevice(rbcp_command_handler, data_generator, rbcp_server,
                        command_port, data_port)
    pdev.run_loop()


if __name__ == "__main__":
    main()
