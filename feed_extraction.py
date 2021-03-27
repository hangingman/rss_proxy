#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import json
import os
import urllib
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.request import build_opener, install_opener, ProxyHandler

import feedparser
import requests
import yaml
from bs4 import BeautifulSoup
from dateutil.parser import parse
from dict_digger import dig


def main(args: argparse.Namespace):
    config: dict = load_config()
    target_url: str = config['target_url']
    webhook_url: str = config['webhook_url']
    proxy: ProxyHandler = proxy_auth(config)

    # 日付指定(from)の設定
    target_date_from = yesterday()
    if args.from_date:
        target_date_from = args.from_date

    post_to_slack(target_url, proxy, webhook_url, target_date_from, args.to_date)


def load_config(path: Optional[str] = None) -> dict:
    if path is None:
        src_dir: str = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(src_dir, 'config.yml')
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


def post_to_slack(target_url: str,
                  proxy: ProxyHandler,
                  webhook_url: str, target_date_from: datetime, target_date_to: datetime):

    attachments = make_attachments(target_url, proxy, target_date_from, target_date_to)
    dt_fmt = '%Y年%m月%d日 %H:%M:%S'
    text = f"【{target_date_from.strftime(dt_fmt)}〜{target_date_to.strftime(dt_fmt)}】"
    if attachments:
        for a in attachments:
            requests.post(
                webhook_url,
                data=json.dumps({
                    'text': text,
                    'attachments': [a],
                    'link_names': 1
                })
            )


def make_attachments(target_url: str, proxy: ProxyHandler, target_date_from: datetime, target_date_to: datetime):
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

        if target_date_from <= rss_date <= target_date_to:
            # RSSのpublishedの日付が対象日付であれば
            attachments += [{
                'title': entry['title'],
                'title_link': entry['link'],
            }]
            # detailに入っている記事もパースする
            attachments += detail_to_articles(dig(entry, 'summary_detail', 'value'))

    # リンク先に重複があれば削除しておく。
    # リンク先のみのリストを作っておき、すでにattachmentsに追加していれば返却時のattachmentsには追加しない。
    title_link_list = [elem['title_link'] for elem in attachments]
    attachments = [elem for i, elem in enumerate(attachments) if elem['title_link'] not in title_link_list[0:i]]
    return attachments


def detail_to_articles(html: str, ignore_words=None):
    """ RSSの<description/> tagから記事をパースする, その際に無視したい記事はignore_wordsで指定できる """
    if ignore_words is None:
        ignore_words = ['Google ニュースですべての記事を見る']
    soup = BeautifulSoup(html, 'html.parser')
    return [{'title': atag.text, 'title_link': atag.attrs['href']}
            for atag in soup.find_all(name="a") if atag.text not in ignore_words]


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
    tz = timezone(timedelta(hours=9), 'JST')
    parser.add_argument('--from-date', required=False, default=None, help='RSS取得したい対象日時(from) yyyy/MM/dd HH:mm:ss')
    parser.add_argument('--to-date', required=False, default=datetime.now(tz=tz), help='RSS取得したい対象日時(to) yyyy/MM/dd HH:mm:ss')
    parsed_args = parser.parse_args()
    if parsed_args.from_date:
        parsed_args.from_date = parse(parsed_args.from_date.__str__()).astimezone(tz)
    if parsed_args.from_date:
        parsed_args.to_date = parse(parsed_args.to_date.__str__()).astimezone(tz)

    main(parsed_args)
