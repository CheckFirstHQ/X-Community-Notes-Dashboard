# app.py

import os
import glob
import json
from datetime import timedelta

import dash
import dash_bootstrap_components as dbc
from dash import dcc, html, Input, Output, dash_table
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from flask_caching import Cache

from community import parse_created_date, add_domains_column  

###########################
# LANGUAGE NAME MAPPING
###########################
LANGUAGE_MAP = {
	"bg": "Bulgarian",
	"ca": "Catalan",
	"cs": "Czech",
	"da": "Danish",
	"de": "German",
	"el": "Greek",
	"en": "English",
	"es": "Spanish",
	"et": "Estonian",
	"fi": "Finnish",
	"fr": "French",
	"hr": "Croatian",
	"hu": "Hungarian",
	"it": "Italian",
	"lt": "Lithuanian",
	"lv": "Latvian",
	"mk": "Macedonian",
	"nl": "Dutch",
	"no": "Norwegian",
	"pl": "Polish",
	"pt": "Portuguese",
	"ro": "Romanian",
	"ru": "Russian",
	"sk": "Slovak",
	"sl": "Slovenian",
	"sq": "Albanian",
	"sv": "Swedish",
	"tr": "Turkish",
	"uk": "Ukrainian",
	# If mapping not here, fallback to code
}

###########################
# DATA LOADING FUNCTIONS
###########################
def load_archive_data():
	ARCHIVE_DIR = "archive_processed"
	df_archive_list = []
	for csv_file in glob.glob(os.path.join(ARCHIVE_DIR, "*.csv")):
		tmp_df = pd.read_csv(csv_file)
		tmp_df["Date"] = pd.to_datetime(tmp_df["Date"], format="%Y-%m-%d")
		df_archive_list.append(tmp_df)
	df_archive = (
		pd.concat(df_archive_list, ignore_index=True)
		if df_archive_list
		else pd.DataFrame(
			columns=[
				"Date", "language", "total_notes", "displayed_notes",
				"pct_displayed", "avg_time_to_display_hours",
				"median_time_to_display_hours"
			]
		)
	)
	df_archive.sort_values("Date", inplace=True)
	return df_archive


def load_all_data():
	DATA_PATH = "data/notes_processed.parquet"
	try:
		df_all = pd.read_parquet(DATA_PATH)
	except FileNotFoundError:
		raise FileNotFoundError(
			f"Could not find {DATA_PATH}. Please run `python preprocess.py` first."
		)
	if "createdDate" not in df_all.columns:
		df_all = parse_created_date(df_all, time_col="createdAtMillis")
	if "domains" not in df_all.columns:
		df_all = add_domains_column(df_all)
	return df_all


def load_display_data():
	DISPLAY_CSV = "data/note_display_analysis.csv"
	try:
		df_display = pd.read_csv(DISPLAY_CSV)
	except FileNotFoundError:
		df_display = pd.DataFrame(
			columns=[
				"language", "total_notes", "displayed_notes", "pct_displayed",
				"avg_time_to_display_hours", "median_time_to_display_hours"
			]
		)
	# Clean up formatting
	df_display["language"] = (
		df_display["language"]
		.astype(str)
		.str.replace(r"[\(\)',]", "", regex=True)
		.str.strip()
	)
	df_display["pct_displayed"] = df_display["pct_displayed"].apply(
		lambda x: f"{float(x):.2f}%" if pd.notnull(x) and str(x).strip() != "" else ""
	)
	df_display["avg_time_to_display_hours"] = df_display["avg_time_to_display_hours"].round(2)
	df_display["median_time_to_display_hours"] = df_display["median_time_to_display_hours"].round(2)
	valid_langs = set(LANGUAGE_MAP.keys())
	df_display = df_display[df_display["language"].isin(valid_langs)]
	df_display["lang_display"] = df_display["language"].map(LANGUAGE_MAP)
	return df_display


def load_fc_stats():
	"""Load factchecking stats from JSON"""
	fc_stats_path = os.path.join("data", "fc_stats.json")
	try:
		with open(fc_stats_path, "r") as f:
			return json.load(f)
	except Exception as e:
		print("Error loading fc_stats.json:", e)
		return {}


# Load data on startup
df_archive = load_archive_data()
df_all = load_all_data()
df_display = load_display_data()
fc_stats = load_fc_stats()

