# Deep-dip scale-in bot v3

[![make.fun · btc-race-24h-20261117-0603](https://make.fun/badge/btc-race-24h-20261117-0603.svg)](https://make.fun/bounty/btc-race-24h-20261117-0603)
[![rank](https://make.fun/badge/btc-race-24h-20261117-0603/Shanumameyra/btc-race-0603-bot/rank.svg)](https://make.fun/bounty/btc-race-24h-20261117-0603/leaderboard)
[![reward](https://make.fun/badge/btc-race-24h-20261117-0603/Shanumameyra/btc-race-0603-bot/reward.svg)](https://make.fun/bounty/btc-race-24h-20261117-0603)

Entry for the [make.fun bounty "Race a BTC trading bot live for 24 hours"](https://make.fun/bounty/btc-race-24h-20261117-0603).

## What it does

Trades Coinbase Wrapped BTC (cbBTC) against USDC, minute by minute, on 1-minute on-chain bars. Deep-dip scale-in: buys in two tranches when the price drops 170 bps from its recent high, trails the recovery (arm +80 bps, trail 90 bps), takes profit at +150 bps, max hold 300 bars. Dev window (16–17 Nov 2026): net +$13.52, 1 round trip, max drawdown 0.62%.

## Run

```sh
python3 main.py
```

Reads one JSON bar per minute on stdin, writes buy/sell orders on stdout. Standard library only; `vendor/makefun_bars.py` is vendored.

## Referral

https://make.fun/r/df7af47d
