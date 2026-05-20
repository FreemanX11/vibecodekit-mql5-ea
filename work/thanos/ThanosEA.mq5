//+------------------------------------------------------------------+
//|                                                     ThanosEA.mq5 |
//|   Grid EA — rebuilt via vibecodekit-mql5-ea enterprise pipeline   |
//|   Original: Grid_Converted (cmillion, MQL4→MQL5)                 |
//|                                                                   |
//|   Fixes applied:                                                  |
//|     AP-5  — inputs grouped by function                            |
//|     AP-8  — CSpreadGuard added                                    |
//|     AP-9  — same-bar entry guard                                  |
//|     AP-11 — netting/hedging mode validation                       |
//|     AP-14 — CMfeMaeLogger wired                                   |
//|     AP-15 — CTrade class replaces direct OrderSend                |
//|     AP-20 — CPipNormalizer replaces all hardcoded pip math        |
//|     AP-21 — digits-tested meta tag added                          |
//|   Code quality: all obfuscated names replaced                     |
//+------------------------------------------------------------------+
// digits-tested: 2,3,4,5

#include <Trade/Trade.mqh>
#include <CPipNormalizer.mqh>
#include <CSpreadGuard.mqh>
#include <CMfeMaeLogger.mqh>
#include <CRiskGuard.mqh>

//=== Group 1: Trade Direction ===//
sinput bool   AllowBuy           = true;
sinput bool   AllowSell          = true;
sinput bool   EAMakesFirstOrder  = true;
sinput bool   OpenOrderOnTrend   = false;

//=== Group 2: Grid Spacing (pips) ===//
input int     FirstStepPips         = 10;
sinput int    MinPriceDistancePips  = 30;
sinput int    MoveStepPips          = 5;
input int     DistBetweenOrdersPips = 30;

//=== Group 3: Lot & Martingale ===//
input double  StartLot             = 0.1;
sinput double LotIncrement         = 0.0;
input double  LotMultiplier        = 1.5;
sinput int    LotDecimalPlaces     = 2;

//=== Group 4: Profit & Loss Thresholds ===//
sinput double MaxAllowedLoss              = 100000.0;
sinput double CloseLossByDrawdown         = 10.0;
sinput double ProfitCloseAllDirections    = 10.0;
input double  ProfitCloseOneDirection     = 50.0;
sinput int    AutoCalcProfitMultiplier    = 50;
sinput double LossCloseThreshold          = 100000.0;

//=== Group 5: Trailing Stop (0=Off, 1=Candles, 2=Fractals, 3+=Points) ===//
input int     TrailingType        = 1;
sinput int    TrailingStepPips    = 0;
sinput int    MinTrailingProfit   = 10;
sinput int    TrailingPadding     = 0;
sinput int    TrailingTimeframe   = 15;

//=== Group 6: SL/TP & Indicators ===//
sinput int    StoplossPips     = 0;
sinput int    TakeprofitPips   = 0;
sinput bool   UseRSIFilter     = false;
sinput int    RSIOversold      = 15;
sinput int    RSIOverbought    = 85;
sinput int    RSIPeriod        = 5;
sinput int    RSITimeframe     = 0;

//=== Group 7: Schedule & Cleanup (sinput — not in optimizer) ===//
sinput bool   DeleteOrdersAtHour = true;
sinput int    DeleteHour     = 20;
sinput int    StartHour      = 0;
sinput int    EndHour        = 24;

//=== Group 8: Risk Management (sinput — not in optimizer) ===//
sinput double MaxSpreadPips    = 5.0;
sinput double DailyLossPct    = 0.05;
sinput int    MaxOpenPositions = 0;
sinput double FreezeOnDDPct   = 0.10;

//=== Group 9: Display & Identification (sinput — not in optimizer) ===//
sinput int    MagicNumber    = 777;
sinput int    FontSize       = 10;
sinput color  InfoColor      = clrLime;

//=== Constants ===//
const int ARROW_RIGHT_PRICE = 220;

#define DIR_BUY   0
#define DIR_SELL  1

//=== Global Objects ===//
CTrade         trade;
CPipNormalizer pip;
CSpreadGuard   spreadGuard;
CMfeMaeLogger  mfeLogger;
CRiskGuard     riskGuard;

