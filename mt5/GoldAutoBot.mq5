//+------------------------------------------------------------------+
//| GoldAutoBot.mq5                                                  |
//| Exness MT5 Expert Advisor — NO REST API needed                   |
//| Attach to XAUUSD M5 chart. Auto buy/sell with SL/TP + exit.      |
//+------------------------------------------------------------------+
#property copyright "trade-bot"
#property version   "1.00"
#property strict

input double LotSize          = 0.01;
input int    MagicNumber      = 260903;
input int    MaxPositions     = 1;
input double RiskSLUSD        = 0.55;   // approx SL distance in price for gold
input double RiskTPUSD        = 0.35;
input int    RSIPeriod        = 14;
input int    RSIBuyBelow      = 35;
input int    RSISellAbove     = 65;
input int    EMAFast          = 9;
input int    EMASlow          = 21;
input int    SlippagePoints   = 30;

int rsiHandle = INVALID_HANDLE;
int emaFHandle = INVALID_HANDLE;
int emaSHandle = INVALID_HANDLE;

int OnInit()
{
   rsiHandle  = iRSI(_Symbol, PERIOD_M5, RSIPeriod, PRICE_CLOSE);
   emaFHandle = iMA(_Symbol, PERIOD_M5, EMAFast, 0, MODE_EMA, PRICE_CLOSE);
   emaSHandle = iMA(_Symbol, PERIOD_M5, EMASlow, 0, MODE_EMA, PRICE_CLOSE);
   if(rsiHandle == INVALID_HANDLE || emaFHandle == INVALID_HANDLE || emaSHandle == INVALID_HANDLE)
   {
      Print("Indicator init failed");
      return INIT_FAILED;
   }
   Print("GoldAutoBot ready on ", _Symbol);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   if(rsiHandle  != INVALID_HANDLE) IndicatorRelease(rsiHandle);
   if(emaFHandle != INVALID_HANDLE) IndicatorRelease(emaFHandle);
   if(emaSHandle != INVALID_HANDLE) IndicatorRelease(emaSHandle);
}

int CountMyPositions()
{
   int n = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if((int)PositionGetInteger(POSITION_MAGIC) != MagicNumber) continue;
      n++;
   }
   return n;
}

void CloseAllMine()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if((int)PositionGetInteger(POSITION_MAGIC) != MagicNumber) continue;
      MqlTradeRequest req; MqlTradeResult res;
      ZeroMemory(req); ZeroMemory(res);
      req.action   = TRADE_ACTION_DEAL;
      req.position = ticket;
      req.symbol   = _Symbol;
      req.volume   = PositionGetDouble(POSITION_VOLUME);
      req.deviation = SlippagePoints;
      req.magic    = MagicNumber;
      long type = PositionGetInteger(POSITION_TYPE);
      if(type == POSITION_TYPE_BUY)
      {
         req.type = ORDER_TYPE_SELL;
         req.price = SymbolInfoDouble(_Symbol, SYMBOL_BID);
      }
      else
      {
         req.type = ORDER_TYPE_BUY;
         req.price = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      }
      OrderSend(req, res);
   }
}

bool OpenDeal(ENUM_ORDER_TYPE type)
{
   double price = (type == ORDER_TYPE_BUY) ?
                  SymbolInfoDouble(_Symbol, SYMBOL_ASK) :
                  SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double sl, tp;
   if(type == ORDER_TYPE_BUY)
   {
      sl = price - RiskSLUSD;
      tp = price + RiskTPUSD;
   }
   else
   {
      sl = price + RiskSLUSD;
      tp = price - RiskTPUSD;
   }

   MqlTradeRequest req; MqlTradeResult res;
   ZeroMemory(req); ZeroMemory(res);
   req.action    = TRADE_ACTION_DEAL;
   req.symbol    = _Symbol;
   req.volume    = LotSize;
   req.type      = type;
   req.price     = price;
   req.sl        = sl;
   req.tp        = tp;
   req.deviation = SlippagePoints;
   req.magic     = MagicNumber;
   req.comment   = "GoldAutoBot";
   bool ok = OrderSend(req, res);
   Print("Open ", EnumToString(type), " retcode=", res.retcode);
   return ok;
}

void OnTick()
{
   // Cap positions — close extras
   if(CountMyPositions() > MaxPositions)
      CloseAllMine();

   if(CountMyPositions() >= MaxPositions)
      return;

   double rsi[3], ef[3], es[3];
   if(CopyBuffer(rsiHandle, 0, 0, 3, rsi) < 3) return;
   if(CopyBuffer(emaFHandle, 0, 0, 3, ef) < 3) return;
   if(CopyBuffer(emaSHandle, 0, 0, 3, es) < 3) return;

   // Buy: EMA fast crossed above slow OR RSI oversold bounce
   bool buySignal  = (ef[1] <= es[1] && ef[0] > es[0]) || (rsi[0] < RSIBuyBelow && rsi[1] < rsi[0]);
   // Sell: EMA death cross OR RSI overbought fade
   bool sellSignal = (ef[1] >= es[1] && ef[0] < es[0]) || (rsi[0] > RSISellAbove && rsi[1] > rsi[0]);

   if(buySignal && !sellSignal)
      OpenDeal(ORDER_TYPE_BUY);
   else if(sellSignal && !buySignal)
      OpenDeal(ORDER_TYPE_SELL);
}