# Valid languages available in the main dataset
valid_langs = set(LANGUAGE_MAP.keys())
all_langs = sorted(valid_langs.intersection(df_all["language"].dropna().unique()))

# Compute the default start/end dates for the date picker (YYYY-MM-DD)
if not df_all.empty:
	analysis_min_date = str(df_all['createdDate'].min())
	analysis_max_date = str(df_all['createdDate'].max())
else:
	analysis_min_date = None
	analysis_max_date = None

###########################
# GLOBAL FIGURES / DATA
###########################
# Global Distribution: total notes per day (stacked bar)
df_by_date = df_all.groupby(["language", "createdDate"]).size().reset_index(name="count")
fig_global_dist = px.bar(
	df_by_date,
	x="createdDate",
	y="count",
	color="language",
)
fig_global_dist.update_layout(
	barmode="stack",
	legend=dict(
		orientation="h",
		yanchor="top",
		y=-0.5,
		xanchor="center",
		x=0.5,
		entrywidth=70,
	),
	margin=dict(b=200),
	title="Global Distribution (Full dataset – last 30 days zoomed)"
)
# Zoom in on the last ~30 days if data allows
if not df_by_date.empty:
	max_date = df_by_date["createdDate"].max()
	min_date = max_date - pd.Timedelta(days=30)
	earliest_date = df_by_date["createdDate"].min()
	if min_date < earliest_date:
		min_date = earliest_date
	fig_global_dist.update_xaxes(range=[min_date, max_date])

# Ratio Displayed Table Data
df_ratio_displayed = df_display[["lang_display", "pct_displayed"]].copy()


def empty_figure(title_text="No Data"):
	fig = go.Figure()
	fig.update_layout(title=title_text)
	return fig


# Helper function to generate filter text for titles
def get_filter_text(langs, start_date, end_date):
	parts = []
	if langs:
		parts.append("Language: " + ", ".join(langs))
	if start_date and end_date:
		parts.append("Timeframe: {} to {}".format(start_date, end_date))
	if parts:
		return " (Filtered by " + "; ".join(parts) + ")"
	else:
		return " (Full dataset)"


# Prepare the donut (pie) chart with custom hover template and hide on-chart text
donut_fig = px.pie(
	names=list(fc_stats.get("displayed_by_language", {}).keys()),
	values=list(fc_stats.get("displayed_by_language", {}).values()),
	hole=0.4,
	title="Displayed by Language"
)
donut_fig.update_traces(textinfo='none', hovertemplate='%{label}: %{value:,}')
donut_fig.update_layout(
	legend=dict(
		orientation="h",
		yanchor="top",
		y=-0.1,
		xanchor="center",
		x=0.5
	)
)

# Prepare the bar chart sorted in descending order
displayed_by_domain = fc_stats.get("displayed_by_domain", {})
sorted_domains = sorted(displayed_by_domain.items(), key=lambda x: x[1], reverse=True)
bar_fig = px.bar(
	x=[item[0] for item in sorted_domains],
	y=[item[1] for item in sorted_domains],
	labels={"x": "Domain", "y": "Count"},
	title="Displayed by Domain"
)

###########################
# DASH APP & LAYOUT
###########################
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP], serve_locally=True)
server = app.server

# Configure small caching 
cache = Cache(server, config={'CACHE_TYPE': 'simple'})
TIMEOUT = 60  # seconds

# External loading
app.index_string = """<!DOCTYPE html>
<html>
<head>
	{%metas%}
	<title>Community Notes Dashboard</title>
	{%favicon%}
	{%css%}
	<!-- External CSS can be placed in assets/styles.css -->
</head>
<body>
	{%app_entry%}
	<footer>
		{%config%}
		{%scripts%}
		{%renderer%}
	</footer>
</body>
</html>
"""

