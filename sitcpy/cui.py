# -*- coding:utf-8 -*-
"""
Python CUI Server Library core

*Extends the CommandHandler class to customize the commands.
*To add a command, add the following function.
def on_cmd_ <COMMAND> (self, session, cmd_list)
on_cmd_ <COMMAND> is called when * <COMMAND> is received.

* Help uses pydoc. Put summary after ':usage:' or '@usage:' with one line and describe the detail from next lines.
* Function details are not displayed in command "help",
* help <COMMAND> will display the detail of the <COMMAND>
* command list holds the command and arguments.
* "session" argument represents the session. To reply the session client, use reply_text(session, message).

Copyright (c) 2018, Bee Beans Technologies Co.,Ltd.
"""

from __future__ import print_function

import argparse
import json
from logging import getLogger, StreamHandler, DEBUG
from operator import itemgetter  # for sorting keys of dict
import os
import select
import socket
import sys
import threading
import time
import traceback
import types

from sitcpy import to_bytes, to_str
import sitcpy


LOGGER = getLogger(__name__)
HANDLER = StreamHandler()
HANDLER.setLevel(DEBUG)
LOGGER.setLevel(DEBUG)
LOGGER.addHandler(HANDLER)
LOGGER.debug("system default encoding:%s", sys.getdefaultencoding())


class DataHandler(object):
    """
    DataHandler is parent class of CommandHandler. This class handle the data
    as binary, bytearray.
    """

    def __init__(self):
        """
        Constructor for the DataHandler.
        """
        self._exit = False
        """:type : bool"""

    def on_server_start(self, server):
        """
        Called just before the server starts looping.
        Override if initialization processing is necessary.

        :type server: CuiServer
        :param server: Started server.
        """
        pass

    def set_exit(self):
        """
        Sets that the handler is in the exit state.
        """
        self._exit = True

    def is_exit(self):
        """
        Returns the exit status
        The self._exit flag is set when the server should be exit.

        :rtype: bool
        :return: Exit status of this handler.
        """
        return self._exit

    def on_shutdown(self, server):
        """
        Called when the server is exiting.

        :type server: CuiServer
        :param server: Server to be shut down.
        """
        pass

    def on_start(self, session):
        """
        Called when the session started. overrides to send the prompt to the client.
        Note that this is called per session bases.

        :type session: SessionThread
        :param session: Client session.
        """
        pass

    def find_delimiter_position(self, byte_data):  # pylint: disable=no-self-use
        """
        Find and return the delimiter position of byte_data.
        If the delimiter position can not be found, please return -1.

        :type byte_data: bytes
        :param byte_data: Find the delimiter position of this byte data.

        :rtype: int
        :return: The delimiter position found in byte_data. If not found, return -1.
        """
        return len(byte_data)

    def on_data(self, session, byte_data):
        """
        Called when the server received data from the session.
        byte_data is delimited by the result of find_delimiter_position().

        :type session: SessionThread
        :param session: Client session.

        :type byte_data: bytes
        :param byte_data: Received data.

        :rtype: bool
        :return: False for exit, True for continue.
        """
        pass

    def on_idle(self, session):
        """
        Called at idle.

        :type session: SessionThread
        :param session: Client session.
        """
        pass


class TextHandler(DataHandler):
    """
    This is a DataHandler derived class that accepts text data from the client.
    """

    def __init__(self):
        super(TextHandler, self).__init__()

        self._linesep = "\r\n"
        """:type : str"""

    def find_delimiter_position(self, byte_data):
        """
        Find and return the delimiter position of byte_data.
        If the delimiter position can not be found, please return -1.

        :type byte_data: bytes
        :param byte_data: Find the delimiter position of this byte data.

        :rtype: int
        :return: The delimiter position found in byte_data. If not found, return -1.
        """

        # Find line delimiter.
        for delimiter, delimiter_str in ((b"\r\n", "\r\n"),
                                         (b"\n", "\n"),
                                         (b"\r", "\r")):
            pos = byte_data.find(delimiter)
            if pos >= 0:
                self._linesep = delimiter_str
                return pos + len(delimiter)
        return -1

    @property
    def linesep(self):
        """
        Line separator of client (CRLF or LF or CR).

        :rtype: str
        """
        return self._linesep

    def reply_text(self, session, text, add_linesep=True):
        """
        Replies text to client. If session.sock is None, output text to stdout.

        :type session: SessionThread
        :param session: Client session.

        :type text: str
        :param text: Text to be sent.

        :type add_linesep: bool
        :param add_linesep: If true, a newline character is added at the end of the text to be sent.
        """

        if add_linesep:
            text += self.linesep

        sock = session.sock
        if sock is not None:
            sock.sendall(to_bytes(text))
        else:
            sys.stdout.write(text)
            sys.stdout.flush()


