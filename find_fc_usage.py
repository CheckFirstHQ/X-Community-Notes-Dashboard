import csv
import json
import logging
from datetime import datetime
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed

from langdetect import detect, DetectorFactory
DetectorFactory.seed = 0  # for consistent language detection

# Configure logging to show debug/info output
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def convert_millis_to_date(millis):
	"""Convert milliseconds since epoch to a human-readable UTC date."""
	try:
		dt = datetime.utcfromtimestamp(int(millis) / 1000)
		return dt.strftime("%Y-%m-%d %H:%M:%S")
	except Exception as e:
		logging.error(f"Error converting millis '{millis}': {e}")
		return ""

def extract_domain(url):
	"""
	Extracts the domain from a URL
	"""
	parsed = urlparse(url)
	domain = parsed.netloc
	if domain.startswith("www."):
		domain = domain[4:]
	return domain

def load_factchecker_websites(filepath):
	"""
	Loads factchecker websites from a CSV file
	Ech line of the file is a URL.
	"""
	websites = []
	logging.info(f"Loading factchecker websites from {filepath}")
	try:
		with open(filepath, newline="", encoding="utf-8") as f:
			for line in f:
				url = line.strip()
				if url:
					websites.append(url)
					logging.debug(f"Loaded factchecker URL: {url}")
	except Exception as e:
		logging.error(f"Error loading factchecker websites: {e}")
	logging.info(f"Total factchecker websites loaded: {len(websites)}")
	return websites

def load_note_status_history(filepath):
	"""
	Loads note status history from a TSV file and returns a set of noteIds
	that have currentStatus "CURRENTLY_RATED_HELPFUL"
	"""
	displayed_notes = set()
	logging.info(f"Loading note status history from {filepath}")
	try:
		with open(filepath, newline="", encoding="utf-8") as f:
			reader = csv.DictReader(f, delimiter="\t")
			for row in reader:
				note_id = row.get("noteId", "")
				current_status = row.get("currentStatus", "")
				if current_status == "CURRENTLY_RATED_HELPFUL":
					displayed_notes.add(note_id)
	except Exception as e:
		logging.error(f"Error loading note status history: {e}")
	logging.info(f"Total displayed notes (CURRENTLY_RATED_HELPFUL): {len(displayed_notes)}")
	return displayed_notes

def process_chunk(chunk, fc_websites, start_index):
	"""
	Processes a chunk of rows from the TSV file
	
	Parameters:
	  - chunk: list of row dictionaries
	  - fc_websites: list of factchecker URLs
	  - start_index: the starting row number 
	
	Returns a list of result entries that match the factchecker URLs in the summary
	Each entry contains the internal NoteID (for stats), the factcheck URL,
	the summary, tweet ID, and the converted human-readable date
	"""
	chunk_results = []
	for offset, row in enumerate(chunk):
		idx = start_index + offset  # overall row number (for logging)
		summary = row.get("summary", "")
		tweet_id = row.get("tweetId", "")
		created_at = row.get("createdAtMillis", "")
		note_id = row.get("noteId", "")
		
		# Warn if key fields are empty
		if not summary:
			logging.debug(f"Note {idx} (noteId: {note_id}) has an empty 'summary' field.")
		if not created_at:
			logging.debug(f"Note {idx} (noteId: {note_id}) has an empty 'createdAtMillis' field.")
		
		# For each factchecker website, check if its URL is in the summary.
		for fc_url in fc_websites:
			if fc_url in summary:
				domain = extract_domain(fc_url)
				human_date = convert_millis_to_date(created_at)
				entry = {
					"NoteID": note_id,          # keep for stats;  removed from output
					"factcheck": fc_url,        # factchecking URL as found in summary
					"factchecker": domain,      # extracted domain 
					"Summary": summary,
					"Tweet": tweet_id,
					"Date": human_date          # human-readable date
				}
				chunk_results.append(entry)
				logging.debug(f"Match found in note {idx} (noteId: {note_id})")
				
				
	return chunk_results