app.layout = html.Div([
	# SIDEBAR
	html.Div([
		html.Div(
			[
				html.Div(
					[
						html.A(
							[
								html.Img(
									src=app.get_asset_url("cn.png"),
									alt="Community Notes Logo",
									style={"height": "15px", "verticalAlign": "middle", "marginRight": "5px"}
								),
								"Community Notes"
							],
							className="navbar-brand",
							href="#"
						)
					],
					className="container-fluid",
				)
			],
			className="navbar",
		),
		
		html.Ul([
			html.Li(html.A("Introduction", href="#introduction")),
			html.Li(html.A("Analysis", href="#analysis")),
			html.Li(html.A("Global Distribution", href="#global-distribution")),
			html.Li(html.A("Search", href="#search")),
			html.Li(html.A("Sources", href="#sources")),
			html.Li(html.A("Media/Tweet-based", href="#media-tweet")),
			html.Li(html.A("Author / Participant", href="#author-participant")),
			html.Li(html.A("Note Visibility", href="#note-visibility")),
			html.Li(html.A("Responsiveness", href="#responsiveness")),
			html.Li(html.A("FactChecking Usage", href="#factchecking-usage")),
			html.Li(html.A("Content Analysis", href="#content-analysis")),
			html.Li(html.A("Ratio Displayed", href="#ratio-displayed"))
		])
	], className="sidebar d-none d-md-block"),
	
	# MAIN CONTENT
	html.Div([
		dbc.Container(fluid=False, className="fixed-container", children=[
			
			# Introduction Section
			html.Section(
				id="introduction",
				children=[
					html.H2("Introduction"),
					html.P([
						"Welcome to the Community Notes Dashboard, an interactive tool developed by ",
						html.A("CheckFirst", href="https://checkfirst.network", target="_blank"),
						" to explore and analyse Community Notes data from X (formerly Twitter). This dashboard is designed to provide insights into how Community Notes function, how they are distributed, and how fact‐checking plays a role in the ecosystem."
					]),
					html.H3("How to Use"),
					html.P("The dashboard is structured into multiple sections, each offering a different perspective on the dataset:"),
					html.Ul([
						html.Li([
							html.Strong("Global Distribution – "), 
							"Displays an overview of the dataset over the past 30 days, showing the volume and spread of Community Notes across languages."
						]),
						html.Li([
							html.Strong("Fact-Checking Usage – "), 
							"Highlights notes that include links to external fact‐checking sources, showing the prevalence of verified information as both created and displayed Community Notes."
						]),
						html.Li([
							html.Strong("Search & Sources – "), 
							"Allows users to search for keywords within notes and explore the most common domains referenced in notes, distinguishing between media‐based and tweet‐based sources."
						]),
						html.Li([
							html.Strong("Author & Participant Analysis – "), 
							"Provides insights into the contributors of Community Notes, including the number of unique authors and the distribution of notes per participant."
						]),
						html.Li([
							html.Strong("Note Visibility – "), 
							"Examines the proportion of Community Notes that are displayed versus those that remain hidden."
						]),
						html.Li([
							html.Strong("Responsiveness – "), 
							"Tracks the time it takes for notes to be displayed once they are created."
						]),
						html.Li([
							html.Strong("Content Analysis – "), 
							"Uses AI‐based processing to group notes by language and detect trends, common narratives, and recurring themes."
						]),
						html.Li([
							html.Strong("Ratio Displayed – "), 
							"Shows the proportion of Community Notes that are ultimately surfaced to users, based on precomputed data."
						]),
					]),
					html.H3("Filters and Interaction"),
					html.P(
						"Users can filter the data by selecting one or more languages and adjusting the timeframe. When filters are applied, relevant visualisations will update accordingly, with active filter settings reflected in their titles. Some sections, such as Content Analysis and Ratio Displayed, are based on fixed data and do not change with filters."
					),
					html.H3("Limitations"),
					html.P(
						"The dashboard updates twice daily, but the release of Community Notes data by X seems to be delayed by up to three days. Additionally, the detected language of a note does not always correspond to a specific country. The fact‐checking references are determined using a curated list of fact‐checking domains."
					)
				]
			),
			
			# 1) Global Distribution
			html.Section(id="global-distribution", children=[
				html.H2("Global Distribution"),
				html.P("This visualisation displays the full dataset (last 30 days zoomed)."),
				dcc.Loading(dcc.Graph(figure=fig_global_dist), type="default")
			]),
			
			# 1.5) FactChecking Usage 
			html.Section(id="factchecking-usage", children=[
				html.H2("FactChecking Usage"),
				dbc.Row([
					dbc.Col([
						html.Div([
							html.P("Total Notes:"),
							html.H4(f"{fc_stats.get('total_notes', 0):,}"),
							html.P("Total Notes with a link to a factcheck:"),
							html.H4(
								f"{fc_stats.get('notes_with_fc', 0):,} "
								f"({(fc_stats.get('notes_with_fc', 0) / fc_stats.get('total_notes', 1) * 100):.2f}%)"
							),
							html.P("Total Notes with a link to a factcheck displayed:"),
							html.H4(
								f"{fc_stats.get('notes_with_fc_displayed', 0):,} "
								f"({(fc_stats.get('notes_with_fc_displayed', 0) / fc_stats.get('notes_with_fc', 1) * 100):.2f}%)"
							),
						], style={"padding": "20px"})
					], width=6),
					dbc.Col([
						dcc.Graph(
							id="fc-donut-chart",
							figure=donut_fig
						)
					], width=6)
				]),
				dcc.Graph(
					id="fc-bar-chart",
					figure=bar_fig
				)
			]),
			
			# 3.5) Content Analysis (does NOT update based on timeframe)
			html.Section(id="content-analysis", children=[
				html.H2("Content Analysis"),
				html.P(
					"This section is based on a pre-computed analysis of Community Notes summaries. "
					"Data is grouped by detected language and processed by an AI model (ChatGPT-o1)."
				),
				dcc.Loading(
					html.Div(id="content-analysis-div"),
					type="default"
				),
			]),
			
			# 9) Ratio Displayed (does NOT update based on timeframe)
			html.Section(id="ratio-displayed", children=[
				html.H2("Ratio Displayed"),
				html.P("Today's ratio of notes displayed (EU Languages). This visualisation is based on preprocessed data."),
				dash_table.DataTable(
					columns=[
						{"name": "Language", "id": "lang_display"},
						{"name": "Displayed (%)", "id": "pct_displayed"}
					],
					data=df_ratio_displayed.to_dict("records"),
					style_table={"width": "50%"},
					style_cell={"textAlign": "left"}
				)
			]),
			
			# 2) Analysis: language and timeframe selector
			html.Section(id="analysis", children=[
				html.H2("Analysis"),
				dbc.Row([
					dbc.Col([
						html.P("Please select one or multiple languages and a timeframe for the following sections.")
					], width=12),
					dbc.Col([
						html.P("Select recognised languages:"),
						dcc.Dropdown(
							id="analysis-lang-selector",
							options=[
								{"label": LANGUAGE_MAP.get(lang, lang.capitalize()), "value": lang}
								for lang in all_langs
							],
							multi=True,
							value=[l for l in ["fr", "de"] if l in all_langs],
							style={"width": "300px"}
						),
					], width=6),
					dbc.Col([
						html.P("Select a timeframe to filter the data:"),
						dcc.DatePickerRange(
							id="date-range-picker",
							start_date=analysis_min_date,
							end_date=analysis_max_date,
							min_date_allowed=analysis_min_date,
							max_date_allowed=analysis_max_date,
							display_format="YYYY-MM-DD"
						)
					], width=6)
				])
			]),
			
			# 3) Search
			html.Section(id="search", children=[
				html.H2("Search"),
				dcc.Input(
					id="keyword-input",
					type="text",
					placeholder="Enter a keyword...",
					debounce=True,
					style={"width": "300px", "marginRight": "10px"}
				),
				dcc.Loading(
					dcc.Graph(id="keyword-usage-graph", figure=empty_figure("Enter a keyword to see results")),
					type="default"
				),
				html.Ul(id="search-results", style={"maxHeight": "400px", "overflowY": "auto"}),
			]),
			
			# 4) Sources (Top Domains)
			html.Section(id="sources", children=[
				html.H2("Sources (Top Domains)"),
				dcc.Loading(
					dcc.Graph(id="domain-graph", figure=empty_figure()),
					type="default"
				),
			]),
			
			# 5) Media-based vs Tweet-based
			html.Section(id="media-tweet", children=[
				html.H2("Media-based vs. Tweet-based"),
				dcc.Loading(
					dcc.Graph(id="media-dist", figure=empty_figure()),
					type="default"
				)
			]),
			
			# 6) Author / Participant
			html.Section(id="author-participant", children=[
				html.H2("Author / Participant"),
				dcc.Loading(
					dcc.Graph(id="author-stats-unique", figure=empty_figure()),
					type="default"
				),
				dcc.Loading(
					dcc.Graph(id="author-stats-dist", figure=empty_figure()),
					type="default"
				),
			]),
			
			# 7) Note Visibility
			html.Section(id="note-visibility", children=[
				html.H2("Note Visibility"),
				dcc.Loading(
					dcc.Graph(id="note-visibility-figure", figure=empty_figure()),
					type="default"
				),
			]),
			
			# 8) Responsiveness
			html.Section(id="responsiveness", children=[
				html.H2("Responsiveness"),
				dcc.Loading(
					dcc.Graph(id="note-responsiveness-figure", figure=empty_figure()),
					type="default"
				),
			]),
			
			# Footer
			html.Section(id="footer", children=[
				html.Hr(),
				html.P(
					[
						"© CheckFirst 2025 – Made with ❤️ in 🇫🇮. Visit ",
						html.A("CheckFirst", href="https://checkfirst.network", target="_blank"),
						" for more information."
					],
					className="text-right text-muted my-3"
				)
			])
		])
	], className="content")
])