class CommandHandler(TextHandler):
    """
    CommandHandler handle the byte data of on_data as string message.
    And call on_command() function.
    A handler whose derived class's on_cmd_ <command> matches the first string <command> is called.
    The on_cmd_<command> handler displays help with the following pydoc.

    :usage: command <mandatory param> [optional param]
    @ Arguments <mandatory param>
    @ Arguments [optional param]
    """

    class _Command(object):
        """
        Represents a parsed command.
        """
        __slots__ = ["function", "usage_text"]

        def __init__(self):
            self.function = None  # Callable object
            """:type : types.MethodType"""
            self.usage_text = None  # Usage text of the command.
            """:type : str"""

    def __init__(self, prompt, seps=" "):
        """
        Constructor.

        :type prompt: str
        :param prompt: Prompt string of the CommandHandler.

        :type seps: str
        :param seps: Command separator.
        """
        assert prompt, "prompt is empty str."

        super(CommandHandler, self).__init__()

        self._prompt = prompt
        """:type : str"""
        self._seps = seps
        """:type : str"""
        self._commands = self._find_commands()
        """:type : dict[str, CommandHandler._Command]"""

    def put_prompt(self, session):
        """
        Put the prompt to the session.

        :type session: SessionThread
        :param session: Client session.
        """
        self.reply_text(session, self._prompt, False)

    def on_start(self, session):
        """
        Send the prompt to the session when the session is started.

        :type session: SessionThread
        :param session: Sender session object.
        """
        self.put_prompt(session)

    def on_data(self, session, byte_data):
        """
        Called when the server received data from the session.
        byte_data is delimited by the result of find_delimiter_position().

        :type session: SessionThread
        :param session: Client session.

        :type byte_data: bytes
        :param byte_data: Received data.

        :rtype: bool
        :return: False for exit, True for continue.
        """
        try:
            str_data = to_str(byte_data).strip()

            for cmd in str_data.split(";"):
                args = [
                    val for val in [
                        val.strip() for val in cmd.split(self._seps)
                    ] if val]

                if not args:
                    continue

                if not self.on_command(session, args):
                    return False

            self.put_prompt(session)
            return True

        except Exception as exc:  # pylint: disable=broad-except
            LOGGER.error(traceback.format_exc())
            self.reply_text(session, "NG:Error occurred (%s)" % str(exc))
            return False

    def on_command(self, session, cmd_list):
        """
        Called when the server received command from the session.

        :type session: SessionThread
        :param session: Client session.

        :type cmd_list: list[str]
        :param cmd_list: Command args.

        :rtype: bool
        :return: False for exit, True for continue.
        """
        assert cmd_list

        cmd = cmd_list[0]
        if cmd in self._commands:
            return self._commands[cmd].function(session, cmd_list)
        else:
            self.reply_text(session, "NG:Unknown command [%s]" % cmd)
            return True

    def print_help(self, session, command_key, usage_only=False):
        """
        Display command help from on_cmd_* pydoc.

        :type session: SessionThread
        :param session: Client session.

        :type command_key: str
        :param command_key: Command to display help.

        :type usage_only: bool
        :param usage_only: True for only display :usage:
        """
        if command_key in self._commands:
            for line in self._commands[command_key].usage_text.splitlines():
                self.reply_text(session, line.strip())
                if usage_only:
                    break
        else:
            self.reply_text(session, "NG:Unknown command:%s" % command_key)

    # TODO: NG:Too many arguments を検索して、この関数を使うようにする？
    def _too_many_arguments(self, session, cmd_list,
                            message="NG:Too many arguments"):
        """
        Print NG:Too many arguments, and help summary.

        :type session: SessionThread
        :param session: Client session.

        :type cmd_list: list[str]
        :param cmd_list: Command args.
        """
        self.reply_text(session, message)
        self.print_help(session, cmd_list[0], True)  # True for usage only

    def _find_commands(self):
        """
        Find on_cmd_* functions from this instance and create dict of function
        object and usage text.

        :rtype: dict[str, CommandHandler._Command]
        """
        result = {}

        prefix = "on_cmd_"
        prefix_len = len(prefix)
        funcs = [getattr(self, a, None) for a in dir(self)
                 if isinstance(getattr(self, a, None), types.MethodType)]
        for func in funcs:
            func_name = func.__func__.__name__
            if len(func_name) > prefix_len and func_name[:prefix_len] == prefix:
                func_name = func_name[prefix_len:]

                cmd = self._Command()
                cmd.function = func

                doc = (func.__func__.__doc__ or "").strip()
                for usage_keyword in (":usage:", ":usage", "@usage:", "@usage"):
                    usage_pos = doc.find(usage_keyword)
                    if usage_pos >= 0:
                        cmd.usage_text = doc[usage_pos + len(usage_keyword):].strip()
                        break

                if not cmd.usage_text:
                    cmd.usage_text = "%s: No usage for command." % func_name

                result[func_name] = cmd

        return result

    def on_cmd_help(self, session, cmd_list):
        """
        Print help to the requested session.

        :type session: SessionThread
        :param session: Client session.

        :type cmd_list: list[str]
        :param cmd_list: Command args.

        :usage: help [<command>...]: Display usage of all commands.
        with argument <command> shows details of the <command>
        of the <command>.
        """
        if len(cmd_list) >= 2:
            for key in cmd_list[1:]:
                self.print_help(session, key)
        else:
            for values in sorted(self._commands.items(), key=itemgetter(0)):
                self.print_help(session, values[0], True)
        return True

    def on_cmd_state(self, session, _cmd_list):
        """
        Print server and session state information.

        :type session: SessionThread
        :param session: Client session.

        :type _cmd_list: list[str]
        :param _cmd_list: Command args.

        :usage: state: Show state of server.
        """
        if session.server is not None:
            for info in session.server.get_server_info_list():
                self.reply_text(session, info)
        else:
            self.reply_text(session, "No state information.")
        return True

    def on_cmd_close(self, session, _cmd_list):
        """
        Close the session. The server will not terminate. To exit the server, use the 'exit' command.

        :type session: SessionThread
        :param session: Client session.

        :type _cmd_list: list[str]
        :param _cmd_list: Command args.

        :usage: close: Close the session. The server will not terminate. To exit the server, use the 'exit' command.
        """
        self.reply_text(session, "closing this (%s) session" % str(self))
        session.close()
        return False

    def on_cmd_exit(self, session, cmd_list):
        """
        Exit the server. To close the session, use the 'close' command.

        :type session: SessionThread
        :param session: Client session.

        :type cmd_list: list[str]
        :param cmd_list: Command args.

        :usage: exit: Exit the server. To close the session, use the 'close' command.
        """
        self.reply_text(session, "exiting thread %s" % self)
        session.close()
        self.set_exit()
        return False

    @staticmethod
    def create_stat_dict(stat_list):
        """
        :return: Converted stat list to to dict.
        """
        return dict([val.split("=", 1) for val in stat_list])

    def create_stat_list(self):
        """
        :rtype: list[str]
        :return: Stat list. The elements of the list are strings like "<key>=<value>".
        """
        return []

    def on_cmd_stat(self, session, cmd_list):
        """
        :type session: SessionThread
        :param session: Client session.

        :type cmd_list: list[str]
        :param cmd_list: Command args.

        :usage: stat [j]: Returns statistics of this process.
        j: Returns statistics as json.
        """
        json_output = False

        # Check args
        if len(cmd_list) > 1:
            if len(cmd_list) == 2 and cmd_list[1] == "j":
                json_output = True
            else:
                self.reply_text(session,
                                "NG:Unknown argument %s" % (cmd_list[1:]))
                return True

        # Create stat list
        stat_list = []
        stat_list.extend(self.create_stat_list())

        # Output
        if json_output:
            self.reply_text(session,
                            json.JSONEncoder().encode(
                                self.create_stat_dict(stat_list)))
        else:
            for stat in stat_list:
                self.reply_text(session, stat)

        return True

    def on_cmd_pwd(self, session, cmd_list):
        """
        Print current directory of this server.

        :type session: SessionThread
        :param session: Client session.

        :type cmd_list: list[str]
        :param cmd_list: Command args.

        :usage: pwd: Returns current directory
        """
        if len(cmd_list) == 1:
            self.reply_text(session, os.getcwd())
        else:
            self.reply_text(session, "NG:Too many arguments")
        return True

    def on_cmd_ls(self, session, cmd_list):
        """
        List files of server current directory.

        :type session: SessionThread
        :param session: Client session.

        :type cmd_list: list[str]
        :param cmd_list: Command args.

        :usage: ls [path]: Returns files in the server's current directory or the specified path.
        """
        current = os.getcwd()
        linesep = self.linesep
        try:
            if len(cmd_list) == 1:
                self.reply_text(session, linesep.join(os.listdir(current)))
            elif len(cmd_list) == 2:
                self.reply_text(session, linesep.join(os.listdir(
                    os.path.join(current, cmd_list[1]))))
            else:
                self.reply_text(session, "NG:Too many arguments")
        except OSError as exc:
            self.reply_text(session, "NG:Error occurred (%s)" % str(exc))
        return True


