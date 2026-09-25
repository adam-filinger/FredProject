import sqlite3
import pandas as pd
import json

DB_FILE = "macroscope.db"



def init_db():
    """Initializes the SQLite database with tables for cached series and user configurations."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # 1. Cached Series Data (Historical Observations)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stock (
            ID INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            currency TEXT,
            last_updated date
        )
    """)
    
    # 2. User Dashboard Configurations & Bookmarks (Future expansion)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS price_data (
            stock_id INTEGER,
            time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            price INTEGER,
            FOREIGN KEY (stock_id) REFERENCES stock(ID)
            PRIMARY KEY (stock_id, time)
        )
    """)
    
    conn.commit()
    conn.close()

def save_stock(stock_name, currency, last_updated):
    """Saves fetched Pandas DataFrame series observations into the persistent disk cache."""
    if df.empty:
        return
    
    conn = sqlite3.connect(DB_FILE)
    # Prepare DataFrame for SQL insertion
    temp_df = df.reset_index()
    temp_df.columns = ['date', 'value']
    temp_df['series_id'] = series_id
    temp_df['units'] = units
    temp_df['frequency'] = frequency
    temp_df['aggregation_method'] = aggregation_method
    
    # Write to SQL (replace on conflict to update with newer values)
    temp_df.to_sql('cached_series', conn, if_exists='append', index=False, method='multi')
    conn.close()

def get_series_from_db(series_id, units, frequency, aggregation_method):
    """Checks if the specific configured series is stored in our persistent SQL cache."""
    conn = sqlite3.connect(DB_FILE)
    query = """
        SELECT date, value FROM cached_series 
        WHERE series_id = ? AND units = ? AND frequency = ? AND aggregation_method = ?
        ORDER BY date ASC
    """
    df = pd.read_sql_query(query, conn, params=(series_id, units, frequency, aggregation_method), parse_dates=['date'])
    conn.close()
    if not df.empty:
        return df.set_index('date')['value']
    return None


init_db()  # Initialize the database when the module is imported