//+------------------------------------------------------------------+
//|                                                     ThanosEA.mq5 |
//|   Grid DCA EA — rebuilt via vibecodekit-mql5-ea enterprise pipeline|
//|   Original: Grid_Converted (cmillion, MQL4→MQL5)                 |
//|                                                                   |
//|   v2.2 — Async close optimization:                              |
//|     CloseAll via CAsyncTradeManager v2 (event-driven, no Sleep)  |
//|     OnTradeTransaction reconciliation for close confirmations    |
//|     Stale request cleanup in OnTick                              |
//|     Async trade stats on deinit                                  |
//|                                                                   |
//|   v2.1 — Feature expansion:                                       |
//|     EMA range entry (± points from EMA baseline)                  |
//|     DCA lot = initial * multiplier^count                          |
//|     TP from breakeven of series                                   |
//|     Hedge trimming: farthest + most-negative order pairing        |
//|     Close-all on profit target                                    |
//|     Daily TP limit — pause trading until next day                 |
//|                                                                   |
//|   Fixes preserved: AP-5/8/9/11/14/15/20/21                       |
//|   Code quality: all obfuscated names replaced                     |
//+------------------------------------------------------------------+
// digits-tested: 2,3,4,5

#include <Trade/Trade.mqh>
#include <CPipNormalizer.mqh>
#include <CSpreadGuard.mqh>
#include <CMfeMaeLogger.mqh>
#include <CRiskGuard.mqh>
#include <CAsyncTradeManager.mqh>

//=== Group 1: Trade Direction ===//
sinput bool   AllowBuy           = true;
sinput bool   AllowSell          = true;
sinput bool   EAMakesFirstOrder  = true;

//=== Group 2: EMA Range Entry ===//
input int     EmaPeriod          = 20;
input int     EmaRangePoints     = 3000;
sinput ENUM_TIMEFRAMES EmaTimeframe = PERIOD_CURRENT;

//=== Group 3: DCA Grid ===//
input int     DcaStepPips        = 30;
input double  StartLot           = 0.01;
input double  LotMultiplier      = 1.4;
sinput int    LotDecimalPlaces   = 2;

//=== Group 4: Take Profit ===//
input int     TpFromBEPips       = 20;
sinput double CloseAllProfit     = 10.0;
sinput double DailyTpTarget      = 50.0;

//=== Group 5: Hedge Trimming ===//
sinput bool   EnableTrimFarthest   = true;
sinput bool   EnableTrimMostLoss   = true;
sinput int    TrimTpPoints         = 1000;

//=== Group 6: Trailing Stop (0=Off, 1=Candles, 2=Fractals, 3+=Points) ===//
sinput int    TrailingType        = 0;
sinput int    TrailingStepPips    = 0;
sinput int    MinTrailingProfit   = 10;
sinput int    TrailingPadding     = 0;
sinput int    TrailingTimeframe   = 15;

//=== Group 7: Schedule & Cleanup (sinput) ===//
sinput bool   DeleteOrdersAtHour = true;
sinput int    DeleteHour     = 20;
sinput int    StartHour      = 0;
sinput int    EndHour        = 24;

//=== Group 8: Risk Management (sinput) ===//
sinput double MaxSpreadPips    = 5.0;
sinput double DailyLossPct    = 0.05;
sinput int    MaxOpenPositions = 0;
sinput double FreezeOnDDPct   = 0.10;

//=== Group 9: Display & Identification (sinput) ===//
sinput int    MagicNumber    = 777;
sinput int    FontSize       = 10;
sinput color  InfoColor      = clrLime;

//=== Constants ===//
const int ARROW_RIGHT_PRICE = 220;

#define DIR_BUY   0
#define DIR_SELL  1

//=== Global Objects ===//
CTrade              trade;
CPipNormalizer      pip;
CSpreadGuard        spreadGuard;
CMfeMaeLogger       mfeLogger;
CRiskGuard          riskGuard;
CAsyncTradeManager  async_tm;

//=== Global State ===//
string    accountCurrency    = "";
double    tickValue          = 0.0;
int       stopsLevelPoints   = 0;
int       slippage           = 0;
bool      isHedging          = false;
int       pipScale           = 1;
int       trailingTF         = 0;
long      lastBarCount       = 0;
int       emaHandle          = INVALID_HANDLE;
double    dailyClosedProfit  = 0.0;
int       dailyTpDay         = -1;
bool      dailyTpReached     = false;

//=== Timeframe Helpers ===//
int NextHigherTF(int minutes) {
   if(minutes > 43200) return 0;
   if(minutes > 10080) return 43200;
   if(minutes > 1440)  return 10080;
   if(minutes > 240)   return 1440;
   if(minutes > 60)    return 240;
   if(minutes > 30)    return 60;
   if(minutes > 15)    return 30;
   if(minutes > 5)     return 15;
   if(minutes > 1)     return 5;
   if(minutes == 1)    return 1;
   if(minutes == 0)    return (int)Period();
   return 0;
}