class SessionThread(threading.Thread):
    """
    A thread class creating for each client session.
    """

    def __init__(self, server, data_handler, sock, client_address,
                 max_buff=1024):
        """
        Constructor.

        :type server: CuiServer
        :param server: The server that owns this session.

        :type data_handler: DataHandler
        :param data_handler: Pass the received data to this data handler.

        :type sock: socket.socket or None
        :param sock: Client socket.

        :type client_address: str or None
        :param client_address: Client IP address.

        :type max_buff: int
        :param max_buff: maximum receive buffer for sock.recv().
        """

        super(SessionThread, self).__init__()

        self._state = sitcpy.State(sitcpy.THREAD_NOT_STARTED)

        self._server = server
        self._data_handler = data_handler
        self._sock = sock
        self._client_address = client_address
        self._max_buff = max_buff

        self._rest_byte_data = bytes()

    @property
    def state(self):
        """
        The state of the thread.

        0: THREAD_NOT_STARTED
        1: THREAD_STARTING
        2: THREAD_RUNNING
        3: THREAD_STOPPING
        4: THREAD_STOPPED

        :rtype: int
        """
        return self._state()

    @property
    def server(self):
        """
        The server that owns this session.

        :rtype: CuiServer
        """
        return self._server

    @property
    def sock(self):
        """
        The socket associated with this session.

        :rtype: socket.socket
        """
        return self._sock

    @property
    def client_address(self):
        """
        Client IP address.

        :rtype: str
        :return: Client IP address.
        """
        return self._client_address

    def start(self):
        """
        Start this thread.
        """
        super(SessionThread, self).start()
        self._state.transit(sitcpy.THREAD_STARTING)
        self._state.wait(sitcpy.THREAD_RUNNING)

    def stop(self):
        """
        Cancel the infinite loop of the session thread.
        Call this function cause the thread exiting.
        """
        self._state.transit(sitcpy.THREAD_STOPPING)

    def close(self):
        """
        Close the client session.
        """
        if self.sock is not None:
            self.sock.close()
        self._sock = None

    def run(self):
        """
        Receive the data from the designated session, and call the associated data_handler.
        """
        # pylint: disable=unused-variable
        try:
            LOGGER.debug("starting session from client %s",
                         str(self._client_address))
            self._data_handler.on_start(self)
            read_list = [self._sock]

            self._state.transit(sitcpy.THREAD_RUNNING)
            while self._state() == sitcpy.THREAD_RUNNING:
                try:
                    readable, _, _ = select.select(read_list, [], [], 0.1)
                    if self._sock in readable:

                        # Receive data.
                        byte_data = self._sock.recv(self._max_buff)
                        if not byte_data:
                            LOGGER.error("readable socket with no data. closing session")
                            break
                        byte_data = self._rest_byte_data + byte_data if self._rest_byte_data else byte_data

                        # Find delimiter position
                        delimiter_pos = self._data_handler.find_delimiter_position(byte_data)

                        if delimiter_pos >= 0:
                            # If delimiter found.
                            if not self._data_handler.on_data(self, byte_data[:delimiter_pos]):
                                break
                            self._rest_byte_data = byte_data[delimiter_pos:]
                        else:
                            # If delimiter not found.
                            self._rest_byte_data = byte_data

                    self._data_handler.on_idle(self)
                except Exception as exc:
                    LOGGER.error("Exception at SessionThread.run : %s", str(exc))
                    raise
            del read_list[:]
        finally:
            self.close()
            self._state.transit(sitcpy.THREAD_STOPPED)


