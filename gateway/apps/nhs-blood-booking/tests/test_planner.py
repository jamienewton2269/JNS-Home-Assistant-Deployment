import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from planner import Interval, Slot, candidates, date_time

TZ = ZoneInfo('Europe/London')
D = datetime(2026, 11, 3, 9, 0, tzinfo=TZ)

def slot(name, start, minutes=10, clinic='Churchtown Clinic'):
    return Slot(name, clinic, Interval(D + timedelta(minutes=start), D + timedelta(minutes=start+minutes)))

class PlanTests(unittest.TestCase):
    def test_unavailable_calendar_fails_closed(self):
        with self.assertRaises(ValueError):
            candidates([slot('s1', 0)], 'both', {'me': []})

    def test_single_booking_avoids_padded_diary(self):
        event = Interval(D - timedelta(minutes=5), D + timedelta(minutes=5))
        self.assertEqual(candidates([slot('s1', 20)], 'me', {'me':[event]}, before=20), [])
        self.assertEqual(len(candidates([slot('s1', 30)], 'me', {'me':[event]}, before=20)), 1)

    def test_two_consecutive_same_clinic_both_orders(self):
        options = candidates([slot('a', 0), slot('b', 10)], 'both', {'me':[], 'jane':[]})
        self.assertEqual(len(options), 2)
        self.assertEqual([x['person'] for x in options[0]['slots']], ['me', 'jane'])

    def test_shared_trip_checks_both_calendars(self):
        busy = {'me': [], 'jane': [Interval(D + timedelta(minutes=8), D + timedelta(minutes=9))]}
        self.assertEqual(candidates([slot('a', 0), slot('b', 10)], 'both', busy), [])

    def test_nonconsecutive_pairs_rejected(self):
        self.assertEqual(candidates([slot('a',0), slot('c',20)], 'both', {'me':[], 'jane':[]}), [])

    def test_ambiguous_time_rejected(self):
        with self.assertRaises(ValueError):
            date_time('2026-11-03T09:00:00')

    def test_overlap_rejected(self):
        self.assertEqual(candidates([slot('a',0,15),slot('b',10)], 'both', {'me':[], 'jane':[]}), [])

if __name__ == '__main__':
    unittest.main()