string TFToString(int m) {
   if(m==1)     return "M1";
   if(m==5)     return "M5";
   if(m==15)    return "M15";
   if(m==30)    return "M30";
   if(m==60)    return "H1";
   if(m==240)   return "H4";
   if(m==1440)  return "D1";
   if(m==10080) return "W1";
   if(m==43200) return "MN1";
   return "period error";
}

ENUM_TIMEFRAMES TFFromMinutes(int m) {
   switch(m) {
      case 0:     return PERIOD_CURRENT;
      case 1:     return PERIOD_M1;
      case 5:     return PERIOD_M5;
      case 15:    return PERIOD_M15;
      case 30:    return PERIOD_M30;
      case 60:    return PERIOD_H1;
      case 240:   return PERIOD_H4;
      case 1440:  return PERIOD_D1;
      case 10080: return PERIOD_W1;
      case 43200: return PERIOD_MN1;
      default:    return PERIOD_CURRENT;
   }
}

//=== Chart Label Helper ===//
void SetChartLabel(const string name, const string txt, int x, int y, color col) {
   if(ObjectFind(0, name) < 0) {
      ObjectCreate(0, name, OBJ_LABEL, 0, 0, 0);
      ObjectSetInteger(0, name, OBJPROP_CORNER, 1);
      ObjectSetInteger(0, name, OBJPROP_XDISTANCE, x);
      ObjectSetInteger(0, name, OBJPROP_YDISTANCE, y);
   }
   ObjectSetString(0, name, OBJPROP_TEXT, txt);
   ObjectSetInteger(0, name, OBJPROP_COLOR, col);
   ObjectSetInteger(0, name, OBJPROP_FONTSIZE, FontSize);
   ObjectSetString(0, name, OBJPROP_FONT, "Arial");
}

//=== Metal detection: XAU/XAG → 1 pip = 10 points (1 USD = 10 pips) ===//
bool IsMetalSymbol() {
   string sym = _Symbol;
   StringToUpper(sym);
   return (StringFind(sym, "XAU") >= 0 || StringFind(sym, "GOLD") >= 0 ||
           StringFind(sym, "XAG") >= 0 || StringFind(sym, "SILVER") >= 0);
}

double ScaledPips(int pips) {
   return pip.Pips(pips * pipScale);
}

double ScaledPipsD(double pips) {
   return pip.Pips((int)(pips * pipScale));
}

//=== EMA Value ===//
double GetEMA() {
   if(emaHandle == INVALID_HANDLE) return 0.0;
   double buf[];
   if(CopyBuffer(emaHandle, 0, 0, 1, buf) <= 0) return 0.0;
   return buf[0];
}

//=== RSI Wrapper ===//
double GetRSI(const string sym, ENUM_TIMEFRAMES tf, int period, ENUM_APPLIED_PRICE price, int shift) {
   static int handle = -1;
   static string lastSym = "";
   static ENUM_TIMEFRAMES lastTF = PERIOD_CURRENT;
   static int lastPeriod = 0;
   static ENUM_APPLIED_PRICE lastPrice = PRICE_CLOSE;

   if(handle == INVALID_HANDLE || sym != lastSym || tf != lastTF || period != lastPeriod || price != lastPrice) {
      if(handle != INVALID_HANDLE) IndicatorRelease(handle);
      handle = iRSI(sym, tf, period, price);
      lastSym = sym; lastTF = tf; lastPeriod = period; lastPrice = price;
   }
   if(handle == INVALID_HANDLE) return 0.0;
   double buf[];
   if(CopyBuffer(handle, 0, shift, 1, buf) <= 0) return 0.0;
   return buf[0];
}

//=== Fractal Wrapper ===//
double GetFractal(const string sym, ENUM_TIMEFRAMES tf, int bufferIndex, int shift) {
   static int handle = INVALID_HANDLE;
   static string lastSym = "";
   static ENUM_TIMEFRAMES lastTF = PERIOD_CURRENT;

   if(handle == INVALID_HANDLE || sym != lastSym || tf != lastTF) {
      if(handle != INVALID_HANDLE) IndicatorRelease(handle);
      handle = iFractals(sym, tf);
      lastSym = sym; lastTF = tf;
   }
   if(handle == INVALID_HANDLE) return 0.0;
   double val[];
   if(CopyBuffer(handle, bufferIndex, shift, 1, val) <= 0) return 0.0;
   return val[0];
}

