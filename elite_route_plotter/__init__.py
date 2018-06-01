from .models import *
from .gui import PlotterApp
GUI_APP:PlotterApp = None
APPLICATION_NAME = "Elite:Dangerous Neutron Router"


def main():
    global GUI_APP
    GUI_APP = gui.PlotterApp()
    GUI_APP.MainLoop()