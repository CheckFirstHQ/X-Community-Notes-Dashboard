#!/usr/bin/env python3
import pandas as pd
import os
import re
import shutil
from datetime import datetime

# Paths
NOTES_PARQUET = "data/notes_processed.parquet"
SINGLE_STATUS_FILE = "data/noteStatusHistory-00000.tsv"  # The single TSV file to process
OUTPUT_DIR = "archive_processed/"  # Folder to store per-language CSVs
ARCHIVE_DIR = "archive/"  # Folder to archive the processed TSV file

# Ensure output directories exist
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(ARCHIVE_DIR, exist_ok=True)

def extract_date_from_filename(filename):
	"""
	Extract date (YYYY-MM-DD) from filenames
	If no date is found, return None.
	"""
	match = re.search(r"noteStatusHistory-(\d{4}-\d{2}-\d{2})-", filename)
	return match.group(1) if match else None

def process_single_status_file(filepath):
	"""
	Process the noteStatusHistory file and append results to the corresponding language CSVs.
	Returns the date used for processing.
	"""
	print(f"Processing {filepath}...")
	
	# Try to extract the date from the filename.
	# If not found (as in noteStatusHistory-00000.tsv), use today's date.
	file_date = extract_date_from_filename(filepath)
	if not file_date:
		file_date = datetime.now().strftime("%Y-%m-%d")
	
	df_status = pd.read_csv(filepath, sep="\t", low_memory=False)
	df_notes = pd.read_parquet(NOTES_PARQUET)
	df_merged = pd.merge(df_notes, df_status, on="noteId", how="inner", suffixes=("_notes", "_status"))
	df_merged["isDisplayed"] = df_merged["currentStatus"] == "CURRENTLY_RATED_HELPFUL"

	# Compute time to display (from note creation to first non-NMR status) in hours.
	df_merged["timeToDisplayHours"] = (
		df_merged["timestampMillisOfFirstNonNMRStatus"] - df_merged["createdAtMillis_notes"]
	) / (1000 * 60 * 60)

	df_merged["timeToDisplayHours"] = df_merged["timeToDisplayHours"].where(df_merged["timeToDisplayHours"] >= 0)

	# Aggregate statistics per language for that date.
	grouped = df_merged.groupby("language").agg(
		total_notes=pd.NamedAgg(column="noteId", aggfunc="count"),
		displayed_notes=pd.NamedAgg(column="isDisplayed", aggfunc="sum"),
		pct_displayed=pd.NamedAgg(
			column="isDisplayed", 
			aggfunc=lambda x: 100.0 * x.sum() / x.count() if x.count() else 0
		),
		avg_time_to_display_hours=pd.NamedAgg(column="timeToDisplayHours", aggfunc="mean"),
		median_time_to_display_hours=pd.NamedAgg(column="timeToDisplayHours", aggfunc="median")
	).reset_index()

	# Add the date column to the aggregated DataFrame.
	grouped.insert(0, "Date", file_date)

	# Save (or update) per-language CSV files.
	for _, row in grouped.iterrows():
		language = row["language"]
		output_csv = os.path.join(OUTPUT_DIR, f"{language}.csv")
		save_to_csv(row, output_csv)
	
	return file_date

def save_to_csv(row, filepath):
	"""
	Append a new row to a per-language CSV file while ensuring
	no duplicate entries exist for the same date.
	"""
	df_new = pd.DataFrame([row])

	if os.path.exists(filepath):
		df_existing = pd.read_csv(filepath)
		# Remove any entry for the same date.
		df_existing = df_existing[df_existing["Date"] != row["Date"]]
		df_combined = pd.concat([df_existing, df_new], ignore_index=True)
	else:
		df_combined = df_new

	df_combined.to_csv(filepath, index=False)
	print(f"Updated {filepath} with data for {row['Date']}")

if __name__ == "__main__":
	# Process the single TSV file.
	processing_date = process_single_status_file(SINGLE_STATUS_FILE)

	# Copy the processed file to the archive directory with the new name.
	archived_filename = f"noteStatusHistory-{processing_date}.tsv"
	destination = os.path.join(ARCHIVE_DIR, archived_filename)
	shutil.copy(SINGLE_STATUS_FILE, destination)
	print(f"Copied {SINGLE_STATUS_FILE} to {destination}")
