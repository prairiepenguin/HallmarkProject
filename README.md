# The Hallmark Project

Streamlit app for exploring Hallmark movies, people, credits, and creative collaborations from the `hallmark.db` SQLite database.

## Database

The app expects `hallmark.db` to live in the same folder as `streamlit_app.py`.

Current tables:

- `movies`: movie metadata, Wikipedia source fields, and TMDB match fields
- `people`: unique people names
- `credits`: actor/director/writer credits linked to movies and people

## Features

- Start from a Home dashboard with quick search, project metrics, and recent movies
- Navigate with a sidebar menu instead of a crowded top tab row
- Search for movies and open dedicated movie detail pages
- Search for people and open dedicated person profile pages
- Click movie titles, directors, writers, actors, and collaborators throughout the app
- View person role counts, career timelines, collaboration networks, and movie credits
- See directors' most frequent writer collaborators
- Explore movies by year, network, director, writer, and director/writer team
- Compare frequent creative teams: director/writer, director/actor, actor pairs, and writer/actor
- Filter by title, year, decade, network, TMDB status, credit role, and credit source
- Review data quality issues such as missing dates, unmatched TMDB rows, possible duplicate titles, and source conflicts
- Run read-only SQL queries for deeper inspection

## Run Locally

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

## Deploy to Streamlit Community Cloud

1. Push this folder to GitHub, including `streamlit_app.py`, `requirements.txt`, `.streamlit/config.toml`, `ABOUT.md`, and `hallmark.db`.
2. In Streamlit Community Cloud, create a new app from the GitHub repository.
3. Set the main file path to `streamlit_app.py`.
4. Deploy.

No secrets are required for the current local SQLite version.
