# Community Notes Dashboard

The **Community Notes Dashboard** is an interactive web application built with [Dash](https://dash.plotly.com/) and [Plotly](https://plotly.com/python/) that allows users to explore and analyse Community Notes data from X (formerly Twitter). Developed by [CheckFirst](https://checkfirst.network), the dashboard offers a wide range of visualisations and interactive features that help you understand note distribution, fact-checking usage, content trends, and more.

## Demo 

**A live version of the the Community Notes Dashboard [is available online](https://cn.kaksi.ovh/)**

## Features

- **Global Distribution:** Visualises the volume and spread of Community Notes across multiple languages over the last 30 days
- **Fact-Checking Usage:** Displays statistics and charts on notes that include external fact-checking links
- **Search:** Search for keywords within note summaries and see detailed results with links to the original tweets
- **Sources & Domains:** Shows the top domains referenced in the notes, distinguishing between media-based and tweet-based sources
- **Author & Participant Analysis:** Provides insights on unique authors and the distribution of notes per participant
- **Note Visibility & Responsiveness:** Compares the total number of notes versus displayed notes, and tracks how quickly notes are displayed
- **Ratio Displayed:** Displays the ratio of notes that are ultimately surfaced to users, based on preprocessed data
- **Interactive Filters:** Filter visualisations by language and timeframe

## Project Structure

```
├── app.py                   # Main Dash application script
├── community.py             # Helper functions (e.g., date parsing, domain extraction)
├── data/
│   ├── fc_stats.json        # Fact-checking statistics JSON file
│   ├── note_display_analysis.csv  # Preprocessed CSV file for display analysis
│   └── notes_processed.parquet    # Main dataset in Parquet format
├── archive_processed/       # Directory containing historical CSV files
├── tmp/
│   └── combined_analysis.json  # Precomputed content analysis data
├── assets/
│   └── cn.png               # Community Notes logo and additional assets (e.g., CSS)
└── README.md                # This file
```

## Installation

1. **Clone the Repository**

```bash
git clone https://github.com/CheckFirstHQ/X-Community-Notes-Dashboard.git
cd community-notes-dashboard
```

2. **Create a Virtual Environment (Optional but Recommended)**

```bash
python -m venv venv
source venv/bin/activate  # On Windows, use: venv\Scripts\activate
```

3. **Install Dependencies**

Ensure you have Python 3.7 or later installed. Then install the required packages:

```bash
pip install -r requirements.txt
```


## Data Preparation

Before running the dashboard, make sure the necessary data files are in place:

```bash 
python3 preprocess.py
python3 archive_summurize.py
python3 find_fc_usage.py
```

## Usage

1. **Run the Dashboard**

Start the Dash server by executing:

```bash
python app.py
```

2. **Access the Dashboard**

Open your web browser and navigate to [http://localhost:8050](http://localhost:8050) (or the host and port specified in `app.py`).

3. **Interact with the Dashboard**

- Use the sidebar to navigate between sections.
- Apply filters by selecting languages and adjusting the date range.
- Search for keywords in note summaries and view corresponding results.
- Explore various interactive graphs and tables that update based on your selections.


## Contact

For questions, feedback, or further information, please contact the CheckFirst team or visit [CheckFirst Network](https://checkfirst.network).