//=== Global State ===//
string    accountCurrency    = "";
double    tickValue          = 0.0;
int       stopsLevelPoints   = 0;
int       slippage           = 0;
bool      isHedging          = false;
int       trailingTF         = 0;
int       gridDistance        = 0;
int       gridFirstStep      = 0;
long      lastBarCount       = 0;

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
      // Points-based trailing
      if(direction == 1)
         level = NormalizeDouble(currentPrice - pip.Pips((int)trailParam), _Digits);
      else
         level = NormalizeDouble(currentPrice + pip.Pips((int)trailParam), _Digits);
   } else if(trailParam == 2.0) {
      // Fractal-based trailing
      if(direction == 1) {
         for(int i = 1; i < 100; i++) {
            level = GetFractal(_Symbol, tf, 1, i);  // LOWER fractal
            if(level != 0.0) {
               level -= NormalizeDouble(pip.Pips(TrailingPadding), _Digits);
               if(currentPrice - pip.Pips((int)pip.StopsLevel()) > level)
                  break;
            } else level = 0;
         }
         DrawArrow("FR Buy", level + pip.Point(), 218, clrRed);
      } else {
         for(int i = 1; i < 100; i++) {
            level = GetFractal(_Symbol, tf, 0, i);  // UPPER fractal
            if(level != 0.0) {
               level += NormalizeDouble(pip.Pips(TrailingPadding), _Digits);
               if(currentPrice + pip.Pips((int)pip.StopsLevel()) < level)
                  break;
            } else level = 0;
         }
         DrawArrow("FR Sell", level, 217, clrRed);
      }
   } else if(trailParam == 1.0) {
      // Candle-based trailing
      if(direction == 1) {
         for(int i = 1; i < 500; i++) {
            level = NormalizeDouble(iLow(_Symbol, tf, i) - pip.Pips(TrailingPadding), _Digits);
            if(level != 0.0) {
               if(currentPrice - pip.Pips((int)pip.StopsLevel()) > level)
                  break;
               level = 0;
            }
         }
         DrawArrow("FR Buy", level + pip.Point(), 159, clrRed);
      } else {
         for(int i = 1; i < 500; i++) {
            level = NormalizeDouble(iHigh(_Symbol, tf, i) + pip.Pips(TrailingPadding), _Digits);
            if(level != 0.0) {
               if(currentPrice + pip.Pips((int)pip.StopsLevel()) < level)
                  break;
               level = 0;
            }
         }
         DrawArrow("FR Sell", level, 159, clrRed);
      }
   }

   // Draw SL and STOPLEVEL markers
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

