# Pseudocode

For each trading day:

1. Update daily OHLCV data.
2. Calculate EMA20 and EMA50.
3. Calculate RSI14.
4. Calculate the highest High of the previous 20 sessions.
5. Calculate the previous 20-session average volume.
6. Mark a candidate when:
   - EMA20 > EMA50
   - Close > prior-20-session highest High
7. Calculate RSI/volume confirmation score.
8. Rank candidates.
9. Enter selected candidates at the next trading day's open.
10. For open positions:
    - gap through stop/target -> execute at open
    - if both stop and target are touched -> stop first
    - otherwise execute stop or target if touched
    - otherwise close at maximum holding period
11. Apply transaction costs and slippage.
12. Record trades and equity.
