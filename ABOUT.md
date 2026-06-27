# About The Hallmark Project

Hello everyone, I'm Jacob, this little project was developed because I got curious to see what particular movies writers or directors made. Hopefully you can find some new movies favorites with the information here. 

This project is completely open sourced and is bound to have a lot of errors currently. I will be working on making the database better over time

## Nuts and Bolts of the Project

The Hallmark Project is an interactive Streamlit app for exploring Hallmark movies, the people who make them, and the creative relationships behind them.

The app is built around a local SQLite database, `hallmark.db`, with three core tables:

- `movies`: movie titles, dates, source fields, and TMDB matching information
- `people`: unique people connected to Hallmark productions
- `credits`: actor, director, writer, teleplay, screenplay, and story credits linked to movies and people

## What You Can Explore

Use the app to search for a movie, open a movie detail page, and see its cast, directors, writers, and related creative-team movies.

You can also search for a person and open a profile page with role counts, a career timeline, movie credits, and collaborator views. Director profiles highlight the writers they work with most.

The Trends and Teams pages help surface larger patterns, including movies by year, top directors, top writers, frequent director/writer teams, director/actor pairings, actor pairs, and writer/actor pairings.

## Data Quality

The Data Quality page is designed to help improve the dataset over time. It highlights missing years, missing air dates, unmatched TMDB records, weaker TMDB matches, possible duplicate titles, and source conflicts.

## Sources

The current dataset combines information gathered from Wikipedia-style source fields and TMDB matching fields. Credits may appear from multiple sources, so the app groups duplicate source rows where possible and counts distinct movies for rankings.

## Deployment

The app is designed to run locally or on Streamlit Community Cloud. For deployment, keep `app.py`, `requirements.txt`, `.streamlit/config.toml`, and `hallmark.db` together in the repository.