###########################
# CALLBACKS
###########################
@app.callback(
	[Output("keyword-usage-graph", "figure"),
	 Output("search-results", "children")],
	[Input("keyword-input", "value"),
	 Input("analysis-lang-selector", "value"),
	 Input("date-range-picker", "start_date"),
	 Input("date-range-picker", "end_date")]
)
@cache.memoize(timeout=TIMEOUT)
def update_keyword_search(keyword, selected_langs, start_date, end_date):
	"""
	Search across all data (df_all) for a keyword in 'summary'
	and display results in a table with four columns:
	Date, Language, Summary, and View.
	Results are filtered by the languages selected and by the selected timeframe.
	"""
	if not keyword:
		return empty_figure("Enter a keyword to see results"), []
	
	df_search = df_all[df_all["summary"].str.contains(keyword, case=False, na=False)].copy()
	
	if selected_langs:
		df_search = df_search[df_search["language"].isin(selected_langs)]
	
	if start_date and end_date:
		start_date_obj = pd.to_datetime(start_date).date()
		end_date_obj = pd.to_datetime(end_date).date()
		df_search = df_search[(df_search["createdDate"] >= start_date_obj) & (df_search["createdDate"] <= end_date_obj)]
	
	if df_search.empty:
		fig = go.Figure()
		fig.update_layout(title=f"No results for keyword: {keyword}")
		return fig, []
	
	df_by_date_kw = df_search.groupby(["language", "createdDate"]).size().reset_index(name="count")
	title_base = f"Occurrences of '{keyword}' over time"
	filter_suffix = get_filter_text(selected_langs, start_date, end_date)
	fig = px.line(df_by_date_kw, x="createdDate", y="count", color="language", title=title_base + filter_suffix)
	fig.update_traces(mode="lines+markers")
	
	df_search["createdDate"] = pd.to_datetime(df_search["createdDate"])
	df_search_sorted = df_search.sort_values("createdDate", ascending=False)
	
	table_header = html.Thead(
		html.Tr([
			html.Th("Date", style={"border": "1px solid black", "padding": "4px"}),
			html.Th("Language", style={"border": "1px solid black", "padding": "4px"}),
			html.Th("Summary", style={"border": "1px solid black", "padding": "4px"}),
			html.Th("View", style={"border": "1px solid black", "padding": "4px"}),
		])
	)
	
	table_rows = []
	for _, row in df_search_sorted.iterrows():
		date_str = str(row["createdDate"].date())
		lang_str = row["language"]
		tweet_id = row["tweetId"]
		summary_str = row["summary"] or ""
		tweet_url = f"https://x.com/i/web/status/{tweet_id}"
		view_link = html.A("🗒️", href=tweet_url, target="_blank", style={"textDecoration": "none"})
		
		table_rows.append(
			html.Tr([
				html.Td(date_str, style={"border": "1px solid black", "padding": "4px"}),
				html.Td(lang_str, style={"border": "1px solid black", "padding": "4px"}),
				html.Td(summary_str, style={"border": "1px solid black", "padding": "4px"}),
				html.Td(view_link, style={"border": "1px solid black", "padding": "4px"})
			])
		)
	
	results_table = html.Table(
		[table_header, html.Tbody(table_rows)],
		className="material-table"
	)
	
	return fig, results_table


