import plotly.express as px
import plotly.graph_objects as go
import pandas as pd

def plot_timeline(df, title="Macroeconomic Indicator", units="Value"):
    """Generates an interactive Plotly timeline from a Pandas Series or DataFrame."""
    if df is None or df.empty:
        # Return empty figure with warning title
        fig = go.Figure()
        fig.update_layout(title="No Data Available")
        return fig
    
    # Prepare DataFrame for Plotly Express
    plot_df = df.reset_index()
    plot_df.columns = ['Date', 'Value']
    
    fig = px.line(
        plot_df, 
        x='Date', 
        y='Value', 
        title=f"{title} ({units})",
        labels={'Value': units, 'Date': 'Timeline'}
    )
    
    # Custom aesthetic adjustments
    fig.update_layout(
        template="plotly_white",
        hovermode="x unified",
        xaxis=dict(showgrid=True, rangeslider=dict(visible=True)),
        yaxis=dict(showgrid=True)
    )
    return fig
