---
id: 77-async-hft
title: Async HFT (OrderSendAsync)
tags: [async, hft, ap-18]
applicable_phase: D
---

# Async HFT (OrderSendAsync)

`OrderSendAsync` posts the order and returns immediately; the result
arrives asynchronously via `OnTradeTransaction`. The kit's flagship
`CAsyncTradeManager.mqh` (`Include/CAsyncTradeManager.mqh`) wraps this
correctly and keeps a per-request reconciliation queue so the HFT
scaffold never ships a "naked" async submission.

## API surface (`CAsyncTradeManager` v2)

### Init

| Method | Purpose |
|---|---|
| `void Init(ulong magic, int maxRetries=2, ulong staleTimeoutUs=5000000, int deviation=10)` | bind to magic; configure retry, stale timeout, slippage |

### Entry (async open)

| Method | Purpose |
|---|---|
| `bool SendBuyAsync(symbol, lots, sl, tp)` | post a market BUY via `OrderSendAsync`, record `request_id` |
| `bool SendSellAsync(symbol, lots, sl, tp)` | post a market SELL via `OrderSendAsync`, record `request_id` |

### Exit (async close) — v2 new

| Method | Purpose |
|---|---|
| `bool SendCloseAsync(ulong ticket)` | close a specific position by ticket via `OrderSendAsync` |
| `int  CloseAllAsync(string symbol="")` | close all positions matching magic (+ optional symbol filter). Returns count of close requests sent |

### Reconciliation

| Method | Purpose |
|---|---|
| `void OnTransactionResult(trans, request, result)` | call from `OnTradeTransaction` — reconciles pending, retries on reject, tracks partial fills |

### Maintenance — v2 new

| Method | Purpose |
|---|---|
| `int  CleanupStale()` | remove pending requests older than `staleTimeoutUs`. Call from `OnTick()`. Returns count cleaned |
| `int  PendingCount()` | number of still-unreconciled `request_id`s |
| `AsyncStats GetStats()` | return stats struct (sent, reconciled, rejected, partial, stale, retried, avg/max latency) |
| `void PrintStats()` | print stats summary to Experts log |

## v2 improvements

1. **Async close** — `SendCloseAsync(ticket)` and `CloseAllAsync(symbol)`
   for event-driven position closing (replaces `CTrade.SetAsyncMode` +
   `Sleep()` polling pattern).

2. **Auto filling mode** — `_detectFilling()` queries
   `SYMBOL_FILLING_MODE` per symbol and selects FOK → IOC → RETURN
   automatically. No more hardcoded `ORDER_FILLING_IOC`.

3. **Stale timeout** — `CleanupStale()` removes pending requests older
   than the configured threshold (default 5s). Prevents memory leaks
   and backpressure deadlocks when the server fails to respond.

4. **Partial fill tracking** — `OnTransactionResult` checks
   `result.volume` vs requested. On partial fill, logs the fill and
   retries the remaining volume automatically.

5. **Retry on reject** — retcodes 10004 (requote), 10006 (reject),
   10007 (cancel), 10021 (too many requests) trigger automatic retry
   with fresh price. Configurable max retries (default 2).

6. **O(1) removal** — swap-with-last instead of O(n) array shift when
   removing reconciled entries from the pending queue.

Internally each pending submission stores `(request_id, symbol, type,
volume, volume_filled, timestamp_us, retry_count, is_close,
close_ticket)` so the reconciliation step can emit real
submission-to-confirmation latency in microseconds.

## Wiring the handler

```mql5
#include <CAsyncTradeManager.mqh>

CAsyncTradeManager async_tm;

int OnInit(void) {
   async_tm.Init(InpMagic, 2, 5000000);  // magic, retries, stale timeout 5s
   return INIT_SUCCEEDED;
}

void OnTick(void) {
   async_tm.CleanupStale();  // housekeeping

   if(/* buy signal */)
      async_tm.SendBuyAsync(_Symbol, lots, sl, tp);

   if(/* close all signal */)
      async_tm.CloseAllAsync(_Symbol);
}

void OnDeinit(const int reason) {
   async_tm.PrintStats();
}

void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest &req,
                        const MqlTradeResult  &res) {
   async_tm.OnTransactionResult(trans, req, res);
}
```

## Anti-pattern hook — AP-18

`scripts/vibecodekit_mql5/lint.py:detect_ap18` scans for any
`OrderSendAsync(` call; if the same translation unit lacks an
`OnTradeTransaction(` definition the linter raises an `ERROR`:

```
EAName.mq5:42:3: ERROR AP-18: OrderSendAsync without OnTradeTransaction handler
```

This is intentionally a hard ERROR: an async submitter without a
matching handler is unrecoverable — request_ids leak, latency stats
are unmeasurable, and partial-fills go silent.

## Scaffold

```bash
python -m vibecodekit_mql5.async_build --name FastEA --symbol EURUSD --tf M1
```

renders the `scaffolds/hft-async/` archetype, which pre-wires both
`CAsyncTradeManager` and the matching `OnTradeTransaction` block so the
EA passes AP-18 out of the box. The v2 scaffold also includes:
- `CleanupStale()` call in `OnTick()`
- `PrintStats()` call in `OnDeinit()`
- Configurable `InpMaxRetries` and `InpStaleTimeoutSec` inputs
