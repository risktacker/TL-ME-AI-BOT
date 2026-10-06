// TL-ME Trend Scalper
// Self-contained trend-following scalper for XAUUSD (works on Exness cent or
// standard MT5 symbols, e.g. XAUUSDc / XAUUSDm). Entries AND exits run inside
// the terminal: no Python round-trip in the trading path.
//
// Concept: follow the higher-timeframe trend, enter on every short pullback
// that resumes in the trend direction, take a small profit fast, get out.
// Adds extra positions only while the existing ones are already protected.
//
// Attach one instance to one XAUUSD chart (any chart timeframe).
#property strict
#property version   "1.00"

#include <Trade/Trade.mqh>

//--- identity
input long            InpMagic               = 261006;
input bool            InpDemoOrCentOnly      = false;   // true = refuse to run on real standard accounts

enum ENUM_TREND_MODE
  {
   TREND_EMA_PULLBACK=0,   // M15 EMA trend + M1 RSI pullback entry
   TREND_CANDLE_MOMENTUM=1 // last N signal candles same direction -> follow it
  };
input ENUM_TREND_MODE InpTrendMode           = TREND_EMA_PULLBACK;

//--- momentum mode
input int             InpMomentumCandles     = 2;       // consecutive same-direction candles
input double          InpMomentumMinBodyATR  = 0.3;     // each candle body at least this x ATR

//--- trend filter (higher timeframe, EMA mode)
input ENUM_TIMEFRAMES InpTrendTF             = PERIOD_M15;
input int             InpTrendEMA            = 50;
input int             InpTrendSlopeBars      = 3;       // EMA must be rising/falling over this many bars

//--- entry trigger (fast timeframe)
input ENUM_TIMEFRAMES InpSignalTF            = PERIOD_M1;
input int             InpFastEMA             = 20;
input int             InpRSIPeriod           = 7;
input double          InpRSIBuyLevel         = 40.0;    // in uptrend: RSI dips below, buy when it crosses back up
input double          InpRSISellLevel        = 60.0;    // in downtrend: RSI pops above, sell when it crosses back down

//--- exits (multiples of signal-TF ATR)
input int             InpATRPeriod           = 14;
input double          InpStopATR             = 1.5;
input double          InpTargetATR           = 1.0;
input double          InpBreakEvenATR        = 0.5;     // move SL to entry (+buffer) after this much profit
input double          InpTrailStartATR       = 0.7;
input double          InpTrailDistanceATR    = 0.5;
input int             InpMaxHoldMinutes      = 15;      // time exit: scalps don't become swings

//--- position sizing
input double          InpRiskPercent         = 2.0;      // % of equity risked per position at the stop
input double          InpFixedLots           = 0.0;     // >0 overrides risk sizing
input int             InpMaxPositions        = 3;       // stacked entries in the trend direction
input int             InpMinSecondsBetween   = 30;

//--- hard risk limits (the account protection)
input double          InpDailyLossPercent    = 0.0;     // 0 = off. Else stop for the day at -X% from day start
input double          InpBasketStopPercent   = 6.0;     // close everything if open loss reaches -X% of equity
input int             InpLossStreakPause     = 3;       // after N losses in a row... (0 = off)
input int             InpPauseMinutes        = 30;      // ...pause entries this long, then resume
input double          InpSpikeATR            = 3.0;     // skip entries if current candle range > X * ATR (0 = off)
input int             InpMaxTradesPerDay     = 0;       // 0 = unlimited
input int             InpMaxSpreadPoints     = 350;     // skip entries when spread is wider (symbol points)
input int             InpDeviationPoints     = 50;

//--- session (broker server time; Exness server = UTC)
input bool            InpUseSession          = false;
input int             InpSessionStartHour    = 12;      // 12:00 UTC = 14:00 CAT, before NY open
input int             InpSessionEndHour      = 17;      // 17:00 UTC = 19:00 CAT

