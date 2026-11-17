"""Deep-dip scale-in bot for cbBTC (agent-fun/bars-replay/v1), v3.

Adapted from the v2 bot of the 15 Nov race for the 17 Nov race
(btc-race-24h-20261117-0603). The dev window (16 Nov 06:03 UTC - 17 Nov
06:03 UTC, 1,440 bars, close $64,461.04 -> $64,775.95, +0.49%) is a flat
range: low $63,874.36, high $65,466.84. Its profit sits in ONE
decline-and-recover episode: the trough near $63,874 recovering about
+2.5% to the $65,467 peak. Everything else in the window is chop too
small to survive the ~26 bps round-trip cost.

What changed vs v2, and why (sweep of 1,200 parameterisations of this
family on THIS window, exact integer simulator):
  * Entry at -170 bps (was -200): the -200 trigger fires late on this
    window; -170 catches the same episode earlier and lets the second
    tranche fill. Neighbourhood -150 to -170 bps all give $10-13.50.
  * Trailing stop arms at +80 bps and trails 90 bps (was +50/60): the
    recovery runs further than v2's tight trail allows.
  * Max hold 300 bars (was 120): the recovery takes ~200+ bars to play
    out; the 120-bar backstop cut it short at $9.84. Holds of 90-300 bars
    all beat v2 ($7.15-13.52: 90 bars $9.07, 120 bars $9.84, 180 bars
    $7.15, 240 bars $8.73, 300 bars $13.52, 600 bars $13.52).
  * Take-profit at +150 bps above the average entry (new): locks the
    peak in instead of trailing back down 90 bps from it. Worth +$3.37
    over the same config without it on this window.
  * Two tranches kept (50% then the rest while the dip is still deep),
    re-arm rule kept (no re-buy until the 60-bar return is above -50 bps).

Long only, at most one position, at most one order per batch, max slippage
50 bps. A full-size round trip costs about 26 bps in fees, slippage and
pool impact.

Dev window, verified with the real bot as a subprocess
(`python3 -P -s main.py`, PYTHONHASHSEED=0, local replay driver, exact
integer port of the kit engine, validated against v1's +$25.16 / 5 RTs /
12 fills exactly): net PnL +$13.52 from 1 round trip, 3 fills, max
drawdown 0.62%, fees $0.81, no rejected orders, two runs byte-identical
(reply log sha256 fec23f012e2def151fea2228363ca944430ada710467b500fecbadb6b334498b).
v2's parameters on this window make only +$5.04 (1 RT, DD 0.29%); the
neighbourhood drop 150-170 bps / take-profit 0-150 bps makes $8.52-13.52
(tp 0 $10.15, tp 100 $8.52, tp 150 $13.52, tp 200 $10.15),
so the gain is broad, not a single tuned point. With fees doubled the
same run nets +$12.71.

Honest caveat: the profit is concentrated in one trade (the single
trough-to-recovery episode, 100% of the net). Across the 1,200-config
sweep, NO configuration achieves a biggest-trade share below 100% with a
positive net on this window -- the window's profit is structurally
concentrated, and the smaller bounces are too small to survive the
round-trip cost. The live race therefore depends on a dip-and-recovery
episode occurring in the race window, as it did in the dev window; the
wider hold and take-profit are the best-measured way to bank it if it
does.

Everything is deterministic: no clock, no network, no randomness, no
files. The only state is the list of closes seen so far and a few numbers
derived from it, so two runs on the same data produce byte-identical
replies.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import makefun_bars

SYMBOL = "CBBTC"

# --- strategy parameters (chosen on the dev window; see the docstring) ---
DROP_BARS = 60            # dip measured against the close 60 bars ago
DROP1_BPS = 170           # first tranche: buy when the close is >= 170 bps below it
SIZE1_BPS = 5000          # first tranche spends 50% of the cash
DROP2_BPS = 170           # second tranche: buy the rest while the dip is still >= 170 bps
ACTIVATE_BPS = 80         # arm the trailing stop once +80 bps above the entry
TRAIL_BPS = 90            # sell when the close falls 90 bps below the peak since entry
TAKE_PROFIT_BPS = 150     # sell once the close is +150 bps above the average entry
MAX_HOLD = 300            # backstop: sell after 300 bars in the trade (5 hours)
MAX_SLIP_BPS = 50         # max slippage on every order
REARM_BPS = -50           # re-arm buying only once the 60-bar return is above -50 bps

# --- per-run state ---
_closes = []
_entry_px = None          # average entry price (raw price units) from cost/qty
_peak = None              # highest close since entry
_hold_bars = 0
_armed = True
_trail_on = False
_tranche2_done = False


def _entry_price(state):
    """Average entry price from the position's cost and qty (raw price units)."""
    pos = state.positions.get(SYMBOL)
    if pos is None or pos.qty == 0:
        return None
    # value(qty, price) = qty * price * 10**6 // 10**13, so price = cost * 10**7 // qty
    return pos.cost * 10 ** 7 // pos.qty


def on_batch(state, batch):
    global _entry_px, _peak, _hold_bars, _armed, _trail_on, _tranche2_done
    close = state.close(SYMBOL)
    if close is None:
        return []
    _closes.append(close)
    pos = state.positions.get(SYMBOL)

    if pos is None:
        # Flat: buy the first tranche on the deep dip.
        if len(_closes) > DROP_BARS:
            ref = _closes[-1 - DROP_BARS]
            drop_bps = (close - ref) * 10_000 // ref
            if not _armed:
                if drop_bps > REARM_BPS:
                    _armed = True
                return []
            if drop_bps <= -DROP1_BPS:
                return [{"side": "buy", "symbol": SYMBOL,
                         "notional_quote_units": state.cash * SIZE1_BPS // 10_000,
                         "max_slippage_bps": MAX_SLIP_BPS}]
        return []

    # In a position: maintain the entry price, the peak and the hold count.
    entry = _entry_price(state)
    if entry is None:
        return []
    if _entry_px is None:
        _entry_px = entry
        _peak = close
        _hold_bars = 0
        _trail_on = False
        _tranche2_done = False
    if close > _peak:
        _peak = close
    _hold_bars += 1

    # Scale in: spend the rest of the cash while the dip is still deep.
    if not _tranche2_done and len(_closes) > DROP_BARS and state.cash > 0:
        ref = _closes[-1 - DROP_BARS]
        drop_bps = (close - ref) * 10_000 // ref
        if drop_bps <= -DROP2_BPS:
            _tranche2_done = True
            _entry_px = None  # recompute the average entry next bar
            return [{"side": "buy", "symbol": SYMBOL,
                     "notional_quote_units": state.cash,
                     "max_slippage_bps": MAX_SLIP_BPS}]

    # Arm the trailing stop once the trade is in profit.
    if not _trail_on and close >= _entry_px * (10_000 + ACTIVATE_BPS) // 10_000:
        _trail_on = True

    hit = False
    if close >= _entry_px * (10_000 + TAKE_PROFIT_BPS) // 10_000:
        hit = True
    if _trail_on and close <= _peak * (10_000 - TRAIL_BPS) // 10_000:
        hit = True
    if _hold_bars >= MAX_HOLD:
        hit = True
    if hit:
        _entry_px = None
        _peak = None
        _hold_bars = 0
        _armed = False
        _trail_on = False
        _tranche2_done = False
        return [{"side": "sell", "symbol": SYMBOL, "qty": pos.qty,
                 "max_slippage_bps": MAX_SLIP_BPS}]
    return []


makefun_bars.run(on_batch)
