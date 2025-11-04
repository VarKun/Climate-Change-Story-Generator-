from datetime import datetime
import os
import io
import json
import uuid
import base64
from typing import Tuple

import requests
import streamlit as st
from PIL import Image
import argparse
from dotenv import load_dotenv
from groq import Groq
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate
import time
from supabase import create_client
from RAG import RAGEngine
from PIL import Image
from io import BytesIO
import zmq
from pathlib import Path
import socket


ROOT_DIR = Path(__file__).resolve().parent.parent

BUDDY_HOST = os.getenv("BUDDY_TCP_HOST", "127.0.0.1")
BUDDY_PORT = int(os.getenv("BUDDY_TCP_PORT", "5058"))


def send_to_buddy(line: str):
    if not line:
        return
    try:
        with socket.create_connection((BUDDY_HOST, BUDDY_PORT), timeout=3) as sock:
            sock.sendall(b"ROLE:app\n")
            sock.sendall((line + "\n").encode("utf-8"))
    except OSError as exc:
        print(f"[buddy] send failed: {exc}")


# TODO add the attach file to the top of the enter prompt 

class SupabaseLogger:
    def __init__(self):
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_KEY")
        
        try:
            self.supabase = create_client(supabase_url, supabase_key)
        except Exception as e:
            print(f"Initial connection failed: {str(e)}")
            raise

    def log_session(self, session_id):
        try:            
            self.supabase.table('chat_sessions').insert({
                'session_id': session_id,
                'start_time': datetime.now().isoformat(),
                'status': 'active'
            }).execute()
        except Exception as e:
            print(f"Failed to log session with error: {str(e)}")
            # Print more details about the error
            import traceback
            print("Full error traceback:")
            print(traceback.format_exc())
            raise
        
    def log_chat(self, session_id, role, message):
        self.supabase.table('chat_history').insert({
            'session_id': session_id,
            'role': role,
            'message': message,
            'timestamp': datetime.now().isoformat()
        }).execute()

    def log_image_description(self, session_id, description):
        self.supabase.table('image_descriptions').insert({
            'session_id': session_id,
            'description': description,
            'timestamp': datetime.now().isoformat()
        }).execute()
        
    def store_image(self, session_id, image_type, image_data, description=None):
        """Store image directly in database"""
        image_id = str(uuid.uuid4())
        
        self.supabase.table('images').insert({
            'image_id': image_id,
            'session_id': session_id,
            'type': image_type,
            'image_data': base64.b64encode(image_data).decode('utf-8'),
            'description': description,
            'timestamp': datetime.utcnow().isoformat()
        }).execute()
        
        return image_id
        
    def store_image(self, session_id, image_type, image_data, description=None):
        image_id = str(uuid.uuid4())
        file_path = f"{session_id}/{image_id}.png"
        
        self.supabase.storage.from_('images').upload(
            file_path,
            image_data
        )
        
        self.supabase.table('images').insert({
            'image_id': image_id,
            'session_id': session_id,
            'type': image_type,
            'storage_path': file_path,
            'description': description,
            'timestamp': datetime.utcnow().isoformat()
        }).execute()
        
        return file_path
    
    def close_session(self, session_id):
        self.supabase.table('chat_sessions').update({
            'status': 'complete',
            'end_time': datetime.utcnow().isoformat()
        }).eq('session_id', session_id).execute()

