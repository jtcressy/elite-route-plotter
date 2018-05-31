import wx
import wx.xrc
import wx.dataview
import requests
import time
import sys
import gevent
from tabulate import tabulate
import threading
import functools
from xbox.sg.console import Console
from xbox.sg.enum import ConnectionState
from xbox.sg.manager import TextManager
from xbox.webapi.authentication.manager import AuthenticationManager
from xbox.sg.scripts import TOKENS_FILE


class PlotterApp(wx.App):
    def MainLoop(self):
        evtloop = wx.GUIEventLoop()
        old = wx.EventLoop.GetActive()
        wx.EventLoop.SetActive(evtloop)
        while self.keepGoing:
            while evtloop.Pending():
                evtloop.Dispatch()
            gevent.sleep()
            self.ProcessIdle()
        wx.EventLoop.SetActive(old)

    def OnInit(self):
        # Set application name before anything else
        self.keepGoing = True
        self.SetAppName("E:D Neutron Route Plotter")
        mainframe = PlotterFrame(None)
        self.SetTopWindow(mainframe)
        mainframe.Show()
        return 1


class PlotterFrame(wx.Frame):

    def __init__(self, parent):
        wx.Frame.__init__(self, parent, id=wx.ID_ANY, title=u"Elite Dangerous Neutron Route Plotter",
                          pos=wx.DefaultPosition, size=wx.Size(1000, 600),
                          style=wx.DEFAULT_FRAME_STYLE | wx.TAB_TRAVERSAL)
        # Attributes

        # Layout
        self.__DoLayout()

        # Events
        self.Bind(wx.EVT_MENU, self.OnQuit, self.quitItem)
        self.Bind(wx.EVT_MENU, self.OnNewRoute, self.newRouteItem)
        self.Bind(wx.EVT_CLOSE, self.OnClose)

    def __DoLayout(self):
        self.SetSizeHints(wx.Size(1000, 600), wx.DefaultSize)

        self.statusBar = self.CreateStatusBar(1, wx.STB_SIZEGRIP, wx.ID_ANY)
        self.menuBar = wx.MenuBar(0)
        self.fileMenu = wx.Menu()
        self.newRouteItem = wx.MenuItem(self.fileMenu, wx.ID_ANY, u"New Route...", u"Plot a New Route", wx.ITEM_NORMAL)
        self.fileMenu.Append(self.newRouteItem)
        self.quitItem = wx.MenuItem(self.fileMenu, wx.ID_EXIT, u"Quit", u"Quit Application", wx.ITEM_NORMAL)
        self.fileMenu.Append(self.quitItem)
        self.menuBar.Append(self.fileMenu, u"&File")
        self.SetMenuBar(self.menuBar)

        pframe_bsizer = wx.BoxSizer(wx.HORIZONTAL)
        self.route_panel = RoutePanel(self)
        self.control_panel = ControlPanel(self)
        pframe_bsizer.Add(self.route_panel, 1, wx.EXPAND | wx.ALL, 0)
        pframe_bsizer.Add(self.control_panel, 1, wx.EXPAND | wx.ALL, 5)
        self.SetSizer(pframe_bsizer)
        self.Layout()
        self.Centre(wx.BOTH)

    def OnNewRoute(self, e):
        rtDialog = NewRouteDialog(None, wx.ID_ANY)
        retcode = rtDialog.ShowModal()
        if retcode == 0:
            self.route_panel.route = Route.create(
                rtDialog.t_src.GetValue(),
                rtDialog.t_dest.GetValue(),
                rtDialog.n_range.GetValue(),
                rtDialog.n_efficiency.GetValue()
            )
        rtDialog.Destroy()

    def OnQuit(self, e):
        if self.control_panel.xbox_section.worker:
            self.control_panel.xbox_section.worker.abort()
        self.Close()

    def OnClose(self, e):
        if self.control_panel.xbox_section.worker:
            self.control_panel.xbox_section.worker.abort()
        self.Destroy()
        sys.exit(0)

    def __del__(self):
        pass


