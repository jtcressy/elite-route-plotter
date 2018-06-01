import elite_route_plotter as erp
import elite_route_plotter.xbox_smartglass as xbs
import wx
import wx.xrc
import wx.dataview
import wx.grid
import gevent
import sys
import multiprocessing as mp
import time


class PlotterApp(wx.App):
    def XboxLoop(self):
        while self.keepGoing:
            while not self.result_queue.empty():
                try:
                    result = self.result_queue.get_nowait()
                except mp.queues.Empty:
                    pass
                else:
                    if isinstance(result, xbs.XboxEvent):
                        wx.PostEvent(self.mainframe, xbs.WX_EVENT_TYPES[result.id](result.payload))
                        BEGIN = time.time()
            gevent.sleep()

    def MainLoop(self):
        evtloop = wx.GUIEventLoop()
        old = wx.EventLoop.GetActive()
        wx.EventLoop.SetActive(evtloop)
        while self.keepGoing:
            while evtloop.Pending():
                evtloop.DispatchTimeout(0.01)
                gevent.sleep()
            gevent.sleep()
        wx.EventLoop.SetActive(old)

    def OnInit(self):
        self.task_queue: mp.JoinableQueue = mp.JoinableQueue()
        self.result_queue: mp.Queue = mp.Queue()
        self.xbox_process = xbs.SmartglassProcessor(self.task_queue, self.result_queue, 0)
        self.mainframe = PlotterFrame(None)
        self.keepGoing = True
        self.SetAppDisplayName(erp.APPLICATION_NAME)
        self.SetAppName(erp.APPLICATION_NAME)
        self.SetTopWindow(self.mainframe)
        self.mainframe.Show()
        self.xbox_process.start()
        return 1


