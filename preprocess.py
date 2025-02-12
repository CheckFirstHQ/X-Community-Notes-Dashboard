# preprocess.py
import os
from community import (
	parallel_process_notes,
	parse_created_date,
	add_domains_column,
	save_processed_notes
)

RAW_NOTES_PATH = "data/notes-00000.tsv"        # The raw file you downloaded
OUTPUT_PATH = "data/notes_processed.parquet"   # Where the processed file will be saved

def main():
	"""
	1. Load and process 'notes.tsv' in parallel (language detection)
	2. Parse date and extract domains
	3. Save the final DataFrame to Parquet
	"""
	print("[PREPROCESS] Starting parallel processing of notes...")
	df_notes = parallel_process_notes(
		RAW_NOTES_PATH,
		chunk_size=50_000,    # Adjust for your machine
		max_workers=11        # Or None to use all available CPU cores
	)

	print("[PREPROCESS] Parsing createdDate from createdAtMillis...")
	df_notes = parse_created_date(df_notes, time_col="createdAtMillis")

	# Extract domains from each summary
	print("[PREPROCESS] Extracting domains from summary...")
	df_notes = add_domains_column(df_notes)

	# save to Parquet
	print("[PREPROCESS] Saving processed data...")
	save_processed_notes(df_notes, OUTPUT_PATH)
	print(f"[PREPROCESS] Done! Processed data saved to {OUTPUT_PATH}")

if __name__ == "__main__":
	main()
