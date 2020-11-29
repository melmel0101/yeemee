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
import json
import socket
import requests
import re
import os
import math
import thread
import time
import urllib
import _strptime                        # this is because of the bug with strptime() in Python (https://bugs.python.org/issue7980)
import lib.webcolors as webcolors
import datetime
from distutils.util import strtobool
from colorsys import rgb_to_hls
from colorsys import hls_to_rgb
from PIL import Image
from threading import Timer

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


# ============================================================
# To be repeated every x seconds - send color to ceiling 650
# ============================================================


def hw():
    global bulbs
    global YeeSmoothen
    global YeePauseLower
    global cl_exlumi
    global cl_exrround
    global cl_exground
    global cl_exbround
    global cl_sw

    if YeeSmoothen > 0:
        effect = "smooth"
    else:
        effect = "sudden"

    for x in bulbs:        # for each bulb, find the bulb by model
        if x.model == "ceiling4":
            activeBulb = x
            break

    lumi = int(activeBulb.applyColorsL * 100)

    if cl_sw:
        if lumi > 5:
            r, g, b = hls_to_rgb(activeBulb.applyColorsH, activeBulb.applyColorsL, activeBulb.applyColorsS)

            rround = ((r * 100)) // 10 * 10
            ground = ((g * 100)) // 10 * 10
            bround = ((b * 100)) // 10 * 10

            if rround != cl_exrround or ground != cl_exground or bround != cl_exbround:
                r = str(r * 100) + "%"
                g = str(g * 100) + "%"
                b = str(b * 100) + "%"

                rgbcolor = webcolors.rgb_percent_to_hex([r, g, b])
                color = int(rgbcolor[1:], 16)
                data = json.dumps({"id": 1, "method": "bg_set_rgb", "params": [color, effect, YeeSmoothen]}) + "\r\n"
                activeBulb.sendMessage(data)

            cl_exrround = rround
            cl_exground = ground
            cl_exbround = bround
    else:
        if activeBulb.paused:
            if lumi > YeePauseLower:
                if YeePauseLower == 0:
                    YeePauseLower = 1
                data = json.dumps({"id": 1, "method": "bg_set_bright", "params": [YeePauseLower, effect, YeeSmoothen]}) + "\r\n"
                activeBulb.sendMessage(data)
        else:
            lumiround = (lumi + 9) // 10 * 10

            if lumiround != cl_exlumi:
                if lumiFactor < 100:
                    lumi = int((lumi * lumiFactor) / 100)

                if activeBulb.bias > 0:
                    lumi = int((lumi * (100 - activeBulb.bias)) / 100)

                data = json.dumps({"id": 1, "method": "bg_set_bright", "params": [lumi, effect, YeeSmoothen]}) + "\r\n"
                activeBulb.sendMessage(data)

            cl_exlumi = lumiround

    cl_sw = not cl_sw

# ============================================================
# Time workaround
# ============================================================


def mystr2time(funct, format):
    try:
        mytime = datetime.datetime.strptime(funct, format)
    except TypeError:
        try:
            mytime = datetime.datetime.fromtimestamp(time.mktime(time.strptime(funct, format)))
        except Exception:
            mytime = datetime.datetime.combine(datetime.date(1, 1, 1), datetime.time(0, 0, 0))

    except ValueError, v:
        ulr = len(v.args[0].partition('unconverted data remains: ')[2])
        if ulr:
            mytime = datetime.datetime.strptime(funct[:-ulr], format)
        else:
            mytime = datetime.datetime.combine(datetime.date(1, 1, 1), datetime.time(0, 0, 0))

    return mytime

# ------------------------------------------------------------
# ============================================================
# Define Settings Monitor Class
# ============================================================
# ------------------------------------------------------------


class SettingMonitor(xbmc.Monitor):
    def __init__(self, *args, **kwargs):
        xbmc.Monitor.__init__(self)

    def onSettingsChanged(self):
        GetSettings(1)

    def onScreensaverActivated(self):
        xbmc.log('YEEMEE >> SCREENSAVER >>START<<')
        saver_state_changed("startsaver")

    def onScreensaverDeactivated(self):
        xbmc.log('YEEMEE >> SCREENSAVER >>STOP<<')
        saver_state_changed("stopsaver")

# ============================================================
# Screensaver state changed, react
# ============================================================


def saver_state_changed(player_state):
    global bulbs
    global timeOn
    global timeOnStart
    global timeOnEnd
    global ServiceOn
    global disablePvr
    global AmbiOn
    global intDuration
    global disableShort
    global disableShortTime
    global numberOfColorBulbs
    global stopHandler
    global YeePriority
    global YeePauseLower
    global isPvr
    global isStream
    global thread_started
    global rt

    if (not ServiceOn):                                            # do not activate if yee service off
        return

    xbmc.log("YEEMEE >> ACTIVATION TIME ON/OFF: " + str(timeOn))     # check activation time
    if timeOn > 0:
        now = datetime.datetime.now()
        strNowTime = '%02d:%02d:%02d' % (now.hour, now.minute, now.second)
        nowTime = mystr2time(strNowTime, '%H:%M:%S').time()

        if nowTime > timeOnStart or nowTime < timeOnEnd:
            xbmc.log("YEEMEE >> IN TIME FRAME: " + str(timeOnStart) + " - (" + str(nowTime) + ") - " + str(timeOnEnd))
        else:
            xbmc.log("YEEMEE >> NOT IN TIME FRAME, QUITTING: " + str(timeOnStart) + " - (" + str(nowTime) + ") - " + str(timeOnEnd))
            return False

    for x in bulbs:
        if player_state == "stopsaver":
            if ServiceOn:                                          # normal operation
                if x.saveroff_action == 3:
                    if x.initial_state == "off":
                        x.turnOff(player_state)
                    else:
                        x.turnOn(player_state)
                elif x.saveroff_action == 2:
                    x.turnOn(player_state)
                elif x.saveroff_action == 1:
                    x.turnOff(player_state)

                if x.model == "ceiling4":                        # @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@ CEILING4
                    if x.saveroff_bg_action == 3:
                        if x.initial_bg_state == "off":
                            x.turnOff_bg(player_state)
                        else:
                            x.turnOn_bg(player_state)
                    elif x.saveroff_bg_action == 2:
                        x.turnOn_bg(player_state)
                    elif x.saveroff_bg_action == 1:
                        x.turnOff_bg(player_state)

        elif player_state == "startsaver":
            bulb_state = x.getState()
            x.initial_state = bulb_state

            if x.model == "ceiling4":                           # @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@ CEILING4
                bulb_state = x.getState_bg()
                x.initial_bg_state = bulb_state

            if ServiceOn:                                          # normal operation
                if x.saveron_action == 2:
                    x.turnOn(player_state)
                elif x.saveron_action == 1:
                    x.turnOff(player_state)

                # @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@ CEILING4
                if x.model == "ceiling4":
                    if x.saveron_bg_action == 2:
                        x.turnOn_bg(player_state)
                    elif x.saveron_bg_action == 1:
                        x.turnOff_bg(player_state)


# ============================================================
# Get settings
# ============================================================


