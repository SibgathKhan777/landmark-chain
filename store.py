"""Per-pincode landmark store (SQLite) with consensus merging, confidence and decay.

Model
  landmark      a language-independent step identity, e.g. TEMPLE+BEHIND+BLUE+GATE, scoped to
                (pincode, cluster). The same house described in Hindi and Marathi maps to the same key.
  observation   one customer's description of one house (latest per customer wins), stored as text and
                an ordered list of landmark ids. Audio is never stored.
  event         evidence about a landmark: customer mentions (weight 0.5 / 0.25 for partial),
                rider confirmations (+1), explicit 'not found' (-1). Weight halves every half_life_days.
  confidence    (1 + decayed positive) / (2 + decayed positive + decayed negative): 0.5 with no evidence,
                drifting back toward 0.5 as evidence ages.
  route         consensus chain for a house: contested alternatives resolved, low-confidence steps dropped,
                order from pairwise precedence across customers.
A voice failure (UNCONFIRMED) never counts against a landmark; only an explicit no or tap does.
"""
import hashlib
import json
import re
import secrets
import sqlite3
import time
from collections import defaultdict
from dataclasses import dataclass, field

from extraction import CRITICAL, SLOTS, split_chain_segments

DAY = 86400.0
ATTRIBUTES = ("colour", "ordinal", "side")

SCHEMA = """
CREATE TABLE IF NOT EXISTS landmarks(
  id INTEGER PRIMARY KEY, pincode TEXT NOT NULL, cluster TEXT NOT NULL, key TEXT NOT NULL,
  slots_json TEXT NOT NULL, display TEXT, created_at REAL, UNIQUE(pincode, cluster, key));
CREATE TABLE IF NOT EXISTS observations(
  id INTEGER PRIMARY KEY, pincode TEXT NOT NULL, cluster TEXT NOT NULL, house_key TEXT NOT NULL,
  customer TEXT NOT NULL, lang TEXT, text TEXT, created_at REAL,
  UNIQUE(pincode, cluster, house_key, customer));
CREATE TABLE IF NOT EXISTS obs_steps(
  obs_id INTEGER NOT NULL, pos INTEGER NOT NULL, landmark_id INTEGER NOT NULL, weight REAL NOT NULL);
CREATE TABLE IF NOT EXISTS events(
  id INTEGER PRIMARY KEY, landmark_id INTEGER NOT NULL, kind TEXT NOT NULL, source TEXT NOT NULL,
  weight REAL NOT NULL, ts REAL NOT NULL, UNIQUE(landmark_id, kind, source));
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS deliveries(
  delivery_id TEXT PRIMARY KEY, pincode TEXT, cluster TEXT, house_key TEXT, delivered INTEGER, ts REAL);
"""


def slot_key(slots):
    return "|".join(f"{s[0].upper()}={'+'.join(sorted(slots[s]))}" for s in SLOTS)


def _load(js):
    return {k: frozenset(v) for k, v in json.loads(js).items()}


def _dump(slots):
    return json.dumps({k: sorted(v) for k, v in slots.items()}, ensure_ascii=False)


def is_subset(small, big):
    return all(small[s] <= big[s] for s in SLOTS)


def contests(a, b):
    """Two steps describe the same place but disagree on colour, lane or side."""
    if any(a[s] != b[s] for s in ("anchor", "relation", "target")):
        return False
    diff = [s for s in CRITICAL if a[s] and b[s] and not (a[s] & b[s])]
    return bool(diff) and all(s in ATTRIBUTES for s in diff)


@dataclass
class RouteStep:
    landmark_id: int
    key: str
    text: str
    slots: dict
    support: float
    confidence: float
    state: str                      # consensus | provisional | stale
    contested: bool = False
    alternatives: list = field(default_factory=list)
    last_event_ts: float = 0.0