class PlotterFrame(wx.Frame):
    def __init__(self, parent):
        wx.Frame.__init__(self, parent, id=wx.ID_ANY, title=erp.APPLICATION_NAME,
                          pos=wx.DefaultPosition, size=wx.Size(925, 640),
                          style=wx.DEFAULT_FRAME_STYLE | wx.TAB_TRAVERSAL)
        # Attributes

        # Layout
        self.__DoLayout()

        # Events
        self.Bind(wx.EVT_MENU, self.OnQuit, self.quitItem)
        self.Bind(wx.EVT_MENU, self.OnNewRoute, self.newRouteItem)
        self.Bind(wx.EVT_CLOSE, self.OnClose)

    def __DoLayout(self):
        self.SetSizeHints(wx.Size(925, 640), wx.DefaultSize)

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
        pframe_bsizer.Add(self.control_panel, 1, wx.ALL, 5)
        self.SetSizer(pframe_bsizer)
        self.Layout()
        self.Centre(wx.BOTH)

    def OnNewRoute(self, e):
        rtDialog = NewRouteDialog(None, wx.ID_ANY)
        retcode = rtDialog.ShowModal()
        if retcode == 0:
            self.route_panel.route = erp.Route.create(
                rtDialog.t_src.GetValue(),
                rtDialog.t_dest.GetValue(),
                rtDialog.n_range.GetValue(),
                rtDialog.n_efficiency.GetValue()
            )
        rtDialog.Destroy()

    def OnQuit(self, e):
        erp.GUI_APP.task_queue.put(xbs.POISON_PILL)
        erp.GUI_APP.xbox_process.join()
        self.Close()

    def OnClose(self, e):
        erp.GUI_APP.task_queue.put(xbs.POISON_PILL)
        erp.GUI_APP.xbox_process.join()
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
        window = self.GetContainingSizer().GetContainingWindow()
        if window:
            window.control_panel.route_detail_section.update_route_details()
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
        vbs.Add(self.routeListView, 1, wx.ALL | wx.EXPAND, 1)

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
        # self.worker: XboxThread = None
        self._discovered = []

        # Layout
        self.__DoLayout()

        # Events
        self.GetStaticBox().Bind(wx.EVT_BUTTON, self.onConnectBtn, self.xbox_connect_btn)
        self.GetStaticBox().Bind(wx.EVT_BUTTON, self.onAuthBtn, self.xbox_auth_btn)
        self.GetStaticBox().Bind(wx.EVT_BUTTON, self.OnDiscoverBtn, self.discover_btn)
        self.GetStaticBox().Bind(wx.EVT_CHOICE, self.OnConsoleSelected, self.xbox_console_list)
        xbs.EVT_XBOX_CONNECT(parent.GetParent(), self.OnConsoleConnected)
        xbs.EVT_XBOX_DISCONNECT(parent.GetParent(), self.OnConsoleDisconnected)
        xbs.EVT_XBOX_SYSTEMTEXT_INPUT(parent.GetParent(), self.OnSystemTextInput)
        xbs.EVT_XBOX_DISCOVERED_CONSOLE(parent.GetParent(), self.OnDiscoveredConsole)
        xbs.EVT_XBOX_DISCOVERYFAILURE(parent.GetParent(), self.OnDiscoveryFailure)
        # EVT_RESULT(self.GetStaticBox(), self.onResult)
        # EVT_XBOX_TEXT_PROMPT(self.GetStaticBox(), self.onTextPrompt)

    def __DoLayout(self):
        sizer1 = wx.BoxSizer(wx.HORIZONTAL)
        sizer2 = wx.BoxSizer(wx.HORIZONTAL)
        sizer3 = wx.BoxSizer(wx.HORIZONTAL)
        self.xbox_console_list = wx.Choice(self.GetStaticBox(), wx.ID_ANY, name="Discovered Consoles")
        self.discover_btn = wx.Button(self.GetStaticBox(), wx.ID_ANY, "Scan")
        self.xbox_connect_btn = wx.Button(self.GetStaticBox(), wx.ID_ANY, u"Connect",
                                          wx.Point(-1, -1), wx.DefaultSize, 0)
        self.xbox_auth_btn = wx.Button(self.GetStaticBox(), wx.ID_ANY, "Auth", wx.Point(-1, -1), wx.DefaultSize, 0)

        self.xbox_status_label = wx.StaticText(self.GetStaticBox(), wx.ID_ANY, "Status:",
                                               wx.DefaultPosition, wx.DefaultSize, 0)
        self.xbox_status_label.Wrap(-1)

        self.xbox_status = wx.StaticText(self.GetStaticBox(), wx.ID_ANY, "Disconnected",
                                         wx.DefaultPosition, wx.DefaultSize, 0)
        self.xbox_status.Wrap(-1)
        sizer1.AddMany([
            (self.xbox_status_label, 0, wx.ALIGN_LEFT | wx.ALL, 5),
            (self.xbox_status, 0, wx.ALL | wx.EXPAND, 5)
        ])
        sizer2.AddMany([
            (self.discover_btn, 1, wx.ALIGN_RIGHT | wx.ALL | wx.EXPAND, 5),
            (self.xbox_console_list, 2, wx.ALL | wx.EXPAND, 0),
            (self.xbox_connect_btn, 1, wx.ALL | wx.EXPAND, 5)
        ])
        sizer3.AddMany([
            (self.xbox_auth_btn, 1, wx.ALIGN_RIGHT | wx.ALL | wx.EXPAND, 5)
        ])
        self.AddMany([
            (sizer1, 1, wx.EXPAND, 5),
            (sizer2, 1, wx.EXPAND, 5),
            (sizer3, 1, wx.EXPAND, 5),
        ])

    @property
    def discovered(self):
        return self._discovered

    @discovered.setter
    def discovered(self, value):
        self._discovered = value
        self.xbox_console_list.Clear()
        for dc in self._discovered:
            self.xbox_console_list.Append(dc, dc.console_dict.name)

    def OnConsoleConnected(self, e):
        erp.GUI_APP.mainframe.SetStatusText(f"Connected to {e.data}")
        self.xbox_status.Label = f"Connected to {e.data}"
        self.xbox_connect_btn.Label = "Disconnect"

    def OnConsoleDisconnected(self, e):
        erp.GUI_APP.mainframe.SetStatusText(f"Disconnected: {e.data}")
        self.xbox_status.Label = f"Disconnected"
        self.xbox_connect_btn.Label = "Connect"

    def OnSystemTextInput(self, e):
        route: erp.Route = erp.GUI_APP.mainframe.route_panel.route
        if route:
            if route.next_waypoint is not None and not route.paused:
                erp.GUI_APP.task_queue.put(xbs.SystemTextSend(route.next_waypoint.name))
                route.visit(route.waypoints.index(route.next_waypoint))
                erp.GUI_APP.mainframe.route_panel.route = route

    def OnConsoleSelected(self, e):
        discoveredConsole = e.EventObject.GetClientData(e.EventObject.GetCurrentSelection()).GetClientObject()

    def OnDiscoverBtn(self, e):
        e.EventObject.Label = "Scanning..."
        erp.GUI_APP.task_queue.put(
            xbs.DiscoverRequest(None)
        )

    def OnDiscoveredConsole(self, e):
        self.discover_btn.Label = "Scan"
        print(e)
        name = e.data.console_dict['name']
        uuid = e.data.console_dict['uuid']
        ipaddr = e.data.console_dict['address']
        dataitems = [self.xbox_console_list.GetClientData(x).GetClientData() for x in range(0, self.xbox_console_list.Count)]
        uuids = [x.console_dict['uuid'] for x in dataitems]
        if uuid in uuids:
            return
        else:
            erp.GUI_APP.mainframe.SetStatusText(f"Discovered console {name} with ip {ipaddr} and uuid {uuid}")
            clientData = wx.ClientDataContainer()
            clientData.SetClientObject(e.data)
            self.xbox_console_list.Append(f"{name}: {ipaddr}", clientData)

    def OnDiscoveryFailure(self, e):
        e.EventObject.Label = "Scan"
        erp.GUI_APP.mainframe.SetStatusText(f"Failed to discover any console {e.data}")

    def onConnectBtn(self, e):
        ""
        if e.EventObject.Label == "Connect":
            e.EventObject.Label = "Connecting..."
            if self.xbox_console_list.Count > 0:
                dc: xbs.DiscoveredConsole = self.xbox_console_list.GetClientData(
                    self.xbox_console_list.GetCurrentSelection()).GetClientObject()
                erp.GUI_APP.task_queue.put(dc)
            else:
                e.EventObject.Label = "Connect"
                erp.GUI_APP.mainframe.SetStatusText("ERROR: No consoles found (Did you forget to Scan?)")
        if e.EventObject.Label == "Disconnect":
            e.EventObject.Label = "Disconnecting..."
            erp.GUI_APP.task_queue.put(xbs.DisconnectRequest())

    def onAuthBtn(self, e):
        ""  # Start a thread to authenticate with the xbox


