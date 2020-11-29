# ============================================================
# YeeMee - Version 4.7 by D. Lanik (2017)
# ------------------------------------------------------------
# Control YeeLight bulbs from Kodi
# ------------------------------------------------------------
# License: GPL (http://www.gnu.org/licenses/gpl-3.0.html)
# ============================================================

import xbmc
import xbmcaddon
import xbmcgui
import socket
import json
import sys
import os
import random
import requests
from datetime import datetime
from threading import Timer
from xml.dom import minidom
from distutils.util import strtobool
from service import Yeelight

# ============================================================
# Class for timer
# ============================================================


class RepeatedTimer(object):
    def __init__(self, interval, function, *args, **kwargs):
        self._timer = None
        self.interval = interval
        self.function = function
        self.args = args
        self.kwargs = kwargs
        self.is_running = False
        self.start()

    def _run(self):
        self.is_running = False
        self.start()
        self.function(*self.args, **self.kwargs)

    def start(self):
        if not self.is_running:
            self._timer = Timer(self.interval, self._run)
            self._timer.start()
            self.is_running = True

    def stop(self):
        self._timer.cancel()
        self.is_running = False

    def isrunning(self):
        if not self.is_running:
            self.is_running = False
        else:
            self.is_running = True

# ============================================================
# Define Overlay Class
# ============================================================


class OverlayText(object):
    def __init__(self, windowid):
        self.showing = False
        self.window = xbmcgui.Window(windowid)
        viewport_w, viewport_h = self._get_skin_resolution()

        pw = int((viewport_w - 1024) / 2)
        ph = int((viewport_h - 445) / 2)
        pp = "%3d,%3d" % (pw, ph)
        pos = pp.split(",")
        pos_x = (viewport_w + int(pos[0]), int(pos[0]))[int(pos[0]) > 0]
        pos_y = (viewport_h + int(pos[1]), int(pos[1]))[int(pos[1]) > 0]
        self.imgbigbulb = xbmcgui.ControlImage(pos_x, pos_y, 1024, 445, os.path.join("media", "YEE02.png"), aspectRatio=2)

        pw = int((viewport_w - 500) / 2)
        ph = int((viewport_h - 550) / 2)
        pp = "%3d,%3d" % (pw, ph)
        pos = pp.split(",")
        pos_x = (viewport_w + int(pos[0]), int(pos[0]))[int(pos[0]) > 0]
        pos_y = (viewport_h + int(pos[1]), int(pos[1]))[int(pos[1]) > 0]
        self.imgtestbulb = xbmcgui.ControlImage(pos_x, pos_y, 500, 550, os.path.join("media", "yee_color.png"), aspectRatio=2)

    def show(self):
        self.showing = True
        self.window.addControl(self.imgbigbulb)
        self.window.addControl(self.imgtestbulb)

    def hide(self):
        self.showing = False
        self.window.removeControl(self.imgbigbulb)
        self.window.removeControl(self.imgtestbulb)

    def _close(self):
        if self.showing:
            self.hide()
        else:
            pass
        try:
            self.window.clearProperties()
        except Exception:
            pass

# ============================================================
# Get resolution
# ============================================================

    def _get_skin_resolution(self):
        xmlFile = os.path.join(xbmc.translatePath("special://skin/"), "addon.xml")
        xmldoc = minidom.parse(xmlFile)

        res = xmldoc.getElementsByTagName("res")
        xval = int(res[0].attributes["width"].value)
        yval = int(res[0].attributes["height"].value)

        return(xval, yval)

# ============================================================
# Time by location - get sunset and sunrise for current loc
# ============================================================