CTrade   trade;
int      hTrendEMA=INVALID_HANDLE, hFastEMA=INVALID_HANDLE, hRSI=INVALID_HANDLE, hATR=INVALID_HANDLE;
datetime lastSignalBar=0;
datetime lastEntryTime=0;
int      dayKey=0;
double   dayStartEquity=0;
int      tradesToday=0;
bool     haltedToday=false;
int      lossStreak=0;
datetime pauseUntil=0;

//+------------------------------------------------------------------+
//| logging for the Python / Telegram layer                           |
//+------------------------------------------------------------------+
void LogEvent(const string kind,const string detail)
  {
   FolderCreate("TLME",FILE_COMMON);
   int h=FileOpen("TLME\\scalper_events.csv",
                  FILE_READ|FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON|FILE_SHARE_READ);
   if(h==INVALID_HANDLE)
      return;
   FileSeek(h,0,SEEK_END);
   FileWrite(h,TimeToString(TimeCurrent(),TIME_DATE|TIME_SECONDS),_Symbol,kind,detail,
             DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY),2));
   FileClose(h);
   Print("[TLME] ",kind," ",detail);
  }

//+------------------------------------------------------------------+
bool ReadBuffer(const int handle,const int buffer,const int count,double &out[])
  {
   ArraySetAsSeries(out,true);
   return CopyBuffer(handle,buffer,0,count,out)==count;
  }

int TodayKey()
  {
   MqlDateTime t;
   TimeToStruct(TimeCurrent(),t);
   return t.year*10000+t.mon*100+t.day;
  }

bool InSession()
  {
   if(!InpUseSession)
      return true;
   MqlDateTime t;
   TimeToStruct(TimeCurrent(),t);
   if(InpSessionStartHour<=InpSessionEndHour)
      return t.hour>=InpSessionStartHour && t.hour<InpSessionEndHour;
   return t.hour>=InpSessionStartHour || t.hour<InpSessionEndHour;   // wraps midnight
  }

//+------------------------------------------------------------------+
//| our positions                                                     |
//+------------------------------------------------------------------+
int CountPositions(int &dir,bool &allProtected,double &floating)
  {
   int n=0;
   dir=0;
   allProtected=true;
   floating=0;
   for(int i=PositionsTotal()-1;i>=0;i--)
     {
      ulong t=PositionGetTicket(i);
      if(t==0 || PositionGetString(POSITION_SYMBOL)!=_Symbol || PositionGetInteger(POSITION_MAGIC)!=InpMagic)
         continue;
      n++;
      long type=PositionGetInteger(POSITION_TYPE);
      dir=(type==POSITION_TYPE_BUY)?1:-1;
      floating+=PositionGetDouble(POSITION_PROFIT)+PositionGetDouble(POSITION_SWAP);
      double open=PositionGetDouble(POSITION_PRICE_OPEN);
      double sl=PositionGetDouble(POSITION_SL);
      bool prot=(type==POSITION_TYPE_BUY)?(sl>=open && sl>0):(sl>0 && sl<=open);
      if(!prot)
         allProtected=false;
     }
   return n;
  }

void CloseAll(const string reason)
  {
   for(int i=PositionsTotal()-1;i>=0;i--)
     {
      ulong t=PositionGetTicket(i);
      if(t==0 || PositionGetString(POSITION_SYMBOL)!=_Symbol || PositionGetInteger(POSITION_MAGIC)!=InpMagic)
         continue;
      if(!trade.PositionClose(t))
         LogEvent("CLOSE_FAIL",(string)t+" "+reason+" rc="+(string)trade.ResultRetcode());
     }
   LogEvent("CLOSE_ALL",reason);
  }

//+------------------------------------------------------------------+
//| sizing                                                            |
//+------------------------------------------------------------------+
double LotsForStop(const double stopDistance)
  {
   double minLot=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MIN);
   double maxLot=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MAX);
   double step  =SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_STEP);
   double lots;
   if(InpFixedLots>0)
      lots=InpFixedLots;
   else
     {
      double tickSize =SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_SIZE);
      double tickValue=SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_VALUE_LOSS);
      if(tickSize<=0 || tickValue<=0 || stopDistance<=0)
         return 0;
      double riskMoney=AccountInfoDouble(ACCOUNT_EQUITY)*InpRiskPercent/100.0;
      double lossPerLot=stopDistance/tickSize*tickValue;
      lots=riskMoney/lossPerLot;
     }
   lots=MathFloor(lots/step)*step;
   if(lots<minLot)
      return 0;                 // cannot fit the stop inside the risk budget -> skip, never force
   return MathMin(lots,maxLot);
  }

