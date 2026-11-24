MT5_ArtOfTrading_EA/ArtOfTrading_EA.mq5 — 786 total lines

    1 │ //+------------------------------------------------------------------+
    2 │ //|                                             ArtOfTrading_EA.mq5   |
    3 │ //|  Expert Advisor inspire de "Inside the Mind of Trader Stewie"     |
    4 │ //|  Strategies implementees (voir README.md pour le detail) :        |
    5 │ //|   1. Holy Grail (pullback sur EMA20 + chandelier de reversal)     |
    6 │ //|   2. Falling Wedge (coin descendant + divergence RSI/MACD)        |
    7 │ //|   3. Breakout & Retest (cassure + retest sur faible volume)       |
    8 │ //|   4. Double Bottom Divergence (marche laterale)                   |
    9 │ //|   5. 2B Bottom Reversal (failed breakdown de Trader Vic)          |
   10 │ //|   6. Divergence RSI/MACD generale                                 |
   11 │ //|   7. Rising Wedge (version short / bearish)                       |
   12 │ //|   8. Over Night Hold (ONH - fin de session)                       |
   13 │ //|   Sortie universelle : Stair Step Stop Loss                       |
   14 │ //|   Gestion du capital : 1% risque / 10% capital / 6 positions max  |
   15 │ //+------------------------------------------------------------------+
   16 │ #property copyright "Art Of Trading - strategies codees pour MT5"
   17 │ #property version   "1.00"
   18 │ #property strict
   19 │ 
   20 │ #include <Trade/Trade.mqh>
   21 │ 
   22 │ //==================================================================
   23 │ //  PARAMETRES
   24 │ //==================================================================
   25 │ 
   26 │ //--- Gestion du capital (regles du livre)
   27 │ input group "=== GESTION DU CAPITAL (regles du livre) ==="
   28 │ input double RiskPercentPerTrade   = 1.0;   // Risque max par trade (% du capital) - livre: 1%
   29 │ input double MaxCapitalPerTradePct = 10.0;  // Capital max immobilise par trade (%) - livre: 10%
   30 │ input int    MaxOpenPositions      = 6;     // Nombre max de positions ouvertes - livre: 5-6
   31 │ input double MaxDailyLossPct       = 3.0;   // Perte journaliere max avant arret (0=desactive)
   32 │ 
   33 │ //--- Filtres generaux
   34 │ input group "=== FILTRES ==="
   35 │ input int    MaxSpreadPoints       = 30;    // Spread max autorise (points)
   36 │ input int    DeviationPoints       = 20;    // Deviation d'execution (points)
   37 │ input bool   TradeOnNewBarOnly     = true;  // Ne prendre des signaux qu'au debut d'une bougie
   38 │ input bool   UseHTFTrendFilter     = true;  // Filtre de tendance EMA200
   39 │ input int    ADXMinTrend           = 20;    // ADX minimum pour considérer une tendance
   40 │ input double VolSpikeRatio         = 1.5;   // Volume minimal d'une cassure (x volume moyen)
   41 │ input double VolPullbackMaxRatio   = 1.0;   // Volume max d'un pullback (x volume moyen)
   42 │ 
   43 │ //--- Indicateurs
   44 │ input group "=== INDICATEURS ==="
   45 │ input int    EMA20Period           = 20;    // Periode EMA rapide (Holy Grail)
   46 │ input int    EMA50Period           = 50;    // Peride EMA intermédiaire
   47 │ input int    EMA200Period          = 200;   // Periode EMA tendance longue
   48 │ input int    RSIPeriod             = 14;    // Periode RSI
   49 │ input int    MACDFast              = 12;    // MACD rapide
   50 │ input int    MACDSlow              = 26;    // MACD lent
   51 │ input int    MACDSignal            = 9;     // MACD signal
   52 │ input int    ADXPeriod             = 14;    // Periode ADX
   53 │ input int    ATRPeriod             = 14;    // Periode ATR
   54 │ input int    VolAvgPeriod          = 20;    // Periode du volume moyen
   55 │ input int    LookbackBars          = 80;    // Nombre de bougies analysees
   56 │ input int    WedgeBars             = 18;    // Fenetre de detection des coins (wedges)
   57 │ 
   58 │ //--- Activation des strategies
   59 │ input group "=== STRATEGIES (du livre) ==="
   60 │ input bool   EnableHolyGrail       = true;  // Holy Grail - pullback EMA20 (tendance)
   61 │ input bool   EnableFallingWedge    = true;  // Falling Wedge - coin descendant (long)
   62 │ input bool   EnableBreakoutRetest  = true;  // Breakout & Retest
   63 │ input bool   EnableDoubleBottomDiv = true;  // Double Bottom Divergence (chop)
   64 │ input bool   Enable2BReversal      = true;  // 2B Bottom Reversal (Trader Vic)
   65 │ input bool   EnableDivergence      = false; // Divergence RSI/MACD generique
   66 │ input bool   EnableRisingWedge     = true;  // Rising Wedge (short)
   67 │ input bool   EnableONH             = false; // Over Night Hold (1ere bougie de la seance)
   68 │ 
   69 │ //--- Sorties / Stop
   70 │ input group "=== SORTIES / STOP LOSS ==="
   71 │ input double TakeProfitRR          = 3.0;   // Ratio Risk/Reward du take profit
   72 │ input double StopBufferATR         = 0.20;  // Marge du stop en multiples d'ATR
   73 │ input int    StopBufferPipsMin     = 10;    // Marge minimale du stop (pips)
   74 │ input double BreakEvenAfterPips    = 30;    // Passer en break-even apres N pips de gain
   75 │ input bool   EnableTrailing        = true;  // Activer le Stair Step Stop Loss
   76 │ input bool   StairUseDaily         = true;  // Stair Step base sur la bougie journaliere (livre) ou locale
   77 │ input bool   UseATRTrailing        = true;  // Marge de trail via ATR (sinon pips)
   78 │ input double StairATRMult          = 0.30;  // Marge trail en multiples d'ATR
   79 │ input int    StairStepBufferPips   = 10;    // Marge trail fixe en pips (si ATR desactive)
   80 │ 
   81 │ //--- Over Night Hold
   82 │ input group "=== OVER NIGHT HOLD (regler selon l'heure serveur) ==="
   83 │ input int    ONHCloseHour          = 21;    // Heure de fermeture du marche (heure serveur MT5)
   84 │ input int    ONHCloseMinute        = 0;     // Minute de fermeture
   85 │ input int    ONHExitHour           = 0;     // Heure de sortie (ouverture suivante)
   86 │ input double ONHCloseLocationMin   = 0.85;  // Cloture dans le haut/bas de la bougie journaliere (0-1)
   87 │ input double ONHVolumeRatio        = 1.20;  // Volume journalier minimum (x volume moyen)
   88 │ 
   89 │ //--- Divers
   90 │ input group "=== DIVERS ==="
   91 │ input ulong  MagicBase             = 20241121; // Magic de base (ne pas changer inutilement)
   92 │ input bool   ShowStatusOnChart     = true;     // Afficher l'etat du robot directement sur le graphique
   93 │ 
   94 │ //==================================================================
   95 │ //  IDENTIFIANTS DE STRATEGIES
   96 │ //==================================================================
   97 │ #define S_HOLYGRAIL   1
   98 │ #define S_FALLWEDGE   2
   99 │ #define S_BREAKOUT    3
  100 │ #define S_DOUBLEBOTTOM 4
  101 │ #define S_2B          5
  102 │ #define S_DIVERGENCE  6
  103 │ #define S_RISINGWEDGE 7
  104 │ #define S_ONH         8
  105 │ 
  106 │ #define SIG_NONE  0
  107 │ #define SIG_BUY   1
  108 │ #define SIG_SELL  2
  109 │ 
  110 │ //==================================================================
  111 │ //  STRUCTURE DE SIGNAL
  112 │ //==================================================================
  113 │ struct SSignal
  114 │ {
  115 │    int    dir;      // SIG_BUY / SIG_SELL
  116 │    int    sid;      // identifiant strategie
  117 │    double sl;       // stop loss
  118 │    double tp;       // take profit
  119 │    string name;     // nom lisible
  120 │ };
  121 │ 
  122 │ //==================================================================
  123 │ //  VARIABLES GLOBALES
  124 │ //==================================================================
  125 │ CTrade trade;
  126 │ 
  127 │ int hMA20=INVALID_HANDLE, hMA50=INVALID_HANDLE, hMA200=INVALID_HANDLE;
  128 │ int hRSI=INVALID_HANDLE, hMACD=INVALID_HANDLE, hADX=INVALID_HANDLE, hATR=INVALID_HANDLE;
  129 │ 
  130 │ double ma20Buf[], ma50Buf[], ma200Buf[], rsiBuf[], macdHistBuf[], adxBuf[], atrBuf[];
  131 │ 
  132 │ datetime lastBarTime=0;
  133 │ int      curDay=-1;
  134 │ double   dayStartEquity=0;
  135 │ datetime lastONHDay=0;
  136 │ string   gLastSignal="aucun";
  137 │ datetime gLastSignalTime=0;
  138 │ double   gLastADX=0;
  139 │ 
  140 │ //==================================================================
  141 │ //  INITIALISATION
  142 │ //==================================================================
  143 │ int OnInit()
  144 │ {
  145 │    hMA20  = iMA(_Symbol,_Period,EMA20Period,0,MODE_EMA,PRICE_CLOSE);
  146 │    hMA50  = iMA(_Symbol,_Period,EMA50Period,0,MODE_EMA,PRICE_CLOSE);
  147 │    hMA200 = iMA(_Symbol,_Period,EMA200Period,0,MODE_EMA,PRICE_CLOSE);
  148 │    hRSI   = iRSI(_Symbol,_Period,RSIPeriod,PRICE_CLOSE);
  149 │    hMACD  = iMACD(_Symbol,_Period,MACDFast,MACDSlow,MACDSignal,PRICE_CLOSE);
  150 │    hADX   = iADX(_Symbol,_Period,ADXPeriod);
  151 │    hATR   = iATR(_Symbol,_Period,ATRPeriod);
  152 │ 
  153 │    if(hMA20==INVALID_HANDLE || hMA50==INVALID_HANDLE || hMA200==INVALID_HANDLE ||
  154 │       hRSI==INVALID_HANDLE || hMACD==INVALID_HANDLE || hADX==INVALID_HANDLE || hATR==INVALID_HANDLE)
  155 │    {
  156 │       Print("Erreur: impossible de creer les indicateurs");
  157 │       return INIT_FAILED;
  158 │    }
  159 │ 
  160 │    ArrayResize(atrBuf,ATRPeriod+10);
  161 │    ArraySetAsSeries(ma20Buf,true);  ArraySetAsSeries(ma50Buf,true);
  162 │    ArraySetAsSeries(ma200Buf,true); ArraySetAsSeries(rsiBuf,true);
  163 │    ArraySetAsSeries(macdHistBuf,true); ArraySetAsSeries(adxBuf,true);
  164 │    ArraySetAsSeries(atrBuf,true);
  165 │    CopyBuffer(hATR,0,0,ATRPeriod+10,atrBuf); // disponible des le premier tick pour le trailing
  166 │ 
  167 │    trade.SetExpertMagicNumber(MagicBase);
  168 │    Print("ArtOfTrading_EA initialise sur ",_Symbol," / ",EnumToString(_Period));
  169 │    return INIT_SUCCEEDED;
  170 │ }
  171 │ 
  172 │ void OnDeinit(const int reason)
  173 │ {
  174 │    if(hMA20!=INVALID_HANDLE)  IndicatorRelease(hMA20);
  175 │    if(hMA50!=INVALID_HANDLE)  IndicatorRelease(hMA50);
  176 │    if(hMA200!=INVALID_HANDLE) IndicatorRelease(hMA200);
  177 │    if(hRSI!=INVALID_HANDLE)   IndicatorRelease(hRSI);
  178 │    if(hMACD!=INVALID_HANDLE)  IndicatorRelease(hMACD);
  179 │    if(hADX!=INVALID_HANDLE)   IndicatorRelease(hADX);
  180 │    if(hATR!=INVALID_HANDLE)   IndicatorRelease(hATR);
  181 │ }
  182 │ 
  183 │ //==================================================================
  184 │ //  OUTILS
  185 │ //==================================================================
  186 │ bool IsNewBar()
  187 │ {
  188 │    datetime t[1];
  189 │    if(CopyTime(_Symbol,_Period,0,1,t)<1) return false;
  190 │    if(t[0]!=lastBarTime){ lastBarTime=t[0]; return true; }
  191 │    return false;
  192 │ }
  193 │ 
  194 │ bool DailyLossOK()
  195 │ {
  196 │    if(MaxDailyLossPct<=0) return true;
  197 │    MqlDateTime dt;
  198 │    TimeToStruct(TimeCurrent(),dt);
  199 │    if(dt.day!=curDay)
  200 │    {
  201 │       curDay=dt.day;
  202 │       dayStartEquity=AccountInfoDouble(ACCOUNT_EQUITY);
  203 │    }
  204 │    if(dayStartEquity<=0) return true;
  205 │    double eq=AccountInfoDouble(ACCOUNT_EQUITY);
  206 │    double dd=(dayStartEquity-eq)/dayStartEquity*100.0;
  207 │    return (dd < MaxDailyLossPct);
  208 │ }
  209 │ 
  210 │ bool PrepareData(int n)
  211 │ {
  212 │    if(BarsCalculated(hMA20)<n  || BarsCalculated(hMA50)<n  ||
  213 │       BarsCalculated(hMA200)<n || BarsCalculated(hRSI)<n   ||
  214 │       BarsCalculated(hMACD)<n  || BarsCalculated(hADX)<n   ||
  215 │       BarsCalculated(hATR)<n) return false;
  216 │ 
  217 │    ArrayResize(ma20Buf,n);    ArraySetAsSeries(ma20Buf,true);
  218 │    ArrayResize(ma50Buf,n);    ArraySetAsSeries(ma50Buf,true);
  219 │    ArrayResize(ma200Buf,n);   ArraySetAsSeries(ma200Buf,true);
  220 │    ArrayResize(rsiBuf,n);     ArraySetAsSeries(rsiBuf,true);
  221 │    ArrayResize(macdHistBuf,n);ArraySetAsSeries(macdHistBuf,true);
  222 │    ArrayResize(adxBuf,n);     ArraySetAsSeries(adxBuf,true);
  223 │    ArrayResize(atrBuf,n);     ArraySetAsSeries(atrBuf,true);
  224 │ 
  225 │    if(CopyBuffer(hMA20,0,0,n,ma20Buf)<n)      return false;
  226 │    if(CopyBuffer(hMA50,0,0,n,ma50Buf)<n)      return false;
  227 │    if(CopyBuffer(hMA200,0,0,n,ma200Buf)<n)    return false;
  228 │    if(CopyBuffer(hRSI,0,0,n,rsiBuf)<n)        return false;
  229 │    if(CopyBuffer(hMACD,2,0,n,macdHistBuf)<n)  return false; // histogramme
  230 │    if(CopyBuffer(hADX,0,0,n,adxBuf)<n)        return false;
  231 │    if(CopyBuffer(hATR,0,0,n,atrBuf)<n)        return false;
  232 │    gLastADX=adxBuf[1];
  233 │    return true;
  234 │ }
  235 │ 
  236 │ double AvgVolume(MqlRates &r[], int start, int len)
  237 │ {
  238 │    double s=0; int c=0;
  239 │    int total=ArraySize(r);
  240 │    for(int i=start;i<start+len && i<total;i++){ s+=(double)r[i].tick_volume; c++; }
  241 │    return (c>0? s/c : 0);
  242 │ }
  243 │ 
  244 │ bool IsHammer(MqlRates &r[], int i)
  245 │ {
  246 │    if(i<0 || i>=ArraySize(r)) return false;
  247 │    double rng=r[i].high-r[i].low;
  248 │    if(rng<=0) return false;
  249 │    double body=MathAbs(r[i].close-r[i].open);
  250 │    double loWick=r[i].low-MathMin(r[i].open,r[i].close);
  251 │    double hiWick=r[i].high-MathMax(r[i].open,r[i].close);
  252 │    return (body/rng<0.35 && loWick>=2.0*body && hiWick<=body);
  253 │ }
  254 │ 
  255 │ bool IsBullEngulf(MqlRates &r[], int i)
  256 │ {
  257 │    if(i<1 || i>=ArraySize(r)) return false;
  258 │    return (r[i].close>r[i].open && r[i-1].close<r[i-1].open &&
  259 │            r[i].close>r[i-1].open && r[i].open<r[i-1].close);
  260 │ }
  261 │ 
  262 │ bool IsBearEngulf(MqlRates &r[], int i)
  263 │ {
  264 │    if(i<1 || i>=ArraySize(r)) return false;
  265 │    return (r[i].close<r[i].open && r[i-1].close>r[i-1].open &&
  266 │            r[i].close<r[i-1].open && r[i].open>r[i-1].close);
  267 │ }
  268 │ 
  269 │ bool IsPivotLow(MqlRates &r[], int i, int left=2, int right=2)
  270 │ {
  271 │    int sz=ArraySize(r);
  272 │    if(i<left || i>sz-1-right) return false;
  273 │    for(int j=i-left;j<=i+right;j++)
  274 │       if(j!=i && r[j].low<=r[i].low) return false;
  275 │    return true;
  276 │ }
  277 │ 
  278 │ bool IsPivotHigh(MqlRates &r[], int i, int left=2, int right=2)
  279 │ {
  280 │    int sz=ArraySize(r);
  281 │    if(i<left || i>sz-1-right) return false;
  282 │    for(int j=i-left;j<=i+right;j++)
  283 │       if(j!=i && r[j].high>=r[i].high) return false;
  284 │    return true;
  285 │ }
  286 │ 
  287 │ // Trouve les pivots dans l'ordre : idx[0] = le plus recent
  288 │ int FindPivots(MqlRates &r[], bool lows, int &idx[], int maxCount, int start, int end)
  289 │ {
  290 │    int c=0;
  291 │    int sz=ArraySize(r);
  292 │    if(end>sz-3) end=sz-3;
  293 │    for(int i=start;i<=end && c<maxCount;i++)
  294 │    {
  295 │       if(lows ? IsPivotLow(r,i) : IsPivotHigh(r,i)) idx[c++]=i;
  296 │    }
  297 │    return c;
  298 │ }
  299 │ 
  300 │ bool BullDivergence(int iRecent, int iOlder)
  301 │ {
  302 │    if(iRecent<0 || iOlder<0) return false;
  303 │    return (rsiBuf[iRecent]>rsiBuf[iOlder] || macdHistBuf[iRecent]>macdHistBuf[iOlder]);
  304 │ }
  305 │ 
  306 │ bool BearDivergence(int iRecent, int iOlder)
  307 │ {
  308 │    if(iRecent<0 || iOlder<0) return false;
  309 │    return (rsiBuf[iRecent]<rsiBuf[iOlder] || macdHistBuf[iRecent]<macdHistBuf[iOlder]);
  310 │ }
  311 │ 
  312 │ bool IsUptrend(MqlRates &r[])
  313 │ {
  314 │    bool ok=(r[1].close>ma50Buf[1] && ma20Buf[1]>ma50Buf[1] && ma20Buf[1]>ma20Buf[5]);
  315 │    if(UseHTFTrendFilter) ok = ok && (r[1].close>ma200Buf[1]);
  316 │    if(adxBuf[1]<ADXMinTrend) ok=false;
  317 │    return ok;
  318 │ }
  319 │ 
  320 │ bool IsDowntrend(MqlRates &r[])
  321 │ {
  322 │    bool ok=(r[1].close<ma50Buf[1] && ma20Buf[1]<ma50Buf[1] && ma20Buf[1]<ma20Buf[5]);
  323 │    if(UseHTFTrendFilter) ok = ok && (r[1].close<ma200Buf[1]);
  324 │    if(adxBuf[1]<ADXMinTrend) ok=false;
  325 │    return ok;
  326 │ }
  327 │ 
  328 │ double StopBufferPrice()
  329 │ {
  330 │    double buf=StopBufferATR*atrBuf[1];
  331 │    double minb=StopBufferPipsMin*_Point;
  332 │    double stopsLvl=(double)SymbolInfoInteger(_Symbol,SYMBOL_TRADE_STOPS_LEVEL)*_Point;
  333 │    return MathMax(MathMax(buf,minb),stopsLvl);
  334 │ }
  335 │ 
  336 │ void BuildSignal(SSignal &sig, int dir, int sid, double sl, double namePrice, string name)
  337 │ {
  338 │    double entry=(dir==SIG_BUY? SymbolInfoDouble(_Symbol,SYMBOL_ASK) : SymbolInfoDouble(_Symbol,SYMBOL_BID));
  339 │    double risk=MathAbs(entry-sl);
  340 │    if(risk<=0) { sig.dir=SIG_NONE; return; }
  341 │    double buf=StopBufferPrice();
  342 │    sig.dir=dir; sig.sid=sid; sig.name=name;
  343 │    if(dir==SIG_BUY)
  344 │    {
  345 │       sig.sl=MathMin(sl, entry-buf);
  346 │       sig.tp=entry+risk*TakeProfitRR;
  347 │       double lv=(double)SymbolInfoInteger(_Symbol,SYMBOL_TRADE_STOPS_LEVEL)*_Point;
  348 │       if(sig.sl>entry-lv) sig.sl=entry-lv;
  349 │    }
  350 │    else
  351 │    {
  352 │       sig.sl=MathMax(sl, entry+buf);
  353 │       sig.tp=entry-risk*TakeProfitRR;
  354 │       double lv=(double)SymbolInfoInteger(_Symbol,SYMBOL_TRADE_STOPS_LEVEL)*_Point;
  355 │       if(sig.sl<entry+lv) sig.sl=entry+lv;
  356 │    }
  357 │    sig.sl=NormalizeDouble(sig.sl,_Digits);
  358 │    sig.tp=NormalizeDouble(sig.tp,_Digits);
  359 │ }
  360 │ 
  361 │ //==================================================================
  362 │ //  STRATEGIES
  363 │ //==================================================================
  364 │ 
  365 │ //--- 1. HOLY GRAIL : premiere/deuxieme cassure du support de l'EMA20 en tendance haussiere
  366 │ bool SignalHolyGrail(MqlRates &r[], SSignal &sig)
  367 │ {
  368 │    if(!IsUptrend(r)) return false;
  369 │ 
  370 │    int touches=0, lastTouch=-1;
  371 │    double lowest=EMPTY_VALUE;
  372 │    for(int i=1;i<30 && i<ArraySize(r);i++)
  373 │    {
  374 │       if(r[i].low<=ma20Buf[i]*1.004 && r[i].low>=ma20Buf[i]*0.992)
  375 │       {
  376 │          touches++;
  377 │          if(lastTouch<0) lastTouch=i;
  378 │          if(lowest==EMPTY_VALUE || r[i].low<lowest) lowest=r[i].low;
  379 │       }
  380 │    }
  381 │    if(touches<1 || touches>2) return false;           // livre: 1er ou 2eme test seulement
  382 │    if(lastTouch<0 || lastTouch>6) return false;        // le test doit etre recent
  383 │ 
  384 │    double avg=AvgVolume(r,0,VolAvgPeriod);
  385 │    double avgPull=AvgVolume(r,0,5);
  386 │    if(avg>0 && avgPull>avg*VolPullbackMaxRatio) return false; // pullback sur faible volume ("smart pullback")
  387 │ 
  388 │    bool reversal=IsHammer(r,1) || IsBullEngulf(r,1) ||
  389 │                  (r[1].close>r[1].open && r[1].close>ma20Buf[1]);
  390 │    if(!reversal) return false;
  391 │    if(r[1].close<=r[2].high) return false;             // confirmation : cassure du haut de la bougie de repli
  392 │ 
  393 │    double sl=lowest-StopBufferPrice();
  394 │    BuildSignal(sig,SIG_BUY,S_HOLYGRAIL,sl,r[1].close,"HolyGrail");
  395 │    return (sig.dir==SIG_BUY);
  396 │ }
  397 │ 
  398 │ //--- 2. FALLING WEDGE : coin descendant en tendance haussiere + divergence haussiere
  399 │ bool SignalFallingWedge(MqlRates &r[], SSignal &sig)
  400 │ {
  401 │    if(!IsUptrend(r)) return false;
  402 │    int pl[12], ph[12];
  403 │    int npl=FindPivots(r,true,pl,12,2,WedgeBars+3);
  404 │    int nph=FindPivots(r,false,ph,12,2,WedgeBars+3);
  405 │    if(npl<2 || nph<2) return false;
  406 │ 
  407 │    int iPL=pl[0], oPL=pl[1], iPH=ph[0], oPH=ph[1];
  408 │    bool lowerLow  = r[iPL].low  < r[oPL].low;
  409 │    bool lowerHigh = r[iPH].high < r[oPH].high;
  410 │    bool converging=(r[iPH].high-r[iPL].low) < (r[oPH].high-r[oPL].low);
  411 │    if(!lowerLow || !lowerHigh || !converging) return false;
  412 │    if(!BullDivergence(iPL,oPL)) return false;
  413 │    if(r[1].close<=r[iPH].high) return false;           // cassure de la resistance descendante
  414 │ 
  415 │    double sl=r[iPL].low-StopBufferPrice();
  416 │    BuildSignal(sig,SIG_BUY,S_FALLWEDGE,sl,r[1].close,"FallingWedge");
  417 │    return (sig.dir==SIG_BUY);
  418 │ }
  419 │ 
  420 │ //--- 3. BREAKOUT & RETEST : cassure sur volume puis retest sur faible volume
  421 │ bool SignalBreakoutRetest(MqlRates &r[], SSignal &sig)
  422 │ {
  423 │    if(IsDowntrend(r)) return false;
  424 │    int sz=ArraySize(r);
  425 │    double resistance=0;
  426 │    for(int i=10;i<45 && i<sz;i++) resistance=MathMax(resistance,r[i].high);
  427 │    if(resistance<=0) return false;
  428 │ 
  429 │    double avg=AvgVolume(r,0,VolAvgPeriod);
  430 │    int breakBar=-1;
  431 │    for(int j=1;j<=10 && j<sz;j++)
  432 │    {
  433 │       if(r[j].close>resistance && r[j].tick_volume>avg*VolSpikeRatio){ breakBar=j; break; }
  434 │    }
  435 │    if(breakBar<0) return false;
  436 │ 
  437 │    // le retest doit se faire au-dessus de l'ancienne resistance, sur un volume plus faible
  438 │    double minLow=EMPTY_VALUE;
  439 │    for(int k=0;k<breakBar;k++)
  440 │    {
  441 │       if(r[k].low<minLow || minLow==EMPTY_VALUE) minLow=r[k].low;
  442 │    }
  443 │    if(minLow<resistance-StopBufferPrice()) return false; // le support a cede -> echec
  444 │    double retestVol=AvgVolume(r,0,breakBar+1);
  445 │    if(retestVol>r[breakBar].tick_volume*0.8) return false;
  446 │ 
  447 │    if(!(IsHammer(r,1) || r[1].close>r[2].high)) return false;
  448 │ 
  449 │    double sl=minLow-StopBufferPrice();
  450 │    BuildSignal(sig,SIG_BUY,S_BREAKOUT,sl,r[1].close,"BreakoutRetest");
  451 │    return (sig.dir==SIG_BUY);
  452 │ }
  453 │ 
  454 │ //--- 4. DOUBLE BOTTOM DIVERGENCE (strategie des marchés lateraux)
  455 │ bool SignalDoubleBottom(MqlRates &r[], SSignal &sig)
  456 │ {
  457 │    int pl[12];
  458 │    int npl=FindPivots(r,true,pl,12,2,35);
  459 │    if(npl<2) return false;
  460 │    int i1=pl[0], i2=pl[1];
  461 │    double p1=r[i1].low, p2=r[i2].low;
  462 │    if(MathAbs(p1-p2)/p1>0.015) return false;           // deux creux de niveau similaire
  463 │    if(!BullDivergence(i1,i2)) return false;
  464 │    if(!(IsHammer(r,1) || IsBullEngulf(r,1) || r[1].close>r[2].high)) return false;
  465 │ 
  466 │    double sl=MathMin(p1,p2)-StopBufferPrice();
  467 │    BuildSignal(sig,SIG_BUY,S_DOUBLEBOTTOM,sl,r[1].close,"DoubleBottomDivergence");
  468 │    return (sig.dir==SIG_BUY);
  469 │ }
  470 │ 
  471 │ //--- 5. 2B BOTTOM REVERSAL : cassure du premier creux puis recapture (failed breakdown)
  472 │ bool Signal2B(MqlRates &r[], SSignal &sig)
  473 │ {
  474 │    int pl[12];
  475 │    int npl=FindPivots(r,true,pl,12,2,45);
  476 │    if(npl<2) return false;
  477 │    int iDeep=pl[0], iFirst=pl[1];
  478 │    double firstLow=r[iFirst].low, deepLow=r[iDeep].low;
  479 │    if(deepLow>=firstLow) return false;                  // doit casser sous le 1er creux
  480 │    // recapture : une bougie plus recente que le 2eme creux clôture au-dessus du 1er creux
  481 │    bool recaptured=false;
  482 │    for(int k=0;k<iDeep;k++)
  483 │       if(r[k].close>firstLow){ recaptured=true; break; }
  484 │    if(!recaptured) return false;
  485 │    if(r[1].close<=r[2].high) return false;              // confirmation de la reversal
  486 │ 
  487 │    double sl=deepLow-StopBufferPrice();
  488 │    BuildSignal(sig,SIG_BUY,S_2B,sl,r[1].close,"2BBottomReversal");
  489 │    return (sig.dir==SIG_BUY);
  490 │ }
  491 │ 
  492 │ //--- 6. DIVERGENCE RSI/MACD generique (retournement haussier)
  493 │ bool SignalDivergence(MqlRates &r[], SSignal &sig)
  494 │ {
  495 │    int pl[12];
  496 │    int npl=FindPivots(r,true,pl,12,2,45);
  497 │    if(npl<2) return false;
  498 │    int iR=pl[0], iO=pl[1];
  499 │    if(r[iR].low>=r[iO].low) return false;               // prix fait un plus bas
  500 │    if(!BullDivergence(iR,iO)) return false;             // indicateur fait un plus haut
  501 │    if(!(IsHammer(r,1) || r[1].close>r[2].high)) return false;
  502 │ 
  503 │    double sl=r[iR].low-StopBufferPrice();
  504 │    BuildSignal(sig,SIG_BUY,S_DIVERGENCE,sl,r[1].close,"RSI_MACD_Divergence");
  505 │    return (sig.dir==SIG_BUY);
  506 │ }
  507 │ 
  508 │ //--- 7. RISING WEDGE : coin montant en tendance baissiere (short)
  509 │ bool SignalRisingWedge(MqlRates &r[], SSignal &sig)
  510 │ {
  511 │    if(!IsDowntrend(r)) return false;
  512 │    int pl[12], ph[12];
  513 │    int npl=FindPivots(r,true,pl,12,2,WedgeBars+3);
  514 │    int nph=FindPivots(r,false,ph,12,2,WedgeBars+3);
  515 │    if(npl<2 || nph<2) return false;
  516 │ 
  517 │    int iPL=pl[0], oPL=pl[1], iPH=ph[0], oPH=ph[1];
  518 │    bool higherLow  = r[iPL].low  > r[oPL].low;
  519 │    bool higherHigh = r[iPH].high > r[oPH].high;
  520 │    bool converging=(r[iPH].high-r[iPL].low) < (r[oPH].high-r[oPL].low);
  521 │    if(!higherLow || !higherHigh || !converging) return false;
  522 │    if(!BearDivergence(iPH,oPH)) return false;
  523 │    if(r[1].close>=r[iPL].low) return false;             // cassure du support montant
  524 │ 
  525 │    double sl=r[iPH].high+StopBufferPrice();
  526 │    BuildSignal(sig,SIG_SELL,S_RISINGWEDGE,sl,r[1].close,"RisingWedge");
  527 │    return (sig.dir==SIG_SELL);
  528 │ }
  529 │ 
  530 │ //==================================================================
  531 │ //  RECHERCHE DE SIGNAL (priorite du livre)
  532 │ //==================================================================
  533 │ bool GetSignal(SSignal &sig)
  534 │ {
  535 │    sig.dir=SIG_NONE;
  536 │    int n=LookbackBars+10;
  537 │    MqlRates r[];
  538 │    ArrayResize(r,n);
  539 │    ArraySetAsSeries(r,true);
  540 │    if(CopyRates(_Symbol,_Period,0,n,r)<n) return false;
  541 │    if(!PrepareData(n)) return false;
  542 │ 
  543 │    if(EnableHolyGrail       && SignalHolyGrail(r,sig))       return true;
  544 │    if(EnableFallingWedge    && SignalFallingWedge(r,sig))    return true;
  545 │    if(EnableBreakoutRetest  && SignalBreakoutRetest(r,sig))  return true;
  546 │    if(EnableDoubleBottomDiv && SignalDoubleBottom(r,sig))    return true;
  547 │    if(Enable2BReversal      && Signal2B(r,sig))              return true;
  548 │    if(EnableDivergence      && SignalDivergence(r,sig))      return true;
  549 │    if(EnableRisingWedge     && SignalRisingWedge(r,sig))     return true;
  550 │    return false;
  551 │ }
  552 │ 
  553 │ //==================================================================
  554 │ //  GESTION DES POSITIONS / STAIL STEP STOP
  555 │ //==================================================================
  556 │ int CountOurPositions()
  557 │ {
  558 │    int c=0;
  559 │    for(int i=PositionsTotal()-1;i>=0;i--)
  560 │    {
  561 │       ulong t=PositionGetTicket(i);
  562 │       if(!PositionSelectByTicket(t)) continue;
  563 │       if(PositionGetString(POSITION_SYMBOL)!=_Symbol) continue;
  564 │       ulong m=PositionGetInteger(POSITION_MAGIC);
  565 │       if(m>=MagicBase && m<=MagicBase+100) c++;
  566 │    }
  567 │    return c;
  568 │ }
  569 │ 
  570 │ double CalcLots(double sl, int dir)
  571 │ {
  572 │    double price=(dir==SIG_BUY? SymbolInfoDouble(_Symbol,SYMBOL_ASK) : SymbolInfoDouble(_Symbol,SYMBOL_BID));
  573 │    double dist=MathAbs(price-sl);
  574 │    if(dist<=0) return 0;
  575 │    double tv=SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_VALUE);
  576 │    double ts=SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_SIZE);
  577 │    if(ts<=0) ts=_Point;
  578 │    if(tv<=0) return 0;
  579 │ 
  580 │    double moneyPerUnit=tv/ts;
  581 │    double risk=AccountInfoDouble(ACCOUNT_BALANCE)*RiskPercentPerTrade/100.0;
  582 │    double lots=risk/(dist*moneyPerUnit);
  583 │ 
  584 │    // plafond 10% du capital immobilise (regle du livre)
  585 │    double cs=SymbolInfoDouble(_Symbol,SYMBOL_TRADE_CONTRACT_SIZE);
  586 │    if(cs>0)
  587 │    {
  588 │       double cap=AccountInfoDouble(ACCOUNT_EQUITY)*MaxCapitalPerTradePct/100.0;
  589 │       double notionalPerLot=cs*price;
  590 │       if(notionalPerLot>0) lots=MathMin(lots,cap/notionalPerLot);
  591 │    }
  592 │ 
  593 │    double vmin=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MIN);
  594 │    double vmax=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MAX);
  595 │    double vstep=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_STEP);
  596 │    if(vstep<=0) vstep=vmin;
  597 │    lots=MathFloor(lots/vstep)*vstep;
  598 │    lots=MathMax(lots,vmin);
  599 │    lots=MathMin(lots,vmax);
  600 │    return NormalizeDouble(lots,2);
  601 │ }
  602 │ 
  603 │ bool PositionIsONH(ulong magic)
  604 │ {
  605 │    return (magic==MagicBase+S_ONH);
  606 │ }
  607 │ 
  608 │ void ManageOpenPositions()
  609 │ {
  610 │    MqlRates r[];
  611 │    ArrayResize(r,3);
  612 │    ArraySetAsSeries(r,true);
  613 │    ENUM_TIMEFRAMES tf=StairUseDaily? PERIOD_D1 : _Period;
  614 │    int n=CopyRates(_Symbol,tf,0,3,r);
  615 │    if(n<2) return;
  616 │ 
  617 │    double bid=SymbolInfoDouble(_Symbol,SYMBOL_BID);
  618 │    double ask=SymbolInfoDouble(_Symbol,SYMBOL_ASK);
  619 │    double stopsLvl=(double)SymbolInfoInteger(_Symbol,SYMBOL_TRADE_STOPS_LEVEL)*_Point;
  620 │ 
  621 │    for(int i=PositionsTotal()-1;i>=0;i--)
  622 │    {
  623 │       ulong ticket=PositionGetTicket(i);
  624 │       if(!PositionSelectByTicket(ticket)) continue;
  625 │       if(PositionGetString(POSITION_SYMBOL)!=_Symbol) continue;
  626 │       ulong magic=PositionGetInteger(POSITION_MAGIC);
  627 │       if(magic<MagicBase || magic>MagicBase+100) continue;
  628 │ 
  629 │       bool isBuy=(PositionGetInteger(POSITION_TYPE)==POSITION_TYPE_BUY);
  630 │       double op=PositionGetDouble(POSITION_PRICE_OPEN);
  631 │       double sl=PositionGetDouble(POSITION_SL);
  632 │       double tp=PositionGetDouble(POSITION_TP);
  633 │ 
  634 │       //--- sortie ONH a l'ouverture de la session suivante
  635 │       if(PositionIsONH(magic))
  636 │       {
  637 │          MqlDateTime dt; TimeToStruct(TimeCurrent(),dt);
  638 │          if(dt.hour>=ONHExitHour && dt.hour<=ONHExitHour+1)
  639 │             trade.PositionClose(ticket);
  640 │          continue;
  641 │       }
  642 │ 
  643 │       if(!EnableTrailing) continue;
  644 │ 
  645 │       //--- Stair Step Stop Loss : stop sous le plus bas de la bougie precedente (long)
  646 │       double ref=isBuy? r[1].low : r[1].high;
  647 │       double buf=UseATRTrailing? StairATRMult*atrBuf[1] : StairStepBufferPips*_Point;
  648 │       double newSL=isBuy? ref-buf : ref+buf;
  649 │ 
  650 │       //--- passage en break-even
  651 │       double profitPips=isBuy? (bid-op)/_Point : (op-ask)/_Point;
  652 │       if(profitPips>=BreakEvenAfterPips)
  653 │       {
  654 │          if(isBuy && op>newSL) newSL=op;
  655 │          if(!isBuy && op<newSL) newSL=op;
  656 │       }
  657 │ 
  658 │       //--- securite : distance minimale au prix
  659 │       if(isBuy && newSL>bid-stopsLvl) newSL=bid-stopsLvl;
  660 │       if(!isBuy && newSL<ask+stopsLvl) newSL=ask+stopsLvl;
  661 │ 
  662 │       newSL=NormalizeDouble(newSL,_Digits);
  663 │       bool improved=isBuy? (newSL>sl+_Point) : (sl<=0 || newSL<sl-_Point);
  664 │       if(improved && newSL>0)
  665 │          trade.PositionModify(ticket,newSL,tp);
  666 │    }
  667 │ }
  668 │ 
  669 │ //==================================================================
  670 │ //  OVER NIGHT HOLD (fin de seance)
  671 │ //==================================================================
  672 │ void CheckONH()
  673 │ {
  674 │    if(!EnableONH) return;
  675 │    MqlDateTime dt; TimeToStruct(TimeCurrent(),dt);
  676 │    if(dt.hour!=ONHCloseHour || dt.min<ONHCloseMinute) return;
  677 │    if(lastONHDay==dt.day) return;
  678 │ 
  679 │    if(CountOurPositions()>=MaxOpenPositions) return;
  680 │    if(SymbolInfoInteger(_Symbol,SYMBOL_SPREAD)>MaxSpreadPoints) return;
  681 │ 
  682 │    MqlRates d[];
  683 │    ArrayResize(d,VolAvgPeriod+2);
  684 │    ArraySetAsSeries(d,true);
  685 │    if(CopyRates(_Symbol,PERIOD_D1,0,VolAvgPeriod+2,d)<VolAvgPeriod+2) return;
  686 │ 
  687 │    double rng=d[0].high-d[0].low;
  688 │    if(rng<=0) return;
  689 │    double locLong=(d[0].close-d[0].low)/rng;   // proche de 1 = cloture au plus haut
  690 │    double locShort=(d[0].high-d[0].close)/rng; // proche de 1 = cloture au plus bas
  691 │    double avg=AvgVolume(d,1,VolAvgPeriod);
  692 │    bool volOK=(avg>0 && d[0].tick_volume>avg*ONHVolumeRatio);
  693 │ 
  694 │    int dir=SIG_NONE;
  695 │    if(volOK && locLong>=ONHCloseLocationMin) dir=SIG_BUY;
  696 │    else if(volOK && locShort>=ONHCloseLocationMin) dir=SIG_SELL;
  697 │    if(dir==SIG_NONE) return;
  698 │ 
  699 │    double sl=(dir==SIG_BUY)? d[0].low-StopBufferPrice() : d[0].high+StopBufferPrice();
  700 │    SSignal sig;
  701 │    BuildSignal(sig,dir,S_ONH,sl,d[0].close,"OverNightHold");
  702 │    if(sig.dir==SIG_NONE) return;
  703 │ 
  704 │    double lots=CalcLots(sig.sl,dir);
  705 │    if(lots<=0) return;
  706 │    trade.SetExpertMagicNumber(MagicBase+S_ONH);
  707 │    bool ok=(dir==SIG_BUY)? trade.Buy(lots,_Symbol,0.0,sig.sl,sig.tp,sig.name)
  708 │                          : trade.Sell(lots,_Symbol,0.0,sig.sl,sig.tp,sig.name);
  709 │    if(ok) lastONHDay=dt.day;
  710 │    Print("ONH ",(dir==SIG_BUY?"BUY":"SELL")," ",ok?"OK":"ECHEC ",trade.ResultRetcodeDescription());
  711 │ }
  712 │ 
  713 │ //==================================================================
  714 │ //  EXECUTION
  715 │ //==================================================================
  716 │ bool ExecuteSignal(SSignal &sig)
  717 │ {
  718 │    if(CountOurPositions()>=MaxOpenPositions) return false;
  719 │    double lots=CalcLots(sig.sl,sig.dir);
  720 │    if(lots<=0) return false;
  721 │ 
  722 │    trade.SetExpertMagicNumber(MagicBase+sig.sid);
  723 │    bool ok=(sig.dir==SIG_BUY)? trade.Buy(lots,_Symbol,0.0,sig.sl,sig.tp,sig.name)
  724 │                              : trade.Sell(lots,_Symbol,0.0,sig.sl,sig.tp,sig.name);
  725 │    if(ok)
  726 │       Print("SIGNAL ",sig.name," ",(sig.dir==SIG_BUY?"BUY":"SELL")," lots=",lots,
  727 │             " SL=",sig.sl," TP=",sig.tp);
  728 │    else
  729 │       Print("Echec ordre ",sig.name," : ",trade.ResultRetcodeDescription());
  730 │    return ok;
  731 │ }
  732 │ 
  733 │ //==================================================================
  734 │ //  AFFICHAGE DE L'ETAT SUR LE GRAPHIQUE
  735 │ //==================================================================
  736 │ void ShowStatus()
  737 │ {
  738 │    if(!ShowStatusOnChart){ Comment(""); return; }
  739 │ 
  740 │    int spread=(int)SymbolInfoInteger(_Symbol,SYMBOL_SPREAD);
  741 │    string tendance="NEUTRE";
  742 │    if(ArraySize(ma20Buf)>5 && ArraySize(ma50Buf)>5)
  743 │    {
  744 │       if(ma20Buf[1]>ma50Buf[1])        tendance="HAUSSE";
  745 │       else if(ma20Buf[1]<ma50Buf[1])   tendance="BAISSE";
  746 │    }
  747 │    string when=(gLastSignalTime>0? " ("+TimeToString(gLastSignalTime,TIME_MINUTES)+")" : "");
  748 │ 
  749 │    string s="===== ArtOfTrading_EA : EN LIGNE =====\n";
  750 │    s+="Robot actif - il attend un setup (regle 1 du livre)\n";
  751 │    s+="Heure serveur : "+TimeToString(TimeCurrent(),TIME_DATE|TIME_SECONDS)+"\n";
  752 │    s+="Spread : "+IntegerToString(spread)+" pts (max "+IntegerToString(MaxSpreadPoints)+")\n";
  753 │    s+="ADX : "+DoubleToString(gLastADX,1)+" (min "+IntegerToString(ADXMinTrend)+") | Tendance : "+tendance+"\n";
  754 │    s+="Positions : "+IntegerToString(CountOurPositions())+" / "+IntegerToString(MaxOpenPositions)+"\n";
  755 │    s+="Dernier signal : "+gLastSignal+when+"\n";
  756 │    s+="Pas de trade = pas de configuration valide. C'est normal.";
  757 │    Comment(s);
  758 │ }
  759 │ 
  760 │ //==================================================================
  761 │ //  BOUCLE PRINCIPALE
  762 │ //==================================================================
  763 │ void OnTick()
  764 │ {
  765 │    if(!MQLInfoInteger(MQL_TRADE_ALLOWED)) return;
  766 │    if(SymbolInfoInteger(_Symbol,SYMBOL_TRADE_MODE)==SYMBOL_TRADE_MODE_DISABLED) return;
  767 │    if(SymbolInfoInteger(_Symbol,SYMBOL_SPREAD)>MaxSpreadPoints) return;
  768 │ 
  769 │    ManageOpenPositions();
  770 │ 
  771 │    if((!TradeOnNewBarOnly || IsNewBar()) && DailyLossOK())
  772 │    {
  773 │       SSignal sig;
  774 │       if(GetSignal(sig))
  775 │       {
  776 │          gLastSignal=sig.name;
  777 │          gLastSignalTime=TimeCurrent();
  778 │          ExecuteSignal(sig);
  779 │       }
  780 │    }
  781 │ 
  782 │    CheckONH();
  783 │    ShowStatus();
  784 │ }
  785 │ //+------------------------------------------------------------------+
  786 │ 