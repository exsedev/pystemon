import logging.handlers
import time
import random
import requests
import socket

try:
    from urllib.error import HTTPError, URLError
except ImportError:
    from urllib2 import HTTPError, URLError

logger = logging.getLogger('pystemon')

class PystemonUA():

    def __init__(self, proxies_list, user_agents_list = [], retries_client = 5, retries_server = 100):
        self.user_agents_list = user_agents_list
        self.proxies_list = proxies_list
        self.retries_client = retries_client
        self.retries_server = retries_server

    def get_random_user_agent(self):
        if self.user_agents_list:
            return random.choice(self.user_agents_list)
        return 'Python-urllib/2.7'

    def __parse_http__(self, url, session, random_proxy):
        logger.debug("Parsing response for url '{0}'".format(url))
        try:
            response = session.get(url, stream=True)
            response.raise_for_status()
            res = {'response': response}
        except HTTPError as e:
            self.proxies_list.failed_proxy(random_proxy)
            logger.warning("!!Proxy error on {0}.".format(url))
            if 404 == e.code:
                htmlPage = e.read()
                logger.warning("404 from proxy received for {url}".format(url=url))
                res = {'loop_client': True, 'wait': 60}
            elif 500 == e.code:
                htmlPage = e.read()
                logger.warning("500 from proxy received for {url}".format(url=url))
                res = {'loop_server': True, 'wait': 60}
            elif 504 == e.code:
                htmlPage = e.read()
                logger.warning("504 from proxy received for {url}".format(url=url))
                res = {'loop_server': True, 'wait': 60}
            elif 429 == e.code:
                retry_after = response.headers.get('Retry-After', 60)
                if retry_after.isdigit():
                    wait = int(retry_after)
                    logger.warning("429 from proxy received for {url} requesting Retry-After {wait} seconds".format(url=url, wait=wait))
                else:
                    logger.warning("429 from proxy received for {url}".format(url=url))
                    wait = 60
                res = {'loop_server': True, 'wait': wait}
            elif 502 == e.code:
                htmlPage = e.read()
                logger.warning("502 from proxy received for {url}".format(url=url))
                res = {'loop_server': True, 'wait': 60}
            elif 403 == e.code:
                htmlPage = e.read()
                if 'Please slow down' in htmlPage or 'has temporarily blocked your computer' in htmlPage or 'blocked' in htmlPage:
                    logger.warning("Slow down message received for {url}".format(url=url))
                    res = {'loop_server': True, 'wait': 60}
                else:
                    logger.warning("403 from proxy received for {url}, aborting".format(url=url))
                    res = {'abort': True}
            else:
                logger.warning("ERROR: HTTP Error ##### {e} ######################## {url}".format(e=e, url=url))
                res = {'abort': True}
        logger.debug("Parsing response done for url '{0}'".format(url))
        return res


    def __download_url__(self, url, session, random_proxy):
        try:
            res = self.__parse_http__(url, session, random_proxy)
        except URLError as e:
            logger.debug("ERROR: URL Error ##### {e} ######################## ".format(e=e, url=url))
            if random_proxy:  # remove proxy from the list if needed
                self.proxies_list.failed_proxy(random_proxy)
                logger.warning("Failed to download the page because of proxy error: {0}".format(url))
                res = {'loop_server': True}
            elif 'timed out' in e.reason:
                logger.warning("Timed out or slow down for {url}".format(url=url))
                res = {'loop_server': True, 'wait': 60}
        except socket.timeout as e:
            logger.debug("ERROR: timeout ##### {e} ######################## ".format(e=e, url=url))
            if random_proxy:  # remove proxy from the list if needed
                self.proxies_list.failed_proxy(random_proxy)
                logger.warning("Failed to download the page because of socket error {0}:".format(url))
                res = {'loop_server': True}
        except requests.ConnectionError as e:
            logger.debug("ERROR: connection failed ##### {e} ######################## ".format(e=e, url=url))
            if random_proxy:  # remove proxy from the list if needed
                self.proxies_list.failed_proxy(random_proxy)
            logger.warning("Failed to download the page because of connection error: {0}".format(url))
            logger.error(traceback.format_exc())
            res = {'loop_server': True, 'wait': 60}
        except Exception as e:
            logger.debug("ERROR: Other HTTPlib error ##### {e} ######################## ".format(e=e, url=url))
            if random_proxy:  # remove proxy from the list if needed
                self.proxies_list.failed_proxy(random_proxy)
            logger.warning("Failed to download the page because of other HTTPlib error proxy error: {0}".format(url))
            logger.error(traceback.format_exc())
            res = {'loop_server': True}
        # do NOT try to download the url again here, as we might end in enless loop
        return res


    def download_url(self, url, data=None, cookie=None, wait=0, throttler=None):
        # let's not recurse where exceptions can raise exceptions can raise exceptions can...
        response = None
        loop_client = 0
        loop_server = 0
        logger.debug("download_url: about to fetch url '{0}'".format(url))
        while (response is None) and (loop_client < self.retries_client) and (loop_server < self.retries_server):
            try:
                if throttler is not None:
                    # wait until the throttler allows us to download
                    logger.debug("download_url: throttling enabled, waiting for permission for download ...")
                    throttler.wait()
                    logger.debug("download_url: permission to download granted")
                session = requests.Session()
                random_proxy = None
                if self.proxies_list:
                    random_proxy = self.proxies_list.get_random_proxy()
                    if random_proxy:
                        session.proxies = {'http': random_proxy}
                user_agent = self.get_random_user_agent()
                session.headers.update({'User-Agent': user_agent, 'Accept-Charset': 'utf-8'})
                if cookie:
                    session.headers.update({'Cookie': cookie})
                if data:
                    session.headers.update(data)
            except Exception as e:
                logger.error("ERROR: unable to initialize session, aborting: {0}".format(e))
                return None
            if wait > 0:
                logger.debug("Waiting {s}s before retrying {url}".format(s=wait, url=url))
                time.sleep(wait)
            logger.debug('Downloading url: {url} with proxy: {proxy} and user-agent: {ua}'.format(url=url, proxy=random_proxy, ua=user_agent))
            if (loop_client > 0) or (loop_server > 0):
                logger.warning("Retry client={lc}/{tc}, server={ls}/{ts} for {url}".format(
                    lc=loop_client, tc=self.retries_client,
                    ls=loop_server, ts=self.retries_server,
                    url=url
                ))
            res = self.__download_url__(url, session, random_proxy)
            logger.debug('Downloading url: {url} done.'.format(url=url))
            response = res.get('response', None)
            if res.get('abort', False):
                break
            if res.get('loop_client', False):
                loop_client += 1
            if res.get('loop_server', False):
                loop_server += 1
            wait = res.get('wait', wait)

        if response is None:
            # Client errors (40x): if more than 5 recursions, give up on URL (used for 404 case)
            if loop_client >= self.retries_client:
                logger.error("ERROR: too many client errors, giving up on {0}".format(url))
            # Server errors (50x): if more than 100 recursions, give up on URL
            elif loop_server >= self.retries_server:
                logger.error("ERROR: too many server errors, giving up on {0}".format(url))
            else:
                logger.error("ERROR: too many errors, giving up on {0}".format(url))

        return response

