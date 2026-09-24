// GOLIDE tick-driven demo position manager.
// Entry selection stays in Python. This EA owns protection and exits only for
// positions carrying InpMagic. Attach one instance to one chart.
#property strict
#property version   "1.00"

#include <Trade/Trade.mqh>

input long   InpMagic                 = 260909;
input bool   InpDemoOnly              = true;
input int    InpTimerMilliseconds     = 200;
input int    InpNoProgressSeconds     = 60;
input double InpMinimumProgressR      = 0.10;
input int    InpProfitStallSeconds    = 20;
input int    InpHardExitSeconds       = 180;
input double InpBreakEvenTriggerR     = 0.20;
input double InpBreakEvenLockR        = 0.03;
input double InpTrailTriggerR         = 0.35;
input double InpTrailDistanceR        = 0.18;
input double InpFailureBufferR        = 0.05;
input int    InpDeviationPoints       = 30;

CTrade trade;

string StateKey(const string field,const ulong ticket)
  {
   return "GFM."+field+"."+(string)ticket;
  }

double ReadState(const string field,const ulong ticket,const double fallback)
  {
   string key=StateKey(field,ticket);
   if(!GlobalVariableCheck(key))
      GlobalVariableSet(key,fallback);
   return GlobalVariableGet(key);
  }

void WriteState(const string field,const ulong ticket,const double value)
  {
   GlobalVariableSet(StateKey(field,ticket),value);
  }

void DeleteState(const ulong ticket)
  {
   GlobalVariableDel(StateKey("risk",ticket));
   GlobalVariableDel(StateKey("peak",ticket));
   GlobalVariableDel(StateKey("peak_time",ticket));
  }

void AuditExit(const ulong ticket,const string symbol,const string reason)
  {
   FolderCreate("GOLIDE",FILE_COMMON);
   int handle=FileOpen("GOLIDE\\fast_manager_events.csv",
                       FILE_READ|FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON|FILE_SHARE_READ);
   if(handle==INVALID_HANDLE)
      return;
   FileSeek(handle,0,SEEK_END);
   FileWrite(handle,(long)TimeCurrent(),ticket,symbol,reason);
   FileClose(handle);
  }

double CommentNumber(const string comment,const int index)
  {
   string fields[];
   ushort separator=StringGetCharacter("|",0);
   if(StringSplit(comment,separator,fields)!=4 || fields[0]!="G" || index<2 || index>3)
      return 0.0;
   return StringToDouble(fields[index]);
  }

void WriteHeartbeat()
  {
   static datetime last_write=0;
   datetime now=TimeCurrent();
   if(now==last_write)
      return;
   last_write=now;
   FolderCreate("GOLIDE",FILE_COMMON);
   int handle=FileOpen("GOLIDE\\fast_manager_heartbeat.csv",
                       FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_COMMON);
   if(handle==INVALID_HANDLE)
      return;
   FileWriteString(handle,(string)(long)now+","+
                   (string)AccountInfoInteger(ACCOUNT_LOGIN)+","+(string)InpMagic);
   FileClose(handle);
  }

bool CloseManagedPosition(const ulong ticket,const string reason)
  {
   if(!PositionSelectByTicket(ticket))
      return false;
   string symbol=PositionGetString(POSITION_SYMBOL);
   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(InpDeviationPoints);
   trade.SetTypeFillingBySymbol(symbol);
   if(!trade.PositionClose(ticket,InpDeviationPoints))
     {
      Print("GOLIDE close failed ticket=",ticket," reason=",reason,
            " retcode=",trade.ResultRetcode()," ",trade.ResultRetcodeDescription());
      return false;
     }
   Print("GOLIDE close ticket=",ticket," reason=",reason);
   AuditExit(ticket,symbol,reason);
   DeleteState(ticket);
   return true;
  }

bool RatchetStop(const ulong ticket,const string symbol,const long side,
                 const double market_price,const double proposed)
  {
   if(!PositionSelectByTicket(ticket))
      return false;
   double current=PositionGetDouble(POSITION_SL);
   double target=proposed;
   double point=SymbolInfoDouble(symbol,SYMBOL_POINT);
   int digits=(int)SymbolInfoInteger(symbol,SYMBOL_DIGITS);
   long stop_points=SymbolInfoInteger(symbol,SYMBOL_TRADE_STOPS_LEVEL);
   long freeze_points=SymbolInfoInteger(symbol,SYMBOL_TRADE_FREEZE_LEVEL);
   double minimum_distance=(double)MathMax(stop_points,freeze_points)*point;
   if(side==POSITION_TYPE_BUY)
     {
      target=MathMin(target,market_price-minimum_distance);
      if(target<=0 || (current>0 && target<=current+point/2.0))
         return false;
     }
   else
     {
      target=MathMax(target,market_price+minimum_distance);
      if(target<=0 || (current>0 && target>=current-point/2.0))
         return false;
     }
   target=NormalizeDouble(target,digits);
   double tp=PositionGetDouble(POSITION_TP);
   trade.SetExpertMagicNumber(InpMagic);
   trade.SetTypeFillingBySymbol(symbol);
   if(!trade.PositionModify(ticket,target,tp))
     {
      Print("GOLIDE stop modify failed ticket=",ticket," retcode=",
            trade.ResultRetcode()," ",trade.ResultRetcodeDescription());
      return false;
     }
   return true;
  }