//=== Trailing Stop Calculator ===//
double CalcTrailingLevel(int direction, double currentPrice, double trailParam) {
   double level = 0.0;
   ENUM_TIMEFRAMES tf = TFFromMinutes(trailingTF);

   if(trailParam > 2.0) {
      if(direction == 1)
         level = NormalizeDouble(currentPrice - ScaledPips((int)trailParam), _Digits);
      else
         level = NormalizeDouble(currentPrice + ScaledPips((int)trailParam), _Digits);
   } else if(trailParam == 2.0) {
      if(direction == 1) {
         for(int i = 1; i < 100; i++) {
            level = GetFractal(_Symbol, tf, 1, i);
            if(level != 0.0) {
               level -= NormalizeDouble(ScaledPips(TrailingPadding), _Digits);
               if(currentPrice - stopsLevelPoints * pip.Point() > level)
                  break;
            } else level = 0;
         }
         DrawArrow("FR Buy", level + pip.Point(), 218, clrRed);
      } else {
         for(int i = 1; i < 100; i++) {
            level = GetFractal(_Symbol, tf, 0, i);
            if(level != 0.0) {
               level += NormalizeDouble(ScaledPips(TrailingPadding), _Digits);
               if(currentPrice + stopsLevelPoints * pip.Point() < level)
                  break;
            } else level = 0;
         }
         DrawArrow("FR Sell", level, 217, clrRed);
      }
   } else if(trailParam == 1.0) {
      if(direction == 1) {
         for(int i = 1; i < 500; i++) {
            level = NormalizeDouble(iLow(_Symbol, tf, i) - ScaledPips(TrailingPadding), _Digits);
            if(level != 0.0) {
               if(currentPrice - stopsLevelPoints * pip.Point() > level)
                  break;
               level = 0;
            }
         }
         DrawArrow("FR Buy", level + pip.Point(), 159, clrRed);
      } else {
         for(int i = 1; i < 500; i++) {
            level = NormalizeDouble(iHigh(_Symbol, tf, i) + ScaledPips(TrailingPadding), _Digits);
            if(level != 0.0) {
               if(currentPrice + stopsLevelPoints * pip.Point() < level)
                  break;
               level = 0;
            }
         }
         DrawArrow("FR Sell", level, 159, clrRed);
      }
   }

   if(direction == 1) {
      if(level != 0.0)
         DrawArrow("SL Buy", level, ARROW_RIGHT_PRICE, clrBlue);
      if(stopsLevelPoints > 0)
         DrawArrow("STOPLEVEL-", currentPrice - stopsLevelPoints * pip.Point(), 4, clrBlue);
   } else {
      if(level != 0.0)
         DrawArrow("SL Sell", level, ARROW_RIGHT_PRICE, clrPink);
      if(stopsLevelPoints > 0)
         DrawArrow("STOPLEVEL+", currentPrice + stopsLevelPoints * pip.Point(), 4, clrPink);
   }
   return level;
}

void DrawArrow(const string name, double price, int arrowCode, color col) {
   ObjectDelete(0, name);
   ObjectCreate(0, name, OBJ_ARROW, 0, iTime(_Symbol, PERIOD_CURRENT, 0), price);
   ObjectSetInteger(0, name, OBJPROP_ARROWCODE, arrowCode);
   ObjectSetInteger(0, name, OBJPROP_COLOR, col);
}

//=== Trading Hours Filter ===//
bool IsTradingHours() {
   MqlDateTime dt;
   TimeToStruct(TimeCurrent(), dt);
   int hour = dt.hour;
   int sh = (StartHour == 0) ? 24 : StartHour;
   int eh = (EndHour == 0) ? 24 : EndHour;
   if(hour == 0) hour = 24;

   if(sh < eh) {
      if(hour < sh || hour >= eh) return false;
   } else if(sh > eh) {
      if(hour < sh && hour >= eh) return false;
   }
   return true;
}

//=== Delete Pending Orders ===//
void DeleteAllPendingOrders() {
   for(int i = OrdersTotal() - 1; i >= 0; i--) {
      ulong ticket = OrderGetTicket(i);
      if(ticket > 0) {
         if(OrderGetString(ORDER_SYMBOL) == _Symbol && OrderGetInteger(ORDER_MAGIC) == MagicNumber) {
            ENUM_ORDER_TYPE ot = (ENUM_ORDER_TYPE)OrderGetInteger(ORDER_TYPE);
            if(ot == ORDER_TYPE_BUY_STOP || ot == ORDER_TYPE_SELL_STOP ||
               ot == ORDER_TYPE_BUY_LIMIT || ot == ORDER_TYPE_SELL_LIMIT) {
               trade.OrderDelete(ticket);
            }
         }
      }
   }
}

