Here's a guide for setting up your Supabase database for the project:

# Setting Up Your Supabase Database

## 1. Create a Supabase Account and Project
1. Go to [Supabase](https://supabase.com/) and sign up for an account
2. Click "New Project" and provide:
   - A project name of your choice
   - A secure password that you'll remember
   - Your preferred region for hosting
   - Wait for project creation to complete

## 2. Set Up Database Tables
1. In your project dashboard, navigate to the "SQL Editor" in the left sidebar
2. Copy and paste the following SQL code into the editor:

```sql
create table public.chat_sessions (
    session_id uuid not null,
    start_time timestamp without time zone null,
    end_time timestamp without time zone null,
    status text null,
    constraint chat_sessions_pkey primary key (session_id)
) tablespace pg_default;

create table public.chat_history (
    id bigint generated always as identity not null,
    session_id uuid null,
    role text null,
    message text null,
    timestamp timestamp without time zone null,
    constraint chat_history_pkey primary key (id),
    constraint chat_history_session_id_fkey foreign key (session_id) references chat_sessions (session_id)
) tablespace pg_default;

create table public.image_descriptions (
    id bigint generated always as identity not null,
    session_id uuid null,
    description text null,
    timestamp timestamp without time zone null,
    constraint image_descriptions_pkey primary key (id),
    constraint image_descriptions_session_id_fkey foreign key (session_id) references chat_sessions (session_id)
) tablespace pg_default;

create table public.images (
    image_id uuid not null,
    session_id uuid null,
    type text null,
    storage_path text null,
    description text null,
    timestamp timestamp without time zone null,
    image_data text null,
    constraint images_pkey primary key (image_id),
    constraint images_session_id_fkey foreign key (session_id) references chat_sessions (session_id)
) tablespace pg_default;
```

3. Click "Run" to create all tables

## 3. Create Storage Bucket
1. Click "Storage" in the left sidebar
2. Click "Create new bucket"
3. Name the bucket "images"
4. Leave other settings as default and click "Create bucket"

## 4. Get API Credentials
1. Go to "Project Settings" in the left sidebar
2. Click "API" under "Configuration"
3. You'll need two pieces of information:
   - Project URL
   - Project API key (use the anon/public key)

## 5. Configure Your Project
1. In your local project directory, create a `.env` file
2. Add your Supabase credentials in this format:
```
SUPABASE_URL=your_project_url
SUPABASE_KEY=your_project_api_key
```

## Database Structure
The database consists of four main tables:

### chat_sessions
- Tracks active chat sessions
- Contains session ID, start time, end time, and status
- Primary table that other tables reference

### chat_history
- Records all AI and human interactions
- Links to chat_sessions via session_id
- Stores message content, role (AI/human), and timestamp

### image_descriptions
- Stores descriptions of generated images
- Links to chat_sessions via session_id
- Includes timestamp information

### images
- Stores image metadata and references
- Links to chat_sessions via session_id
- Contains image type, storage path, and optional description
- Can include direct image data or reference to storage bucket

## Data Access
- All interaction data can be exported as CSV from the Supabase dashboard
- Images can be accessed through the Storage bucket
- You can query relationships between sessions, messages, and images using the session_id