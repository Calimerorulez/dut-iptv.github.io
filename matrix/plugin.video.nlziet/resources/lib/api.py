import base64, datetime, hmac, os, random, re, string, time

from hashlib import sha1
from resources.lib.base import gui, settings
from resources.lib.base.constants import ADDON_ID, ADDON_PROFILE
from resources.lib.base.exceptions import Error
from resources.lib.base.log import log
from resources.lib.base.session import Session
from resources.lib.base.util import check_key, clean_filename, combine_playlist, get_credentials, is_file_older_than_x_minutes, load_file, set_credentials, write_file
from resources.lib.constants import CONST_API_URL, CONST_BASE_URL, CONST_IMAGE_URL
from resources.lib.language import _

try:
    from urllib.parse import parse_qs, urlparse, quote
except ImportError:
    from urlparse import parse_qs, urlparse
    from urllib import quote

class APIError(Error):
    pass

class API(object):
    def new_session(self, force=False, retry=False, channels=False):
        cookies = settings.get(key='_cookies')

        if len(cookies) > 0 and force == False:
            self._session = Session(cookies_key='_cookies')
            self.logged_in = True
            return

        self.logged_in = False

        creds = get_credentials()

        username = creds['username']
        password = creds['password']

        if not len(username) > 0:
            return

        if not len(password) > 0:
            password = gui.numeric(message=_.ASK_PASSWORD).strip()

            if not len(password) > 0:
                gui.ok(message=_.EMPTY_PASS, heading=_.LOGIN_ERROR_TITLE)
                return

        self.login(username=username, password=password, channels=channels, retry=retry)

    def login(self, username, password, channels=False, retry=False):
        settings.remove(key='_cookies')
        self._session = Session(cookies_key='_cookies')

        login_url = '{base_url}/account/login'.format(base_url=CONST_BASE_URL)

        resp = self.download(url=login_url, type="get", code=None, data=None, json_data=False, data_return=True, return_json=False, retry=retry, check_data=False, allow_redirects=True)

        if resp.status_code != 200 and resp.status_code != 302:
            gui.ok(message=_.LOGIN_ERROR, heading=_.LOGIN_ERROR_TITLE)
            self.clear_session()
            return

        resp.encoding = 'utf-8'
        frmtoken = re.findall(r'name=\"__RequestVerificationToken\"\s+type=\"hidden\"\s+value=\"([\S]*)\"', resp.text)
        frmaction = re.findall(r'form\s+action=\"([\S]*)\"', resp.text)

        login_url2 = '{base_url}{action}'.format(base_url=CONST_BASE_URL, action=frmaction[0])

        session_post_data = {
            "__RequestVerificationToken": frmtoken[0],
            "PasswordLogin.Email": username,
            "PasswordLogin.Password": password,
            'RememberMe': 'true',
            'RememberMe': 'false',
        }

        headers = {
            'content-type': 'application/x-www-form-urlencoded',
            'Origin': CONST_BASE_URL,
            'Referer': '{base_url}/account/login'.format(base_url=CONST_BASE_URL),
            'sec-fetch-dest': 'document',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-user': '?1'
        }

        self._session = Session(headers=headers, cookies_key='_cookies')

        resp = self.download(url=login_url2, type="post", code=None, data=session_post_data, json_data=False, data_return=True, return_json=False, retry=retry, check_data=False, allow_redirects=True)

        if (resp.status_code != 200 and resp.status_code != 302):
            gui.ok(message=_.LOGIN_ERROR, heading=_.LOGIN_ERROR_TITLE)
            self.clear_session()
            return

        token_url_base = '{base_url}/OAuth/GetRequestToken'.format(base_url=CONST_BASE_URL)
        token_url_base_encode = quote(token_url_base, safe='')

        nonce = ''.join(random.choice(string.ascii_uppercase + string.ascii_lowercase + string.digits) for _ in range(6))
        token_timestamp = int(time.time())
        token_parameter = 'oauth_consumer_key=key&oauth_signature_method=HMAC-SHA1&oauth_callback=https%3A%2F%2Fapp.nlziet.nl%2Fcallback.html%23nofetch&oauth_version=1.0&oauth_timestamp={timestamp}&oauth_nonce={nonce}'.format(timestamp=token_timestamp, nonce=nonce)
        token_parameter_encode = 'oauth_callback%3Dhttps%253A%252F%252Fapp.nlziet.nl%252Fcallback.html%2523nofetch%26oauth_consumer_key%3Dkey%26oauth_nonce%3D{nonce}%26oauth_signature_method%3DHMAC-SHA1%26oauth_timestamp%3D{timestamp}%26oauth_version%3D1.0'.format(nonce=nonce, timestamp=token_timestamp)

        base_string = 'GET&{token_url_base_encode}&{token_parameter_encode}'.format(token_url_base_encode=token_url_base_encode, token_parameter_encode=token_parameter_encode)
        base_string_bytes = base_string.encode('utf-8')
        key = b'secret&'

        hashed = hmac.new(key, base_string_bytes, sha1)
        signature = quote(base64.b64encode(hashed.digest()).decode(), safe='')

        resp = self.download(url='{token_url_base}?{token_parameter}&oauth_signature={signature}'.format(token_url_base=token_url_base, token_parameter=token_parameter, signature=signature), type="get", code=None, data=None, json_data=False, data_return=True, return_json=False, retry=False, check_data=False, allow_redirects=True)

        if resp.status_code != 200:
            gui.ok(message=_.LOGIN_ERROR, heading=_.LOGIN_ERROR_TITLE)
            self.clear_session()
            return

        resource_credentials = parse_qs(resp.text)
        resource_key = resource_credentials.get('oauth_token')[0]
        resource_secret = resource_credentials.get('oauth_token_secret')[0]

        if not len(resource_key) > 0:
            gui.ok(message=_.LOGIN_ERROR, heading=_.LOGIN_ERROR_TITLE)
            self.clear_session()
            return

        settings.set(key='_resource_key', value=resource_key)
        settings.set(key='_resource_secret', value=resource_secret)

        resp = self.download(url='{base_url}/OAuth/Authorize?layout=framed&oauth_token={token}'.format(base_url=CONST_BASE_URL, token=resource_key), type="get", code=None, data=None, json_data=False, data_return=True, return_json=False, retry=False, check_data=False, allow_redirects=False)

        if (resp.status_code != 302):
            gui.ok(message=_.LOGIN_ERROR, heading=_.LOGIN_ERROR_TITLE)
            self.clear_session()
            return

        authorization = parse_qs(resp.headers['Location'])
        resource_verifier = authorization.get('oauth_verifier')[0]

        if not len(resource_verifier) > 0:
            gui.ok(message=_.LOGIN_ERROR, heading=_.LOGIN_ERROR_TITLE)
            self.clear_session()
            return

        settings.set(key='_resource_verifier', value=resource_verifier)

        token_url_base = '{base_url}/OAuth/GetAccessToken'.format(base_url=CONST_BASE_URL)
        token_parameter = 'oauth_consumer_key=key&oauth_signature_method=HMAC-SHA1&oauth_verifier=' + str(resource_verifier) + '&oauth_token={token}&oauth_version=1.0&oauth_timestamp={timestamp}&oauth_nonce={nonce}'

        url_encoded = self.oauth_encode(type="GET", base_url=token_url_base, parameters=token_parameter)

        resp = self.download(url=url_encoded, type="get", code=None, data=None, json_data=False, data_return=True, return_json=False, retry=retry, check_data=False, allow_redirects=True)

        if resp.status_code != 200:
            gui.ok(message=_.LOGIN_ERROR, heading=_.LOGIN_ERROR_TITLE)
            self.clear_session()
            return

        resource_credentials = parse_qs(resp.text)
        resource_key = resource_credentials.get('oauth_token')[0]
        resource_secret = resource_credentials.get('oauth_token_secret')[0]

        if not len(resource_key) > 0:
            gui.ok(message=_.LOGIN_ERROR, heading=_.LOGIN_ERROR_TITLE)
            self.clear_session()
            return

        settings.set(key='_resource_key', value=resource_key)
        settings.set(key='_resource_secret', value=resource_secret)

        if channels == True or settings.getInt(key='_channels_age') < int(time.time() - 86400):
            data = self.download(url='{base_url}/v6/epg/channels'.format(base_url=CONST_API_URL), type="get", code=[200], data=None, json_data=False, data_return=True, return_json=True, retry=retry, check_data=False, allow_redirects=True)

            if not data:
                gui.ok(message=_.LOGIN_ERROR, heading=_.LOGIN_ERROR_TITLE)
                self.clear_session()
                return

            self.get_channels_for_user(channels=data)

        if settings.getBool(key='save_password', default=False):
            set_credentials(username=username, password=password)
        else:
            set_credentials(username=username, password='')

        self.logged_in = True

    def clear_session(self):
        settings.remove(key='_cookies')

        try:
            self._session.clear_cookies()
        except:
            pass

    def get_channels_for_user(self, channels):
        settings.setInt(key='_channels_age', value=time.time())

        write_file(file="channels.json", data=channels, isJSON=True)

        data = u'#EXTM3U\n'
        channelno = 0

        for row in channels:
            channelno += 1
            channeldata = self.get_channel_data(row=row, channelno=channelno)
            path = 'plugin://{addonid}/?_=play_video&channel={channel}&type=channel&_l=.pvr'.format(addonid=ADDON_ID, channel=channeldata['channel_id'])
            data += u'#EXTINF:-1 tvg-id="{id}" tvg-chno="{channel}" tvg-name="{name}" tvg-logo="{logo}" group-title="TV" radio="false",{name}\n{path}\n'.format(id=channeldata['channel_id'], channel=channeldata['channel_number'], name=channeldata['label'], logo=channeldata['station_image_large'], path=path)

        write_file(file="tv.m3u8", data=data, isJSON=False)
        combine_playlist()

    def get_channel_data(self, row, channelno):
        path = ADDON_PROFILE + "images" + os.sep + str(row['Id']) + ".png"

        if os.path.isfile(path):
            image = path
        else:
            image = '{image_url}/static/channel-logos/{logo}.png'.format(image_url=CONST_IMAGE_URL, logo=row['UrlFriendlyName'])

        channeldata = {
            'channel_id': row['Id'],
            'channel_id_long': row['LongStationId'],
            'channel_friendly': row['UrlFriendlyName'],
            'channel_number': channelno,
            'description': '',
            'label': row['Title'],
            'station_image_large': image
        }

        return channeldata

    def play_url(self, type, channel=None, friendly=None, id=None):
        playdata = {'path': '', 'license': None, 'info': None}

        if not type or not len(type) > 0:
            return playdata

        if type == 'channel' and friendly:
            channel_url = '{base_url}/v6/epg/locations/{friendly}/live/1?fromDate={date}'.format(base_url=CONST_API_URL, friendly=friendly, date=datetime.datetime.now().strftime("%Y-%m-%dT%H%M%S"))
            data = self.download(url=channel_url, type="get", code=[200], data=None, json_data=False, data_return=True, return_json=True, retry=True, check_data=True, allow_redirects=True)

            if not data:
                return playdata

            for row in data:
                if not check_key(row, 'Channel') or not check_key(row, 'Locations'):
                    return playdata

                for row2 in row['Locations']:
                    id = row2['LocationId']

        if not id:
            return playdata

        if not type == 'vod':
            token_url_base = '{base_url}/v6/epg/location/{location}'.format(base_url=CONST_API_URL, location=id)
        else:
            token_url_base = '{base_url}/v6/playnow/ondemand/0/{location}'.format(base_url=CONST_API_URL, location=id)

        retry = 0

        while retry < 2:
            token_parameter = 'oauth_token={token}&oauth_consumer_key=key&oauth_signature_method=HMAC-SHA1&oauth_version=1.0&oauth_timestamp={timestamp}&oauth_nonce={nonce}'
            url_encoded = self.oauth_encode(type="GET", base_url=token_url_base, parameters=token_parameter)

            data = self.download(url=url_encoded, type="get", code=[200], data=None, json_data=False, data_return=True, return_json=True, retry=True, check_data=True, allow_redirects=True)

            if not data:
                retry += 1

                if retry == 2:
                    return playdata
            else:
                retry = 2

        if type == 'vod':
            if not check_key(data, 'VideoInformation'):
                return playdata

            info = data['VideoInformation']
            token_url_base = '{base_url}/v6/stream/handshake/Widevine/dash/VOD/{id}'.format(base_url=CONST_API_URL, id=info['Id'])
            timeshift = info['Id']
        else:
            info = data

            timeshift = ''

            if check_key(info, 'VodContentId') and len(str(info['VodContentId'])) > 0:
                token_url_base = '{base_url}/v6/stream/handshake/Widevine/dash/VOD/{id}'.format(base_url=CONST_API_URL, id=info['VodContentId'])
                timeshift = info['VodContentId']

                if type == 'channel' and channel and friendly:
                    if not gui.yes_no(message=_.START_FROM_BEGINNING, heading=info['Title']):
                        token_url_base = '{base_url}/v6/stream/handshake/Widevine/dash/Live/{friendly}'.format(base_url=CONST_API_URL, friendly=friendly)
                        timeshift = channel

            elif type == 'channel' and channel and friendly:
                token_url_base = '{base_url}/v6/stream/handshake/Widevine/dash/Live/{friendly}'.format(base_url=CONST_API_URL, friendly=friendly)
                timeshift = channel
            else:
                token_url_base = '{base_url}/v6/stream/handshake/Widevine/dash/Replay/{id}'.format(base_url=CONST_API_URL, id=id)
                timeshift = id

        retry = 0

        while retry < 2:
            token_parameter = 'oauth_token={token}&oauth_consumer_key=key&oauth_signature_method=HMAC-SHA1&playerName=NLZIET%20Meister%20Player%20Web&profile=default&maxResolution=&timeshift=' + str(timeshift) + '&oauth_version=1.0&oauth_timestamp={timestamp}&oauth_nonce={nonce}'
            url_encoded = self.oauth_encode(type="GET", base_url=token_url_base, parameters=token_parameter)

            data = self.download(url=url_encoded, type="get", code=[200], data=None, json_data=False, data_return=True, return_json=True, retry=True, check_data=True, allow_redirects=True)

            if not data:
                retry += 1

                if retry == 2:
                    return playdata
            else:
                retry = 2

        if not data or not check_key(data, 'uri'):
            return playdata

        license = data
        path = data['uri']

        real_url = "{hostscheme}://{hostname}".format(hostscheme=urlparse(path).scheme, hostname=urlparse(path).hostname)
        proxy_url = "http://127.0.0.1:{proxy_port}".format(proxy_port=settings.get(key='_proxyserver_port'))

        settings.set(key='_stream_hostname', value=real_url)
        path = path.replace(real_url, proxy_url)

        playdata = {'path': path, 'license': license, 'info': info}

        return playdata

    def vod_seasons(self, id):
        seasons = []

        program_url = '{base_url}/v6/series/{id}/fullWithSeizoenen?count=99999999&expand=true&expandlist=true&maxResults=99999999&offset=0'.format(base_url=CONST_API_URL, id=id)
        file = "cache" + os.sep + "vod_seasons_" + str(id) + ".json"

        if settings.getBool(key='enable_cache') == True and is_file_older_than_x_minutes(file=ADDON_PROFILE + file, minutes=10) == False:
            data = load_file(file=file, isJSON=True)
        else:
            data = self.download(url=program_url, type='get', code=[200], data=None, json_data=False, data_return=True, return_json=True, retry=True, check_data=True)

            if data and settings.getBool(key='enable_cache') == True:
                write_file(file=file, data=data, isJSON=True)

        if not data or not check_key(data, 'Serie'):
            return None

        season_count = 0
        type = 'seasons'

        if check_key(data, 'SeizoenenForSerie'):
            for row in data['SeizoenenForSerie']:
                season_count += 1

                seasons.append({'id': row['SeizoenId'], 'seriesNumber': row['Titel'], 'desc': data['Serie']['Omschrijving'], 'image': data['Serie']['ProgrammaAfbeelding']})

        if check_key(data, 'ItemsForSeizoen') and season_count < 2:
            seasons = []
            type = 'episodes'

            for row in data['ItemsForSeizoen']:
                duration = 0
                ep_id = ''
                desc = ''
                image = ''
                start = ''

                if check_key(row, 'AfleveringTitel'):
                    episodeTitle = row['AfleveringTitel']
                else:
                    episodeTitle = row['ProgrammaTitel']

                if check_key(row, 'Duur'):
                    duration = row['Duur']

                if check_key(row, 'ContentId'):
                    ep_id = row['ContentId']

                if check_key(row, 'ProgrammaOmschrijving'):
                    desc = row['ProgrammaOmschrijving']

                if check_key(row, 'ProgrammaAfbeelding'):
                    image = row['ProgrammaAfbeelding']

                if check_key(row, 'Uitzenddatum'):
                    start = row['Uitzenddatum']

                seasons.append({'id': ep_id, 'start': start, 'duration': duration, 'title': episodeTitle, 'seasonNumber': row['SeizoenVolgnummer'], 'episodeNumber': row['AfleveringVolgnummer'], 'desc': desc, 'image': image})

        return {'program': data['Serie'], 'type': type, 'seasons': seasons}

    def vod_season(self, series, id):
        season = []

        program_url = '{base_url}/v6/series/{series}/seizoenItems?seizoenId={id}&count=99999999&expand=true&expandlist=true&maxResults=99999999&offset=0'.format(base_url=CONST_API_URL, series=series, id=id)
        file = "cache" + os.sep + "vod_series_" + str(series) + "_season_" + str(id) + ".json"

        if settings.getBool(key='enable_cache') == True and is_file_older_than_x_minutes(file=ADDON_PROFILE + file, minutes=10) == False:
            data = load_file(file=file, isJSON=True)
        else:
            data = self.download(url=program_url, type='get', code=[200], data=None, json_data=False, data_return=True, return_json=True, retry=True, check_data=True)

            if data and settings.getBool(key='enable_cache') == True:
                write_file(file=file, data=data, isJSON=True)

        if not data:
            return None

        for row in data:
            duration = 0
            ep_id = ''
            desc = ''
            image = ''

            if check_key(row, 'AfleveringTitel') and len(row['AfleveringTitel']) > 0:
                episodeTitle = row['AfleveringTitel']
            else:
                episodeTitle = row['ProgrammaTitel']

            if check_key(row, 'Duur'):
                duration = row['Duur']

            if check_key(row, 'ContentId'):
                ep_id = row['ContentId']

            if check_key(row, 'ProgrammaOmschrijving'):
                desc = row['ProgrammaOmschrijving']

            if check_key(row, 'ProgrammaAfbeelding'):
                image = row['ProgrammaAfbeelding']

            if check_key(row, 'Uitzenddatum'):
                start = row['Uitzenddatum']

            season.append({'id': ep_id, 'start': start, 'duration': duration, 'title': episodeTitle, 'seasonNumber': row['SeizoenVolgnummer'], 'episodeNumber': row['AfleveringVolgnummer'], 'desc': desc, 'image': image})

        return season

    def vod_download(self, type):
        if type == "movies":
            url = '{base_url}/v6/tabs/GenreFilms?count=99999999&expand=true&expandlist=true&maxResults=99999999&offset=0'.format(base_url=CONST_API_URL)
        elif type == "watchahead":
            url = '{base_url}/v6/tabs/VooruitKijken2?count=99999999&expand=true&expandlist=true&maxResults=99999999&offset=0'.format(base_url=CONST_API_URL)
        elif type == "seriesbinge":
            url = '{base_url}/v6/tabs/SeriesBingewatch?count=99999999&expand=true&expandlist=true&maxResults=99999999&offset=0'.format(base_url=CONST_API_URL)
        elif type == "mostviewed":
            url = '{base_url}/v6/tabs/MostViewed?count=99999999&expand=true&expandlist=true&maxResults=99999999&offset=0'.format(base_url=CONST_API_URL)
        elif type == "tipfeed":
            url = '{base_url}/v6/tabs/Tipfeed?count=99999999&expand=true&expandlist=true&maxResults=99999999&offset=0'.format(base_url=CONST_API_URL)
        else:
            return None

        file = "cache" + os.sep + "vod_" + type + ".json"

        if settings.getBool(key='enable_cache') == True and is_file_older_than_x_minutes(file=ADDON_PROFILE + file, minutes=10) == False:
            data = load_file(file=file, isJSON=True)
        else:
            data = self.download(url=url, type='get', code=[200], data=None, json_data=False, data_return=True, return_json=True, retry=True, check_data=True)

            if data and settings.getBool(key='enable_cache') == True:
                write_file(file=file, data=data, isJSON=True)

        if not data or not check_key(data, 'Items'):
            return None

        return self.process_vod(data=data)

    def search(self, query):
        file = "cache" + os.sep + "search_" + clean_filename(query) + ".json"

        if settings.getBool(key='enable_cache') == True and is_file_older_than_x_minutes(file=ADDON_PROFILE + file, minutes=10) == False:
            data = load_file(file=file, isJSON=True)
        else:
            data = self.download(url='{base_url}/v6/search/v2/combined?searchterm={query}&maxSerieResults=99999999&maxVideoResults=99999999&expand=true&expandlist=true'.format(base_url=CONST_API_URL, query=query), type='get', code=[200], data=None, json_data=False, data_return=True, return_json=True, retry=True, check_data=True)

            if data and settings.getBool(key='enable_cache') == True:
                write_file(file=file, data=data, isJSON=True)

        if not data:
            return None

        items = []

        if check_key(data, 'Series'):
            for row in data['Series']:
                item = {}

                if not check_key(row, 'SerieId') or not check_key(row, 'Name'):
                    continue

                desc = ''

                if check_key(row, 'Omschrijving'):
                    desc = row['Omschrijving']

                if check_key(row, 'ProgrammaAfbeelding'):
                    if 'http' in row['ProgrammaAfbeelding']:
                        image = row['ProgrammaAfbeelding']
                    else:
                        image_ar = row['ProgrammaAfbeelding'].rsplit('/', 1)

                        if image_ar[1]:
                            image = "https://nlzietprodstorage.blob.core.windows.net/thumbnails/hd1080/" + image_ar[1];
                        else:
                            image = "https://nlzietprodstorage.blob.core.windows.net/" + row['ProgrammaAfbeelding'];

                item['id'] = row['SerieId']
                item['title'] = row['Name']
                item['desc'] = desc
                item['type'] = 'Serie'
                item['image'] = image
                item['timestamp'] = 0

                items.append(item)

        if check_key(data, 'Videos'):
            for row in data['Videos']:
                item = {}

                if not check_key(row, 'Video') or not check_key(row['Video'], 'VideoId') or not check_key(row['Video'], 'VideoType') or (not check_key(row, 'Titel') and (not check_key(row, 'Serie') or not check_key(row['Serie'], 'Titel'))):
                    continue

                id = row['Video']['VideoId']

                if row['Video']['VideoType'] == 'VOD':
                    type = 'VideoTile'
                elif row['Video']['VideoType'] == 'Replay':
                    type = 'EpgTile'
                elif row['Video']['VideoType'] == 'Serie':
                    type = 'SerieTile'
                else:
                    continue

                basetitle = ''
                desc = ''
                start = ''
                duration = 0
                timestamp = 0

                if check_key(row, 'Serie') and check_key(row['Serie'], 'Titel'):
                    basetitle = row['Serie']['Titel']

                if check_key(row, 'Titel'):
                    if len(row['Titel']) > 0 and basetitle != row['Titel']:
                        if len(basetitle) > 0:
                            basetitle += ": " + row['Titel']
                        else:
                            basetitle = row['Titel']

                if check_key(row, 'Omschrijving'):
                    desc = row['Omschrijving']

                if check_key(row, 'Duur'):
                    duration = row['Duur']

                if check_key(row, 'AfbeeldingUrl'):
                    if 'http' in row['AfbeeldingUrl']:
                        image = row['AfbeeldingUrl']
                    else:
                        image_ar = row['AfbeeldingUrl'].rsplit('/', 1)

                        if image_ar[1]:
                            image = "https://nlzietprodstorage.blob.core.windows.net/thumbnails/hd1080/" + image_ar[1];
                        else:
                            image = "https://nlzietprodstorage.blob.core.windows.net/" + row['AfbeeldingUrl'];

                if check_key(row, 'Uitzenddatum'):
                    start = row['Uitzenddatum']
                    timestamp = time.mktime(time.strptime(start, "%Y-%m-%dT%H:%M:%S"))

                item['id'] = id
                item['title'] = basetitle
                item['desc'] = desc
                item['duration'] = duration
                item['type'] = type
                item['image'] = image
                item['start'] = start
                item['timestamp'] = timestamp

                items.append(item)

        return items

    def process_vod(self, data):
        data = self.mix(data['Items']['npo'], data['Items']['rtl'], data['Items']['sbs'])

        items = []

        for row in data:
            item = {}

            if not check_key(row, 'Type'):
                continue

            if row['Type'] == 'Vod':
                key = 'VideoTile'
            elif row['Type'] == 'Epg':
                key = 'EpgTile'
            elif row['Type'] == 'Serie':
                key = 'SerieTile'
            else:
                continue

            if not check_key(row, key):
                continue

            entry = row[key]

            if not check_key(entry, 'Id') or (not check_key(entry, 'Titel') and (not check_key(entry, 'Serie') or not check_key(entry['Serie'], 'Titel'))):
                continue

            id = entry['Id']
            basetitle = ''
            desc = ''
            start = ''
            duration = 0
            timestamp = 0

            if check_key(entry, 'Serie') and check_key(entry['Serie'], 'Titel'):
                basetitle = entry['Serie']['Titel']

            if check_key(entry, 'Titel'):
                if len(entry['Titel']) > 0 and basetitle != entry['Titel']:
                    if len(basetitle) > 0:
                        basetitle += ": " + entry['Titel']
                    else:
                        basetitle = entry['Titel']

            if check_key(entry, 'Omschrijving'):
                desc = entry['Omschrijving']

            if check_key(entry, 'Duur'):
                duration = entry['Duur']

            if check_key(entry, 'AfbeeldingUrl'):
                if 'http' in entry['AfbeeldingUrl']:
                    image = entry['AfbeeldingUrl']
                else:
                    image_ar = entry['AfbeeldingUrl'].rsplit('/', 1)

                    if image_ar[1]:
                        image = "https://nlzietprodstorage.blob.core.windows.net/thumbnails/hd1080/" + image_ar[1];
                    else:
                        image = "https://nlzietprodstorage.blob.core.windows.net/" + entry['AfbeeldingUrl'];

            if check_key(entry, 'Uitzenddatum'):
                start = entry['Uitzenddatum']
                timestamp = datetime.datetime.fromtimestamp(time.mktime(time.strptime(start, "%Y-%m-%dT%H:%M:%S")))

            item['id'] = id
            item['title'] = basetitle
            item['desc'] = desc
            item['duration'] = duration
            item['type'] = row['Type']
            item['image'] = image
            item['start'] = start
            item['timestamp'] = timestamp

            items.append(item)

        return items

    def check_data(self, resp, json=False):
        return True

    def download(self, url, type, code=None, data=None, json_data=True, data_return=True, return_json=True, retry=True, check_data=True, allow_redirects=True):
        if type == "post" and data:
            if json_data == True:
                resp = self._session.post(url, json=data, allow_redirects=allow_redirects)
            else:
                resp = self._session.post(url, data=data, allow_redirects=allow_redirects)
        else:
            resp = getattr(self._session, type)(url, allow_redirects=allow_redirects)

        if (resp.status_code == 403 and 'Teveel verschillende apparaten' in resp.text):
            gui.ok(message=_.TOO_MANY_DEVICES)
            return None

        if (code and not resp.status_code in code) or (check_data == True and self.check_data(resp=resp) == False):
            if retry != True:
                return None

            self.new_session(force=True, retry=False)

            if self.logged_in != True:
                return None

            if type == "post" and data:
                if json_data == True:
                    resp = self._session.post(url, json=data, allow_redirects=allow_redirects)
                else:
                    resp = self._session.post(url, data=data, allow_redirects=allow_redirects)
            else:
                resp = getattr(self._session, type)(url, allow_redirects=allow_redirects)

            if (code and not resp.status_code in code) or (check_data == True and self.check_data(resp=resp) == False):
                return None

        if data_return == True:
            try:
                if return_json == True:
                    return resp.json()
                else:
                    return resp
            except:
                return None

        return True

    def oauth_encode(self, type, base_url, parameters):
        base_url_encode = quote(base_url, safe='')
        nonce = ''.join(random.choice(string.ascii_uppercase + string.ascii_lowercase + string.digits) for _ in range(6))
        token_timestamp = int(time.time())

        parameters = parameters.format(token=settings.get(key='_resource_key'), timestamp=token_timestamp, nonce=nonce)

        parsed_parameters = parse_qs(parameters, keep_blank_values=True)
        encode_string = ''

        for parameter in sorted(parsed_parameters):
            encode_string += quote(str(parameter).replace(" ", "%2520") + "=" + str(parsed_parameters[parameter][0]).replace(" ", "%2520") + "&", safe='%')

        if encode_string.endswith("%26"):
            encode_string = encode_string[:-len("%26")]

        base_string = '{type}&{token_url_base_encode}&{token_parameter_encode}'.format(type=type, token_url_base_encode=base_url_encode, token_parameter_encode=encode_string)
        base_string_bytes = base_string.encode('utf-8')
        key = 'secret&{key}'.format(key=settings.get(key='_resource_secret'))
        key_bytes = key.encode('utf-8')

        hashed = hmac.new(key_bytes, base_string_bytes, sha1)
        signature = quote(base64.b64encode(hashed.digest()).decode(), safe='')

        url = '{token_url_base}?{token_parameter}&oauth_signature={signature}'.format(token_url_base=base_url, token_parameter=parameters, signature=signature)

        return url

    def mix(self, list1, list2, list3=None):
        if list3:
            i,j,k = iter(list1), iter(list2), iter(list3)
            result = [item for sublist in zip(i,j,k) for item in sublist]
            result += [item for item in i]
            result += [item for item in j]
            result += [item for item in k]
        else:
            i,j = iter(list1), iter(list2)
            result = [item for sublist in zip(i,j) for item in sublist]
            result += [item for item in i]
            result += [item for item in j]

        return result