//=== Close Positions by Direction (async via CAsyncTradeManager v2) ===//
int ClosePositionsByDirection(int direction) {
   int sent = 0;
   double closingProfit = 0.0;

   // Async close positions via CAsyncTradeManager
   for(int i = PositionsTotal() - 1; i >= 0; i--) {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if(PositionGetInteger(POSITION_MAGIC) != MagicNumber) continue;
      ENUM_POSITION_TYPE ptype = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
      if((ptype == POSITION_TYPE_BUY && (direction == 1 || direction == 0)) ||
         (ptype == POSITION_TYPE_SELL && (direction == -1 || direction == 0))) {
         closingProfit += PositionGetDouble(POSITION_PROFIT);
         if(async_tm.SendCloseAsync(ticket))
            sent++;
      }
   }

   // Delete pending orders (sync — not latency-critical)
   for(int i = OrdersTotal() - 1; i >= 0; i--) {
      ulong ticket = OrderGetTicket(i);
      if(ticket == 0) continue;
      if(OrderGetString(ORDER_SYMBOL) != _Symbol) continue;
      if(OrderGetInteger(ORDER_MAGIC) != MagicNumber) continue;
      ENUM_ORDER_TYPE ot = (ENUM_ORDER_TYPE)OrderGetInteger(ORDER_TYPE);
      if((ot == ORDER_TYPE_BUY_STOP && (direction == 1 || direction == 0)) ||
         (ot == ORDER_TYPE_SELL_STOP && (direction == -1 || direction == 0))) {
         trade.OrderDelete(ticket);
      }
   }

   // Pre-compute daily profit (async close confirms via OnTradeTransaction)
   dailyClosedProfit += closingProfit;

   if(sent > 0)
      PrintFormat("CloseAll async: sent %d close requests, est profit %.2f", sent, closingProfit);
   return sent;
}

//=== Protective SL for DCA series (wide, non-interfering) ===//
double CalcProtectiveSL(int direction, double price) {
   double slDistance = ScaledPips(500);
   if(direction == 1)
      return NormalizeDouble(price - slDistance, _Digits);
   else
      return NormalizeDouble(price + slDistance, _Digits);
}

//=== Calculate DCA Lot: initial * multiplier^count ===//
double CalcNextLot(int seriesCount) {
   if(seriesCount == 0) return StartLot;
   return NormalizeDouble(StartLot * MathPow(LotMultiplier, seriesCount), LotDecimalPlaces);
}

//=== Calculate Breakeven Price of a series ===//
double CalcSeriesBE(int direction, double &totalLots) {
   double weightedPrice = 0.0;
   totalLots = 0.0;
   for(int i = 0; i < PositionsTotal(); i++) {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if(PositionGetInteger(POSITION_MAGIC) != MagicNumber) continue;
      ENUM_POSITION_TYPE ptype = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
      if((direction == 1 && ptype != POSITION_TYPE_BUY) ||
         (direction == -1 && ptype != POSITION_TYPE_SELL)) continue;
      double lots = PositionGetDouble(POSITION_VOLUME);
      double price = PositionGetDouble(POSITION_PRICE_OPEN);
      weightedPrice += price * lots;
      totalLots += lots;
   }
   if(totalLots <= 0.0) return 0.0;
   return NormalizeDouble(weightedPrice / totalLots, _Digits);
}

//=== Hedge Trim: pair most-profitable with target order ===//
void TrimPair(int direction, bool trimFarthest) {
   ulong bestTicket = 0;
   double bestProfit = -999999.0;
   ulong targetTicket = 0;
   double targetValue = 0.0;
   bool targetInit = false;

   for(int i = 0; i < PositionsTotal(); i++) {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if(PositionGetInteger(POSITION_MAGIC) != MagicNumber) continue;
      ENUM_POSITION_TYPE ptype = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
      if((direction == 1 && ptype != POSITION_TYPE_BUY) ||
         (direction == -1 && ptype != POSITION_TYPE_SELL)) continue;

      double profit = PositionGetDouble(POSITION_PROFIT);
      double openPrice = PositionGetDouble(POSITION_PRICE_OPEN);
      double currentPrice = (direction == 1) ?
         SymbolInfoDouble(_Symbol, SYMBOL_BID) : SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      double distance = MathAbs(openPrice - currentPrice);

      if(profit > bestProfit) {
         bestProfit = profit;
         bestTicket = ticket;
      }

      if(trimFarthest) {
         if(!targetInit || distance > targetValue) {
            targetValue = distance;
            targetTicket = ticket;
            targetInit = true;
         }
      } else {
         if(!targetInit || profit < targetValue) {
            targetValue = profit;
            targetTicket = ticket;
            targetInit = true;
         }
      }
   }

   if(bestTicket == 0 || targetTicket == 0 || bestTicket == targetTicket) return;
   if(bestProfit <= 0.0) return;

   double bestLots = 0, bestOpen = 0, targetLots = 0, targetOpen = 0;
   if(PositionSelectByTicket(bestTicket)) {
      bestLots = PositionGetDouble(POSITION_VOLUME);
      bestOpen = PositionGetDouble(POSITION_PRICE_OPEN);
   }
   if(PositionSelectByTicket(targetTicket)) {
      targetLots = PositionGetDouble(POSITION_VOLUME);
      targetOpen = PositionGetDouble(POSITION_PRICE_OPEN);
   }
   if(bestLots <= 0 || targetLots <= 0) return;

   double pairBE = NormalizeDouble((bestOpen * bestLots + targetOpen * targetLots) /
                                    (bestLots + targetLots), _Digits);
   double trimTP = 0.0;
   if(direction == 1)
      trimTP = NormalizeDouble(pairBE + pip.Pips(TrimTpPoints), _Digits);
   else
      trimTP = NormalizeDouble(pairBE - pip.Pips(TrimTpPoints), _Digits);

   trade.PositionModify(bestTicket, PositionGetDouble(POSITION_SL), trimTP);
   trade.PositionModify(targetTicket, PositionGetDouble(POSITION_SL), trimTP);
   PrintFormat("Trim %s: paired #%I64d (profit %.2f) with #%I64d (%s), BE=%.5f TP=%.5f",
               trimFarthest ? "farthest" : "most-loss",
               bestTicket, bestProfit, targetTicket,
               trimFarthest ? "farthest" : "most-negative",
               pairBE, trimTP);
}

