#!/usr/bin/env python

##
# Global parameters
N = 10
RATIO = 0.4
WARNING_TEXT = f"\033[33mWARNING\033[0m: There is error in number of keywords.\n\tDo you want to proceed? (y/N): "
VECTOR_STORE_LOCATION = "./test/vector_store.json"

##
# Argement Parser
import re
import argparse

parser = argparse.ArgumentParser(
    prog='paper_rel_gen',
    description='Processes markdown notes with BibTeX to add metadata to paper notes.'
    )
parser.add_argument(
    'filename',
    help='Markdown file to process.'
    )
parser.add_argument(
    '-b',
    '--bibtex',
    action='store_true',
    help='Extract metatdata from bibtex entry codeblock'
    )
parser.add_argument(
    '-vs',
    '--vector-store',
    action='store_true',
    help='Creates embedding vector of the text.'
    )
parser.add_argument(
    '--keyword-only',
    action='store_true',
    help='Only prints keywords and exits.'
    )
args = parser.parse_args()


##
# Read file
import yaml
with open(args.filename, 'r') as file:
    markdown = file.readlines()

# Extract Markdown file metadata
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

# Extract BibTeX metadata
import bibtexparser

def bibtex_2_dict(bibtex):
    fields_dict = bibtex.fields_dict
    data = {}
    data["key"] = bibtex.key
    data["title"] = fields_dict['title'].value
    data["author"] = fields_dict['author'].value.split(' and ')
    data["year"] = fields_dict['year'].value
    return data

def extract_bibtex_entries(markdown_text):
    pattern = r'```BibTeX(.*?)```'
    match = re.findall(pattern, markdown_text, re.DOTALL | re.IGNORECASE)
    entry = bibtexparser.parse_string(match[0])
    return bibtex_2_dict(entry.entries[0])

##
# OpenAI
import os
from openai import OpenAI
endpoint = "https://models.inference.ai.azure.com"
token = os.environ["GITHUB_TOKEN"]

# OpenAI Embedding
from azure.ai.inference import EmbeddingsClient
from azure.core.credentials import AzureKeyCredential

def embedding(text: list[str]) -> list[float]: 
    embedding_model_name = "text-embedding-3-small"
    client = EmbeddingsClient(
        endpoint=endpoint,
        credential=AzureKeyCredential(token)
    )

    embedding_response = client.embed(
        input = text,
        model = embedding_model_name
    )

    embeddings = []
    for data in embedding_response.data:
        embeddings.append(data.embedding)

    return embeddings

# OpenAI Keyword Extraction
import json

def keyword_extraction(text: str) -> list[str]:
    chat_model_name = "gpt-4o-mini"
    client = OpenAI(
        base_url=endpoint,
        api_key=token,
    )

# TODO Category Prompt
    GPT_INSTRUCTIONS = f"""
    This GPT helps users generate a set of relevant keywords or tags based on the content of any note or text they provide.
    It offers concise, descriptive, and relevant tags that help organize and retrieve similar notes or resources later.
    The GPT will aim to provide up to {N} keywords, with 1 keyword acting as a category, {N*RATIO} general tags applicable to a broad context, and {N - 1 - N*RATIO} being more specific to the content of the note.
    It avoids suggesting overly generic or redundant keywords unless necessary.
    It will list the tags using underscores instead of spaces, ordered from the most general to the most specific.
    Every tag will be lowercase.
    Return the list in json format with key "keywords" for keyword list.
    """

    messages = [
        {"role":"system", "content": GPT_INSTRUCTIONS},
        {"role": "user", "content": text},
    ]

    completion = client.beta.chat.completions.parse(
        model = chat_model_name,
        messages = messages,
        response_format = { "type": "json_object" }
    )

    chat_response = completion.choices[0].message
    json_data = json.loads(chat_response.content)

    keywords = json_data["keywords"]

    try:
        assert len(keywords) == 10
    except:
        print(f"\033[33mWARNING\033[0m: created keywords({keywords})")
        if input(WARNING_TEXT) == 'y':
            return keywords
        print("\033[31mABORTED\033[0m")
        exit()

    return keywords



##
# Processing
metadata, body = extract_metadata(markdown)

keywords = keyword_extraction(body)

# If keyword only mode
if args.keyword_only:
    for keyword in keywords:
        print(f"- {keyword}")
    exit()

# Add metadata from bibtex
if args.bibtex:
    data = extract_bibtex_entries(body)

    metadata["key"] = data["key"]
    metadata["title"] = data["title"]
    metadata["author"] = data["author"]
    metadata["year"] = int(data["year"])


if args.vector_store:
    embeddings = embedding([body, metadata["title"]])

    # Vector store entry
    entry = {}
    metadata["key"] = data["key"]
    entry["embeddings"] = {"title": embeddings[0], "contents": embeddings[1]}
    entry["keywords"] = keywords

    with open(VECTOR_STORE_LOCATION, 'w') as fp:
        json.dump(entry, fp)

# Process metadata
from datetime import datetime

metadata["tags"] = ["Paper"] + keywords
metadata["category"] = keywords[0]
metadata["updated"] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')


# Add matadata to Markdown
with open(f"{args.filename}", 'w') as file:
    file.write("---\n")
    file.write(yaml.dump(metadata, default_flow_style=False))
    file.write("---\n")
    file.write(body)

