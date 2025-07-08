from dash import html, dcc, Output, Input, State, no_update, callback, clientside_callback
import dash_mantine_components as dmc
from dash_iconify import DashIconify
import dash
import time
from session_manager import (
    close_ssh_session, 
    connect_and_run_jupyter_with_output, 
    get_output_buffer, 
    clear_output_buffer,
    send_command_to_active_shell,
    disconnect_session
)

# Register this page with Dash Pages
dash.register_page(__name__, path="/notebook")

layout = html.Div([
    dcc.Location(id="page-location-notebook", refresh=False),
    dcc.Store(id="notebook-session-data"),  # Store for session information
    dcc.Store(id="jupyter-process-running", data=False),  # Track if jupyter is running
    dcc.Interval(
        id="output-interval",
        interval=1000,  # Update every second
        n_intervals=0,
        disabled=True  # Initially disabled
    ),
    
    # Header with navigation buttons
    dmc.Flex(
        [
            dmc.Button(
                "Logout",
                id="logout-btn-notebook",
                variant="outline",
                className="button-logout logout-button",
                leftSection=DashIconify(icon="material-symbols:logout-rounded"),
            ),
            html.H3("📓 Jupyter Notebook Session"),
            dmc.Button(
                "Disconnect & Back to Servers",
                id="disconnect-btn",
                variant="outline", 
                color="orange",
                leftSection=DashIconify(icon="material-symbols:arrow-back"),
            ),
        ],
        direction={"base": "column", "sm": "row"},
        gap={"base": "sm", "sm": "lg"},
        justify={"sm": "space-between", "base": "center"},
        align="center",
        style={"marginBottom": "20px"}
    ),
    
    # Server info display
    dmc.Card(
        children=[
            dmc.CardSection(
                dmc.Group([
                    DashIconify(icon="mdi:server", width=24),
                    dmc.Text("Server Information", size="lg", fw=500)
                ]),
                withBorder=True,
                inheritPadding=True,
                py="xs",
            ),
            dmc.SimpleGrid(
                cols=2,
                spacing="md",
                children=[
                    dmc.Group([
                        dmc.Text("Server:", fw=500),
                        dmc.Text(id="server-name-display", c="blue")
                    ]),
                    dmc.Group([
                        dmc.Text("Environment:", fw=500),
                        dmc.Text(id="env-name-display", c="green")
                    ]),
                    dmc.Group([
                        dmc.Text("Directory:", fw=500),
                        dmc.Text(id="dest-folder-display", c="purple")
                    ]),
                    dmc.Group([
                        dmc.Text("Status:", fw=500),
                        dmc.Badge(id="status-badge", variant="filled")
                    ]),
                ]
            )
        ],
        withBorder=True,
        shadow="sm",
        radius="md",
        style={"marginBottom": "20px"}
    ),
    
    # CMD-like terminal window
    dmc.Card(
        children=[
            dmc.CardSection(
                dmc.Group([
                    DashIconify(icon="mdi:console", width=24),
                    dmc.Text("Session Terminal", size="lg", fw=500),
                    dmc.Group([
                        dmc.Button(
                            "Clear",
                            id="clear-terminal-btn",
                            size="xs",
                            variant="subtle",
                            leftSection=DashIconify(icon="mdi:broom", width=16)
                        ),
                        dmc.Button(
                            "Starting Jupyter...",
                            id="start-jupyter-btn",
                            size="xs",
                            variant="filled",
                            color="green",
                            leftSection=DashIconify(icon="mdi:loading", width=16),
                            disabled=True
                        ),
                    ])
                ], justify="space-between"),
                withBorder=True,
                inheritPadding=True,
                py="xs",
            ),
            html.Div(
                id="terminal-output",
                className="terminal-window",
                children=[
                    html.Div("Welcome to Jupyter Notebook Session Manager", className="terminal-line"),
                    html.Div("Automatically starting Jupyter session...", className="terminal-line info"),
                ],
                style={
                    "backgroundColor": "#1e1e1e",
                    "color": "#00ff00",
                    "fontFamily": "monospace",
                    "fontSize": "14px",
                    "padding": "20px",
                    "height": "400px",
                    "overflowY": "auto",
                    "border": "1px solid #333",
                    "borderRadius": "4px"
                }
            ),
            dmc.Space(h=10),
            # Command input area
            dmc.Group([
                dmc.TextInput(
                    id="command-input",
                    placeholder="Enter command (experimental)...",
                    style={"flex": 1},
                    leftSection=DashIconify(icon="mdi:chevron-right", width=16)
                ),
                dmc.Button(
                    "Send",
                    id="send-command-btn",
                    leftSection=DashIconify(icon="mdi:send", width=16)
                )
            ], style={"marginTop": "10px"})
        ],
        withBorder=True,
        shadow="sm",
        radius="md",
    ),
    
    # Status and URL display
    dmc.Card(
        children=[
            dmc.CardSection(
                dmc.Group([
                    DashIconify(icon="mdi:link", width=24),
                    dmc.Text("Jupyter Access", size="lg", fw=500)
                ]),
                withBorder=True,
                inheritPadding=True,
                py="xs",
            ),
            html.Div(id="jupyter-url-display", children=[
                dmc.Text("Jupyter URL will appear here once started...", c="dimmed")
            ])
        ],
        withBorder=True,
        shadow="sm",
        radius="md",
        style={"marginTop": "20px"}
    )
])