//+------------------------------------------------------------------+
//| OnInit                                                            |
//+------------------------------------------------------------------+
int OnInit() {
   ENUM_ACCOUNT_MARGIN_MODE marginMode =
      (ENUM_ACCOUNT_MARGIN_MODE)AccountInfoInteger(ACCOUNT_MARGIN_MODE);
   isHedging = (marginMode == ACCOUNT_MARGIN_MODE_RETAIL_HEDGING);
   if(!isHedging) {
      Alert("WARNING: Thanos EA is designed for HEDGING accounts. ",
            "Current mode: ", EnumToString(marginMode),
            ". Grid logic may not work correctly on netting accounts.");
   }

   if(!pip.Init(_Symbol)) {
      Alert("CPipNormalizer failed to init for ", _Symbol);
      return INIT_FAILED;
   }

   pipScale = IsMetalSymbol() ? 10 : 1;
   PrintFormat("Pip scale: %d (%s)", pipScale, IsMetalSymbol() ? "Metal" : "Forex");

   trade.SetExpertMagicNumber(MagicNumber);
   trade.SetDeviationInPoints((ulong)((_Digits == 5 || _Digits == 3) ? 30 : 3));
   trade.SetTypeFilling(ORDER_FILLING_RETURN);

   int deviation = (_Digits == 5 || _Digits == 3) ? 30 : 3;
   async_tm.Init((ulong)MagicNumber, 2, 5000000, deviation);

   spreadGuard.Init(pip, MaxSpreadPips * pipScale);
   mfeLogger.Init("ThanosEA_mfe_mae.csv");
   riskGuard.Init(DailyLossPct, MaxOpenPositions, FreezeOnDDPct);

   accountCurrency = " " + AccountInfoString(ACCOUNT_CURRENCY);
   SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE, tickValue);
   trailingTF = NextHigherTF(TrailingTimeframe);
   slippage = (_Digits == 5 || _Digits == 3) ? 30 : 3;
   stopsLevelPoints = (int)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL);

   emaHandle = iMA(_Symbol, EmaTimeframe, EmaPeriod, 0, MODE_EMA, PRICE_CLOSE);
   if(emaHandle == INVALID_HANDLE) {
      Alert("Failed to create EMA indicator");
      return INIT_FAILED;
   }

   lastBarCount = Bars(_Symbol, _Period);
   dailyClosedProfit = 0.0;
   dailyTpReached = false;
   MqlDateTime dt;
   TimeToStruct(TimeCurrent(), dt);
   dailyTpDay = dt.day;

   int yPos = FontSize + FontSize / 2;
   SetChartLabel("Balance",    "", 5, yPos, InfoColor); yPos += FontSize * 2;
   SetChartLabel("Equity",     "", 5, yPos, InfoColor); yPos += FontSize * 2;
   SetChartLabel("FreeMargin", "", 5, yPos, InfoColor); yPos += FontSize * 2;
   SetChartLabel("ProfitB",    "", 5, yPos, InfoColor); yPos += FontSize * 2;
   SetChartLabel("ProfitS",    "", 5, yPos, InfoColor); yPos += FontSize * 2;
   SetChartLabel("Profit",     "", 5, yPos, InfoColor); yPos += FontSize * 3;
   SetChartLabel("EMAInfo",    "", 5, yPos, InfoColor); yPos += FontSize * 2;
   SetChartLabel("DailyPL",    "", 5, yPos, InfoColor); yPos += FontSize * 2;
   SetChartLabel("ParamHeader", "── Thanos EA v2.1 ──", 5, yPos, clrAqua);
   yPos += FontSize * 2;

   string dirText = "";
   if(AllowBuy)  dirText = "Buy ";
   if(AllowSell) dirText += "Sell";
   SetChartLabel("ParamDir", "Allowed: " + dirText, 5, yPos, InfoColor);
   yPos += FontSize * 2;
   SetChartLabel("ParamEMA",     StringFormat("EMA(%d) range +/- %d pts", EmaPeriod, EmaRangePoints), 5, yPos, InfoColor);
   yPos += FontSize * 2;
   SetChartLabel("ParamDCA",     StringFormat("DCA step %d pips, mult %.2f", DcaStepPips, LotMultiplier), 5, yPos, InfoColor);
   yPos += FontSize * 2;
   SetChartLabel("ParamLot",     StringFormat("Start lot %.2f", StartLot), 5, yPos, InfoColor);
   yPos += FontSize * 2;
   SetChartLabel("ParamMode",    StringFormat("Account: %s", isHedging ? "Hedging" : "Netting (WARNING)"), 5, yPos,
                 isHedging ? InfoColor : clrRed);

   Comment("Thanos EA Grid DCA v2.1");
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| OnDeinit                                                          |
//+------------------------------------------------------------------+
void OnDeinit(const int reason) {
   if(emaHandle != INVALID_HANDLE) IndicatorRelease(emaHandle);
   async_tm.PrintStats();
   ObjectsDeleteAll(0, 0, -1);
}