def GetSettings(par1):
    global __addon__
    global __addondir__
    global __addonname__
    global bulbs
    global disableShort
    global disableShortTime
    global timeOn
    global timeOnStart
    global timeOnEnd
    global reportErrors
    global OffAtEnd
    global OnAtStart
    global OnAtStart_color
    global OnAtStart_effect
    global OnAtStart_duration
    global OnAtStart_intensity
    global OnAtStart_blink
    global OnAtStart_timeframe
    global numberOfControllers
    global controllers
    global MsgControllerOn
    global MsgUrlOn
    global ServiceOn
    global disablePvr
    global AmbiOn
    global numberOfBulbs
    global numberOfColorBulbs
    global YeePriority
    global YeePauseLower
    global YeeSmoothen
    global YeeAmbiMaxDay
    global YeeAmbiMaxCivTw
    global YeeAmbiMaxNauTw
    global YeeAmbiMaxNight
    global AmbiPrecision
    global debugRenderCapture

    if(xbmcgui.Window(10000).getProperty('YeeMeeDiscovery_Running') == "True"):
        xbmc.log('YEEMEE >> YEEMEE BULB DISCOVERY RUNNING, TERMINATING GET SETTINGS...')
        return

    __addon__ = xbmcaddon.Addon(id='service.yeemee')
    errors = False
    errstr = ""

    AmbiOn = bool(strtobool(str(__addon__.getSetting('AmbiOn').title())))
    ServiceOn = bool(strtobool(str(__addon__.getSetting('ServiceOn').title())))
    disablePvr = bool(strtobool(str(__addon__.getSetting('disablePvr').title())))
    numberOfBulbs = int(__addon__.getSetting("numberOfBulbs"))
    reportErrors = bool(strtobool(str(__addon__.getSetting('reportErrors').title())))
    debugRenderCapture = bool(strtobool(str(__addon__.getSetting('debugRenderCapture').title())))

    YeePriority = int(__addon__.getSetting("YeePriority"))
    YeePauseLower = int(__addon__.getSetting("YeePauseLower"))
    YeeSmoothen = int(__addon__.getSetting("YeeSmoothen"))

    AmbiPrecision = int(__addon__.getSetting("AmbiPrecision"))

    xbmc.log("YEEMEE >> YEMME - AMBI PRIORITY >> " + str(YeePriority))
    xbmc.log("YEEMEE >> LOWER BRIGHTNESS ON AMBI PAUSE >> " + str(YeePauseLower))
    xbmc.log("YEEMEE >> AMBI SMOOTHEN (MS) >> " + str(YeeSmoothen))
    xbmc.log("YEEMEE >> YEMME - AMBI PRECISION >> " + str(AmbiPrecision))

    OffAtEnd = bool(strtobool(str(__addon__.getSetting('OffAtEnd').title())))
    OnAtStart = int(__addon__.getSetting('OnAtStart'))

    xbmc.log("YEEMEE >> REPORT ERRORS >> " + str(reportErrors))
    xbmc.log('YEEMEE >> NUMBER OF BULBS >> ' + str(numberOfBulbs))
    xbmc.log('YEEMEE >> ON AT START >> ' + str(OnAtStart))

    if OnAtStart == 1:
        OnAtStart_color = __addon__.getSetting("OnAtStart_color")
        OnAtStart_blink = __addon__.getSetting("OnAtStart_blink")
        OnAtStart_effect = int(__addon__.getSetting("OnAtStart_effect"))
        OnAtStart_duration = int(__addon__.getSetting("OnAtStart_duration"))
        OnAtStart_intensity = int(__addon__.getSetting("OnAtStart_intensity"))
        OnAtStart_timeframe = bool(strtobool(str(__addon__.getSetting('OnAtStart_timeframe').title())))

        if OnAtStart_color[0] != "#":
            OnAtStart_color = "#" + OnAtStart_color
            __addon__.setSetting("OnAtStart_color", OnAtStart_color)

        if not validColor(OnAtStart_color):
            errstr = "On-start color has no valid hex code: " + str(OnAtStart_color)
            xbmc.log("YEEMEE >> " + errstr.upper())
            errors = True
        else:
            xbmc.log('YEEMEE >> AT START COLOR >> ' + str(OnAtStart_color))

        if OnAtStart_blink[0] != "#":
            OnAtStart_blink = "#" + OnAtStart_blink
            __addon__.setSetting("OnAtStart_blink", OnAtStart_blink)

        if not validColor(OnAtStart_blink):
            errstr = "Blink color has no valid hex code: " + str(OnAtStart_blink)
            xbmc.log("YEEMEE >> " + errstr.upper())
            errors = True
        else:
            xbmc.log('YEEMEE >> BLINK COLOR >> ' + str(OnAtStart_blink))

        xbmc.log('YEEMEE >> AT START DURATION >> ' + str(OnAtStart_duration))
        xbmc.log('YEEMEE >> AT START EFFECT >> ' + str(OnAtStart_effect))

    disableShort = bool(strtobool(str(__addon__.getSetting('disableShort').title())))
    if disableShort:
        disableShortTime = int(__addon__.getSetting('disableShortTime'))
        xbmc.log("YEEMEE >> DISABLE FOR SHORT FILMS >>" + str(disableShortTime) + "<< MIN")
    else:
        xbmc.log("YEEMEE >> DISABLE FOR SHORT FILMS >>FALSE<<")

    timeOn = int(__addon__.getSetting('timeOn'))

    if timeOn == 1:
        timeOnStart = mystr2time(__addon__.getSetting('timeOnStart'), '%H:%M').time()
        timeOnEnd = mystr2time(__addon__.getSetting('timeOnEnd'), '%H:%M').time()

        xbmc.log("YEEMEE >> ACTIVATION TIME >> " + str(timeOnStart) + " - " + str(timeOnEnd))
    elif timeOn == 2:
        timeOnStart = mystr2time(__addon__.getSetting('sunset'), '%H:%M').time()
        timeOnEnd = mystr2time(__addon__.getSetting('sunrise'), '%H:%M').time()

        xbmc.log("YEEMEE >> ACTIVATION TIME >> " + str(timeOnStart) + " - " + str(timeOnEnd))
    else:
        xbmc.log("YEEMEE >> ACTIVATION TIME >>OFF<<")

    YeeAmbiMaxDay = int(__addon__.getSetting('YeeAmbiMaxDay'))
    YeeAmbiMaxCivTw = int(__addon__.getSetting('YeeAmbiMaxCivTw'))
    YeeAmbiMaxNauTw = int(__addon__.getSetting('YeeAmbiMaxNauTw'))
    YeeAmbiMaxNight = int(__addon__.getSetting('YeeAmbiMaxNight'))

    xbmc.log("YEEMEE >> MAX BRIGHT DAY >> " + str(YeeAmbiMaxDay))
    xbmc.log("YEEMEE >> MAX BRIGHT CIVIL TW >> " + str(YeeAmbiMaxCivTw))
    xbmc.log("YEEMEE >> MAX BRIGHT NAUTIC TW >> " + str(YeeAmbiMaxNauTw))
    xbmc.log("YEEMEE >> MAX BRIGTH NIGHT >> " + str(YeeAmbiMaxNight))

    bulbs = []

    c = 0
    for x in range(1, numberOfBulbs + 1):
        bulbid = "bulb_" + str(x)
        bulbmodel = "bulb_" + str(x) + "_model"
        bulbStart = "OnAtStart_" + bulbid
        bulbStart_bg = bulbStart + "_bg"
        bulbAmbi = "bulb_" + str(x) + "_ambipos"
        ipaddr = __addon__.getSetting(bulbid)
        if validIP(ipaddr):
            bulbs.append(Yeelight(ipaddr))

            bulbs[c].model = __addon__.getSetting(bulbmodel)

            bulbs[c].on_start = bool(strtobool(str(__addon__.getSetting(bulbStart).title())))
            if bulbs[c].model == 'ceiling4':
                bulbs[c].on_bg_start = bool(strtobool(str(__addon__.getSetting(bulbStart_bg).title())))

            bulbs[c].applyColorsH = 0
            bulbs[c].applyColorsL = 0
            bulbs[c].applyColorsS = 0
            bulbs[c].paused = False

            bulbs[c].ambipos = int(__addon__.getSetting(bulbAmbi))
            bulbs[c].ambicoord = []
            bulbs[c].bias = int(__addon__.getSetting(bulbid + "_bias"))

            xbmc.log('YEEMEE >> INIT BULB NUM: ' + str(x) + ", IP ADDR: " + ipaddr + ", MODEL: " + bulbs[c].model)

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

            bulbs[c].saveron_action = int(__addon__.getSetting(bulbid + "_saveron_action"))
            bulbs[c].saveron_intensity = int(__addon__.getSetting(bulbid + "_saveron_intensity"))
            bulbs[c].saveron_color = __addon__.getSetting(bulbid + "_saveron_color")
            bulbs[c].saveron_effect = int(__addon__.getSetting(bulbid + "_saveron_effect"))
            bulbs[c].saveron_duration = int(__addon__.getSetting(bulbid + "_saveron_duration"))

            bulbs[c].saveroff_action = int(__addon__.getSetting(bulbid + "_saveroff_action"))
            bulbs[c].saveroff_intensity = int(__addon__.getSetting(bulbid + "_saveroff_intensity"))
            bulbs[c].saveroff_color = __addon__.getSetting(bulbid + "_saveroff_color")
            bulbs[c].saveroff_effect = int(__addon__.getSetting(bulbid + "_saveroff_effect"))
            bulbs[c].saveroff_duration = int(__addon__.getSetting(bulbid + "_saveroff_duration"))

            if bulbs[c].model == 'ceiling4':
                bulbs[c].play_bg_action = int(__addon__.getSetting(bulbid + "_play_bg_action"))
                bulbs[c].play_bg_intensity = int(__addon__.getSetting(bulbid + "_play_bg_intensity"))
                bulbs[c].play_bg_color = __addon__.getSetting(bulbid + "_play_bg_color")
                bulbs[c].play_bg_effect = int(__addon__.getSetting(bulbid + "_play_bg_effect"))
                bulbs[c].play_bg_duration = int(__addon__.getSetting(bulbid + "_play_bg_duration"))

                bulbs[c].stop_bg_action = int(__addon__.getSetting(bulbid + "_stop_bg_action"))
                bulbs[c].stop_bg_intensity = int(__addon__.getSetting(bulbid + "_stop_bg_intensity"))
                bulbs[c].stop_bg_color = __addon__.getSetting(bulbid + "_stop_bg_color")
                bulbs[c].stop_bg_effect = int(__addon__.getSetting(bulbid + "_stop_bg_effect"))
                bulbs[c].stop_bg_duration = int(__addon__.getSetting(bulbid + "_stop_bg_duration"))

                bulbs[c].pause_bg_action = int(__addon__.getSetting(bulbid + "_pause_bg_action"))
                bulbs[c].pause_bg_intensity = int(__addon__.getSetting(bulbid + "_pause_bg_intensity"))
                bulbs[c].pause_bg_color = __addon__.getSetting(bulbid + "_pause_bg_color")
                bulbs[c].pause_bg_effect = int(__addon__.getSetting(bulbid + "_pause_bg_effect"))
                bulbs[c].pause_bg_duration = int(__addon__.getSetting(bulbid + "_pause_bg_duration"))

                bulbs[c].saveron_bg_action = int(__addon__.getSetting(bulbid + "_saveron_action"))
                bulbs[c].saveron_bg_intensity = int(__addon__.getSetting(bulbid + "_saveron_intensity"))
                bulbs[c].saveron_bg_color = __addon__.getSetting(bulbid + "_saveron_color")
                bulbs[c].saveron_bg_effect = int(__addon__.getSetting(bulbid + "_saveron_effect"))
                bulbs[c].saveron_bg_duration = int(__addon__.getSetting(bulbid + "_saveron_duration"))

                bulbs[c].saveroff_bg_action = int(__addon__.getSetting(bulbid + "_saveroff_action"))
                bulbs[c].saveroff_bg_intensity = int(__addon__.getSetting(bulbid + "_saveroff_intensity"))
                bulbs[c].saveroff_bg_color = __addon__.getSetting(bulbid + "_saveroff_color")
                bulbs[c].saveroff_bg_effect = int(__addon__.getSetting(bulbid + "_saveroff_effect"))
                bulbs[c].saveroff_bg_duration = int(__addon__.getSetting(bulbid + "_saveroff_duration"))

                if bulbs[c].play_bg_color[0] != "#":
                    bulbs[c].play_bg_color = "#" + bulbs[c].play_bg_color
                    __addon__.setSetting(bulbid + "_play_bg_color", bulbs[c].play_bg_color)

                if bulbs[c].stop_bg_color[0] != "#":
                    bulbs[c].stop_bg_color = "#" + bulbs[c].stop_bg_color
                    __addon__.setSetting(bulbid + "_stop_bg_color", bulbs[c].stop_bg_color)

                if bulbs[c].pause_bg_color[0] != "#":
                    bulbs[c].pause_bg_color = "#" + bulbs[c].pause_bg_color
                    __addon__.setSetting(bulbid + "_pause_bg_color", bulbs[c].pause_bg_color)

                if bulbs[c].saveron_bg_color[0] != "#":
                    bulbs[c].saveron_bg_color = "#" + bulbs[c].saveron_bg_color
                    __addon__.setSetting(bulbid + "_saveron_bg_color", bulbs[c].saveron_bg_color)

                if bulbs[c].saveroff_bg_color[0] != "#":
                    bulbs[c].saveroff_bg_color = "#" + bulbs[c].saveroff_bg_color
                    __addon__.setSetting(bulbid + "_saveroff_bg_color", bulbs[c].saveroff_bg_color)

                if not validColor(bulbs[c].play_bg_color):
                    errstr = "Bulb number " + str(x) + " (Play bg) has no valid hex color: " + str(bulbs[c].play_bg_color)
                    xbmc.log("YEEMEE >> " + errstr.upper())
                    errors = True

                if not validColor(bulbs[c].stop_bg_color):
                    errstr = "Bulb number " + str(x) + " (Stop bg) has no valid hex color: " + str(bulbs[c].stop_bg_color)
                    xbmc.log("YEEMEE >> " + errstr.upper())
                    errors = True

                if not validColor(bulbs[c].pause_bg_color):
                    errstr = "Bulb number " + str(x) + " (Pause bg) has no valid hex color: " + str(bulbs[c].pause_bg_color)
                    xbmc.log("YEEMEE >> " + errstr)
                    errors = True

                if not validColor(bulbs[c].saveron_bg_color):
                    errstr = "Bulb number " + str(x) + " (Saver bg on) has no valid hex color: " + str(bulbs[c].saveron_bg_color)
                    xbmc.log("YEEMEE >> " + errstr.upper())
                    errors = True

                if not validColor(bulbs[c].saveroff_bg_color):
                    errstr = "Bulb number " + str(x) + " (Saver bg off) has no valid hex color: " + str(bulbs[c].saveroff_bg_color)
                    xbmc.log("YEEMEE >> " + errstr.upper())
                    errors = True

            if bulbs[c].play_color[0] != "#":
                bulbs[c].play_color = "#" + bulbs[c].play_color
                __addon__.setSetting(bulbid + "_play_color", bulbs[c].play_color)

            if bulbs[c].stop_color[0] != "#":
                bulbs[c].stop_color = "#" + bulbs[c].stop_color
                __addon__.setSetting(bulbid + "_stop_color", bulbs[c].stop_color)

            if bulbs[c].pause_color[0] != "#":
                bulbs[c].pause_color = "#" + bulbs[c].pause_color
                __addon__.setSetting(bulbid + "_pause_color", bulbs[c].pause_color)

            if bulbs[c].saveron_color[0] != "#":
                bulbs[c].saveron_color = "#" + bulbs[c].saveron_color
                __addon__.setSetting(bulbid + "_saveron_color", bulbs[c].saveron_color)

            if bulbs[c].saveroff_color[0] != "#":
                bulbs[c].saveroff_color = "#" + bulbs[c].saveroff_color
                __addon__.setSetting(bulbid + "_saveroff_color", bulbs[c].saveroff_color)

            if not validColor(bulbs[c].play_color):
                errstr = "Bulb number " + str(x) + " (Play) has no valid hex color: " + str(bulbs[c].play_color)
                xbmc.log("YEEMEE >> " + errstr.upper())
                errors = True

            if not validColor(bulbs[c].stop_color):
                errstr = "Bulb number " + str(x) + " (Stop) has no valid hex color: " + str(bulbs[c].stop_color)
                xbmc.log("YEEMEE >> " + errstr.upper())
                errors = True

            if not validColor(bulbs[c].pause_color):
                errstr = "Bulb number " + str(x) + " (Pause) has no valid hex color: " + str(bulbs[c].pause_color)
                xbmc.log("YEEMEE >> " + errstr)
                errors = True

            if not validColor(bulbs[c].saveron_color):
                errstr = "Bulb number " + str(x) + " (Saver) has no valid hex color: " + str(bulbs[c].saveron_color)
                xbmc.log("YEEMEE >> " + errstr.upper())
                errors = True

            if not validColor(bulbs[c].saveroff_color):
                errstr = "Bulb number " + str(x) + " (Saver off) has no valid hex color: " + str(bulbs[c].saveroff_color)
                xbmc.log("YEEMEE >> " + errstr.upper())
                errors = True

            c += 1
        else:
            errstr = "Bulb number " + str(x) + " does not have a valid IP address (" + ipaddr.encode('utf8') + ") assigned!"
            xbmc.log("YEEMEE >> " + errstr.upper())
            errors = True

    xbmc.log('YEEMEE >> NUMBER OF ACTIVE BULBS >> ' + str(len(bulbs)))

    numberOfColorBulbs = 0

    for i, x in enumerate(bulbs):
        xbmc.log("YEEMEE >> Number           Act Int Color   Eff Duration")
        xbmc.log("YEEMEE >> BULB %d PLAY     : %3d %3d %s %3d %4d" % (i, x.play_action, x.play_intensity, x.play_color, x.play_effect, x.play_duration))
        xbmc.log("YEEMEE >> BULB %d STOP     : %3d %3d %s %3d %4d" % (i, x.stop_action, x.stop_intensity, x.stop_color, x.stop_effect, x.stop_duration))
        xbmc.log("YEEMEE >> BULB %d PAUSE    : %3d %3d %s %3d %4d" % (i, x.pause_action, x.pause_intensity, x.pause_color, x.pause_effect, x.pause_duration))

        xbmc.log("YEEMEE >> BULB %d SAVERON  : %3d %3d %s %3d %4d" % (i, x.saveron_action, x.saveron_intensity, x.saveron_color, x.saveron_effect, x.saveron_duration))
        xbmc.log("YEEMEE >> BULB %d SAVEROFF : %3d %3d %s %3d %4d" % (i, x.saveroff_action, x.saveroff_intensity, x.saveroff_color, x.saveroff_effect, x.saveroff_duration))


        if x.model == 'ceiling4':
            xbmc.log("YEEMEE >> BULB %d PLAY BG  : %3d %3d %s %3d %4d" % (i, x.play_bg_action, x.play_bg_intensity, x.play_bg_color, x.play_bg_effect, x.play_bg_duration))
            xbmc.log("YEEMEE >> BULB %d STOP BG  : %3d %3d %s %3d %4d" % (i, x.stop_bg_action, x.stop_bg_intensity, x.stop_bg_color, x.stop_bg_effect, x.stop_bg_duration))
            xbmc.log("YEEMEE >> BULB %d PAUSE BG : %3d %3d %s %3d %4d" % (i, x.pause_bg_action, x.pause_bg_intensity, x.pause_bg_color, x.pause_bg_effect, x.pause_bg_duration))

            xbmc.log("YEEMEE >> BULB %d SAVERON BG  : %3d %3d %s %3d %4d" % (i, x.saveron_bg_action, x.saveron_bg_intensity, x.saveron_bg_color, x.saveron_bg_effect, x.saveron_bg_duration))
            xbmc.log("YEEMEE >> BULB %d SAVEROFF BG : %3d %3d %s %3d %4d" % (i, x.saveroff_bg_action, x.saveroff_bg_intensity, x.saveroff_bg_color, x.saveroff_bg_effect, x.saveroff_bg_duration))

        xbmc.log("YEEMEE >> BULB %d AMBI     : %d BIAS: %d" % (i, x.ambipos, x.bias))
        if (x.model == 'color' or x.model == 'stripe' or x.model == 'ceiling4') and x.ambipos > 0:
            numberOfColorBulbs += 1

    xbmc.log('YEEMEE >> NUMBER OF AMBI BULBS >> ' + str(numberOfColorBulbs))

    numberOfControllers = int(__addon__.getSetting("numberOfControllers"))
    xbmc.log('YEEMEE >> NUMBER OF CONTROLLERS >> ' + str(numberOfControllers))
    MsgControllerOn = int(__addon__.getSetting("MsgControllerOn"))
    MsgUrlOn = int(__addon__.getSetting("MsgUrlOn"))

    controllers = []

    c = 0
    for x in range(1, numberOfControllers + 1):
        controllerid = "controller_" + str(x)
        ipaddr = __addon__.getSetting(controllerid)
        if validIP(ipaddr):
            controllers.append(ipaddr)
            c += 1
        else:
            errstr = "Controller number " + str(x) + " does not have a valid IP address (" + ipaddr.encode('utf8') + ") assigned!"
            xbmc.log("YEEMEE >> " + errstr.upper())
            errors = True

    for i, x in enumerate(controllers, 0):
        xbmc.log("YEEMEE >> CONTROLLER " + str(i) + ": " + str(x))

    if errors and par1 == 1:
        dialog = xbmcgui.Dialog()
        dialog.ok(__addonname__.encode('utf8'), errstr)
        __addon__.openSettings()