//+------------------------------------------------------------------+
//| trend + trigger                                                   |
//+------------------------------------------------------------------+
int TrendDirection()
  {
   double ema[];
   if(!ReadBuffer(hTrendEMA,0,InpTrendSlopeBars+2,ema))
      return 0;
   double close1=iClose(_Symbol,InpTrendTF,1);
   bool up  =close1>ema[1] && ema[1]>ema[1+InpTrendSlopeBars];
   bool down=close1<ema[1] && ema[1]<ema[1+InpTrendSlopeBars];
   return up?1:(down?-1:0);
  }

int EntrySignal(const int trend)
  {
   if(trend==0)
      return 0;
   double rsi[],fast[];
   if(!ReadBuffer(hRSI,0,3,rsi) || !ReadBuffer(hFastEMA,0,3,fast))
      return 0;
   double close1=iClose(_Symbol,InpSignalTF,1);
   if(trend>0 && rsi[2]<InpRSIBuyLevel && rsi[1]>=InpRSIBuyLevel && close1>fast[1])
      return 1;
   if(trend<0 && rsi[2]>InpRSISellLevel && rsi[1]<=InpRSISellLevel && close1<fast[1])
      return -1;
   return 0;
  }

int MomentumSignal(const double atr)
  {
   int n=MathMax(1,InpMomentumCandles);
   int dir=0;
   for(int i=1;i<=n;i++)
     {
      double o=iOpen(_Symbol,InpSignalTF,i), c=iClose(_Symbol,InpSignalTF,i);
      double body=c-o;
      if(MathAbs(body)<InpMomentumMinBodyATR*atr)
         return 0;
      int d=body>0?1:-1;
      if(dir==0) dir=d;
      else if(d!=dir) return 0;
     }
   return dir;
  }

int Signal(const double atr)
  {
   if(InpTrendMode==TREND_CANDLE_MOMENTUM)
      return MomentumSignal(atr);
   return EntrySignal(TrendDirection());
  }

//+------------------------------------------------------------------+
//| per-tick management: break-even, trailing, time exit              |
//+------------------------------------------------------------------+
void ManagePositions(const double atr)
  {
   double point=SymbolInfoDouble(_Symbol,SYMBOL_POINT);
   int    digits=(int)SymbolInfoInteger(_Symbol,SYMBOL_DIGITS);
   double spread=SymbolInfoDouble(_Symbol,SYMBOL_ASK)-SymbolInfoDouble(_Symbol,SYMBOL_BID);
   for(int i=PositionsTotal()-1;i>=0;i--)
     {
      ulong t=PositionGetTicket(i);
      if(t==0 || PositionGetString(POSITION_SYMBOL)!=_Symbol || PositionGetInteger(POSITION_MAGIC)!=InpMagic)
         continue;
      long   type=PositionGetInteger(POSITION_TYPE);
      double open=PositionGetDouble(POSITION_PRICE_OPEN);
      double sl  =PositionGetDouble(POSITION_SL);
      double tp  =PositionGetDouble(POSITION_TP);
      datetime opened=(datetime)PositionGetInteger(POSITION_TIME);

      if(InpMaxHoldMinutes>0 && TimeCurrent()-opened>=InpMaxHoldMinutes*60)
        {
         if(trade.PositionClose(t))
            LogEvent("TIME_EXIT",(string)t);
         continue;
        }
      if(atr<=0)
         continue;

      bool   isBuy=(type==POSITION_TYPE_BUY);
      double price=isBuy?SymbolInfoDouble(_Symbol,SYMBOL_BID):SymbolInfoDouble(_Symbol,SYMBOL_ASK);
      double profit=isBuy?price-open:open-price;
      double newSL=sl;

      if(profit>=InpBreakEvenATR*atr)
        {
         double be=isBuy?open+spread:open-spread;
         if(isBuy && (sl==0 || sl<be)) newSL=be;
         if(!isBuy && (sl==0 || sl>be)) newSL=be;
        }
      if(profit>=InpTrailStartATR*atr)
        {
         double trail=isBuy?price-InpTrailDistanceATR*atr:price+InpTrailDistanceATR*atr;
         if(isBuy && trail>newSL) newSL=trail;
         if(!isBuy && (newSL==0 || trail<newSL)) newSL=trail;
        }
      newSL=NormalizeDouble(newSL,digits);
      if(MathAbs(newSL-sl)>=MathMax(point,0.05*atr))   // avoid spamming the server every tick
         trade.PositionModify(t,newSL,tp);
     }
  }