//+------------------------------------------------------------------+
//| OnTradeTransaction — wire MFE/MAE logger                         |
//+------------------------------------------------------------------+
void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest &request,
                        const MqlTradeResult &result) {
   mfeLogger.OnTradeTransaction(trans);
   async_tm.OnTransactionResult(trans, request, result);
}

//+------------------------------------------------------------------+
//| OnTick                                                            |
//+------------------------------------------------------------------+
void OnTick() {
   riskGuard.OnTick();
   mfeLogger.OnTick();
   async_tm.CleanupStale();

   // Daily TP reset on new day
   MqlDateTime dt;
   TimeToStruct(TimeCurrent(), dt);
   if(dt.day != dailyTpDay) {
      dailyTpDay = dt.day;
      dailyClosedProfit = 0.0;
      dailyTpReached = false;
   }

   if(DeleteOrdersAtHour && dt.hour == DeleteHour)
      DeleteAllPendingOrders();

   // Check daily TP
   if(dailyTpReached) {
      Comment("Daily TP reached — trading paused until next day");
      return;
   }

   double Bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double Ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double emaValue = GetEMA();

   // Position/order tracking
   int    buyCount = 0, sellCount = 0;
   double buyLots = 0, sellLots = 0;
   double buyProfit = 0, sellProfit = 0;
   double buyWeightedPrice = 0, sellWeightedPrice = 0;
   double buyHighPrice = 0, buyLowPrice = 0;
   double sellHighPrice = 0, sellLowPrice = 0;

   // Scan open positions
   for(int i = 0; i < PositionsTotal(); i++) {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if(PositionGetInteger(POSITION_MAGIC) != MagicNumber) continue;

      ENUM_POSITION_TYPE ptype = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
      double lots     = PositionGetDouble(POSITION_VOLUME);
      double openPrice = NormalizeDouble(PositionGetDouble(POSITION_PRICE_OPEN), _Digits);
      double posProfit = PositionGetDouble(POSITION_PROFIT);

      if(ptype == POSITION_TYPE_BUY) {
         buyCount++;
         buyLots += lots;
         buyWeightedPrice += openPrice * lots;
         if(buyHighPrice < openPrice || buyHighPrice == 0.0) buyHighPrice = openPrice;
         if(buyLowPrice > openPrice || buyLowPrice == 0.0) buyLowPrice = openPrice;
         buyProfit += posProfit;
      } else if(ptype == POSITION_TYPE_SELL) {
         sellCount++;
         sellLots += lots;
         sellWeightedPrice += openPrice * lots;
         if(sellLowPrice > openPrice || sellLowPrice == 0.0) sellLowPrice = openPrice;
         if(sellHighPrice < openPrice || sellHighPrice == 0.0) sellHighPrice = openPrice;
         sellProfit += posProfit;
      }
   }

   // Average prices & markers
   double buyAvgPrice = 0, sellAvgPrice = 0;
   ObjectDelete(0, "SLb");
   ObjectDelete(0, "SLs");
   if(buyCount > 0) {
      buyAvgPrice = NormalizeDouble(buyWeightedPrice / buyLots, _Digits);
      DrawArrow("SLb", buyAvgPrice, ARROW_RIGHT_PRICE, clrBlue);
   }
   if(sellCount > 0) {
      sellAvgPrice = NormalizeDouble(sellWeightedPrice / sellLots, _Digits);
      DrawArrow("SLs", sellAvgPrice, ARROW_RIGHT_PRICE, clrRed);
   }

   // Set TP from BE for buy series
   if(buyCount > 0 && TpFromBEPips > 0) {
      double buyBE = buyAvgPrice;
      double buyTP = NormalizeDouble(buyBE + ScaledPips(TpFromBEPips), _Digits);
      for(int i = 0; i < PositionsTotal(); i++) {
         ulong ticket = PositionGetTicket(i);
         if(ticket == 0) continue;
         if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
         if(PositionGetInteger(POSITION_MAGIC) != MagicNumber) continue;
         if((ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE) != POSITION_TYPE_BUY) continue;
         double currentTP = NormalizeDouble(PositionGetDouble(POSITION_TP), _Digits);
         if(currentTP != buyTP)
            trade.PositionModify(ticket, PositionGetDouble(POSITION_SL), buyTP);
      }
   }

   // Set TP from BE for sell series
   if(sellCount > 0 && TpFromBEPips > 0) {
      double sellBE = sellAvgPrice;
      double sellTP = NormalizeDouble(sellBE - ScaledPips(TpFromBEPips), _Digits);
      for(int i = 0; i < PositionsTotal(); i++) {
         ulong ticket = PositionGetTicket(i);
         if(ticket == 0) continue;
         if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
         if(PositionGetInteger(POSITION_MAGIC) != MagicNumber) continue;
         if((ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE) != POSITION_TYPE_SELL) continue;
         double currentTP = NormalizeDouble(PositionGetDouble(POSITION_TP), _Digits);
         if(currentTP != sellTP)
            trade.PositionModify(ticket, PositionGetDouble(POSITION_SL), sellTP);
      }
   }

   // Trailing stop logic
   if(TrailingType != 0) {
      for(int i = 0; i < PositionsTotal(); i++) {
         ulong ticket = PositionGetTicket(i);
         if(ticket == 0) continue;
         if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
         if(PositionGetInteger(POSITION_MAGIC) != MagicNumber) continue;

         ENUM_POSITION_TYPE ptype = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
         double sl  = NormalizeDouble(PositionGetDouble(POSITION_SL), _Digits);

         if(ptype == POSITION_TYPE_BUY) {
            double level = CalcTrailingLevel(1, Bid, TrailingType);
            if(level >= buyAvgPrice + ScaledPips(MinTrailingProfit) &&
               level > sl + ScaledPips(TrailingStepPips) &&
               Bid - level > stopsLevelPoints * pip.Point()) {
               if(level > sl)
                  trade.PositionModify(ticket, level, PositionGetDouble(POSITION_TP));
            }
         } else if(ptype == POSITION_TYPE_SELL) {
            double level = CalcTrailingLevel(-1, Ask, TrailingType);
            if((level <= sellAvgPrice - ScaledPips(MinTrailingProfit) &&
                level < sl - ScaledPips(TrailingStepPips)) ||
               (sl == 0.0 && level - Ask > stopsLevelPoints * pip.Point())) {
               if(level < sl || (sl == 0.0 && level != 0.0))
                  trade.PositionModify(ticket, level, PositionGetDouble(POSITION_TP));
            }
         }
      }
   }

   // Close-all on profit target ($)
   double totalProfit = buyProfit + sellProfit;
   if(CloseAllProfit > 0 && totalProfit >= CloseAllProfit) {
      Print("Close ALL on profit target: ", totalProfit);
      ClosePositionsByDirection(0);
      if(dailyClosedProfit >= DailyTpTarget && DailyTpTarget > 0) {
         dailyTpReached = true;
         Print("Daily TP target reached: ", dailyClosedProfit);
      }
      return;
   }

   // Check daily TP after close-all
   if(dailyClosedProfit >= DailyTpTarget && DailyTpTarget > 0) {
      dailyTpReached = true;
      Print("Daily TP target reached: ", dailyClosedProfit);
      return;
   }

   // Hedge trimming
   if(EnableTrimFarthest) {
      if(buyCount >= 2) TrimPair(1, true);
      if(sellCount >= 2) TrimPair(-1, true);
   }
   if(EnableTrimMostLoss) {
      if(buyCount >= 2) TrimPair(1, false);
      if(sellCount >= 2) TrimPair(-1, false);
   }

   // AP-9: Same-bar guard
   long currentBars = Bars(_Symbol, _Period);
   bool isNewBar = (currentBars != lastBarCount);
   if(isNewBar) lastBarCount = currentBars;

   // AP-8: Spread guard
   bool spreadOK = spreadGuard.IsTradable();
   bool riskOK = riskGuard.CanOpenNewPosition();

   // EMA range entry logic
   double emaUpper = emaValue + pip.Pips(EmaRangePoints);
   double emaLower = emaValue - pip.Pips(EmaRangePoints);
   bool priceAboveRange = (Bid > emaUpper);
   bool priceBelowRange = (Ask < emaLower);

   // Draw EMA range lines
   DrawArrow("EMA_Upper", emaUpper, 4, clrYellow);
   DrawArrow("EMA_Lower", emaLower, 4, clrYellow);
   DrawArrow("EMA_Line", emaValue, 4, clrAqua);

   // DCA: open BUY when price below EMA - range
   if(AllowBuy && spreadOK && riskOK && isNewBar && !dailyTpReached) {
      if(buyCount == 0) {
         if(priceBelowRange && EAMakesFirstOrder) {
            double lot = CalcNextLot(0);
            double margin = 0;
            if(OrderCalcMargin(ORDER_TYPE_BUY, _Symbol, lot, Ask, margin) && margin > 0) {
               if(margin <= AccountInfoDouble(ACCOUNT_MARGIN_FREE)) {
                  if(IsTradingHours()) {
                     double buySL = CalcProtectiveSL(1, Ask);
                     if(!trade.Buy(lot, _Symbol, Ask, buySL, 0, "ThanosEA Buy"))
                        PrintFormat("Failed Buy: Lot=%.2f Ask=%.5f", lot, Ask);
                  }
               }
            }
         }
      } else {
         double lastBuyPrice = buyLowPrice;
         if(Ask <= NormalizeDouble(lastBuyPrice - ScaledPips(DcaStepPips), _Digits)) {
            double lot = CalcNextLot(buyCount);
            double margin = 0;
            if(OrderCalcMargin(ORDER_TYPE_BUY, _Symbol, lot, Ask, margin) && margin > 0) {
               if(margin <= AccountInfoDouble(ACCOUNT_MARGIN_FREE)) {
                  if(IsTradingHours()) {
                     double dcaBuySL = CalcProtectiveSL(1, Ask);
                     if(!trade.Buy(lot, _Symbol, Ask, dcaBuySL, 0, "ThanosEA DCA Buy"))
                        PrintFormat("Failed DCA Buy #%d: Lot=%.2f Ask=%.5f", buyCount + 1, lot, Ask);
                  }
               }
            }
         }
      }
   }

   // DCA: open SELL when price above EMA + range
   if(AllowSell && spreadOK && riskOK && isNewBar && !dailyTpReached) {
      if(sellCount == 0) {
         if(priceAboveRange && EAMakesFirstOrder) {
            double lot = CalcNextLot(0);
            double margin = 0;
            if(OrderCalcMargin(ORDER_TYPE_SELL, _Symbol, lot, Bid, margin) && margin > 0) {
               if(margin <= AccountInfoDouble(ACCOUNT_MARGIN_FREE)) {
                  if(IsTradingHours()) {
                     double sellSL = CalcProtectiveSL(-1, Bid);
                     if(!trade.Sell(lot, _Symbol, Bid, sellSL, 0, "ThanosEA Sell"))
                        PrintFormat("Failed Sell: Lot=%.2f Bid=%.5f", lot, Bid);
                  }
               }
            }
         }
      } else {
         double lastSellPrice = sellHighPrice;
         if(Bid >= NormalizeDouble(lastSellPrice + ScaledPips(DcaStepPips), _Digits)) {
            double lot = CalcNextLot(sellCount);
            double margin = 0;
            if(OrderCalcMargin(ORDER_TYPE_SELL, _Symbol, lot, Bid, margin) && margin > 0) {
               if(margin <= AccountInfoDouble(ACCOUNT_MARGIN_FREE)) {
                  if(IsTradingHours()) {
                     double dcaSellSL = CalcProtectiveSL(-1, Bid);
                     if(!trade.Sell(lot, _Symbol, Bid, dcaSellSL, 0, "ThanosEA DCA Sell"))
                        PrintFormat("Failed DCA Sell #%d: Lot=%.2f Bid=%.5f", sellCount + 1, lot, Bid);
                  }
               }
            }
         }
      }
   }

   // Update info labels
   SetChartLabel("Balance",    StringFormat("Balance %.2f", AccountInfoDouble(ACCOUNT_BALANCE)), 5, 0, InfoColor);
   SetChartLabel("Equity",     StringFormat("Equity %.2f", AccountInfoDouble(ACCOUNT_EQUITY)), 5, 0, InfoColor);
   SetChartLabel("FreeMargin", StringFormat("Free Margin %.2f", AccountInfoDouble(ACCOUNT_MARGIN_FREE)), 5, 0, InfoColor);

   if(buyLots > 0.0)
      SetChartLabel("ProfitB", StringFormat("Buy %d  Profit %.2f  Lot=%.2f  BE=%.5f", buyCount, buyProfit, buyLots, buyAvgPrice), 5, 0,
                    buyProfit > 0 ? clrLime : clrRed);
   else
      SetChartLabel("ProfitB", "", 5, 0, clrGray);

   if(sellLots > 0.0)
      SetChartLabel("ProfitS", StringFormat("Sell %d  Profit %.2f  Lot=%.2f  BE=%.5f", sellCount, sellProfit, sellLots, sellAvgPrice), 5, 0,
                    sellProfit > 0 ? clrLime : clrRed);
   else
      SetChartLabel("ProfitS", "", 5, 0, clrGray);

   if(buyLots + sellLots > 0.0)
      SetChartLabel("Profit", StringFormat("Profit All %.2f", totalProfit), 5, 0,
                    totalProfit >= 0 ? clrGreen : clrRed);
   else
      SetChartLabel("Profit", "", 5, 0, clrGray);

   if(emaValue > 0)
      SetChartLabel("EMAInfo", StringFormat("EMA(%d)=%.5f Range: %.5f - %.5f [scale:%d]",
                 EmaPeriod, emaValue, emaLower, emaUpper, pipScale), 5, 0, clrAqua);

   SetChartLabel("DailyPL", StringFormat("Daily P/L: %.2f / %.2f%s",
                 dailyClosedProfit, DailyTpTarget,
                 dailyTpReached ? " [PAUSED]" : ""), 5, 0,
                 dailyTpReached ? clrOrange : InfoColor);
}