class CuiServer(threading.Thread):
    """
    Server class. Listening the socket and create the SessionThread for the client.
    """

    def __init__(self, session_thread_class, data_handler, tcp_port, acceptable_host="0.0.0.0"):
        """
        Constructor.

        :param session_thread_class: SessionThread class to processing the client session.

        :type data_handler: DataHandler
        :param data_handler: A Instance of the DataHandler derived class to processing the client commands.

        :type tcp_port: int
        :param tcp_port: Listening TCP port number for this server.

        :type acceptable_host: str
        """
        super(CuiServer, self).__init__()

        self._state = sitcpy.State(sitcpy.THREAD_NOT_STARTED)
        """:type : sitcpy.State"""

        self._session_thread_class = session_thread_class
        """:type : subclass of SessionThreadClass"""
        self._data_handler = data_handler
        """:type : DataHandler"""

        self._tcp_port = tcp_port
        """:type : int"""
        self._acceptable_host = acceptable_host
        """:type : str"""

        self._server_address = None
        self._server_sock = None
        self._sessions = []  # list of created sessions.
        """:type : list[SessionThread]"""

    @property
    def state(self):
        return self._state()

    @property
    def server_address(self):
        """
        Returns tuple of server ip address and port.
        """
        return self._server_address

    def start(self):
        super(CuiServer, self).start()
        self._state.transit(sitcpy.THREAD_STARTING)
        self._state.wait(sitcpy.THREAD_RUNNING)

    def stop(self):
        """
        Exit the server listening loop.
        """
        self._state.transit(sitcpy.THREAD_STOPPING)

    def get_server_info_list(self):
        """
        Returns list of server information separated with colon.
        """
        # TODO: 不要では？特に理由がなければ削除する
        result = []
        if self._server_sock is not None:
            result.append("Sever address: %s" %
                          str(self._server_sock.getsockname()))
        else:
            result.append("Sever address: Not initialized yet.")
        result.append("Handler: %s" %
                      str(self._data_handler.__class__))
        result.append("Sessions: %d" % len(self._sessions))
        for idx, session_thread in enumerate(self._sessions):
            result.append("Session[%d]: %s" % (
                idx, str(session_thread.client_address)))
        return result

    def is_exit(self):
         # TODO: 存在意義があやしい
        """
        Returns exiting status(received exit command or not).
        """
        return self._data_handler.is_exit()

    def run(self):
        """
        Server thread processing.
        """
        # pylint: disable=unused-variable
        try:
            self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                self._server_sock.bind(
                    (self._acceptable_host, self._tcp_port))
                self._server_address = self._server_sock.getsockname()
                LOGGER.info("port:%d", self._server_address[1])
                self._server_sock.listen(10)  # argument is the number of sessions
                read_list = [self._server_sock]
            except OSError as exc:
                LOGGER.error("socket error %s @ %s %s", str(exc),
                             self._acceptable_host, self._tcp_port)
                LOGGER.debug(traceback.format_exc())
                if self._data_handler is not None:
                    self._data_handler.set_exit()
                if self._server_sock is not None:
                    self._server_sock.close()
                return

            self._data_handler.on_server_start(self)

            self._state.transit(sitcpy.THREAD_RUNNING)
            while self._state() == sitcpy.THREAD_RUNNING:
                try:
                    readable, _, _ = select.select(read_list, [], [], 0.1)
                    for read_sock in readable:
                        try:
                            client_sock, client_address = read_sock.accept()  # 接続されればデータを格納
                            LOGGER.debug("DEBUG:creating session_thread %s",
                                         self._session_thread_class)
                            session_thread = self._session_thread_class(
                                self, self._data_handler, client_sock, client_address)
                            LOGGER.debug("DEBUG:created session_thread %s",
                                         self._session_thread_class)
                            self._sessions.append(session_thread)
                            LOGGER.debug("DEBUG:starting session_thread %s",
                                         self._session_thread_class)
                            session_thread.start()
                            LOGGER.debug("DEBUG:started session_thread %s",
                                         self._session_thread_class)
                        except OSError as exc:
                            LOGGER.error("CuiSvr.run accept %s", exc)
                            read_sock.close()
                            break

                    if self.is_exit():
                        break

                    # cleanup dead(not alive session)
                    for session_thread in self._sessions:
                        if session_thread.state == sitcpy.THREAD_STOPPED:
                            self._sessions.remove(session_thread)
                            LOGGER.debug("closing session %s",
                                         str(session_thread.client_address))
                except OSError as exc:
                    print("select error, closed server session and exit CuiSvr %s %s " %
                          (str(exc), read_list))
                    break

            self._state.transit(sitcpy.THREAD_STOPPING)
            for session_thread in self._sessions:
                session_thread.stop()
                session_thread.join(10)
            self._sessions = []
            if self._server_sock is not None:  # 接続の待ち受けをします（キューの最大数を指定）
                self._server_sock.close()
        finally:
            self._state.transit(sitcpy.THREAD_STOPPED)