# Add CSS for terminal styling
app_styles = """
.terminal-window {
    background-color: #1e1e1e !important;
    color: #00ff00 !important;
    font-family: 'Consolas', 'Monaco', 'Courier New', monospace !important;
}

.terminal-line {
    margin: 2px 0;
    line-height: 1.4;
}

.terminal-line.error {
    color: #ff4444 !important;
}

.terminal-line.success {
    color: #44ff44 !important;
}

.terminal-line.warning {
    color: #ffaa00 !important;
}

.terminal-line.info {
    color: #44aaff !important;
}
"""

# Callback to populate server information when page loads
@callback(
    [Output("server-name-display", "children"),
     Output("env-name-display", "children"), 
     Output("dest-folder-display", "children"),
     Output("status-badge", "children"),
     Output("status-badge", "color")],
    Input("page-location-notebook", "pathname"),
    [State("selected-hostname", "data"),
     State("stored-env-name", "data"),
     State("stored-dest-folder", "data")],
    prevent_initial_call=True
)
def populate_server_info(pathname, hostname, env_name, dest_folder):
    if pathname != "/notebook":
        return no_update, no_update, no_update, no_update, no_update
    
    return (
        hostname or "Unknown",
        env_name or "base", 
        dest_folder or "Unknown",
        "Initializing",
        "yellow"
    )

# Callback to handle Jupyter startup
@callback(
    [Output("jupyter-process-running", "data"),
     Output("output-interval", "disabled"),
     Output("status-badge", "children", allow_duplicate=True),
     Output("status-badge", "color", allow_duplicate=True),
     Output("start-jupyter-btn", "disabled")],
    Input("start-jupyter-btn", "n_clicks"),
    [State("selected-hostname", "data"),
     State("stored-env-name", "data"),
     State("stored-dest-folder", "data")],
    prevent_initial_call=True
)
def start_jupyter_session(n_clicks, hostname, env_name, dest_folder):
    if not n_clicks or not hostname:
        return no_update, no_update, no_update, no_update, no_update
    
    try:
        # Clear the output buffer before starting
        clear_output_buffer()
        
        # Start the Jupyter session in a separate thread to avoid blocking
        import threading
        
        def run_jupyter():
            connect_and_run_jupyter_with_output(hostname, env_name, dest_folder)
        
        # Start Jupyter session in background
        jupyter_thread = threading.Thread(target=run_jupyter)
        jupyter_thread.daemon = True
        jupyter_thread.start()
        
        # Enable real-time updates and update status
        return True, False, "Starting...", "yellow", True
        
    except Exception as e:
        return False, True, "Error", "red", False

