from sentence_transformers import SentenceTransformer
from transformers import CLIPProcessor, CLIPModel
from PIL import Image
import faiss
import numpy as np
import torch
import json
import matplotlib.pyplot as plt
import os
import argparse
import shutil

class RAGEngine:
    def __init__(self, index_path=None, metadata_path=None, clip_model_name="openai/clip-vit-base-patch32"):
        """
        Initialize the QueryEngine with required models, index, and metadata.
        
        Parameters:
        - index_path: Path to the FAISS index file.
        - metadata_path: Path to the metadata JSON file.
        """
        # Load models
        self.clip_model = CLIPModel.from_pretrained(clip_model_name)
        self.clip_processor = CLIPProcessor.from_pretrained(clip_model_name)

        # Load FAISS index and metadata
        self.index_path = index_path
        self.metadata_path = metadata_path
        if self.index_path:
            self.index = self._load_faiss_index(index_path)
        if self.metadata_path:
            self.metadata = self._load_metadata(metadata_path)

    @staticmethod
    def _load_faiss_index(index_path):
        return faiss.read_index(index_path)

    @staticmethod
    def _load_metadata(metadata_path):
        with open(metadata_path, "r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def _normalize_embeddings(embeddings):
        return embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)

    def _encode_text(self, texts):
        inputs = self.clip_processor(text=texts, return_tensors="pt", padding=True, truncation=True)
        with torch.no_grad():
            text_embeddings = self.clip_model.get_text_features(**inputs)
        return text_embeddings.cpu().numpy()

    def _encode_image(self, images=None, image_paths=None):
        if image_paths:
            images = [Image.open(path).convert("RGB") for path in image_paths]
        inputs = self.clip_processor(images=images, return_tensors="pt", padding=True)
        with torch.no_grad():
            image_embeddings = self.clip_model.get_image_features(**inputs)
        return image_embeddings.cpu().numpy()

    def combine_chunks_based_on_id(self, indices, metadata):
        # Create a dictionary to store the full articles
        results = []
        
        # Step 1: Group entries by their main ID (before the dot)
        grouped_by_article = {}
        
        # Populate the grouped dictionary with content based on main ID
        for entry in metadata:
            if entry.get('type') == 'text':  # We only care about text entries
                main_id = entry['ID'].split('.')[0]  # Get the part before the dot (e.g., '1' from '1.1')
                if main_id not in grouped_by_article:
                    grouped_by_article[main_id] = []
                grouped_by_article[main_id].append(entry)
        
        # Step 2: For each index in the provided indices list, find the corresponding article
        for idx in indices[0]:
            if idx < len(metadata):
                # Get the main ID of the selected entry
                selected_entry = metadata[idx]
                main_id = selected_entry['ID'].split('.')[0]
                
                # Get all entries with the same main ID
                article_chunks = [entry for entry in grouped_by_article.get(main_id, [])]
                
                # Step 3: Sort chunks by the chunk number (after the dot) and combine them
                article_chunks_sorted = sorted(article_chunks, key=lambda x: float(x['ID'].split('.')[1]))  # Sort by chunk number
                
                # Combine all content for the full article
                full_article = " ".join([entry['content'] for entry in article_chunks_sorted])
                
                # Add the combined full article to the results
                results.append(full_article)

        return results


    def query(self, text_query=None, image=None, k=5, text_weight=0.5, image_weight=0.5):
        """
        Query the FAISS index using a combined text and image query.
        
        Parameters:
        - text_query: A string representing the text query.
        - image: A PIL.Image object representing the image query.
        - k: Number of results to retrieve.
        - text_weight: Weight for the text embedding in the combined query.
        - image_weight: Weight for the image embedding in the combined query.
        
        Returns:
        - List of relevant text retrieved from the metadata.
        """
        combined_embedding = None

        # Encode text query if provided
        if text_query:
            text_embedding = self._normalize_embeddings(self._encode_text([text_query]))
            combined_embedding = text_weight * text_embedding

        # Encode image query if provided
        if image:
            image_embedding = self._normalize_embeddings(self._encode_image(image))
            if combined_embedding is None:
                combined_embedding = image_weight * image_embedding
            else:
                combined_embedding += image_weight * image_embedding

        # Query the FAISS index
        distances, indices = self.index.search(combined_embedding, k)

        # Retrieve corresponding metadata, only for 'text' entries
        #results = self.combine_chunks_based_on_id(indices, self.metadata)
        results = [self.metadata[idx]['content'] for idx in indices[0] if idx < len(self.metadata) and self.metadata[idx].get('type') == 'text']
        
        return results, distances, indices
    

    def create_new_index(self):
        #with open(metadata_path, "r", encoding="utf-8") as f:
        #    metadata = json.load(f)

        embeddings = []

        text_data = []
        image_paths = []
        for entry in self.metadata:
            if entry['type'] == 'text':
                text_data.append(entry['content'])
            elif entry['type'] == 'image':
                image_paths.append(entry['image_path'])

        text_embedding = self._encode_text(text_data)
        embeddings.append(text_embedding)
        image_embedding = self._encode_image(image_paths=image_paths)
        embeddings.append(image_embedding)

        # Normalize embeddings
        embeddings = np.vstack(embeddings)
        embeddings = self._normalize_embeddings(embeddings)

        # Create FAISS index
        dimension = embeddings.shape[1]
        index = faiss.IndexFlatL2(dimension)
        index.reset()
        index.add(embeddings)

        # Save FAISS index
        faiss.write_index(index, "faiss_index.idx")

    def add_new_data(self, new_texts=None, imgs=None, img_pths=None, chunk_size=100, min_chunk_size=10):
        """
        Add new text or image data to the FAISS index and metadata, with chunking for long texts.
        
        Parameters:
        - new_texts: List of new text entries to add.
        - new_images: List of new PIL.Image objects to add.
        
        Updates the index and metadata in-place.
        """
        new_embeddings = []
        new_metadata = []
        current_topic_id = len(self.metadata)

        if new_texts:
            chunked_texts = []
            chunked_ids = []
            chunked_titles = []
            chunked_summaries = []
            
            for text_idx, text in enumerate(new_texts):
                words = text.split()
                title = text.split(".")[0]  # Use the first sentence as the title
                summary = " ".join(words[:20])  # First 20 words as a summary
                if len(words) <= chunk_size:
                    if len(words) >= min_chunk_size:  # Keep only valid chunks
                        chunked_texts.append(text)
                        chunked_ids.append(f"{current_topic_id}.1")  # Assign chunk ID
                        chunked_titles.append(title)
                        chunked_summaries.append(summary)
                else:
                    chunks = [words[i:i + chunk_size] for i in range(0, len(words), chunk_size)]
                    if len(chunks) > 1 and len(chunks[-1]) < min_chunk_size:
                        chunks[-2].extend(chunks[-1])
                        chunks.pop()
                    for sub_idx, chunk in enumerate(chunks, start=1):
                        if len(chunk) >= min_chunk_size:
                            chunked_texts.append(' '.join(chunk))
                            chunked_ids.append(f"{current_topic_id}.{sub_idx}")
                            chunked_titles.append(title)
                            chunked_summaries.append(summary)
                current_topic_id += 1  # Increment topic ID
            text_embeddings = self._normalize_embeddings(self._encode_text(chunked_texts))
            new_embeddings.append(text_embeddings)
            for idx, (chunk, chunk_id, title, summary) in enumerate(zip(chunked_texts, chunked_ids, chunked_titles, chunked_summaries)):
                new_metadata.append({
                    "type": "text",
                    "ID": chunk_id,
                    "title": title,
                    "summary": summary,
                    "content": chunk,
                    "source": "User Input"  # Change if needed
                })

        if img_pths:
            image_embeddings = self._normalize_embeddings(
                np.vstack([self._encode_image(image) for image in imgs])
            )
            new_embeddings.append(image_embeddings)
            for idx, img_pth in enumerate(img_pths):
                img_id = f"{len(self.metadata) + len(new_metadata) + idx}"  # Unique ID for image
                new_metadata.append({
                    "type": "image",
                    "ID": img_id,
                    "title": os.path.basename(img_pth).replace("_", " ").split(".")[0],  # Use filename as title
                    "summary": "",
                    "content": "",
                    "source": "User Upload",  # Change if needed
                    "image_path": img_pth
                })
            
        if new_embeddings:
            combined_embeddings = np.vstack(new_embeddings)
            self.index.add(combined_embeddings)
            self.metadata.extend(new_metadata)
        self.save()

    def add_images(self, img_dir=None, database_dir=None):
        """
        Loads images from a file path or directory and returns a list of PIL Image objects.
        
        Parameters:
        - image_path (str): Path to a single image file.
        - image_dir (str): Path to a directory containing images.
        
        Returns:
        - List of tuples (PIL.Image, image_path) for further processing.
        """
        image_paths = []
        imgs = []
        if not os.path.isdir(img_dir) or not os.path.isdir(database_dir):
            print(f"Error: Directory not found at {img_dir} or {database_dir}")
            return image_paths
         

        for filename in os.listdir(img_dir):
            file_path = os.path.join(img_dir, filename)

            if file_path.lower().endswith(('.png', '.jpg', '.jpeg')):
                try:
                    # Move image to the database folder
                    img = Image.open(file_path).convert("RGB")
                    imgs.append(img)
                    new_path = os.path.join(database_dir, filename)
                    shutil.move(file_path, new_path)
                    #new_images = [Image.open("/path/to/new_image1.jpg").convert("RGB"), Image.open("/path/to/new_image2.jpg").convert("RGB")]
                    image_paths.append(new_path)
                except Exception as e:
                    print(f"Error processing image {file_path}: {e}")

        return imgs, image_paths


    def add_data_from_txt(self, file_path):
        """
        Reads text data from a .txt file and adds it to knowledge base and updates index.

        Parameters:
        - file_path: Path to the text file.

        """
        if not os.path.exists(file_path):
            print(f"Error: File {file_path} not found.")
            return []

        with open(file_path, "r", encoding="utf-8") as file:
            text_data = file.read().strip()

        # Split by paragraphs (or use file.readlines() if you want line-by-line splitting)
        text_chunks = text_data.split("\n\n")  # Assuming paragraphs are separated by double newlines
        new_texts = [chunk.strip() for chunk in text_chunks if chunk.strip()]
        return new_texts
        #self.add_new_data(new_texts)
        #self.create_new_index()
        #return [chunk.strip() for chunk in text_chunks if chunk.strip()]

    def save(self):
        """
        Save the FAISS index and metadata.
        """
        faiss.write_index(self.index, self.index_path)
        with open(self.metadata_path, "w", encoding="utf-8") as f:
            json.dump(self.metadata, f, indent=4)