@app.callback(
	[Output("domain-graph", "figure"),
	 Output("media-dist", "figure"),
	 Output("author-stats-unique", "figure"),
	 Output("author-stats-dist", "figure")],
	[Input("analysis-lang-selector", "value"),
	 Input("date-range-picker", "start_date"),
	 Input("date-range-picker", "end_date")]
)
@cache.memoize(timeout=TIMEOUT)
def update_analysis_figures(langs, start_date, end_date):
	"""
	Update figures for top domains, media/tweet distribution, and author statistics.
	Filter by the selected languages and timeframe.
	"""
	if not langs:
		return [empty_figure("No data")] * 4

	df_selected = df_all[df_all["language"].isin(langs)].copy()
	
	if start_date and end_date:
		start_date_obj = pd.to_datetime(start_date).date()
		end_date_obj = pd.to_datetime(end_date).date()
		df_selected = df_selected[(df_selected["createdDate"] >= start_date_obj) & (df_selected["createdDate"] <= end_date_obj)]
	
	if df_selected.empty:
		return [empty_figure("No data")] * 4

	filter_suffix = get_filter_text(langs, start_date, end_date)
	
	df_exploded = df_selected.explode("domains")
	df_exploded["domains"] = df_exploded["domains"].fillna("")
	df_domains = df_exploded.groupby(["language", "domains"]).size().reset_index(name="count")

	frames = []
	for lang in langs:
		df_lang = df_domains[df_domains["language"] == lang].copy()
		df_lang = df_lang.sort_values("count", ascending=False).head(10)
		frames.append(df_lang)
	df_top_all = pd.concat(frames) if frames else pd.DataFrame(columns=["language", "domains", "count"])

	if not df_top_all.empty:
		fig_domains = px.bar(
			df_top_all,
			x="count",
			y="domains",
			orientation="h",
			color="language",
			barmode="group",
			labels={"domains": "Domain", "count": "Count"}
		)
		fig_domains.update_layout(
			yaxis={'categoryorder': 'total ascending'},
			title="Top Domains" + filter_suffix
		)
	else:
		fig_domains = empty_figure("No Domain Data")

	df_media = df_selected.groupby(["language", "isMediaNote"]).size().reset_index(name="count")
	if not df_media.empty:
		df_media["isMediaNote"] = df_media["isMediaNote"].map({0: "Tweet-based", 1: "Media-based"})
		fig_media = px.bar(
			df_media,
			x="count",
			y="isMediaNote",
			orientation="h",
			color="language",
			barmode="group",
			labels={"isMediaNote": "Type", "count": "Count"},
			title="Media-based vs. Tweet-based" + filter_suffix
		)
	else:
		fig_media = empty_figure("No Media/Tweet Data")

	df_author_lang = df_selected.groupby("language")["noteAuthorParticipantId"].nunique().reset_index(name="unique_authors")
	fig_author_unique = px.bar(
		df_author_lang,
		x="unique_authors",
		y="language",
		orientation="h",
		title="Unique Authors" + filter_suffix,
		labels={"language": "Language", "unique_authors": "Unique Authors"}
	)

	df_author_counts = (
		df_selected.groupby(["language", "noteAuthorParticipantId"])
		.size()
		.reset_index(name="note_count")
	)
	if df_author_counts.empty:
		fig_author_hist = empty_figure("No Author Data")
	else:
		bins = [0, 1, 5, 10, 50, 100, 500, 1000, float("inf")]
		labels_bins = ["1", "1-5", "5-10", "10-50", "50-100", "100-500", "500-1000", "1000+"]
		df_author_counts["note_bins"] = pd.cut(df_author_counts["note_count"], bins=bins, labels=labels_bins)
		df_bins = df_author_counts.groupby(["language", "note_bins"]).size().reset_index(name="count")
		fig_author_hist = px.bar(
			df_bins,
			x="note_bins",
			y="count",
			color="language",
			barmode="group",
			title="Distribution of # Notes per Participant (Binned)" + filter_suffix,
			labels={"note_bins": "# Notes Range", "count": "Number of Participants"}
		)

	return fig_domains, fig_media, fig_author_unique, fig_author_hist


