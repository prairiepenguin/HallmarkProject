from pathlib import Path
import sqlite3

import pandas as pd
import streamlit as st


APP_DIR = Path(__file__).parent
DB_PATH = APP_DIR / "hallmark.db"
WRITING_ROLES = ("Writer", "Teleplay", "Story", "Screenplay")
CREATIVE_ROLES = ("Director",) + WRITING_ROLES


st.set_page_config(
    page_title="The Hallmark Project",
    page_icon=":material/movie:",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_resource
def get_connection() -> sqlite3.Connection:
    if not DB_PATH.exists():
        st.error("Could not find hallmark.db next to app.py.")
        st.stop()

    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


@st.cache_data(show_spinner=False)
def load_frame(query: str, params: tuple = ()) -> pd.DataFrame:
    return pd.read_sql_query(query, get_connection(), params=params)


def placeholders(items: tuple | list) -> str:
    return ", ".join("?" for _ in items)


@st.cache_data(show_spinner=False)
def get_year_bounds() -> tuple[int, int]:
    row = get_connection().execute(
        "SELECT MIN(year) AS min_year, MAX(year) AS max_year FROM movies WHERE year IS NOT NULL"
    ).fetchone()
    return int(row["min_year"]), int(row["max_year"])


@st.cache_data(show_spinner=False)
def get_networks() -> list[str]:
    rows = get_connection().execute(
        """
        SELECT DISTINCT network
        FROM movies
        WHERE network IS NOT NULL AND TRIM(network) <> ''
        ORDER BY network
        """
    ).fetchall()
    return [row["network"] for row in rows]


@st.cache_data(show_spinner=False)
def get_roles() -> list[str]:
    rows = get_connection().execute(
        "SELECT DISTINCT role FROM credits ORDER BY role COLLATE NOCASE"
    ).fetchall()
    return [row["role"] for row in rows]


@st.cache_data(show_spinner=False)
def get_sources() -> list[str]:
    rows = get_connection().execute(
        "SELECT DISTINCT source FROM credits ORDER BY source COLLATE NOCASE"
    ).fetchall()
    return [row["source"] for row in rows]


@st.cache_data(show_spinner=False)
def search_people(search: str) -> pd.DataFrame:
    term = search.strip().lower()
    if not term:
        return load_frame(
            """
            SELECT p.person_id, p.name, COUNT(DISTINCT c.movie_id) AS credits
            FROM people p
            LEFT JOIN credits c ON c.person_id = p.person_id
            GROUP BY p.person_id, p.name
            ORDER BY credits DESC, p.name COLLATE NOCASE
            LIMIT 75
            """
        )

    return load_frame(
        """
        SELECT p.person_id, p.name, COUNT(DISTINCT c.movie_id) AS credits
        FROM people p
        LEFT JOIN credits c ON c.person_id = p.person_id
        WHERE LOWER(p.name) LIKE ?
        GROUP BY p.person_id, p.name
        ORDER BY
            CASE WHEN LOWER(p.name) = ? THEN 0 WHEN LOWER(p.name) LIKE ? THEN 1 ELSE 2 END,
            credits DESC,
            p.name COLLATE NOCASE
        LIMIT 75
        """,
        (f"%{term}%", term, f"{term}%"),
    )


@st.cache_data(show_spinner=False)
def search_movies(search: str) -> pd.DataFrame:
    term = search.strip().lower()
    if not term:
        return load_frame(
            """
            SELECT movie_id, title, year, original_air_date, network
            FROM movies
            ORDER BY COALESCE(year, 0) DESC, title COLLATE NOCASE
            LIMIT 75
            """
        )

    return load_frame(
        """
        SELECT movie_id, title, year, original_air_date, network
        FROM movies
        WHERE LOWER(title) LIKE ?
        ORDER BY
            CASE WHEN LOWER(title) = ? THEN 0 WHEN LOWER(title) LIKE ? THEN 1 ELSE 2 END,
            COALESCE(year, 0) DESC,
            title COLLATE NOCASE
        LIMIT 75
        """,
        (f"%{term}%", term, f"{term}%"),
    )


@st.cache_data(show_spinner=False)
def get_person_name(person_id: int) -> str:
    row = get_connection().execute(
        "SELECT name FROM people WHERE person_id = ?",
        (person_id,),
    ).fetchone()
    return row["name"] if row else "Unknown"


@st.cache_data(show_spinner=False)
def get_movie_title(movie_id: int) -> str:
    row = get_connection().execute(
        "SELECT title FROM movies WHERE movie_id = ?",
        (movie_id,),
    ).fetchone()
    return row["title"] if row else "Unknown"


def open_person(person_id: int) -> None:
    st.session_state.view = "person"
    st.session_state.selected_person_id = int(person_id)


def open_movie(movie_id: int) -> None:
    st.session_state.view = "movie"
    st.session_state.selected_movie_id = int(movie_id)


def back_to_explorer() -> None:
    st.session_state.view = "explorer"


def metric_row() -> None:
    summary = load_frame(
        """
        SELECT
            COUNT(*) AS movies,
            COUNT(CASE WHEN tmdb_match_found = 1 THEN 1 END) AS tmdb_matches,
            COUNT(DISTINCT year) AS years,
            (SELECT COUNT(*) FROM people) AS people,
            (SELECT COUNT(*) FROM credits) AS credits
        FROM movies
        """
    ).iloc[0]

    cols = st.columns(5)
    cols[0].metric("Movies", f"{summary.movies:,.0f}")
    cols[1].metric("People", f"{summary.people:,.0f}")
    cols[2].metric("Credits", f"{summary.credits:,.0f}")
    cols[3].metric("Years", f"{summary.years:,.0f}")
    cols[4].metric("TMDB matches", f"{summary.tmdb_matches:,.0f}")


def sidebar_filters(alias: str = "m") -> tuple[str, tuple]:
    min_year, max_year = get_year_bounds()
    decade_options = list(range((min_year // 10) * 10, (max_year // 10) * 10 + 1, 10))

    st.sidebar.header("Filters")
    search = st.sidebar.text_input("Movie title contains")
    year_range = st.sidebar.slider("Year", min_year, max_year, (min_year, max_year))
    decades = st.sidebar.multiselect("Decade", decade_options, format_func=lambda d: f"{d}s")
    networks = st.sidebar.multiselect("Network", get_networks())
    tmdb_status = st.sidebar.selectbox("TMDB status", ["Any", "Matched", "Unmatched"])
    roles = st.sidebar.multiselect("Credit role", get_roles())
    sources = st.sidebar.multiselect("Credit source", get_sources())

    where = [f"({alias}.year IS NULL OR {alias}.year BETWEEN ? AND ?)"]
    params: list = [year_range[0], year_range[1]]

    if search.strip():
        where.append(f"LOWER({alias}.title) LIKE ?")
        params.append(f"%{search.strip().lower()}%")

    if decades:
        decade_parts = []
        for decade in decades:
            decade_parts.append(f"({alias}.year BETWEEN ? AND ?)")
            params.extend([decade, decade + 9])
        where.append("(" + " OR ".join(decade_parts) + ")")

    if networks:
        where.append(f"{alias}.network IN ({placeholders(networks)})")
        params.extend(networks)

    if tmdb_status == "Matched":
        where.append(f"{alias}.tmdb_match_found = 1")
    elif tmdb_status == "Unmatched":
        where.append(f"COALESCE({alias}.tmdb_match_found, 0) = 0")

    credit_filters = []
    credit_params = []
    if roles:
        credit_filters.append(f"fc.role IN ({placeholders(roles)})")
        credit_params.extend(roles)
    if sources:
        credit_filters.append(f"fc.source IN ({placeholders(sources)})")
        credit_params.extend(sources)
    if credit_filters:
        where.append(
            f"EXISTS (SELECT 1 FROM credits fc WHERE fc.movie_id = {alias}.movie_id AND "
            + " AND ".join(credit_filters)
            + ")"
        )
        params.extend(credit_params)

    return " AND ".join(where), tuple(params)


def movie_button_rows(frame: pd.DataFrame, key_prefix: str, title_col: str = "title", id_col: str = "movie_id") -> None:
    if frame.empty:
        st.caption("No movies found.")
        return

    for row in frame.itertuples(index=False):
        data = row._asdict()
        year = data.get("year")
        label_year = "Unknown" if pd.isna(year) else str(int(year))
        cols = st.columns([4, 1, 2])
        cols[0].button(data[title_col], key=f"{key_prefix}-{data[id_col]}", on_click=open_movie, args=(int(data[id_col]),), use_container_width=True)
        cols[1].write(label_year)
        cols[2].write(data.get("network") or "")


def person_button_rows(frame: pd.DataFrame, key_prefix: str, name_col: str, id_col: str, metric_col: str) -> None:
    if frame.empty:
        st.caption("No people found.")
        return

    for idx, row in enumerate(frame.itertuples(index=False)):
        data = row._asdict()
        cols = st.columns([4, 1])
        cols[0].button(
            data[name_col],
            key=f"{key_prefix}-{idx}-{data[id_col]}",
            on_click=open_person,
            args=(int(data[id_col]),),
            use_container_width=True,
        )
        cols[1].metric(metric_col.replace("_", " ").title(), f"{data[metric_col]:,.0f}")


def movie_search_view() -> None:
    st.subheader("Find a Movie")
    search = st.text_input("Search by title", key="movie_lookup_search")
    movie_button_rows(search_movies(search), "movie-search")


def person_search_view() -> None:
    st.subheader("Find a Person")
    search = st.text_input("Search by name", key="person_lookup_search")
    person_button_rows(search_people(search), "person-search", "name", "person_id", "credits")


def movies_view(where_clause: str, params: tuple) -> None:
    movies = load_frame(
        f"""
        SELECT
            m.movie_id,
            m.title,
            m.year,
            m.original_air_date,
            m.network,
            m.tmdb_title,
            m.tmdb_release_date,
            ROUND(m.tmdb_similarity, 3) AS tmdb_similarity,
            m.tmdb_match_found
        FROM movies m
        WHERE {where_clause}
        ORDER BY COALESCE(m.year, 0) DESC, m.title COLLATE NOCASE
        LIMIT 500
        """,
        params,
    )

    st.subheader("Movies")
    movie_button_rows(movies[["movie_id", "title", "year", "network"]], "movies-list")
    with st.expander("Table view"):
        st.dataframe(movies, use_container_width=True, hide_index=True)


def get_movie_creatives(movie_id: int) -> pd.DataFrame:
    return load_frame(
        f"""
        SELECT
            p.person_id,
            p.name,
            c.role,
            GROUP_CONCAT(DISTINCT c.source) AS sources
        FROM credits c
        JOIN people p ON p.person_id = c.person_id
        WHERE c.movie_id = ? AND c.role IN ({placeholders(CREATIVE_ROLES)})
        GROUP BY p.person_id, p.name, c.role
        ORDER BY
            CASE c.role
                WHEN 'Director' THEN 0
                WHEN 'Writer' THEN 1
                WHEN 'Screenplay' THEN 2
                WHEN 'Teleplay' THEN 3
                WHEN 'Story' THEN 4
                ELSE 5
            END,
            p.name COLLATE NOCASE
        """,
        (movie_id, *CREATIVE_ROLES),
    )


def movie_detail_page(movie_id: int) -> None:
    movie = load_frame(
        """
        SELECT *
        FROM movies
        WHERE movie_id = ?
        """,
        (movie_id,),
    )
    if movie.empty:
        st.error("Movie not found.")
        return

    row = movie.iloc[0]
    st.button("Back to explorer", on_click=back_to_explorer)
    st.header(row.title)

    cols = st.columns(5)
    cols[0].metric("Year", "Unknown" if pd.isna(row.year) else f"{int(row.year)}")
    cols[1].metric("Air Date", row.original_air_date or "Unknown")
    cols[2].metric("Network", row.network or "Unknown")
    cols[3].metric("TMDB Match", "Yes" if row.tmdb_match_found else "No")
    cols[4].metric("TMDB Similarity", "Unknown" if pd.isna(row.tmdb_similarity) else f"{row.tmdb_similarity:.3f}")

    credits = load_frame(
        """
        SELECT p.person_id, p.name, c.role, GROUP_CONCAT(DISTINCT c.source) AS sources
        FROM credits c
        JOIN people p ON p.person_id = c.person_id
        WHERE c.movie_id = ?
        GROUP BY p.person_id, p.name, c.role
        ORDER BY
            CASE c.role WHEN 'Director' THEN 0 WHEN 'Writer' THEN 1 WHEN 'Screenplay' THEN 2 WHEN 'Teleplay' THEN 3 WHEN 'Story' THEN 4 ELSE 5 END,
            p.name COLLATE NOCASE
        """,
        (movie_id,),
    )

    st.subheader("Credits")
    for role in ["Director", "Writer", "Screenplay", "Teleplay", "Story", "Actor"]:
        group = credits[credits["role"] == role]
        if group.empty:
            continue
        st.markdown(f"**{role}**")
        cols = st.columns(3)
        for idx, person in enumerate(group.itertuples(index=False)):
            cols[idx % 3].button(person.name, key=f"movie-{movie_id}-{role}-{person.person_id}", on_click=open_person, args=(int(person.person_id),), use_container_width=True)

    related = load_frame(
        f"""
        SELECT DISTINCT m.movie_id, m.title, m.year, m.network
        FROM movies m
        JOIN credits c ON c.movie_id = m.movie_id
        WHERE m.movie_id <> ?
            AND c.person_id IN (
                SELECT person_id FROM credits WHERE movie_id = ? AND role IN ({placeholders(CREATIVE_ROLES)})
            )
            AND c.role IN ({placeholders(CREATIVE_ROLES)})
        ORDER BY COALESCE(m.year, 0) DESC, m.title COLLATE NOCASE
        LIMIT 30
        """,
        (movie_id, movie_id, *CREATIVE_ROLES, *CREATIVE_ROLES),
    )
    st.subheader("Related Creative-Team Movies")
    movie_button_rows(related, f"related-{movie_id}")


def get_person_role_films(person_id: int, roles: tuple[str, ...]) -> pd.DataFrame:
    return load_frame(
        f"""
        SELECT
            m.movie_id,
            m.title,
            m.year,
            GROUP_CONCAT(DISTINCT c.role) AS roles,
            GROUP_CONCAT(DISTINCT c.source) AS sources,
            m.original_air_date,
            m.network,
            m.tmdb_title,
            m.tmdb_release_date
        FROM credits c
        JOIN movies m ON m.movie_id = c.movie_id
        WHERE c.person_id = ? AND c.role IN ({placeholders(roles)})
        GROUP BY m.movie_id, m.title, m.year, m.original_air_date, m.network, m.tmdb_title, m.tmdb_release_date
        ORDER BY COALESCE(m.year, 0) DESC, m.title COLLATE NOCASE
        """,
        (person_id, *roles),
    )


def get_director_writer_collaborators(director_id: int) -> pd.DataFrame:
    return load_frame(
        f"""
        SELECT
            writer.person_id AS writer_id,
            writer.name AS writer,
            COUNT(DISTINCT m.movie_id) AS movies_together,
            GROUP_CONCAT(DISTINCT wc.role) AS writing_roles,
            MAX(m.year) AS latest_year,
            GROUP_CONCAT(DISTINCT m.title) AS movies
        FROM credits dc
        JOIN movies m ON m.movie_id = dc.movie_id
        JOIN credits wc ON wc.movie_id = m.movie_id
        JOIN people writer ON writer.person_id = wc.person_id
        WHERE dc.person_id = ?
            AND dc.role = 'Director'
            AND wc.role IN ({placeholders(WRITING_ROLES)})
            AND writer.person_id <> dc.person_id
        GROUP BY writer.person_id, writer.name
        ORDER BY movies_together DESC, latest_year DESC, writer.name COLLATE NOCASE
        LIMIT 50
        """,
        (director_id, *WRITING_ROLES),
    )


def get_person_collaborators(person_id: int) -> pd.DataFrame:
    return load_frame(
        """
        SELECT
            other.person_id,
            other.name,
            oc.role,
            COUNT(DISTINCT c.movie_id) AS movies_together,
            MAX(m.year) AS latest_year
        FROM credits c
        JOIN credits oc ON oc.movie_id = c.movie_id AND oc.person_id <> c.person_id
        JOIN people other ON other.person_id = oc.person_id
        JOIN movies m ON m.movie_id = c.movie_id
        WHERE c.person_id = ?
        GROUP BY other.person_id, other.name, oc.role
        ORDER BY movies_together DESC, latest_year DESC, other.name COLLATE NOCASE
        LIMIT 75
        """,
        (person_id,),
    )


def collaborator_buttons(frame: pd.DataFrame, key_prefix: str) -> None:
    if frame.empty:
        st.caption("No collaborations found.")
        return

    for item in frame.itertuples(index=False):
        cols = st.columns([3, 1, 2, 1, 4])
        cols[0].button(item.writer, key=f"{key_prefix}-{item.writer_id}", on_click=open_person, args=(int(item.writer_id),), use_container_width=True)
        cols[1].metric("Together", f"{item.movies_together:,.0f}")
        cols[2].write(item.writing_roles or "")
        cols[3].write("Unknown" if pd.isna(item.latest_year) else f"{int(item.latest_year)}")
        cols[4].write((item.movies or "").replace(",", ", "))


def person_profile(person_id: int) -> None:
    person_name = get_person_name(person_id)
    role_summary = load_frame(
        """
        SELECT role, COUNT(DISTINCT movie_id) AS movies
        FROM credits
        WHERE person_id = ?
        GROUP BY role
        ORDER BY movies DESC, role COLLATE NOCASE
        """,
        (person_id,),
    )

    st.header(person_name)
    if role_summary.empty:
        st.caption("No credits found for this person.")
        return

    metric_cols = st.columns(min(len(role_summary), 4))
    for idx, row in enumerate(role_summary.head(4).itertuples(index=False)):
        metric_cols[idx].metric(row.role, f"{row.movies:,.0f}")

    credits = load_frame(
        """
        SELECT
            m.movie_id,
            m.title,
            m.year,
            GROUP_CONCAT(DISTINCT c.role) AS roles,
            GROUP_CONCAT(DISTINCT c.source) AS sources,
            m.original_air_date,
            m.network,
            m.tmdb_title,
            m.tmdb_release_date
        FROM credits c
        JOIN movies m ON m.movie_id = c.movie_id
        WHERE c.person_id = ?
        GROUP BY m.movie_id, m.title, m.year, m.original_air_date, m.network, m.tmdb_title, m.tmdb_release_date
        ORDER BY COALESCE(m.year, 0) DESC, m.title COLLATE NOCASE
        """,
        (person_id,),
    )
    timeline = credits.dropna(subset=["year"]).groupby(["year", "roles"]).size().reset_index(name="credits")

    tab_overview, tab_timeline, tab_collabs, tab_movies = st.tabs(["Overview", "Career Timeline", "Network", "Movies"])

    with tab_overview:
        left, right = st.columns([1, 2])
        with left:
            st.subheader("Role Mix")
            st.dataframe(role_summary, hide_index=True, use_container_width=True)
        with right:
            if "Director" in set(role_summary["role"]):
                st.subheader("Writers This Director Works With Most")
                collaborator_buttons(get_director_writer_collaborators(person_id), f"director-writers-{person_id}")
            else:
                st.subheader("Top Collaborators")
                collabs = get_person_collaborators(person_id).head(25)
                person_button_rows(collabs, f"collabs-{person_id}", "name", "person_id", "movies_together")

    with tab_timeline:
        st.subheader("Career Timeline")
        if timeline.empty:
            st.caption("No dated credits found.")
        else:
            st.bar_chart(timeline, x="year", y="credits", color="roles", use_container_width=True)
            st.dataframe(timeline, hide_index=True, use_container_width=True)

    with tab_collabs:
        st.subheader("Collaboration Network")
        collabs = get_person_collaborators(person_id)
        person_button_rows(collabs, f"network-{person_id}", "name", "person_id", "movies_together")

    with tab_movies:
        st.subheader("Movie Credits")
        movie_button_rows(credits[["movie_id", "title", "year", "network"]], f"person-movies-{person_id}")
        with st.expander("Table view"):
            st.dataframe(credits, hide_index=True, use_container_width=True)


def person_page(person_id: int) -> None:
    st.button("Back to explorer", on_click=back_to_explorer)
    person_profile(person_id)


def trends_view(where_clause: str, params: tuple) -> None:
    by_year = load_frame(
        f"""
        SELECT m.year, COUNT(*) AS movies
        FROM movies m
        WHERE {where_clause} AND m.year IS NOT NULL
        GROUP BY m.year
        ORDER BY m.year
        """,
        params,
    )
    by_network = load_frame(
        f"""
        SELECT COALESCE(NULLIF(TRIM(m.network), ''), 'Unknown') AS network, COUNT(*) AS movies
        FROM movies m
        WHERE {where_clause}
        GROUP BY COALESCE(NULLIF(TRIM(m.network), ''), 'Unknown')
        ORDER BY movies DESC, network
        LIMIT 20
        """,
        params,
    )
    top_directors = load_frame(
        f"""
        SELECT p.person_id AS director_id, p.name AS director, COUNT(DISTINCT m.movie_id) AS movies
        FROM movies m
        JOIN credits c ON c.movie_id = m.movie_id
        JOIN people p ON p.person_id = c.person_id
        WHERE {where_clause} AND c.role = 'Director'
        GROUP BY p.person_id, p.name
        ORDER BY movies DESC, p.name COLLATE NOCASE
        LIMIT 50
        """,
        params,
    )
    top_writers = load_frame(
        f"""
        SELECT p.person_id AS writer_id, p.name AS writer, COUNT(DISTINCT m.movie_id) AS movies
        FROM movies m
        JOIN credits c ON c.movie_id = m.movie_id
        JOIN people p ON p.person_id = c.person_id
        WHERE {where_clause} AND c.role IN ({placeholders(WRITING_ROLES)})
        GROUP BY p.person_id, p.name
        ORDER BY movies DESC, p.name COLLATE NOCASE
        LIMIT 50
        """,
        (*params, *WRITING_ROLES),
    )
    director_writer_pairs = load_frame(
        f"""
        SELECT
            director.person_id AS director_id,
            director.name AS director,
            writer.person_id AS writer_id,
            writer.name AS writer,
            COUNT(DISTINCT m.movie_id) AS movies_together,
            MAX(m.year) AS latest_year
        FROM movies m
        JOIN credits dc ON dc.movie_id = m.movie_id AND dc.role = 'Director'
        JOIN people director ON director.person_id = dc.person_id
        JOIN credits wc ON wc.movie_id = m.movie_id AND wc.role IN ({placeholders(WRITING_ROLES)})
        JOIN people writer ON writer.person_id = wc.person_id
        WHERE {where_clause} AND writer.person_id <> director.person_id
        GROUP BY director.person_id, director.name, writer.person_id, writer.name
        ORDER BY movies_together DESC, latest_year DESC, director.name COLLATE NOCASE, writer.name COLLATE NOCASE
        LIMIT 75
        """,
        (*WRITING_ROLES, *params),
    )

    overview_tab, directors_tab, writers_tab, teams_tab = st.tabs(["Overview", "Directors", "Writers", "Frequent Teams"])

    with overview_tab:
        left, right = st.columns([2, 1])
        with left:
            st.subheader("Movies by Year")
            st.bar_chart(by_year, x="year", y="movies", use_container_width=True)
        with right:
            st.subheader("Top Networks")
            st.dataframe(by_network, hide_index=True, use_container_width=True)

    with directors_tab:
        st.subheader("Movies by Director")
        st.bar_chart(top_directors, x="director", y="movies", use_container_width=True)
        person_button_rows(top_directors, "trend-director", "director", "director_id", "movies")

    with writers_tab:
        st.subheader("Movies by Writer")
        st.bar_chart(top_writers, x="writer", y="movies", use_container_width=True)
        person_button_rows(top_writers, "trend-writer", "writer", "writer_id", "movies")

    with teams_tab:
        st.subheader("Director/Writer Teams")
        for row in director_writer_pairs.itertuples(index=False):
            cols = st.columns([3, 3, 1, 1])
            cols[0].button(row.director, key=f"team-d-{row.director_id}-{row.writer_id}", on_click=open_person, args=(int(row.director_id),), use_container_width=True)
            cols[1].button(row.writer, key=f"team-w-{row.director_id}-{row.writer_id}", on_click=open_person, args=(int(row.writer_id),), use_container_width=True)
            cols[2].metric("Together", f"{row.movies_together:,.0f}")
            cols[3].metric("Latest", "Unknown" if pd.isna(row.latest_year) else f"{int(row.latest_year)}")


def teams_dashboard() -> None:
    st.subheader("Frequent Creative Teams")
    team_type = st.selectbox(
        "Team type",
        ["Director + Writer", "Director + Actor", "Actor Pairs", "Writer + Actor"],
    )

    if team_type == "Director + Writer":
        query = f"""
            SELECT d.person_id AS first_id, d.name AS first_name, w.person_id AS second_id, w.name AS second_name,
                   COUNT(DISTINCT m.movie_id) AS movies_together, MAX(m.year) AS latest_year
            FROM movies m
            JOIN credits dc ON dc.movie_id = m.movie_id AND dc.role = 'Director'
            JOIN people d ON d.person_id = dc.person_id
            JOIN credits wc ON wc.movie_id = m.movie_id AND wc.role IN ({placeholders(WRITING_ROLES)})
            JOIN people w ON w.person_id = wc.person_id
            WHERE d.person_id <> w.person_id
            GROUP BY d.person_id, d.name, w.person_id, w.name
            ORDER BY movies_together DESC, latest_year DESC
            LIMIT 100
        """
        params = WRITING_ROLES
    elif team_type == "Director + Actor":
        query = """
            SELECT d.person_id AS first_id, d.name AS first_name, a.person_id AS second_id, a.name AS second_name,
                   COUNT(DISTINCT m.movie_id) AS movies_together, MAX(m.year) AS latest_year
            FROM movies m
            JOIN credits dc ON dc.movie_id = m.movie_id AND dc.role = 'Director'
            JOIN people d ON d.person_id = dc.person_id
            JOIN credits ac ON ac.movie_id = m.movie_id AND ac.role = 'Actor'
            JOIN people a ON a.person_id = ac.person_id
            GROUP BY d.person_id, d.name, a.person_id, a.name
            ORDER BY movies_together DESC, latest_year DESC
            LIMIT 100
        """
        params = ()
    elif team_type == "Actor Pairs":
        query = """
            SELECT a.person_id AS first_id, a.name AS first_name, b.person_id AS second_id, b.name AS second_name,
                   COUNT(DISTINCT m.movie_id) AS movies_together, MAX(m.year) AS latest_year
            FROM movies m
            JOIN credits ac ON ac.movie_id = m.movie_id AND ac.role = 'Actor'
            JOIN people a ON a.person_id = ac.person_id
            JOIN credits bc ON bc.movie_id = m.movie_id AND bc.role = 'Actor' AND bc.person_id > ac.person_id
            JOIN people b ON b.person_id = bc.person_id
            GROUP BY a.person_id, a.name, b.person_id, b.name
            ORDER BY movies_together DESC, latest_year DESC
            LIMIT 100
        """
        params = ()
    else:
        query = f"""
            SELECT w.person_id AS first_id, w.name AS first_name, a.person_id AS second_id, a.name AS second_name,
                   COUNT(DISTINCT m.movie_id) AS movies_together, MAX(m.year) AS latest_year
            FROM movies m
            JOIN credits wc ON wc.movie_id = m.movie_id AND wc.role IN ({placeholders(WRITING_ROLES)})
            JOIN people w ON w.person_id = wc.person_id
            JOIN credits ac ON ac.movie_id = m.movie_id AND ac.role = 'Actor'
            JOIN people a ON a.person_id = ac.person_id
            WHERE w.person_id <> a.person_id
            GROUP BY w.person_id, w.name, a.person_id, a.name
            ORDER BY movies_together DESC, latest_year DESC
            LIMIT 100
        """
        params = WRITING_ROLES

    teams = load_frame(query, tuple(params))
    for row in teams.itertuples(index=False):
        cols = st.columns([3, 3, 1, 1])
        cols[0].button(row.first_name, key=f"team-first-{team_type}-{row.first_id}-{row.second_id}", on_click=open_person, args=(int(row.first_id),), use_container_width=True)
        cols[1].button(row.second_name, key=f"team-second-{team_type}-{row.first_id}-{row.second_id}", on_click=open_person, args=(int(row.second_id),), use_container_width=True)
        cols[2].metric("Together", f"{row.movies_together:,.0f}")
        cols[3].metric("Latest", "Unknown" if pd.isna(row.latest_year) else f"{int(row.latest_year)}")


def data_quality_view() -> None:
    st.subheader("Data Quality")
    summary = load_frame(
        """
        SELECT
            COUNT(*) AS movies,
            SUM(CASE WHEN year IS NULL THEN 1 ELSE 0 END) AS missing_year,
            SUM(CASE WHEN original_air_date IS NULL THEN 1 ELSE 0 END) AS missing_air_date,
            SUM(CASE WHEN COALESCE(tmdb_match_found, 0) = 0 THEN 1 ELSE 0 END) AS unmatched_tmdb,
            SUM(CASE WHEN tmdb_match_found = 1 AND tmdb_similarity < 0.9 THEN 1 ELSE 0 END) AS weak_tmdb_matches
        FROM movies
        """
    ).iloc[0]
    cols = st.columns(5)
    for idx, key in enumerate(summary.index):
        cols[idx].metric(key.replace("_", " ").title(), f"{summary[key]:,.0f}")

    tab_missing, tab_duplicates, tab_conflicts = st.tabs(["Missing / Weak", "Possible Duplicates", "Source Conflicts"])

    with tab_missing:
        missing = load_frame(
            """
            SELECT movie_id, title, year, original_air_date, tmdb_title, tmdb_release_date, tmdb_similarity, tmdb_match_found
            FROM movies
            WHERE year IS NULL OR original_air_date IS NULL OR COALESCE(tmdb_match_found, 0) = 0 OR (tmdb_match_found = 1 AND tmdb_similarity < 0.9)
            ORDER BY COALESCE(year, 0) DESC, title COLLATE NOCASE
            LIMIT 300
            """
        )
        movie_button_rows(missing[["movie_id", "title", "year"]].assign(network=""), "quality-missing")
        with st.expander("Table view"):
            st.dataframe(missing, hide_index=True, use_container_width=True)

    with tab_duplicates:
        dupes = load_frame(
            """
            SELECT LOWER(TRIM(title)) AS normalized_title, COUNT(*) AS rows, GROUP_CONCAT(movie_id) AS movie_ids, GROUP_CONCAT(DISTINCT year) AS years
            FROM movies
            GROUP BY LOWER(TRIM(title))
            HAVING COUNT(*) > 1
            ORDER BY rows DESC, normalized_title
            """
        )
        st.dataframe(dupes, hide_index=True, use_container_width=True)

    with tab_conflicts:
        conflicts = load_frame(
            """
            SELECT m.title, m.year, c.role, p.name, COUNT(DISTINCT c.source) AS sources, GROUP_CONCAT(DISTINCT c.source) AS source_names
            FROM credits c
            JOIN movies m ON m.movie_id = c.movie_id
            JOIN people p ON p.person_id = c.person_id
            GROUP BY m.movie_id, c.role, p.person_id
            HAVING COUNT(DISTINCT c.source) > 1
            ORDER BY m.year DESC, m.title COLLATE NOCASE, c.role
            LIMIT 300
            """
        )
        st.dataframe(conflicts, hide_index=True, use_container_width=True)


def raw_sql_view() -> None:
    st.subheader("Read-only SQL")
    st.caption("Use SELECT queries only. The app blocks writes before running anything.")
    query = st.text_area(
        "Query",
        value=(
            "SELECT title, year, wikipedia_cast, wikipedia_director\n"
            "FROM movies\n"
            "ORDER BY year DESC, title\n"
            "LIMIT 25"
        ),
        height=160,
    )

    if st.button("Run query", type="primary"):
        normalized = query.strip().lower()
        blocked = ["insert", "update", "delete", "drop", "alter", "create", "replace", "pragma", "attach"]
        if not normalized.startswith("select") or any(f" {word} " in f" {normalized} " for word in blocked):
            st.error("Only read-only SELECT queries are allowed.")
            return

        try:
            st.dataframe(load_frame(query), hide_index=True, use_container_width=True)
        except Exception as exc:
            st.error(f"Query failed: {exc}")


def about_view() -> None:
    about_path = APP_DIR / "ABOUT.md"
    if not about_path.exists():
        st.info("ABOUT.md was not found.")
        return

    st.markdown(about_path.read_text(encoding="utf-8"))


def main() -> None:
    st.title("The Hallmark Project")
    st.caption("Explore Hallmark movies, people, credits, and creative collaborations.")

    view = st.session_state.get("view", "explorer")
    if view == "person" and st.session_state.get("selected_person_id"):
        person_page(int(st.session_state.selected_person_id))
        return
    if view == "movie" and st.session_state.get("selected_movie_id"):
        movie_detail_page(int(st.session_state.selected_movie_id))
        return

    metric_row()
    where_clause, params = sidebar_filters("m")

    tabs = st.tabs([
        "Movie Search",
        "Person Search",
        "Movies",
        "Trends",
        "Teams",
        "Data Quality",
        "About",
        "SQL",
    ])

    with tabs[0]:
        movie_search_view()
    with tabs[1]:
        person_search_view()
    with tabs[2]:
        movies_view(where_clause, params)
    with tabs[3]:
        trends_view(where_clause, params)
    with tabs[4]:
        teams_dashboard()
    with tabs[5]:
        data_quality_view()
    with tabs[6]:
        about_view()
    with tabs[7]:
        raw_sql_view()


if __name__ == "__main__":
    main()
