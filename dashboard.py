import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Variables
WEEKDAYS      = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
RAG_COLORS    = {"Green": "green", "Amber": "orange", "Red": "red"}
PERIOD_COLORS = {"Morning": "#ff7350", "Evening": "#374d84"}
PERIOD_ORDER  = ["Morning", "Evening"]

COMPRESS_START  = 8
COMPRESS_END    = 17
COMPRESS_FACTOR = 0.2

CSV_PATH = "Commute Tracker - Metrics.csv"

# Helper Functions
def compress_time(hour):
    hour             = np.asarray(hour, dtype=float)
    compressed_width = (COMPRESS_END - COMPRESS_START) * COMPRESS_FACTOR
    result = np.where(
        hour <= COMPRESS_START,
        hour,
        np.where(
            hour <= COMPRESS_END,
            COMPRESS_START + (hour - COMPRESS_START) * COMPRESS_FACTOR,
            COMPRESS_START + compressed_width + (hour - COMPRESS_END),
        ),
    )
    return result.item() if result.shape == () else result


def add_period_traces(fig, df, trace_fn, row):
    for period in PERIOD_ORDER:
        if period in df["Period"].values:
            group = df[df["Period"] == period]
            color = PERIOD_COLORS.get(period, "gray")
            fig.add_trace(trace_fn(period, group, color), row=row, col=1)


# Data Load
df = pd.read_csv(CSV_PATH)
df["Date"]           = pd.to_datetime(df["Date"],           errors="coerce")
df["Departure Time"] = pd.to_datetime(df["Departure Time"], errors="coerce")

if df["Departure Time"].isna().all():
    raise ValueError("Departure Time parsing failed")

df["Hour"]            = df["Departure Time"].dt.hour + df["Departure Time"].dt.minute / 60
df["Day of Week"]     = pd.Categorical(df["Day of Week"], categories=WEEKDAYS, ordered=True)
df["Hour_Compressed"] = compress_time(df["Hour"])

latest = df.sort_values("Date").iloc[-1]

# Compressed Axis Setup
visible_hours = list(range(5, 22))
visible_ticks = [h for h in visible_hours if h <= COMPRESS_START or h >= COMPRESS_END]
axis_ticks    = compress_time(visible_ticks)
axis_labels   = [f"{h}:00" for h in visible_ticks]

x_min        = compress_time(5)
x_max        = compress_time(20)
x_zone_start = compress_time(COMPRESS_START)
x_zone_end   = compress_time(COMPRESS_END)

# Top Level KPI
rag_color = RAG_COLORS.get(latest["RAG"], "gray")
kpi_html  = f"""
<div style='text-align:center;font-family:"Noto Sans Display",Helvetica Neue,Helvetica,Arial,sans-serif;'>
    <div style='font-size:48px;'>
        <span style='display:inline-block;width:48px;height:48px;border-radius:50%;background:{rag_color};'></span>
        {latest['Duration (mins)']} mins
    </div>
    <div style='font-size:16px;color:#666'>{latest['Day of Week']} {latest['Period']}</div>
    <div style='font-size:12px;color:#777;font-style:italic'>Updated: {latest['Date'].strftime('%d-%m-%Y')}</div>
</div>
"""
with open("kpi.html", "w") as f:
    f.write(kpi_html)

# Charts
fig = make_subplots(
    rows=4, cols=1,
    vertical_spacing=0.08,
    subplot_titles=(
        "Commute Duration",
        "Departure Time vs Duration",
        "Distribution",
        "Average Commute Duration",
    ),
)

# Trend
add_period_traces(fig, df, lambda p, d, c: go.Scatter(
    x=d["Date"], y=d["Duration (mins)"], mode="lines+markers",
    line=dict(color=c), marker=dict(color=c, size=8), name=p,
), row=1)

# Departure Time
add_period_traces(fig, df, lambda p, d, c: go.Scatter(
    x=d["Hour_Compressed"], y=d["Duration (mins)"], mode="markers",
    marker=dict(size=10, opacity=0.8, color=c),
    customdata=d["Hour"],
    hovertemplate="Hour: %{customdata:.1f}<br>Duration: %{y} mins<extra></extra>",
    name=p,
), row=2)

# Distribution
add_period_traces(fig, df, lambda p, d, c: go.Box(
    y=d["Duration (mins)"], name=p, marker_color=c,
), row=3)

# Heatmap
pivot = (
    df.groupby(["Period", "Day of Week"])["Duration (mins)"]
    .mean()
    .unstack("Day of Week")
    .reindex(index=PERIOD_ORDER, columns=WEEKDAYS)
)
fig.add_trace(go.Heatmap(
    z=pivot.values, x=pivot.columns, y=pivot.index,
    showscale=False,
    colorscale=[[0, "green"], [0.5, "orange"], [1, "red"]],
), row=4, col=1)

# Overall Styling Of The Charts
fig.update_layout(
    height=1400, showlegend=False,
    plot_bgcolor="white", paper_bgcolor="white",
    font=dict(size=14, color="black"),
)
for ann in fig["layout"]["annotations"]:
    ann.update(x=0, xanchor="left", font=dict(size=16))

fig.update_xaxes(showgrid=True, gridcolor="lightgray")
fig.update_yaxes(showgrid=True, gridcolor="lightgray")

fig.update_xaxes(
    range=[x_min, x_max], tickvals=axis_ticks, ticktext=axis_labels,
    showgrid=False, row=2, col=1,
)
fig.add_vrect(
    x0=x_zone_start, x1=x_zone_end,
    fillcolor="lightgray", opacity=0.3, layer="below", line_width=0,
    row=2, col=1,
)
fig.add_vline(x=x_zone_start, line_dash="dash", line_color="gray", row=2, col=1)
fig.add_vline(x=x_zone_end,   line_dash="dash", line_color="gray", row=2, col=1)

for hour in visible_hours:
    if hour <= COMPRESS_START or hour >= COMPRESS_END:
        fig.add_vline(
            x=compress_time(hour), line_width=0.5, line_color="lightgray",
            row=2, col=1,
        )

# Export Charts
fig.write_html("dashboard.html", include_plotlyjs="cdn")
