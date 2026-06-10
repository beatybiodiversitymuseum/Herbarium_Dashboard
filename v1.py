import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import time

# ─── Page Config ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="UBC Herbarium Explorer",
    page_icon="🌿",
    layout="wide"
)

# ─── Styling ──────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;600&family=Source+Sans+3:wght@300;400;600&display=swap');

    html, body, [class*="css"] {
        font-family: 'Source Sans 3', sans-serif;
    }
    h1, h2, h3 {
        font-family: 'Playfair Display', serif !important;
    }
    .main { background-color: #f8f6f1; }
    .block-container { padding-top: 2rem; }

    [data-testid="metric-container"] {
        background: white;
        border: 1px solid #e0ddd5;
        border-radius: 8px;
        padding: 1rem 1.5rem;
        box-shadow: 0 1px 4px rgba(0,0,0,0.04);
    }
    [data-testid="stSidebar"] {
        background-color: #1f2e1f;
    }
    [data-testid="stSidebar"] * {
        color: #d4e8d4 !important;
    }
    [data-testid="stSidebar"] .stRadio label {
        color: #d4e8d4 !important;
    }
    .data-note {
        background: #fdf8ee;
        border-left: 3px solid #c8a951;
        padding: 0.6rem 1rem;
        border-radius: 0 6px 6px 0;
        font-size: 0.875rem;
        color: #7a6030;
        margin-bottom: 1rem;
    }
</style>
""", unsafe_allow_html=True)


# ─── Data Loading ─────────────────────────────────────────────────────────────
USE_API = False  # Set to True to pull live data from Specify
#
# NOTE: Authentication currently uses browser cookies via specify_api.auth.
# This works locally if you are logged in to Specify in your browser.
# For hosted/shared deployment, replace make_session() in load_from_api()
# with direct username/password login and store credentials securely
# (e.g. Streamlit secrets manager). Contact the database administrator
# for a read-only service account.

@st.cache_data(ttl=604800, show_spinner="Refreshing collection data from Specify...")
def load_from_api():
    from specify_api.auth import make_session
    s = make_session()

    filter_str = (
        "&collectionmemberid=32768"
        "&collectingevent__isnull=False"
        "&determinations__isnull=False"
    )

    def extract_id(uri):
        if not uri or not isinstance(uri, str):
            return None
        try:
            return int(uri.rstrip("/").split("/")[-1])
        except:
            return None

    def extract_specimen_row(obj):
        row = {}
        row["id"]            = obj.get("id")
        row["catalognumber"] = obj.get("catalognumber")
        ce = obj.get("collectingevent") or {}
        if isinstance(ce, str):
            ce = {}
        row["collection_date"] = ce.get("enddate")
        row["verbatim_date"]   = ce.get("enddateverbatim")
        loc = ce.get("locality")
        if isinstance(loc, str):
            row["locality_id"] = extract_id(loc)
        elif isinstance(loc, dict):
            row["locality_id"] = loc.get("id")
        else:
            row["locality_id"] = None
        collectors       = ce.get("collectors") or []
        primary_agent_id = None
        agent_ids        = []
        for c in collectors:
            agent_uri = c.get("agent", "")
            agent_id  = extract_id(agent_uri) if isinstance(agent_uri, str) else None
            if agent_id:
                agent_ids.append(agent_id)
            if c.get("isprimary") and agent_id:
                primary_agent_id = agent_id
        if not primary_agent_id and collectors:
            first            = min(collectors, key=lambda c: c.get("ordernumber", 999))
            agent_uri        = first.get("agent", "")
            primary_agent_id = extract_id(agent_uri) if isinstance(agent_uri, str) else None
        row["all_agent_ids"]    = agent_ids
        row["primary_agent_id"] = primary_agent_id
        return row

    total    = s.get(f"/api/specify/collectionobject/?limit=1&offset=0{filter_str}").json()["meta"]["total_count"]
    raw_rows = []
    limit    = 500
    for offset in range(0, total, limit):
        url     = f"/api/specify/collectionobject/?limit={limit}&offset={offset}{filter_str}"
        objects = s.get(url).json()["objects"]
        if not objects:
            break
        for obj in objects:
            raw_rows.append(extract_specimen_row(obj))
        time.sleep(0.05)
    specimen_df = pd.DataFrame(raw_rows)

    locality_ids = specimen_df["locality_id"].dropna().unique().tolist()
    all_locs     = []
    for loc_id in locality_ids:
        try:
            r = s.get(f"/api/specify/locality/{loc_id}/")
            if r.status_code == 200:
                loc = r.json()
                all_locs.append({
                    "locality_id":  loc.get("id"),
                    "localityname": loc.get("localityname"),
                    "latitude":     loc.get("latitude1"),
                    "longitude":    loc.get("longitude1")
                })
        except:
            pass
        time.sleep(0.02)
    loc_df = pd.DataFrame(all_locs)

    total_agents = s.get("/api/specify/agent/?limit=1&offset=0&agenttype=1").json()["meta"]["total_count"]
    raw_agents   = []
    for offset in range(0, total_agents, limit):
        objects = s.get(f"/api/specify/agent/?limit={limit}&offset={offset}&agenttype=1").json()["objects"]
        for obj in objects:
            raw_agents.append({
                "agent_id":      obj.get("id"),
                "firstname":     obj.get("firstname"),
                "lastname":      obj.get("lastname"),
                "middleinitial": obj.get("middleinitial")
            })
        time.sleep(0.05)
    agent_df              = pd.DataFrame(raw_agents)
    agent_df["full_name"] = (
        agent_df["firstname"].fillna("") + " " + agent_df["lastname"].fillna("")
    ).str.strip()

    df = specimen_df.merge(loc_df, on="locality_id", how="left")
    df = df.merge(agent_df[["agent_id", "full_name", "lastname", "firstname"]],
                  left_on="primary_agent_id", right_on="agent_id", how="left")
    return _clean_df(df)


@st.cache_data(show_spinner="Loading collection data...")
def load_from_csv():
    return _clean_df(pd.read_csv("algae.csv"))


def _clean_df(df):
    df["collection_date"] = pd.to_datetime(df["collection_date"], errors="coerce")
    df["year"]            = df["collection_date"].dt.year
    df["decade"]          = (df["year"] // 10) * 10
    df["full_name"]       = df["full_name"].fillna("Unknown Collector")
    df["lastname"]        = df["lastname"].fillna("")
    df["localityname"]    = df["localityname"].fillna("Unknown Locality")
    df["latitude"]        = pd.to_numeric(df["latitude"],  errors="coerce")
    df["longitude"]       = pd.to_numeric(df["longitude"], errors="coerce")
    return df


df             = load_from_api() if USE_API else load_from_csv()
all_collectors = sorted(df["full_name"].unique())


# ─── Session State ────────────────────────────────────────────────────────────
if "selected_collectors" not in st.session_state:
    st.session_state.selected_collectors = []  # empty = all collectors


# ─── Sidebar ──────────────────────────────────────────────────────────────────
st.sidebar.title("🌿 Herbarium Explorer")
st.sidebar.markdown("---")

page = st.sidebar.radio(
    "Navigate",
    ["Overview", "Collector Timeline", "Geographic Map"]
)

st.sidebar.markdown("---")
st.sidebar.markdown("### Collector Filter")
st.sidebar.caption(
    "Search for a collector to add them to your selection. "
    "Leave selection empty to include all collectors."
)

# ── Search box ────────────────────────────────────────────────────────────────
search_query = st.sidebar.text_input("🔍 Search collectors", placeholder="e.g. Markham")

if search_query:
    matches = [c for c in all_collectors if search_query.lower() in c.lower()]
    if matches:
        to_add = st.sidebar.multiselect(
            f"Results ({len(matches)} found)",
            options=matches,
            default=[],
            key="search_results"
        )
        col_a, col_b = st.sidebar.columns(2)
        if col_a.button("➕ Add Selected", use_container_width=True):
            current = st.session_state.selected_collectors
            st.session_state.selected_collectors = sorted(
                list(set(current + to_add))
            )
            st.rerun()
        if col_b.button("➕ Add All Results", use_container_width=True):
            current = st.session_state.selected_collectors
            st.session_state.selected_collectors = sorted(
                list(set(current + matches))
            )
            st.rerun()
    else:
        st.sidebar.caption("No collectors match that search.")

st.sidebar.markdown("---")

# ── Active selection display ──────────────────────────────────────────────────
if st.session_state.selected_collectors:
    st.sidebar.markdown(
        f"**Selected:** {len(st.session_state.selected_collectors)} collector(s)"
    )
    st.sidebar.caption("\n".join(st.session_state.selected_collectors))
    col_c, col_d = st.sidebar.columns(2)
    if col_c.button("✅ Add All", use_container_width=True):
        st.session_state.selected_collectors = all_collectors
        st.rerun()
    if col_d.button("❌ Clear", use_container_width=True):
        st.session_state.selected_collectors = []
        st.rerun()
else:
    st.sidebar.markdown("**Showing all collectors**")
    if st.sidebar.button("➕ Add All to Selection", use_container_width=True):
        st.session_state.selected_collectors = all_collectors
        st.rerun()

# ── Year range ────────────────────────────────────────────────────────────────
st.sidebar.markdown("---")
years_available = df["year"].dropna()
year_min   = int(years_available.min())
year_max   = int(years_available.max())
year_range = st.sidebar.slider(
    "Collection Year Range",
    min_value=year_min,
    max_value=year_max,
    value=(year_min, year_max)
)

st.sidebar.markdown("---")

# ── Apply filters ─────────────────────────────────────────────────────────────
if st.session_state.selected_collectors:
    filtered_df = df[df["full_name"].isin(st.session_state.selected_collectors)].copy()
else:
    filtered_df = df.copy()

filtered_df = filtered_df[
    filtered_df["year"].isna() |
    ((filtered_df["year"] >= year_range[0]) & (filtered_df["year"] <= year_range[1]))
]

with_date   = filtered_df["collection_date"].notna().sum()
with_coords = filtered_df["latitude"].notna().sum()

st.sidebar.caption(f"**{len(filtered_df):,}** specimens match filters")
st.sidebar.caption(f"📅 {with_date:,} have collection dates")
st.sidebar.caption(f"📍 {with_coords:,} have coordinates")

if not USE_API:
    st.sidebar.markdown("---")
    st.sidebar.caption("⚠️ Running on CSV data. Set `USE_API = True` to connect live.")


# ─── Page: Overview ───────────────────────────────────────────────────────────
if page == "Overview":
    st.title("Herbarium Collection Overview")

    missing_dates_pct  = filtered_df["collection_date"].isna().sum() / len(filtered_df) * 100
    missing_coords_pct = filtered_df["latitude"].isna().sum() / len(filtered_df) * 100
    if missing_dates_pct > 10 or missing_coords_pct > 10:
        st.markdown(
            f'<div class="data-note">⚠️ This is real herbarium data — '
            f'{missing_dates_pct:.0f}% of specimens are missing collection dates and '
            f'{missing_coords_pct:.0f}% are missing coordinates. '
            f'This is normal for older collections that predate standardized digitization.</div>',
            unsafe_allow_html=True
        )

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Specimens", f"{len(filtered_df):,}")
    col2.metric("Collectors",      f"{filtered_df['full_name'].nunique():,}")
    col3.metric("With Dates",      f"{with_date:,}")
    col4.metric("Georeferenced",   f"{with_coords:,}")

    st.markdown("---")

    # ── Specimens per collector ───────────────────────────────────────────────
    st.subheader("Specimens per Collector")

    collector_counts = (
        filtered_df.groupby("full_name")
        .size()
        .reset_index(name="specimen_count")
        .sort_values("specimen_count", ascending=False)
    )

    n_display = st.slider(
        "Number of collectors to display",
        min_value=5,
        max_value=min(200, len(collector_counts)),
        value=min(50, len(collector_counts)),
        step=5
    )

    chart_df = collector_counts.head(n_display).sort_values("specimen_count", ascending=True)
    st.caption(
        f"Showing top {n_display} of {len(collector_counts):,} collectors by specimen count."
    )

    fig = px.bar(
        chart_df,
        x="specimen_count",
        y="full_name",
        orientation="h",
        labels={"specimen_count": "Specimens", "full_name": "Collector"},
        color="specimen_count",
        color_continuous_scale="Greens",
    )
    fig.update_layout(
        coloraxis_showscale=False,
        height=max(400, n_display * 22),
        plot_bgcolor="white",
        paper_bgcolor="white",
        yaxis=dict(tickfont=dict(size=11))
    )
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    # ── Collection activity by decade ─────────────────────────────────────────
    st.subheader("Collection Activity by Decade")
    dated = filtered_df[filtered_df["decade"].notna()].copy()

    if len(dated) > 0:
        decade_counts = dated.groupby("decade").size().reset_index(name="count")
        fig2 = px.bar(
            decade_counts, x="decade", y="count",
            labels={"decade": "Decade", "count": "Specimens"},
            color="count", color_continuous_scale="Greens"
        )
        fig2.update_layout(
            coloraxis_showscale=False,
            plot_bgcolor="white",
            paper_bgcolor="white"
        )
        st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("No dated specimens in current filter selection.")

    st.markdown("---")

    # ── Raw data table ────────────────────────────────────────────────────────
    st.subheader("Specimen Records")
    st.caption(
        "Showing up to 2,000 records. Use the collector filter or year "
        "range to narrow results."
    )
    display_cols = {
        "catalognumber":   "Catalog #",
        "full_name":       "Collector",
        "collection_date": "Date",
        "localityname":    "Locality",
        "latitude":        "Lat",
        "longitude":       "Lon"
    }
    display_df = (
        filtered_df[[c for c in display_cols if c in filtered_df.columns]]
        .sort_values("collection_date", na_position="last")
        .head(2000)
    )
    display_df.columns = [display_cols[c] for c in display_df.columns]
    st.dataframe(display_df, use_container_width=True, hide_index=True)


# ─── Page: Collector Timeline ─────────────────────────────────────────────────
elif page == "Collector Timeline":
    st.title("Collector Timeline")
    st.markdown(
        "Each bar spans a collector's active period based on their earliest and "
        "latest recorded collection. Collectors sharing a last name are highlighted — "
        "non-overlapping timelines suggest they are different individuals. "
        "Spans over 100 years are flagged as possible data attribution errors."
    )

    # Threshold above which a span is considered suspiciously long
    UNUSUAL_SPAN_YEARS = 100

    dated = filtered_df[filtered_df["collection_date"].notna()].copy()

    if len(dated) == 0:
        st.warning("No dated specimens in current filter selection.")
    else:
        # Build timeline using integer years to avoid datetime overflow
        timeline = (
            dated.groupby("full_name")
            .agg(
                first_year=("year", "min"),
                last_year=("year", "max"),
                specimen_count=("catalognumber", "count"),
                lastname=("lastname", "first")
            )
            .reset_index()
        )

        timeline["first_year"] = timeline["first_year"].fillna(0)
        timeline["last_year"]  = timeline["last_year"].fillna(0)
        timeline["span_years"] = (
            timeline["last_year"] - timeline["first_year"]
        ).clip(lower=1)

        # Assign name status — unusual span takes priority over shared last name
        lastname_counts = timeline["lastname"].value_counts()

        def assign_status(row):
            if row["span_years"] >= UNUSUAL_SPAN_YEARS:
                return "Unusual span (possible attribution error)"
            elif lastname_counts.get(row["lastname"], 0) > 1:
                return "Shared last name"
            else:
                return "Unique"

        timeline["name_status"] = timeline.apply(assign_status, axis=1)

        # ── Display controls ──────────────────────────────────────────────────
        st.markdown("### Display Controls")
        ctrl1, ctrl2 = st.columns(2)

        max_specimens = int(timeline["specimen_count"].max())
        min_specimens = ctrl1.slider(
            "Minimum specimens",
            min_value=1,
            max_value=max(100, max_specimens // 10),
            value=5,
            step=1,
            help="Only show collectors with at least this many specimens"
        )

        # Guard: ensure max_value > min_value for the top_n slider
        n_eligible = len(timeline[timeline["specimen_count"] >= min_specimens])
        top_n_max  = max(11, n_eligible)  # always at least 11 so max > min
        top_n = ctrl2.slider(
            "Max collectors to display",
            min_value=10,
            max_value=top_n_max,
            value=min(50, top_n_max),
            step=10,
            help="Show the top N collectors by specimen count"
        )

        timeline_filtered = (
            timeline[timeline["specimen_count"] >= min_specimens]
            .sort_values("specimen_count", ascending=False)
            .head(top_n)
            .sort_values("first_year")
            .reset_index(drop=True)
        )

        st.caption(
            f"Showing {len(timeline_filtered):,} of {len(timeline):,} collectors "
            f"({min_specimens}+ specimens, top {top_n} by count)."
        )

        if len(timeline_filtered) == 0:
            st.warning(
                "No collectors match the current display controls. "
                "Try lowering the minimum specimens threshold."
            )
        else:
            # Count how many unusual spans are showing
            n_unusual = (timeline_filtered["name_status"] == "Unusual span (possible attribution error)").sum()
            if n_unusual > 0:
                st.markdown(
                    f'<div class="data-note">⚠️ {n_unusual} collector(s) have an active span '
                    f'exceeding {UNUSUAL_SPAN_YEARS} years, which is biologically impossible for '
                    f'a single person. These are shown in red and likely indicate specimens '
                    f'incorrectly attributed to a modern collector in the database. '
                    f'Consider flagging these to the database manager.</div>',
                    unsafe_allow_html=True
                )

            # ── Build chart using go.Bar with integer years ───────────────────
            color_map = {
                "Unique":                                    "#3a7c4a",
                "Shared last name":                          "#c8793a",
                "Unusual span (possible attribution error)": "#b03030"
            }

            fig = go.Figure()

            for status, color in color_map.items():
                subset = timeline_filtered[timeline_filtered["name_status"] == status]
                if len(subset) == 0:
                    continue
                fig.add_trace(go.Bar(
                    name=status,
                    orientation="h",
                    y=subset["full_name"],
                    x=subset["span_years"],
                    base=subset["first_year"],
                    marker_color=color,
                    customdata=subset[[
                        "first_year", "last_year", "specimen_count"
                    ]].values,
                    hovertemplate=(
                        "<b>%{y}</b><br>"
                        "First collection: %{customdata[0]:.0f}<br>"
                        "Last collection: %{customdata[1]:.0f}<br>"
                        "Specimens: %{customdata[2]}<br>"
                        "<extra></extra>"
                    ),
                    text=subset["first_year"].astype(int).astype(str),
                    textposition="inside",
                    insidetextanchor="start",
                    textfont=dict(size=9, color="white")
                ))

            x_min = int(timeline_filtered["first_year"].min()) - 5
            x_max = int(timeline_filtered["last_year"].max()) + 5

            fig.update_layout(
                barmode="overlay",
                height=max(500, len(timeline_filtered) * 26),
                plot_bgcolor="white",
                paper_bgcolor="white",
                legend_title="Name Status",
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.01,
                    xanchor="left",
                    x=0
                ),
                yaxis=dict(tickfont=dict(size=10), title=""),
                xaxis=dict(
                    title="Year",
                    range=[x_min, x_max],
                    showgrid=True,
                    gridcolor="#e8e4dc",
                    tickformat="d",
                    side="bottom"
                ),
                xaxis2=dict(
                    overlaying="x",
                    side="top",
                    range=[x_min, x_max],
                    showgrid=False,
                    matches="x",
                    tickformat="d",
                    showticklabels=True
                ),
                margin=dict(t=80, b=40)
            )

            st.plotly_chart(fig, use_container_width=True)

            undated_count = len(filtered_df[filtered_df["collection_date"].isna()])
            if undated_count > 0:
                st.markdown(
                    f'<div class="data-note">📅 {undated_count:,} specimens are excluded '
                    f'from this view because they have no recorded collection date.</div>',
                    unsafe_allow_html=True
                )

            st.markdown("---")
            st.subheader("Collector Activity Details")

            table = timeline_filtered[[
                "full_name", "first_year", "last_year",
                "specimen_count", "name_status", "span_years"
            ]].copy()
            table["first_year"]  = table["first_year"].astype(int)
            table["last_year"]   = table["last_year"].astype(int)
            table["active_span"] = table["span_years"].astype(int).astype(str) + " yrs"
            table = table.drop(columns=["span_years"])
            table.columns = [
                "Collector", "First Collection", "Last Collection",
                "Specimens", "Name Status", "Active Span"
            ]
            st.dataframe(
                table.sort_values("First Collection"),
                use_container_width=True,
                hide_index=True
            )


# ─── Page: Geographic Map ─────────────────────────────────────────────────────
elif page == "Geographic Map":
    st.title("Geographic Distribution")
    st.markdown("Collection localities for filtered specimens with known coordinates.")

    map_df    = filtered_df.dropna(subset=["latitude", "longitude"]).copy()
    no_coords = len(filtered_df) - len(map_df)

    if no_coords > 0:
        st.markdown(
            f'<div class="data-note">📍 {no_coords:,} specimens '
            f'({no_coords/len(filtered_df)*100:.0f}%) are missing coordinates and are not shown. '
            f'This is common for older herbarium records collected before georeferencing '
            f'was standard practice.</div>',
            unsafe_allow_html=True
        )

    if len(map_df) == 0:
        st.error("No georeferenced specimens match the current filters.")
    else:
        MAX_MAP_POINTS = 5000
        if len(map_df) > MAX_MAP_POINTS:
            st.markdown(
                f'<div class="data-note">🗺 {len(map_df):,} georeferenced specimens match '
                f'your filters. Displaying a random sample of {MAX_MAP_POINTS:,} for '
                f'performance. Use the collector filter or year range to narrow results '
                f'and see all points.</div>',
                unsafe_allow_html=True
            )
            map_df = map_df.sample(MAX_MAP_POINTS, random_state=42)

        fig = px.scatter_map(
            map_df,
            lat="latitude",
            lon="longitude",
            color="full_name",
            hover_name="full_name",
            hover_data={
                "catalognumber":   True,
                "collection_date": True,
                "localityname":    True,
                "latitude":        False,
                "longitude":       False,
                "full_name":       False
            },
            labels={
                "full_name":       "Collector",
                "catalognumber":   "Catalog #",
                "collection_date": "Date",
                "localityname":    "Locality"
            },
            zoom=2,
            height=600,
            map_style="open-street-map"
        )
        fig.update_layout(legend_title="Collector")
        st.plotly_chart(fig, use_container_width=True)

        st.markdown("---")
        st.subheader("Georeferenced Specimens")
        st.caption(
            "Showing up to 2,000 records. Use the collector filter or year "
            "range to narrow results."
        )
        st.dataframe(
            map_df[[
                "catalognumber", "full_name", "collection_date",
                "localityname", "latitude", "longitude"
            ]]
            .sort_values("collection_date", na_position="last")
            .head(2000),
            use_container_width=True,
            hide_index=True
        )
