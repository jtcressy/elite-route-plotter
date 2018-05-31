from multiprocessing import Process, Queue, JoinableQueue, cpu_count, current_process, freeze_support
import multiprocessing as mp
from gevent import Greenlet
import gevent
import time
from xbox.sg.console import Console
from xbox.sg.crypto import Crypto
from xbox.sg.enum import ConnectionState, ServiceChannel
from xbox.sg.manager import TextManager
from xbox.webapi.authentication.manager import AuthenticationManager
from xbox.sg.scripts import TOKENS_FILE
import xbox.sg.factory
import xbox.sg.protocol

# import logging
# logging.basicConfig(level=logging.DEBUG)

# --------------------- #
# WX EVENT DECLARATIONS #
# --------------------- #

import wx

EVT_XBOX_CONNECT_ID = wx.NewId()
EVT_XBOX_DISCONNECT_ID = wx.NewId()
EVT_XBOX_SYSTEMTEXT_INPUT_ID = wx.NewId()
EVT_XBOX_DISCOVERED_CONSOLE_ID = wx.NewId()
EVT_XBOX_DISCOVERYFAILURE_ID = wx.NewId()

def EVT_XBOX_CONNECT(win, func):
    win.Connect(-1, -1, EVT_XBOX_CONNECT_ID, func)


def EVT_XBOX_DISCONNECT(win, func):
    win.Connect(-1, -1, EVT_XBOX_DISCONNECT_ID, func)


def EVT_XBOX_SYSTEMTEXT_INPUT(win, func):
    win.Connect(-1, -1, EVT_XBOX_SYSTEMTEXT_INPUT_ID, func)


def EVT_XBOX_DISCOVERED_CONSOLE(win, func):
    win.Connect(-1, -1, EVT_XBOX_DISCOVERED_CONSOLE_ID, func)

def EVT_XBOX_DISCOVERYFAILURE(win, func):
    win.Connect(-1, -1, EVT_XBOX_DISCOVERYFAILURE_ID, func)


class XboxConnectEvent(wx.PyEvent):
    def __init__(self, data):
        wx.PyEvent.__init__(self)
        self.SetEventType(EVT_XBOX_CONNECT_ID)
        self.data = data

class XboxDisconnectEvent(wx.PyEvent):
    def __init__(self, data):
        wx.PyEvent.__init__(self)
        self.SetEventType(EVT_XBOX_DISCONNECT_ID)
        self.data = data

class XboxSystemTextInputEvent(wx.PyEvent):
    def __init__(self, data):
        wx.PyEvent.__init__(self)
        self.SetEventType(EVT_XBOX_SYSTEMTEXT_INPUT_ID)
        self.data = data

class XboxDiscoveredConsoleEvent(wx.PyEvent):
    def __init__(self, data):
        wx.PyEvent.__init__(self)
        self.SetEventType(EVT_XBOX_DISCOVERED_CONSOLE_ID)
        self.data = data

class XboxDiscoveryFailureEvent(wx.PyEvent):
    def __init__(self, data):
        wx.PyEvent.__init__(self)
        self.SetEventType(EVT_XBOX_DISCOVERYFAILURE_ID)
        self.data = data

WX_EVENT_TYPES = {
    EVT_XBOX_CONNECT_ID: XboxConnectEvent,
    EVT_XBOX_DISCONNECT_ID: XboxDisconnectEvent,
    EVT_XBOX_DISCOVERED_CONSOLE_ID: XboxDiscoveredConsoleEvent,
    EVT_XBOX_SYSTEMTEXT_INPUT_ID: XboxSystemTextInputEvent,
    EVT_XBOX_DISCOVERYFAILURE_ID: XboxDiscoveryFailureEvent,
}

class XboxEvent:
    def __init__(self, id, payload):
        self.id = id
        self.payload = payload

# ------------------------- #
# End WX EVENT DECLARATIONS #
# ------------------------- #

POISON_PILL = "STOP"

class ConnectionRequest:
    def __init__(self, console):
        self.console_dict = console.to_dict()

class DiscoverRequest:
    def __init__(self, addr, timeout=10):
        self.addr = addr
        self.timeout = timeout

class DiscoveredConsole(ConnectionRequest):
    pass

class DisconnectRequest:  # This is our poison pill for the connection
    pass

class ConnectionEvent:
    def __init__(self, payload):
        self.payload = payload

    def __str__(self):
        return str(self.payload)

class SystemTextSend:
    def __init__(self, text):
        self.text = text

    def __str__(self):
        return self.text

class SystemTextInput:
    def __init__(self, text, result):
        self.text = text
        self.result = result

    def __str__(self):
        return self.text



