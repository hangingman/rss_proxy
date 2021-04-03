import unittest

from feed_extraction import exec_request_slack


class FeedExtractionTestCase(unittest.TestCase):

    def test_exec_request_slack(self):
        exec_request_slack(
            ignore_domains=[],
            ignore_words=[],
            posts=[{
                'title': 'aaa', 'title_link': 'http://dummy.example.com/path'}
            ],
            fallback_text='unit test',
            webhook_url='http://dummy.example.com/path'
        )
        self.assertEqual(True, True)


if __name__ == '__main__':
    unittest.main()