//+------------------------------------------------------------------+
int OnInit()
  {
   if(InpDemoOrCentOnly)
     {
      bool demo=AccountInfoInteger(ACCOUNT_TRADE_MODE)==ACCOUNT_TRADE_MODE_DEMO;
      bool cent=StringFind(AccountInfoString(ACCOUNT_CURRENCY),"USC")>=0;
      if(!demo && !cent)
        {
         Print("[TLME] Refusing to start: InpDemoOrCentOnly=true and account is neither demo nor cent.");
         return INIT_FAILED;
        }
     }
   hTrendEMA=iMA(_Symbol,InpTrendTF,InpTrendEMA,0,MODE_EMA,PRICE_CLOSE);
   hFastEMA =iMA(_Symbol,InpSignalTF,InpFastEMA,0,MODE_EMA,PRICE_CLOSE);
   hRSI     =iRSI(_Symbol,InpSignalTF,InpRSIPeriod,PRICE_CLOSE);
   hATR     =iATR(_Symbol,InpSignalTF,InpATRPeriod);
   if(hTrendEMA==INVALID_HANDLE || hFastEMA==INVALID_HANDLE || hRSI==INVALID_HANDLE || hATR==INVALID_HANDLE)
      return INIT_FAILED;
   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(InpDeviationPoints);
   trade.SetTypeFillingBySymbol(_Symbol);
   dayKey=TodayKey();
   dayStartEquity=AccountInfoDouble(ACCOUNT_EQUITY);
   LogEvent("START","equity="+DoubleToString(dayStartEquity,2)+" currency="+AccountInfoString(ACCOUNT_CURRENCY));
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason)
  {
   IndicatorRelease(hTrendEMA);
   IndicatorRelease(hFastEMA);
   IndicatorRelease(hRSI);
   IndicatorRelease(hATR);
   LogEvent("STOP","reason="+(string)reason);
  }

