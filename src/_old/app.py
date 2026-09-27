import streamlit as st
import data_fetcher as df_fetcher
import charts as charts
import database as db

# UI Layout configuration
st.set_page_config(page_title="MacroScope - Macroeconomic Insights", layout="wide")

# Ensure SQL persistence layer is initialized
db.init_db()

st.title("📊 MacroScope")
st.subheader("Visualizing global economic indicators using FRED")

# Sidebar navigation
app_mode = st.sidebar.selectbox("Choose Mode", ["Macro Snapshot", "Custom Search", "Revision Tracker"])

if app_mode == "Macro Snapshot":
    st.info("Macro Snapshot under construction. Soon displaying Curated Core Indicators.")

elif app_mode == "Custom Search":
    st.write("### 🔍 Search macroeconomic data")
    search_query = st.text_input("Enter key words (e.g., 'GDP of America', 'unemployment'):", "")
    
    if search_query:
        try:
            results = df_fetcher.search_series(search_query)
            if not results.empty:
                st.write("#### Search Results (Sorted by Popularity):")
                # Showing ID, Title, Frequency, Units
                st.dataframe(results[['id', 'title', 'frequency', 'units', 'popularity']])
                
                # Selection dropdown or trigger Dialog configuration
                selected_id = st.selectbox("Select a Series ID to configure and visualize:", results['id'].tolist())
                
                # Metadata notes expander
                selected_row = results[results['id'] == selected_id].iloc[0]
                with st.expander("ℹ️ Show Series Metadata / Description"):
                    st.write(selected_row.get('notes', 'No description available.'))
                
                # Config & Plot trigger
                if st.button("Configure & Visualize"):
                    st.success(f"Series selected: {selected_id}. Ready to configure and plot.")
                    df_fetcher.configure_series_dialog(selected_id, selected_row['title'])
                    
            else:
                st.warning("No matches found. Try another query.")
        except Exception as e:
            st.error(f"Initialization required: Please verify FRED_API_KEY is properly set up. Details: {e}")

elif app_mode == "Revision Tracker":
    st.info("Revision Tracker (ALFRED) under construction. Soon displaying point-in-time data releases.")
