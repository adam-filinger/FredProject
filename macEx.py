import pandas as pd
import matplotlib.pyplot as plt
import ipywidgets as widgets
from fredapi import Fred as fredApi
from IPython.display import display
import os
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv('FRED_API_KEY')

fred = fredApi(api_key)

while(True):
    user_input = input("Enter a FRED series ID (or type 'exit' to quit): ")
    if user_input.lower() == 'exit':
        break
    try:
        series_data = fred.get_series(user_input)
        df = pd.DataFrame(series_data, columns=['Value'])
        df.index.name = 'Date'
        print(df.head())
        
        # Plotting the data
        plt.figure(figsize=(10, 5))
        plt.plot(df.index, df['Value'], label=user_input)
        plt.title(f'FRED Series: {user_input}')
        plt.xlabel('Date')
        plt.ylabel('Value')
        plt.legend()
        plt.grid()
        plt.show()
    except Exception as e:
        print(f"Error retrieving data for series ID '{user_input}': {e}")
