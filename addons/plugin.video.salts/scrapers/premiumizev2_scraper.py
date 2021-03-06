"""
    SALTS XBMC Addon
    Copyright (C) 2014 tknorris

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""
import re
import urlparse
import kodi
import log_utils  # @UnusedImport
from salts_lib import scraper_utils
from salts_lib.constants import FORCE_NO_MATCH
from salts_lib.constants import VIDEO_TYPES
from salts_lib.utils2 import i18n
from salts_lib.constants import QUALITIES
import scraper

VIDEO_EXT = ['MKV', 'AVI', 'MP4']
MIN_MEG = 100
LIST_URL = '/api/transfer/list'
FOLDER_URL = '/api/folder/list'
BROWSE_URL = '/api/torrent/browse'

class Scraper(scraper.Scraper):
    base_url = ''
    base_name = 'Premiumize.me'

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        if kodi.get_setting('%s-use_https' % (self.__class__.base_name)) == 'true':
            scheme = 'https'
            prefix = 'www'
        else:
            scheme = 'http'
            prefix = 'http'
        base_url = kodi.get_setting('%s-base_url' % (self.__class__.base_name))
        self.base_url = scheme + '://' + prefix + '.' + base_url
        self.username = kodi.get_setting('%s-username' % (self.__class__.base_name))
        self.password = kodi.get_setting('%s-password' % (self.__class__.base_name))

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.MOVIE, VIDEO_TYPES.EPISODE, VIDEO_TYPES.SEASON])

    @classmethod
    def get_name(cls):
        return 'Premiumize.V2'

    def get_sources(self, video):
        hosters = []
        source_url = self.get_url(video)
        if source_url and source_url != FORCE_NO_MATCH:
            norm_title = scraper_utils.normalize_title(video.title)
            for stream in self.__get_videos(source_url, video):
                if video.video_type == VIDEO_TYPES.EPISODE and not self.__match_episode(video, norm_title, stream['name']):
                    continue

                host = self._get_direct_hostname(stream['url'])
                hoster = {'multi-part': False, 'class': self, 'views': None, 'url': stream['url'], 'rating': None, 'host': host, 'quality': stream['quality'], 'direct': True}
                if 'size' in stream: hoster['size'] = scraper_utils.format_size(stream['size'])
                if 'name' in stream: hoster['extra'] = stream['name']
                hosters.append(hoster)
                         
        return hosters
    
    def __get_videos(self, source_url, video):
        videos = []
        query = urlparse.parse_qs(source_url)
        if 'hash' in query:
            url = urlparse.urljoin(self.base_url, BROWSE_URL)
            js_data = self._http_get(url, params={'hash': query['hash'][0]}, cache_limit=1)
            if 'content' in js_data:
                videos = self.__get_videos2(js_data['content'], video)
        return videos
        
    def __get_videos2(self, content, video):
        videos = []
        for key in content:
            item = content[key]
            if item['type'].lower() == 'dir':
                videos += self.__get_videos2(item['children'], video)
            else:
                if item['ext'].upper() in VIDEO_EXT and ('size' not in item or int(item['size']) > (MIN_MEG * 1024 * 1024)):
                    temp_video = {'name': item['name'], 'url': item['url'], 'size': item['size']}
                    temp_video['quality'] = self.__get_quality(item, video)
                    videos.append(temp_video)
                    if 'transcoded' in item and item['transcoded']:
                        transcode = item['transcoded']
                        name = '(Transcode) %s' % (item['name'])
                        temp_video = {'name': name, 'url': transcode['url']}
                        temp_video['quality'] = self.__get_quality(transcode, video)
                        if 'size' in transcode: temp_video['size'] = transcode['size']
                        videos.append(temp_video)
        return videos
    
    def __get_quality(self, item, video):
        if 'width' in item and item['width']:
            return scraper_utils.width_get_quality(item['width'])
        elif 'height' in item and item['height']:
            return scraper_utils.height_get_quality(item['height'])
        elif 'name' in item:
            if video.video_type == VIDEO_TYPES.MOVIE:
                meta = scraper_utils.parse_movie_link(item['name'])
            else:
                meta = scraper_utils.parse_episode_link(item['name'])
            return scraper_utils.height_get_quality(meta['height'])
        else:
            return QUALITIES.HIGH
        
    def get_url(self, video):
        url = super(self.__class__, self).get_url(video)
        if url is None and video.video_type == VIDEO_TYPES.EPISODE:
            return self.__find_episodes(video)
        return url

    def _get_episode_url(self, season_url, video):
        query = urlparse.parse_qs(season_url)
        if 'hash' in query:
            hash_id = query['hash'][0]
            norm_title = scraper_utils.normalize_title(video.title)
            for stream in self.__get_videos(season_url, video):
                if self.__match_episode(video, norm_title, stream['name'], hash_id):
                    return season_url
        
    def __find_episodes(self, video):
        if not scraper_utils.force_title(video):
            norm_title = scraper_utils.normalize_title(video.title)
            for item in self.__get_torrents():
                match_url = self.__match_episode(video, norm_title, item['name'], item['hash'])
                if match_url is not None:
                    return match_url
                
    def __match_episode(self, video, norm_title, title, hash_id=None):
        sxe_patterns = [
            '(.*?)[._ -]s([0-9]+)[._ -]*e([0-9]+)',
            '(.*?)[._ -]([0-9]+)x([0-9]+)',
            '(.*?)[._ -]([0-9]+)([0-9][0-9])',
            '(.*?)[._ -]?season[._ -]*([0-9]+)[._ -]*-?[._ -]*episode[._ -]*([0-9]+)',
            '(.*?)[._ -]\[s([0-9]+)\][._ -]*\[e([0-9]+)\]',
            '(.*?)[._ -]s([0-9]+)[._ -]*ep([0-9]+)']
        
        show_title = ''
        for pattern in sxe_patterns:
            match = re.search(pattern, title, re.I)
            if match:
                temp_title, season, episode = match.groups()
                if int(season) == int(video.season) and int(episode) == int(video.episode):
                    show_title = temp_title
                    break
        else:
            airdate_fallback = kodi.get_setting('airdate-fallback') == 'true' and video.ep_airdate
            if video.ep_airdate and airdate_fallback:
                airdate_pattern = '(.*?)[. _]%s[. _]%02d[. _]%02d[. _]' % (video.ep_airdate.year, video.ep_airdate.month, video.ep_airdate.day)
                match = re.search(airdate_pattern, title)
                if match:
                    show_title = match.group(1)
        
        if show_title and norm_title in scraper_utils.normalize_title(show_title):
            return 'hash=%s' % (hash_id)
    
    def __get_torrents(self, folder_id=None):
        torrents = []
        url = urlparse.urljoin(self.base_url, FOLDER_URL)
        if folder_id is not None:
            url += '?id=%s' % (folder_id)
            
        js_data = self._http_get(url, cache_limit=.001)
        if 'content' in js_data:
            for item in js_data['content']:
                if item['type'] == 'folder':
                    torrents += self.__get_torrents(item['id'])
                elif item['type'] == 'torrent':
                    torrents.append(item)
                    
        return torrents
    
    def search(self, video_type, title, year, season=''):
        results = []
        norm_title = scraper_utils.normalize_title(title)
        for item in self.__get_torrents():
            if title or year or season:
                is_season = re.search('(.*?[._ ]season[._ ]+(\d+))[._ ]?(.*)', item['name'], re.I)
                if (not is_season and video_type == VIDEO_TYPES.SEASON) or (is_season and video_type == VIDEO_TYPES.MOVIE):
                    continue
                
                if re.search('[._ ]S\d+E\d+[._ ]', item['name'], re.I): continue  # skip episodes
                if video_type == VIDEO_TYPES.SEASON:
                    match_title, match_season, extra = is_season.groups()
                    if season and int(match_season) != int(season): continue
                    match_year = ''
                    match_title = re.sub('[._-]', ' ', match_title)
                else:
                    match = re.search('(.*?)\(?(\d{4})\)?(.*)', item['name'])
                    if match:
                        match_title, match_year, extra = match.groups()
                    else:
                        match_title, match_year, extra = item['name'], '', ''
            else:
                match_title, match_year, extra = item['name'], '', ''
                    
            match_title = match_title.strip()
            extra = extra.strip()
            if norm_title in scraper_utils.normalize_title(match_title) and (not year or not match_year or year == match_year):
                result_title = match_title
                if extra: result_title += ' [%s]' % (extra)
                result = {'title': result_title, 'year': match_year, 'url': 'hash=%s' % (item['hash'])}
                results.append(result)
        
        return results

    @classmethod
    def get_settings(cls):
        name = cls.get_name()
        settings = [
            '         <setting id="%s-enable" type="bool" label="%s %s" default="true" visible="true"/>' % (name, name, i18n('enabled')),
            '         <setting id="%s-sub_check" type="bool" label="    %s" default="false" visible="eq(-1,true)"/>' % (name, i18n('page_existence')),
            '         <setting id="%s_last_results" type="number" default="0" visible="false"/>' % (name)
        ]
        return settings

    def _http_get(self, url, params=None, data=None, allow_redirect=True, cache_limit=8):
        if not self.username or not self.password:
            return {}
        
        if data is None: data = {}
        data.update({'customer_id': self.username, 'pin': self.password})
        result = super(self.__class__, self)._http_get(url, params=params, data=data, allow_redirect=allow_redirect, cache_limit=cache_limit)
        js_result = scraper_utils.parse_json(result, url)
        if 'status' in js_result and js_result['status'] == 'error':
            log_utils.log('Premiumize V2 Scraper Error: %s - (%s)' % (url, js_result.get('message', 'Unknown Error')), log_utils.LOGWARNING)
            js_result = {}
            
        return js_result