@app.callback(
	[Output("note-visibility-figure", "figure"),
	 Output("note-responsiveness-figure", "figure")],
	[Input("analysis-lang-selector", "value"),
	 Input("date-range-picker", "start_date"),
	 Input("date-range-picker", "end_date")]
)
@cache.memoize(timeout=TIMEOUT)
def update_visibility_responsiveness(langs, start_date, end_date):
	"""
	Update note visibility & responsiveness based on selected languages
	and the selected timeframe.
	"""
	if not langs or df_archive.empty:
		return empty_figure("No Data"), empty_figure("No Data")

	df_filtered = df_archive[df_archive["language"].isin(langs)].copy()
	
	if start_date and end_date:
		start_date_dt = pd.to_datetime(start_date)
		end_date_dt = pd.to_datetime(end_date)
		df_filtered = df_filtered[(df_filtered["Date"] >= start_date_dt) & (df_filtered["Date"] <= end_date_dt)]
	
	if df_filtered.empty:
		return empty_figure("No Data"), empty_figure("No Data")

	filter_suffix = get_filter_text(langs, start_date, end_date)
	
	df_visibility = df_filtered.melt(
		id_vars=["Date", "language"],
		value_vars=["total_notes", "displayed_notes"],
		var_name="metric",
		value_name="count"
	)
	fig_visibility = px.line(
		df_visibility,
		x="Date",
		y="count",
		color="language",
		line_dash="metric",
		title="Total vs. Displayed Notes Over Time" + filter_suffix,
		labels={"count": "Notes"}
	)
	fig_visibility.update_traces(mode="lines+markers")

	df_resp = df_filtered.melt(
		id_vars=["Date", "language"],
		value_vars=["avg_time_to_display_hours", "median_time_to_display_hours"],
		var_name="metric",
		value_name="hours"
	)
	fig_responsiveness = px.line(
		df_resp,
		x="Date",
		y="hours",
		color="language",
		line_dash="metric",
		title="Average vs. Median Time to Display" + filter_suffix,
		labels={"hours": "Hours"}
	)
	fig_responsiveness.update_traces(mode="lines+markers")

	return fig_visibility, fig_responsiveness