void ManageTicket(const ulong ticket)
  {
   if(!PositionSelectByTicket(ticket))
      return;
   if(PositionGetInteger(POSITION_MAGIC)!=InpMagic)
      return;

   string symbol=PositionGetString(POSITION_SYMBOL);
   long side=PositionGetInteger(POSITION_TYPE);
   double entry=PositionGetDouble(POSITION_PRICE_OPEN);
   double initial_sl=PositionGetDouble(POSITION_SL);
   datetime opened=(datetime)PositionGetInteger(POSITION_TIME);
   string comment=PositionGetString(POSITION_COMMENT);
   MqlTick tick;
   if(!SymbolInfoTick(symbol,tick))
      return;
   double market_price=(side==POSITION_TYPE_BUY ? tick.bid : tick.ask);
   double direction=(side==POSITION_TYPE_BUY ? 1.0 : -1.0);
   double comment_risk=CommentNumber(comment,3);
   double initial_risk=ReadState("risk",ticket,
                                 comment_risk>0 ? comment_risk : MathAbs(entry-initial_sl));
   if(initial_risk<=0)
      return;

   double favorable=direction*(market_price-entry);
   double peak=ReadState("peak",ticket,MathMax(0.0,favorable));
   datetime peak_time=(datetime)ReadState("peak_time",ticket,(double)opened);
   if(favorable>peak)
     {
      peak=favorable;
      peak_time=TimeCurrent();
      WriteState("peak",ticket,peak);
      WriteState("peak_time",ticket,(double)peak_time);
     }
   double current_r=favorable/initial_risk;
   double peak_r=peak/initial_risk;
   int age=(int)(TimeCurrent()-opened);
   int since_peak=(int)(TimeCurrent()-peak_time);

   double breakout=CommentNumber(comment,2);
   if(breakout>0)
     {
      bool failed=(side==POSITION_TYPE_BUY
                   ? market_price<breakout-InpFailureBufferR*initial_risk
                   : market_price>breakout+InpFailureBufferR*initial_risk);
      if(failed && CloseManagedPosition(ticket,"failed_breakout"))
         return;
     }
   if(age>=InpNoProgressSeconds && peak_r<InpMinimumProgressR)
     {
      if(CloseManagedPosition(ticket,"no_progress"))
         return;
     }
   if(peak_r>=InpMinimumProgressR && current_r<=0 && since_peak>=InpProfitStallSeconds)
     {
      if(CloseManagedPosition(ticket,"edge_evaporated"))
         return;
     }
   if(peak_r>=InpMinimumProgressR && current_r>0 && since_peak>=InpProfitStallSeconds)
     {
      if(CloseManagedPosition(ticket,"profit_stalled"))
         return;
     }
   if(InpHardExitSeconds>0 && age>=InpHardExitSeconds)
     {
      if(CloseManagedPosition(ticket,"hard_time_exit"))
         return;
     }

   double protected_r=-DBL_MAX;
   if(peak_r>=InpBreakEvenTriggerR)
      protected_r=InpBreakEvenLockR;
   if(peak_r>=InpTrailTriggerR)
      protected_r=MathMax(protected_r,peak_r-InpTrailDistanceR);
   if(protected_r>-DBL_MAX/2.0)
      RatchetStop(ticket,symbol,side,market_price,
                  entry+direction*protected_r*initial_risk);
  }

void ManageAll()
  {
   WriteHeartbeat();
   for(int index=PositionsTotal()-1;index>=0;--index)
     {
      ulong ticket=PositionGetTicket(index);
      if(ticket>0)
         ManageTicket(ticket);
     }
  }

int OnInit()
  {
   if(InpDemoOnly && AccountInfoInteger(ACCOUNT_TRADE_MODE)!=ACCOUNT_TRADE_MODE_DEMO)
     {
      Print("GOLIDE Fast Manager refused: InpDemoOnly is true on a non-demo account");
      return INIT_FAILED;
     }
   if(InpTimerMilliseconds<50 || InpNoProgressSeconds<1 || InpProfitStallSeconds<1 ||
      InpMinimumProgressR<0 || InpBreakEvenTriggerR<0 || InpTrailTriggerR<0 ||
      InpTrailDistanceR<=0)
      return INIT_PARAMETERS_INCORRECT;
   EventSetMillisecondTimer(InpTimerMilliseconds);
   trade.SetExpertMagicNumber(InpMagic);
   Print("GOLIDE Fast Manager active; magic=",InpMagic);
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason)
  {
   EventKillTimer();
   FileDelete("GOLIDE\\fast_manager_heartbeat.csv",FILE_COMMON);
  }

void OnTick()
  {
   ManageAll();
  }

void OnTimer()
  {
   // A timer is required because OnTick only belongs to the chart symbol.
   ManageAll();
  }