class SmartglassProcessor(Process):
    def __init__(self, input_queue, result_queue, idx, **kwargs):
        super(SmartglassProcessor, self).__init__()
        self.inq: JoinableQueue = input_queue
        self.outq: Queue = result_queue
        self.idx = idx
        self.kwargs = kwargs
        self._console: Console = None
        self._stay_connected = mp.Event()
        self._timedout = mp.Event()

    @property
    def stay_connected(self):
        return self._stay_connected.is_set()

    @stay_connected.setter
    def stay_connected(self, value: bool):
        if value:
            self._stay_connected.set()
        if not value:
            self._stay_connected.clear()

    def run(self):
        def on_text(payload):
            self.outq.put(XboxEvent(EVT_XBOX_SYSTEMTEXT_INPUT_ID, payload))

        def on_connect_request(req: ConnectionRequest):
            auth_mgr = AuthenticationManager.from_file(TOKENS_FILE)
            auth_mgr.dump(TOKENS_FILE)
            userhash = auth_mgr.userinfo.userhash
            token = auth_mgr.xsts_token.jwt
            for c in Console.discovered():
                if str(c.uuid) == str(req.console_dict['uuid']):
                    self._console = c
            if self._console is None:
                self.outq.put(XboxEvent(EVT_XBOX_DISCONNECT_ID, "Failed to connect"))
                return
            self._console.add_manager(TextManager)
            self._console.text.on_systemtext_input += on_text
            self._console.protocol.on_timeout += lambda: self._timedout.set()
            try:
                status = self._console.connect(userhash, token)
            except OSError as e:
                self.outq.put(XboxEvent(EVT_XBOX_DISCONNECT_ID, f"Failed to connect {e}"))
                return
            self._console.wait(1)
            self.outq.put(XboxEvent(EVT_XBOX_CONNECT_ID, self._console.address))

        def mainloop(skip_connection=False):
            while True:
                if skip_connection:
                    new_item = None
                    try:
                        new_item = self.inq.get_nowait()
                    except:
                        pass
                    if new_item is not None:
                        if isinstance(new_item, DiscoverRequest):
                            try:
                                discovered = Console.discover(addr=new_item.addr)
                            except OSError as e:
                                self.outq.put(XboxEvent(EVT_XBOX_DISCOVERYFAILURE_ID, e))
                            for console in discovered:
                                dc = DiscoveredConsole(
                                    console
                                )
                                self.outq.put(XboxEvent(EVT_XBOX_DISCOVERED_CONSOLE_ID, dc))
                            if len(discovered) < 1:
                                try:
                                    Console.__protocol__.start()
                                    Console.__protocol__._discover(xbox.sg.factory.discovery(), xbox.sg.protocol.BROADCAST, 5)
                                except OSError as e:
                                    self.outq.put(XboxEvent(EVT_XBOX_DISCOVERYFAILURE_ID, e))
                            self.inq.task_done()
                        if isinstance(new_item, ConnectionRequest) or isinstance(new_item, DiscoveredConsole):
                            on_connect_request(new_item)  # this instantiates self._console
                            self.inq.task_done()
                        if isinstance(new_item, SystemTextSend):
                            self._console.send_systemtext_input(new_item.text)
                            self._console.finish_text_input()
                            self.outq.put(f"Sent {new_item.text} to console")
                            self.inq.task_done()
                        if isinstance(new_item, DisconnectRequest):
                            if self._console:
                                if self._console.connected:
                                    self._console.protocol._stop_event.set()
                                    self._console.disconnect()
                                    self.inq.task_done()
                                    self.outq.put(
                                        XboxEvent(EVT_XBOX_DISCONNECT_ID, self._console.address if self._console else None))
                                else:
                                    self.inq.task_done()
                                    self.outq.put(
                                        XboxEvent(EVT_XBOX_DISCONNECT_ID, self._console.address if self._console else None))
                            else:
                                self.inq.task_done()
                                self.outq.put(XboxEvent(EVT_XBOX_DISCONNECT_ID, self._console.address if self._console else None))
                        if new_item == POISON_PILL:
                            if self._console:
                                if self._console.connected:
                                    self._console.disconnect()
                                    self._console = None
                            self.inq.put("STOP")
                            self.inq.task_done()
                            break
                    gevent.sleep(0)

                if self._console:
                    if self._console.connected:
                        # print("console instantiated. started:", self._console.protocol.started)
                        # print("console status:", self._console.connection_state)
                        # print("Closed?:", self._console.protocol.closed)
                        # print("Timedout?:", self._timedout.is_set())
                        try:
                            ""
                            gevent.sleep(self._console.protocol.HEARTBEAT_INTERVAL)
                            self._console.protocol.ack([], [], ServiceChannel.Core, need_ack=True)
                        except OSError as e:
                            self._console.protocol.on_timeout()
                            self.outq.put(XboxEvent(EVT_XBOX_DISCONNECT_ID, f"Failed to connect {e}"))
                        finally:
                            if self._stay_connected.is_set() and self._timedout.is_set():
                                gevent.sleep(10)
                                on_connect_request(ConnectionRequest(self._console))
                gevent.sleep(0.1)
        event_thread = Greenlet.spawn(mainloop, True)
        event_thread.start()
        event_thread.join()
