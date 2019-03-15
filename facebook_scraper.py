import codecs
from datetime import datetime
import json
import re
import time

from requests import RequestException
from requests_html import HTMLSession, HTML


__all__ = ['get_posts']


_base_url = 'https://m.facebook.com'

_likes_regex = re.compile(r'([0-9,.]+)\s+Like')
_comments_regex = re.compile(r'([0-9,.]+)\s+Comment')
_shares_regex = re.compile(r'([0-9,.]+)\s+Shares')

_cursor_regex = re.compile(r'href:"(/page_content[_/?=&%\w]+)"')
_cursor_regex_2 = re.compile(r'href":"(\\/page_content[^"]+)"')

_image_regex = re.compile(r"background-image: url\('(.+)'\)")


def get_posts(account, pages=10, timeout=5, sleep=0):
    url = f'{_base_url}/{account}/posts/'

    session = HTMLSession()
    session.headers.update({'Accept-Language': 'en-US,en;q=0.5'})

    response = session.get(url, timeout=timeout)
    html = response.html
    cursor_blob = html.html

    while True:
        for article in html.find('article'):
            yield _extract_post(article)

        pages -= 1
        if pages == 0:
            return

        cursor = _find_cursor(cursor_blob)
        next_url = f'{_base_url}{cursor}'

        if sleep:
            time.sleep(sleep)

        try:
            response = session.get(next_url, timeout=timeout)
            response.raise_for_status()
            data = json.loads(response.text.replace('for (;;);', '', 1))
        except (RequestException, ValueError):
            return

        for action in data['payload']['actions']:
            if action['cmd'] == 'replace':
                html = HTML(html=action['html'], url=_base_url)
            elif action['cmd'] == 'script':
                cursor_blob = action['code']


def _extract_post(article):
    return {
        'post_id': _extract_post_id(article),
        'text': _extract_text(article),
        'time': _extract_time(article),
        'image': _extract_image(article),
        'likes': _find_and_search(article, 'footer', _likes_regex, _parse_int) or 0,
        'comments': _find_and_search(article, 'footer', _comments_regex, _parse_int) or 0,
        'shares':  _find_and_search(article, 'footer', _shares_regex, _parse_int) or 0,
    }


def _extract_post_id(article):
    try:
        data_ft = json.loads(article.attrs['data-ft'])
        return data_ft['mf_story_key']
    except (KeyError, ValueError):
        return None


def _extract_text(article):
    paragraph = article.find('p', first=True)
    return paragraph and paragraph.text


def _extract_time(article):
    try:
        data_ft = json.loads(article.attrs['data-ft'])
        page_insights = data_ft['page_insights']
    except (KeyError, ValueError):
        return None

    for page in page_insights.values():
        try:
            timestamp = page['post_context']['publish_time']
            return datetime.fromtimestamp(timestamp)
        except (KeyError, ValueError):
            continue
    return None


def _extract_image(article):
    story_container = article.find('div.story_body_container', first=True)
    other_containers = story_container.xpath('div/div')

    for container in other_containers:
        image_container = container.find('.img', first=True)
        if image_container is None:
            continue

        style = image_container.attrs.get('style', '')
        match = _image_regex.search(style)
        if match:
            return _decode_css_url(match.groups()[0])

    return None


def _find_and_search(article, selector, pattern, cast=str):
    container = article.find(selector, first=True)
    text = container and container.text
    match = text and pattern.search(text)
    return match and cast(match.groups()[0])


def _find_cursor(text):
    match = _cursor_regex.search(text)
    if match:
        return match.groups()[0]

    match = _cursor_regex_2.search(text)
    if match:
        value = match.groups()[0]
        return value.encode('utf-8').decode('unicode_escape').replace('\\/', '/')

    return None


def _parse_int(value):
    return int(''.join(filter(lambda c: c.isdigit(), value)))


def _decode_css_url(url):
    url = re.sub(r'\\(..) ', r'\\x\g<1>', url)
    url, _ = codecs.unicode_escape_decode(url)
    return url