def process_notes(tsv_filepath, fc_websites, num_workers=8, chunk_size=10000):
	"""
	Processes the TSV file containing notes using multi-threading.
	
	Returns a tuple (results, total_notes) where:
	  - results: list of entries (each entry has "NoteID", "factcheck", "Summary", "Tweet", "Date", etc.)
	  - total_notes: total number of rows processed.
	"""
	results = []
	logging.info(f"Processing notes from {tsv_filepath}")
	try:
		with open(tsv_filepath, newline="", encoding="utf-8") as f:
			reader = csv.DictReader(f, delimiter="\t")
			rows = list(reader)
		total_notes = len(rows)
		logging.info(f"Total rows loaded: {total_notes}")
	except Exception as e:
		logging.error(f"Error reading TSV file: {e}")
		return results, 0

	# Break rows into chunks for multi-threading.
	chunks = []
	start_indexes = []  # keep track of each chunk's starting row number
	for i in range(0, total_notes, chunk_size):
		chunks.append(rows[i:i + chunk_size])
		start_indexes.append(i + 1)  # row numbering starts at 1

	logging.info(f"Total chunks created: {len(chunks)} (chunk size: {chunk_size})")

	with ThreadPoolExecutor(max_workers=num_workers) as executor:
		futures = []
		for chunk, start_index in zip(chunks, start_indexes):
			futures.append(executor.submit(process_chunk, chunk, fc_websites, start_index))
		for future in as_completed(futures):
			try:
				chunk_results = future.result()
				results.extend(chunk_results)
			except Exception as e:
				logging.error(f"Error processing a chunk: {e}")

	logging.info(f"Total factcheck matches found: {len(results)}")
	return results, total_notes

def main():
	# File paths (adjust as needed)
	fc_websites_path = "data/fc_websites.csv"
	notes_tsv_path = "data/notes-00000.tsv"
	note_status_tsv_path = "data/noteStatusHistory-00000.tsv"
	fc_usage_output = "data/fc_usage.json"
	fc_stats_output = "data/fc_stats.json"

	# Load factchecker websites.
	fc_websites = load_factchecker_websites(fc_websites_path)

	# Process the notes to extract those with factchecking links
	fc_results, total_notes = process_notes(notes_tsv_path, fc_websites, num_workers=8, chunk_size=50000)

	# --- Build output: fc_usage.json ---
	#   factcheck, Summary, Tweet, Date (human-readable)
	fc_usage_for_output = []
	for entry in fc_results:
		output_entry = {
			"factcheck": entry["factcheck"],
			"Summary": entry["Summary"],
			"Tweet": entry["Tweet"],
			"Date": entry["Date"]
		}
		fc_usage_for_output.append(output_entry)

	try:
		with open(fc_usage_output, "w", encoding="utf-8") as outfile:
			json.dump(fc_usage_for_output, outfile, indent=4, ensure_ascii=False)
		logging.info(f"Detailed factcheck output written to {fc_usage_output}")
	except Exception as e:
		logging.error(f"Error writing output JSON ({fc_usage_output}): {e}")

	# --- Load note status history to determine which notes are displayed ---
	displayed_note_ids = load_note_status_history(note_status_tsv_path)

	# --- Build statistics ---
	# 1. notes_with_fc: unique noteIds from fc_results
	unique_notes_with_fc = {entry["NoteID"] for entry in fc_results if entry.get("NoteID")}
	notes_with_fc = len(unique_notes_with_fc)

	# 2. notes_with_fc_displayed: unique noteIds from fc_results that are in displayed_note_ids
	unique_notes_with_fc_displayed = {entry["NoteID"] for entry in fc_results if entry.get("NoteID") in displayed_note_ids}
	notes_with_fc_displayed = len(unique_notes_with_fc_displayed)

	# 3. displayed_by_language: for each displayed note (with factcheck), detect language from the summary
	displayed_by_language = {}
	for entry in fc_results:
		note_id = entry.get("NoteID")
		if note_id in displayed_note_ids:
			summary = entry.get("Summary", "")
			if summary:
				try:
					lang = detect(summary)
				except Exception:
					lang = "unknown"
				displayed_by_language[lang] = displayed_by_language.get(lang, 0) + 1

	# 4. displayed_by_domain: count by factchecking domain from the factcheck URL (stored in "factchecker")
	displayed_by_domain = {}
	for entry in fc_results:
		note_id = entry.get("NoteID")
		if note_id in displayed_note_ids:
			domain = entry.get("factchecker", "unknown")
			displayed_by_domain[domain] = displayed_by_domain.get(domain, 0) + 1

	fc_stats = {
		"total_notes": total_notes,
		"notes_with_fc": notes_with_fc,
		"notes_with_fc_displayed": notes_with_fc_displayed,
		"displayed_by_language": displayed_by_language,
		"displayed_by_domain": displayed_by_domain
	}

	try:
		with open(fc_stats_output, "w", encoding="utf-8") as outfile:
			json.dump(fc_stats, outfile, indent=4, ensure_ascii=False)
		logging.info(f"Statistics output written to {fc_stats_output}")
	except Exception as e:
		logging.error(f"Error writing statistics JSON ({fc_stats_output}): {e}")

if __name__ == "__main__":
	main()