# Real-time terminal output update callback
@callback(
    [Output("terminal-output", "children", allow_duplicate=True),
     Output("jupyter-url-display", "children", allow_duplicate=True),
     Output("status-badge", "children", allow_duplicate=True),
     Output("status-badge", "color", allow_duplicate=True)],
    Input("output-interval", "n_intervals"),
    State("jupyter-process-running", "data"),
    prevent_initial_call=True
)
def update_terminal_output(n_intervals, is_running):
    if not is_running:
        return no_update, no_update, no_update, no_update
    
    # Get the latest output from buffer
    output_buffer = get_output_buffer()
    
    if not output_buffer:
        return no_update, no_update, no_update, no_update
    
    # Convert buffer to terminal display elements
    terminal_elements = []
    jupyter_url = None
    current_status = "Running"
    status_color = "green"
    
    for entry in output_buffer:
        timestamp = entry["timestamp"]
        message = entry["message"]
        msg_type = entry["type"]
        
        # Check for Jupyter URL in messages
        if "http://localhost:" in message and "token=" in message:
            jupyter_url = message.split("http://localhost:")[1].split()[0]
            if not jupyter_url.startswith("http"):
                jupyter_url = "http://localhost:" + jupyter_url
        
        # Determine CSS class based on message type
        css_class = f"terminal-line {msg_type}"
        terminal_elements.append(
            html.Div(f"[{timestamp}] {message}", className=css_class)
        )
    
    # Update URL display if Jupyter URL found
    url_display = no_update
    if jupyter_url:
        url_display = dmc.Group([
            dmc.Text("Jupyter Notebook URL:", fw=500),
            dmc.Anchor(
                jupyter_url,
                href=jupyter_url,
                target="_blank",
                c="blue"
            ),
            dmc.Anchor(
                dmc.Button(
                    "Open in Browser",
                    size="xs",
                    leftSection=DashIconify(icon="mdi:open-in-new", width=16),
                ),
                href=jupyter_url,
                target="_blank"
            )
        ])
        current_status = "Running"
        status_color = "green"
    
    return terminal_elements, url_display, current_status, status_color

# Callback to clear terminal
@callback(
    Output("terminal-output", "children", allow_duplicate=True),
    Input("clear-terminal-btn", "n_clicks"),
    prevent_initial_call=True
)
def clear_terminal(n_clicks):
    if not n_clicks:
        return no_update
    
    clear_output_buffer()
    return [
        html.Div(f"[{time.strftime('%H:%M:%S')}] Terminal cleared", className="terminal-line info"),
    ]

# Callback to handle command sending
@callback(
    [Output("command-input", "value")],
    Input("send-command-btn", "n_clicks"),
    State("command-input", "value"),
    prevent_initial_call=True
)
def send_command(n_clicks, command):
    if not n_clicks or not command:
        return no_update
    
    # Send command to active shell
    success = send_command_to_active_shell(command)
    
    # Clear the input field
    return [""]

# Callback to handle logout
@callback(
    Output("_pages_location", "pathname", allow_duplicate=True),
    Input("logout-btn-notebook", "n_clicks"),
    prevent_initial_call=True
)
def logout_from_notebook(n_clicks):
    if not n_clicks:
        return no_update
    
    disconnect_session()  # Clean up session
    close_ssh_session()   # Close SSH connection
    return "/"

# Callback to handle disconnect and return to servers
@callback(
    Output("_pages_location", "pathname", allow_duplicate=True),
    Input("disconnect-btn", "n_clicks"),
    prevent_initial_call=True
)
def disconnect_and_return(n_clicks):
    if not n_clicks:
        return no_update
    
    disconnect_session()  # Clean up session but keep SSH connection
    return "/servers"

# Clientside callback to handle Enter key in command input
clientside_callback(
    """
    function(n_submit, n_clicks) {
        if (n_submit > 0) {
            return n_clicks + 1;  // Trigger the send button
        }
        return n_clicks;
    }
    """,
    Output("send-command-btn", "n_clicks"),
    Input("command-input", "n_submit"),
    State("send-command-btn", "n_clicks"),
    prevent_initial_call=True
)

# Callback to automatically start Jupyter when page loads
@callback(
    Output("start-jupyter-btn", "n_clicks", allow_duplicate=True),
    Input("page-location-notebook", "pathname"),
    State("start-jupyter-btn", "n_clicks"),
    prevent_initial_call=True
)
def auto_start_jupyter(pathname, current_clicks):
    if pathname == "/notebook":
        # Automatically trigger the start button when page loads
        return (current_clicks or 0) + 1
    return no_update