//+------------------------------------------------------------------+
void OnTick()
  {
   //--- new day reset
   int today=TodayKey();
   if(today!=dayKey)
     {
      dayKey=today;
      dayStartEquity=AccountInfoDouble(ACCOUNT_EQUITY);
      tradesToday=0;
      haltedToday=false;
     }

   double atrBuf[];
   double atr=ReadBuffer(hATR,0,2,atrBuf)?atrBuf[1]:0;

   int dir; bool allProt; double floating;
   int open=CountPositions(dir,allProt,floating);
   double equity=AccountInfoDouble(ACCOUNT_EQUITY);

   //--- hard limits, checked every tick
   if(open>0 && floating<=-equity*InpBasketStopPercent/100.0)
     {
      CloseAll("basket stop "+DoubleToString(floating,2));
      return;
     }
   if(InpDailyLossPercent>0 && !haltedToday && equity<=dayStartEquity*(1.0-InpDailyLossPercent/100.0))
     {
      haltedToday=true;
      CloseAll("daily loss limit");
      return;
     }

   //--- exits run on every tick
   if(open>0)
      ManagePositions(atr);

   //--- entries: evaluated once per closed signal bar
   datetime bar=iTime(_Symbol,InpSignalTF,0);
   if(bar==lastSignalBar)
      return;
   lastSignalBar=bar;

   if(haltedToday || !InSession() || atr<=0 || TimeCurrent()<pauseUntil)
      return;
   if(InpMaxTradesPerDay>0 && tradesToday>=InpMaxTradesPerDay)
      return;
   if(InpSpikeATR>0)
     {
      double hi=iHigh(_Symbol,InpSignalTF,1), lo=iLow(_Symbol,InpSignalTF,1);
      if(hi-lo>InpSpikeATR*atr)
         return;               // news-like spike: stand aside
     }
   if(TimeCurrent()-lastEntryTime<InpMinSecondsBetween)
      return;
   if(SymbolInfoInteger(_Symbol,SYMBOL_SPREAD)>InpMaxSpreadPoints)
      return;

   int signal=Signal(atr);
   if(signal==0)
      return;
   if(open>0)
     {
      if(open>=InpMaxPositions || signal!=dir || !allProt)
         return;               // stack only with the trend, only when existing trades are protected
     }

   double stopDist=InpStopATR*atr;
   double lots=LotsForStop(stopDist);
   if(lots<=0)
     {
      LogEvent("SKIP","stop too wide for risk budget atr="+DoubleToString(atr,2));
      return;
     }
   int    digits=(int)SymbolInfoInteger(_Symbol,SYMBOL_DIGITS);
   double ask=SymbolInfoDouble(_Symbol,SYMBOL_ASK);
   double bid=SymbolInfoDouble(_Symbol,SYMBOL_BID);
   bool ok;
   if(signal>0)
      ok=trade.Buy(lots,_Symbol,ask,NormalizeDouble(ask-stopDist,digits),
                   NormalizeDouble(ask+InpTargetATR*atr,digits),"TLME");
   else
      ok=trade.Sell(lots,_Symbol,bid,NormalizeDouble(bid+stopDist,digits),
                    NormalizeDouble(bid-InpTargetATR*atr,digits),"TLME");
   if(ok && (trade.ResultRetcode()==TRADE_RETCODE_DONE || trade.ResultRetcode()==TRADE_RETCODE_PLACED))
     {
      tradesToday++;
      lastEntryTime=TimeCurrent();
      LogEvent(signal>0?"BUY":"SELL","lots="+DoubleToString(lots,2)+" atr="+DoubleToString(atr,2)
               +" stack="+(string)(open+1));
     }
   else
      LogEvent("ORDER_FAIL","rc="+(string)trade.ResultRetcode()+" "+trade.ResultRetcodeDescription());
  }

//+------------------------------------------------------------------+
void OnTradeTransaction(const MqlTradeTransaction &trans,const MqlTradeRequest &req,const MqlTradeResult &res)
  {
   if(trans.type!=TRADE_TRANSACTION_DEAL_ADD)
      return;
   if(!HistoryDealSelect(trans.deal))
      return;
   if(HistoryDealGetInteger(trans.deal,DEAL_MAGIC)!=InpMagic)
      return;
   if(HistoryDealGetInteger(trans.deal,DEAL_ENTRY)!=DEAL_ENTRY_OUT)
      return;
   double pnl=HistoryDealGetDouble(trans.deal,DEAL_PROFIT)+HistoryDealGetDouble(trans.deal,DEAL_COMMISSION)
              +HistoryDealGetDouble(trans.deal,DEAL_SWAP);
   LogEvent("CLOSED","deal="+(string)trans.deal+" pnl="+DoubleToString(pnl,2));
   if(pnl<0) lossStreak++; else lossStreak=0;
   if(InpLossStreakPause>0 && lossStreak>=InpLossStreakPause)
     {
      pauseUntil=TimeCurrent()+InpPauseMinutes*60;
      lossStreak=0;
      LogEvent("PAUSE",(string)InpPauseMinutes+" min after "+(string)InpLossStreakPause+" losses in a row");
     }
  }
//+------------------------------------------------------------------+
