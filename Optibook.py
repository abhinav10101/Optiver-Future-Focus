"""
Optibook FF2026 — Market-Making Core (PENNY-THE-MARKET)
=======================================================
Same inventory-skewed MM as the standalone core, with one change to quoting:
instead of always resting at r +/- half, we PENNY THE MARKET. Compute the
ideal bid/ask from the reservation price and (vol-aware) half-spread, then if
the public spread is wide, join/undercut the best quote by a tick -- clamped so
we never quote past our own ideal (never pay more than ideal_bid or sell cheaper
than ideal_ask). The vol term still widens quotes in volatile names; penny only
tightens toward the touch when the book is wider than that. All safety behavior
(inventory gating, requote-on-change, reconnect clear) is unchanged.
"""

import time
import math
import datetime
from collections import deque, defaultdict

from optibook.synchronous_client import Exchange

# ---------------- config ----------------
INSTRUMENTS = ["AMZN", "JPM", "XOM"]

TICK = 0.10
POS_LIMIT = 100
SOFT_LIMIT = 70
MSG_BUDGET = 15

QUOTE_SIZE = 40
BASE_HALF = 0.12
MIN_HALF = 0.05
GAMMA = 0.02
VOL_WINDOW = 60
VOL_MULT = 1.5
REQUOTE_TICKS = 1
LOOP_SLEEP = 0.10
LOG = True


class RateLimiter:
    def __init__(self, budget=MSG_BUDGET):
        self.budget, self.t = budget, deque()
    def can(self, n=1):
        now = time.time()
        while self.t and now - self.t[0] > 1.0:
            self.t.popleft()
        return len(self.t) + n <= self.budget
    def mark(self, n=1):
        now = time.time()
        for _ in range(n):
            self.t.append(now)


def round_tick(p):
    return round(round(p / TICK) * TICK, 2)


