# community.py
import pandas as pd
import re
import concurrent.futures

from langdetect import detect, DetectorFactory
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import KMeans

DetectorFactory.seed = 0


############################
# Example stopword sets    #
############################
FRENCH_STOPWORDS = {
	"alors","au","aucuns","aussi","autre","avant","avec","avoir","bon","car","ce","cela","ces",
	"ceux","chaque","ci","comme","comment","dans","des","du","dedans","dehors","depuis","devrait",
	"doit","donc","dos","droite","début","elle","elles","en","encore","essai","est","et","eu","fait",
	"faites","fois","font","hors","ici","il","ils","je","la","le","les","leur","là","ma","maintenant",
	"mais","mes","mine","moins","mon","mot","ni","nommés","notre","nous","ou","où","par","parce","pas",
	"peut","peu","plupart","pour","pourquoi","quand","que","quel","quelle","quelles","quels","qui",
	"sa","sans","ses","seulement","si","sien","son","sont","sous","soyez","sujet","sur","ta","tandis",
	"tellement","tels","tes","ton","tous","tout","trop","très","tu","valeur","voie","voient","vont","votre",
	"vous","vu", "http", "https", "www", "un", "une"
}
GERMAN_STOPWORDS = {
	"aber","alle","allem","allen","aller","alles","als","also","am","an","ander","andere","anderem","anderen",
	"anderer","anderes","andern","auch","auf","aus","bei","bin","bis","bist","da","damit","dann","der","den",
	"des","dem","die","das","daß","derselbe","derselben","doch","dort","du","durch","ein","eine","einem","einen",
	"einer","eines","einige","einiges","einiger","einigen","etc","für","gab","ganz","gib","hat","hatte","hier",
	"hin","hinter","ich","ihm","ihn","ihr","ihre","ihrem","ihren","ihrer","ihres","im","in","indem","ist","ja",
	"jede","jedem","jeden","jeder","jedes","jetzt","kann","kein","keine","keinem","keinen","keiner","keines",
	"können","macht","mit","muss","nach","nicht","nur","ob","oder","sehr","sein","seine","sich","sie","sind",
	"so","solche","soll","sollen","sollte","um","und","unse","unsere","unserer","unter","viel","vom","von",
	"vor","wann","war","waren","was","weiter","weiteren","welche","welchem","welchen","welcher","welches","wenn",
	"wer","werde","werden","wie","wieder","wir","wird","zu","zum","zur", "http", "https", "www"
}

def clean_text_for_clustering(text: str) -> str:
	"""
	1. Remove URLs
	2. Lowercase
	3. Remove punctuation except maybe for internal apostrophes/hyphens if desired
	4. Remove short tokens (<3 chars)
	5. Remove FR/DE stopwords
	"""
	if not isinstance(text, str):
		return ""
	
	text_no_urls = re.sub(r"http\S+", " ", text)
	text_lower = text_no_urls.lower()
	text_alpha = re.sub(r"[^\w\s]", " ", text_lower)
	tokens = text_alpha.split()
	tokens = [t for t in tokens if len(t) >= 3 and not t.isnumeric()]
	
	# Remove stopwords
	combined_sw = FRENCH_STOPWORDS.union(GERMAN_STOPWORDS)
	tokens = [t for t in tokens if t not in combined_sw]
	
	return " ".join(tokens)


###############################
# Language detection pipeline #
###############################

def detect_language(text: str) -> str:
	"""Detect language, returning 'unknown' if empty or detection fails."""
	if not isinstance(text, str) or not text.strip():
		return "unknown"
	try:
		return detect(text)
	except:
		return "unknown"

def process_chunk(chunk_df: pd.DataFrame) -> pd.DataFrame:
	"""
	Worker function to detect language in a given chunk of the DataFrame.
	Returns the chunk with a 'language' column.
	"""
	chunk_df["language"] = chunk_df["summary"].apply(detect_language)
	return chunk_df

def parallel_process_notes(notes_file_path: str, chunk_size=100_000, max_workers=None) -> pd.DataFrame:
	"""
	Reads the notes TSV in chunks, distributing each chunk’s language detection 
	to a pool of processes so we can use multiple cores.
	"""
	use_columns = ["noteId", "noteAuthorParticipantId", "createdAtMillis", "tweetId", "classification", "trustworthySources", "isMediaNote",  "summary"]
	processed_chunks = []

	with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
		futures = []
		for i, chunk in enumerate(pd.read_csv(
			notes_file_path,
			sep="\t",
			usecols=use_columns,
			low_memory=False,
			chunksize=chunk_size
		)):
			print(f"[DEBUG] Submitting chunk {i}, shape={chunk.shape}")
			futures.append(executor.submit(process_chunk, chunk))

		for i, future in enumerate(concurrent.futures.as_completed(futures)):
			processed_chunk = future.result()
			print(f"[DEBUG] Chunk {i} finished processing, shape={processed_chunk.shape}")
			processed_chunks.append(processed_chunk)

	df_notes = pd.concat(processed_chunks, ignore_index=True)
	print(f"[DEBUG] Combined DataFrame shape={df_notes.shape}")
	return df_notes


