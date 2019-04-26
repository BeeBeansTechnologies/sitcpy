# -*- coding:utf-8 -*-
"""
SiTCP python library

Copyright (c) 2018, Bee Beans Technologies Co.,Ltd.
"""
__version__ = '0.1.1'


import sys
import threading
import time


PY2 = sys.version_info[0] == 2
PY3 = sys.version_info[0] == 3

PY26 = PY2 and sys.version_info[1] == 6
PY27 = PY2 and sys.version_info[1] == 7


if PY2:
    import Queue as queue
else:
    import queue


Queue = queue.Queue  # pylint: disable=invalid-name
Empty = queue.Empty  # pylint: disable=invalid-name
Full = queue.Full  # pylint: disable=invalid-name


THREAD_NOT_STARTED = 0
THREAD_STARTING = 1
THREAD_RUNNING = 2
THREAD_STOPPING = 3
THREAD_STOPPED = 4


class State(object):
    """
    This class has an integer value representing the state value.
    The state value can only transition in the forward direction.
    """

    def __init__(self, initial_state=0):
        self._cond = threading.Condition()
        self._state = initial_state

    def __call__(self):
        return self._state

    @property
    def state(self):
        return self._state

    def transit(self, new_state):
        """
        Performs state transitions.
        It returns True if the state value changes in the forward direction.
        If you try to set a value below the current state value, do not do anything.

        :type: new_state: int
        :param: new_state: New state value.

        :rtype: bool
        :return: returns True if the state value changes in the forward direction.
        """
        with self._cond:
            if new_state > self._state:
                self._state = new_state
                self._cond.notify_all()
                return True
            return False

    def wait(self, state, timeout=None):
        """
        Wait for the condition.
        Returns True if the condition is satisfied, False if it times out.
        If it transits beyond the specified state, it returns True.

        :type state: int
        :param state: State value.

        :type timeout: float or None
        :param timeout: Timeout seconds. If it is None, timeout does not occur.

        :rtype: bool
        :return: Returns True if the condition is satisfied, False if it times out.
        """
        with self._cond:
            end = time.time() + (timeout or 0)
            while True:
                if self._state >= state:
                    return True
                if timeout is None:
                    self._cond.wait()
                else:
                    now = time.time()
                    if now > end:
                        return False  # timeout
                    self._cond.wait(end - now)


# noinspection PyUnresolvedReferences
def is_unicode(val):
    """
    If the value is a unicode string, it returns True.
    """
    if PY2:
        return isinstance(val, unicode)
    else:
        return isinstance(val, str)


def is_int(val):
    """
    If the value is a int, it returns True.
    """
    if PY2:
        return isinstance(val, (int, long))
    else:
        return isinstance(val, int)


# noinspection PyUnresolvedReferences
def to_str(val, encoding="utf-8"):
    """
    Converts a value from str or bytes or bytearray to str.

    :type val: str or bytes or bytearray
    :type encoding: str
    :rtype: str
    """
    if isinstance(val, str):
        return val

    if PY2:
        if isinstance(val, bytearray):
            return str(val)
        if isinstance(val, unicode):
            return val.encode(encoding)
    else:
        if isinstance(val, (bytes, bytearray)):
            return val.decode(encoding)

    raise ValueError("Invalid value: %s" % type(val))


def to_bytes(val, encoding="utf-8"):
    """
    Converts a value from str to bytes.

    :type val: str or bytes or bytearray
    :type encoding: str
    :rtype: bytes
    """
    if isinstance(val, bytes):
        return val

    if PY2:
        return to_str(val, encoding)
    else:
        if isinstance(val, bytearray):
            return bytes(val)
        if isinstance(val, str):
            return val.encode(encoding)

    raise ValueError("Invalid value: %s" % type(val))


# noinspection PyUnresolvedReferences
def to_bytearray(val, encoding="utf-8"):
    """
    Converts a value from str or bytes or bytearray to bytearray.

    :type val: str or bytes or bytearray
    :type encoding: str
    :rtype: bytearray
    """
    if isinstance(val, bytearray):
        return val

    if isinstance(val, bytes):
        return bytearray(val)
    if isinstance(val, str):
        return bytearray(val.encode(encoding))
    if PY2 and isinstance(val, unicode):
        return bytearray(val.encode(encoding))

    raise ValueError("Invalid value: %s" % type(val))


def total_seconds(val):
    """
    This is an alternative to the total_seconds method for python2.6.

    :type val: datetime.timedelta
    :param val: Instance of timedelta
    """
    return (
        (val.days * 86400 + val.seconds) * 10**6 + val.microseconds
    ) * 0.1**6