class MarketMaker:
    def __init__(self):
        self.e = Exchange()
        self.e.connect()
        self.rl = RateLimiter()
        self.books = {}
        self.pos = {}
        self.mid_hist = {i: deque(maxlen=VOL_WINDOW) for i in INSTRUMENTS}
        self.my_bid = {i: None for i in INSTRUMENTS}
        self.my_ask = {i: None for i in INSTRUMENTS}

    # ---- data ----
    def refresh(self):
        self.pos = self.e.get_positions()
        for i in INSTRUMENTS:
            self.books[i] = self.e.get_last_price_book(i)

    def mid(self, i):
        b = self.books.get(i)
        if b and b.bids and b.asks:
            return 0.5 * (b.bids[0].price + b.asks[0].price)
        return None

    def sigma(self, i):
        h = self.mid_hist[i]
        if len(h) < 10:
            return 0.0
        m = sum(h) / len(h)
        var = sum((x - m) ** 2 for x in h) / len(h)
        return math.sqrt(var)

    # ---- connection management ----
    def ensure_connected(self):
        try:
            if self.e.is_connected():
                return True
        except Exception:
            pass
        self.my_bid = {i: None for i in INSTRUMENTS}
        self.my_ask = {i: None for i in INSTRUMENTS}
        backoff = 0.5
        while True:
            try:
                print("DISCONNECTED — attempting reconnect...")
                self.e.connect()
                if self.e.is_connected():
                    self.rl = RateLimiter()
                    for inst in INSTRUMENTS:
                        try:
                            self.e.delete_orders(inst)
                        except Exception:
                            pass
                    print("RECONNECTED. State re-synced, quotes cleared.")
                    return True
            except Exception as ex:
                print("reconnect failed:", ex)
            time.sleep(backoff)
            backoff = min(backoff * 2, 5.0)

    # ---- order management ----
    def cancel_side(self, inst, side):
        rec = self.my_bid[inst] if side == "bid" else self.my_ask[inst]
        if rec is None:
            return
        oid, _ = rec
        if self.rl.can(1):
            self.e.delete_order(inst, order_id=oid)
            self.rl.mark(1)
        if side == "bid":
            self.my_bid[inst] = None
        else:
            self.my_ask[inst] = None

    def post(self, inst, side, price, size):
        if not self.rl.can(1):
            return
        resp = self.e.insert_order(inst, price=price, volume=size,
                                   side=side, order_type="limit")
        self.rl.mark(1)
        oid = getattr(resp, "order_id", None)
        if oid is not None:
            if side == "bid":
                self.my_bid[inst] = (oid, price)
            else:
                self.my_ask[inst] = (oid, price)
            if LOG:
                print(f"  POST {side.upper():4} {inst:5} {size}@{price:.2f}")

    def needs_requote(self, inst, side, target_px):
        rec = self.my_bid[inst] if side == "bid" else self.my_ask[inst]
        if rec is None:
            return True
        _, cur_px = rec
        return abs(cur_px - target_px) >= REQUOTE_TICKS * TICK - 1e-9

    # ---- the quoting logic (PENNY-THE-MARKET) ----
    def quote(self, inst):
        mid = self.mid(inst)
        if mid is None:
            return
        self.mid_hist[inst].append(mid)

        q = self.pos.get(inst, 0)
        sig = self.sigma(inst)

        # reservation price: skew away from inventory
        r = mid - q * GAMMA * (sig ** 2 + TICK)     # +TICK floor so skew works even at low vol

        half = max(MIN_HALF, BASE_HALF + VOL_MULT * sig + GAMMA * abs(q) * TICK)

        # IDEAL: our worst acceptable prices (vol- and inventory-aware).
        ideal_bid = round_tick(r - half)
        ideal_ask = round_tick(r + half)

        bb = self.books[inst].bids[0].price if self.books[inst].bids else None
        ba = self.books[inst].asks[0].price if self.books[inst].asks else None
        my_bid_px = self.my_bid[inst][1] if self.my_bid[inst] else None
        my_ask_px = self.my_ask[inst][1] if self.my_ask[inst] else None

        # PENNY-THE-MARKET: if the public spread is wide, join/undercut the best
        # quote by a tick, but NEVER quote past our own ideal (don't pay more than
        # ideal_bid or sell cheaper than ideal_ask). Falls back to ideal when the
        # book is already tight. Same logic as the futures module.
        want_bid = ideal_bid
        if bb is not None:
            if my_bid_px == bb:
                want_bid = min(ideal_bid, bb)                  # we're best bid -> hold
            else:
                want_bid = min(ideal_bid, round_tick(bb + TICK))   # undercut by 1 tick
        want_ask = ideal_ask
        if ba is not None:
            if my_ask_px == ba:
                want_ask = max(ideal_ask, ba)                  # we're best ask -> hold
            else:
                want_ask = max(ideal_ask, round_tick(ba - TICK))

        # never quote a crossed/locked market against the real book
        if ba is not None:
            want_bid = min(want_bid, round_tick(ba - TICK))
        if bb is not None:
            want_ask = max(want_ask, round_tick(bb + TICK))

        # inventory gating: near the cap, quote only the reducing side
        quote_bid = q < SOFT_LIMIT
        quote_ask = q > -SOFT_LIMIT

        # size also respects the hard cap worst-case
        bid_sz = min(QUOTE_SIZE, POS_LIMIT - q)
        ask_sz = min(QUOTE_SIZE, POS_LIMIT + q)

        # ---- bid side ----
        if quote_bid and bid_sz > 0:
            if self.needs_requote(inst, "bid", want_bid):
                have = self.my_bid[inst] is not None
                need = 2 if have else 1
                if self.rl.can(need):
                    self.cancel_side(inst, "bid")
                    self.post(inst, "bid", want_bid, bid_sz)
        else:
            if self.my_bid[inst] is not None and self.rl.can(1):
                self.cancel_side(inst, "bid")

        # ---- ask side ----
        if quote_ask and ask_sz > 0:
            if self.needs_requote(inst, "ask", want_ask):
                have = self.my_ask[inst] is not None
                need = 2 if have else 1
                if self.rl.can(need):
                    self.cancel_side(inst, "ask")
                    self.post(inst, "ask", want_ask, ask_sz)
        else:
            if self.my_ask[inst] is not None and self.rl.can(1):
                self.cancel_side(inst, "ask")

    def run(self):
        print(f"MM core (PENNY) running on {INSTRUMENTS}. "
              f"BASE_HALF={BASE_HALF} GAMMA={GAMMA} SIZE={QUOTE_SIZE}")
        last_log = 0
        while True:
            try:
                if not self.ensure_connected():
                    continue
                self.refresh()
                for inst in INSTRUMENTS:
                    self.quote(inst)

                if LOG and time.time() - last_log > 5:
                    nz = {k: v for k, v in self.pos.items() if v}
                    print(f"pos={nz} pnl={self.e.get_pnl():.1f}")
                    last_log = time.time()

                time.sleep(LOOP_SLEEP)
            except KeyboardInterrupt:
                for inst in INSTRUMENTS:
                    try:
                        self.e.delete_orders(inst)
                    except Exception:
                        pass
                print("stopped, quotes pulled.")
                break
            except Exception as ex:
                print("ERROR:", ex)
                time.sleep(0.2)


if __name__ == "__main__":
    MarketMaker().run()
