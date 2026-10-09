// TL-ME Trend Presser
// High-frequency trend presser: market up -> keep buying, market down -> keep
// selling. Adds a new position every few seconds while the trend holds, takes
// small profits per trade, closes the whole stack at a basket profit, and
// flips side when the trend flips. One instance per chart; works on any pair.
#property strict
#property version   "1.00"

#include <Trade/Trade.mqh>

input long            InpMagic              = 261009;
input bool            InpDemoOrCentOnly     = true;    // refuse to run on real standard accounts

//--- trend
input ENUM_TIMEFRAMES InpTrendTF            = PERIOD_M5;
input int             InpFastEMA            = 9;
input int             InpSlowEMA            = 21;

//--- pressing
input int             InpEntryEverySeconds  = 30;      // add a position this often while trend holds
input int             InpMaxPositions       = 10;      // max stacked positions per pair
input double          InpLotsPer1000        = 0.02;    // lot size per 1,000 of equity (auto-scales)

//--- per-trade exits (multiples of trend-TF ATR)
input int             InpATRPeriod          = 14;
input double          InpTakeProfitATR      = 0.5;     // small, quick profit per trade
input double          InpStopATR            = 3.0;     // per-trade emergency stop

//--- stack (basket) control
input double          InpBasketTakeProfitPct= 1.0;     // close all on this pair at +X% of equity
input double          InpBasketStopPct      = 15.0;    // close all on this pair at -X% of equity
input bool            InpCloseOnTrendFlip   = true;    // close the old side when trend flips

//--- costs
input double          InpMaxSpreadATR       = 0.5;     // skip entries if spread > X * ATR (0 = off)
input int             InpDeviationPoints    = 50;

CTrade   trade;
int      hFast=INVALID_HANDLE, hSlow=INVALID_HANDLE, hATR=INVALID_HANDLE;
datetime lastEntry=0;

bool Buf(const int h,const int n,double &out[])
  {
   ArraySetAsSeries(out,true);
   return CopyBuffer(h,0,0,n,out)==n;
  }

int Trend()
  {
   double f[],s[];
   if(!Buf(hFast,2,f) || !Buf(hSlow,2,s))
      return 0;
   double c=iClose(_Symbol,InpTrendTF,1);
   if(f[1]>s[1] && c>f[1]) return 1;
   if(f[1]<s[1] && c<f[1]) return -1;
   return 0;
  }

int Stack(int &buys,int &sells,double &floating)
  {
   buys=0; sells=0; floating=0;
   for(int i=PositionsTotal()-1;i>=0;i--)
     {
      ulong t=PositionGetTicket(i);
      if(t==0 || PositionGetString(POSITION_SYMBOL)!=_Symbol || PositionGetInteger(POSITION_MAGIC)!=InpMagic)
         continue;
      if(PositionGetInteger(POSITION_TYPE)==POSITION_TYPE_BUY) buys++; else sells++;
      floating+=PositionGetDouble(POSITION_PROFIT)+PositionGetDouble(POSITION_SWAP);
     }
   return buys+sells;
  }

void CloseSide(const int side)   // 1 = buys, -1 = sells, 0 = all
  {
   for(int i=PositionsTotal()-1;i>=0;i--)
     {
      ulong t=PositionGetTicket(i);
      if(t==0 || PositionGetString(POSITION_SYMBOL)!=_Symbol || PositionGetInteger(POSITION_MAGIC)!=InpMagic)
         continue;
      bool isBuy=PositionGetInteger(POSITION_TYPE)==POSITION_TYPE_BUY;
      if(side==0 || (side>0 && isBuy) || (side<0 && !isBuy))
         trade.PositionClose(t);
     }
  }

double Lots()
  {
   double step=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_STEP);
   double mn=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MIN);
   double mx=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MAX);
   double lots=InpLotsPer1000*AccountInfoDouble(ACCOUNT_EQUITY)/1000.0;
   lots=MathFloor(lots/step)*step;
   return MathMin(MathMax(lots,mn),mx);
  }

