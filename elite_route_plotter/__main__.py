import elite_route_plotter as erp
from elite_route_plotter import gui

def main():
    erp.GUI_APP = gui.PlotterApp()
    erp.GUI_APP.MainLoop()

main()