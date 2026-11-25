"""Tiny breakout bot for make.fun "Tiny Bot, Easy $2: Beat Buy-and-Hold on Solana".

Strategy: Donchian breakout + EMA trend filter + trailing stop, long only, across
all 7 symbols (FARTCOIN, JITOSOL, POPCAT, RAY, SOL, WETH, WIF).

Per symbol, over its own hourly closes:
  - EMA(12) and EMA(26), each seeded as the mean of its first span of closes,
    then moving 2 / (span + 1) of the way to each new close (float64, deterministic).
  - The 24-bar Donchian high: the highest close of the previous 24 bars.
  - The 6-bar return: close / close 6 bars ago - 1.

Entry (on a bar's close, filled at the next bar's open), on a symbol not held:
  EMA(8) is above EMA(21) AND the 6-bar return is above +0.2% AND either the
  close breaks above the 12-bar high or EMA(8) has just crossed above EMA(21)
  on this bar. The trend must be up with real momentum behind it, and the
  trigger is either a fresh 12-hour high or a fresh trend cross.

Exit (the whole position), on a bar's close:
  - EMA(8) crosses back below EMA(21), or
  - the close falls 8% below the highest close seen since entry (trailing stop), or
  - the position is worth 30% over its cost (take profit), or
  - the 6-bar return drops below -5% (momentum collapse).

Sizing: equity split over 7 slots (one per symbol), capped at the 25% per-symbol
weight cap and by the cash this reply has not spent yet; below the minimum
notional it buys nothing. Sells go first, then buys in universe order, at most
caps.max_orders_per_bar in all. Each order caps slippage at 100 bps past the
close it was decided on.

Drawdown guard: the bot tracks its running peak equity; while equity sits more
than 8% below that peak it opens no new positions (existing ones keep their
exits). No randomness, no clock, no network, no environment reads: the same
bars always produce the same orders.

Protocol: agent-fun/bars-replay/v1, via the vendored sdk/makefun_bars.py shim.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "sdk"))
import makefun_bars

FAST_SPAN = 8
SLOW_SPAN = 21
DONCHIAN_BARS = 12
MOMENTUM_BARS = 6
ENTRY_MOMENTUM = 0.002      # 6-bar return must exceed +0.2% to enter
EXIT_MOMENTUM = -0.05       # 6-bar return below -5% exits
TRAIL_STOP = 0.92           # exit if close < 92% of the peak close since entry
TAKE_PROFIT = 1.30          # exit if position value >= 130% of cost
MAX_SLIPPAGE_BPS = 100
GUARD_DRAWDOWN = 0.92       # no new entries while equity < 92% of peak equity
SLOTS = 7                   # one slot per symbol in the universe


class Ema:
    """One EMA: the closes it has seen until it starts, then its value."""

    __slots__ = ("span", "warm", "value")

    def __init__(self, span):
        self.span = span
        self.warm = []
        self.value = None

    def step(self, close):
        if self.value is not None:
            self.value += (2.0 / (self.span + 1)) * (close - self.value)
            return
        self.warm.append(close)
        if len(self.warm) == self.span:
            self.value = sum(self.warm) / self.span


class Series:
    """Per-symbol indicator state."""

    __slots__ = ("fast", "slow", "closes", "peak_since_entry", "gap_before", "gap_after")

    def __init__(self):
        self.fast = Ema(FAST_SPAN)
        self.slow = Ema(SLOW_SPAN)
        self.closes = []
        self.peak_since_entry = None
        self.gap_before = None
        self.gap_after = None

    def push(self, close):
        if self.fast.value is not None and self.slow.value is not None:
            self.gap_before = self.fast.value - self.slow.value
        self.fast.step(close)
        self.slow.step(close)
        self.closes.append(close)
        if self.fast.value is not None and self.slow.value is not None:
            self.gap_after = self.fast.value - self.slow.value

    def crossed_up(self):
        """True when EMA(fast) crossed above EMA(slow) on this bar."""
        return (
            self.gap_before is not None
            and self.gap_after is not None
            and self.gap_after > 0
            and self.gap_before <= 0
        )

    def donchian_high(self):
        """Highest close of the previous DONCHIAN_BARS bars (not this one)."""
        prev = self.closes[:-1]
        if len(prev) < DONCHIAN_BARS:
            return None
        return max(prev[-DONCHIAN_BARS:])

    def momentum(self):
        """Return over the last MOMENTUM_BARS bars, or None without enough history."""
        if len(self.closes) <= MOMENTUM_BARS:
            return None
        return self.closes[-1] / self.closes[-1 - MOMENTUM_BARS] - 1.0

    def trend_up(self):
        if self.fast.value is None or self.slow.value is None:
            return False
        return self.fast.value > self.slow.value


series = {}
peak_equity = 0


def on_batch(state, batch):
    global peak_equity
    if state.equity > peak_equity:
        peak_equity = state.equity

    fresh = set()
    for bar in batch["bars"]:
        s = series.get(bar["symbol"])
        if s is None:
            s = Series()
            series[bar["symbol"]] = s
        s.push(float(bar["c"]))
        fresh.add(bar["symbol"])

    if state.warming_up:
        return []

    sells = []
    entries = []
    for sym in state.hello["symbols"]:
        symbol = sym["symbol"]
        if symbol not in fresh:
            continue
        s = series[symbol]
        held = state.positions.get(symbol)
        close = float(state.close(symbol))
        if held is not None:
            if s.peak_since_entry is None or close > s.peak_since_entry:
                s.peak_since_entry = close
            value = state.value(symbol, held.qty)
            mom = s.momentum()
            if (
                not s.trend_up()
                or close < TRAIL_STOP * s.peak_since_entry
                or value * 100 >= held.cost * 130
                or (mom is not None and mom < EXIT_MOMENTUM)
            ):
                sells.append(
                    {"side": "sell", "symbol": symbol, "qty": held.qty,
                     "max_slippage_bps": MAX_SLIPPAGE_BPS}
                )
                s.peak_since_entry = None
        else:
            s.peak_since_entry = None
            high = s.donchian_high()
            mom = s.momentum()
            if (
                s.trend_up()
                and mom is not None
                and mom > ENTRY_MOMENTUM
                and (
                    (high is not None and close > high)
                    or s.crossed_up()
                )
            ):
                entries.append(symbol)

    orders = sells[: state.hello["caps"]["max_orders_per_bar"]]
    if entries and state.equity >= GUARD_DRAWDOWN * peak_equity:
        slots = min(len(state.hello["symbols"]), state.hello["caps"]["max_open_positions"])
        stake = state.equity // slots
        by_weight = state.hello["caps"]["max_weight_bps"] * state.equity // makefun_bars.BPS
        room = slots - len(state.positions)
        cash = state.cash
        for symbol in entries:
            if room <= 0 or len(orders) >= state.hello["caps"]["max_orders_per_bar"]:
                break
            slice_ = stake if stake < by_weight else by_weight
            room_for_symbol = state.weight_room(symbol)
            if slice_ > room_for_symbol:
                slice_ = room_for_symbol
            if cash < slice_:
                slice_ = cash
            if slice_ == 0 or slice_ < int(state.hello["fees"]["min_notional_quote_units"]):
                continue
            orders.append(
                {"side": "buy", "symbol": symbol, "notional_quote_units": slice_,
                 "max_slippage_bps": MAX_SLIPPAGE_BPS}
            )
            cash -= slice_
            room -= 1
    return orders


makefun_bars.run(on_batch)