int OnInit()
  {
   if(InpDemoOrCentOnly)
     {
      bool demo=AccountInfoInteger(ACCOUNT_TRADE_MODE)==ACCOUNT_TRADE_MODE_DEMO;
      bool cent=StringFind(AccountInfoString(ACCOUNT_CURRENCY),"USC")>=0;
      if(!demo && !cent)
        {
         Print("[TLME] Refusing to start: demo or cent accounts only (InpDemoOrCentOnly=true).");
         return INIT_FAILED;
        }
     }
   hFast=iMA(_Symbol,InpTrendTF,InpFastEMA,0,MODE_EMA,PRICE_CLOSE);
   hSlow=iMA(_Symbol,InpTrendTF,InpSlowEMA,0,MODE_EMA,PRICE_CLOSE);
   hATR =iATR(_Symbol,InpTrendTF,InpATRPeriod);
   if(hFast==INVALID_HANDLE || hSlow==INVALID_HANDLE || hATR==INVALID_HANDLE)
      return INIT_FAILED;
   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(InpDeviationPoints);
   trade.SetTypeFillingBySymbol(_Symbol);
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason)
  {
   IndicatorRelease(hFast);
   IndicatorRelease(hSlow);
   IndicatorRelease(hATR);
  }

void OnTick()
  {
   double equity=AccountInfoDouble(ACCOUNT_EQUITY);
   int buys,sells; double floating;
   int open=Stack(buys,sells,floating);

   //--- stack exits, every tick
   if(open>0 && floating>=equity*InpBasketTakeProfitPct/100.0) { CloseSide(0); return; }
   if(open>0 && floating<=-equity*InpBasketStopPct/100.0)      { CloseSide(0); return; }

   int trend=Trend();
   if(trend==0)
      return;

   //--- trend flipped: close the old side
   if(InpCloseOnTrendFlip)
     {
      if(trend>0 && sells>0) CloseSide(-1);
      if(trend<0 && buys>0)  CloseSide(1);
     }

   //--- keep pressing in the trend direction
   int sameSide=(trend>0)?buys:sells;
   if(sameSide>=InpMaxPositions)
      return;
   if(TimeCurrent()-lastEntry<InpEntryEverySeconds)
      return;

   double atrBuf[];
   if(!Buf(hATR,2,atrBuf) || atrBuf[1]<=0)
      return;
   double atr=atrBuf[1];
   double ask=SymbolInfoDouble(_Symbol,SYMBOL_ASK), bid=SymbolInfoDouble(_Symbol,SYMBOL_BID);
   if(InpMaxSpreadATR>0 && ask-bid>InpMaxSpreadATR*atr)
      return;

   int    dg=(int)SymbolInfoInteger(_Symbol,SYMBOL_DIGITS);
   double lots=Lots();
   bool ok;
   if(trend>0)
      ok=trade.Buy(lots,_Symbol,ask,NormalizeDouble(ask-InpStopATR*atr,dg),NormalizeDouble(ask+InpTakeProfitATR*atr,dg),"TLME-P");
   else
      ok=trade.Sell(lots,_Symbol,bid,NormalizeDouble(bid+InpStopATR*atr,dg),NormalizeDouble(bid-InpTakeProfitATR*atr,dg),"TLME-P");
   if(ok)
      lastEntry=TimeCurrent();
  }

//--- tester report in DAYS; return = average profit per trading day
double OnTester()
  {
   if(!HistorySelect(0,TimeCurrent()))
      return 0;
   int days=0,green=0,trades=0,cur=-1;
   double sum=0,day=0,best=-DBL_MAX,worst=DBL_MAX;
   int total=HistoryDealsTotal();
   for(int i=0;i<=total;i++)
     {
      bool last=(i==total);
      int key=-1; double pnl=0;
      if(!last)
        {
         ulong d=HistoryDealGetTicket(i);
         if(d==0 || HistoryDealGetInteger(d,DEAL_MAGIC)!=InpMagic || HistoryDealGetInteger(d,DEAL_ENTRY)!=DEAL_ENTRY_OUT)
            continue;
         MqlDateTime t;
         TimeToStruct((datetime)HistoryDealGetInteger(d,DEAL_TIME),t);
         key=t.year*10000+t.mon*100+t.day;
         pnl=HistoryDealGetDouble(d,DEAL_PROFIT)+HistoryDealGetDouble(d,DEAL_COMMISSION)+HistoryDealGetDouble(d,DEAL_SWAP);
         trades++;
        }
      if((last || key!=cur) && cur!=-1)
        {
         days++; sum+=day;
         if(day>0) green++;
         best=MathMax(best,day); worst=MathMin(worst,day);
         day=0;
        }
      if(last) break;
      cur=key; day+=pnl;
     }
   if(days==0) { Print("[TLME DAILY] no trades"); return 0; }
   PrintFormat("[TLME DAILY] %s | trading days=%d | trades/day=%.1f | avg/day=%.2f | best day=%.2f | worst day=%.2f | green days=%.0f%%",
               _Symbol,days,(double)trades/days,sum/days,best,worst,100.0*green/days);
   return sum/days;
  }