def byLoc():
    xbmc.executebuiltin("ActivateWindow(busydialog)")

    url = "http://ip-api.com/json"
    r = requests.get(url)
    data = r.json()

    lat = data["lat"]
    lng = data["lon"]
    timezone = data["timezone"]
    response = data["status"]

    if response == "success":
        xbmc.log("YEEMEE >> GOT CURRENT LAT-LON: " + str(lat) + ", " + str(lng) + " TIMEZONE: " + str(timezone))
        __addon__.setSetting("Lat", str(lat))
        __addon__.setSetting("Lon", str(lng))
    else:
        lat = int(__addon__.getSetting("Lat", str(lat)))
        lng = int(__addon__.getSetting("Lon", str(lng)))

    ts = 1288483950000 * 1e-3
    utc_offset = datetime.fromtimestamp(ts) - datetime.utcfromtimestamp(ts)
    xbmc.log("YEEMEE >> GOT TIMEZONE OFFSET: " + str(utc_offset))

    url = "http://api.sunrise-sunset.org/json?lat=" + str(lat) + "&lng=" + str(lng)
    r = requests.get(url)
    data = r.json()

    sunrise = data["results"]["sunrise"]
    sunset = data["results"]["sunset"]
    response = data["status"]

    if response == "OK":
        datetime_sunrise = datetime.strptime(sunrise, '%I:%M:%S %p')
        datetime_sunrise += utc_offset
        tem = str(datetime_sunrise)[-8:]
        h, m, s = tem.split(':')
        sunrise = h + ":" + m
        xbmc.log("YEEMEE >> GOT CURRENT SUNRISE: " + str(sunrise))

        datetime_sunset = datetime.strptime(sunset, '%I:%M:%S %p')
        datetime_sunset += utc_offset
        tem = str(datetime_sunset)[-8:]
        h, m, s = tem.split(':')
        sunset = h + ":" + m
        xbmc.log("YEEMEE >> GOT CURRENT SUNSET: " + str(sunset))

        __addon__.setSetting('timeOnStart', str(sunset))
        __addon__.setSetting('timeOnEnd', str(sunrise))
        timeOnStart = datetime.strptime(__addon__.getSetting('timeOnStart'), '%H:%M').time()
        timeOnEnd = datetime.strptime(__addon__.getSetting('timeOnEnd'), '%H:%M').time()

        xbmc.log("YEEMEE >> TIME ON >> " + str(timeOnStart) + " - " + str(timeOnEnd))
    else:
        xbmc.log("YEEMEE >> COULD NOT RETRIEVE SUNSET+SUNRISE")

    xbmc.executebuiltin("Dialog.Close(busydialog)")

# ============================================================
# To be repeated every x seconds
# ============================================================


def hw():
    global myWidget

    r = lambda: random.randint(0, 255)
    color = '0xF0%02X%02X%02X' % (r(), r(), r())

    myWidget.imgtestbulb.setColorDiffuse(color)
    myWidget.imgbigbulb.setColorDiffuse(color)

# ============================================================
# Test the bulb
# ============================================================


def testbulb(number):
    global __addonname__
    global __addonwd__
    global myWidget
    global Yeelight

    dialog = xbmcgui.Dialog()
    dialog.ok(__addonname__.encode('utf8'), __addon__.getLocalizedString(32100) + "[COLOR red]" + str(number) + "[/COLOR]")

    bulbid = "bulb_" + str(number)
    bulbmodel = "bulb_" + str(number) + "_model"
    ipaddr = __addon__.getSetting(bulbid)
    model = "yee_" + __addon__.getSetting(bulbmodel) + ".png"

    ActWin = xbmcgui.getCurrentWindowId()
    myWidget = OverlayText(ActWin)
    myWidget.show()
    myWidget.imgtestbulb.setImage(os.path.join(__addonwd__, "media", model))
    xbmc.log('YEEMEE STANDALONE >> INITIALIZING OVERLAY')

    rt = RepeatedTimer(0.1, hw)
    rt.isrunning()
    if not rt.is_running:
        rt.start()

    xbmc.executebuiltin("ActivateWindow(busydialog)")

    bulbone = Yeelight(ipaddr)

    xbmc.log("YEEMEE >> TEST BULB NR " + str(number))
    mmm1 = bulbone.testTurnOn()
    xbmc.sleep(3000)
    mmm2 = bulbone.testTurnOff()

    rt.stop()

    try:
        myWidget._close()
    except Exception:
        pass

    myWidget = None

    xbmc.executebuiltin("Dialog.Close(busydialog)")

    errstr = __addon__.getLocalizedString(32103) + "\n" + __addon__.getLocalizedString(32082) + ": " + mmm1 + "\n" + __addon__.getLocalizedString(32081) + ": " + mmm2

    dialog = xbmcgui.Dialog()
    dialog.ok(__addonname__.encode('utf8'), errstr)


# ============================================================
# Bulb on
# ============================================================


