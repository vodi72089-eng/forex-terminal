# ArtOfTrading_EA (MetaTrader 5)

Expert Advisor inspire du livre *Inside the Mind of Trader Stewie* (239 pages).
Compile avec 0 erreur / 0 warning sur MetaEditor 5 (build 2026).

> AVERTISSEMENT : outil educatif, pas un conseil en investissement. Le trading comporte un risque de perte en capital. Teste toujours sur compte demo avant toute utilisation en reel.

## Strategies implémentées

| Strategie du livre | Fonction |
|---|---|
| Holy Grail — 1er/2e pullback sur EMA20, smart pullback faible volume, Hammer | `SignalHolyGrail()` |
| Falling Wedge — coin descendant + divergence RSI/MACD | `SignalFallingWedge()` |
| Breakout & Retest — cassure sur volume puis retest faible volume | `SignalBreakoutRetest()` |
| Double Bottom Divergence — marche laterale | `SignalDoubleBottom()` |
| 2B Bottom Reversal (Trader Vic) — failed breakdown | `Signal2B()` |
| Divergence RSI/MACD generique | `SignalDivergence()` |
| Rising Wedge — version short | `SignalRisingWedge()` |
| Over Night Hold (ONH) — entree avant cloture sur HOD + volume | `CheckONH()` |
| Stair Step Stop Loss — stop sous le plus bas de la bougie precedente | `ManageOpenPositions()` |
| Money management — 1% risque/trade, 10% capital/position, 6 positions max | `CalcLots()` |

## Installation

1. Copier `ArtOfTrading_EA.mq5` dans `MQL5/Experts/` du terminal MT5.
2. Ouvrir MetaEditor et compiler (F7) pour generer `ArtOfTrading_EA.ex5`.
3. Dans MT5, glisser l'EA sur un graphique et cocher « Autoriser le trading automatique ».
4. Activer le bouton « Trading Algo » (AutoTrading).

L'EA affiche directement son etat sur le graphique (`ShowStatusOnChart = true`) : heure serveur, spread, ADX, tendance, positions ouvertes, dernier signal.

## Parametres importants

- `RiskPercentPerTrade = 1.0` — risque maximum par trade (regle du livre).
- `MaxCapitalPerTradePct = 10.0` — capital maximum immobilise par trade.
- `MaxOpenPositions = 6` — nombre maximum de positions.
- `TakeProfitRR = 3.0` — ratio risk/reward vise (1:3 a 1:5 dans le livre).
- `StairUseDaily = true` — trail base sur la bougie journaliere.
- `EnableONH = false` — a activer seulement apres reglage de `ONHCloseHour` selon l'heure du serveur du courtier.

## Limites connues

Les elements du livre lies aux actions US ne sont pas disponibles dans MT5 sans donnees externes : Power Earnings Gap (calendrier des resultats), Short Interest, NYMO/NAMO. Le volume utilise `tick_volume` comme proxy.

## Recommandations

Backtest sur 12 mois en « Every tick based on real ticks », puis forward test sur demo avant tout passage en reel.