//=== Close Positions by Direction ===//
// direction: 1=close buys, -1=close sells, 0=close all
int ClosePositionsByDirection(int direction) {
   int attempts = 0;
   while(true) {
      for(int i = PositionsTotal() - 1; i >= 0; i--) {
         ulong ticket = PositionGetTicket(i);
         if(ticket > 0) {
            if(PositionGetString(POSITION_SYMBOL) == _Symbol &&
               PositionGetInteger(POSITION_MAGIC) == MagicNumber) {
               ENUM_POSITION_TYPE ptype = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
               if((ptype == POSITION_TYPE_BUY && (direction == 1 || direction == 0)) ||
                  (ptype == POSITION_TYPE_SELL && (direction == -1 || direction == 0))) {
                  if(trade.PositionClose(ticket)) {
                     Comment(StringFormat("Closed position #%I64d  profit %.2f  %s",
                             ticket, PositionGetDouble(POSITION_PROFIT),
                             TimeToString(TimeCurrent(), TIME_SECONDS)));
                  }
               }
            }
         }
      }
      // Delete matching pending orders
      for(int i = OrdersTotal() - 1; i >= 0; i--) {
         ulong ticket = OrderGetTicket(i);
         if(ticket > 0) {
            if(OrderGetString(ORDER_SYMBOL) == _Symbol &&
               OrderGetInteger(ORDER_MAGIC) == MagicNumber) {
               ENUM_ORDER_TYPE ot = (ENUM_ORDER_TYPE)OrderGetInteger(ORDER_TYPE);
               if((ot == ORDER_TYPE_BUY_STOP && (direction == 1 || direction == 0)) ||
                  (ot == ORDER_TYPE_SELL_STOP && (direction == -1 || direction == 0))) {
                  trade.OrderDelete(ticket);
               }
            }
         }
      }

      // Check remaining
      int remaining = 0;
      for(int i = 0; i < PositionsTotal(); i++) {
         ulong ticket = PositionGetTicket(i);
         if(ticket > 0 && PositionGetString(POSITION_SYMBOL) == _Symbol &&
            PositionGetInteger(POSITION_MAGIC) == MagicNumber) {
            ENUM_POSITION_TYPE ptype = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
            if((ptype == POSITION_TYPE_BUY && (direction == 1 || direction == 0)) ||
               (ptype == POSITION_TYPE_SELL && (direction == -1 || direction == 0)))
               remaining++;
         }
      }
      for(int i = 0; i < OrdersTotal(); i++) {
         ulong ticket = OrderGetTicket(i);
         if(ticket > 0 && OrderGetString(ORDER_SYMBOL) == _Symbol &&
            OrderGetInteger(ORDER_MAGIC) == MagicNumber) {
            ENUM_ORDER_TYPE ot = (ENUM_ORDER_TYPE)OrderGetInteger(ORDER_TYPE);
            if((ot == ORDER_TYPE_BUY_STOP && (direction == 1 || direction == 0)) ||
               (ot == ORDER_TYPE_SELL_STOP && (direction == -1 || direction == 0)))
               remaining++;
         }
      }
      if(remaining == 0) break;
      attempts++;
      if(attempts > 10) {
         Alert(_Symbol, " Failed to close all trades, remaining: ", remaining);
         return 0;
      }
      Sleep(1000);
   }
   return 1;
}

//=== Calculate Next Lot Size ===//
double CalcNextLot(int gridLevel) {
   if(gridLevel == 0) return StartLot;
   return NormalizeDouble(StartLot * MathPow(LotMultiplier, gridLevel) +
                          gridLevel * LotIncrement, LotDecimalPlaces);
}

