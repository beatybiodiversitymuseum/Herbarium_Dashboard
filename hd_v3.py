import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

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
    [data-testid="stSidebar"] .stButton > button {
        background-color: #2d4a2d;
        color: #ffffff !important;
        border: 1px solid #4a7a4a;
        border-radius: 6px;
        font-size: 0.85rem;
    }
    [data-testid="stSidebar"] .stButton > button:hover {
        background-color: #3a5c3a;
        border-color: #6aaa6a;
    }
    [data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {
        color: #b0c8b0 !important;
        font-size: 0.82rem;
    }
    [data-testid="stSidebar"] .stTextInput input {
        color: #2d2d2d !important;
    }
    [data-testid="stSidebar"] .stMarkdown p,
    [data-testid="stSidebar"] h1,
    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3 {
        color: #e8f5e8 !important;
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

@st.cache_data(show_spinner="Loading collection data...")
def load_from_csv():
    return _clean_df(pd.read_csv("herbarium_algae_test.csv"))


SPECIFY_BASE_URL = "https://database.beatymuseum.ubc.ca/specify/view/collectionobject/"

def _clean_df(df):
    parsed_dates          = pd.to_datetime(df["collection_date"], errors="coerce")
    df["year"]            = parsed_dates.dt.year
    df["decade"]          = (df["year"] // 10) * 10
    df["collection_date"] = parsed_dates.dt.date
    df["full_name"]       = df["full_name"].fillna("Unknown Collector")
    df["lastname"]        = df["lastname"].fillna("")
    df["localityname"]    = df["localityname"].fillna("Unknown Locality")
    df["latitude"]        = pd.to_numeric(df["latitude"],  errors="coerce")
    df["longitude"]       = pd.to_numeric(df["longitude"], errors="coerce")
    # Geography columns — present after new data pull; gracefully absent for old CSVs
    if "country" not in df.columns:
        df["country"]  = None
    if "province" not in df.columns:
        df["province"] = None
    df["country"]  = df["country"].fillna("Unknown")
    df["province"] = df["province"].fillna("Unknown")
    # Specify record link — requires id column from the pull
    if "id" in df.columns:
        df["specify_url"] = SPECIFY_BASE_URL + df["id"].astype(str) + "/"
    else:
        df["specify_url"] = None
    return df


df             = load_from_csv()
all_collectors = sorted(df["full_name"].unique())
all_countries  = sorted([c for c in df["country"].unique()  if c != "Unknown"])
all_provinces  = sorted([p for p in df["province"].unique() if p != "Unknown"])


# ─── Session State ────────────────────────────────────────────────────────────
if "selected_collectors" not in st.session_state:
    st.session_state.selected_collectors = []  # empty = all collectors
if "map_selected_catalognumbers" not in st.session_state:
    st.session_state.map_selected_catalognumbers = set()
if "map_clear_counter" not in st.session_state:
    st.session_state.map_clear_counter = 0
if "selected_countries" not in st.session_state:
    st.session_state.selected_countries = []   # empty = all countries
if "selected_provinces" not in st.session_state:
    st.session_state.selected_provinces = []   # empty = all provinces


# ─── Sidebar ──────────────────────────────────────────────────────────────────
st.sidebar.title("🌿 Herbarium Explorer")
st.sidebar.markdown("---")
st.sidebar.markdown("### Filters")
st.sidebar.caption("Type to search, click a suggestion to add it as a filter tag. Click a tag to remove it.")

# ── Helper: render a tag-based filter in the sidebar ─────────────────────────
def tag_filter(label, search_key, options, state_key, max_suggestions=8):
    """
    Single-input tag filter. Type to search, matching options appear as
    clickable suggestion buttons. Selected items show as ✕ tag buttons.
    Returns the current list of selected items.
    """
    selected = st.session_state[state_key]

    st.sidebar.markdown(f"**{label}**")

    # Show selected tags as removable buttons
    if selected:
        tag_cols = st.sidebar.columns(min(len(selected), 2))
        to_remove = None
        for i, item in enumerate(selected):
            short = item if len(item) <= 22 else item[:20] + "…"
            if tag_cols[i % 2].button(f"✕ {short}", key=f"tag_{state_key}_{i}", use_container_width=True):
                to_remove = item
        if to_remove:
            st.session_state[state_key] = [x for x in selected if x != to_remove]
            st.rerun()

    # Search input
    query = st.sidebar.text_input(
        f"Search {label.lower()}",
        key=search_key,
        placeholder=f"Type to search...",
        label_visibility="collapsed"
    )

    # Suggestion buttons
    if query:
        matches = [o for o in options if query.lower() in o.lower() and o not in selected]
        if matches:
            st.sidebar.caption(f"{len(matches)} match{'es' if len(matches) != 1 else ''} — click to add:")
            for match in matches[:max_suggestions]:
                short = match if len(match) <= 28 else match[:26] + "…"
                if st.sidebar.button(short, key=f"sug_{state_key}_{match}", use_container_width=True):
                    st.session_state[state_key] = sorted(list(set(selected + [match])))
                    st.rerun()
            if len(matches) > max_suggestions:
                st.sidebar.caption(f"… and {len(matches) - max_suggestions} more. Narrow your search.")
        else:
            st.sidebar.caption("No matches found.")

    return st.session_state[state_key]

# ── Collector filter ──────────────────────────────────────────────────────────
st.session_state.selected_collectors = tag_filter(
    "Collectors", "collector_search", all_collectors, "selected_collectors"
)

st.sidebar.markdown("")

# ── Year range ────────────────────────────────────────────────────────────────
years_available = df["year"].dropna()
year_min   = int(years_available.min())
year_max   = int(years_available.max())
year_range = st.sidebar.slider(
    "Collection Year Range",
    min_value=year_min,
    max_value=year_max,
    value=(year_min, year_max)
)

st.sidebar.markdown("")

# ── Country filter ────────────────────────────────────────────────────────────
st.session_state.selected_countries = tag_filter(
    "Country", "country_search", all_countries, "selected_countries"
)

st.sidebar.markdown("")

# ── Province filter (options narrow based on selected countries) ───────────────
if st.session_state.selected_countries:
    available_provinces = sorted([
        p for p in df[df["country"].isin(st.session_state.selected_countries)]["province"].unique()
        if p != "Unknown"
    ])
    st.session_state.selected_provinces = [
        p for p in st.session_state.selected_provinces if p in available_provinces
    ]
else:
    available_provinces = all_provinces

st.session_state.selected_provinces = tag_filter(
    "Province / State", "province_search", available_provinces, "selected_provinces"
)

# ── Clear all filters ─────────────────────────────────────────────────────────
st.sidebar.markdown("")
any_active = (
    bool(st.session_state.selected_collectors) or
    bool(st.session_state.selected_countries)  or
    bool(st.session_state.selected_provinces)  or
    (year_range != (year_min, year_max))
)
if any_active:
    if st.sidebar.button("❌ Clear All Filters", use_container_width=True):
        st.session_state.selected_collectors = []
        st.session_state.selected_countries  = []
        st.session_state.selected_provinces  = []
        st.rerun()

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

if st.session_state.selected_countries:
    filtered_df = filtered_df[filtered_df["country"].isin(st.session_state.selected_countries)]

if st.session_state.selected_provinces:
    filtered_df = filtered_df[filtered_df["province"].isin(st.session_state.selected_provinces)]



with_date   = filtered_df["collection_date"].notna().sum()
with_coords = filtered_df["latitude"].notna().sum()

st.sidebar.caption(f"**{len(filtered_df):,}** specimens match filters")
st.sidebar.caption(f"📅 {with_date:,} have collection dates")
st.sidebar.caption(f"📍 {with_coords:,} have coordinates")
n_countries = filtered_df[filtered_df["country"] != "Unknown"]["country"].nunique()
n_provinces = filtered_df[filtered_df["province"] != "Unknown"]["province"].nunique()
st.sidebar.caption(f"🌍 {n_countries:,} countries · {n_provinces:,} provinces/states")


# ─── Overview ─────────────────────────────────────────────────────────────────
st.title("UBC Herbarium Explorer")
st.subheader("Collection Overview")
st.info("ℹ️ This dashboard currently represents only the **algae** portion of the UBC Herbarium collection.")
st.markdown("---")

# Total physical collection size (databased + undatabased)
TOTAL_COLLECTION = 102_862

missing_dates_pct  = filtered_df["collection_date"].isna().sum() / len(filtered_df) * 100
missing_coords_pct = filtered_df["latitude"].isna().sum() / len(filtered_df) * 100

databased        = len(df)          # all records in the loaded CSV, unfiltered
pct_databased    = databased / TOTAL_COLLECTION * 100
pct_filtered     = len(filtered_df) / TOTAL_COLLECTION * 100
pct_dated        = with_date  / TOTAL_COLLECTION * 100
pct_coords       = with_coords / TOTAL_COLLECTION * 100

# ── Featured banner: total physical collection ────────────────────────────────
st.markdown(
    f"""
    <div style="
        background: #1f2e1f;
        border-radius: 10px;
        padding: 1.2rem 2rem;
        margin-bottom: 1.2rem;
        display: flex;
        align-items: center;
        gap: 2rem;
    ">
        <div style="color:#d4e8d4; font-family:'Playfair Display',serif; font-size:2.6rem; font-weight:600; line-height:1;">
            {TOTAL_COLLECTION:,}
        </div>
        <div>
            <div style="color:#d4e8d4; font-size:1rem; font-weight:600;">Total Physical Specimens in Collection</div>
            <div style="color:#8ab88a; font-size:0.85rem; margin-top:0.2rem;">
                {databased:,} databased ({pct_databased:.1f}%) &nbsp;·&nbsp;
                {TOTAL_COLLECTION - databased:,} not yet databased
            </div>
        </div>
    </div>
    """,
    unsafe_allow_html=True
)

# ── Four metrics: filtered counts + % of total collection ─────────────────────
col1, col2, col3, col4 = st.columns(4)
col1.metric(
    "Filtered Specimens",
    f"{len(filtered_df):,}",
    delta=f"{pct_filtered:.1f}% of collection",
    delta_color="off"
)
col2.metric(
    "Collectors",
    f"{filtered_df['full_name'].nunique():,}"
)
col3.metric(
    "With Dates",
    f"{with_date:,}",
    delta=f"{pct_dated:.1f}% of collection",
    delta_color="off"
)
col4.metric(
    "Georeferenced",
    f"{with_coords:,}",
    delta=f"{pct_coords:.1f}% of collection",
    delta_color="off"
)

if missing_dates_pct > 10 or missing_coords_pct > 10:
    st.markdown(
        f'<div class="data-note">⚠️ This is real herbarium data — '
        f'{missing_dates_pct:.0f}% of specimens are missing collection dates and '
        f'{missing_coords_pct:.0f}% are missing coordinates. '
        f'This is normal for older collections that predate standardized digitization.</div>',
        unsafe_allow_html=True
    )

st.markdown("---")

# ── Specimens per collector ───────────────────────────────────────────────
st.subheader("Specimens per Collector")

collector_counts = (
    filtered_df.groupby("full_name")
    .size()
    .reset_index(name="specimen_count")
    .sort_values("specimen_count", ascending=False)
)

max_specimens = int(collector_counts["specimen_count"].max())
min_specimens = st.slider(
    "Minimum specimens",
    min_value=1,
    max_value=max(100, max_specimens // 10),
    value=1,
    step=1,
    help="Only show collectors with at least this many specimens",
    key="overview_min_specimens"
)
collector_counts = collector_counts[collector_counts["specimen_count"] >= min_specimens]

if len(collector_counts) <= 5:
    n_display = len(collector_counts)
    st.caption(f"Showing all {n_display} collector(s) with {min_specimens}+ specimens.")
else:
    n_display = st.slider(
        "Number of collectors to display",
        min_value=5,
        max_value=min(200, len(collector_counts)),
        value=min(50, len(collector_counts)),
        step=5
    )
    st.caption(
        f"Showing top {n_display} of {len(collector_counts):,} collectors "
        f"with {min_specimens}+ specimens."
    )
    n_display = min(n_display, len(collector_counts))

chart_df = collector_counts.head(n_display).sort_values("specimen_count", ascending=True)

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

# ── Collection activity by time period ────────────────────────────────────
st.subheader("Collection Activity by Time Period")
dated = filtered_df[filtered_df["year"].notna()].copy()

if len(dated) > 0:
    year_min_act = int(dated["year"].min())
    year_max_act = int(dated["year"].max())
    total_years  = max(1, year_max_act - year_min_act)

    bin_size = st.slider(
        "Group by (years)",
        min_value=1,
        max_value=max(10, total_years // 5),
        value=min(10, max(1, total_years // 10)),
        step=1,
        help="Set to 1 to see individual years, 10 for decades, etc.",
        key="activity_bin_size"
    )

    dated["period"] = (dated["year"] // bin_size) * bin_size
    period_counts = dated.groupby("period").size().reset_index(name="count")
    period_label  = "Year" if bin_size == 1 else f"{bin_size}-Year Period"

    fig2 = px.bar(
        period_counts, x="period", y="count",
        labels={"period": period_label, "count": "Specimens"},
        color="count", color_continuous_scale="Greens"
    )
    fig2.update_layout(
        coloraxis_showscale=False,
        plot_bgcolor="white",
        paper_bgcolor="white",
        xaxis=dict(tickformat="d")
    )
    st.plotly_chart(fig2, use_container_width=True)
else:
    st.info("No dated specimens in current filter selection.")

st.markdown("---")

# ─── Collector Timeline ───────────────────────────────────────────────────────
st.markdown("---")
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

    # Derive last name from full_name for reliable comparison
    timeline["derived_lastname"] = (
        timeline["full_name"]
        .str.strip()
        .str.split()
        .str[-1]
        .str.lower()
        .fillna("")
    )

    lastname_counts = timeline["derived_lastname"].value_counts()

    def assign_status(row):
        if row["span_years"] >= UNUSUAL_SPAN_YEARS:
            return "Unusual span (possible attribution error)"
        ln = row.get("derived_lastname", "")
        if ln and lastname_counts.get(ln, 0) > 1:
            return "Shared last name"
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
        value=1,
        step=1,
        help="Only show collectors with at least this many specimens",
        key="timeline_min_specimens"
    )

    # Guard: ensure max_value > min_value for the top_n slider
    n_eligible = len(timeline[timeline["specimen_count"] >= min_specimens])
    top_n_max  = max(11, n_eligible)
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
        col_act_title, col_act_dl = st.columns([6, 1])
        col_act_title.subheader("Collector Activity Details")

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
        col_act_dl.download_button(
            "⬇️ CSV",
            data=table.sort_values("First Collection").to_csv(index=False),
            file_name="collector_activity.csv",
            mime="text/csv",
            use_container_width=True
        )
        st.dataframe(
            table.sort_values("First Collection"),
            use_container_width=True,
            hide_index=True
        )


# ─── Geographic Map ───────────────────────────────────────────────────────────
st.markdown("---")
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

    # ── Region filter ─────────────────────────────────────────────────────────
    all_lats = map_df["latitude"]
    all_lons = map_df["longitude"]

    with st.expander("🔍 Filter by region", expanded=False):
        st.caption(
            "Narrow the visible area using the sliders below, then the map will show "
            "up to 5,000 points within that region. Pan the map first to find your "
            "region of interest, then use these sliders to match the bounds."
        )
        rcol1, rcol2 = st.columns(2)

        # Add a buffer when min == max (e.g. single point filtered) to prevent slider crash
        lat_min = float(round(all_lats.min(), 2))
        lat_max = float(round(all_lats.max(), 2))
        if lat_min == lat_max:
            lat_min -= 0.5
            lat_max += 0.5

        lon_min = float(round(all_lons.min(), 2))
        lon_max = float(round(all_lons.max(), 2))
        if lon_min == lon_max:
            lon_min -= 0.5
            lon_max += 0.5

        lat_range = rcol1.slider(
            "Latitude range",
            min_value=lat_min,
            max_value=lat_max,
            value=(lat_min, lat_max),
            step=0.5,
            key="map_lat_range"
        )
        lon_range = rcol2.slider(
            "Longitude range",
            min_value=lon_min,
            max_value=lon_max,
            value=(lon_min, lon_max),
            step=0.5,
            key="map_lon_range"
        )

    # Apply region filter
    map_df = map_df[
        (map_df["latitude"]  >= lat_range[0]) & (map_df["latitude"]  <= lat_range[1]) &
        (map_df["longitude"] >= lon_range[0]) & (map_df["longitude"] <= lon_range[1])
    ].copy()

    region_filtered = len(map_df)
    if map_df.empty:
        st.error("No georeferenced specimens fall within the selected region.")
        st.stop()

    if len(map_df) > MAX_MAP_POINTS:
        st.markdown(
            f'<div class="data-note">🗺 {region_filtered:,} georeferenced specimens fall within this region. '
            f'Displaying a random sample of {MAX_MAP_POINTS:,} for performance. '
            f'Narrow the region using the filter above to see all points.</div>',
            unsafe_allow_html=True
        )
        map_df = map_df.sample(MAX_MAP_POINTS, random_state=42)
    elif region_filtered < len(filtered_df.dropna(subset=["latitude", "longitude"])):
        st.markdown(
            f'<div class="data-note">🗺 Showing all {region_filtered:,} georeferenced specimens in the selected region.</div>',
            unsafe_allow_html=True
        )

    # Centre map on filtered region
    map_center_lat = (lat_range[0] + lat_range[1]) / 2
    map_center_lon = (lon_range[0] + lon_range[1]) / 2
    lat_span = lat_range[1] - lat_range[0]
    lon_span = lon_range[1] - lon_range[0]
    import math
    zoom_lat = math.log2(360 / max(lat_span, 0.01)) - 1
    zoom_lon = math.log2(360 / max(lon_span, 0.01)) - 1
    auto_zoom = max(1, min(12, int(min(zoom_lat, zoom_lon))))

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
            "country":         True,
            "province":        True,
            "latitude":        False,
            "longitude":       False,
            "full_name":       False
        },
        labels={
            "full_name":       "Collector",
            "catalognumber":   "Catalog #",
            "collection_date": "Date",
            "localityname":    "Locality",
            "country":         "Country",
            "province":        "Province/State"
        },
        center={"lat": map_center_lat, "lon": map_center_lon},
        zoom=auto_zoom,
        height=600,
        map_style="open-street-map"
    )
    fig.update_layout(
        legend_title="Collector",
        dragmode="lasso"
    )
    st.caption("💡 Use the box or lasso select tools in the chart toolbar to select points. Selections accumulate — use the Clear button below to reset.")

    # Key the chart off a counter so pressing Clear forces a fresh chart instance,
    # wiping Plotly's internal selection state and preventing it from re-adding points.
    if "map_clear_counter" not in st.session_state:
        st.session_state.map_clear_counter = 0
    selection = st.plotly_chart(
        fig,
        use_container_width=True,
        on_select="rerun",
        selection_mode=["points", "box", "lasso"],
        key=f"map_selection_{st.session_state.map_clear_counter}"
    )

    if selection and selection.selection and selection.selection.points:
        selected_lats = [p["lat"] for p in selection.selection.points]
        selected_lons = [p["lon"] for p in selection.selection.points]
        selected_mask = map_df.apply(
            lambda row: any(
                abs(row["latitude"] - lat) < 1e-9 and abs(row["longitude"] - lon) < 1e-9
                for lat, lon in zip(selected_lats, selected_lons)
            ),
            axis=1
        )
        newly_selected = set(map_df[selected_mask]["catalognumber"].tolist())
        st.session_state.map_selected_catalognumbers |= newly_selected

    # Render clear button outside the selection check so it always appears
    # when there are selections, and pressing it clears state before the
    # table is rendered this cycle.
    if st.session_state.map_selected_catalognumbers:
        st.markdown("---")
        accumulated_df = filtered_df[
            filtered_df["catalognumber"].isin(st.session_state.map_selected_catalognumbers)
        ].copy()

        col_title, col_clear, col_sel_dl = st.columns([5, 1, 1])
        col_title.subheader(f"Selected Specimens ({len(accumulated_df):,})")

        cleared = col_clear.button("🗑️ Clear", use_container_width=True)
        if cleared:
            st.session_state.map_selected_catalognumbers = set()
            st.session_state.map_clear_counter += 1

        # Only render the table if not just cleared
        if not cleared:
            sel_cols = ["specify_url", "catalognumber", "full_name", "collection_date",
                        "country", "province", "localityname", "latitude", "longitude"]
            sel_display = accumulated_df[[c for c in sel_cols if c in accumulated_df.columns]].copy()
            sel_display_renamed = sel_display.rename(columns={
                "catalognumber":   "Catalog #",
                "full_name":       "Collector",
                "collection_date": "Date",
                "country":         "Country",
                "province":        "Province/State",
                "localityname":    "Locality",
                "latitude":        "Lat",
                "longitude":       "Lon",
                "specify_url":     "Specify"
            })
            col_sel_dl.download_button(
                "⬇️ CSV",
                data=sel_display_renamed.drop(columns=["Specify"], errors="ignore")
                    .sort_values("Date", na_position="last").to_csv(index=False),
                file_name="selected_specimens.csv",
                mime="text/csv",
                use_container_width=True
            )
            st.dataframe(
                sel_display_renamed.sort_values("Date", na_position="last"),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Specify": st.column_config.LinkColumn(
                        "Specify",
                        display_text="Open ↗",
                        help="Open this record in Specify"
                    )
                }
            )


# ─── Specimen Records ─────────────────────────────────────────────────────────
st.markdown("---")
col_spec_title, col_spec_dl = st.columns([6, 1])
col_spec_title.subheader("Specimen Records")

spec_cols = ["specify_url", "catalognumber", "full_name", "collection_date",
             "country", "province", "localityname", "latitude", "longitude"]
filters_applied = (
    bool(st.session_state.selected_collectors) or
    bool(st.session_state.selected_countries)  or
    bool(st.session_state.selected_provinces)  or
    (year_range != (year_min, year_max))
)
display_df = (
    filtered_df[[c for c in spec_cols if c in filtered_df.columns]]
    .sort_values("collection_date", na_position="last")
)
if not filters_applied:
    display_df = display_df.head(5000)
    st.caption(f"Showing {len(display_df):,} of {len(filtered_df):,} records. Capped at 5,000 for performance — apply a collector or year filter to see all results.")

display_df = display_df.rename(columns={
    "specify_url":   "Specify",
    "catalognumber": "Catalog #",
    "full_name":     "Collector",
    "collection_date": "Date",
    "country":       "Country",
    "province":      "Province/State",
    "localityname":  "Locality",
    "latitude":      "Lat",
    "longitude":     "Lon"
})

col_spec_dl.download_button(
    "⬇️ CSV",
    data=display_df.drop(columns=["Specify"], errors="ignore").to_csv(index=False),
    file_name="specimen_records.csv",
    mime="text/csv",
    use_container_width=True
)
st.dataframe(
    display_df,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Specify": st.column_config.LinkColumn(
            "Specify",
            display_text="Open ↗",
            help="Open this record in Specify (login required)"
        )
    }
)
