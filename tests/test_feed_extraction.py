import os
import pathlib

from feed_extraction import exec_request_slack, load_config, title_contains_ignore_words, url_contains_ignore_domains


def test_load_config():
    cwd: pathlib.Path = pathlib.Path(os.path.abspath(__file__))
    tests_dir: str = os.path.dirname(cwd)
    path: str = os.path.join(tests_dir, 'test_config.yml')
    config: dict = load_config(path)

    assert ["Google ニュースですべての記事を見る"] == config['ignore_words']
    assert [
      "f1-gate.com",
      "jp.motorsport.com",
      "nikkansports.com",
      "www.nikkansports.com",
      "hochi.news",
      "news.golfdigest.co.jp",
    ], config['ignore_domains']

def test_title_contains_ignore_words():
    ignore_words = ["ニッカンスポーツ", "F1"]
    assert title_contains_ignore_words('古賀さん次男玄暉が優勝 悲しみ耐え「何としても」 - ニッカンスポーツ', ignore_words) == True
    assert title_contains_ignore_words('レッドブル・ホンダF1のマックス・フェルスタッペン、ポジションを返さなければ勝っていた？ / F1バーレーンGP決勝 - F1-Gate.com', ignore_words) == True
    assert title_contains_ignore_words('松本人志“ネットニュースの写真”に問題提起「悪意に満ちたやつある」（オリコン） - Yahoo!ニュース - Yahoo!ニュース', ignore_words) == False
    assert title_contains_ignore_words('未開封マリオに7300万円 ゲームソフト最高落札額 米で競売 - 毎日新聞 - 毎日新聞', ignore_words) == False

def test_url_contains_ignore_domains():
    ignore_domains = ["f1-gate.com", "www.nikkansports.com"]
    assert url_contains_ignore_domains('https://f1-gate.com/verstappen/f1_61457.html', ignore_domains) == True
    assert url_contains_ignore_domains('https://www.nikkansports.com/baseball/news/202104040000263.html', ignore_domains) == True

def test_exec_request_slack(requests_mock):
    dummy_webhook_url='http://dummy.example.com/path'
    requests_mock.post(dummy_webhook_url, text='data')

    exec_request_slack(
        ignore_domains=[],
        ignore_words=[],
        posts=[{
            'title': 'aaa', 'title_link': 'http://dummy.example.com/path'}
        ],
        fallback_text='unit test',
        webhook_url=dummy_webhook_url
    )