class CommandClient(object):
    """
    A simple client class for the CommandHandler based server.
    """

    def __init__(self, prompt, ip_address, port):
        """
        A simple command client sample that sends a command and
        waits for a reply until receiving the command prompt.

        :type prompt: str
        :type ip_address: str
        :type port: int
        """
        self._ip_address = ip_address
        self._port = int(port)
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.connect((self._ip_address, self._port))
        self._prompt = prompt
        while True:
            reply = self._receive(False)
            if reply is not None:
                if to_str(reply) == self._prompt:
                    break
            else:
                break

    def close(self):
        """
        Close the session.
        """
        self.send_command("close", no_reply=True)

    def send_command(self, command, no_reply=False):
        """
        Sends a command to the server, and returns the reply from the server.

        :type command: str
        :param command: command string to the server.

        :type no_reply: bool
        :param no_reply: If True, just sends command and returns immediately.
        """
        command += os.linesep
        self._sock.sendall(to_bytes(command))
        if not no_reply:
            reply = self._receive()
            if reply is not None:
                return to_str(reply)
        return None

    def _receive(self, strip_prompt=True):
        """
        Receive process.

        :type strip_prompt: bool
        :param strip_prompt: If True, strip the prompt string from the message.

        :rtype: bytes
        :return: the bytearray object that is replied from the server.
        """
        # pylint: disable=unused-variable
        received = None
        read_list = [self._sock]
        byte_data = bytearray()
        # retry = 0
        while True:
            try:
                readable, _, _ = select.select(read_list, [], [], 0.1)
                if self._sock in readable:
                    read_byte_data = self._sock.recv(4096)

                    if not read_byte_data:
                        break
                    pos_prompt = read_byte_data.find(to_bytes(self._prompt))
                    if pos_prompt >= 0:
                        if strip_prompt:
                            byte_data += read_byte_data[0:pos_prompt]
                        else:
                            byte_data += read_byte_data
                        received = byte_data
                        break
                    else:
                        byte_data += read_byte_data
                # else:
                #     retry += 1
                #     if retry > 3:
                #         break
            except Exception:
                raise
        del read_list[:]
        return received


