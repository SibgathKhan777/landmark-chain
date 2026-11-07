import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from checkpoint import Checkpoint  # noqa: E402
from store import DAY, LandmarkStore  # noqa: E402

NOW = 1_800_000_000.0
P, C, H = "411001", "kothrud", "house-7"
BLUE_HI = "मंदिर के पीछे नीला गेट"
BLUE_MR = "देवळाच्या मागे निळे गेट"
RED_HI = "मंदिर के पीछे लाल गेट"


def make_store(test, *args, **kwargs):
    s = LandmarkStore(*args, **kwargs)
    test.addCleanup(s.close)
    return s


def route(s, now=NOW, house=H, pin=P, cluster=C):
    return s.route(pin, cluster, house, now=now)


class TestMerging(unittest.TestCase):
    def setUp(self):
        self.s = make_store(self)

    def test_hindi_and_marathi_descriptions_merge_into_one_step(self):
        self.s.add_description(P, C, H, "cust-a", BLUE_HI, "hi-IN", NOW)
        self.s.add_description(P, C, H, "cust-b", BLUE_MR, "mr-IN", NOW)
        r = route(self.s)
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0].support, 2.0)
        self.assertEqual(r[0].state, "consensus")

    def test_single_customer_is_provisional(self):
        self.s.add_description(P, C, H, "cust-a", BLUE_HI, now=NOW)
        r = route(self.s)
        self.assertEqual((r[0].state, r[0].support), ("provisional", 1.0))
        self.assertAlmostEqual(r[0].confidence, 0.6, places=3)

    def test_resubmission_replaces_instead_of_double_counting(self):
        self.s.add_description(P, C, H, "cust-a", BLUE_HI, now=NOW)
        self.s.add_description(P, C, H, "cust-a", BLUE_HI, now=NOW + 10)
        self.assertEqual(route(self.s)[0].support, 1.0)
        self.s.add_description(P, C, H, "cust-a", RED_HI, now=NOW + 20)   # customer corrects themselves
        r = route(self.s)
        self.assertEqual([x.slots["colour"] for x in r], [["RED"]])

    def test_partial_description_supports_the_unique_full_landmark(self):
        self.s.add_description(P, C, H, "cust-a", BLUE_HI, now=NOW)
        keys = self.s.add_description(P, C, H, "cust-b", "नीला गेट", now=NOW)
        r = route(self.s)
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0].support, 1.5)
        self.assertEqual(keys, [r[0].key])

    def test_ambiguous_partial_does_not_inflate_either_candidate(self):
        self.s.add_description(P, C, H, "cust-a", "मंदिर के पीछे नीला गेट, फिर मस्जिद के पीछे नीला गेट", now=NOW)
        self.s.add_description(P, C, H, "cust-b", "नीला गेट", now=NOW)
        support = sorted(x.support for x in route(self.s))
        self.assertEqual(support, [1.0, 1.0, 1.0])       # the partial became its own provisional step

    def test_order_comes_from_pairwise_precedence_across_partial_chains(self):
        self.s.add_description(P, C, H, "c1", "मंदिर के पीछे, फिर नीला गेट", now=NOW)
        self.s.add_description(P, C, H, "c2", "नीला गेट, फिर हरा मकान", now=NOW)
        r = route(self.s)
        self.assertEqual([x.slots.get("anchor") or x.slots.get("colour") for x in r],
                         [["TEMPLE"], ["BLUE"], ["GREEN"]])

    def test_many_votes_for_one_pair_do_not_distort_the_rest_of_the_order(self):
        """Regression: three 'temple, gate' votes must not push the gate below a house that follows it."""
        for i in range(3):
            self.s.add_description(P, C, H, f"t{i}", "मंदिर के पीछे, फिर नीला गेट", now=NOW)
        self.s.add_description(P, C, H, "g", "नीला गेट, फिर हरा मकान", now=NOW)
        r = route(self.s)
        self.assertEqual([x.slots.get("anchor") or x.slots.get("colour") for x in r],
                         [["TEMPLE"], ["BLUE"], ["GREEN"]])

    def test_conflicting_orders_still_produce_a_complete_route(self):
        self.s.add_description(P, C, H, "a", "मंदिर के पीछे, फिर नीला गेट", now=NOW)
        self.s.add_description(P, C, H, "b", "नीला गेट, फिर मंदिर के पीछे", now=NOW)
        self.assertEqual(len(route(self.s)), 2)

    def test_empty_description_stores_nothing(self):
        self.assertEqual(self.s.add_description(P, C, H, "cust-a", "ठीक है भाई", now=NOW), [])
        self.assertEqual(route(self.s), [])

    def test_pincode_and_cluster_are_isolated(self):
        self.s.add_description(P, C, H, "a", BLUE_HI, now=NOW)
        self.s.add_description(P, "other-cluster", H, "b", BLUE_HI, now=NOW)
        self.s.add_description("411002", C, H, "c", BLUE_HI, now=NOW)
        self.assertEqual(route(self.s)[0].support, 1.0)
        n = self.s.db.execute("SELECT COUNT(*) FROM landmarks").fetchone()[0]
        self.assertEqual(n, 3)