def get_top_keywords_per_cluster(kmeans: KMeans, vectorizer: TfidfVectorizer, n_terms: int = 10) -> dict:
	"""
	Given a fitted KMeans model and its corresponding TfidfVectorizer,
	return a dictionary { cluster_index: [top terms ...] }.
	"""
	# Feature names from the TF–IDF vectorizer
	feature_names = vectorizer.get_feature_names_out()
	
	top_keywords = {}
	
	for cluster_id in range(kmeans.n_clusters):
		# Get the centroid of this cluster
		centroid = kmeans.cluster_centers_[cluster_id]
	
		# Sort feature indices by weight, descending
		top_indices = centroid.argsort()[::-1][:n_terms]
		top_terms = [feature_names[i] for i in top_indices]
		top_keywords[cluster_id] = top_terms
	
	return top_keywords


#############################
# Date & domain extraction  #
#############################

def parse_created_date(df: pd.DataFrame, time_col: str = "createdAtMillis") -> pd.DataFrame:
	"""
	Convert createdAtMillis to a datetime (by default in ms).
	Adds a 'createdDate' column truncated to daily granularity.
	"""
	if time_col in df.columns:
		df["createdDate"] = pd.to_datetime(df[time_col], unit="ms", errors="coerce")
		df["createdDate"] = df["createdDate"].dt.date
	return df

def extract_domains(text: str) -> list:
	"""Find all URLs in the text via regex, return their domains."""
	if not isinstance(text, str):
		return []
	url_pattern = r"(https?://[^\s]+)"
	urls = re.findall(url_pattern, text)
	domains = []
	for url in urls:
		domain = re.sub(r"^https?://", "", url).split("/")[0].lower()
		domain = re.sub(r"[^\w.\-]", "", domain)
		domains.append(domain)
	return domains

def add_domains_column(df: pd.DataFrame) -> pd.DataFrame:
	"""Extract domains from each 'summary' text and store them in a 'domains' list."""
	df["domains"] = df["summary"].apply(extract_domains)
	return df


##############################
# Filtering & Basic Counting #
##############################

def filter_languages(df: pd.DataFrame, languages: list) -> pd.DataFrame:
	"""
	Filter the DataFrame to only rows where 'language' is in the given list.
	"""
	return df[df["language"].isin(languages)].copy()

def get_language_counts(df_notes: pd.DataFrame) -> pd.DataFrame:
	"""
	Count how many notes of each detected language exist in df_notes.
	"""
	counts = df_notes["language"].value_counts(dropna=False).reset_index()
	counts.columns = ["language", "count"]
	return counts


########################
# Semantic Clustering  #
########################

def cluster_summaries(df: pd.DataFrame, language: str, n_clusters: int = 5):
	"""
	Returns a tuple: (df_lang_with_clusters, fitted_kmeans, fitted_vectorizer)
	Enhanced with better text cleaning to avoid stopwords/URLs dominating.
	"""
	df_lang = df[df["language"] == language].copy()
	df_lang["summary_clean"] = df_lang["summary"].fillna("").apply(clean_text_for_clustering)
	
	if df_lang.empty:
		df_lang["cluster"] = -1
		return df_lang, None, None
	
	# Increase max_features if desired
	vectorizer = TfidfVectorizer(max_features=5000, ngram_range=(2,3), min_df=2, max_df=0.8)
	X = vectorizer.fit_transform(df_lang["summary_clean"])
	
	kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init="auto")
	clusters = kmeans.fit_predict(X)
	df_lang["cluster"] = clusters
	
	return df_lang, kmeans, vectorizer




#######################
# Saving & Loading    #
#######################

def save_processed_notes(df: pd.DataFrame, output_path: str):
	"""
	Save the processed DataFrame to Parquet (or CSV).
	Parquet is usually smaller and faster to load.
	"""
	df.to_parquet(output_path, index=False)
	print(f"[DEBUG] Processed data saved to {output_path}")