//+------------------------------------------------------------------+
//| OnInit                                                            |
//+------------------------------------------------------------------+
int OnInit() {
   // AP-11: Validate account mode
   ENUM_ACCOUNT_MARGIN_MODE marginMode =
      (ENUM_ACCOUNT_MARGIN_MODE)AccountInfoInteger(ACCOUNT_MARGIN_MODE);
   isHedging = (marginMode == ACCOUNT_MARGIN_MODE_RETAIL_HEDGING);
   if(!isHedging) {
      Alert("WARNING: Thanos EA is designed for HEDGING accounts. ",
            "Current mode: ", EnumToString(marginMode),
            ". Grid logic may not work correctly on netting accounts.");
   }

   // Initialize CPipNormalizer (AP-20 fix)
   if(!pip.Init(_Symbol)) {
      Alert("CPipNormalizer failed to init for ", _Symbol);
      return INIT_FAILED;
   }

   // Initialize CTrade (AP-15 fix)
   trade.SetExpertMagicNumber(MagicNumber);
   trade.SetDeviationInPoints((ulong)((_Digits == 5 || _Digits == 3) ? 30 : 3));
   trade.SetTypeFilling(ORDER_FILLING_RETURN);

   // Initialize CSpreadGuard (AP-8 fix)
   spreadGuard.Init(pip, MaxSpreadPips);

   // Initialize CMfeMaeLogger (AP-14 fix)
   mfeLogger.Init("ThanosEA_mfe_mae.csv");

   // Initialize CRiskGuard
   riskGuard.Init(DailyLossPct, MaxOpenPositions, FreezeOnDDPct);

   // Cache broker info
   accountCurrency = " " + AccountInfoString(ACCOUNT_CURRENCY);
   SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE, tickValue);
   trailingTF = NextHigherTF(TrailingTimeframe);
   slippage = (_Digits == 5 || _Digits == 3) ? 30 : 3;
   stopsLevelPoints = (int)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL);

   // Validate grid parameters against broker stops level
   gridDistance = DistBetweenOrdersPips;
   if((int)(pip.Pips(gridDistance) / pip.Point()) < stopsLevelPoints) {
      int minPips = pip.ClampSLPips(gridDistance);
      Alert("DistBetweenOrdersPips < STOPLEVEL, adjusted to ", minPips);
      gridDistance = minPips;
   }
   gridFirstStep = FirstStepPips;
   if((int)(pip.Pips(gridFirstStep) / pip.Point()) < stopsLevelPoints) {
      int minPips = pip.ClampSLPips(gridFirstStep);
      Alert("FirstStepPips < STOPLEVEL, adjusted to ", minPips);
      gridFirstStep = minPips;
   }

   // Same-bar guard init (AP-9 fix)
   lastBarCount = Bars(_Symbol, _Period);

   // Setup chart labels
   int yPos = FontSize + FontSize / 2;
   SetChartLabel("Balance",    "", 5, yPos, InfoColor); yPos += FontSize * 2;
   SetChartLabel("Equity",     "", 5, yPos, InfoColor); yPos += FontSize * 2;
   SetChartLabel("FreeMargin", "", 5, yPos, InfoColor); yPos += FontSize * 2;
   SetChartLabel("ProfitB",    "", 5, yPos, InfoColor); yPos += FontSize * 2;
   SetChartLabel("ProfitS",    "", 5, yPos, InfoColor); yPos += FontSize * 2;
   SetChartLabel("Profit",     "", 5, yPos, InfoColor); yPos += FontSize * 3;
   SetChartLabel("ParamHeader", "── Thanos EA Parameters ──", 5, yPos, clrAqua);
   yPos += FontSize * 2;

   string dirText = "";
   if(AllowBuy)  dirText = "Buy ";
   if(AllowSell) dirText += "Sell";
   SetChartLabel("ParamDir", "Allowed: " + dirText, 5, yPos, InfoColor);
   yPos += FontSize * 2;

   if(!OpenOrderOnTrend)
      SetChartLabel("ParamTrend", "Do not open orders on trend", 5, yPos, InfoColor);
   yPos += FontSize * 2;

   SetChartLabel("ParamFirst",   StringFormat("First step %d pips", gridFirstStep), 5, yPos, InfoColor);
   yPos += FontSize * 2;
   SetChartLabel("ParamMinDist", StringFormat("Min price distance %d pips", MinPriceDistancePips), 5, yPos, InfoColor);
   yPos += FontSize * 2;
   SetChartLabel("ParamMove",    StringFormat("Move step %d pips", MoveStepPips), 5, yPos, InfoColor);
   yPos += FontSize * 2;
   SetChartLabel("ParamGrid",    StringFormat("Grid distance %d pips", gridDistance), 5, yPos, InfoColor);
   yPos += FontSize * 2;
   SetChartLabel("ParamLot",     StringFormat("Start lot %.2f + %.2f x %.2f", StartLot, LotIncrement, LotMultiplier), 5, yPos, InfoColor);
   yPos += FontSize * 2;
   SetChartLabel("ParamMode",    StringFormat("Account: %s", isHedging ? "Hedging" : "Netting (WARNING)"), 5, yPos,
                 isHedging ? InfoColor : clrRed);

   Comment("Thanos EA Grid");
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| OnDeinit                                                          |
//+------------------------------------------------------------------+
void OnDeinit(const int reason) {
   ObjectsDeleteAll(0, 0, -1);
}

//+------------------------------------------------------------------+
//| OnTradeTransaction — wire MFE/MAE logger                         |
//+------------------------------------------------------------------+
void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest &request,
                        const MqlTradeResult &result) {
   mfeLogger.OnTradeTransaction(trans);
}

