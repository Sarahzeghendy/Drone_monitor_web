import dash
from dash import dcc, html, Input, Output
import plotly.graph_objects as go
from datetime import datetime
import base64
import os
from collections import defaultdict

app = dash.Dash(__name__)
app.title = "Drone Monitor"

# Données des drones
drones_data = {}

# Dictionnaire des erreurs critiques
ERROR_CODES = {
    193: "MAG", 194: "GYRO", 195: "ACC", 196: "BARO", 197: "GPS",
    198: "MOTOR", 199: "LOWBAT", 200: "HOME", 201: "FENCE",
    202: "CLK", 203: "EXTCLK", 204: "NO HW", 205: "INITFAIL",
    206: "COMMFAIL", 207: "CRASH", 255: "FATAL"
}

# Parser le fichier .txt

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

            timestamps, gps_statuses, batteries, rssis, driftHs, driftVs = [], [], [], [], [], []
            fc_errors = []

            for entry in entries:
                parts = entry.split(',')
                timestamp = int(parts[0])
                gps_status = float(parts[1].strip().replace('gps=', ''))
                battery = rssi = driftH = driftV = fc_error = None

                for part in parts[2:]:
                    if '=' in part:
                        key, value = part.split('=')
                        value = value.strip()
                        if key == 'battery':
                            battery = float(value)
                        elif key == 'rssi':
                            rssi = float(value) if value != 'None' else None
                        elif key == 'driftH':
                            driftH = float(value)
                        elif key == 'driftV':
                            driftV = float(value)
                        elif key == 'fc_error':
                            fc_error = int(value)

                timestamps.append(timestamp)
                gps_statuses.append(gps_status)
                batteries.append(battery)
                rssis.append(rssi)
                driftHs.append(driftH)
                driftVs.append(driftV)
                if fc_error:
                    fc_errors.append((timestamp, fc_error))

            drones_data[drone_id] = {
                'timestamps': timestamps,
                'gps_statuses': gps_statuses,
                'batteries': batteries,
                'rssis': rssis,
                'driftHs': driftHs,
                'driftVs': driftVs,
                'fc_errors': fc_errors
            }

# Layout de l'app
app.layout = html.Div([
    html.H1("Luminousbees Swarm Monitoring", style={"textAlign": "center"}),

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

    dcc.RadioItems(
        id='metric-selector',
        options=[
            {'label': 'GPS Status', 'value': 'gps_statuses'},
            {'label': 'Battery', 'value': 'batteries'},
            {'label': 'RSSI', 'value': 'rssis'},
            {'label': 'Horizontal Drift', 'value': 'driftHs'},
            {'label': 'Vertical Drift', 'value': 'driftVs'},
            {'label': 'FC Errors', 'value': 'fc_errors'}
        ],
        value='gps_statuses',
        inline=True,
        labelStyle={'margin-right': '20px'},
        style={'textAlign': 'center'}
    ),

    html.Div(id='main-output')
])

@app.callback(
    Output('main-output', 'children'),
    Input('upload-data', 'contents'),
    Input('metric-selector', 'value')
)
def update_output(contents, selected_metric):
    if not contents:
        return "Please upload a valid TXT file."

    parse_uploaded_file(contents)
    if not drones_data:
        return "No data found."

    min_timestamp = min(ts for data in drones_data.values() for ts in data['timestamps'])

    if selected_metric == 'fc_errors':
        error_groups = defaultdict(list)

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

            graphs.append(html.Div([
                dcc.Graph(figure=fig),
                html.P(f"Drones affected: {' '.join(sorted(affected_drones))}", style={"textAlign": "center", "fontWeight": "bold"})
            ]))

        return graphs

    else:
        fig = go.Figure()
        metric_label = {
            'gps_statuses': 'GPS Status',
            'batteries': 'Battery (dV)',
            'rssis': 'RSSI',
            'driftHs': 'Horizontal Drift (m)',
            'driftVs': 'Vertical Drift (m)'
        }[selected_metric]

        for drone_id, data in sorted(drones_data.items()):
            y_values = data[selected_metric]
            relative_timestamps = [(ts - min_timestamp) / 1000.0 for ts in data['timestamps']]
            fig.add_trace(go.Scatter(
                x=relative_timestamps,
                y=y_values,
                mode='lines+markers',
                name=f'Drone {drone_id}'
            ))

        yaxis_config = dict(
            tickmode='array',
            tickvals=[3, 4, 5, 6],
            ticktext=['DGPS', '3D', 'RTK', 'RTK+'],
            automargin=True
        ) if selected_metric == 'gps_statuses' else dict(automargin=True)

        fig.update_layout(
            title=metric_label,
            xaxis_title='Time (s)',
            yaxis_title=metric_label,
            template='plotly_white',
            height=700,
            margin=dict(t=80, b=60),
            yaxis=yaxis_config
        )

        return dcc.Graph(figure=fig)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8050))
    app.run_server(host="0.0.0.0", port=port)
