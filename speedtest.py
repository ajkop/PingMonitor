import bisect
import re
import xml.etree.ElementTree as ET
from math import sqrt
from statistics import mean
from time import time

import requests


class SpeedTest:

    def __init__(self, server=None):
        self.host = server or self.getserver()
        self.http_host = f'http://{self.host}'

    def check_http_success(self, request_obj):
        if request_obj.status_code == 200:
            return
        else:
            raise NotImplementedError

    def getserver(self):
        base_url = 'https://www.speedtest.net'
        client_response = requests.get(f'{base_url}/speedtest-config.php')

        self.check_http_success(client_response)
        parsed_client_xml = ET.fromstring(client_response.text)

        client_index = None
        for index, child in enumerate(parsed_client_xml):
            if child.tag == "client":
                client_index = index
                break

        if client_index is None:
            raise NotImplementedError

        client_info = parsed_client_xml[client_index].attrib
        my_lat = float(client_info['lat'])
        my_lon = float(client_info['lon'])

        server_response = requests.get(f'{base_url}/speedtest-servers.php')
        self.check_http_success(server_response)
        parsed_server_xml = ET.fromstring(server_response.text)

        server_info_index = None
        for index, item in enumerate(parsed_server_xml.findall('servers')):
            if item.tag == "servers":
                server_info_index = index
                break

        if server_info_index is None:
            raise NotImplementedError

        servers = [{'url': server.attrib['url'], 'lat': server.attrib['lat'], 'lon': server.attrib['lon']}
                   for server in parsed_server_xml[server_info_index]]

        sorted_server_list = []
        for server in servers:
            s_lat = float(server['lat'])
            s_lon = float(server['lon'])
            distance = sqrt(pow(s_lat - my_lat, 2) + pow(s_lon - my_lon, 2))
            bisect.insort_left(sorted_server_list, (distance, server['url']))
        best_server = (99999, '')
        for server in sorted_server_list[:10]:
            match = re.search(r'http://([^/]+)/speedtest/upload\.php', server[1])
            if not match:
                continue

            server_host = match.groups()[0]
            latency = self.ping(server_host)
            if latency < best_server[0]:
                best_server = (latency, server_host)
        if best_server is None:
            raise NotImplementedError('Cannot find a test server')
        return best_server[1]

    def _get_ms(self, start_time):
        return (time() - start_time) * 1000

    def ping(self, server=None):
        server = server or self.host

        times = []
        worst = 0
        for i in range(5):
            total_start_time = time()
            requests.get(f'http://{server}/speedtest/latency.txt')
            total_ms = (time() - total_start_time) * 1000
            times.append(total_ms)  # total_ms will be in seconds, multiply by 1000 to get ms
            if total_ms > worst:
                worst = total_ms
        times.remove(worst)
        total_ms = mean(times)  # get the mean ping time after removing worst result
        return total_ms

    def check_download(self):
        download_files = [
            '/speedtest/random350x350.jpg',
            '/speedtest/random500x500.jpg',
            '/speedtest/random1500x1500.jpg'
        ]

        total_download = 0
        start_time = time()
        s = requests.Session()
        for down_file in download_files:
            r = s.get(f'http://speedtest05.suddenlink.net:8080{down_file}')
            total_download += len(r.content)

        total_ms = self._get_ms(start_time)
        bytes_per_ms = (total_download * 8000) / total_ms
        return self._convert_bytes(bytes_per_ms)

    def _convert_bytes(self, speed):
        units = ['bps', 'Kbps', 'Mbps', 'Gbps']
        unit = 0
        while speed >= 1024:
            speed /= 1024
            unit += 1
        return '%0.2f %s' % (speed, units[unit])