class RouteDetailSection(wx.StaticBoxSizer):
    def __init__(self, parent):
        wx.StaticBoxSizer.__init__(self, wx.StaticBox(parent, wx.ID_ANY, "Route Details"), wx.VERTICAL)

        # Attributes

        # Layout
        self.__DoLayout()

        # Events

    @property
    def route_metadata(self):
        if erp.GUI_APP:
            route: erp.Route = erp.GUI_APP.mainframe.route_panel.route
            return erp.RouteMeta(route)

    def update_route_details(self):
        m: erp.RouteMeta = self.route_metadata
        if m.current is not None:
            current_type = " | (Neutron)" if m.current.is_neutron else ""
            remaining_distance = m.current.distance_left
            self.current_system_text.Label = f"{m.current.name}{current_type}\n({m.current.x}, {m.current.y}, {m.current.z})"
        else:
            remaining_distance = m.distance
            self.current_system_text.Label = ""
        if m.next is not None:
            next_type = " | (Neutron)" if m.next.is_neutron else ""
            self.next_system_text.Label = f"{m.next.name}{next_type}\nDist: {m.next.distance_jumped:,.2f}LY\nJumps: {m.next.jumps}"
        else:
            self.next_system_text.Label = ""
        self.status_text.Label = f"Rem. Distance: {remaining_distance:,.2f}LY\nRem. Jumps: {m.remaining_jumps}"
        self.jump_range.Label = f"{m.jump_range}LY"
        self.src.Label = f"{m.src}"
        self.dest.Label = f"{m.dest}"
        self.eff.Label = f"{m.eff}%"
        self.distance.Label = f"{m.distance:,.2f}LY"
        self.Layout()
        erp.GUI_APP.mainframe.Layout()


    def __DoLayout(self):
        sizer1 = wx.BoxSizer(wx.VERTICAL)
        sbs1 = wx.StaticBoxSizer(wx.StaticBox(self.GetStaticBox(), wx.ID_ANY, "Current System"), wx.HORIZONTAL)
        sbs2 = wx.StaticBoxSizer(wx.StaticBox(self.GetStaticBox(), wx.ID_ANY, "Next System"), wx.HORIZONTAL)
        sbs3 = wx.StaticBoxSizer(wx.StaticBox(self.GetStaticBox(), wx.ID_ANY, "Status"), wx.HORIZONTAL)
        self.current_system_text = wx.StaticText(self.GetStaticBox(), wx.ID_ANY)
        self.next_system_text = wx.StaticText(self.GetStaticBox(), wx.ID_ANY)
        self.status_text = wx.StaticText(self.GetStaticBox(), wx.ID_ANY)
        self.extra_text = wx.FlexGridSizer(2, 5, 0)
        sbs1.Add(self.current_system_text, 1, wx.EXPAND | wx.ALL, 0)
        sbs2.Add(self.next_system_text, 1, wx.EXPAND | wx.ALL, 0)
        sbs3.Add(self.status_text, 1, wx.EXPAND | wx.ALL, 0)
        self.jump_range = wx.StaticText(self.GetStaticBox(), wx.ID_ANY)
        self.src = wx.StaticText(self.GetStaticBox(), wx.ID_ANY)
        self.dest = wx.StaticText(self.GetStaticBox(), wx.ID_ANY)
        self.eff = wx.StaticText(self.GetStaticBox(), wx.ID_ANY)
        self.distance = wx.StaticText(self.GetStaticBox(), wx.ID_ANY)
        self.extra_text.AddMany([
            (wx.StaticText(self.GetStaticBox(), wx.ID_ANY, "Ship Jump range:"), 0, wx.ALIGN_RIGHT | wx.ALL, 0),
            (self.jump_range, 1, wx.ALIGN_LEFT | wx.ALL | wx.EXPAND, 0),
            (wx.StaticText(self.GetStaticBox(), wx.ID_ANY, "Start System:"), 0, wx.ALIGN_RIGHT | wx.ALL, 0),
            (self.src, 1, wx.ALIGN_LEFT | wx.ALL | wx.EXPAND, 0),
            (wx.StaticText(self.GetStaticBox(), wx.ID_ANY, "End System:"), 0, wx.ALIGN_RIGHT | wx.ALL, 0),
            (self.dest, 1, wx.ALIGN_LEFT | wx.ALL | wx.EXPAND, 0),
            (wx.StaticText(self.GetStaticBox(), wx.ID_ANY, "Route Efficiency:"), 0, wx.ALIGN_RIGHT | wx.ALL, 0),
            (self.eff, 1, wx.ALIGN_LEFT | wx.ALL | wx.EXPAND, 0),
            (wx.StaticText(self.GetStaticBox(), wx.ID_ANY, "Total Distance:"), 0, wx.ALIGN_RIGHT | wx.ALL, 0),
            (self.distance, 1, wx.ALIGN_LEFT | wx.ALL | wx.EXPAND, 0),
        ])
        sizer1.AddMany([
            (sbs1, 0, wx.ALL | wx.EXPAND, 0),
            (sbs2, 0, wx.ALL | wx.EXPAND, 0),
            (sbs3, 0, wx.ALL | wx.EXPAND, 0),
            (self.extra_text, 0, wx.ALL | wx.EXPAND, 5),

        ])

        self.AddMany([
            (sizer1, 0, wx.ALL | wx.EXPAND, 0),
        ])
        self.Layout()


