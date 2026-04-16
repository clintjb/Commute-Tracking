import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# --- Load & Prepare Data ---
df = pd.read_csv("Commute Tracker - Metrics.csv")
df['Date'] = pd.to_datetime(df['Date'])
df['Hour'] = pd.to_datetime(df['Departure Time']).dt.hour + pd.to_datetime(df['Departure Time']).dt.minute / 60
df['Day of Week'] = pd.Categorical(df['Day of Week'],
    categories=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"], ordered=True)

latest = df.sort_values("Date").iloc[-1]
RAG_COLORS = {"Green": "green", "Amber": "orange", "Red": "red"}
PERIOD_COLORS = {"Morning": "#ff7350", "Evening": "#374d84"}
WEEKDAY_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]

# --- Compressed Time Scale ---
def compress_time(hour):
    hour = np.asarray(hour, dtype=float)
    result = np.where(hour <= 8, hour,
             np.where(hour <= 17, 8 + (hour - 8) * 0.2,
                                  8 + 9 * 0.2 + (hour - 17)))
    return result

df['Hour_Compressed'] = compress_time(df['Hour'])

original_ticks = [0, 2, 4, 6, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 20, 22, 24]
compressed_ticks = compress_time(original_ticks)
tick_labels = [f"{int(h)}:00" for h in original_ticks]

# --- KPI HTML ---
rag_color = RAG_COLORS.get(latest["RAG"], "gray")
kpi_html = f"""
<style>
    .kpi-container {{
        text-align: center;
        font-family: "Noto Sans Display",Helvetica Neue,Helvetica,Arial,sans-serif;
        padding-top: 20px;
    }}
    .kpi-container .rag {{
        display: inline-block;
        width: 48px;
        height: 48px;
        border-radius: 50%;
        margin-right: 8px;
        vertical-align: middle;
    }}
    .kpi-container .duration {{
        font-size: 48px;
        margin: 0;
    }}
    .kpi-container .details {{
        font-size: 16px;
        color: #666;
        margin-top: 8px;
    }}
    .kpi-container .timestamp {{
        font-size: 12px;
        margin-top: 10px;
        font-style: italic;
        color: #777;
    }}
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

# --- Dashboard ---
fig = make_subplots(rows=4, cols=1, row_heights=[0.25]*4, vertical_spacing=0.1,
    subplot_titles=("Commute Duration", "Departure Time vs Commute Duration",
                    "Distribution", "Average Commute Duration Heatmap"))

# 1. Trend
for period in df["Period"].unique():
    d = df[df["Period"] == period]
    c = PERIOD_COLORS.get(period, "gray")
    fig.add_trace(go.Scatter(x=d["Date"], y=d["Duration (mins)"], mode='lines+markers',
        name=period, line=dict(color=c), marker=dict(color=c)), row=1, col=1)

# 2. Scatter (compressed time)
for period in df["Period"].unique():
    d = df[df["Period"] == period]
    c = PERIOD_COLORS.get(period, "gray")
    fig.add_trace(go.Scatter(x=d["Hour_Compressed"], y=d["Duration (mins)"], mode='markers',
        marker=dict(size=8, opacity=0.7, color=c), name=f"{period} Commutes",
        customdata=d["Hour"], hovertemplate="Hour: %{customdata:.1f}<br>Duration: %{y} mins<extra></extra>"),
        row=2, col=1)

# 3. Box Plot
for period in df["Period"].unique():
    d = df[df["Period"] == period]
    c = PERIOD_COLORS.get(period, "gray")
    fig.add_trace(go.Box(y=d["Duration (mins)"], name=period,
        marker_color=c, line=dict(color=c)), row=3, col=1)

# 4. Heatmap
pivot = df.groupby(['Day of Week', 'Period'])['Duration (mins)'].mean().unstack("Day of Week")
z = np.where(pivot.values < 10, np.nan, pivot.values)
fig.add_trace(go.Heatmap(z=z, x=pivot.columns, y=pivot.index,
    colorscale=[[0, "green"], [0.5, "orange"], [1, "red"]],
    showscale=False, hoverongaps=False), row=4, col=1)

# --- Styling ---
fig.update_layout(height=1400, showlegend=False,
    plot_bgcolor="white", paper_bgcolor="white", font=dict(color="black"))

for annotation in fig['layout']['annotations']:
    annotation.update(x=0, xanchor='left')

fig.update_xaxes(tickvals=compressed_ticks, ticktext=tick_labels, row=2, col=1)
fig.update_xaxes(categoryorder='array', categoryarray=WEEKDAY_ORDER, row=4, col=1)
fig.update_xaxes(showgrid=True, gridwidth=0.5, gridcolor='lightgray')
fig.update_yaxes(showgrid=True, gridwidth=0.5, gridcolor='lightgray')

x0, x1 = compress_time(8), compress_time(17)
fig.add_vrect(x0=x0, x1=x1, fillcolor="lightgray", opacity=0.3, layer="below", line_width=0, row=2, col=1)
fig.add_vline(x=x0, line_width=1, line_dash="dash", line_color="gray", row=2, col=1)
fig.add_vline(x=x1, line_width=1, line_dash="dash", line_color="gray", row=2, col=1)

fig.write_html("dashboard.html", include_plotlyjs='cdn')
print("Generated: kpi.html, dashboard.html")
