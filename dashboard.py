import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
RAG_COLORS = {"Green": "green", "Amber": "orange", "Red": "red"}
PERIOD_COLORS = {"Morning": "#ff7350", "Evening": "#374d84"}

COMPRESS_START, COMPRESS_END, COMPRESS_FACTOR = 8, 17, 0.2

# ---------------------------------------------------------------------------
# Load & prepare data
# ---------------------------------------------------------------------------
df = pd.read_csv("Commute Tracker - Metrics.csv")
df["Date"] = pd.to_datetime(df["Date"])
df["Hour"] = (pd.to_datetime(df["Departure Time"]).dt.hour
              + pd.to_datetime(df["Departure Time"]).dt.minute / 60)
df["Day of Week"] = pd.Categorical(df["Day of Week"], categories=WEEKDAYS, ordered=True)

latest = df.sort_values("Date").iloc[-1]

# ---------------------------------------------------------------------------
# Compressed time scale
# ---------------------------------------------------------------------------
def compress_time(hour):
    hour = np.asarray(hour, dtype=float)
    compressed_width = (COMPRESS_END - COMPRESS_START) * COMPRESS_FACTOR
    return np.where(
        hour <= COMPRESS_START, hour,
        np.where(
            hour <= COMPRESS_END,
            COMPRESS_START + (hour - COMPRESS_START) * COMPRESS_FACTOR,
            COMPRESS_START + compressed_width + (hour - COMPRESS_END)
        )
    )

df["Hour_Compressed"] = compress_time(df["Hour"])

# Axis ticks: drop those strictly inside the condensed zone (no labels or gridlines there)
_all_ticks = [0, 2, 4, 6, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 20, 22, 24]
_outside = [h <= COMPRESS_START or h >= COMPRESS_END for h in _all_ticks]
axis_ticks  = compress_time([h for h, keep in zip(_all_ticks, _outside) if keep])
axis_labels = [f"{h}:00" for h, keep in zip(_all_ticks, _outside) if keep]

x_zone_start = compress_time(COMPRESS_START)
x_zone_end   = compress_time(COMPRESS_END)

# ---------------------------------------------------------------------------
# KPI widget
# ---------------------------------------------------------------------------
rag_color = RAG_COLORS.get(latest["RAG"], "gray")
kpi_html = f"""
<style>
    .kpi-container {{
        text-align: center;
        font-family: "Noto Sans Display", Helvetica Neue, Helvetica, Arial, sans-serif;
        padding-top: 20px;
    }}
    .kpi-container .rag {{
        display: inline-block;
        width: 48px; height: 48px;
        border-radius: 50%;
        margin-right: 8px;
        vertical-align: middle;
    }}
    .kpi-container .duration  {{ font-size: 48px; margin: 0; }}
    .kpi-container .details   {{ font-size: 16px; color: #666; margin-top: 8px; }}
    .kpi-container .timestamp {{ font-size: 12px; margin-top: 10px; font-style: italic; color: #777; }}
</style>
<div class="kpi-container">
    <div class="duration">
        <span class="rag" style="background-color:{rag_color}"></span>
        {latest['Duration (mins)']} mins
    </div>
    <div class="details">{latest['Day of Week']} {latest['Period']}</div>
    <div class="timestamp">Updated: {latest['Date'].strftime('%d-%m-%Y')}</div>
</div>
"""
with open("kpi.html", "w") as f:
    f.write(kpi_html)

# ---------------------------------------------------------------------------
# Helper: add one trace per period
# ---------------------------------------------------------------------------
def add_period_traces(fig, trace_fn, row):
    for period, group in df.groupby("Period", observed=True):
        color = PERIOD_COLORS.get(period, "gray")
        fig.add_trace(trace_fn(period, group, color), row=row, col=1)

# ---------------------------------------------------------------------------
# Build dashboard
# ---------------------------------------------------------------------------
fig = make_subplots(
    rows=4, cols=1,
    row_heights=[0.25] * 4,
    vertical_spacing=0.1,
    subplot_titles=(
        "Commute Duration",
        "Departure Time vs Commute Duration",
        "Distribution",
        "Average Commute Duration Heatmap",
    ),
)

# 1. Trend line
add_period_traces(fig, lambda period, d, c: go.Scatter(
    x=d["Date"], y=d["Duration (mins)"], mode="lines+markers",
    name=period, line=dict(color=c), marker=dict(color=c),
), row=1)

# 2. Scatter – compressed departure time
add_period_traces(fig, lambda period, d, c: go.Scatter(
    x=d["Hour_Compressed"], y=d["Duration (mins)"], mode="markers",
    name=f"{period} Commutes",
    marker=dict(size=8, opacity=0.7, color=c),
    customdata=d["Hour"],
    hovertemplate="Hour: %{customdata:.1f}<br>Duration: %{y} mins<extra></extra>",
), row=2)

# 3. Box plot
add_period_traces(fig, lambda period, d, c: go.Box(
    y=d["Duration (mins)"], name=period, marker_color=c, line=dict(color=c),
), row=3)

# 4. Heatmap
pivot = df.groupby(["Day of Week", "Period"])["Duration (mins)"].mean().unstack("Day of Week")
z = np.where(pivot.values < 10, np.nan, pivot.values)
fig.add_trace(go.Heatmap(
    z=z, x=pivot.columns, y=pivot.index,
    colorscale=[[0, "green"], [0.5, "orange"], [1, "red"]],
    showscale=False, hoverongaps=False,
), row=4, col=1)

# ---------------------------------------------------------------------------
# Styling
# ---------------------------------------------------------------------------
fig.update_layout(
    height=1400, showlegend=False,
    plot_bgcolor="white", paper_bgcolor="white",
    font=dict(color="black"),
)

# Left-align subplot titles
for annotation in fig["layout"]["annotations"]:
    annotation.update(x=0, xanchor="left")

# Global grid
fig.update_xaxes(showgrid=True, gridwidth=0.5, gridcolor="lightgray")
fig.update_yaxes(showgrid=True, gridwidth=0.5, gridcolor="lightgray")

# Heatmap: enforce weekday order
fig.update_xaxes(categoryorder="array", categoryarray=WEEKDAYS, row=4, col=1)

# Scatter (row 2): custom ticks only outside condensed zone, no auto gridlines
fig.update_xaxes(tickvals=axis_ticks, ticktext=axis_labels, showgrid=False, row=2, col=1)

# Condensed zone: gray fill + dashed boundaries
fig.add_vrect(x0=x_zone_start, x1=x_zone_end,
              fillcolor="lightgray", opacity=0.3, layer="below", line_width=0, row=2, col=1)
fig.add_vline(x=x_zone_start, line_width=1, line_dash="dash", line_color="gray", row=2, col=1)
fig.add_vline(x=x_zone_end,   line_width=1, line_dash="dash", line_color="gray", row=2, col=1)

# Hourly gridlines in the visible ranges either side of the condensed zone
for hour in [*range(5, 8), *range(18, 21)]:
    fig.add_vline(x=compress_time(hour), line_width=0.5, line_color="lightgray", row=2, col=1)

# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------
fig.write_html("dashboard.html", include_plotlyjs="cdn")
print("Generated: kpi.html, dashboard.html")