def default_arg_parser():
    """
    :rtype: argparse.ArgumentParser
    :return: Default argument parser.
    """
    arg_parser = argparse.ArgumentParser(description="cui main.")
    arg_parser.add_argument("-a", "--host", type=str,
                            default="0.0.0.0", help="acceptable host")
    arg_parser.add_argument("-p", "--port", type=int,
                            default=0, help="server port number")
    arg_parser.add_argument("-s", "--source", type=open,
                            help="initial command file")
    arg_parser.add_argument("-x", "--command",
                            help="single line initial commands separated with semicolon")
    return arg_parser


def cui_main(server_class, command_handler, session_thread_class=None, args=None):
    """
    :type server_class: class
    :param server_class: Server class.

    :type command_handler: CommandHandler
    :param command_handler: CommandHandler instance.

    :type session_thread_class: class
    :param session_thread_class: SessionThread class.
    """
    session_thread_class = session_thread_class or SessionThread
    args = default_arg_parser().parse_args(args)

    init_commands = args.command
    init_file = args.source
    tcp_port = args.port
    acceptable_host = args.host

    if init_file is not None:
        file_commands = init_file.readlines()
        init_commands = init_commands + ";" + file_commands

    server = server_class(session_thread_class, command_handler, tcp_port, acceptable_host)
    server.start()

    if init_commands:
        init_commands = to_bytes(init_commands)
        command_handler.on_data(SessionThread(server, command_handler, None, None),
                                init_commands)

    try:
        while True:
            time.sleep(0.1)
            if server.is_exit():
                break
    except KeyboardInterrupt:
        command_handler.on_shutdown(server)

    server.stop()
    server.join(5)


if __name__ == "__main__":
    cui_main(CuiServer, CommandHandler("$ "))
