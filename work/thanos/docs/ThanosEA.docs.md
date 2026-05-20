---
ea_name: ThanosEA
ea_version: 0.1.0
kit_version: 1.0.1
built_at: 2026-05-20T20:58:02Z
built_from: work/thanos/ea-spec.yaml
symbol: EURUSD
timeframe: H1
mode: enterprise
---

# ThanosEA
_Hệ thống_
_ThanosEA Kiến trúc_

## Kiến trúc hệ thống

- **Quản lý vốn** — Tính size + chặn DD ngày + veto correlation
- **Tổng hợp tín hiệu** — 1 signal · fuse OR · 0 filter
- **Thực thi lệnh** — Stealth, magic registry, async order book

## Chu trình chiến lược

Quét → Soạn → Kiểm → **Phát hành**

- _Quét_: Đọc spec
- _Soạn_: Sinh code từ scaffold
- _Kiểm_: Quét lint + cổng kiểm quyền
- _Phát hành_: Biên dịch + dashboard

## Tham số EA

| Nhóm | Tên | Kiểu | Mặc định | Ghi chú |
|---|---|---|---|---|
| - | `AllowBuy` | `bool` | `true` |  |
| - | `AllowSell` | `bool` | `true` |  |
| - | `EAMakesFirstOrder` | `bool` | `true` |  |
| - | `EmaPeriod` | `int` | `20` |  |
| - | `EmaRangePips` | `int` | `3000` |  |
| - | `EmaTimeframe` | `ENUM_TIMEFRAMES` | `PERIOD_CURRENT` |  |
| - | `DcaStepPips` | `int` | `30` |  |
| - | `StartLot` | `double` | `0.01` |  |
| - | `LotMultiplier` | `double` | `1.4` |  |
| - | `LotDecimalPlaces` | `int` | `2` |  |
| - | `TpFromBEPips` | `int` | `20` |  |
| - | `CloseAllProfit` | `double` | `10.0` |  |
| - | `DailyTpTarget` | `double` | `50.0` |  |
| - | `EnableTrimFarthest` | `bool` | `true` |  |
| - | `EnableTrimMostLoss` | `bool` | `true` |  |
| - | `TrimTpPips` | `int` | `1000` |  |
| - | `TrailingType` | `int` | `0` |  |
| - | `TrailingStepPips` | `int` | `0` |  |
| - | `MinTrailingProfit` | `int` | `10` |  |
| - | `TrailingPadding` | `int` | `0` |  |
| - | `TrailingTimeframe` | `int` | `15` |  |
| - | `DeleteOrdersAtHour` | `bool` | `true` |  |
| - | `DeleteHour` | `int` | `20` |  |
| - | `StartHour` | `int` | `0` |  |
| - | `EndHour` | `int` | `24` |  |
| - | `MaxSpreadPips` | `double` | `5.0` |  |
| - | `DailyLossPct` | `double` | `0.05` |  |
| - | `MaxOpenPositions` | `int` | `0` |  |
| - | `FreezeOnDDPct` | `double` | `0.10` |  |
| - | `MagicNumber` | `int` | `777` |  |
| - | `FontSize` | `int` | `10` |  |
| - | `InfoColor` | `color` | `clrLime` |  |

## Lưu ý quan trọng

> [Lưu ý] **Mode: enterprise (7-layer permission gate)**
> Permission gate enterprise yêu cầu Trader-17 đầy đủ trước khi ship. Scaffold không có logic giao dịch thật → fail là đúng.
