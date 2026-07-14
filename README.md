# MacroScope 📊

An interactive, production-grade macroeconomic data visualization and analysis platform powered by **Streamlit**, **Plotly**, and the **FRED API**.

---

## 📖 Project Overview

**MacroScope** is designed for economists, researchers, and financial developers who need a quick, highly responsive, and modular dashboard to parse global and national economic trends. Leveraging the Federal Reserve Economic Data (FRED) API, MacroScope allows users to query over 800,000 time-series datasets, visualize key indicators like GDP, CPI, and Unemployment, and dissect historical point-in-time data revisions (ALFRED) without leaving their browser.

The system emphasizes:
* **Clean Code Architecture:** Strict separation of concerns across presentation, business logic, configuration, and data storage.
* **Performance Optimization:** Protects rate limits through a unique **Hybrid Caching Engine**.
* **Intuitive User Journey:** Eliminates the need to memorize raw economic database parameters through human-readable transformation dialogs.

---

## 🛠️ Tech Stack

* **Frontend Framework:** [Streamlit](https://streamlit.io/) (Decoupled React-based UI orchestration)
* **Visualization Engine:** [Plotly Graph Objects & Express](https://plotly.com/python/) (Interactive, high-performance web charting)
* **Database & Persistence:** SQLite (Pure standard-library local persistence layer)
* **API Wrapper:** [fredapi](https://github.com/mortada/fredapi) (Python wrapper for Federal Reserve Economic Data)
* **Data Core:** Pandas & NumPy (Scientific analysis and time-series dataframe operations)

---

## 💡 Key Features & Functionality

### 1. Macro Snapshot Dashboard
* **Dynamic Core Indicators:** Quick-view dashboards tracking crucial indices such as Real Gross Domestic Product (Real GDP), Consumer Price Index (CPI/Inflation), Unemployment Rates, and the Federal Funds Rate.
* **Transformation Engines:** Seamless on-the-fly toggling between raw index values (`lin`), absolute change (`chg`), period-over-period percent change (`pch`), year-over-year percentage change (`pc1`), or natural logarithms (`log`).

### 2. Custom Search Engine
* **Full-text Querying:** Programmatic discovery using natural query terms (e.g., "unemployment rate of Texas" or "GDP of America"). Shows matching lists sorted by popular database downloads.
* **Dynamic Config Dialogs:** Modern Streamlit dialog modal pop-ups (`@st.dialog`) allow users to click a series, select custom frequencies (Daily, Weekly, Monthly, Quarterly, Annual), choose aggregation rules (Average, Sum, End of Period), and plot interactive timeframes.
* **Metadata Context Panel:** Integrates expanders to expose source information, data footnotes, and methodology notes directly inside the application.

### 3. Historical Revisions Tracker (ALFRED Integration)
* **Vintage Date Analysis:** Understands what data was known when by comparing initial estimates with subsequent revisions.
* **Realtime Analytics:** Maps `realtime_start` and `realtime_end` values over an economic timeline.

---

## ⚡ Architecture & Caching Strategy

The FRED API has a standard request limit of **120 requests per minute**. Because Streamlit executes scripts from top-to-bottom on every user click, MacroScope employs a **Hybrid Hot/Cold Caching Pipeline**:

```
                     +---------------------------+
                     | User Requests Data Series |
                     +-------------+-------------+
                                   |
                     [ Is it in Hot (RAM) Cache? ]
                     +-------------+-------------+
                               Yes | No
                                   |
           +-----------------------v-------------------------+
           | Serving Instantly (RAM)  [ Is it in SQL DB Cache? ]
           +-----------------------+-------------+-----------+
                                             Yes | No
                                                 |
             +-----------------------------------v-------------------------+
             | Reading from SQLite and  [ Fetch from Remote API (FRED) ]    |
             | Loading to RAM            +---------------+-----------------+
             +---------------------------+               |
                                                         v
                                              [ Save to SQLite & RAM ]
```

1. **Hot Cache (RAM):** Implemented using Streamlit's `@st.cache_data` decorator. Re-renders UI charts with microsecond-level latency during active application use.
2. **Cold Cache (Disk Persistence):** Uses a local SQLite database (`data/macroscope_cache.db`) to preserve historical observation data across app restarts, preparing the framework for bookmark storage and layout retention in future releases.

---

## 📂 Directory Structure

Our folder layout follows absolute separation of concerns to guarantee long-term stability and painless CI/CD deployment:

```text
macroscope/
│
├── .env.example             # Safe blueprint for API environments (no secrets)
├── .gitignore               # Ignores database files, local environment configurations, and virtual environments
├── README.md                # General documentation and quick start guide
├── requirements.txt         # Package dependency tree
├── pyproject.toml           # PEP 518 modern standard build tools configuration
│
├── assets/                  # UI assets and styles
│   └── custom.css           # Styling modifications override
│
├── data/                    # Storage directory for databases
│   ├── .gitkeep             # Holds empty directory under Git
│   └── macroscope_cache.db  # (Git-ignored) Persistent SQLite database cache
│
├── src/                     # Codebase package directory
│   ├── __init__.py          # Marks source files as importable Python modules
│   ├── app.py               # Main UI rendering, sidebar routing, and dialogue controller
│   ├── config.py            # Environment validation and path resolution utilities
│   ├── database.py          # SQLite schema, transaction logic, and reads/writes
│   ├── data_fetcher.py      # Core FRED client wrapper and Hybrid Caching router
│   └── charts.py            # Decoupled visualization mapping using Plotly interactive charts
│
└── tests/                   # Automated testing framework
    ├── __init__.py          
    ├── test_database.py     # Verifies SQLite schema creation and transaction procedures
    └── test_data_fetcher.py # Mocks API integration and validates error handling limits
```

---

## 🚀 Quick Start Tutorial

Follow these clear, step-by-step instructions to get the application up and running on your local machine (tested on macOS, Linux, and Windows).

### Prerequisites
* **Python 3.9+** installed on your machine.
* A free **FRED API Key**. Register for a key at: [St. Louis Fed API Keys](https://fred.stlouisfed.org/docs/api/api_key.html)

---

### Step 1: Clone the Repository
Open your Terminal (or Command Prompt) and execute:
```bash
git clone https://github.com/your-username/macroscope.git
cd macroscope
```

### Step 2: Configure Environment Variables
Create your local environment file by copying the template file:
```bash
cp .env.example .env
```
Open the `.env` file in your preferred text editor (e.g., VS Code, Vim, or Nano) and replace the placeholder value with your actual FRED API key:
```ini
FRED_API_KEY=your_actual_32_character_fred_api_key
```

### Step 3: Initialize Virtual Environment
Set up an isolated environment to prevent library conflicts:
```bash
# Create the environment
python3 -m venv venv

# Activate the environment (macOS/Linux)
source venv/bin/activate

# Activate the environment (Windows PowerShell)
.\venv\Scripts\Activate.ps1
```

### Step 4: Install Dependencies
Run the installation command to fetch all required libraries listed in our dependency config:
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 5: Start the App Server
Launch the application server utilizing the execution path from the project root:
```bash
streamlit run src/app.py
```

Streamlit will automatically build the components, trigger SQLite database initialization inside the `/data` folder, and open your default web browser to the application page (typically at `http://localhost:8501`).

---

## 🧪 Running Automated Tests

Keep your app codebase secure and stable. To verify directory layout paths and database integration functions, execute the standard unit test framework:
```bash
python -m unittest discover -s tests
```

---

## 🔮 Future Roadmap Plan

* **Saved Dashboard Layouts:** Storing custom search configurations and user selections locally inside the SQLite database to rebuild screens instantly.
* **NBER Recession Shading:** Adding automatic gray-shaded bars to Plotly timelines during historic US economic recessions.
* **Multi-Series Plotting:** Overlaying multiple series on a dual-Y axis or multi-panel charts to directly visualize key economic correlations (e.g., Fed Funds Rate vs. Core CPI inflation).
