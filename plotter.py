import pandas as pd
import plotly.graph_objects as go
import dash
from dash import dcc, html, Input, Output
from datetime import datetime
import base64
import io
import os
from collections import defaultdict

app = dash.Dash(__name__)
app.title = "Drone Monitor"

drones_data = {}

ERROR_CODES = {
    128: "COMM T/O", 129: "ACK T/O", 130: "PROTO", 131: "PREARM", 132: "RC LOST",
    133: "NO GPS", 139: "WIND", 140: "PAYLOAD", 141: "PROXIMITY", 188: "SIMERR",
    189: "CONTROL", 190: "SENSOR", 191: "ERROR", 192: "COMPAT",
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


def generate_log_info():
    total_drones = len(drones_data)
    non_six_drones_ids = [drone_id for drone_id, data in drones_data.items() if any(status != 6 for status in data['gps_statuses'])]
    num_non_six_drones = len(non_six_drones_ids)
    all_timestamps = [ts for data in drones_data.values() for ts in data['timestamps']]
    total_duration_seconds = (max(all_timestamps) - min(all_timestamps)) / 1000 if all_timestamps else 0

    return f"""Analysis Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\nTotal number of drones: {total_drones}
Drones with GPS_STATUS different from 6: {num_non_six_drones}
IDs of such drones: {', '.join(non_six_drones_ids)}
Total log duration: {total_duration_seconds:.2f} seconds"""

app.layout = html.Div([
    html.H1("Luminousbees Swarm monitoring", style={"textAlign": "center"}),

    dcc.Upload(
        id='upload-data',
        children=html.Div(['📁 Drag & Drop or ', html.A('Select a TXT File')]),
        style={
            'width': '50%',
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
            {'label': 'RSSI SiK (%)', 'value': 'rssi_sik'},
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

    html.Div([
        html.Div(id='threshold-label', style={'fontWeight': 'bold', 'marginBottom': '5px'}),
        dcc.Input(
            id='drift-threshold',
            type='number',
            value=0,
            step=0.1,
            style={'margin': '0 10px'}
        )
    ], id='threshold-container', style={'textAlign': 'center', 'marginBottom': '20px'}),


    dcc.Graph(id='drones-graph'),
    html.Pre(id='log-info', style={'whiteSpace': 'pre-wrap', 'marginTop': '20px', 'padding': '10px'})
])

@app.callback(
    Output('threshold-container', 'style'),
    Output('threshold-label', 'children'),
    Input('metric-selector', 'value')
)
def update_threshold_label(metric):
    if metric in ['driftHs', 'driftVs']:
        return {'textAlign': 'center', 'marginBottom': '20px'}, "Show drones with drift higher than:"
    elif metric == 'batteries':
        return {'textAlign': 'center', 'marginBottom': '20px'}, "Show drones with battery lower than:"
    elif metric == 'rssis':
        return {'textAlign': 'center', 'marginBottom': '20px'}, "Show drones with RSSI higher than:"
    elif metric == 'rssi_sik':
        return {'textAlign': 'center', 'marginBottom': '20px'}, "Show drones with RSSI SiK above:"
    else:
        return {'display': 'none'}, ""

@app.callback(
    Output('log-info', 'children'),
    Output('drones-graph', 'figure'),
    Input('upload-data', 'contents'),
    Input('metric-selector', 'value'),
    Input('drift-threshold', 'value'),
    prevent_initial_call='initial_duplicate'
)
def update_output(contents, selected_metric, threshold):
    if contents:
        parse_uploaded_file(contents)

    if not drones_data:
        return "Please upload a valid TXT file.", go.Figure()

    fig = go.Figure()
    drones_displayed = 0
    all_timestamps = [ts for data in drones_data.values() for ts in data['timestamps']]
    min_timestamp = min(all_timestamps) if all_timestamps else 0

    if selected_metric == 'fc_errors':
        error_summary = defaultdict(set)

        for drone_id, data in sorted(drones_data.items()):
            for ts, code in data.get('fc_errors', []):
                if code not in ERROR_CODES:
                    continue
                error_name = ERROR_CODES[code]
                error_summary[error_name].add(drone_id)
                relative_time = (ts - min_timestamp) / 1000.0
                fig.add_trace(go.Scatter(
                    x=[relative_time],
                    y=[error_name],
                    mode='markers+text',
                    name=f'Drone {drone_id}',
                    text=[f'Drone {drone_id}'],
                    textposition='top center',
                    marker=dict(size=10, symbol='x')
                ))
                drones_displayed += 1

        summary_lines = [f"{err}: {' '.join(sorted(ids))}" for err, ids in error_summary.items()]
        summary_text = "\n".join(summary_lines) if summary_lines else "No critical errors found."

        fig.update_layout(
            title="Flight Controller Errors",
            xaxis_title="Time (s)",
            yaxis_title="Error Type",
            template='plotly_white',
            height=900,
            margin=dict(t=80, b=80)
        )
        return summary_text, fig

    titles = {
        'gps_statuses': 'GPS Status',
        'batteries': 'Battery (dV)',
        'rssis': 'RSSI',
        'rssi_sik': 'RSSI SiK (%)',
        'driftHs': 'Horizontal Drift (m)',
        'driftVs': 'Vertical Drift (m)'
    }

    for drone_id, data in sorted(drones_data.items()):
        y_values = data[selected_metric]
        display_drone = True

        if selected_metric in ['driftHs', 'driftVs']:
            display_drone = any(v is not None and v > threshold for v in y_values)
        elif selected_metric == 'batteries':
            display_drone = any(v is not None and v < threshold for v in y_values)
        elif selected_metric == 'rssis':
            display_drone = any(v is not None and v > threshold for v in y_values)
        elif selected_metric == 'gps_statuses':
            if all(val == y_values[0] for val in y_values):
                continue
            display_drone = any(v != 6 for v in y_values)
        elif selected_metric == 'rssi_sik':
            display_drone = any(v is not None and v > threshold and 0 <= v <= 100 for v in data['rssis'])

        if not display_drone:
            continue

        relative_timestamps = [(ts - min_timestamp) / 1000.0 for ts in data['timestamps']]

        fig.add_trace(go.Scatter(
            x=relative_timestamps,
            y=y_values,
            mode='lines+markers',
            name=f'Drone {drone_id}'
        ))
        drones_displayed += 1

    yaxis_config = dict(
        tickmode='array',
        tickvals=[3, 4, 5, 6],
        ticktext=['DGPS', '3D', 'RTK', 'RTK+'],
        dtick=1,
        automargin=True,
        constrain='range'
    ) if selected_metric == 'gps_statuses' else dict(automargin=True, constrain='range')

    fig.update_layout(
        title=titles[selected_metric],
        xaxis_title='Time (s)',
        yaxis_title=titles[selected_metric],
        template='plotly_white',
        height=900,
        margin=dict(t=80, b=80),
        yaxis=yaxis_config
    )

    if drones_displayed == 0 and selected_metric in ['driftHs', 'driftVs']:
        return f"No drones exceed the threshold of {threshold} m in {titles[selected_metric]}.", fig

    return generate_log_info(), fig

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8050))
    app.run(host="0.0.0.0", port=port)