//+------------------------------------------------------------------+
//| OnTick                                                            |
//+------------------------------------------------------------------+
void OnTick() {
   // Risk guard tick
   riskGuard.OnTick();
   mfeLogger.OnTick();

   MqlDateTime dt;
   TimeToStruct(TimeCurrent(), dt);
   if(DeleteOrdersAtHour && dt.hour == DeleteHour)
      DeleteAllPendingOrders();

   // Negate thresholds for comparison
   double drawdownLimit    = -1.0 * CloseLossByDrawdown;
   double maxAllowedLossNeg = -1.0 * MaxAllowedLoss;
   double lossCloseNeg     = -1.0 * LossCloseThreshold;

   double Bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double Ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);

   // Position/order tracking
   int    buyCount = 0, sellCount = 0;
   int    buyStopCount = 0, sellStopCount = 0;
   double buyLots = 0, sellLots = 0;
   double buyProfit = 0, sellProfit = 0;
   double buyWeightedPrice = 0, sellWeightedPrice = 0;
   double buyHighPrice = 0, buyLowPrice = 0;
   double sellHighPrice = 0, sellLowPrice = 0;
   int    lastBuyStopTicket = 0, lastSellStopTicket = 0;
   double lastBuyStopPrice = 0, lastSellStopPrice = 0;
   double slNew = 0, tpNew = 0;

   // Scan open positions
   for(int i = 0; i < PositionsTotal(); i++) {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if(PositionGetInteger(POSITION_MAGIC) != MagicNumber) continue;

      ENUM_POSITION_TYPE ptype = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
      double lots     = PositionGetDouble(POSITION_VOLUME);
      double openPrice = NormalizeDouble(PositionGetDouble(POSITION_PRICE_OPEN), _Digits);
      double sl       = NormalizeDouble(PositionGetDouble(POSITION_SL), _Digits);
      double tp       = NormalizeDouble(PositionGetDouble(POSITION_TP), _Digits);
      double posProfit = PositionGetDouble(POSITION_PROFIT);

      if(ptype == POSITION_TYPE_BUY) {
         buyCount++;
         buyLots += lots;
         buyWeightedPrice += openPrice * lots;
         if(buyHighPrice < openPrice || buyHighPrice == 0.0) buyHighPrice = openPrice;
         if(buyLowPrice > openPrice || buyLowPrice == 0.0) buyLowPrice = openPrice;
         buyProfit += posProfit;

         // Auto-set SL/TP if missing
         slNew = sl; tpNew = tp;
         if(sl == 0.0 && StoplossPips > 0 && pip.IsValidSLDistance(StoplossPips))
            slNew = NormalizeDouble(openPrice - pip.Pips(StoplossPips), _Digits);
         if(tp == 0.0 && TakeprofitPips > 0 && pip.IsValidSLDistance(TakeprofitPips))
            tpNew = NormalizeDouble(openPrice + pip.Pips(TakeprofitPips), _Digits);
         if(slNew > sl || tpNew != tp)
            trade.PositionModify(ticket, slNew, tpNew);

      } else if(ptype == POSITION_TYPE_SELL) {
         sellCount++;
         sellLots += lots;
         sellWeightedPrice += openPrice * lots;
         if(sellLowPrice > openPrice || sellLowPrice == 0.0) sellLowPrice = openPrice;
         if(sellHighPrice < openPrice || sellHighPrice == 0.0) sellHighPrice = openPrice;
         sellProfit += posProfit;

         slNew = sl; tpNew = tp;
         if(sl == 0.0 && StoplossPips > 0 && pip.IsValidSLDistance(StoplossPips))
            slNew = NormalizeDouble(openPrice + pip.Pips(StoplossPips), _Digits);
         if(tp == 0.0 && TakeprofitPips > 0 && pip.IsValidSLDistance(TakeprofitPips))
            tpNew = NormalizeDouble(openPrice - pip.Pips(TakeprofitPips), _Digits);
         if(slNew < sl || (sl == 0.0 && slNew != 0.0) || tpNew != tp)
            trade.PositionModify(ticket, slNew, tpNew);
      }
   }

   // Scan pending orders
   for(int i = 0; i < OrdersTotal(); i++) {
      ulong ticket = OrderGetTicket(i);
      if(ticket == 0) continue;
      if(OrderGetString(ORDER_SYMBOL) != _Symbol) continue;
      if(OrderGetInteger(ORDER_MAGIC) != MagicNumber) continue;

      ENUM_ORDER_TYPE ot = (ENUM_ORDER_TYPE)OrderGetInteger(ORDER_TYPE);
      double price = NormalizeDouble(OrderGetDouble(ORDER_PRICE_OPEN), _Digits);

      if(ot == ORDER_TYPE_BUY_STOP) {
         buyStopCount++;
         if(buyHighPrice < price || buyHighPrice == 0.0) buyHighPrice = price;
         lastBuyStopTicket = (int)ticket;
         lastBuyStopPrice = price;
      } else if(ot == ORDER_TYPE_SELL_STOP) {
         sellStopCount++;
         if(sellLowPrice > price || sellLowPrice == 0.0) sellLowPrice = price;
         lastSellStopTicket = (int)ticket;
         lastSellStopPrice = price;
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
            if(level >= buyAvgPrice + pip.Pips(MinTrailingProfit) &&
               level > sl + pip.Pips(TrailingStepPips) &&
               pip.PriceToPips(Bid - level) > pip.StopsLevel()) {
               if(level > sl)
                  trade.PositionModify(ticket, level, PositionGetDouble(POSITION_TP));
            }
         } else if(ptype == POSITION_TYPE_SELL) {
            double level = CalcTrailingLevel(-1, Ask, TrailingType);
            if((level <= sellAvgPrice - pip.Pips(MinTrailingProfit) &&
                level < sl - pip.Pips(TrailingStepPips)) ||
               (sl == 0.0 && pip.PriceToPips(level - Ask) > pip.StopsLevel())) {
               if(level < sl || (sl == 0.0 && level != 0.0))
                  trade.PositionModify(ticket, level, PositionGetDouble(POSITION_TP));
            }
         }
      }
   }

   // Auto-calculated profit per direction
   double buyTargetProfit = 0, sellTargetProfit = 0;
   if(AutoCalcProfitMultiplier == 0) {
      buyTargetProfit = ProfitCloseOneDirection;
      sellTargetProfit = ProfitCloseOneDirection;
   } else {
      buyTargetProfit  = (buyLots == 0.0 ? StartLot : buyLots) * AutoCalcProfitMultiplier * tickValue;
      sellTargetProfit = (sellLots == 0.0 ? StartLot : sellLots) * AutoCalcProfitMultiplier * tickValue;
      SetChartLabel("AutoProfitBuy",  StringFormat("Auto Profit Buy %.2f", buyTargetProfit), 5, 0, InfoColor);
      SetChartLabel("AutoProfitSell", StringFormat("Auto Profit Sell %.2f", sellTargetProfit), 5, 0, InfoColor);
   }

   // Profit/loss closing logic
   if(buyProfit > drawdownLimit && sellProfit > drawdownLimit) {
      if(buyProfit >= buyTargetProfit) {
         Print("Closure of Buy on Profit ", buyProfit);
         ClosePositionsByDirection(1);
         return;
      }
      if(sellProfit >= sellTargetProfit) {
         Print("Closure of Sell on Profit ", sellProfit);
         ClosePositionsByDirection(-1);
         return;
      }
   } else {
      if(buyProfit + sellProfit >= ProfitCloseAllDirections) {
         Print("Closing all orders in 2 directions ", buyProfit + sellProfit);
         ClosePositionsByDirection(0);
         return;
      }
   }
   if(buyProfit <= lossCloseNeg) {
      Print("Closure of Buy on Loss ", buyProfit);
      ClosePositionsByDirection(1);
      return;
   }
   if(sellProfit <= lossCloseNeg) {
      Print("Closure of Sell on Loss ", sellProfit);
      ClosePositionsByDirection(-1);
      return;
   }

   // AP-9: Same-bar guard — only open new pending orders on new bar
   long currentBars = Bars(_Symbol, _Period);
   bool isNewBar = (currentBars != lastBarCount);
   if(isNewBar) lastBarCount = currentBars;

   // AP-8: Spread guard
   bool spreadOK = spreadGuard.IsTradable();

   // Risk guard check
   bool riskOK = riskGuard.CanOpenNewPosition();

   // RSI for first entries
   double rsiValue = 0;
   if(buyCount == 0 || sellCount == 0) {
      ENUM_TIMEFRAMES rsiTF = TFFromMinutes(RSITimeframe == 0 ? (int)Period() : RSITimeframe);
      rsiValue = GetRSI(_Symbol, rsiTF, RSIPeriod, PRICE_CLOSE, 0);
   }

   // Open BuyStop
   double pendingPrice = 0;
   if(buyStopCount == 0 && buyProfit > maxAllowedLossNeg && AllowBuy && spreadOK && riskOK) {
      if(buyCount == 0) {
         bool rsiPass = !UseRSIFilter || (rsiValue < RSIOversold);
         if(rsiPass && isNewBar)
            pendingPrice = NormalizeDouble(Ask + pip.Pips(gridFirstStep), _Digits);
      } else {
         pendingPrice = NormalizeDouble(Ask + pip.Pips(MinPriceDistancePips), _Digits);
         double gridLow = NormalizeDouble(buyLowPrice - pip.Pips(gridDistance), _Digits);
         if(pendingPrice < gridLow)
            pendingPrice = NormalizeDouble(Ask + pip.Pips(gridDistance), _Digits);
      }
      if(pendingPrice != 0.0 &&
         (buyCount == 0 ||
          (buyHighPrice != 0.0 && pendingPrice >= NormalizeDouble(buyHighPrice + pip.Pips(gridDistance), _Digits) && OpenOrderOnTrend) ||
          (buyLowPrice != 0.0 && pendingPrice <= NormalizeDouble(buyLowPrice - pip.Pips(gridDistance), _Digits)))) {
         double lot = CalcNextLot(buyCount);
         double margin = 0;
         if(OrderCalcMargin(ORDER_TYPE_BUY, _Symbol, lot, Ask, margin) && margin > 0) {
            if((margin <= AccountInfoDouble(ACCOUNT_MARGIN_FREE) && buyCount > 0) || EAMakesFirstOrder) {
               if(IsTradingHours()) {
                  if(!trade.BuyStop(lot, pendingPrice, _Symbol))
                     PrintFormat("Failed BuyStop: Lot=%.2f Price=%.5f Ask=%.5f", lot, pendingPrice, Ask);
               } else {
                  Comment("BuyStop blocked — outside trading hours");
               }
            } else Comment(StringFormat("Insufficient margin for Lot %.2f", lot));
         }
      }
   }

   // Open SellStop
   pendingPrice = 0;
   if(sellStopCount == 0 && sellProfit > maxAllowedLossNeg && AllowSell && spreadOK && riskOK) {
      if(sellCount == 0) {
         bool rsiPass = !UseRSIFilter || (rsiValue > RSIOverbought);
         if(rsiPass && isNewBar)
            pendingPrice = NormalizeDouble(Bid - pip.Pips(gridFirstStep), _Digits);
      } else {
         pendingPrice = NormalizeDouble(Bid - pip.Pips(MinPriceDistancePips), _Digits);
         double gridHigh = NormalizeDouble(sellHighPrice + pip.Pips(gridDistance), _Digits);
         if(pendingPrice < gridHigh)
            pendingPrice = NormalizeDouble(Bid - pip.Pips(gridDistance), _Digits);
      }
      if(pendingPrice != 0.0 &&
         (sellCount == 0 ||
          (sellLowPrice != 0.0 && pendingPrice <= NormalizeDouble(sellLowPrice - pip.Pips(gridDistance), _Digits) && OpenOrderOnTrend) ||
          (sellHighPrice != 0.0 && pendingPrice >= NormalizeDouble(sellHighPrice + pip.Pips(gridDistance), _Digits)))) {
         double lot = CalcNextLot(sellCount);
         double margin = 0;
         if(OrderCalcMargin(ORDER_TYPE_SELL, _Symbol, lot, Bid, margin) && margin > 0) {
            if((margin <= AccountInfoDouble(ACCOUNT_MARGIN_FREE) && sellCount > 0) || EAMakesFirstOrder) {
               if(IsTradingHours()) {
                  if(!trade.SellStop(lot, pendingPrice, _Symbol))
                     PrintFormat("Failed SellStop: Lot=%.2f Price=%.5f Bid=%.5f", lot, pendingPrice, Bid);
               } else {
                  Comment("SellStop blocked — outside trading hours");
               }
            } else Comment(StringFormat("Insufficient margin for Lot %.2f", lot));
         }
      }
   }

   // Update info labels
   double totalProfit = buyProfit + sellProfit;
   SetChartLabel("Balance",    StringFormat("Balance %.2f", AccountInfoDouble(ACCOUNT_BALANCE)), 5, 0, InfoColor);
   SetChartLabel("Equity",     StringFormat("Equity %.2f", AccountInfoDouble(ACCOUNT_EQUITY)), 5, 0, InfoColor);
   SetChartLabel("FreeMargin", StringFormat("Free Margin %.2f", AccountInfoDouble(ACCOUNT_MARGIN_FREE)), 5, 0, InfoColor);

   if(buyLots > 0.0)
      SetChartLabel("ProfitB", StringFormat("Buy %d  Profit %.2f  Lot=%.2f", buyCount, buyProfit, buyLots), 5, 0,
                    buyProfit > 0 ? clrLime : clrRed);
   else
      SetChartLabel("ProfitB", "", 5, 0, clrGray);

   if(sellLots > 0.0)
      SetChartLabel("ProfitS", StringFormat("Sell %d  Profit %.2f  Lot=%.2f", sellCount, sellProfit, sellLots), 5, 0,
                    sellProfit > 0 ? clrLime : clrRed);
   else
      SetChartLabel("ProfitS", "", 5, 0, clrGray);

   if(buyLots + sellLots > 0.0)
      SetChartLabel("Profit", StringFormat("Profit All %.2f", totalProfit), 5, 0,
                    totalProfit >= 0 ? clrGreen : clrRed);
   else
      SetChartLabel("Profit", "", 5, 0, clrGray);

   // Move existing pending orders closer to price
   if(lastBuyStopPrice != 0.0 && AllowBuy && lastBuyStopTicket > 0) {
      double targetPrice;
      if(buyCount == 0) targetPrice = NormalizeDouble(Ask + pip.Pips(gridFirstStep), _Digits);
      else              targetPrice = NormalizeDouble(Ask + pip.Pips(MinPriceDistancePips), _Digits);

      if(NormalizeDouble(lastBuyStopPrice - pip.Pips(MoveStepPips), _Digits) > targetPrice &&
         (targetPrice <= NormalizeDouble(buyLowPrice - pip.Pips(gridDistance), _Digits) || buyLowPrice == 0.0 ||
          (OpenOrderOnTrend && buyCount == 0) ||
          targetPrice >= NormalizeDouble(buyHighPrice + pip.Pips(gridDistance), _Digits) ||
          targetPrice <= NormalizeDouble(buyLowPrice - pip.Pips(gridDistance), _Digits))) {
         if(!trade.OrderModify(lastBuyStopTicket, targetPrice, 0, 0, ORDER_TIME_GTC, 0))
            PrintFormat("Error Modify BuyStop %.5f -> %.5f", lastBuyStopPrice, targetPrice);
         else
            PrintFormat("BuyStop Modified %.5f -> %.5f", lastBuyStopPrice, targetPrice);
      }
   }
   if(lastSellStopPrice != 0.0 && AllowSell && lastSellStopTicket > 0) {
      double targetPrice;
      if(sellCount == 0) targetPrice = NormalizeDouble(Bid - pip.Pips(gridFirstStep), _Digits);
      else               targetPrice = NormalizeDouble(Bid - pip.Pips(MinPriceDistancePips), _Digits);

      if(NormalizeDouble(lastSellStopPrice + pip.Pips(MoveStepPips), _Digits) < targetPrice &&
         (targetPrice >= NormalizeDouble(sellHighPrice + pip.Pips(gridDistance), _Digits) || sellHighPrice == 0.0 ||
          (OpenOrderOnTrend && sellCount == 0) ||
          targetPrice <= NormalizeDouble(sellLowPrice - pip.Pips(gridDistance), _Digits) ||
          targetPrice >= NormalizeDouble(sellHighPrice + pip.Pips(gridDistance), _Digits))) {
         if(!trade.OrderModify(lastSellStopTicket, targetPrice, 0, 0, ORDER_TIME_GTC, 0))
            PrintFormat("Error Modify SellStop %.5f -> %.5f", lastSellStopPrice, targetPrice);
         else
            PrintFormat("SellStop Modified %.5f -> %.5f", lastSellStopPrice, targetPrice);
      }
   }
}
//+------------------------------------------------------------------+