class NewRouteDialog(wx.Dialog):
    def __init__(self, parent, id):
        super(NewRouteDialog, self).__init__(parent, id, '')
        self.__DoLayout()
        self.SetSize((250,160))
        self.SetTitle("Enter New Route")
        self.route = None

    def __DoLayout(self):
        pnl = wx.Panel(self)
        self.t_src = wx.TextCtrl(pnl, value="Colonia")
        self.t_dest = wx.TextCtrl(pnl, value="Sagittarius A*")
        self.n_range = wx.SpinCtrl(pnl, value="55")
        self.n_efficiency = wx.SpinCtrl(pnl, value='60')
        self.n_efficiency.SetRange(0, 100)
        vbox = wx.BoxSizer(wx.VERTICAL)

        sizer = wx.FlexGridSizer(5, 2, 5, 5)
        sizer.AddMany([
            (wx.StaticText(pnl, label="Source System"), 0, wx.EXPAND),
            (self.t_src, 1, wx.EXPAND),
            (wx.StaticText(pnl, label="Destination System"), 0, wx.EXPAND),
            (self.t_dest, 1, wx.EXPAND),
            (wx.StaticText(pnl, label="Jump Range (LY)"), 0, wx.EXPAND),
            (self.n_range, 1, wx.EXPAND),
            (wx.StaticText(pnl, label="Efficiency (%)"), 0, wx.EXPAND),
            (self.n_efficiency, 1, wx.EXPAND)
        ])

        pnl.SetSizer(sizer)

        okButton = wx.Button(self, label='Create')
        closeButton = wx.Button(self, label='Cancel')
        sizer.Add(okButton, 0, wx.ALIGN_RIGHT, border=5)
        sizer.Add(closeButton, 1, wx.ALIGN_LEFT, border=5)

        vbox.Add(pnl, proportion=1,
                 flag=wx.ALL | wx.EXPAND, border=5)

        self.SetSizer(vbox)

        okButton.Bind(wx.EVT_BUTTON, self.OnRouteCreate)
        closeButton.Bind(wx.EVT_BUTTON, self.OnClose)

    def OnRouteCreate(self, e):
        self.EndModal(0)

    def OnClose(self, e):
        self.EndModal(1)


class RoutePanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, 0)

        # Attributes
        self._route = None

        # Layout
        self.__DoLayout()

        # Events
        self.Bind(wx.dataview.EVT_DATAVIEW_ITEM_VALUE_CHANGED, self.onValueChange)

    def get_next_system(self):
        route = self._route
        next_system = [system for system in route.waypoints if not system.visited][0]
        return route.waypoints.index(next_system), next_system

    def mark_visited(self, i):
        """Mark a waypoint as visited based on its index"""
        route = self.route
        try:
            route.waypoints[i].visited = True
        except IndexError:
            self.GetParent().statusBar.StatusText = f"No waypoint by index {i}"
        except AttributeError:
            self.GetParent().statusBar.StatusText = f"No route defined!"
        self.route = route

    @property
    def route(self):
        return self._route

    @route.setter
    def route(self, value):
        self._route = value
        # update routeListView
        self.routeListView.DeleteAllItems()
        for w in self._route.waypoints:
            item = (
                    w.visited,
                    w.name,
                    "{:.2f}".format(w.distance_jumped),
                    "{:.2f}".format(w.distance_left),
                    str(w.jumps)
                )
            self.routeListView.AppendItem(item)

    def __DoLayout(self):
        vbs = wx.BoxSizer(wx.VERTICAL)
        self.routeListView = wx.dataview.DataViewListCtrl(self, wx.ID_ANY, wx.DefaultPosition,
                                                          wx.DefaultSize,
                                                          wx.dataview.DV_HORIZ_RULES | wx.dataview.DV_ROW_LINES | wx.dataview.DV_VERT_RULES)
        self.visitedCol = self.routeListView.AppendToggleColumn("Visited", width=50, align=wx.ALIGN_CENTER)
        self.sysNameCol = self.routeListView.AppendTextColumn("System Name", width=180)
        self.distCol = self.routeListView.AppendTextColumn("Distance (LY)", width=100, align=wx.ALIGN_RIGHT)
        self.remainCol = self.routeListView.AppendTextColumn("Remaining (LY)", width=100, align=wx.ALIGN_RIGHT)
        self.jumpsCol = self.routeListView.AppendTextColumn("Jumps", width=50, align=wx.ALIGN_CENTER)
        vbs.Add(self.routeListView, 1, wx.ALL | wx.EXPAND, 5)

        self.SetSizer(vbs)
        self.Layout()
        vbs.Fit(self)

    def onValueChange(self, e):
        selectedrow = e.EventObject.SelectedRow
        eobj: wx.dataview.DataViewListCtrl = e.EventObject
        val = eobj.GetValue(selectedrow, 0)
        route = self.route
        try:
            route.waypoints[selectedrow].visited = val
        except Exception as e:
            print(e)
            pass
        self.route = route