def BulbOn(number):
    global __addonname__
    global __addonwd__
    global myWidget
    global Yeelight

    bulbid = "bulb_" + str(number)
    ipaddr = __addon__.getSetting(bulbid)

    bulbone = Yeelight(ipaddr)

    xbmc.log("YEEMEE >> ON BULB NR " + str(number))
    mmm1 = bulbone.testTurnOn()

# ============================================================
# Bulb on
# ============================================================


def BulbOff(number):
    global __addonname__
    global __addonwd__
    global myWidget
    global Yeelight

    bulbid = "bulb_" + str(number)
    ipaddr = __addon__.getSetting(bulbid)

    bulbone = Yeelight(ipaddr)

    xbmc.log("YEEMEE >> OFF BULB NR " + str(number))
    mmm1 = bulbone.testTurnOff()

# ============================================================
# Get settings
# ============================================================


def SaGetSettings():
    global __addon__
    global bulbs

    __addon__ = xbmcaddon.Addon(id='service.yeemee')

    numberOfBulbs = int(__addon__.getSetting("numberOfBulbs")) + 1

    bulbs = []

    c = 0
    for x in range(1, numberOfBulbs + 1):
        bulbid = "bulb_" + str(x)
        bulbmodel = "bulb_" + str(x) + "_model"
        ipaddr = __addon__.getSetting(bulbid)

        xbmc.log('YEEMEE >> STANDALONE >> INIT BULB NUM: ' + str(x) + ", IP ADDR: " + ipaddr)
        bulbs.append(Yeelight(ipaddr))

        bulbs[c].model = __addon__.getSetting(bulbmodel)

        bulbs[c].play_action = int(__addon__.getSetting(bulbid + "_play_action"))
        bulbs[c].play_intensity = int(__addon__.getSetting(bulbid + "_play_intensity"))
        bulbs[c].play_color = __addon__.getSetting(bulbid + "_play_color")
        bulbs[c].play_effect = int(__addon__.getSetting(bulbid + "_play_effect"))
        bulbs[c].play_duration = int(__addon__.getSetting(bulbid + "_play_duration"))

        bulbs[c].stop_action = int(__addon__.getSetting(bulbid + "_stop_action"))
        bulbs[c].stop_intensity = int(__addon__.getSetting(bulbid + "_stop_intensity"))
        bulbs[c].stop_color = __addon__.getSetting(bulbid + "_stop_color")
        bulbs[c].stop_effect = int(__addon__.getSetting(bulbid + "_stop_effect"))
        bulbs[c].stop_duration = int(__addon__.getSetting(bulbid + "_stop_duration"))

        bulbs[c].pause_action = int(__addon__.getSetting(bulbid + "_pause_action"))
        bulbs[c].pause_intensity = int(__addon__.getSetting(bulbid + "_pause_intensity"))
        bulbs[c].pause_color = __addon__.getSetting(bulbid + "_pause_color")
        bulbs[c].pause_effect = int(__addon__.getSetting(bulbid + "_pause_effect"))
        bulbs[c].pause_duration = int(__addon__.getSetting(bulbid + "_pause_duration"))

        c += 1

# ============================================================
# Playback state changed, react
# ============================================================


def state_changed(player_state):
    global bulbs

    for i, x in enumerate(bulbs):
        if player_state == "stop":
            if x.stop_action == 3:
                if x.initial_state == "off":
                    x.turnOff(player_state)
                else:
                    x.turnOn(player_state)
            elif x.stop_action == 2:
                x.turnOn(player_state)
            elif x.stop_action == 1:
                x.turnOff(player_state)
        elif player_state == "pause":
            if x.pause_action == 2:
                x.turnOn(player_state)
            elif x.pause_action == 1:
                x.turnOff(player_state)
        elif player_state == "play":
            if x.play_action == 2:
                x.turnOn(player_state)
            elif x.play_action == 1:
                x.turnOff(player_state)

# ============================================================
# Start animation
# ============================================================


def StartAni():
    global myWidget
    global rt

    ActWin = xbmcgui.getCurrentWindowId()
    myWidget = OverlayText(ActWin)
    myWidget.show()
    myWidget.imgbigbulb.setImage(os.path.join(__addonwd__, "media", "YEE02.png"))
    xbmc.log('YEEMEE STANDALONE >> INITIALIZING OVERLAY')

    rt.isrunning()
    if not rt.is_running:
        rt.start()

    xbmc.executebuiltin("ActivateWindow(busydialog)")


# ============================================================
# Stop animation
# ============================================================

