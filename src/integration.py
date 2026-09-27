"""
integration.py - Pipeline orchestrator for the MacroScope yfinance pipeline.

Chains all modules in the correct order:
  1. db.init_all_tables()     -- ensure schema is up-to-date
  2. price_data.update_all()  -- incremental hourly price download
  3. financials.update_all()  -- today's fundamental snapshot
  4. quant.analyse_watchlist() -- compute BUY/HOLD/SELL signals
  5. output.print_report()    -- render formatted console report

Usage
-----
  # As a standalone script:
  python src/integration.py

  # From a notebook or another module:
  import sys; sys.path.insert(0, "src")
  import integration
  integration.update_all()
"""

import sys
import os

# Ensure src/ is on the path when run as a script
_SRC = os.path.dirname(os.path.abspath(__file__))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import db
import price_data
import financials
import quant
import output


def update_all(
    skip_prices: bool = False,
    skip_financials: bool = False,
) -> None:
    """
    Run the full pipeline end-to-end.

    Parameters
    ----------
    skip_prices     : skip the hourly price download step
    skip_financials : skip the fundamentals snapshot step
    """
    print("\n[1/5] Initialising database tables...")
    db.init_all_tables()

    if not skip_prices:
        print("\n[2/5] Updating price data...")
        price_data.update_all()
    else:
        print("\n[2/5] Skipping price data update.")

    if not skip_financials:
        print("\n[3/5] Updating financial snapshots...")
        financials.update_all()
    else:
        print("\n[3/5] Skipping financials update.")

    print("\n[4/5] Computing signals...")
    signals = quant.analyse_watchlist()

    print("\n[5/5] Generating report...")
    fin_pivot = financials.load_latest()
    output.print_report(signals, financials_df=fin_pivot)


if __name__ == "__main__":
    update_all()