class XboxSection(wx.StaticBoxSizer):
    def __init__(self, parent):
        wx.StaticBoxSizer.__init__(self, wx.StaticBox(parent, wx.ID_ANY, "XBOX Connection"), wx.VERTICAL)

        # Attributes
        self.worker: XboxThread = None
        self.discovered = []

        # Layout
        self.__DoLayout()

        # Events
        self.GetStaticBox().Bind(wx.EVT_BUTTON, self.onConnectBtn, self.xbox_connect_btn)
        self.GetStaticBox().Bind(wx.EVT_BUTTON, self.onAuthBtn, self.xbox_auth_btn)
        EVT_RESULT(self.GetStaticBox(), self.onResult)
        EVT_XBOX_TEXT_PROMPT(self.GetStaticBox(), self.onTextPrompt)

    def __DoLayout(self):
        gsizer = wx.GridSizer(2,2,0,0)
        self.xbox_ip_label = wx.StaticText(self.GetStaticBox(), wx.ID_ANY, "XBOX IP Address",
                                           wx.DefaultPosition, wx.DefaultSize, 0)
        self.xbox_ip_label.Wrap(-1)
        gsizer.Add(self.xbox_ip_label, 0, wx.ALIGN_RIGHT | wx.ALL, 5)

        self.xbox_ip_address = wx.TextCtrl(self.GetStaticBox(), wx.ID_ANY, "192.168.0.25",
                                           wx.DefaultPosition, wx.DefaultSize, 0)
        gsizer.Add(self.xbox_ip_address, 1, wx.ALIGN_RIGHT | wx.ALL | wx.EXPAND, 5)

        self.xbox_status_label = wx.StaticText(self.GetStaticBox(), wx.ID_ANY, "Status:",
                                               wx.DefaultPosition, wx.DefaultSize, 0)
        self.xbox_status_label.Wrap(-1)
        gsizer.Add(self.xbox_status_label, 0, wx.ALIGN_RIGHT | wx.ALL, 5)

        self.xbox_status = wx.StaticText(self.GetStaticBox(), wx.ID_ANY, "Disconnected",
                                         wx.DefaultPosition, wx.DefaultSize, 0)
        self.xbox_status.Wrap(-1)
        gsizer.Add(self.xbox_status, 0, wx.ALL, 5)

        self.Add(gsizer, 1, wx.EXPAND, 5)
        self.xbox_connect_btn = wx.Button(self.GetStaticBox(), wx.ID_ANY, u"Connect",
                                          wx.Point(-1, -1), wx.DefaultSize, 0)
        self.xbox_auth_btn = wx.Button(self.GetStaticBox(), wx.ID_ANY, "Auth", wx.Point(-1, -1), wx.DefaultSize, 0)
        self.Add(self.xbox_connect_btn, 0, wx.ALIGN_RIGHT | wx.ALL | wx.EXPAND, 5)
        self.Add(self.xbox_auth_btn, 0, wx.ALIGN_RIGHT | wx.ALL | wx.EXPAND, 5)

    def discover(self, addr=None):
        discovered = Console.discover(addr=addr, timeout=10)
        self.discovered = discovered

    def on_text(self, console, payload):
        print(console, payload, "ITS THE FUCKING SHIT YO")

    def onResult(self, e):
        self.xbox_status.Label = "Disconnected"
        self.xbox_connect_btn.Label = "Connect"

    def onConnect(self, e):
        self.xbox_status.Label = "Connected"
        self.xbox_connect_btn.Label = "Disconnect"

    def onTextPrompt(self, e):
        print("Old Text:", e)
        index, next_system = self.GetStaticBox().GetParent().GetParent().route_panel.get_next_system()
        self.worker.send_text(str(next_system.name))
        self.GetStaticBox().GetParent().GetParent().route_panel.mark_visited(int(index))

    def onConnectBtn(self, e):
        e.EventObject.Label = "Connecting..."
        auth_mgr = AuthenticationManager.from_file(TOKENS_FILE)
        auth_mgr.authenticate()
        auth_mgr.dump(TOKENS_FILE)
        userhash = auth_mgr.userinfo.userhash
        token = auth_mgr.xsts_token.jwt
        # TODO: make a drop-down list of discovered xboxes
        if self.worker is None:
            self.discover(self.xbox_ip_address.GetValue())
            if len(self.discovered):
                c = self.discovered[0]
                self.worker = XboxThread(
                    self.GetStaticBox(),
                    c.address,
                    c.name,
                    c.uuid,
                    c.liveid,
                    c.protocol.crypto,
                    userhash,
                    token
                )
            else:
                print("Discover a console first")
        else:  # Kill worker if it's alive
            self.worker.abort()
            self.worker = None


    def onAuthBtn(self, e):
        ""  # Start a thread to authenticate with the xbox


