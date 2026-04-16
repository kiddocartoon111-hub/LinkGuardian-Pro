import requests
import time
import random
import os
import logging

logger = logging.getLogger(__name__)

class LinkMonitor:
    def __init__(self, scraper_api_key=None):
        self.scraper_api_key = scraper_api_key or os.getenv('SCRAPER_API_KEY')
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        ]

    def check_link(self, url: str, platform: str = 'generic'):
        # Layer 1: Direct
        result = self._direct_check(url)
        if result and result.get('status_code', 500) < 500:
            result['layer_used'] = 'direct'
            return self._enrich_result(result, platform)
        # Layer 2: ScraperAPI
        if self.scraper_api_key:
            result = self._scraperapi_check(url)
            if result and result.get('status_code', 500) < 500:
                result['layer_used'] = 'scraperapi'
                return self._enrich_result(result, platform)
        return {'status': 'error', 'error': 'All layers failed', 'response_time': 0, 'layer_used': 'none'}

    def _direct_check(self, url):
        try:
            headers = {'User-Agent': random.choice(self.user_agents)}
            start = time.time()
            r = requests.get(url, timeout=15, headers=headers, allow_redirects=True)
            return {'status_code': r.status_code, 'response_time': int((time.time()-start)*1000), 'content': r.text[:5000]}
        except:
            return None

    def _scraperapi_check(self, url):
        try:
            proxy_url = f"http://api.scraperapi.com?api_key={self.scraper_api_key}&url={url}&render=true"
            start = time.time()
            r = requests.get(proxy_url, timeout=30)
            return {'status_code': r.status_code, 'response_time': int((time.time()-start)*1000), 'content': r.text[:5000]}
        except:
            return None

    def _enrich_result(self, result, platform):
        content = result.get('content', '').lower()
        sc = result.get('status_code', 0)
        if sc >= 400:
            result['status'] = 'broken'
        elif self._is_out_of_stock(content, platform):
            result['status'] = 'out_of_stock'
        elif sc in [200, 201, 301, 302]:
            result['status'] = 'active'
        else:
            result['status'] = 'unknown'
        if 'content' in result:
            del result['content']
        return result

    def _is_out_of_stock(self, content, platform):
        kw = {
            'amazon': ['out of stock', 'currently unavailable'],
            'flipkart': ['out of stock', 'sold out'],
            'generic': ['out of stock', 'sold out', 'unavailable']
        }
        for k in kw.get(platform.lower(), kw['generic']):
            if k in content:
                return True
        return False
