CONST_BASE_URL = 'https://tv.kpn.com'

CONST_BASE_HEADERS = {
    'Pragma': 'no-cache',
    'Cache-Control': 'no-cache',
    'DNT': '1',
    'AVSSite': 'http://www.itvonline.nl',
    'Accept': '*/*',
    'Origin': CONST_BASE_URL,
    'Sec-Fetch-Site': 'same-site',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Dest': 'empty',
    'Referer': CONST_BASE_URL + '/',
    'Accept-Encoding': 'gzip, deflate',
    'Accept-Language': 'en-US,en;q: 0.9,nl;q: 0.8',
}

CONST_DEFAULT_API = 'https://api.prd.tv.kpn.com/101/1.2.0/A/nld/pctv/kpn'
CONST_DEFAULT_IMG_SIZE = '325x220'
CONST_EPG = 'https://dut-epg.github.io/k.epg.xml.zip'
CONST_IMAGES = 'https://dut-epg.github.io/k.images.zip'
CONST_IMAGE_URL = 'https://images.tv.kpn.com'
CONST_MD5 = 'https://dut-epg.github.io/k.md5.json'
CONST_MINIMALEPG = 'https://dut-epg.github.io/k.epg.xml.minimal.zip'
CONST_RADIO = 'https://dut-epg.github.io/radio.m3u8'
CONST_SETTINGS = 'https://dut-epg.github.io/k.settings.json'
CONST_VOD = 'https://dut-epg.github.io/k.vod.json'