import datetime, pytz, requests, time, xbmc, xbmcaddon, xbmcgui

from resources.lib.base import settings
from resources.lib.base.constants import ADDON_PROFILE
from resources.lib.base.util import change_icon, check_iptv_link, check_key, clear_cache, convert_datetime_timezone, date_to_nl_dag, date_to_nl_maand, download_files, find_free_port, get_system_arch, load_file
from resources.lib.proxy import HTTPMonitor, RemoteControlBrowserService
from resources.lib.util import get_image, update_settings

def daily():
    update_settings()
    check_iptv_link()
    clear_cache()

def hourly():
    download_files()

def startup():
    system, arch = get_system_arch()
    settings.set(key="_system", value=system)
    settings.set(key="_arch", value=arch)

    settings.setInt(key='_proxyserver_port', value=find_free_port())

    hourly()
    daily()
    change_icon()

def main():
    startup()
    service = RemoteControlBrowserService()
    service.clearBrowserLock()
    monitor = HTTPMonitor(service)
    service.reloadHTTPServer()

    k = 0
    z = 0
    l = 0

    while not xbmc.Monitor().abortRequested():
        if monitor.waitForAbort(1):
            break

        if k == 60:
            k = 0
            z += 1

        if z == 60:
            z = 0
            l += 1

            hourly()

        if l == 24:
            l = 0

            daily()

        k += 1

    service.shutdownHTTPServer()