class RouteDetailSection(wx.StaticBoxSizer):
    def __init__(self, parent):
        wx.StaticBoxSizer.__init__(self, wx.StaticBox(parent, wx.ID_ANY, "Route Details"), wx.VERTICAL)

        # Attributes

        # Layout
        self.__DoLayout()

        # Events

    def __DoLayout(self):
        "" # Empty for now, use a property pane


class RouteControlSection(wx.StaticBoxSizer):
    def __init__(self, parent):
        wx.StaticBoxSizer.__init__(self, wx.StaticBox(parent, wx.ID_ANY, "Route Controls"), wx.VERTICAL)

        # Attributes

        # Layout
        self.__DoLayout()

        # Events
        self.GetStaticBox().Bind(wx.EVT_BUTTON, self.onPlayPauseBtn, self.playpausebtn)

    def __DoLayout(self):
        self.playpausebtn = wx.Button(self.GetStaticBox(), wx.ID_ANY, "Pause")
        self.Add(self.playpausebtn, 0, wx.ALIGN_RIGHT | wx.ALL | wx.EXPAND, 5)

    def onPlayPauseBtn(self, e):
        route = self.GetStaticBox().GetParent().GetParent().route_panel.route
        if route is not None:
            route.paused = not route.paused
            if route.paused:
                e.EventObject.Label = "Resume"
            else:
                e.EventObject.Label = "Pause"
            self.GetStaticBox().GetParent().GetParent().route_panel.route = route


class ControlPanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.TAB_TRAVERSAL)

        # Attributes

        # Layout
        self.__DoLayout()

        # Events

    def __DoLayout(self):
        vbs = wx.BoxSizer(wx.VERTICAL)
        self.xbox_section = XboxSection(self)
        self.route_detail_section = RouteDetailSection(self)
        self.route_control_section = RouteControlSection(self)
        vbs.Add(self.xbox_section, 0, wx.EXPAND, 5)
        vbs.Add(self.route_detail_section, 1, wx.EXPAND, 5)
        vbs.Add(self.route_control_section, 1, wx.EXPAND, 5)
        self.SetSizer(vbs)
        self.Layout()
        vbs.Fit(self)


# --------------------------------- #
#    Data Classes
# --------------------------------- #


class StarSystem:
    def __init__(self, name, x, y, z, is_neutron=False):
        self.name = name
        self.x = x
        self.y = y
        self.z = z
        self.is_neutron = is_neutron


class RouteWaypoint(StarSystem):
    def __init__(self, w):
        super().__init__(
            w['system'],
            w['x'], w['y'], w['z'],
            bool(w['neutron_star'])
        )
        self.distance_jumped = w['distance_jumped']
        self.distance_left = w['distance_left']
        self.jumps = w['jumps']
        self.visited = False