def StopAni():
    global myWidget
    global rt

    rt.stop()

    try:
        myWidget._close()
    except Exception:
        pass

    myWidget = None

    xbmc.executebuiltin("Dialog.Close(busydialog)")


# ============================================================
# ------------------------------------------------------------
# Main
# ------------------------------------------------------------
# ============================================================


__addon__ = xbmcaddon.Addon(id='service.yeemee')
__addondir__ = xbmc.translatePath(__addon__.getAddonInfo('profile').decode('utf-8'))
__addonwd__ = xbmc.translatePath(__addon__.getAddonInfo('path').decode("utf-8"))
__addonname__ = __addon__.getAddonInfo('name')
__version__ = __addon__.getAddonInfo('version')

myWidget = None
rt = None
bulbs = []

if __name__ == '__main__':
    arg = None

    try:
        arg = sys.argv[1].lower()
        xbmc.log("YEEMEE >> STANDALONE STARTED VERSION %s - TEST LIGHTS" % (__version__))
    except Exception:
        xbmc.log("YEEMEE >> STANDALONE STARTED VERSION %s" % (__version__))
        pass

    if arg == "testyee1":
        testbulb(1)
    elif arg == "testyee2":
        testbulb(2)
    elif arg == "testyee3":
        testbulb(3)
    elif arg == "testyee4":
        testbulb(4)
    elif arg == "testyee5":
        testbulb(5)
    elif arg == "testyee6":
        testbulb(6)
    elif arg == "testyee7":
        testbulb(7)
    elif arg == "testyee8":
        testbulb(8)
    elif arg == "byloc":
        byLoc()
    elif arg == "bulb_play":
        SaGetSettings()
        state_changed("play")
    elif arg == "bulb_stop":
        SaGetSettings()
        state_changed("stop")
    elif arg == "bulb_pause":
        SaGetSettings()
        state_changed("pause")
    elif arg == "bulb_play_test":
        rt = RepeatedTimer(0.1, hw)
        StartAni()
        SaGetSettings()
        state_changed("play")
        xbmc.sleep(3000)
        StopAni()
    elif arg == "bulb_stop_test":
        rt = RepeatedTimer(0.1, hw)
        StartAni()
        SaGetSettings()
        state_changed("stop")
        xbmc.sleep(3000)
        StopAni()
    elif arg == "bulb_pause_test":
        rt = RepeatedTimer(0.1, hw)
        StartAni()
        SaGetSettings()
        state_changed("pause")
        xbmc.sleep(3000)
        StopAni()
    elif arg == "bulb1_on":
        BulbOn(1)
    elif arg == "bulb1_off":
        BulbOff(1)
    elif arg == "bulb2_on":
        BulbOn(2)
    elif arg == "bulb2_off":
        BulbOff(2)
    elif arg == "bulb3_on":
        BulbOn(3)
    elif arg == "bulb3_off":
        BulbOff(3)
    elif arg == "bulb4_on":
        BulbOn(4)
    elif arg == "bulb4_off":
        BulbOff(4)
    elif arg == "bulb5_on":
        BulbOn(5)
    elif arg == "bulb5_off":
        BulbOff(5)
    elif arg == "bulb6_on":
        BulbOn(6)
    elif arg == "bulb6_off":
        BulbOff(6)
    elif arg == "bulb7_on":
        BulbOn(7)
    elif arg == "bulb7_off":
        BulbOff(7)
    elif arg == "bulb8_on":
        BulbOn(8)
    elif arg == "bulb8_off":
        BulbOff(8)
    elif arg == "service_start":
        ServiceOn = bool(strtobool(str(__addon__.getSetting('ServiceOn').title())))
        if not ServiceOn:
            __addon__.setSetting('ServiceOn', 'true')
    elif arg == "service_stop":
        ServiceOn = bool(strtobool(str(__addon__.getSetting('ServiceOn').title())))
        if ServiceOn:
            __addon__.setSetting('ServiceOn', 'false')

    __addon__.openSettings()
    xbmc.log("YEEMEE >> STANDALONE FINISHED")

# ------------------------------------------------------------
# ------------------------------------------------------------
# ------------------------------------------------------------
# ------------------------------------------------------------
# ------------------------------------------------------------
# ------------------------------------------------------------
# ------------------------------------------------------------
# ------------------------------------------------------------
# ------------------------------------------------------------
# ------------------------------------------------------------