# ============================================================
# Check if IP adress is valid
# ============================================================


def validIP(address):
    if re.match(r'^((\d{1,2}|1\d{2}|2[0-4]\d|25[0-5])\.){3}(\d{1,2}|1\d{2}|2[0-4]\d|25[0-5])$', address):
        return True
    else:
        return False

# ============================================================
# Check if URL is valid
# ============================================================


def validURL(address):
    pattern = re.compile(
        r'^(?:http|ftp)s?://'                           # http:// or https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|'    # domain...
        r'localhost|'                                   # localhost...
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'          # ...or ip
        r'(?::\d+)?'                                    # optional port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)

    if pattern.match(address):
        return True
    else:
        return False

# ============================================================
# Check if string is valid hex color code
# ============================================================


def validColor(code):
    if re.match(r'^#(?:[0-9a-fA-F]{3}){1,2}$', code):
        return True
    else:
        return False

# ============================================================
# Get location
# ============================================================


def getLoc():
    url = "http://ip-api.com/json"
    response = ''

    try:
        r = requests.get(url)
        data = r.json()
        lat = str(data["lat"])
        lng = str(data["lon"])
        response = data["status"]
    except Exception as e:
        xbmc.log("YEEMEE >> ERROR GETTING LOCATION: " + str(e).encode('utf-8'))
        xbmc.executebuiltin("Dialog.Close(busydialog)")

    if response == "success":
        if "." not in lat:
            lat = lat + ".0"
        if "." not in lng:
            lng = lng + ".0"

        xbmc.log("YEEMEE >> GOT CURRENT LAT-LON: " + str(lat) + ", " + str(lng))
        __addon__.setSetting("Lat", str(lat))
        __addon__.setSetting("Lon", str(lng))
    else:
        lat = __addon__.getSetting("Lat")
        lng = __addon__.getSetting("Lon")
        xbmc.log("YEEMEE >> COULD NOT GET CURRENT LAT-LON, USING SAVED: " + str(lat) + ", " + str(lng))

# ============================================================
# Time by location - get sunset and sunrise for current loc
# ============================================================


def byLoc():
    xbmc.executebuiltin("ActivateWindow(busydialog)")

    lat = __addon__.getSetting("Lat")
    lng = __addon__.getSetting("Lon")

    ts = 1288483950000 * 1e-3
    utc_offset = datetime.datetime.fromtimestamp(ts) - datetime.datetime.utcfromtimestamp(ts)
    xbmc.log("YEEMEE >> GOT TIMEZONE OFFSET: " + str(utc_offset))

    url = "http://api.sunrise-sunset.org/json?lat=" + str(lat) + "&lng=" + str(lng)
    try:
        r = requests.get(url)
        data = r.json()
    except Exception as e:
        xbmc.log("YEEMEE >> ERROR GETTING SUNRISE-SUNSET: " + str(e).encode('utf-8'))
        xbmc.executebuiltin("Dialog.Close(busydialog)")
        return "", "", "", ""

    sunrise = data["results"]["sunrise"]
    sunset = data["results"]["sunset"]

    civil_tw = data["results"]["civil_twilight_end"]
    nautic_tw = data["results"]["nautical_twilight_end"]

    response = data["status"]

    if response == "OK":
        datetime_sunrise = mystr2time(sunrise, '%I:%M:%S %p')

        if datetime_sunrise != 0:
            datetime_sunrise = datetime.datetime.combine(datetime.date(1, 1, 1), datetime_sunrise.time()) + utc_offset

            tem = str(datetime_sunrise)[-8:]
            h, m, s = tem.split(':')
            sunrise = h + ":" + m
            xbmc.log("YEEMEE >> GOT CURRENT SUNRISE: " + str(sunrise))
        else:
            xbmc.log("YEEMEE >> COULD NOT RETRIEVE SUNSET+SUNRISE")

        datetime_sunset = mystr2time(sunset, '%I:%M:%S %p')
        if datetime_sunset != 0:
            datetime_sunset = datetime.datetime.combine(datetime.date.today(), datetime_sunset.time()) + utc_offset

            tem = str(datetime_sunset)[-8:]
            h, m, s = tem.split(':')
            sunset = h + ":" + m
            xbmc.log("YEEMEE >> GOT CURRENT SUNSET: " + str(sunset))
        else:
            xbmc.log("YEEMEE >> COULD NOT RETRIEVE SUNSET")

        datetime_civil_tw = mystr2time(civil_tw, '%I:%M:%S %p')
        if datetime_civil_tw != 0:
            datetime_civil_tw = datetime.datetime.combine(datetime.date.today(), datetime_civil_tw.time()) + utc_offset

            tem = str(datetime_civil_tw)[-8:]
            h, m, s = tem.split(':')
            civil_tw = h + ":" + m
            xbmc.log("YEEMEE >> GOT CIVIL TW: " + str(civil_tw))
        else:
            xbmc.log("YEEMEE >> COULD NOT RETRIEVE CIVIL TW")

        datetime_nautic_tw = mystr2time(nautic_tw, '%I:%M:%S %p')
        if datetime_nautic_tw != 0:
            datetime_nautic_tw = datetime.datetime.combine(datetime.date.today(), datetime_nautic_tw.time()) + utc_offset

            tem = str(datetime_nautic_tw)[-8:]
            h, m, s = tem.split(':')
            nautic_tw = h + ":" + m
            xbmc.log("YEEMEE >> GOT NAUTIC TW: " + str(nautic_tw))
        else:
            xbmc.log("YEEMEE >> COULD NOT RETRIEVE NAUTIC TW")
    else:
        xbmc.log("YEEMEE >> COULD NOT RETRIEVE SUNSET+SUNRISE+TW")

    xbmc.executebuiltin("Dialog.Close(busydialog)")

    return str(sunrise), str(sunset), str(civil_tw), str(nautic_tw)

# ------------------------------------------------------------
# ============================================================
# Player class
# ============================================================
# ------------------------------------------------------------


class XBMCPlayer(xbmc.Player):
    def __init__(self):
        xbmc.Player.__init__(self)

# ============================================================
# Player class - play started - Krypton + Jarvis
# ============================================================

    def onPlayBackStarted(self):
        global isVideo
        global MsgControllerOn
        global MsgUrlOn
        global kodiVer

        if int(float(kodiVer)) > 17:                     # above Krypton
            return

        xbmc.log('YEEMEE >> PLAYBACK >>PLAYING KRYPTON<<')
        if self.isPlayingVideo():
            isVideo = True

            if MsgControllerOn > 0:
                message_controller("start")
            if MsgUrlOn > 0:
                url_controller("play")

            state_changed("start")
        else:
            isVideo = False

            if MsgControllerOn != 1:
                message_controller("start")
            if MsgUrlOn != 1:
                url_controller("play")

# ============================================================
# Player class - play started - Leia
# ============================================================

    def onAVStarted(self):
        global isVideo
        global MsgControllerOn
        global MsgUrlOn
        global kodiVer

        if int(float(kodiVer)) < 18:                     # Leia and below
            return

        xbmc.log('YEEMEE >> PLAYBACK >>PLAYING LEIA<<')
        if self.isPlayingVideo():
            isVideo = True

            if MsgControllerOn > 0:
                message_controller("start")
            if MsgUrlOn > 0:
                url_controller("play")

            state_changed("start")
        else:
            isVideo = False

            if MsgControllerOn != 1:
                message_controller("start")
            if MsgUrlOn != 1:
                url_controller("play")

# ============================================================
# Player class - paused
# ============================================================

    def onPlayBackPaused(self):
        global isVideo

        xbmc.log('YEEMEE >> PLAYBACK >>PAUSED<<')
        if self.isPlayingVideo():
            isVideo = True

            state_changed("pause")
        else:
            isVideo = False

# ============================================================
# Player class - resumed
# ============================================================

    def onPlayBackResumed(self):
        global isVideo

        xbmc.log('YEEMEE >> PLAYBACK >>RESUMED<<')
        if self.isPlayingVideo():
            isVideo = True

            state_changed("play")
        else:
            isVideo = False

# ============================================================
# Player class - stopped
# ============================================================

    def onPlayBackStopped(self):
        global isVideo
        global MsgControllerOn
        global MsgUrlOn

        xbmc.log('YEEMEE >> PLAYBACK >>STOPPED<<')
        if isVideo:
            if MsgControllerOn > 0:
                message_controller("stop")
            if MsgUrlOn > 0:
                url_controller("stop")

            state_changed("stop")
        else:
            if MsgControllerOn != 1:
                message_controller("stop")
            if MsgUrlOn != 1:
                url_controller("stop")


# ============================================================
# Player class - ended
# ============================================================

    def onPlayBackEnded(self):
        global isVideo
        global MsgControllerOn
        global MsgUrlOn

        xbmc.log('YEEMEE >> PLAYBACK >>ENDED<<')
        if isVideo:
            if MsgControllerOn > 0:
                message_controller("stop")
            if MsgUrlOn > 0:
                url_controller("stop")

            state_changed("stop")
        else:
            if MsgControllerOn != 1:
                message_controller("stop")
            if MsgUrlOn != 1:
                url_controller("stop")


# ============================================================
# Playback state changed, send message to controller(s)
# ============================================================


def message_controller(action):
    global numberOfControllers
    global controllers

    strCover = xbmc.getInfoLabel('Player.Art(thumb)')               # do not activate if ATV (video) screensaver
    if "screensaver.atv4" in strCover:
        if os.path.isfile(strCover):
            return False

    strTitle = xbmc.getInfoLabel('VideoPlayer.Title')               # do not activate if Video screensaver
    try:
        videoSaver = xbmcaddon.Addon(id='screensaver.video')
        strVideosaverPath = videoSaver.getSetting('screensaverFolder')
        if strVideosaverPath in strTitle:
            return False
    except Exception:
        pass

    if numberOfControllers > 0:
        for i, x in enumerate(controllers, 0):
            addr = "http://" + str(x) + ":8765"
            try:
                r = requests.post(addr, params=action)

                if r.status_code != 200:
                    xbmc.log("YEEMEE >> ERROR SENDING MESSAGE TO CONTROLLER " + addr + ", STATUS CODE: " + str(r.status_code).encode('utf-8'))
                else:
                    xbmc.log("YEEMEE >> SENT MESSAGE TO CONTROLLER " + addr + ": " + action)
            except Exception as e:
                xbmc.log("YEEMEE >> ERROR SENDING MESSAGE TO CONTROLLER " + addr + ": " + str(e).encode('utf-8'))

# ============================================================
# Playback state changed, send message to controller(s)
# ============================================================


def url_controller(action):
    strCover = xbmc.getInfoLabel('Player.Art(thumb)')               # do not activate if ATV (video) screensaver
    if "screensaver.atv4" in strCover:
        if os.path.isfile(strCover):
            return False

    strTitle = xbmc.getInfoLabel('VideoPlayer.Title')               # do not activate if Video screensaver
    try:
        videoSaver = xbmcaddon.Addon(id='screensaver.video')
        strVideosaverPath = videoSaver.getSetting('screensaverFolder')
        if strVideosaverPath in strTitle:
            return False
    except Exception:
        pass

    param = "control_url_" + action
    link = __addon__.getSetting(param)

    if link != "" and validURL(link):
        try:
            f = urllib.urlopen(link)
            page = f.read()
        except Exception:
            pass

# ============================================================
# Playback state changed, react
# ============================================================


def state_changed(player_state):
    global bulbs
    global timeOn
    global timeOnStart
    global timeOnEnd
    global ServiceOn
    global disablePvr
    global AmbiOn
    global intDuration
    global disableShort
    global disableShortTime
    global numberOfColorBulbs
    global stopHandler
    global YeePriority
    global YeePauseLower
    global isPvr
    global isStream
    global thread_started
    global rt

    if (not ServiceOn) and (not AmbiOn):                            # do not activate if yee service and ambi both off
        return

    if disablePvr:                                                  # do not activate if it is a PVR
        if player_state == "stop":
            if isPvr == "pvr://":
                xbmc.log("YEEMEE >> DISABLE PVR: QUITTING")
                return False

            if isStream == "":                                      # do not activate if it is a live stream
                xbmc.log("YEEMEE >> DISABLE LIVE STREAM: QUITTING")
                return False
        else:
            filename = xbmc.getInfoLabel('Player.Filenameandpath')
            isPvr = filename[:6]
            if isPvr == "pvr://":
                xbmc.log("YEEMEE >> DISABLE PVR: QUITTING")
                return False

            isStream = xbmc.getInfoLabel('VideoPlayer.Duration')     # do not activate if it is a live stream
            if isStream == "":
                xbmc.log("YEEMEE >> DISABLE LIVE STREAM: QUITTING")
                return False

    strCover = xbmc.getInfoLabel('Player.Art(thumb)')                # do not activate if ATV (video) screensaver
    if "screensaver.atv4" in strCover:
        if os.path.isfile(strCover):
            xbmc.log("YEEMEE >> DISABLE ATV SCREENSAVER: QUITTING")
            return False

    strTitle = xbmc.getInfoLabel('VideoPlayer.Title')                # do not activate if Video screensaver
    try:
        videoSaver = xbmcaddon.Addon(id='screensaver.video')
        strVideosaverPath = videoSaver.getSetting('screensaverFolder')
        if strVideosaverPath in strTitle:
            xbmc.log("YEEMEE >> DISABLE VIDEO SCREEN SAVER: QUITTING")
            return False
    except Exception:
        pass

    if player_state == "stop":                                       # disabled for short movies
        if disableShort and (intDuration < disableShortTime):
            xbmc.log("YEEMEE >> DISABLE FOR SHORT MOVIES: %s < %s: QUITTING" % (str(intDuration), str(disableShortTime), ))
            return False
    else:
        strDuration = xbmc.getInfoLabel('VideoPlayer.Duration')
        TimeFormat = strDuration.count(':')

        if TimeFormat == 1:
            m, s = strDuration.split(':')
            intDuration = int(m)
        elif TimeFormat == 2:
            h, m, s = strDuration.split(':')
            intDuration = int(h) * 60 + int(m)
        else:
            intDuration = 0

        if disableShort and (intDuration < disableShortTime):
            xbmc.log("YEEMEE >> DISABLE FOR SHORT MOVIES: %s < %s: QUITTING" % (str(intDuration), str(disableShortTime), ))
            return False

    xbmc.log("YEEMEE >> ACTIVATION TIME ON/OFF: " + str(timeOn))     # check activation time
    if timeOn > 0:
        now = datetime.datetime.now()
        strNowTime = '%02d:%02d:%02d' % (now.hour, now.minute, now.second)
        nowTime = mystr2time(strNowTime, '%H:%M:%S').time()

        if nowTime > timeOnStart or nowTime < timeOnEnd:
            xbmc.log("YEEMEE >> IN TIME FRAME: " + str(timeOnStart) + " - (" + str(nowTime) + ") - " + str(timeOnEnd))
        else:
            xbmc.log("YEEMEE >> NOT IN TIME FRAME, QUITTING: " + str(timeOnStart) + " - (" + str(nowTime) + ") - " + str(timeOnEnd))
            return False

    if AmbiOn and numberOfColorBulbs > 0:                            # ambilight
        if player_state == "stop":
            for x in bulbs:
                if x.model == "ceiling4":
                    xbmc.log("YEEMEE >> CEILING 650 - STOP")
                    rt.stop()
                    break

            stopHandler = True
            stopServer()
            xbmc.sleep(500)

        elif player_state == "start":
            stopHandler = False
            thread.start_new_thread(grabloop, (None,))
            host_ip = get_ip()
            thread.start_new_thread(startServer, (host_ip,))

            for x in bulbs:
                if x.model == "ceiling4":
                    xbmc.log("YEEMEE >> CEILING 650 - START")
                    rt.start()
                    break

    for x in bulbs:
        if player_state == "stop":
            if AmbiOn and x.ambipos > 0:                           # ambilight
                x.paused = False

                if x.model == "ceiling4":                           # @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@ CEILING4
                    data = json.dumps({"id": 1, "method": "get_prop", "params": ["bg_power"]})
                    result1, result2 = x.sendMessage(data)
                    if result1 == "on":
                        data = json.dumps({"id": 1, "method": "bg_set_power", "params": ["off", "smooth", 500]})
                        x.sendMessage(data)
                        xbmc.sleep(100)

            if ServiceOn:                                          # normal operation
                if x.stop_action == 3:
                    if x.initial_state == "off":
                        x.turnOff(player_state)
                    else:
                        x.turnOn(player_state)
                elif x.stop_action == 2:
                    x.turnOn(player_state)
                elif x.stop_action == 1:
                    x.turnOff(player_state)

                if x.model == "ceiling4":                        # @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@ CEILING4
                    if x.stop_bg_action == 3:
                        if x.initial_bg_state == "off":
                            x.turnOff_bg(player_state)
                        else:
                            x.turnOn_bg(player_state)
                    elif x.stop_bg_action == 2:
                        x.turnOn_bg(player_state)
                    elif x.stop_bg_action == 1:
                        x.turnOff_bg(player_state)

        elif player_state == "pause":
            if AmbiOn and x.ambipos > 0 and YeePriority == 1:      # ambilight
                if YeePauseLower < 100:
                    x.paused = True

            if (not AmbiOn and ServiceOn) or (ServiceOn and x.ambipos == 0) or (ServiceOn and AmbiOn and x.ambipos > 0 and YeePriority == 0):
                if x.pause_action == 2:
                    x.turnOn(player_state)
                elif x.pause_action == 1:
                    x.turnOff(player_state)

                if x.model == "ceiling4":                        # @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@ CEILING4
                    if x.pause_bg_action == 2:
                        x.turnOn_bg(player_state)
                    elif x.pause_bg_action == 1:
                        x.turnOff_bg(player_state)

        elif player_state == "play":
            if AmbiOn and x.ambipos > 0:                           # ambilight
                x.paused = False

                if YeePriority == 0 and (not thread_started):
                    if x.play_action == 2:
                        if x.model == "ceiling4":                # @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@ CEILING4
                            x.turnOn_bg(player_state)
                        else:
                            x.turnOn(player_state)
                    elif x.play_action == 1:
                        if x.model == "ceiling4":                # @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@ CEILING4
                            x.turnOff_bg(player_state)
                        else:
                            x.turnOff(player_state)
            elif ServiceOn:                                        # normal operation
                if x.play_action == 2:
                    x.turnOn(player_state)
                elif x.play_action == 1:
                    x.turnOff(player_state)

                if x.model == "ceiling4":                       # @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@ CEILING4
                    if x.play_bg_action == 2:
                        x.turnOn_bg(player_state)
                    elif x.play_bg_action == 1:
                        x.turnOff_bg(player_state)

        elif player_state == "start":
            bulb_state = x.getState()
            x.initial_state = bulb_state

            if x.model == "ceiling4":                           # @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@ CEILING4
                bulb_state = x.getState_bg()
                x.initial_bg_state = bulb_state

            if AmbiOn and x.ambipos > 0:                           # ambilight
                x.paused = False

                if x.model != "mono" and x.model != "ceiling" and x.model != "ct_bulb" and x.ambipos > 0:
                    if x.model == "ceiling4":                           # @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@ CEILING4
                        data = json.dumps({"id": 1, "method": "get_prop", "params": ["power"]})
                        result1, result2 = x.sendMessage(data)
                        if result1 == "off":
                            data = json.dumps({"id": 1, "method": "bg_set_power", "params": ["on", "smooth", 200]})
                            x.sendMessage(data)
                            xbmc.sleep(100)
                    else:
                        data = json.dumps({"id": 1, "method": "get_prop", "params": ["power", "music_on"]})
                        result1, result2 = x.sendMessage(data)
                        if result1 == "off":
                            data = json.dumps({"id": 1, "method": "set_power", "params": ["on", "smooth", 200]})
                            x.sendMessage(data)
                            xbmc.sleep(100)
                        if result2 == "0":
                            data = json.dumps({"id": 1, "method": "set_music", "params": [1, host_ip, 55440]})
                            x.sendMessage(data)
            elif ServiceOn:                                        # normal operation
                if x.play_action == 2:
                    x.turnOn(player_state)
                elif x.play_action == 1:
                    x.turnOff(player_state)

                # @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@ CEILING4
                if x.model == "ceiling4":
                    if x.play_bg_action == 2:
                        x.turnOn_bg(player_state)
                    elif x.play_bg_action == 1:
                        x.turnOff_bg(player_state)


# ------------------------------------------------------------
# ============================================================
# Define Yeelight class
# ============================================================
# ------------------------------------------------------------


class Yeelight:
    connected = None

# ============================================================
# Yeelight class - Initialize
# ============================================================

    def __init__(self, IPadresss):
        self.bulb_ip = IPadresss
        self.bulb_port = 55443
        self.initial_state = ""
        self.initial_bg_state = ""
        self.on_start = False
        self.on_bg_start = False
        self.model = ""

        self.play_action = 0
        self.play_intensity = 0
        self.play_color = ""
        self.play_effect = 0
        self.play_duration = 0

        self.play_bg_action = 0
        self.play_bg_intensity = 0
        self.play_bg_color = ""
        self.play_bg_effect = 0
        self.play_bg_duration = 0

        self.stop_action = 0
        self.stop_intensity = 0
        self.stop_color = ""
        self.stop_effect = 0
        self.stop_duration = 0

        self.stop_bg_action = 0
        self.stop_bg_intensity = 0
        self.stop_bg_color = ""
        self.stop_bg_effect = 0
        self.stop_bg_duration = 0

        self.pause_action = 0
        self.pause_intensity = 0
        self.pause_color = ""
        self.pause_effect = 0
        self.pause_duration = 0

        self.pause_bg_action = 0
        self.pause_bg_intensity = 0
        self.pause_bg_color = ""
        self.pause_bg_effect = 0
        self.pause_bg_duration = 0

        self.ambipos = 0
        self.paused = False
        self.bias = 0
        self.applyColorsH = 0
        self.applyColorsL = 0
        self.applyColorsS = 0

        self.saveron_action = 0
        self.saveron_intensity = 0
        self.saveron_color = ""
        self.saveron_effect = 0
        self.saveron_duration = 0

        self.saveron_bg_action = 0
        self.saveron_bg_intensity = 0
        self.saveron_bg_color = ""
        self.saveron_bg_effect = 0
        self.saveron_bg_duration = 0

        self.saveroff_action = 0
        self.saveroff_intensity = 0
        self.saveroff_color = ""
        self.saveroff_effect = 0
        self.saveroff_duration = 0

        self.saveroff_bg_action = 0
        self.saveroff_bg_intensity = 0
        self.saveroff_bg_color = ""
        self.saveroff_bg_effect = 0
        self.saveroff_bg_duration = 0

# ============================================================
# Yeelight class - Turn off bulb
# ============================================================

    def turnOff(self, action):
        global __addon__
        global reportErrors

        effect = "smooth"

        if action == "play":
            duration = self.play_duration
            if self.play_effect == 0:
                effect = "sudden"
        elif action == "pause":
            duration = self.pause_duration
            if self.pause_effect == 0:
                effect = "sudden"
        elif action == "blink":
            duration = 0
            effect = "sudden"
        elif action == "stopsaver":
            duration = self.saveroff_duration
            if self.saveroff_effect == 0:
                effect = "sudden"
        else:
            duration = self.stop_duration
            if self.stop_effect == 0:
                effect = "sudden"

        if (self.model != "mono") and (self.model != "ceiling") and (self.model != "ct_bulb"):
            message = {"id": 1, "method": "stop_cf", "params": []}
            result = self.connect(message, self.bulb_ip, self.bulb_port)

            a = ""
            try:
                a = json.loads(result)["result"][0]
            except Exception:
                try:
                    a = json.loads(result)["error"]["message"]
                except Exception:
                    if reportErrors:
                        strMess = __addon__.getLocalizedString(32101) + "\n" + a     # Error while trying to connect to bulb!
                        a = strMess
                        xbmc.executebuiltin("XBMC.Notification(%s,%s,2000,%s)" % ('YeeMee', strMess, __addon__.getAddonInfo('icon')))

            xbmc.log("YEEMEE >> %s: STOP CF RESULT >> %s" % (self.bulb_ip, a))
            xbmc.sleep(300)

        message = {"id": 1, "method": "set_power", "params": ["off", effect, duration]}
        result = self.connect(message, self.bulb_ip, self.bulb_port)

        a = ""
        try:
            a = json.loads(result)["result"][0]
        except Exception:
            try:
                a = json.loads(result)["error"]["message"]
            except Exception:
                if reportErrors:
                    strMess = __addon__.getLocalizedString(32101) + "\n" + a     # Error while trying to connect to bulb!
                    a = strMess
                    xbmc.executebuiltin("XBMC.Notification(%s,%s,2000,%s)" % ('YeeMee', strMess, __addon__.getAddonInfo('icon')))

        xbmc.log("YEEMEE >> %s: TURN OFF RESULT >> %s" % (self.bulb_ip, a))

# ============================================================
# Yeelight class - Turn off bg_bulb
# ============================================================

    def turnOff_bg(self, action):
        global __addon__
        global reportErrors

        effect = "smooth"

        if action == "play":
            duration = self.play_bg_duration
            if self.play_bg_effect == 0:
                effect = "sudden"
        elif action == "pause":
            duration = self.pause_bg_duration
            if self.pause_bg_effect == 0:
                effect = "sudden"
        elif action == "blink":
            duration = 0
            effect = "sudden"
        elif action == "stopsaver":
            duration = self.saveroff_bg_duration
            if self.saveroff_bg_effect == 0:
                effect = "sudden"
        else:
            duration = self.stop_bg_duration
            if self.stop_bg_effect == 0:
                effect = "sudden"

        if (self.model == "ceiling4"):
            message = {"id": 1, "method": "bg_stop_cf", "params": []}
            result = self.connect(message, self.bulb_ip, self.bulb_port)

            a = ""
            try:
                a = json.loads(result)["result"][0]
            except Exception:
                try:
                    a = json.loads(result)["error"]["message"]
                except Exception:
                    if reportErrors:
                        strMess = __addon__.getLocalizedString(32101) + "\n" + a     # Error while trying to connect to bulb!
                        a = strMess
                        xbmc.executebuiltin("XBMC.Notification(%s,%s,2000,%s)" % ('YeeMee', strMess, __addon__.getAddonInfo('icon')))

            xbmc.log("YEEMEE >> %s: STOP CF RESULT >> %s" % (self.bulb_ip, a))
            xbmc.sleep(300)

        message = {"id": 1, "method": "bg_set_power", "params": ["off", effect, duration]}
        result = self.connect(message, self.bulb_ip, self.bulb_port)

        a = ""
        try:
            a = json.loads(result)["result"][0]
        except Exception:
            try:
                a = json.loads(result)["error"]["message"]
            except Exception:
                if reportErrors:
                    strMess = __addon__.getLocalizedString(32101) + "\n" + a     # Error while trying to connect to bulb!
                    a = strMess
                    xbmc.executebuiltin("XBMC.Notification(%s,%s,2000,%s)" % ('YeeMee', strMess, __addon__.getAddonInfo('icon')))

        xbmc.log("YEEMEE >> %s: TURN OFF RESULT >> %s" % (self.bulb_ip, a))


# ============================================================
# Yeelight class - Turn on bulb
# ============================================================

    def turnOn(self, action):
        global __addon__
        global reportErrors

        global OnAtStart_color
        global OnAtStart_effect
        global OnAtStart_duration
        global OnAtStart_intensity
        global OnAtStart_blink

        effect = "smooth"

        if action == "play" or action == "start":
            duration = self.play_duration
            if self.play_effect == 0:
                effect = "sudden"
            intensity = self.play_intensity
            color = int(self.play_color[1:], 16)

        elif action == "pause":
            duration = self.pause_duration
            if self.pause_effect == 0:
                effect = "sudden"
            intensity = self.pause_intensity
            color = int(self.pause_color[1:], 16)

        elif action == "onstart":
            duration = OnAtStart_duration
            if OnAtStart_effect == 0:
                effect = "sudden"
            intensity = OnAtStart_intensity
            color = int(OnAtStart_color[1:], 16)

        elif action == "blink":
            duration = 0
            effect = "sudden"
            intensity = 100
            color = int(OnAtStart_blink[1:], 16)

        elif action == "startsaver":
            duration = self.saveron_duration
            if self.saveron_effect == 0:
                effect = "sudden"
            intensity = self.saveron_intensity
            color = int(self.saveron_color[1:], 16)

        else:
            duration = self.stop_duration
            if self.stop_effect == 0:
                effect = "sudden"
            intensity = self.stop_intensity
            color = int(self.stop_color[1:], 16)

        if (self.model != "mono") and (self.model != "ceiling") and (self.model != "ct_bulb"):                          # color led
            if color != 0:                       # display single color, set scene
                message = {"id": 1, "method": "set_scene", "params": ["color", color, 1]}
                log = "YEEMEE >> " + str(self.bulb_ip) + ": (ON) SET SCENE (COLOR: " + str(hex(color)) + ") RESULT >> "
            else:                                # color is #000000 to display color flow, so just turn on the bulb for the time being
                message = {"id": 1, "method": "set_power", "params": ["on", effect, duration]}
                log = "YEEMEE >> " + str(self.bulb_ip) + ": (ON) POWER ON (COLOR - CF) RESULT >> "

            xbmc.sleep(300)
        else:                                     # mono led, just turn on (or color is 0 - color flow)
            message = {"id": 1, "method": "set_power", "params": ["on", effect, duration]}
            log = "YEEMEE >> " + str(self.bulb_ip) + ": (ON) POWER ON (MONO) RESULT >> "

        result = self.connect(message, self.bulb_ip, self.bulb_port)

        a = ""
        try:
            a = json.loads(result)["result"][0]
        except Exception:
            try:
                a = json.loads(result)["error"]["message"]
            except Exception:
                if reportErrors:
                    strMess = __addon__.getLocalizedString(32101) + "\n" + a     # Error while trying to connect to bulb!
                    a = strMess
                    xbmc.executebuiltin("XBMC.Notification(%s,%s,2000,%s)" % ('YeeMee', strMess, __addon__.getAddonInfo('icon')))

        xbmc.log(log + a)
        xbmc.sleep(300)

        if (self.model != "mono") and (self.model != "ceiling") and (self.model != "ct_bulb") and color == 0:      # color led, color flow when color set to 000000 (black)
            #         [duration, mode, value, brightness]          red                 green            pink                yellow              blue           orange
            message = {"id": 1, "method": "start_cf", "params": [0, 1, "500,1,16711680,100, 500,1,65280,100, 500,1,14101947,100, 500,1,16776960,100, 500,1,255,100, 500,1,16753920,100"]}
            log = "YEEMEE >> " + str(self.bulb_ip) + ": (ON) SET FLOW RESULT >> "
        else:                                                   # mono led, just set brightness
            message = {"id": 1, "method": "set_bright", "params": [intensity, effect, duration]}
            log = "YEEMEE >> " + str(self.bulb_ip) + ": (ON) SET BRIGHT RESULT >> int: " + str(intensity) + " > "

        result = self.connect(message, self.bulb_ip, self.bulb_port)

        a = ""
        try:
            a = json.loads(result)["result"][0]
        except Exception:
            try:
                a = json.loads(result)["error"]["message"]
            except Exception:
                if reportErrors:
                    strMess = __addon__.getLocalizedString(32101) + "\n" + a     # Error while trying to connect to bulb!
                    a = strMess
                    xbmc.executebuiltin("XBMC.Notification(%s,%s,2000,%s)" % ('YeeMee', strMess, __addon__.getAddonInfo('icon')))

        xbmc.log(log + a)


# ============================================================
# Yeelight class - Turn on bulb
# ============================================================

    def turnOn_bg(self, action):
        global __addon__
        global reportErrors

        global OnAtStart_color
        global OnAtStart_effect
        global OnAtStart_duration
        global OnAtStart_blink

        effect = "smooth"

        if action == "play" or action == "start":
            duration = self.play_bg_duration
            if self.play_bg_effect == 0:
                effect = "sudden"
            color = int(self.play_bg_color[1:], 16)

        elif action == "pause":
            duration = self.pause_bg_duration
            if self.pause_bg_effect == 0:
                effect = "sudden"
            color = int(self.pause_bg_color[1:], 16)

        elif action == "onstart":
            duration = OnAtStart_duration
            if OnAtStart_effect == 0:
                effect = "sudden"
            color = int(OnAtStart_color[1:], 16)

        elif action == "blink":
            duration = 0
            effect = "sudden"
            color = int(OnAtStart_blink[1:], 16)

        elif action == "startsaver":
            duration = self.saveron_bg_duration
            if self.saveron_bg_effect == 0:
                effect = "sudden"
            color = int(self.saveron_bg_color[1:], 16)

        else:
            duration = self.stop_bg_duration
            if self.stop_bg_effect == 0:
                effect = "sudden"
            color = int(self.stop_bg_color[1:], 16)

        if (self.model == "ceiling4"):                          # ceiling4 led
            if color != 0:                       # display single color, set scene
                message = {"id": 1, "method": "bg_set_scene", "params": ["color", color, 1]}
                log = "YEEMEE >> " + str(self.bulb_ip) + ": (ON) SET SCENE (COLOR: " + str(hex(color)) + ") RESULT >> "
            else:                                # color is #000000 to display color flow, so just turn on the bulb for the time being
                message = {"id": 1, "method": "bg_set_power", "params": ["on", effect, duration]}
                log = "YEEMEE >> " + str(self.bulb_ip) + ": (ON) POWER ON (COLOR - CF) RESULT >> "

            xbmc.sleep(300)

        result = self.connect(message, self.bulb_ip, self.bulb_port)

        a = ""
        try:
            a = json.loads(result)["result"][0]
        except Exception:
            try:
                a = json.loads(result)["error"]["message"]
            except Exception:
                if reportErrors:
                    strMess = __addon__.getLocalizedString(32101) + "\n" + a     # Error while trying to connect to bulb!
                    a = strMess
                    xbmc.executebuiltin("XBMC.Notification(%s,%s,2000,%s)" % ('YeeMee', strMess, __addon__.getAddonInfo('icon')))

        xbmc.log(log + a)
        xbmc.sleep(300)

        if (self.model == "ceiling4") and color == 0:                 # ceiling4 led, color flow when color set to 000000 (black)
            #         [duration, mode, value, brightness]          red                 green            pink                yellow              blue           orange
            message = {"id": 1, "method": "bg_start_cf", "params": [0, 1, "500,1,16711680,100, 500,1,65280,100, 500,1,14101947,100, 500,1,16776960,100, 500,1,255,100, 500,1,16753920,100"]}
            log = "YEEMEE >> " + str(self.bulb_ip) + ": (ON) SET FLOW RESULT >> "

        result = self.connect(message, self.bulb_ip, self.bulb_port)

        a = ""
        try:
            a = json.loads(result)["result"][0]
        except Exception:
            try:
                a = json.loads(result)["error"]["message"]
            except Exception:
                if reportErrors:
                    strMess = __addon__.getLocalizedString(32101) + "\n" + a     # Error while trying to connect to bulb!
                    a = strMess
                    xbmc.executebuiltin("XBMC.Notification(%s,%s,2000,%s)" % ('YeeMee', strMess, __addon__.getAddonInfo('icon')))

        xbmc.log(log + a)


# ============================================================
# Yeelight class - Turn on bulb
# ============================================================

    def testTurnOn(self):
        xbmc.log("YEEMEE >> TEST BULB ON")
        message = {"id": 1, "method": "set_power", "params": ["on", "sudden", 0]}
        result = self.connect(message, self.bulb_ip, self.bulb_port)

        a1 = ""
        a2 = ""

        try:
            a1 = json.loads(result)["result"][0]
            try:
                a2 = json.loads(result)["result"][1]
            except Exception:
                a2 = ""
        except Exception:
            a1 = json.loads(result)["error"]["message"]
            try:
                a2 = json.loads(result)["error"]["code"]
            except Exception:
                a2 = ""

        mess = str(a1) + " " + str(a2)
        xbmc.log("YEEMEE >> " + str(self.bulb_ip) + ": TEST ON >> " + str(a1) + " >> " + str(a2) + " <<")
        return mess

# ============================================================
# Yeelight class - Turn off bulb
# ============================================================

    def testTurnOff(self):
        xbmc.log("YEEMEE >> TEST BULB OFF")
        message = {"id": 1, "method": "set_power", "params": ["off", "sudden", 0]}
        result = self.connect(message, self.bulb_ip, self.bulb_port)

        a1 = ""
        a2 = ""

        try:
            a1 = json.loads(result)["result"][0]
            try:
                a2 = json.loads(result)["result"][1]
            except Exception:
                a2 = ""
        except Exception:
            a1 = json.loads(result)["error"]["message"]
            try:
                a2 = json.loads(result)["error"]["code"]
            except Exception:
                a2 = ""

        mess = str(a1) + " " + str(a2)
        xbmc.log("YEEMEE >> " + str(self.bulb_ip) + ": TEST ON >> " + str(a1) + " >> " + str(a2) + " <<")
        return mess

# ============================================================
# Yeelight class - Get bulb state
# ============================================================

    def getState(self):
        message = {"id": 1, "method": "get_prop", "params": ["power"]}
        try:
            state = self.connect(message, self.bulb_ip, self.bulb_port)
            return json.loads(state)["result"][0]
        except Exception as e:
            if reportErrors:
                strMess = __addon__.getLocalizedString(32101) + "\n"     # Error while trying to connect to bulb!
                xbmc.executebuiltin("XBMC.Notification(%s,%s,2000,%s)" % ('YeeMee', strMess, __addon__.getAddonInfo('icon')))

            xbmc.log("YEEMEE >> " + str(self.bulb_ip) + ": GET STATE ERROR %s" % (e))


# ============================================================
# Yeelight class - Get bulb_bg state
# ============================================================

    def getState_bg(self):
        message = {"id": 1, "method": "get_prop", "params": ["bg_power"]}
        try:
            state = self.connect(message, self.bulb_ip, self.bulb_port)
            return json.loads(state)["result"][0]
        except Exception as e:
            if reportErrors:
                strMess = __addon__.getLocalizedString(32101) + "\n"     # Error while trying to connect to bulb!
                xbmc.executebuiltin("XBMC.Notification(%s,%s,2000,%s)" % ('YeeMee', strMess, __addon__.getAddonInfo('icon')))

            xbmc.log("YEEMEE >> " + str(self.bulb_ip) + ": GET STATE ERROR %s" % (e))

# ============================================================
# Yeelight class - Get bulb model
# ============================================================

    def getModel(self):
        message = {"id": 1, "method": "get_prop", "params": ["ct", "rgb", "hue", "sat"]}
        try:
            state = self.connect(message, self.bulb_ip, self.bulb_port)
            response = json.loads(state)["result"]

            for i in response:
                xbmc.log("YEEMEE >> " + str(self.bulb_ip) + ": RESPONSE %s" % (str(i)))

        except Exception as e:
            if reportErrors:
                strMess = __addon__.getLocalizedString(32101) + "\n"     # Error while trying to connect to bulb!
                xbmc.executebuiltin("XBMC.Notification(%s,%s,2000,%s)" % ('YeeMee', strMess, __addon__.getAddonInfo('icon')))

            xbmc.log("YEEMEE >> " + str(self.bulb_ip) + ": GET STATE ERROR %s" % (e))

# ============================================================
# Yeelight class - Send custom JSON message
# ============================================================

    def sendMessage(self, message):
        message = json.loads(message)

        if self.model != "ceiling4":
            xbmc.log("YEEMEE >> MESSAGE TO " + str(self.bulb_ip) + ": " + str(message))

        result = self.connect(message, self.bulb_ip, self.bulb_port)

        a1 = ""
        a2 = ""

        try:
            a1 = json.loads(result)["result"][0]
            try:
                a2 = json.loads(result)["result"][1]
            except Exception:
                a2 = ""
        except Exception:
            try:
                a1 = json.loads(result)["error"]["message"]
            except Exception:
                a1 = ""
            try:
                a2 = json.loads(result)["error"]["code"]
            except Exception:
                a2 = ""

        if self.model != "ceiling4":
            xbmc.log("YEEMEE >> RESPONSE FROM " + str(self.bulb_ip) + ": " + str(a1) + ", " + str(a2))

        return str(a1), str(a2)


# ============================================================
# Yeelight class - Connect to bulb, pass message, get result
# ============================================================

    def connect(self, command, bulb_ip, bulb_port):
        try:
            tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            msg = json.dumps(command) + "\r\n"
            tcp_socket.connect((bulb_ip, int(bulb_port)))
            tcp_socket.send(msg)
            data = tcp_socket.recv(1024)
            tcp_socket.close()
            return data
        except Exception as e:
            xbmc.log("YEEMEE >> CONNECT ERROR %s" % (e))


# ------------------------------------------------------------
# ============================================================
# Screenshot class
# ============================================================
# ------------------------------------------------------------


class Screenshot:
    def __init__(self, pixels, capture_width, capture_height):
        self.pixels = pixels
        self.capture_width = capture_width
        self.capture_height = capture_height

# ============================================================
# Screenshot class - calc dominant color in region
# ============================================================

    def calcRegColorSimple(self, bulbnr, pixels, x, y, w, h):
        global debugRenderCapture

        colors = {}
        r, g, b = 0, 0, 0

        area = (x, y, x + w, y + h)

        width = self.capture_width
        height = self.capture_height

        count = 1

        x = x * 4
        w = w * 4
        wid = width * 4

        for yy in range(0, height):
            if yy >= y and yy < y + h:
                yp = yy * width * 4

                for xx in range(0, wid, 4):
                    if xx >= x and xx < w + x:
                        ypos = yp + xx
                        try:
                            b += pixels[ypos]
                            g += pixels[ypos + 1]
                            r += pixels[ypos + 2]
                            count += 1
                        except Exception:
                            pass

        colors[0] = r / count
        colors[1] = g / count
        colors[2] = b / count

        if colors[0] < 10 and colors[1] < 10 and colors[2] < 10:
            colors[0] = 0
            colors[1] = 0
            colors[2] = 0

        blackLimit = 0.1
        minimumSaturation = 0.15
        rgDiff = colors[0] - colors[1]
        rbDiff = colors[0] - colors[2]
        gbDiff = colors[1] - colors[2]
        tolerance = 14
        isGray = 0

        if math.fabs(rgDiff) < tolerance and math.fabs(rbDiff) < tolerance and math.fabs(gbDiff) < tolerance:
            isGray = 1

        hls = colorWithBrightness_from_rgb(colors[0], colors[1], colors[2])

        if hls[2] <= minimumSaturation and isGray == 1:
            if hls[1] > blackLimit:
                hls[2] = 0
            else:
                hls[1] = 0
                hls[2] = 0

        if debugRenderCapture:
            ba = pixels

            try:
                ba[0::4], ba[2::4] = ba[2::4], ba[0::4]                    # change ABGR to RGBA
            except Exception as e:
                xbmc.log('YEEMEE >> ABGR TO RGBA DEBUG >> EXCEPTION: ' + str(e))

            try:
                im = Image.frombuffer('RGBA', (self.capture_width, self.capture_height), ba, 'raw', 'RGBA', 0, 1)
            except Exception as e:
                xbmc.log('YEEMEE >> RENDERCAPTURE DEBUG >> EXCEPTION: ' + str(e))
                return hls[0], hls[1], hls[2]

            ci = im.convert('RGB')

            cropped_img = ci.crop(area)                                # crop to only selected area
            current_milli_time = int(round(time.time() * 1000))
            savepath = os.path.join(xbmc.translatePath("special://temp/"), bulbnr + "_" + str(current_milli_time) + ".jpg")
            cropped_img.save(savepath)

        return hls[0], hls[1], hls[2]

# ============================================================
# Screenshot class - set color(s) for bulbs
# ============================================================

    def getColorsSimple(self, screen):
        global bulbs

        for x in bulbs:                       # for each bulb
            if x.ambipos > 0:
                x.applyColorsH, x.applyColorsL, x.applyColorsS = screen.calcRegColorSimple(x.bulb_ip, screen.pixels, *x.ambicoord)

# ============================================================
# Converts RGB color to hue value
# ============================================================


def colorWithBrightness_from_rgb(red, green, blue):
    r = min(red, 255)
    g = min(green, 255)
    b = min(blue, 255)
    if r > 1 or g > 1 or b > 1:
        r = r / 255.0
        g = g / 255.0
        b = b / 255.0

    return colorWithBrightness_from_hls(*rgb_to_hls(r, g, b))

# ============================================================
# Converts hls color to hue value
# ============================================================


def colorWithBrightness_from_hls(hue, light, sat):
    hls = {}

    hls[0] = hue
    hls[1] = light
    hls[2] = sat

    return hls

# ============================================================
# Set lumi factor according to current time
# ============================================================


def setLumiFactor():
    global Sunrise
    global Sunset
    global nauticTW
    global civilTW

    timeSunrise = mystr2time(Sunrise, '%H:%M').time()
    timeSunset = mystr2time(Sunset, '%H:%M').time()
    timenauticTW = mystr2time(nauticTW, '%H:%M').time()
    timecivilTW = mystr2time(civilTW, '%H:%M').time()

    now = datetime.datetime.now()
    strNowTime = '%02d:%02d:%02d' % (now.hour, now.minute, now.second)
    nowTime = mystr2time(strNowTime, '%H:%M:%S').time()

    if nowTime > timeSunrise and nowTime <= timeSunset:                           # day
        lF = YeeAmbiMaxDay
    elif nowTime > timeSunset and nowTime <= timecivilTW:                         # civil twilight
        lF = YeeAmbiMaxCivTw
    elif nowTime > timecivilTW and nowTime <= timenauticTW:                       # nautical twilight
        lF = YeeAmbiMaxNauTw
    elif nowTime > timenauticTW:                                                  # night
        lF = YeeAmbiMaxNight
    elif nowTime < timeSunrise:                                                   # night
        lF = YeeAmbiMaxNight
    else:
        lF = 100

    xbmc.log("YEEMEE >> LUMIFACTOR IS " + str(lF))
    return lF

# ============================================================
# Thread - sends color to bulbs
# ============================================================


def handler(clientsock, addr):
    global stopHandler
    global bulbs
    global YeePauseLower
    global YeeSmoothen
    global lumiFactor

    activeBulb = None

    if YeeSmoothen > 0:
        effect = "smooth"
    else:
        effect = "sudden"

    for x in bulbs:        # for each bulb, find the bulb by IP address
        if x.bulb_ip == addr[0]:
            activeBulb = x
            break

    if activeBulb is None:
        xbmc.log('YEEMEE >> SERVER >> NO BULB, CONNECTION FROM ' + str(addr) + ", TERMINATING HANDLER")
        return
    else:
        xbmc.log('YEEMEE >> SERVER >> CONNECTION OPEN FOR ' + str(addr))

    xbmc.log("YEEMEE >> SERVER >> LUMIFACTOR IS " + str(lumiFactor))

    lumi = 10
    exlumi = 100
    exrround = 0
    exground = 0
    exbround = 0
    sw = True

    while 1:
        xbmc.sleep(10)
        if sw:
            if lumi > 5:
                r, g, b = hls_to_rgb(activeBulb.applyColorsH, activeBulb.applyColorsL, activeBulb.applyColorsS)

                rround = ((r * 100)) // 10 * 10
                ground = ((g * 100)) // 10 * 10
                bround = ((b * 100)) // 10 * 10

                if rround != exrround or ground != exground or bround != exbround:
                    r = str(r * 100) + "%"
                    g = str(g * 100) + "%"
                    b = str(b * 100) + "%"

                    rgbcolor = webcolors.rgb_percent_to_hex([r, g, b])
                    color = int(rgbcolor[1:], 16)
                    data = json.dumps({"id": 1, "method": "set_rgb", "params": [color, effect, YeeSmoothen]}) + "\r\n"
                    clientsock.send(data)

                exrround = rround
                exground = ground
                exbround = bround
        else:
            lumi = int(activeBulb.applyColorsL * 100)

            if activeBulb.paused:
                if lumi > YeePauseLower:
                    if YeePauseLower == 0:
                        YeePauseLower = 1
                    data = json.dumps({"id": 1, "method": "set_bright", "params": [YeePauseLower, effect, YeeSmoothen]}) + "\r\n"
                    clientsock.send(data)
            else:
                lumiround = (lumi + 9) // 10 * 10

                if lumiround != exlumi:
                    if lumiFactor < 100:
                        lumi = int((lumi * lumiFactor) / 100)

                    if activeBulb.bias > 0:
                        lumi = int((lumi * (100 - activeBulb.bias)) / 100)

                    data = json.dumps({"id": 1, "method": "set_bright", "params": [lumi, effect, YeeSmoothen]}) + "\r\n"
                    clientsock.send(data)

                exlumi = lumiround

        sw = not sw

        if stopHandler:
            break

    clientsock.close()
    xbmc.log('YEEMEE >> SERVER >> CONNECTION CLOSED FOR ' + str(activeBulb.bulb_ip))
    xbmc.sleep(200)

    data = json.dumps({"id": 1, "method": "get_prop", "params": ["power", "music_on"]})
    result1, result2 = activeBulb.sendMessage(data)
    xbmc.sleep(100)

    if result1 == "on":
        data = json.dumps({"id": 1, "method": "set_power", "params": ["off", "smooth", 500]})
        activeBulb.sendMessage(data)
        xbmc.sleep(100)

    if result2 == "1":
        data = json.dumps({"id": 1, "method": "set_music", "params": [0]})
        activeBulb.sendMessage(data)

# ============================================================
# Thread - Socket server
# ============================================================


def startServer(HOST):
    global thread_started
    global numberOfColorBulbs

    lock.acquire()
    thread_started = True
    lock.release()

    PORT = 55440
    ADDR = (HOST, PORT)

    serversock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    serversock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    serversock.settimeout(None)
    serversock.bind(ADDR)
    serversock.listen(8)

    xbmc.log('YEEMEE >> SERVER >> ' + HOST + ' WAITING FOR CONNECTION...')

    for x in range(0, numberOfColorBulbs + 1):
        try:
            clientsock, addr = serversock.accept()
        except socket.timeout:
            pass
        except Exception as e:
            xbmc.log('YEEMEE >> SERVER >> EXCEPTION: ' + str(e))

        xbmc.log('YEEMEE >> SERVER >> CONNECTION FROM: ' + str(addr) + ' ACCEPTED')
        thread.start_new_thread(handler, (clientsock, addr))

    try:
        clientsock.shutdown(socket.SHUT_RDWR)
        clientsock.close()
    except Exception as e:
        xbmc.log('YEEMEE >> SERVER >> EXCEPTION: ' + str(e))

    lock.acquire()
    thread_started = False
    lock.release()

    xbmc.log('YEEMEE >> SERVER >> END')

# ============================================================
# Stop server by opening all unused sessions
# ============================================================


def stopServer():
    global numberOfColorBulbs

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_ip = get_ip()
    port = 55440

    for x in range(0, numberOfColorBulbs + 1):
        try:
            s.connect((server_ip, port))
            s.recv(1024)
            data = json.dumps({"id": 1, "result": ["ok"]})
            s.send(data)
            s.close()
        except Exception as e:
            xbmc.log('YEEMEE >> SERVER >> STOP SERVER EXCEPTION (THIS IS EXPECTED AND OK): ' + str(e))
            break

# ============================================================
# Get local IP adress
# ============================================================


def get_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # doesn't even have to be reachable
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

# ============================================================
# Grabs screen
# ============================================================


def grabloop(arg):
    global stopHandler
    global capture
    global kodiVer
    global screendef
    global AmbiPrecision
    global YeeAmbiMaxDay
    global YeeAmbiMaxCivTw
    global YeeAmbiMaxNauTw
    global YeeAmbiMaxNight
    global Sunrise
    global Sunset
    global nauticTW
    global civilTW
    global lumiFactor

    # capture resolution
    if AmbiPrecision == 0:
        capture_width = 16
    elif AmbiPrecision == 1:
        capture_width = 32
    elif AmbiPrecision == 2:
        capture_width = 64
    elif AmbiPrecision == 3:
        capture_width = 128

    capture_height = int(capture_width / capture.getAspectRatio())

    # screen positions, Width
    OneQuarterW = capture_width / 4
    OneThirdW = capture_width / 3
    OneHalfW = capture_width / 2

    ThreeQuarterW = (capture_width / 4) * 3
    TwoThirdW = (capture_width / 3) * 2

    # screen positions, Height
    OneHalfH = capture_height / 2

    # screen sections
    screendef = []

    screendef.append([0, 0, 0, 0])                                         # 0 - 0 bulbs - nothing
    screendef.append([0, 0, capture_width, capture_height])                # 1 - 1 bulb  - whole screen
    screendef.append([0, 0, OneQuarterW, capture_height])                  # 2 - 2 bulbs - leftQuarter
    screendef.append([0, 0, OneThirdW, capture_height])                    # 3 - 2 bulbs - leftThird
    screendef.append([0, 0, OneHalfW, capture_height])                     # 4 - 2 bulbs - leftHalf
    screendef.append([ThreeQuarterW, 0, OneQuarterW, capture_height])      # 5 - 2 bulbs - rightQuarter
    screendef.append([TwoThirdW, 0, OneThirdW, capture_height])            # 6 - 2 bulbs - rightThird
    screendef.append([OneHalfW, 0, OneHalfW, capture_height])              # 7 - 2 bulbs - rightHalf
    screendef.append([OneQuarterW, 0, OneHalfW, OneHalfH])                 # 8 - 4 bulbs - topCenter
    screendef.append([OneQuarterW, OneHalfH, OneHalfW, OneHalfH])          # 9 - 4 bulbs - bottomCenter

    lumiFactor = setLumiFactor()

    for j, x in enumerate(bulbs):                       # for each bulb
        x.ambicoord = screendef[x.ambipos]

    if int(float(kodiVer)) == 16:              # Jarvis
        capture.capture(capture_width, capture_height, xbmc.CAPTURE_FLAG_CONTINUOUS)

        while 1:
            capture.waitForCaptureStateChangeEvent(100)
            if capture.getCaptureState() == xbmc.CAPTURE_STATE_DONE:
                screen = Screenshot(capture.getImage(), capture.getWidth(), capture.getHeight())
                screen.getColorsSimple(screen)
                xbmc.sleep(10)

            if stopHandler:
                break

    elif int(float(kodiVer)) >= 17:            # Krypton and above
        capture.capture(capture_width, capture_height)

        while 1:
            capture.getImage(100)
            screen = Screenshot(capture.getImage(), capture.getWidth(), capture.getHeight())
            screen.getColorsSimple(screen)
            xbmc.sleep(10)

            if stopHandler:
                break

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

try:

    kodiVer = xbmc.getInfoLabel('System.BuildVersion').partition(".")[0]
except Exception:
    kodiVer = xbmc.getInfoLabel('System.BuildVersion')

bulbs = []
controllers = []
screendef = []

numberOfControllers = int(__addon__.getSetting("numberOfControllers"))
MsgControllerOn = 1
MsgUrlOn = 1
numberOfBulbs = int(__addon__.getSetting("numberOfBulbs"))
disableShort = False
disableShortTime = 60
intDuration = 0
timeOn = 0
timeOnStart = datetime.datetime.now()
timeOnEnd = datetime.datetime.now()
reportErrors = False
OffAtEnd = False
OnAtStart = 0
OnAtStart_color = "#FFFFFF"
OnAtStart_effect = 0
OnAtStart_duration = 500
OnAtStart_intensity = 100
OnAtStart_blink = "#FF0000"
OnAtStart_timeframe = True
isVideo = False
isPvr = ""
isStream = ""
ServiceOn = True
AmbiOn = True
disablePvr = False
numberOfColorBulbs = 0
stopHandler = False
YeePriority = 1
YeePauseLower = 0
YeeSmoothen = 0
YeeAmbiMaxDay = 100
YeeAmbiMaxCivTw = 100
YeeAmbiMaxNauTw = 100
YeeAmbiMaxNight = 100
AmbiPrecision = 0
osAndroid = False
lumiFactor = 100
Sunrise = ""
Sunset = ""
nauticTW = ""
civilTW = ""
thread_started = False
lock = thread.allocate_lock()
debugRenderCapture = False

cl_exlumi = 100
cl_exrround = 0
cl_exground = 0
cl_exbround = 0
cl_sw = True

if __name__ == '__main__':
    osAndroid = xbmc.getCondVisibility('System.Platform.Android')

    xbmc.log("YEEMEE >> STARTED VERSION %s on Kodi %s" % (__version__, kodiVer))

    monitor = xbmc.Monitor()
    player = XBMCPlayer()

    data = json.dumps({"id": 1, "method": "get_prop", "params": ["power", "music_on"]})
    for x in bulbs:        # for each bulb
        if x.model != "mono" and x.model != "ceiling" and x.model != "ct_bulb":
            result1, result2 = x.sendMessage(data)
            if result2 == "1":
                data = json.dumps({"id": 1, "method": "set_music", "params": [0]})
                x.sendMessage(data)

    getLoc()

    Sunrise, Sunset, civilTW, nauticTW = byLoc()

    if Sunset:
        __addon__.setSetting('sunset', str(Sunset))
    if Sunrise:
        __addon__.setSetting('sunrise', str(Sunrise))

    GetSettings(0)

    if OnAtStart == 2 or OnAtStart == 3:
        for bulb in bulbs:
            if bulb.on_start:
                xbmc.log("YEEMEE >> BLINKING BULB %s ON START" % (str(bulb.bulb_ip)))
                bulb.turnOn("blink")

        xbmc.sleep(700)
        for bulb in bulbs:
            if bulb.on_start:
                bulb.turnOff("blink")

        xbmc.sleep(700)
        for bulb in bulbs:
            if bulb.on_start:
                bulb.turnOn("blink")

        xbmc.sleep(700)
        for bulb in bulbs:
            if bulb.on_start:
                bulb.turnOff("blink")

    if OnAtStart == 3:
        xbmc.sleep(1500)

    if OnAtStart == 1 or OnAtStart == 3:
        if OnAtStart_timeframe:
            xbmc.log("YEEMEE >> ON AT START >> ACTIVATION TIME: " + str(timeOn))

            if timeOn > 0:
                now = datetime.datetime.now()
                strNowTime = '%02d:%02d:%02d' % (now.hour, now.minute, now.second)
                nowTime = mystr2time(strNowTime, '%H:%M:%S').time()

                if nowTime > timeOnStart or nowTime < timeOnEnd:
                    xbmc.log("YEEMEE >> ON AT START >> IN TIME FRAME: " + str(timeOnStart) + " - (" + str(nowTime) + ") - " + str(timeOnEnd))

                    for bulb in bulbs:
                        if bulb.on_start:
                            xbmc.log("YEEMEE >> ON AT START >> TURNING ON BULB %s" % (str(bulb.bulb_ip)))
                            bulb.turnOn("onstart")

                        if bulb.model == 'ceiling4':
                            if bulb.on_bg_start:
                                xbmc.log("YEEMEE >> ON AT START >> TURNING ON BG BULB %s" % (str(bulb.bulb_ip)))
                                bulb.turnOn_bg("onstart")
                else:
                    xbmc.log("YEEMEE >> ON AT START >> NOT IN TIME FRAME: " + str(timeOnStart) + " - (" + str(nowTime) + ") - " + str(timeOnEnd))
            else:
                for bulb in bulbs:
                    if bulb.on_start:
                        xbmc.log("YEEMEE >> ON AT START >> TURNING ON BULB %s" % (str(bulb.bulb_ip)))
                        bulb.turnOn("onstart")

                    if bulb.model == 'ceiling4':
                        if bulb.on_bg_start:
                            xbmc.log("YEEMEE >> ON AT START >> TURNING ON BG BULB %s" % (str(bulb.bulb_ip)))
                            bulb.turnOn_bg("onstart")
        else:
            for bulb in bulbs:
                if bulb.on_start:
                    xbmc.log("YEEMEE >> ON AT START >> TURNING ON BULB %s" % (str(bulb.bulb_ip)))
                    bulb.turnOn("onstart")
                if bulb.model == 'ceiling4':
                    if bulb.on_bg_start:
                        xbmc.log("YEEMEE >> ON AT START >> TURNING ON BG BULB %s" % (str(bulb.bulb_ip)))
                        bulb.turnOn_bg("onstart")

    monsettings = SettingMonitor()

    rt = RepeatedTimer(1, hw)
    rt.stop()

    capture = xbmc.RenderCapture()
    fmt = capture.getImageFormat()
    fmtRGBA = fmt == 'RGBA'

    date_auto_lastrun = int(round(time.time()))
    lastrundays = 1
    iCounter = 0

    while True:
        if monitor.waitForAbort(2):    # Sleep/wait for abort
            stopHandler = True

            if OffAtEnd:
                if OnAtStart_timeframe:
                    xbmc.log("YEEMEE >> OFF AT END >> ACTIVATION TIME: " + str(timeOn))

                    if timeOn > 0:
                        now = datetime.datetime.now()
                        strNowTime = '%02d:%02d:%02d' % (now.hour, now.minute, now.second)
                        nowTime = mystr2time(strNowTime, '%H:%M:%S').time()

                        if nowTime > timeOnStart or nowTime < timeOnEnd:
                            xbmc.log("YEEMEE >> OFF AT END >> IN TIME FRAME: " + str(timeOnStart) + " - (" + str(nowTime) + ") - " + str(timeOnEnd))

                            for bulb in bulbs:
                                if bulb.on_start:
                                    xbmc.log("YEEMEE >> OFF AT END >> TURNING OFF BULB %s" % (str(bulb.bulb_ip)))
                                    bulb.turnOff('blink')
                                if bulb.model == 'ceiling4':
                                    if bulb.on_bg_start:
                                        xbmc.log("YEEMEE >> OFF AT END >> TURNING OFF BG BULB %s" % (str(bulb.bulb_ip)))
                                        bulb.turnOff_bg('blink')
                        else:
                            xbmc.log("YEEMEE >> OFF AT END >> NOT IN TIME FRAME: " + str(timeOnStart) + " - (" + str(nowTime) + ") - " + str(timeOnEnd))
                    else:
                        for bulb in bulbs:
                            if bulb.on_start:
                                xbmc.log("YEEMEE >> OFF AT END >> TURNING OFF BULB %s" % (str(bulb.bulb_ip)))
                                bulb.turnOff('blink')
                            if bulb.model == 'ceiling4':
                                if bulb.on_bg_start:
                                    xbmc.log("YEEMEE >> OFF AT END >> TURNING OFF BG BULB %s" % (str(bulb.bulb_ip)))
                                    bulb.turnOff_bg('blink')

                else:
                    for bulb in bulbs:
                        if bulb.on_start:
                            xbmc.log("YEEMEE >> OFF AT END >> TURNING OFF BULB %s" % (str(bulb.bulb_ip)))
                            bulb.turnOff('blink')
                        if bulb.model == 'ceiling4':
                            if bulb.on_bg_start:
                                xbmc.log("YEEMEE >> OFF AT END >> TURNING OFF BG BULB %s" % (str(bulb.bulb_ip)))
                                bulb.turnOff_bg('blink')

            xbmc.log('YEEMEE >> EXIT')
            break                      # Abort was requested while waiting. Exit the while loop.
        else:
            iCounter += 1

            if iCounter > 7200:
                iCounter = 0
                date_now = int(round(time.time()))
                time_difference = date_now - date_auto_lastrun
                time_difference_days = int(time_difference) / 86400

                xbmc.log("YEEMEE >> UPDATE SUNRISE-SUNSET >> LAST RUN " + str(time_difference_days) + " DAYS AGO, SET TO RUN EVERY " + str(lastrundays) + " DAYS (NOW: " + str(date_now) + ")")

                if time_difference_days > lastrundays:
                    xbmc.log('YEEMEE >> UPDATE SUNRISE-SUNSET >> UPDATING...')

                    Sunrise, Sunset, civilTW, nauticTW = byLoc()
                    __addon__.setSetting('sunset', str(Sunset))
                    __addon__.setSetting('sunrise', str(Sunrise))

                    date_auto_lastrun = int(round(time.time()))
                    xbmc.log('YEEMEE >> UPDATE SUNRISE-SUNSET >> END')
            elif iCounter > 150:
                condition = xbmc.getCondVisibility('Player.HasMedia')
                if condition:
                    is_video = xbmc.getCondVisibility('Player.HasVideo')
                    if is_video:
                        lumiFactor = setLumiFactor()

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