class Route:
    def __init__(self, waypoints: list, src, dest, eff, jump_range, distance, total_jumps, via):
        self.waypoints = waypoints
        self.total_jumps = total_jumps
        self.via = via
        self.src = src
        self.dest = dest
        self.eff = eff
        self.jump_range = jump_range
        self.distance = distance
        self.paused = False  # Used by the pause button to halt the queue of system names

    def __str__(self):
        output = "Route Summary\n\n"
        output += tabulate(
            [
                [
                    self.src.title(),
                    self.dest.title(),
                    self.distance,
                    self.total_jumps
                ]
            ],
            ["Source System", "Destination System", "Total Distance (LY)", "Total Jumps"]
        )
        output += "\n\n"
        output += tabulate(
            [
                [w.name, w.distance_jumped, w.distance_left, w.jumps]
                for w in self.waypoints
            ],
            ["System Name", "Distance (LY)", "Remaining(LY)", "Jumps"]
        )
        output += "\n"
        return output

    @staticmethod
    def create(src, dest, jump_range, eff='60', timeout=10):
        """Create a Route() from source (src) to destination (dest) with a jump range of (jump_range) """
        request_url = f"https://spansh.co.uk/api/route?efficiency={eff}&from={src}&to={dest}&range={jump_range}"
        result = requests.post(request_url).json()
        job_id = result['job']
        elapsed = 0
        while True:
            response_url = f"https://spansh.co.uk/api/results/{job_id}"
            response = requests.get(response_url).json()
            if response['status'] == 'ok':
                new_route = Route(
                    [RouteWaypoint(w) for w in response['result']['system_jumps']],
                    response['result']['source_system'],
                    response['result']['destination_system'],
                    response['result']['efficiency'],
                    response['result']['range'],
                    response['result']['distance'],
                    response['result']['total_jumps'],
                    response['result']['via']
                )
                return new_route
            time.sleep(1)
            elapsed += 1
            if elapsed >= timeout:
                raise TimeoutError(f"Route job exceeded timeout of {timeout}s")

# ---------------------- #
#      Worker Threads    #
# ---------------------- #


EVT_RESULT_ID = wx.NewId()
EVT_XBOX_TEXT_PROMPT_ID = wx.NewId()


def EVT_RESULT(win, func):
    """Define Result Event."""
    win.Connect(-1, -1, EVT_RESULT_ID, func)


def EVT_XBOX_TEXT_PROMPT(win, func):
    win.Connect(-1, -1, EVT_XBOX_TEXT_PROMPT_ID, func)


class ResultEvent(wx.PyEvent):
    """Simple event to carry arbitrary result data."""
    def __init__(self, data):
        """Init Result Event."""
        wx.PyEvent.__init__(self)
        self.SetEventType(EVT_RESULT_ID)
        self.data = data


class TextPromptEvent(wx.PyEvent):
    def __init__(self, data):
        wx.PyEvent.__init__(self)
        self.SetEventType(EVT_XBOX_TEXT_PROMPT_ID)
        self.data = data


def on_input(win, payload):
    """Called when the xbox opens the virtual keyboard"""
    print("got input event")
    wx.PostEvent(win, TextPromptEvent(payload))


# Thread class that executes processing
class XboxThread(threading.Thread):
    """Xbox Worker Thread"""
    def __init__(self, notify_window, addr, name, uuid, liveid, crypto, userhash, token):
        """Init Worker Thread Class."""
        threading.Thread.__init__(self)
        self._notify_window = notify_window
        self.addr = addr
        self.name = name
        self.uuid = uuid
        self.liveid = liveid
        self.crypto = crypto
        self.userhash = userhash
        self.token = token
        self._console = None
        self.daemon = True
        self.start()

    def run(self):
        """Run Worker Thread."""
        print("started worker")
        # Re-instantiate console in-thread to prevent gevent fuckery
        self._console = Console(self.addr, self.name, self.uuid, self.liveid)
        self._console.protocol.crypto = self.crypto
        # make a callback for on_system_input

        def on_text(console, payload):
            wx.PostEvent(self._notify_window, TextPromptEvent(payload))

        print("reached connect")
        self._console.add_manager(TextManager)
        self._console.text.on_systemtext_input += functools.partial(on_text, self._console)
        status = self._console.connect(self.userhash, self.token)
        self._console.wait(1)
        if status == ConnectionState.Connected:
            self._notify_window.GetParent().GetParent().SetStatusText("Connected")
            wx.PostEvent(self._notify_window, ResultEvent("Connected"))
            print("Connected")
            self._console.protocol.serve_forever()
        else:
            self._notify_window.GetParent().GetParent().SetStatusText("Connection Failed")
        self._notify_window.GetParent().GetParent().SetStatusText("Disconnected")
        print("Disconnected")
        wx.PostEvent(self._notify_window, ResultEvent("Disconnected"))

    def abort(self):
        """abort worker thread."""
        # Method for use by main thread to signal an abort
        if self._console:
            self._console.protocol.stop()
            self.join()

    def send_text(self, text):
        self._console.send_systemtext_input(text)
        self._console.finish_text_input()

# ---------------------------------------------------------------- #


if __name__ == "__main__":
    APP = PlotterApp()
    APP.MainLoop()