def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(description="Run RAGEngine with FAISS index and metadata.")
    parser.add_argument("--index_path", type=str, required=True, help="Path to the FAISS index file.")
    parser.add_argument("--metadata_path", type=str, required=True, help="Path to the metadata JSON file.")
    parser.add_argument("--text_query", type=str, required=False, help="Please provide the text_query for retrieval")
    parser.add_argument("--new_text_file", type=str, required=False, help="Path to the text file to add new data. (.txt file)")
    parser.add_argument("--new_img_dir", type=str, required=False, help="Path to a directory containing new images.")
    parser.add_argument("--database_dir", type=str, required=False, help="Path to the existing image database where new images will be stored.")

    args = parser.parse_args()
    #print(args)
    # Check if index and metadata paths exist
    if not os.path.exists(args.index_path):
        print(f"Error: Index file not found at {args.index_path}")
        return
    if not os.path.exists(args.metadata_path):
        print(f"Error: Metadata file not found at {args.metadata_path}")
        return
    if args.database_dir and not os.path.isdir(args.database_dir):
        print(f"Error: Database directory not found at {args.database_dir}")
        return
    if args.database_dir:
        if not os.path.isdir(args.database_dir):
            print(f"Database directory not found at {args.database_dir}. Creating it now...")
            os.makedirs(args.database_dir, exist_ok=True)  # Create the directory
            print(f"Database directory created at {args.database_dir}")

    # Initialize RAGEngine
    engine = RAGEngine(index_path=args.index_path, metadata_path=args.metadata_path)

    new_texts = []
    new_image_paths = []
    imgs = None
    if args.new_text_file:
        try:
            new_texts = engine.add_data_from_txt(args.new_text_file)
            #print(new_texts)
        except Exception as e:
            print(e)
            return
        
    if args.new_img_dir:
        if not args.database_dir:
            print("Error: --database_dir is required when adding new images.")
            return
        try:
            imgs, new_image_paths = engine.add_images(img_dir=args.new_img_dir, database_dir=args.database_dir)
            #print(new_image_paths)
        except Exception as e:
            print(e)
            return
    
    
    if new_texts or new_image_paths:
        print(f"Adding {len(new_texts)} new text entries and {len(new_image_paths)} new images to FAISS index...")
        engine.add_new_data(new_texts=new_texts, imgs=imgs, img_pths=new_image_paths)
        print("Data successfully added and index updated!")

    #text_query = "A polar bear lying on an ice floe, a significant symbol of the impact of climate change."
    if args.text_query:
        ret_context, distances, indices = engine.query(text_query=args.text_query, k=3)

        # Print query results
        print("\nQuery Results:")
        for i, result in enumerate(ret_context):
            print(f"{i + 1}: {result}")


if __name__ == "__main__":
    main()
