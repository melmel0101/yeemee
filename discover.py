# ============================================================
# YeeMee - Version 5.0 by D. Lanik (2017)
# ------------------------------------------------------------
# Control YeeLight bulbs from Kodi
# ------------------------------------------------------------
# License: GPL (http://www.gnu.org/licenses/gpl-3.0.html)
# ============================================================

import xbmc
import xbmcvfs
import xbmcaddon
import xbmcgui
import socket
import sys
import os
import random
from urllib.parse import urlparse
from standalone import RepeatedTimer, OverlayText

# ============================================================
# To be repeated every x seconds
# ============================================================


def hw():
    global myWidget

    r = lambda: random.randint(0, 255)
    color = '0xF0%02X%02X%02X' % (r(), r(), r())

    myWidget.imgbigbulb.setColorDiffuse(color)

# ============================================================
# Function to discover the bulbs
# ============================================================


def discover_bulbs(timeout=3):
    global __addonwd__
    global myWidget

    ActWin = xbmcgui.getCurrentWindowId()
    myWidget = OverlayText(ActWin)
    myWidget.show()
    myWidget.imgbigbulb.setImage(os.path.join(__addonwd__, "media", 'YEE01.png'))
    xbmc.log('YEEMEE STANDALONE >> INITIALIZING OVERLAY')

    rt = RepeatedTimer(0.1, hw)
    rt.isrunning()
    if not rt.is_running:
        rt.start()

    xbmc.executebuiltin("ActivateWindow(busydialog)")

    msg = 'M-SEARCH * HTTP/1.1\r\n' \
          'ST:wifi_bulb\r\n' \
          'MAN:"ssdp:discover"\r\n'

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    s.settimeout(timeout)
    s.sendto(msg.encode(), ('239.255.255.250', 1982))

    bulbs = []
    bulb_ips = set()
    while True:
        try:
            data, addr = s.recvfrom(65507)
        except socket.timeout:
            break

        capabilities = dict([x.strip("\r").split(": ") for x in data.decode().split("\n") if ":" in x])
        parsed_url = urlparse(capabilities["Location"])

        bulb_ip = (parsed_url.hostname, parsed_url.port)
        if bulb_ip in bulb_ips:
            continue

        bulbs.append({"ip": bulb_ip[0], "port": bulb_ip[1], "capabilities": capabilities})
        bulb_ips.add(bulb_ip)

    rt.stop()
    try:
        myWidget._close()
    except Exception:
        pass

    myWidget = None
    xbmc.executebuiltin("Dialog.Close(busydialog)")

    return bulbs

# ============================================================
# ------------------------------------------------------------
# Main
# ------------------------------------------------------------
# ============================================================


__addon__ = xbmcaddon.Addon(id='service.yeemee')
__addondir__ = xbmcvfs.translatePath(__addon__.getAddonInfo('profile').decode('utf-8'))
__addonwd__ = xbmcvfs.translatePath(__addon__.getAddonInfo('path').decode("utf-8"))
__addonname__ = __addon__.getAddonInfo('name')
__version__ = __addon__.getAddonInfo('version')

myWidget = None

if __name__ == '__main__':
    arg = None

    try:
        arg = sys.argv[1].lower()
        xbmc.log("YEEMEE >> STANDALONE STARTED VERSION %s - DISCOVER" % (__version__))
    except Exception:
        pass

    xbmcgui.Window(10000).setProperty('YeeMeeDiscovery_Running', 'True')

    if arg == "discover":
        bulbs = discover_bulbs()

        dialog = xbmcgui.Dialog()
        if len(bulbs) == 0:
            mess = __addon__.getLocalizedString(32105)             # Unable to discover any bulbs, check connection or try again.
            dialog.ok(__addonname__.encode('utf8') + " " + __addon__.getLocalizedString(32107) + ":", mess)      # Bulb discovery
        else:
            mess = ""
            for i, bu in enumerate(bulbs):
                ip = bulbs[i]['ip']
                capa = bulbs[i]['capabilities']
                model = capa['model']
                xbmc.log("YEEMEE >> BULB : " + str(ip) + " Model: " + model)
                mess += __addon__.getLocalizedString(32108) + " " + str(i + 1) + ": " + __addon__.getLocalizedString(32001) + ": " + str(ip) + ", " + __addon__.getLocalizedString(32109) + ": " + model + "\n"

            mess += __addon__.getLocalizedString(32106)            # Add to settings (will overwrite existing!)?
            answ = dialog.yesno(__addonname__.encode('utf8') + " " + __addon__.getLocalizedString(32107) + ":", mess)     # Bulb discovery

            if answ:
                __addon__.setSetting("numberOfBulbs", str(len(bulbs)))

                for i, bu in enumerate(bulbs):
                    ip = bulbs[i]['ip']
                    capa = bulbs[i]['capabilities']
                    model = capa['model']

                    bulbid = "bulb_" + str(i + 1)
                    bulbmodel = "bulb_" + str(i + 1) + "_model"
                    __addon__.setSetting(bulbid, str(ip))
                    __addon__.setSetting(bulbmodel, model)

    __addon__.openSettings()
    xbmcgui.Window(10000).clearProperty('YeeMeeDiscovery_Running')
    bb = __addon__.getSetting('AmbiOn')
    __addon__.setSetting("AmbiOn", bb)

    xbmc.log("YEEMEE >> STANDALONE FINISHED - DISCOVER")

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