class LandmarkStore:
    def __init__(self, path=":memory:", *, half_life_days=90.0, min_support=2.0, min_confidence=0.45,
                 consensus_confidence=0.6, stale_days=180.0, salt=None):
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self.half_life, self.min_support = half_life_days * DAY, min_support
        self.min_confidence, self.consensus_confidence = min_confidence, consensus_confidence
        self.stale = stale_days * DAY
        self.salt = salt if salt is not None else self._persistent_salt()

    def close(self):
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # ---- helpers
    def _persistent_salt(self):
        """A random secret per database, created once. A fixed public salt would let anyone hash every
        possible phone number and reverse the pseudonyms."""
        row = self.db.execute("SELECT value FROM meta WHERE key='salt'").fetchone()
        if row:
            return row["value"]
        value = secrets.token_hex(16)
        self.db.execute("INSERT INTO meta VALUES('salt', ?)", (value,))
        self.db.commit()
        return value

    @staticmethod
    def _scrub(text):
        """Spoken phone numbers, house numbers and ids are personal data: keep the words, drop the digits."""
        return re.sub(r"[0-9\u0966-\u096f]+", "#", text or "")

    def _cust(self, customer_id):
        """Pseudonymise: the raw customer id is never stored."""
        return hashlib.sha256((self.salt + str(customer_id)).encode()).hexdigest()[:16]

    @staticmethod
    def _now(now):
        return time.time() if now is None else now

    def _house_landmarks(self, pincode, cluster, house_key):
        rows = self.db.execute(
            """SELECT DISTINCT l.id, l.key, l.slots_json FROM obs_steps s
               JOIN observations o ON o.id = s.obs_id JOIN landmarks l ON l.id = s.landmark_id
               WHERE o.pincode=? AND o.cluster=? AND o.house_key=?""", (pincode, cluster, house_key)).fetchall()
        return [(r["id"], r["key"], _load(r["slots_json"])) for r in rows]

    def _delete_observation(self, obs_id, source):
        ids = [r["landmark_id"] for r in self.db.execute("SELECT landmark_id FROM obs_steps WHERE obs_id=?", (obs_id,))]
        for lid in ids:
            self.db.execute("DELETE FROM events WHERE landmark_id=? AND kind='mention' AND source=?", (lid, source))
        self.db.execute("DELETE FROM obs_steps WHERE obs_id=?", (obs_id,))
        self.db.execute("DELETE FROM observations WHERE id=?", (obs_id,))

    # ---- writing
    def add_description(self, pincode, cluster, house_key, customer_id, text, lang=None, now=None):
        """Store one customer's spoken description of a house. Returns the landmark keys in order."""
        now, cust = self._now(now), self._cust(customer_id)
        segs = split_chain_segments(text)
        if not segs:
            return []
        source = f"{cust}:{house_key}"
        old = self.db.execute("SELECT id FROM observations WHERE pincode=? AND cluster=? AND house_key=? AND customer=?",
                              (pincode, cluster, house_key, cust)).fetchone()
        if old:
            self._delete_observation(old["id"], source)
        house = self._house_landmarks(pincode, cluster, house_key)

        resolved = {}   # landmark_id -> weight, insertion-ordered
        for seg, slots in segs:
            key = slot_key(slots)
            row = self.db.execute("SELECT id FROM landmarks WHERE pincode=? AND cluster=? AND key=?",
                                  (pincode, cluster, key)).fetchone()
            if row:
                lid, w = row["id"], 1.0
            else:
                cands = [h for h in house if is_subset(slots, h[2])]
                if len(cands) == 1:      # unambiguous partial description of a known landmark
                    lid, w = cands[0][0], 0.5
                else:
                    cur = self.db.execute(
                        "INSERT INTO landmarks(pincode, cluster, key, slots_json, display, created_at) VALUES(?,?,?,?,?,?)",
                        (pincode, cluster, key, _dump(slots), self._scrub(seg), now))
                    lid, w = cur.lastrowid, 1.0
                    house.append((lid, key, slots))
            resolved[lid] = max(resolved.get(lid, 0.0), w)

        cur = self.db.execute("INSERT INTO observations(pincode, cluster, house_key, customer, lang, text, created_at) "
                              "VALUES(?,?,?,?,?,?,?)",
                              (pincode, cluster, house_key, cust, lang, " | ".join(self._scrub(seg) for seg, _ in segs), now))
        for pos, (lid, w) in enumerate(resolved.items()):
            self.db.execute("INSERT INTO obs_steps VALUES(?,?,?,?)", (cur.lastrowid, pos, lid, w))
            self.db.execute("INSERT OR REPLACE INTO events(landmark_id, kind, source, weight, ts) VALUES(?,?,?,?,?)",
                            (lid, "mention", source, 0.5 * w, now))
        self.db.commit()
        keys = {r["id"]: r["key"] for r in self.db.execute("SELECT id, key FROM landmarks")}
        return [keys[lid] for lid in resolved]

    def record_result(self, landmark_id, status, delivery_id, now=None):
        """CONFIRMED adds evidence, NOT_FOUND removes it, anything else (UNCONFIRMED) is ignored."""
        kind = {"CONFIRMED": "confirm", "NOT_FOUND": "fail"}.get(status)
        if kind is None:
            return False
        self.db.execute("INSERT OR REPLACE INTO events(landmark_id, kind, source, weight, ts) VALUES(?,?,?,?,?)",
                        (landmark_id, kind, str(delivery_id), 1.0, self._now(now)))
        self.db.commit()
        return True

    def record_checkpoint(self, landmark_id, checkpoint, delivery_id, now=None):
        return self.record_result(landmark_id, checkpoint.status, delivery_id, now)

    def record_delivery(self, pincode, cluster, house_key, delivery_id, delivered, now=None):
        self.db.execute("INSERT OR REPLACE INTO deliveries VALUES(?,?,?,?,?,?)",
                        (str(delivery_id), pincode, cluster, house_key, int(delivered), self._now(now)))
        self.db.commit()

    def delivery_rate(self, pincode, cluster, house_key):
        r = self.db.execute("SELECT COUNT(*) n, COALESCE(SUM(delivered),0) d FROM deliveries "
                            "WHERE pincode=? AND cluster=? AND house_key=?", (pincode, cluster, house_key)).fetchone()
        return (r["d"] / r["n"]) if r["n"] else None

    def forget_customer(self, customer_id):
        """Erase a customer's observations and mention events. Returns the number of observations removed."""
        cust, n = self._cust(customer_id), 0
        for o in self.db.execute("SELECT id, house_key FROM observations WHERE customer=?", (cust,)).fetchall():
            self._delete_observation(o["id"], f"{cust}:{o['house_key']}")
            n += 1
        self.db.commit()
        return n

    def prune(self, now=None, max_age_half_lives=8):
        """Drop evidence older than 8 half-lives (about 2% weight) and landmarks nothing refers to."""
        now = self._now(now)
        e = self.db.execute("DELETE FROM events WHERE ts < ?", (now - max_age_half_lives * self.half_life,)).rowcount
        l = self.db.execute(
            """DELETE FROM landmarks WHERE id NOT IN (SELECT landmark_id FROM events)
               AND id NOT IN (SELECT landmark_id FROM obs_steps)""").rowcount
        self.db.commit()
        return e, l

    # ---- reading
    def confidence(self, landmark_id, now=None):
        """Returns (confidence, last_event_ts). Prior is 0.5; old evidence fades back toward it."""
        now = self._now(now)
        pos = neg = 0.0
        last = 0.0
        for r in self.db.execute("SELECT kind, weight, ts FROM events WHERE landmark_id=?", (landmark_id,)):
            w = r["weight"] * 0.5 ** (max(now - r["ts"], 0.0) / self.half_life)
            if r["kind"] == "fail":
                neg += w
            else:
                pos += w
            last = max(last, r["ts"])
        return (1 + pos) / (2 + pos + neg), last

    @staticmethod
    def _order(nodes, before, support):
        """Topological sort over majority precedence (a -> b if more customers put a before b).

        Summing pairwise votes is wrong for partial chains: many 'A then B' votes would push B below
        C even when someone said 'B then C' and nobody said the opposite. Ties go to the better
        supported landmark; if the majority graph has a cycle, the rest fall back to net votes.
        """
        edges = {n: set() for n in nodes}
        indeg = {n: 0 for n in nodes}
        for a in nodes:
            for b in nodes:
                if a != b and before[(a, b)] > before[(b, a)]:
                    edges[a].add(b)
                    indeg[b] += 1
        out, ready = [], sorted([n for n in nodes if indeg[n] == 0], key=lambda n: (-support[n], n))
        while ready:
            n = ready.pop(0)
            out.append(n)
            for m in sorted(edges[n]):
                indeg[m] -= 1
                if indeg[m] == 0:
                    ready.append(m)
            ready.sort(key=lambda x: (-support[x], x))
        rest = [n for n in nodes if n not in out]
        rest.sort(key=lambda n: (-sum(before[(n, m)] - before[(m, n)] for m in nodes), -support[n], n))
        return out + rest

    def route(self, pincode, cluster, house_key, now=None):
        """Consensus chain for a house, in order."""
        now = self._now(now)
        obs = self.db.execute("SELECT id, customer FROM observations WHERE pincode=? AND cluster=? AND house_key=?",
                              (pincode, cluster, house_key)).fetchall()
        if not obs:
            return []
        seqs, support = [], defaultdict(float)
        for o in obs:
            steps = self.db.execute("SELECT landmark_id, weight FROM obs_steps WHERE obs_id=? ORDER BY pos",
                                    (o["id"],)).fetchall()
            seqs.append([s["landmark_id"] for s in steps])
            for s in steps:
                support[s["landmark_id"]] += s["weight"]      # one observation per customer, so already distinct
        info = {}
        for lid in support:
            r = self.db.execute("SELECT key, slots_json, display FROM landmarks WHERE id=?", (lid,)).fetchone()
            conf, last = self.confidence(lid, now)
            info[lid] = dict(key=r["key"], slots=_load(r["slots_json"]), text=r["display"], conf=conf, last=last)

        # contested alternatives: pick one per group
        ids, parent = list(info), {}
        def find(x):
            while parent.setdefault(x, x) != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                if contests(info[a]["slots"], info[b]["slots"]):
                    parent[find(a)] = find(b)
        groups = defaultdict(list)
        for x in ids:
            groups[find(x)].append(x)
        rep, chosen = {}, {}
        for members in groups.values():
            members.sort(key=lambda x: (-info[x]["conf"], -support[x], x))
            best = members[0]
            gap_small = len(members) > 1 and info[members[1]]["conf"] >= info[best]["conf"] - 0.1
            chosen[best] = (gap_small, [info[m]["key"] for m in members[1:]])
            for m in members:
                rep[m] = best
        keep = [x for x in chosen if info[x]["conf"] >= self.min_confidence]

        # order: pairwise precedence across customers (losers count as their winner)
        before = defaultdict(int)          # before[(a, b)]: customers who said a comes before b
        for seq in seqs:
            mapped = []
            for x in seq:
                if rep[x] in keep and rep[x] not in mapped:
                    mapped.append(rep[x])
            for i in range(len(mapped)):
                for j in range(i + 1, len(mapped)):
                    before[(mapped[i], mapped[j])] += 1
        keep = self._order(keep, before, support)

        out = []
        for x in keep:
            i = info[x]
            if now - i["last"] > self.stale:
                state = "stale"
            elif support[x] >= self.min_support and i["conf"] >= self.consensus_confidence:
                state = "consensus"
            else:
                state = "provisional"
            out.append(RouteStep(x, i["key"], i["text"], {k: sorted(v) for k, v in i["slots"].items() if v},
                                 support[x], round(i["conf"], 3), state, chosen[x][0], chosen[x][1], i["last"]))
        return out
