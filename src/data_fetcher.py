import os
import pandas as pd
import streamlit as st
from fredapi import Fred
from dotenv import load_dotenv
import database as db

# Load environment variables
load_dotenv()

# Secure client initialization
@st.cache_resource
def get_fred_client():
    """Initializes and caches the FRED API wrapper instance."""
    api_key = os.getenv("FRED_API_KEY")
    if not api_key:
        # Fallback to Streamlit secrets if running in cloud, or raise error
        api_key = st.secrets.get("FRED_API_KEY") if "FRED_API_KEY" in st.secrets else None
    
    if not api_key:
        raise ValueError("FRED_API_KEY not found in environment variables or Streamlit secrets.")
    return Fred(api_key=api_key)

@st.cache_data(ttl=3600)  # In-memory "Hot" Cache
def search_series(query):
    """Calls fredapi to perform a full-text search and returns sorted results."""
    fred = get_fred_client()
    results = fred.search(query)
    if results is not None and not results.empty:
        # Sort by popularity or default release patterns
        return results.sort_values(by='popularity', ascending=False)
    return pd.DataFrame()

def get_series_observations(series_id, units='lin', frequency=None, aggregation_method='avg'):
    """
    Retrieves series observations using the Hybrid Caching mechanism.
    Checks SQL Database (Persistent Cache) first, falls back to Fred API, then saves to DB.
    """
    # 1. Check Cold (Persistent) Cache
    cached_data = db.get_series_from_db(series_id, units, frequency, aggregation_method)
    if cached_data is not None and not cached_data.empty:
        return cached_data
    
    # 2. Fetch from FRED API
    fred = get_fred_client()
    try:
        # Fetching raw or server-side transformed series
        # fredapi get_series can accept extra FRED params like units, frequency, aggregation_method
        data = fred.get_series(series_id, units=units, frequency=frequency, aggregation_method=aggregation_method)
        
        # 3. Save to SQL database for durability
        if data is not None and not data.empty:
            df = pd.DataFrame(data)
            db.save_series_to_db(series_id, df, units, frequency, aggregation_method)
            return data
    except Exception as e:
        st.error(f"Error fetching series {series_id} from FRED: {str(e)}")
    
    return pd.Series()


# Modern Streamlit Dialog Modal for customizing parameters
@st.dialog("Configure Series Transformation")
def configure_series_dialog(series_id, title):
    st.markdown(f"Configure settings for: **{title}** (`{series_id}`)")
    
    # 1. Select Transformation Units
    units = st.selectbox(
        "Units (Transformation)",
        options=["lin", "chg", "pch", "pc1", "log"],
        index=0,
        format_func=lambda x: {
            "lin": "Raw Data / Index Level",
            "chg": "Absolute Change (Δ)",
            "pch": "% Change (Period-over-Period)",
            "pc1": "% Change (Year-over-Year)",
            "log": "Natural Logarithm"
        }[x]
    )
    
    # 2. Select Custom Frequency
    freq_opts = {
        "Default (Original)": None,
        "Daily": "d",
        "Weekly": "w",
        "Monthly": "m",
        "Quarterly": "q",
        "Annual": "a"
    }
    frequency_key = st.selectbox("Frequency Modification", options=list(freq_opts.keys()))
    frequency = freq_opts[frequency_key]
    
    # 3. Select Aggregation Method
    aggregation_method = st.selectbox(
        "Aggregation Method (used if modifying frequency)",
        options=["avg", "sum", "eop"],
        index=0,
        format_func=lambda x: {
            "avg": "Average (avg)",
            "sum": "Sum (sum)",
            "eop": "End of Period (eop)"
        }[x]
    )
    
    st.markdown("---")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Generate Timeline", type="primary"):
            # Put configuration details in session state
            st.session_state["chart_config"] = {
                "series_id": series_id,
                "title": title,
                "units": units,
                "frequency": frequency,
                "aggregation_method": aggregation_method
            }
            st.rerun()
    with col2:
        if st.button("Cancel"):
            st.rerun()
