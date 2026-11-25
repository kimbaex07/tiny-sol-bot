# Tiny Breakout Bot — Beat Buy-and-Hold on Solana

[![make.fun · u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1](https://make.fun/badge/u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1.svg)](https://make.fun/bounty/u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1?utm_source=github&utm_medium=readme&utm_campaign=u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1)
[![rank](https://make.fun/badge/u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1/kimbaex07/tiny-sol-bot/rank.svg)](https://make.fun/bounty/u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1)
[![reward](https://make.fun/badge/u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1/kimbaex07/tiny-sol-bot/reward.svg)](https://make.fun/bounty/u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1?utm_source=github&utm_medium=readme&utm_campaign=u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1)

A tiny paper-trading bot for the make.fun contest
"Tiny Bot, Easy $2: Beat Buy-and-Hold on Solana" (`u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1`).
It trades hourly bars of FARTCOIN, JITOSOL, POPCAT, RAY, SOL, WETH and WIF
against 10,000 USDC of paper capital, long only, no leverage.

## Strategy

A Donchian breakout with an EMA trend filter, a trailing stop, and a
drawdown guard. Per symbol, over its own hourly closes, the bot tracks
EMA(8) and EMA(21), the highest close of the previous 12 bars, and the
6-bar return. It buys when EMA(8) is above EMA(21), the 6-bar return is
above +0.2%, and either the close breaks above the 12-bar high or EMA(8)
has just crossed above EMA(21). It sells the whole position when EMA(8)
falls back below EMA(21), when the close drops 8% under the highest close
since entry, when the position is worth 30% over its cost, or when the
6-bar return collapses below −5%. Each entry risks one seventh of equity,
capped at the 25% per-symbol weight cap, and while equity sits more than
8% below its running peak the bot opens nothing new. Fully deterministic:
no randomness, no clock, no network, no environment reads.

## Dev-window result (official `grade-local`, 136 hourly bars)

| | Net PnL (USDC) | Trades | Max drawdown |
|---|---|---|---|
| **This bot** | **−160.74** | **24** | **2.38%** |
| Buy-and-hold baseline | −869.34 | 7 | 10.92% |
| EMA-cross baseline | −173.04 | 28 | 2.51% |

The dev window was a down market (buy-and-hold lost 8.7%). The bot lost
far less than buy-and-hold (+708.60 USDC better), beat the EMA-cross
baseline too, and met every guardrail (≥ 8 trades, drawdown ≤ 25%,
0 rejected orders). The two executions reproduced byte for byte
(L1 regrade). Dev numbers are no promise about the final window — the
final 3 days of hourly bars do not exist yet.

## How to run / grade locally

```sh
# From the contest kit directory (it ships cli/makefun.mjs):
node cli/makefun.mjs grade-local --kit . --bot /path/to/tiny-sol-bot --driver docker

# Without docker, with python3.13 on PATH:
node cli/makefun.mjs grade-local --kit . --bot /path/to/tiny-sol-bot --driver process
```

The bot is Python 3 stdlib only, plus the vendored `sdk/makefun_bars.py`
(a verbatim copy of the kit's protocol shim). It speaks
`agent-fun/bars-replay/v1` on stdin/stdout; the grader runs it as
`python3 -P -s main.py`.

## Files

- `main.py` — the bot (strategy + protocol loop, stdlib only).
- `sdk/makefun_bars.py` — vendored protocol shim, verbatim from the kit.
- `.makefun/owner.json` — payout wallet of the entry's owner.
- `LICENSE` — MIT.