class TestContested(unittest.TestCase):
    def test_majority_wins_and_loser_is_listed(self):
        s = make_store(self)
        for i in range(3):
            s.add_description(P, C, H, f"blue{i}", BLUE_HI, now=NOW)
        s.add_description(P, C, H, "red", RED_HI, now=NOW)
        r = route(s)
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0].slots["colour"], ["BLUE"])
        self.assertFalse(r[0].contested)
        self.assertEqual(len(r[0].alternatives), 1)

    def test_even_split_is_flagged_contested(self):
        s = make_store(self)
        for i in range(2):
            s.add_description(P, C, H, f"blue{i}", BLUE_HI, now=NOW)
            s.add_description(P, C, H, f"red{i}", RED_HI, now=NOW)
        r = route(s)
        self.assertEqual(len(r), 1)
        self.assertTrue(r[0].contested)

    def test_rider_evidence_can_overturn_the_majority(self):
        s = make_store(self)
        ids = {}
        for i in range(3):
            s.add_description(P, C, H, f"blue{i}", BLUE_HI, now=NOW)
        s.add_description(P, C, H, "red", RED_HI, now=NOW)
        blue = route(s)[0].landmark_id
        red = [r["id"] for r in s.db.execute("SELECT id FROM landmarks WHERE key LIKE '%C=RED%'")][0]
        for d in range(4):                                  # riders find no blue gate, find the red one
            s.record_result(blue, "NOT_FOUND", f"d{d}", NOW + 1)
            s.record_result(red, "CONFIRMED", f"d{d}", NOW + 1)
        self.assertEqual(route(s, NOW + 2)[0].slots["colour"], ["RED"])


class TestConfidence(unittest.TestCase):
    def setUp(self):
        self.s = make_store(self)
        self.s.add_description(P, C, H, "a", BLUE_HI, now=NOW)
        self.lid = route(self.s)[0].landmark_id

    def conf(self, now=NOW):
        return self.s.confidence(self.lid, now)[0]

    def test_confirmations_raise_confidence(self):
        before = self.conf()
        for d in range(3):
            self.s.record_result(self.lid, "CONFIRMED", f"d{d}", NOW)
        self.assertAlmostEqual(self.conf(), 4.5 / 5.5, places=3)
        self.assertGreater(self.conf(), before)

    def test_explicit_not_found_lowers_it_and_drops_the_step(self):
        for d in range(3):
            self.s.record_result(self.lid, "NOT_FOUND", f"d{d}", NOW)
        self.assertLess(self.conf(), 0.45)
        self.assertEqual(route(self.s), [])

    def test_voice_failure_never_counts_against_a_landmark(self):
        before = self.conf()
        self.assertFalse(self.s.record_result(self.lid, "UNCONFIRMED", "d1", NOW))
        self.assertEqual(self.conf(), before)

    def test_checkpoint_objects_feed_the_store(self):
        ok = Checkpoint(BLUE_HI)
        ok.hear(BLUE_HI)
        self.assertTrue(self.s.record_checkpoint(self.lid, ok, "d1", NOW))
        skipped = Checkpoint(BLUE_HI)
        for _ in range(3):
            skipped.hear("")
        skipped.tap(None)
        self.assertFalse(self.s.record_checkpoint(self.lid, skipped, "d2", NOW))
        no = Checkpoint(BLUE_HI)
        no.hear("मंदिर के पीछे")
        no.hear("नहीं")
        self.assertTrue(self.s.record_checkpoint(self.lid, no, "d3", NOW))
        n = self.s.db.execute("SELECT COUNT(*) FROM events WHERE kind IN ('confirm','fail')").fetchone()[0]
        self.assertEqual(n, 2)

    def test_repeating_the_same_delivery_does_not_double_count(self):
        self.s.record_result(self.lid, "CONFIRMED", "d1", NOW)
        c1 = self.conf()
        self.s.record_result(self.lid, "CONFIRMED", "d1", NOW)
        self.assertEqual(self.conf(), c1)


