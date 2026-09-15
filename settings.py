"""All knobs in one place, each overridable by environment variable. Defaults match a plain `docker compose up`.
   DATA_DIR=demo puts bronze/, silver/ and gold.db under demo/ so a trial never touches your real archive."""
import os
_e = os.environ.get
DATA_DIR = _e('DATA_DIR', '.')                                   # where bronze/, silver/, gold.db live
BRONZE = f'{DATA_DIR}/bronze'
SILVER = f'{DATA_DIR}/silver/emails.jsonl'
DB = f'{DATA_DIR}/gold.db'
OWN_ADDRESSES = {a.strip().lower() for a in _e('OWN_ADDRESSES', '').split(',') if a.strip()}   # "me@a.de,@mydomain.de"
EMBED_MODEL = _e('EMBED_MODEL', 'jinaai/jina-embeddings-v2-base-de')   # any fastembed model; DIM must match
EMBED_DIM = int(_e('EMBED_DIM', 768))
MODEL_DIR = _e('MODEL_DIR', 'models')                                   # Docker: /models baked into the image
EMBED_CHARS = int(_e('EMBED_CHARS', 20000))                             # body chars fed to the model (~8k tokens)
PAGE_SIZE = int(_e('PAGE_SIZE', 30))                                    # rows per browse page / default search hits
FUSION_K = int(_e('FUSION_K', 60))                                      # candidates per retriever before rank fusion
IMAGE_MIN_KB = int(_e('IMAGE_MIN_KB', 50))                              # smaller images are logos and pixels
IMAGE_DIR = _e('IMAGE_DIR', f'{DATA_DIR}/exports/images')
