#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import json
import os
import time
import traceback
import urllib
from datetime import datetime, timedelta, timezone
from typing import Optional, List
from urllib.parse import urlparse
from urllib.request import build_opener, install_opener, ProxyHandler

import feedparser
import requests
import yaml
from bs4 import BeautifulSoup
from dateutil.parser import parse
from dict_digger import dig
from peewee import SqliteDatabase, Model, TextField, DateTimeField
from requests import Response

# RSS投稿の管理用db(ソースと同じディレクトリに設置する)
db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'rss_database.db')
db = SqliteDatabase(db_path)

# 連続でSlackに投稿しないために待ち時間を設定する
SLACK_POST_WAIT = 3


class BaseModel(Model):
    class Meta:
        database = db


class Rss(BaseModel):
    """ Slackに投稿済みのURLをここで管理する """
    url = TextField(unique=True)
    title = TextField()
    created_date = DateTimeField(default=datetime.now)


def main(args: argparse.Namespace):
    config: dict = load_config()
    target_urls: List[str] = config['target_urls']
    webhook_url: str = config['webhook_url']
    proxy: ProxyHandler = proxy_auth(config)
    ignore_words: list = config['ignore_words']
    ignore_domains: list = config['ignore_domains']

    db.connect()
    db.create_tables([Rss], safe=True)  # デフォルトで create table if not exists が入っている

    # 日付指定(from)の設定
    target_date_from = yesterday()
    if args.from_date:
        target_date_from = args.from_date

    post_to_slack(target_urls, proxy, webhook_url, target_date_from, args.to_date, ignore_words, ignore_domains)


def load_config(path: Optional[str] = None) -> dict:
    """ config.ymlから設定情報を読み込む """
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


def post_to_slack(target_urls: List[str],
                  proxy: ProxyHandler,
                  webhook_url: str,
                  target_date_from: datetime,
                  target_date_to: datetime,
                  ignore_words: list,
                  ignore_domains: list):
    """ SlackにRSSの内容をpostする """

    posts: List[dict] = make_posts(target_urls, proxy, target_date_from, target_date_to)
    dt_fmt = '%Y年%m月%d日 %H:%M:%S'
    fallback_text: str = f"【{target_date_from.strftime(dt_fmt)}〜{target_date_to.strftime(dt_fmt)}】"
    exec_request_slack(ignore_domains, ignore_words, posts, fallback_text, webhook_url)


def title_contains_ignore_words(title: str, ignore_words: list) -> bool:
    return any((word in title) for word in ignore_words)


def url_contains_ignore_domains(title_link: str, ignore_domains: list) -> bool:
    url = get_redirected_url(title_link)
    return any((urlparse(url).netloc == domain) for domain in ignore_domains)


def exec_request_slack(ignore_domains: list,
                       ignore_words: list,
                       posts: List[dict],
                       fallback_text: str,
                       webhook_url: str):
    """
    POST情報を受け取って実際にSlackにリクエストを実施する
    """
    for post in posts:
        # 無視対象単語を含むのであればskip
        if title_contains_ignore_words(post['title'], ignore_words):
            continue
        # 無視対象ドメインを含むのであればskip
        if url_contains_ignore_domains(post['title_link'], ignore_domains):
            continue
        # slackに投稿済みであればpostしない
        if not Rss.select().where(Rss.url == post['title_link']):
            # デフォルトで3秒待つ
            time.sleep(SLACK_POST_WAIT)
            payload = {'text': fallback_text, 'attachments': [post], 'link_names': 1}
            print(f"slack post: {payload}")
            response: Response = requests.post(
                webhook_url, data=json.dumps(payload)
            )
            if response.status_code == 200:
                Rss(title=post['title'], url=post['title_link']).save()
            print(f"response: {response.status_code}")


def make_posts(target_urls: List[str],
               proxy: ProxyHandler,
               target_date_from: datetime,
               target_date_to: datetime) -> List[dict]:

    # 複数RSSのURLを処理する
    feeds = [feedparser.parse(url, handlers=[proxy]) for url in target_urls]

    opener = build_opener(proxy)
    install_opener(opener)
    posts = []
    entries = []

    for feed in feeds:
        entries.extend([entry for entry in feed['entries'] if dig(entry, 'published')])

    for entry in entries:
        rss_date_str = entry['published']
        # 'Wed, 24 Mar 2021 22:33:04 GMT'
        rss_date: datetime = parse(rss_date_str).astimezone(timezone(timedelta(hours=9), 'JST'))

        # RSSのpublishedの日付が対象日付であれば取得
        if target_date_from <= rss_date <= target_date_to:
            # 短縮リンクは解除して直接リンクに変換
            title_link: str = get_redirected_url(entry['link'])
            posts += [{
                'title': entry['title'],
                'title_link': title_link,
            }]

    # リンク先に重複があれば削除しておく。
    # リンク先のみのリストを作っておき、すでにattachmentsに追加していれば返却時のattachmentsには追加しない。
    title_link_list = [elem['title_link'] for elem in posts]
    posts = [elem for i, elem in enumerate(posts) if elem['title_link'] not in title_link_list[0:i]]
    return posts


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


def get_redirected_url(short_url: str) -> str:
    """ 短縮URLが返す真のURLを取得する """
    try:
        response = requests.head(short_url, allow_redirects=True)
        if not response.url:
            return short_url

        return  response.url
    except:
        formatted_lines: List[str] = traceback.format_exc().splitlines()
        print(formatted_lines)
        return short_url


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="""
          (1) サーバーにプロキシを通してRSSを取得
          (2) デフォルトでスクリプト実行時の前日に公開された記事のタイトル・リンク・本文をSlackに投稿 (Incoming WebHooksを利用)
        """
    )
    tz = timezone(timedelta(hours=9), 'JST')
    parser.add_argument('--from-date', required=False, default=None,
                        help='RSS取得したい対象日時(from) yyyy/MM/dd HH:mm:ss')
    parser.add_argument('--to-date', required=False, default=datetime.now(tz=tz),
                        help='RSS取得したい対象日時(to) yyyy/MM/dd HH:mm:ss')
    parsed_args = parser.parse_args()
    if parsed_args.from_date:
        parsed_args.from_date = parse(parsed_args.from_date.__str__()).astimezone(tz)
    if parsed_args.from_date:
        parsed_args.to_date = parse(parsed_args.to_date.__str__()).astimezone(tz)

    main(parsed_args)