# --- Callback for Content Analysis (does NOT update based on timeframe) ---
@app.callback(
	Output("content-analysis-div", "children"),
	[Input("analysis-lang-selector", "value")]
)
def update_content_analysis(selected_langs):
	"""
	Load content analysis from tmp/combined_analysis.json and display
	trends, narratives, and themes for each selected language using the latest date.
	"""
	if not selected_langs:
		return html.P("Please select at least one language in the Analysis section to view Content Analysis.")

	json_path = os.path.join("tmp", "combined_analysis.json")
	try:
		with open(json_path, "r") as f:
			analysis_data = json.load(f)
	except Exception as e:
		return html.P("Error loading content analysis data.")

	try:
		latest_date = max(analysis_data.keys(), key=lambda d: pd.to_datetime(d))
		latest_data = analysis_data[latest_date]
	except Exception as e:
		return html.P("No valid analysis data available.")

	content_children = [html.P(f"Latest: {latest_date}", className="text-muted")]

	for lang in selected_langs:
		if lang in latest_data:
			lang_data = latest_data[lang]
			content_children.append(html.H4(f"{LANGUAGE_MAP.get(lang, lang)}"))
			content_children.append(html.H5("Trends"))
			if lang_data.get("trends"):
				content_children.append(html.Ul([html.Li(item) for item in lang_data["trends"]]))
			else:
				content_children.append(html.P("No trends available."))
			content_children.append(html.H5("Narratives"))
			if lang_data.get("narratives"):
				content_children.append(html.Ul([html.Li(item) for item in lang_data["narratives"]]))
			else:
				content_children.append(html.P("No narratives available."))
			content_children.append(html.H5("Themes"))
			if lang_data.get("themes"):
				content_children.append(html.Ul([html.Li(item) for item in lang_data["themes"]]))
			else:
				content_children.append(html.P("No themes available."))
			content_children.append(html.Hr())
		else:
			content_children.append(html.P(f"No content analysis available for language: {LANGUAGE_MAP.get(lang, lang)}."))

	return content_children


if __name__ == "__main__":
	app.run_server(host="0.0.0.0", port=8050)
