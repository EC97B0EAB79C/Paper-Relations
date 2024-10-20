#!/usr/bin/env python

##
# Global parameters
import os
DB_LOCATION = os.environ["PAPER_REL_DB"]

##
# Argement Parser
import re
import argparse

parser = argparse.ArgumentParser(
    prog='paper_db_creation',
    description='Create DB for paper relations'
    )
parser.add_argument(
    'path',
    help='Paper memo location',
    default='./'
    )
parser.add_argument(
    '--metatags',
    nargs="+",
    type=str,
    default=["Paper"]
    )
args = parser.parse_args()


##
# Load/Save DB
import pandas
import json

def load_db(path):    
    df=pandas.DataFrame()
    try:
        df = pandas.read_hdf(path, key='df')
    except FileNotFoundError:
        pass
    except Exception as e: 
        print("Error when loading DB")
        print(e)

    print(f"Loaded {len(df.index)} entries")
    return df


def save_db(path, df):
    try:
        df.to_hdf(path, key='df', mode='w')
    except Exception as e: 
        print("Error when saving to DB")
        print(e)
        exit()
    print(f"Saved {len(df.index)} entries")


def update_entries(old_entries, new_entries):
    if old_entries.empty:
        return new_entries
    return old_entries.set_index('key').combine_first(new_entries.set_index('key')).reset_index()
    


##
# OpenAI Embedding API
from openai import OpenAI

endpoint = "https://models.inference.ai.azure.com"
token = os.environ["GITHUB_TOKEN"]
embedding_model_name = "text-embedding-3-small"
client = OpenAI(base_url=endpoint, api_key=token)

def embedding(text: list[str]) -> list[list[float]]: 
    embedding_response = client.embeddings.create(
        input = text,
        model = embedding_model_name,
    )

    embeddings = []
    for data in embedding_response.data:
        embeddings.append(data.embedding)
    
    print(embedding_response.usage)
    return embeddings


##
# Extract metadata
import yaml
def extract_metadata(markdown):
    while markdown[0].strip() =='':
        markdown = markdown[1:]
    if '---' not in markdown[0].strip():
        return {}, ''.join(markdown)

    markdown = markdown[1:]
    for idx, line in enumerate(markdown):
        if '---' in line.strip():
            metadata_end = idx
            break

    metadata_text = ''.join(markdown[:metadata_end])
    metadata = yaml.safe_load(metadata_text)

    return metadata, ''.join(markdown[metadata_end+1:])


##
# Process files
def process_file(file):
    print(f"Processing [{file}]:")
    try:
        with open(file, 'r') as f:
            metadata, body = extract_metadata(f.readlines())
    except Exception as e: 
        print(e)
        return None

    if not metadata.get("key", None):
        return None

    entry = {}
    entry["key"] = metadata["key"]
    entry["title"] = metadata["title"]
    entry["category"] = metadata["category"]
    entry["year"] = metadata["year"]
    entry["tags"] = list(filter(lambda t: t not in args.metatags, metadata['tags']))

    embeddings = embedding([metadata["title"], body])
    entry["embedding_title"] = embeddings[0]
    entry["embedding_body"] = embeddings[1]

    return entry
    

def process_files(files):
    entries = []
    for file in files:
        if ".md" not in file[-3:]: continue

        entry = process_file(file)
        if not entry: continue
        entries.append(entry)

    return entries


def process_path(path):
    entries = []
    for (root, dirs, files) in os.walk(path):
        entries = entries + process_files(
                map(lambda file: os.path.join(root, file), files)
            )
        
    return entries


##
# Main processing
old_entries = load_db(DB_LOCATION)
new_entries = pandas.DataFrame.from_dict(process_path(args.path))
updated_entries = update_entries(old_entries, new_entries)
save_db(DB_LOCATION, updated_entries)