class ClimateStoryGenerator:
    def __init__(self):
        """
        Initialize the Climate Story Generator with necessary configurations
        """

        # Load environment variables
        load_dotenv()

        # Initialize Groq client and model
        self.client = Groq()
        # self.llama32_model = 'llama-3.2-11b-vision-preview'
        self.llama32_model = 'meta-llama/llama-4-scout-17b-16e-instruct'
        # Load stability API key
        self.sk_token = os.getenv("STABILITY_KEY")

        self.logger = SupabaseLogger()

        # Initialize session state
        self._initialize_session_state()

        # Create a context
        self.context = zmq.Context()
        # Create a PUSH socket (publisher)
        self.publisher = self.context.socket(zmq.PUB)
        self.publisher.bind("tcp://*:5555")  # Bind to TCP port 5555
        # Allow some time for subscribers to connect
        # time.sleep(1)

        # Drawing service integration disabled for public release.
        # self._drawing_service_host = os.getenv("LINEUS_BRIDGE_HOST", "127.0.0.1")
        # self._drawing_service_port = int(os.getenv("LINEUS_BRIDGE_PORT", "8765"))
        # self._drawing_service_timeout = float(os.getenv("LINEUS_BRIDGE_TIMEOUT", "15"))
        # self._drawing_service_save_svg = os.getenv("LINEUS_SAVE_SVG")
        # self._drawing_service_save_gcode = os.getenv("LINEUS_SAVE_GCODE")
        # self._drawing_service_lineus_host = os.getenv("LINEUS_HOST") or os.getenv("LINEUS_DEVICE_NAME")
        # port_override = os.getenv("LINEUS_PORT")
        # self._drawing_service_lineus_port = int(port_override) if port_override else None

    def _initialize_session_state(self):
        """
        Initialize or reset session state variables
        """
        if "session_id" not in st.session_state:
            st.session_state.session_id = str(uuid.uuid4())
            self.logger.log_session(st.session_state.session_id)
        if "chat_history" not in st.session_state:
            st.session_state.chat_history = []

    def setup_ui(self):
        """
        Set up Streamlit user interface with editing options
        """
        st.set_page_config(page_title="Climate Change Story Generator", page_icon=":earth_africa:")
        st.title("Climate Change Story Generator - University of Southampton")

        # Add sidebar with editing options
        st.sidebar.title("Story & Image Options")
        
        st.sidebar.markdown("""
        ### How to use:
        1. Enter a prompt to generate a climate story and image. For example: "generate me a story about a man that creates a robot that helps fight against climate change"
        2. To change just the image, include phrases like "**make the image** more realistic"
        3. To edit just the story, include phrases like "**update the story** to be more educational"
        """)

        # Display conversation history and images
        self._display_chat_history()


    def get_user_input(self):
        """Get user input with support for preset prompts"""
        if "preset_prompt" in st.session_state and st.session_state.preset_prompt:
            preset = st.session_state.preset_prompt
            user_query = st.chat_input("Enter your prompt or message", value=preset)
            # Clear the preset after use
            st.session_state.preset_prompt = ""
            return user_query
        else:
            return st.chat_input("Enter your prompt or message")
        
    def _add_session_management_buttons(self):
        """
        Add button to exit the chat session
        """
        if st.sidebar.button("Exit Session"):
            self.exit_session()

    def _reset_session_state(self):
        """
        Reset all session state variables
        """
        # Clear chat and image history
        st.session_state.chat_history = []
        st.session_state.image_history = []
        st.session_state.current_story = None
        st.session_state.current_image_description = None
        
        # Generate a new session ID for the next session
        st.session_state.chat_session_id = str(uuid.uuid4())

    def _display_chat_history(self):
        """
        Display chat history messages and images
        """
        for message in st.session_state.chat_history:
            if isinstance(message, dict):
                self._display_dict_message(message)
            elif isinstance(message, (HumanMessage, AIMessage)):
                self._display_langchain_message(message)

    def _display_dict_message(self, message):
        """
        Display a dictionary-type message
        """
        if message.get('role') == 'Human':
            with st.chat_message("Human"):
                if 'content' in message:
                    st.markdown(message['content'])
                if 'image' in message:
                    st.image(
                        message['image'],
                        caption=message.get('caption', 'Uploaded Image'),
                        use_container_width=True,
                    )
        elif message.get('role') == 'AI':
            with st.chat_message("AI"):
                if 'content' in message:
                    st.markdown(message['content'])
                if 'image' in message:
                    st.image(
                        message['image'],
                        caption=message.get('caption', 'Generated Image'),
                        use_container_width=True,
                    )
                    
    def _display_langchain_message(self, message):
        """
        Display a LangChain message
        """
        with st.chat_message("Human" if isinstance(message, HumanMessage) else "AI"):
            st.markdown(message.content)

    def encode_image(self, uploaded_image):
        """
        Encode an uploaded image to base64
        """
        return base64.b64encode(uploaded_image.read()).decode('utf-8')

    def image_to_text(self, base64_image, prompt):
        """
        Convert an image to text description
        """
        chat_completion = self.client.chat.completions.create(
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                    ]
                }
            ],
            model=self.llama32_model
        )
        return chat_completion.choices[0].message.content

    def generate_story(self, input_text):
        """
        Generate a short story based on input
        """
        chat_completion = self.client.chat.completions.create(
            messages=[
                {"role": "system", "content": "You are a children's book author specializing in climate change stories."},
                {"role": "user", "content": input_text}
            ],
            model=self.llama32_model
        )
        return chat_completion.choices[0].message.content

    def generate_story_summary(self, user_prompt):
        """
        Generate a summary if no image is provided
        """
        return f"This story explores climate change through the theme: '{user_prompt}'."

    def generate_story_image(self, description):
        """
        Generate an image based on story description
        """
        response = requests.post(
            f"https://api.stability.ai/v2beta/stable-image/generate/core",
            headers={
                "authorization": f"Bearer {self.sk_token}",
                "accept": "image/*"
            },
            files={"none": ''},
            data={
                "prompt": description,
                "output_format": "webp",
            },
        )
        if response.status_code == 200:
            return response.content
        else:
            raise Exception(str(response.json()))
        
    def display_streaming_story(self, story, delay=0.005):
        """
        Display the story character by character with a streaming effect

        Args:
            story (str): The story text to display
            delay (float): Delay between each character in seconds
        """
        # Create a placeholder for the streaming text
        story_placeholder = st.empty()
        displayed_text = ""
        
        # Stream each character
        for char in story:
            displayed_text += char
            story_placeholder.markdown(displayed_text + "▌")
            time.sleep(delay)
        
        # Show final text without cursor
        story_placeholder.markdown(displayed_text)

    def _parse_model_output(self, response: str) -> Tuple[str, str]:
        """Split the LLM response into image prompt and story body."""
        if not response:
            return "", ""
        cleaned = response.strip()
        if not cleaned:
            return "", ""
        parts = [part.strip() for part in cleaned.split("\n\n") if part.strip()]
        if not parts:
            return "", ""
        if len(parts) == 1:
            return "", parts[0]
        image_prompt = parts[0]
        story_text = "\n\n".join(parts[1:])
        return image_prompt, story_text

    def _coalesce_image_prompt(self, image_prompt: str, fallback_story: str, user_prompt: str = "") -> str:
        if image_prompt:
            return image_prompt
        base = fallback_story or user_prompt
        return f"A vivid illustration of a children's climate story: {base}".strip()

    # Drawing robot helper methods are disabled in this build.

    def get_response(self, use_rag=False, index_path=None, metadata_path=None, image_base64=None, user_prompt="", uploaded_image=None):
        """
        Generate a response based on user input.
        - If the user requests an image update, regenerate the image but keep the story unchanged.
        - If the user requests a story edit, modify the story but keep the image unchanged.
        - If the user requests both, update both the story and image.
        """
        story_placeholder = st.empty()
        image_placeholder = st.empty()

        # Detection for image change requests
        image_change_keywords = [
            "image",
            "change image", "new image", "different image", "update image", 
            "modify image", "another image", "remake image", "regenerate image",
            "make image more",
            "change the image", "new the image", "different the image", "update the image", 
            "modify the image", "another the image", "remake the image", "regenerate the image",
            "make the image more"
        ]
        
        # Detection for story edit requests
        story_edit_keywords = [
            "story",
            "edit story", "change story", "modify story", "update story",
            "rewrite story", "different story", "alter story", "adjust story",
            "change text", "edit text", "modify text",
            "but keep image", "same image", "don't change image", 
            "rewrite", "make story more", 
            "edit the story", "change the story", "modify the story", "update the story",
            "rewrite the story", "alter the story", "adjust the story",
            "change the text", "edit the text", "modify the text",
            "but keep the image", "same image", "don't change the image", 
            "rewrite", "make the story more", "change the story", "happy ending"


        ]
        
        # Detection for combined updates
        combined_update_keywords = [
            "change both", "update both", "modify both", "change everything",
            "both story and image", "story and image", "image and story",
            "change story and image", "update story and image"
        ]
        
        # Improved detection logic with better logging
        user_wants_image_update = any(keyword in user_prompt.lower() for keyword in image_change_keywords)
        user_wants_story_edit = any(keyword in user_prompt.lower() for keyword in story_edit_keywords)
        user_wants_combined_update = any(keyword in user_prompt.lower() for keyword in combined_update_keywords)
        
        
        # Check if we have existing content
        has_existing_story = "current_story" in st.session_state
        has_existing_image = "current_image" in st.session_state

        print(f"DEBUG - Image update: {user_wants_image_update}, Story edit: {user_wants_story_edit}, Combined: {user_wants_combined_update}, has_existing_story: {has_existing_story}, has_existing_image: {has_existing_image}")

        # CASE 0: User wants to update both story and image
        if (user_wants_combined_update or (user_wants_image_update and user_wants_story_edit)) and has_existing_story and has_existing_image:
            # Generate a new story based on the user's prompt and current story
            story_edit_prompt = f"""
            Edit the following story based on this request: "{user_prompt}".

            Respond with exactly two paragraphs and no headings:
            1) First paragraph: an updated, vivid illustration prompt (no label).
            2) Second paragraph: the revised story under 150 words (no label).

            Original story:
            {st.session_state.get('current_story', '')}
            """

            raw_story = self.generate_story(story_edit_prompt)
            image_prompt, story_text = self._parse_model_output(raw_story)
            story_text = story_text or raw_story.strip()
            st.session_state["current_story"] = story_text

            image_description = self._coalesce_image_prompt(image_prompt, story_text, user_prompt)
            st.session_state["current_image_description"] = image_description
            
            # Generate new image based on the updated description
            image_bytes = self.generate_story_image(image_description)
            image = Image.open(io.BytesIO(image_bytes))
            image_buffer = io.BytesIO()
            image.save(image_buffer, format="PNG")
            image_buffer.seek(0)
            
            # Store the new image in session state
            st.session_state["current_image"] = image_buffer
            
            # Display the image
            image_placeholder.image(image_buffer, use_container_width=True)
            
            # Store new image
            storage_path = self.logger.store_image(
                st.session_state.session_id,
                'generated',
                image_buffer.getvalue(),
                image_description
            )
            
            # Log chat for combined update
            self.logger.log_chat(st.session_state.session_id, 'AI', story_text)
            
            return raw_story, image_buffer
        
        # CASE 1: User wants to edit the story but keep the image
        elif user_wants_story_edit and not user_wants_image_update and has_existing_image:
            # Retrieve the existing image - avoid copying to maintain the same image buffer
            image_buffer = st.session_state["current_image"]
            
            # Generate a new story based on the user's prompt
            story_edit_prompt = f"""
            Edit the following story based on this request: "{user_prompt}".

            Respond with exactly two paragraphs and no headings:
            1) First paragraph: an updated illustration prompt (no label).
            2) Second paragraph: the revised story under 150 words (no label).

            Original story:
            {st.session_state.get('current_story', '')}
            """

            raw_story = self.generate_story(story_edit_prompt)
            image_prompt, story_text = self._parse_model_output(raw_story)
            story_text = story_text or raw_story.strip()
            st.session_state["current_story"] = story_text
            if image_prompt:
                st.session_state["current_image_description"] = image_prompt
            
            # Display the new story with the existing image
            image_placeholder.image(image_buffer, use_container_width=True)
            
            # Log chat for story update
            self.logger.log_chat(st.session_state.session_id, 'AI', story_text)
            
            return raw_story, image_buffer
        
        # CASE 2: User wants to update the image but keep the story
        elif user_wants_image_update and not user_wants_story_edit and has_existing_story:
            # Keep the existing story
            story = st.session_state["current_story"]

            
            # Create an image description that combines the original story with the user's new request
            if "current_image_description" not in st.session_state:
                # If no saved image description, use the story as a base
                image_description = f"{story}. {user_prompt}"
            else:
                # Modify the existing image description with the new request
                image_description = f"{st.session_state['current_image_description']}. {user_prompt}"
            
            # Save the updated image description for future modifications
            st.session_state["current_image_description"] = image_description
            
            # Generate new image based on the updated description
            image_bytes = self.generate_story_image(image_description)
            image = Image.open(io.BytesIO(image_bytes))
            image_buffer = io.BytesIO()
            image.save(image_buffer, format="PNG")
            image_buffer.seek(0)
            
            # Store the new image in session state
            st.session_state["current_image"] = image_buffer
            
            # Display the image
            image_placeholder.image(image_buffer, use_container_width=True)

            # Store new image
            storage_path = self.logger.store_image(
                st.session_state.session_id,
                'generated',
                image_buffer.getvalue(),
                image_description
            )

            # Log chat for image update
            self.logger.log_chat(st.session_state.session_id, 'AI', f"Updated image based on: {user_prompt}")

            combined_response = f"{image_description}\n\n{story}".strip()
            return combined_response, image_buffer

        # CASE 3: Generate both new story and image (default behavior for fresh generation)
        else:
            # Proceed with normal story generation
            image_description = ""
            if image_base64:
                image_description = self.image_to_text(image_base64, "Describe this image in relation to climate change.")
                self.logger.log_image_description(st.session_state.session_id, image_description)

            if use_rag:
                print("DEBUG - Using RAG")
                rag = RAGEngine(index_path, metadata_path)
                if image_base64:
                    context, distances, indices = rag.query(text_query=image_description, k=3)
                else:
                    context, distances, indices = rag.query(text_query=user_prompt, k=3)
                formatted_contexts = "\n".join([f"- **Context {i+1}**: {context}" for i, context in enumerate(context)])

                template = """
                You are a children's book author specializing in climate change stories.
                Using the user prompt, optional image description, and the factual context below, respond with exactly two paragraphs separated by a single blank line. Output nothing else.
                Paragraph 1 (no heading): a vivid illustration prompt an artist could use (<=50 words).
                Paragraph 2 (no heading): the full story suitable for children (<=150 words).
                User prompt: {user_prompt}
                Image description: {image_description}
                Context: {formatted_contexts}
                """
            else:
                template = """
                You are a children's book author specializing in climate change stories.
                Using the user prompt and optional image description below, respond with exactly two paragraphs separated by a single blank line. Output nothing else.
                Paragraph 1 (no heading): a vivid illustration prompt an artist could use (<=50 words).
                Paragraph 2 (no heading): the full story suitable for children (<=150 words).
                User prompt: {user_prompt}
                Image description: {image_description}
                """
            
            prompt = ChatPromptTemplate.from_template(template)
            prompt_text = prompt.format(
                user_prompt=user_prompt,
                image_description=image_description,
                formatted_contexts=formatted_contexts if 'formatted_contexts' in locals() else ""
            )

            raw_story = self.generate_story(prompt_text)
            image_prompt, story_text = self._parse_model_output(raw_story)
            story_text = story_text or raw_story.strip()
            st.session_state["current_story"] = story_text
            image_prompt = self._coalesce_image_prompt(image_prompt, story_text, user_prompt)
            st.session_state["current_image_description"] = image_prompt

            # Generate and display image
            image_bytes = self.generate_story_image(image_prompt)
            image = Image.open(io.BytesIO(image_bytes))
            image_buffer = io.BytesIO()
            image.save(image_buffer, format="PNG")
            image_buffer.seek(0)
            
            # Store the image in session state for future reference
            st.session_state["current_image"] = image_buffer
            
            # Display the image
            image_placeholder.image(image_buffer, use_container_width=True)

            # Store image and log chat
            self.logger.store_image(
                st.session_state.session_id,
                'generated',
                image_buffer.getvalue(),
                image_prompt
            )
            self.logger.log_chat(st.session_state.session_id, 'AI', story_text)

            return raw_story, image_buffer

    def save_image_buffer_to_png(self, image_buffer: BytesIO, output_path: str):
        """
        Saves an image buffer (in memory) to a PNG file.

        Args:
            image_buffer (BytesIO): The image buffer containing the image data.
            output_path (str): The file path where the PNG image will be saved.
        """
        # Open the image from the buffer
        image = Image.open(image_buffer)
        
        # Save the image as a PNG file
        image.save(output_path, 'PNG')

        print("Image has been save to: ", output_path)

    def save_txt(self, text:str, output_path: str):
        # Open the file in write mode ('w')
        with open(output_path, 'w') as file:
            file.write(text)
        
        print("Story has been save to: ", output_path)

    def run(self, use_rag, index_path=None, metadata_path=None):
        """
        Main method to run the Streamlit application
        """
        # Setup UI
        self.setup_ui()
        # uploaded_image = st.file_uploader("Upload an image", type=["jpg", "jpeg", "png"])
        uploaded_image = []
        
        # Get user input (now using the enhanced method)
        user_query = self.get_user_input()
        if user_query:
            with st.chat_message("Human"):
                st.markdown(user_query)
                self.logger.log_chat(st.session_state.session_id, 'Human', user_query)

            image_description = None
            if uploaded_image:
                uploaded_image.seek(0)
                image_base64 = self.encode_image(uploaded_image)
                
                # Generate image description when an image is uploaded
                image_description = self.image_to_text(image_base64, "Describe this image in relation to climate change.")
                self.logger.log_image_description(st.session_state.session_id, image_description)
                
                # Log the image upload with the description instead of generic message
                self.logger.log_chat(st.session_state.session_id, 'Image', f"Image description: {image_description}")
            else:
                image_base64 = None

            with st.chat_message("AI"):
                ai_response, generated_image = self.get_response(
                    use_rag,
                    index_path, 
                    metadata_path,
                    image_base64=image_base64,
                    user_prompt=user_query,
                    uploaded_image=uploaded_image
                )
            
            self.save_image_buffer_to_png(generated_image, "current.png")
            image_prompt, story_text_clean = self._parse_model_output(ai_response)
            story_text_clean = story_text_clean or ai_response.strip()
            self.save_txt(story_text_clean, "current.txt")
            image_path = ROOT_DIR / "current.png"
            image_b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
            st.session_state.last_story_text = story_text_clean
            st.session_state.last_image_prompt = image_prompt
            st.session_state.last_story_image = image_b64
            
            # Display the story using the streaming method
            self.display_streaming_story(story_text_clean)

            # Add to chat history
            st.session_state.chat_history.append({
                'role': 'Human',
                'content': user_query
            })
            
            # If there was an image, also add it to the chat history
            if uploaded_image:
                uploaded_image.seek(0)
                st.session_state.chat_history.append({
                    'role': 'Human',
                    'content': f"Image uploaded: {image_description}",
                    'image': uploaded_image,
                    'caption': image_description
                })
                
            st.session_state.chat_history.append({
                'role': 'AI',
                'content': story_text_clean,
                'image': generated_image
            })
        has_story = bool(st.session_state.get("last_story_text") and st.session_state.get("last_story_image"))
        drawing_status = st.empty()

        if has_story:
            if st.button("Robot Story Teller"):
                print("---------------------------Send")
                self.publisher.send_string("robot")

                story_text = st.session_state.get("last_story_text")
                story_image = st.session_state.get("last_story_image")

                if not story_text or not story_image:
                    st.warning("Generate the story first before activating the robot.")
                else:
                    story_payload = story_text.replace("\n", "\\n")
                    send_to_buddy("SAY_STORY:" + story_payload)
                    send_to_buddy("IMAGE_BASE64:" + story_image)

            # 已隐藏 Line-us Drawing 按钮，如需恢复请去掉条件
            # if st.button("Line-us Drawing"):
            #     self._send_image_to_drawing_robot(drawing_status)
        else:
            drawing_status.empty()
            st.info("Generate a story and illustration to unlock the robot controls.")



    def exit_session(self):
            """Handle session cleanup"""
            self.logger.close_session(st.session_state.session_id)
            self._reset_session_state()
                
                
