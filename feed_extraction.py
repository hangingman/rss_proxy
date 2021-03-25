#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import os
import json
from typing import Optional
from urllib.request import build_opener, install_opener, ProxyHandler

import yaml
import requests
import urllib
import feedparser
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone

from dateutil.parser import parse
from dict_digger import dig


def main(args: argparse.Namespace):
    config: dict = load_config()
    target_url: str = config['target_url']
    webhook_url: str = config['webhook_url']
    proxy: ProxyHandler = proxy_auth(config)

    # 日付指定(from)の設定
    target_date = yesterday()
    if args.from_date:
        target_date = args.from_date

    post_to_slack(target_url, proxy, webhook_url, target_date)


def load_config(path: Optional[str] = None) -> dict:
    if path is None:
        path = os.path.join(os.getcwd(), 'config.yml')
    with open(path, 'r', encoding='UTF-8') as yml:
        config = yaml.load(yml, Loader=yaml.FullLoader)
    return config


def proxy_auth(config: dict) -> ProxyHandler:
    username = config['username']
    password = config['password']
    server = config['server']
    port = config['port']
    proxies = {"http": f"http://{username}:{password}@{server}:{port}"}
    proxy = urllib.request.ProxyHandler(proxies)
    return proxy


def post_to_slack(target_url, proxy, webhook_url, target_date):
    attachments = feed_of_the_day(target_url, proxy, target_date)
    if not attachments:
        text = f'【{target_date}に掲示された記事はありません】'
    else:
        text = f'【{target_date}に掲示された記事一覧】'
    requests.post(
        webhook_url,
        data=json.dumps({
            'text': text,
            'attachments': attachments,
            'link_names': 1}))


def feed_of_the_day(target_url: str, proxy: ProxyHandler, target_date: datetime):
    feed = feedparser.parse(target_url, handlers=[proxy])
    opener = build_opener(proxy)
    install_opener(opener)
    attachments = []

    entries = [entry for entry in feed['entries'] if dig(entry, 'published')]
    for entry in entries:
        rss_date_str = entry['published']
        # 'Wed, 24 Mar 2021 22:33:04 GMT'
        rss_date: datetime = parse(rss_date_str).\
            astimezone(timezone(timedelta(hours=9), 'JST'))

        if target_date.date() == rss_date.date():
            # RSSのpublishedの日付が対象日付であれば
            attachments += [{
                'title': entry['title'],
                'title_link': entry['link'],
                # 'text': text_of_article(entry['link'])
            }]
    return attachments


def text_of_article(url):
    html = urllib.request.urlopen(url)
    soup = BeautifulSoup(html, 'html.parser')
    soup.head.decompose()
    soup.b.decompose()
    text = ''
    for t in soup.find_all(text=True):
        if t.strip():
            text += t
    return text


def yesterday(tz: str = 'JST') -> datetime:
    """ 現在日付から見て昨日の日付をdatetimeで返す(JST) """
    tzone = timezone(timedelta(hours=+9), tz)
    return datetime.now(tz=tzone) + timedelta(days=-1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="""
          (1) サーバーにプロキシを通してRSSを取得
          (2) デフォルトでスクリプト実行時の前日に公開された記事のタイトル・リンク・本文をSlackに投稿 (Incoming WebHooksを利用)
        """
    )
    parser.add_argument('--from-date', required=False, default=None, help='RSS取得したい対象日時(from) yyyy-mm-dd')
    parser.add_argument('--to-date', required=False, default=None, help='RSS取得したい対象日時(to) yyyy-mm-dd')
    parsed_args = parser.parse_args()
    if parsed_args.from_date:
        parsed_args.from_date = datetime.strptime(parsed_args.from_date, '%Y-%m-%d')

    main(parsed_args)
