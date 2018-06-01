from .models import *
from .gui import PlotterApp
GUI_APP:PlotterApp = None
APPLICATION_NAME = "Elite:Dangerous Neutron Router"
import gevent


def main():
    global GUI_APP
    GUI_APP = gui.PlotterApp()
    gevent.spawn(GUI_APP.XboxLoop)
    GUI_APP.MainLoop()