class TestDecay(unittest.TestCase):
    def setUp(self):
        self.s = make_store(self)
        self.s.add_description(P, C, H, "a", BLUE_HI, now=NOW)
        self.lid = route(self.s)[0].landmark_id

    def test_evidence_halves_every_half_life(self):
        self.assertAlmostEqual(self.s.confidence(self.lid, NOW)[0], 1.5 / 2.5, places=4)
        self.assertAlmostEqual(self.s.confidence(self.lid, NOW + 90 * DAY)[0], 1.25 / 2.25, places=4)
        self.assertAlmostEqual(self.s.confidence(self.lid, NOW + 900 * DAY)[0], 0.5, places=2)

    def test_old_landmarks_are_marked_stale_and_fresh_ones_are_not(self):
        self.assertEqual(route(self.s, NOW + 10 * DAY)[0].state, "provisional")
        self.assertEqual(route(self.s, NOW + 200 * DAY)[0].state, "stale")

    def test_recent_failure_outweighs_old_confirmations(self):
        for d in range(3):
            self.s.record_result(self.lid, "CONFIRMED", f"d{d}", NOW)
        fresh = NOW + 400 * DAY
        before = self.s.confidence(self.lid, fresh)[0]
        self.s.record_result(self.lid, "NOT_FOUND", "late", fresh)
        after = self.s.confidence(self.lid, fresh)[0]
        self.assertLess(after, before)
        self.assertLess(after, 0.5)

    def test_a_fresh_confirmation_revives_a_stale_landmark(self):
        later = NOW + 300 * DAY
        self.assertEqual(route(self.s, later)[0].state, "stale")
        self.s.record_result(self.lid, "CONFIRMED", "d9", later)
        self.assertNotEqual(route(self.s, later)[0].state, "stale")


