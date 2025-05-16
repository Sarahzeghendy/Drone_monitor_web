import dash
from dash import dcc, html, Input, Output
import plotly.graph_objects as go
import pandas as pd
import base64
import io
from datetime import datetime
from collections import defaultdict
import os

app = dash.Dash(__name__)
app.title = "Drone Monitor"

drones_data = {}

ERROR_CODES = {
    193: "MAG", 194: "GYRO", 195: "ACC", 196: "BARO", 197: "GPS",
    198: "MOTOR", 199: "LOWBAT", 200: "HOME", 201: "FENCE",
    202: "CLK", 203: "EXTCLK", 204: "NO HW", 205: "INITFAIL",
    206: "COMMFAIL", 207: "CRASH", 255: "FATAL"
}

def parse_uploaded_file(contents):
    global drones_data
    drones_data = {}

    content_type, content_string = contents.split(',')
    decoded = base64.b64decode(content_string)
    lines = decoded.decode('utf-8').splitlines()

    for line in lines:
        if line.strip():
            drone_id, data = line.strip().split(' ', 1)
            drone_id = drone_id.split('=')[1]
            entries = data[1:-1].split('//')

            timestamps, fc_errors = [], []

            for entry in entries:
                parts = entry.split(',')
                timestamp = int(parts[0])
                fc_error = None

                for part in parts[2:]:
                    if '=' in part:
                        key, value = part.split('=')
                        value = value.strip()
                        if key == 'fc_error':
                            fc_error = int(value)

                timestamps.append(timestamp)
                if fc_error:
                    fc_errors.append((timestamp, fc_error))

            drones_data[drone_id] = {
                'timestamps': timestamps,
                'fc_errors': fc_errors
            }

app.layout = html.Div([
    html.H1("FC Error Aggregated Report", style={"textAlign": "center"}),

    dcc.Upload(
        id='upload-data',
        children=html.Div(['📁 Drag & Drop or ', html.A('Select a TXT File')]),
        style={
            'width': '60%',
            'height': '60px',
            'lineHeight': '60px',
            'borderWidth': '2px',
            'borderStyle': 'dashed',
            'borderRadius': '10px',
            'textAlign': 'center',
            'margin': 'auto',
            'marginBottom': '20px'
        },
        accept='.txt'
    ),

    html.Div(id='fc-error-graphs')
])

@app.callback(
    Output('fc-error-graphs', 'children'),
    Input('upload-data', 'contents')
)
def update_fc_error_graphs(contents):
    if not contents:
        return "Please upload a TXT file."

    parse_uploaded_file(contents)

    if not drones_data:
        return "No data found."

    # Regrouper par erreur
    error_groups = defaultdict(list)
    min_timestamp = min(ts for data in drones_data.values() for ts in data['timestamps'])

    for drone_id, data in drones_data.items():
        for ts, code in data.get('fc_errors', []):
            if code in ERROR_CODES:
                error_groups[code].append((drone_id, ts))

    if not error_groups:
        return "No critical errors found."

    graphs = []
    for code, entries in sorted(error_groups.items()):
        error_name = ERROR_CODES[code]
        fig = go.Figure()
        affected_drones = set()

        for drone_id, ts in entries:
            relative_time = (ts - min_timestamp) / 1000.0
            fig.add_trace(go.Scatter(
                x=[relative_time],
                y=[error_name],
                mode='markers+text',
                name=f'Drone {drone_id}',
                text=[drone_id],
                textposition='top center',
                marker=dict(size=10, symbol='x')
            ))
            affected_drones.add(drone_id)

        fig.update_layout(
            title=f"Error: {error_name} (code {code})",
            xaxis_title="Time (s)",
            yaxis_title="",
            template='plotly_white',
            height=400,
            margin=dict(t=60, b=40)
        )

        graph_component = html.Div([
            dcc.Graph(figure=fig),
            html.P(f"Drones affected: {' '.join(sorted(affected_drones))}", style={"textAlign": "center", "fontWeight": "bold"})
        ])
        graphs.append(graph_component)

    return graphs

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8050))
    app.run_server(host="0.0.0.0", port=port)