class RouteControlSection(wx.StaticBoxSizer):
    def __init__(self, parent):
        wx.StaticBoxSizer.__init__(self, wx.StaticBox(parent, wx.ID_ANY, "Route Controls"), wx.VERTICAL)

        # Attributes

        # Layout
        self.__DoLayout()

        # Events
        self.GetStaticBox().Bind(wx.EVT_BUTTON, self.onPlayPauseBtn, self.playpausebtn)
        self.GetStaticBox().Bind(wx.EVT_BUTTON, self.OnSkipBtn, self.skip_btn)
        self.GetStaticBox().Bind(wx.EVT_BUTTON, self.onRouteNextScoopable, self.route_nearest_scoopable)
        self.GetStaticBox().Bind(wx.EVT_BUTTON, self.OnPrevBtn, self.prev_btn)
        self.GetStaticBox().Bind(wx.EVT_TEXT_ENTER, self.OnManualSend, self.manual_text_input)
        self.GetStaticBox().Bind(wx.EVT_BUTTON, self.OnManualSend, self.manual_text_btn)

    def __DoLayout(self):
        row1 = wx.BoxSizer(wx.HORIZONTAL)
        row2 = wx.BoxSizer(wx.HORIZONTAL)
        row3 = wx.BoxSizer(wx.HORIZONTAL)
        self.playpausebtn = wx.Button(self.GetStaticBox(), wx.ID_ANY, "Pause")
        self.playpausebtn.SetToolTip("Pause/Resume automatic insertion of system name into xbox's keyboard")
        self.route_nearest_scoopable = wx.Button(self.GetStaticBox(), wx.ID_ANY, "Route to Fuel Star")
        self.route_nearest_scoopable.SetToolTip("Insert a waypoint to scoop for fuel (Star Class K/G/B/F/O/A/M)")
        self.skip_btn = wx.Button(self.GetStaticBox(), wx.ID_ANY, "Next")
        self.skip_btn.SetToolTip("Skip to next system in route")
        self.prev_btn = wx.Button(self.GetStaticBox(), wx.ID_ANY, "Back")
        self.prev_btn.SetToolTip("Go back to the previous system in route")
        self.manual_text_input = wx.TextCtrl(self.GetStaticBox(), wx.ID_ANY, "", wx.DefaultPosition, wx.DefaultSize, 0)
        self.manual_text_btn = wx.Button(self.GetStaticBox(), wx.ID_ANY, "Send", wx.Point(-1, -1), wx.DefaultSize, 0)
        row1.AddMany([
            (self.route_nearest_scoopable, 1, wx.ALL | wx.EXPAND, 5),
            (self.playpausebtn, 0, wx.ALL | wx.EXPAND, 5),
            (self.prev_btn, 0, wx.ALL | wx.EXPAND, 5),
            (self.skip_btn, 0, wx.ALL | wx.EXPAND, 5),
        ])
        row2.AddMany([
            (wx.StaticText(self.GetStaticBox(), wx.ID_ANY, "Send text manually:"), 0, wx.ALIGN_LEFT | wx.ALL, 5),
            (self.manual_text_input, 1, wx.ALIGN_CENTER | wx.ALL, 0),
            (self.manual_text_btn, 0, wx.ALIGN_RIGHT | wx.ALL, 5)
        ])
        row3.AddMany([
        ])
        self.AddMany([
            (row1, 0, wx.EXPAND, 5),
            (row2, 0, wx.EXPAND, 5),
            (row3, 5, wx.EXPAND, 5)
        ])

    def OnSkipBtn(self, e):
        route = erp.GUI_APP.mainframe.route_panel.route
        if route:
            if route.next_waypoint is not None:
                route.visit(route.waypoints.index(route.next_waypoint))
                erp.GUI_APP.mainframe.route_panel.route = route

    def OnPrevBtn(self, e):
        route = erp.GUI_APP.mainframe.route_panel.route
        if route:
            if route.current_waypoint is not None:
                route.cancel_visit(route.waypoints.index(route.current_waypoint))
                erp.GUI_APP.mainframe.route_panel.route = route

    def onPlayPauseBtn(self, e):
        route = erp.GUI_APP.mainframe.route_panel.route
        if route is not None:
            route.paused = not route.paused
            if route.paused:
                e.EventObject.Label = "Resume"
            else:
                e.EventObject.Label = "Pause"
            erp.GUI_APP.mainframe.route_panel.route = route

    def OnManualSend(self, e):
        text = self.manual_text_input.GetValue()
        print("text to send:", text)
        if type(text) == str:
            erp.GUI_APP.task_queue.put(xbs.SystemTextSend(text))

    def onRouteNextScoopable(self, e):
        """Fetch nearest main-sequence scoopable star nearest to current star system and insert into route"""
        # Get list of neighboring star systems to current system from EDSM and insert as a waypoint
        # also, duplicate previous waypoint so the player returns to the nearest neutron star for FSD boost


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
        vbs.Add(self.route_control_section, 0, wx.EXPAND, 5)
        self.SetSizer(vbs)
        self.Layout()
        vbs.Fit(self)