class TestPrivacyAndHousekeeping(unittest.TestCase):
    def test_forget_customer_erases_their_evidence(self):
        s = make_store(self)
        s.add_description(P, C, H, "customer-123", BLUE_HI, now=NOW)
        s.add_description(P, C, H, "customer-456", BLUE_HI, now=NOW)
        self.assertEqual(route(s)[0].support, 2.0)
        self.assertEqual(s.forget_customer("customer-123"), 1)
        self.assertEqual(route(s)[0].support, 1.0)
        self.assertEqual(s.forget_customer("customer-123"), 0)

    def test_raw_customer_ids_are_never_stored(self):
        s = make_store(self)
        s.add_description(P, C, H, "customer-123", BLUE_HI, now=NOW)
        dump = "\n".join(s.db.iterdump())
        self.assertNotIn("customer-123", dump)

    def test_prune_removes_old_events_and_orphan_landmarks(self):
        s = make_store(self)
        s.add_description(P, C, H, "a", BLUE_HI, now=NOW)
        s.forget_customer("a")                      # nothing refers to the landmark any more
        self.assertEqual(s.db.execute("SELECT COUNT(*) FROM landmarks").fetchone()[0], 1)
        events, lms = s.prune(NOW)
        self.assertEqual(lms, 1)

    def test_prune_keeps_recent_evidence(self):
        s = make_store(self)
        s.add_description(P, C, H, "a", BLUE_HI, now=NOW)
        self.assertEqual(s.prune(NOW + 10 * DAY), (0, 0))
        events, _ = s.prune(NOW + 9 * 90 * DAY)
        self.assertEqual(events, 1)

    def test_data_survives_reopening_the_database(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "lm.db")
            s1 = LandmarkStore(path)
            s1.add_description(P, C, H, "a", BLUE_HI, now=NOW)
            s1.add_description(P, C, H, "b", BLUE_MR, now=NOW)
            s1.close()
            s2 = LandmarkStore(path)
            self.addCleanup(s2.close)
            r = route(s2)
            self.assertEqual((len(r), r[0].support, r[0].state), (1, 2.0, "consensus"))

    def test_delivery_rate(self):
        s = make_store(self)
        self.assertIsNone(s.delivery_rate(P, C, H))
        for i, ok in enumerate([True, True, False, True]):
            s.record_delivery(P, C, H, f"d{i}", ok, NOW)
        self.assertEqual(s.delivery_rate(P, C, H), 0.75)



class TestContextManager(unittest.TestCase):
    def test_store_closes_when_used_as_a_context_manager(self):
        import sqlite3
        with LandmarkStore() as s:
            s.add_description(P, C, H, "a", BLUE_HI, now=NOW)
        with self.assertRaises(sqlite3.ProgrammingError):
            s.db.execute("SELECT 1")


class TestPrivacyHardening(unittest.TestCase):
    """Found in review: the pseudonym salt was a fixed public string and raw transcripts were stored."""

    def dump(self, s):
        return "\n".join(s.db.iterdump())

    def test_each_database_has_its_own_random_salt(self):
        a, b = make_store(self), make_store(self)
        a.add_description(P, C, H, "customer-1", BLUE_HI, now=NOW)
        b.add_description(P, C, H, "customer-1", BLUE_HI, now=NOW)
        ha = a.db.execute("SELECT customer FROM observations").fetchone()[0]
        hb = b.db.execute("SELECT customer FROM observations").fetchone()[0]
        self.assertNotEqual(ha, hb)

    def test_salt_survives_reopening_so_erasure_still_works(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "lm.db")
            s1 = LandmarkStore(path)
            s1.add_description(P, C, H, "customer-1", BLUE_HI, now=NOW)
            s1.close()
            s2 = LandmarkStore(path)
            self.addCleanup(s2.close)
            self.assertEqual(s2.forget_customer("customer-1"), 1)

    def test_an_explicit_salt_is_still_honoured(self):
        a, b = make_store(self, salt="x"), make_store(self, salt="x")
        a.add_description(P, C, H, "c", BLUE_HI, now=NOW)
        b.add_description(P, C, H, "c", BLUE_HI, now=NOW)
        self.assertEqual(a.db.execute("SELECT customer FROM observations").fetchone()[0],
                         b.db.execute("SELECT customer FROM observations").fetchone()[0])

    def test_spoken_digits_are_not_stored(self):
        s = make_store(self)
        s.add_description(P, C, H, "a", "मंदिर के पीछे नीला गेट 9876543210, फिर ९८७६ नंबर का हरा मकान", now=NOW)
        dump = self.dump(s)
        for digits in ("9876543210", "९८७६"):
            self.assertNotIn(digits, dump)

    def test_only_recognised_landmark_text_is_kept(self):
        s = make_store(self)
        s.add_description(P, C, H, "a", "मेरा नाम राहुल है, फिर मंदिर के पीछे", now=NOW)
        dump = self.dump(s)
        self.assertNotIn("राहुल", dump)
        self.assertIn("मंदिर के पीछे", dump)


if __name__ == "__main__":
    unittest.main()
