#!/bin/sh
### Without RAG ###
python -m streamlit run src/app.py

### With RAG ###
#python -m streamlit run src/app.py -- --use_rag \
#--index_path "path/to/index.idx" \
#--metadata_path "path/to/metadata.json"

######### RAG #########
### Using the Existing Knowledge Base ###
#python src/RAG.py \
#--index_path "pth/to/index(.idx)" \
#--metadata_path "pth/to/metadata(.json)" \
#--text_query 'what do you know about climate change'

### Adding More Data ### 
## Adding New Text Data ##
#python src/RAG.py \
#--index_path "pth/to/index(.idx)" \
#--metadata_path "pth/to/metadata(.json)" \
#--new_text_file "path/to/text/file(.txt)"

## Adding New Images ##
#python src/RAG.py \
#--index_path "pth/to/index(.idx)" \
#--metadata_path "pth/to/metadata(.json)" \
#--new_img_dir "path/to/new_images/" \
#--database_dir "path/to/image_database/"

## Adding Both Text and Images ##
#python src/RAG.py \
#--index_path "pth/to/index(.idx)" \
#--metadata_path "pth/to/metadata(.json)" \
#--new_text_file "path/to/text/file(.txt)" \
#--new_img_dir "path/to/new_images/" \
#--database_dir "path/to/image_database/"