def main(use_rag, index_path=None, metadata_path=None):
    """
    Main entry point for the Climate Change Story Generator.
    """
    # Initialize the story generator
    generator = ClimateStoryGenerator()

    if use_rag:
        # Ensure index and metadata paths are provided
        if not index_path or not metadata_path:
            print("Error: --index_path and --metadata_path are required when using RAG.")
            return
        
        # Check if paths exist
        if not os.path.exists(index_path):
            print(f"Error: Index file not found at {index_path}")
            return
        if not os.path.exists(metadata_path):
            print(f"Error: Metadata file not found at {metadata_path}")
            return

        #print("Using RAG with the provided FAISS index and metadata.")
        generator.run(use_rag=True, index_path=index_path, metadata_path=metadata_path)

    else:
        generator.run(use_rag=False)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Climate Change Story Generator.")
    
    # RAG option
    parser.add_argument("--use_rag", action="store_true", help="Enable Retrieval-Augmented Generation (RAG).")
    
    # FAISS index and metadata paths (only needed if --use_rag is set)
    parser.add_argument("--index_path", type=str, default="./faiss_indices/faiss_index.idx", help="Path to the FAISS index file (required if using RAG).")
    parser.add_argument("--metadata_path", type=str, default="./faiss_indices/combined_metadata.json", help="Path to the metadata JSON file (required if using RAG).")

    args = parser.parse_args()

    main(args.use_rag, args.index_path, args.metadata_path)
