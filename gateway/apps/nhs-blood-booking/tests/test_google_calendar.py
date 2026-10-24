import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

from calendars import FREEBUSY_SCOPE, fetch_calendar, parse_freebusy


class FreeBusyTests(unittest.TestCase):
    def setUp(self):
        self.ids = ['primary', 'shared-calendar@example.com']
        self.start = datetime(2026, 11, 3, 9, tzinfo=timezone.utc)
        self.end = self.start + timedelta(hours=4)

    def test_multiple_calendars_aggregate(self):
        result = {'calendars': {
            'primary': {'busy': [{'start':'2026-11-03T09:00:00Z','end':'2026-11-03T09:30:00Z'}]},
            'shared-calendar@example.com': {'busy': [{'start':'2026-11-03T10:00:00+00:00','end':'2026-11-03T10:30:00+00:00'}]},
        }}
        self.assertEqual(len(parse_freebusy(result, self.ids)), 2)

    def test_calendar_not_shared_fails_closed(self):
        with self.assertRaises(RuntimeError):
            parse_freebusy({'calendars': {'primary': {'busy':[]}}}, self.ids)

    def test_google_calendar_error_fails_closed(self):
        with self.assertRaises(RuntimeError):
            parse_freebusy({'calendars': {'primary': {'busy': []}, self.ids[1]: {'errors': [{'reason':'notFound'}]}}}, self.ids)

    def test_malformed_period_fails_closed(self):
        with self.assertRaises(RuntimeError):
            parse_freebusy({'calendars': {'primary': {'busy': [{'start':'bad','end':'also-bad'}]}, self.ids[1]: {'busy':[]}}}, self.ids)

    @patch('calendars.requests.post')
    @patch('calendars.Credentials.from_authorized_user_file')
    @patch('calendars._calendar_ids')
    @patch('calendars._secret_path')
    def test_google_request_reads_only_freebusy(self, secret, ids, authorized_user, post):
        secret.return_value = '/secret/token.json'
        ids.return_value = self.ids
        credentials = MagicMock()
        credentials.valid = True
        credentials.scopes = [FREEBUSY_SCOPE]
        credentials.token = 'mock-secret'
        authorized_user.return_value = credentials
        response = MagicMock(status_code=200)
        response.json.return_value = {'calendars': {k: {'busy': []} for k in self.ids}}
        post.return_value = response
        self.assertEqual(fetch_calendar('me', self.start, self.end), [])
        kwargs = post.call_args.kwargs
        self.assertEqual([item['id'] for item in kwargs['json']['items']], self.ids)
        self.assertTrue(kwargs['json']['timeMin'].endswith('+00:00'))
        self.assertEqual(kwargs['json']['timeZone'], 'Europe/London')
        self.assertEqual(kwargs['headers']['Authorization'], 'Bearer mock-secret')
        self.assertFalse(kwargs['allow_redirects'])
        self.assertNotIn('fields', kwargs['json'])
        authorized_user.assert_called_once_with('/secret/token.json', scopes=[FREEBUSY_SCOPE])

    @patch('calendars.requests.post')
    @patch('calendars.Credentials.from_authorized_user_file')
    @patch('calendars._calendar_ids')
    @patch('calendars._secret_path')
    def test_provider_failure_masks_secrets(self, secret, ids, authorized_user, post):
        ids.return_value = ['primary']
        authorized_user.return_value = MagicMock(valid=True, token='hidden', scopes=[FREEBUSY_SCOPE])
        post.side_effect = RuntimeError('Secret access token: abcdef')
        with self.assertRaisesRegex(RuntimeError, 'free/busy check failed for me') as error:
            fetch_calendar('me', self.start, self.end)
        self.assertNotIn('abcdef', str(error.exception))


if __name__ == '__main__':
    unittest.main()
