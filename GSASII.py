#!/usr/bin/env python
# -*- coding: utf-8 -*-
#GSASII
########### SVN repository information ###################
# $Date$
# $Author$
# $Revision$
# $URL$
# $Id$
########### SVN repository information ###################
'''
A single class, :class:`G2App`, is defined here to create 
an wxPython application. This is only used on 
MacOS. For other platforms ``wx.App()`` is called directly. 
'''

import sys
#import os
import platform
import scipy.optimize # addresses problem with build for wx on Pi
try:
    import wx
    # the next line removes the need for pythonw. Thanks to Matt Newville!
    if sys.platform.lower() == 'darwin': wx.PyApp.IsDisplayAvailable = lambda _: True
# importing the following wx modules at the same time as wx seems to eliminate 
# the "Debug: Adding duplicate image handler for 'Windows bitmap file'"
# error message
    import wx.grid as wg
    import wx.aui
    import wx.lib.scrolledpanel as wxscroll
    import wx.html        # could postpone this for quicker startup
    import wx.lib.mixins.listctrl  as  listmix
    import wx.richtext as wxrt
    import wx.lib.filebrowsebutton as wxfilebrowse
except ImportError:
    pass
import GSASIIpath
GSASIIpath.SetVersionNumber("$Revision$")

__version__ = '1.0.0'

class G2App(wx.App):
    '''Used to create a wx python application for the GUI for Mac.
    Customized to implement drop of GPX files onto app.
    '''
    startupMode = True
    def ClearStartup(self):
        '''Call this after app startup complete because a Drop event is posted 
        when GSAS-II is initially started.
        '''
        self.startupMode = False        
    def MacOpenFiles(self, filenames):
        if self.startupMode:
            return
        for project in filenames:
            #print("Start GSAS-II with project file "+str(project))
            GSASIIpath.MacStartGSASII(__file__,project)

if __name__ == '__main__':
    if sys.platform == "darwin": 
        application = G2App(0) # create the GUI framework
    else:
        application = wx.App(0) # create the GUI framework
    try:
        GSASIIpath.SetBinaryPath(True)
    except:
        print('Unable to run with current setup, do you want to update to the')
        try:
            if '2' in platform.python_version_tuple()[0]:            
                ans = raw_input("latest GSAS-II version? Update ([Yes]/no): ")
            else:
                ans = input("latest GSAS-II version? Update ([Yes]/no): ")                
        except:
            ans = 'no'
        if ans.strip().lower() == "no":
            import sys
            print('Exiting')
            sys.exit()
        print('Updating...')
        GSASIIpath.svnUpdateProcess()
    import GSASIIdataGUI as G2gd    
    G2gd.GSASIImain(application) # start the GUI
    if sys.platform == "darwin": 
        wx.CallLater(100,application.ClearStartup)
    GSASIIpath.InvokeDebugOpts()
    application.MainLoop()
