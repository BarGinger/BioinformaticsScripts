from dash import html, dcc, Input, Output, State, no_update, callback, clientside_callback
import dash_mantine_components as dmc
from dash_iconify import DashIconify
import json
from pathlib import Path
import paramiko
import dash
import time
import dash_bootstrap_components as dbc
from session_manager import establish_ssh_session, run_command_with_paramiko, parse_ai_output


# Register this page with Dash Pages
dash.register_page(__name__, path="/")

CONFIG_FILE = Path("notebook_launcher_config.json")

def load_config():
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {}

def save_config(data):
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f)

layout = dmc.Box(
    children=[      
        dmc.Stack(
            pos="relative",
            align="streach",
            justify="center",
            p=2,
            w=800,
            children=[
                dmc.LoadingOverlay(
                    visible=False,
                    id="loading-overlay",
                    zIndex=10,
                    loaderProps={
                        "variant": "custom",
                        "children": 
                        dmc.Box(
                            children=[
                                dmc.Text(
                                    "Logging in and fetching available servers... Please wait, this may take a moment",
                                    style={"color": "#01283a", "fontSize": "18px", "marginTop": "20px", "fontWeight": "bold"},
                                ),
                                dmc.Image(
                                    h=200,
                                    radius="md",
                                    src="/assets/custom_loadingoverlay.gif",
                                )
                            ]
                        )
                    },
                    overlayProps={"radius": "md", "blur": 0.3}
                ),
                html.Div(className="form-group", children=[
                    html.Label(["Username ", html.Span("*", className="required-field")], htmlFor="username"),
                    dmc.TextInput(
                        id="username",
                        placeholder="Enter your SSH username",
                        leftSection=DashIconify(icon="radix-icons:person"),       
                        className="textInput",                 
                        value=load_config().get("username", ""),
                    ),
                ]),
                html.Div(className="form-group", children=[
                    html.Label([
                        "Gateway Host ",
                        html.Span("*", className="required-field")
                    ], htmlFor="gateway"),
                    dmc.TextInput(
                        id="gateway",
                        placeholder="e.g., alive.bio.uu.nl",
                        leftSection=DashIconify(icon="solar:server-square-cloud-bold"),    
                        className="textInput",                    
                        value=load_config().get("gateway", "alive.bio.uu.nl"),
                    ),
                ]),
                html.Div(className="form-group", children=[
                    html.Label([
                        "Destination Folder ",
                        html.Span("*", className="required-field")
                    ], htmlFor="dest_folder"),
                    dmc.TextInput(
                        id="dest_folder",
                        placeholder="Specify the folder on the server (e.g., Projects)",
                        leftSection=DashIconify(icon="solar:folder-bold-duotone"),
                        className="textInput",
                        value=load_config().get("dest_folder", ""),
                    ),
                ]),
                html.Div(className="form-group", children=[
                    html.Label("Conda Environment", htmlFor="env_name"),
                    dmc.TextInput(
                        placeholder="Specify Anaconda environment (optional)",
                        leftSection=DashIconify(icon="simple-icons:anaconda"),
                        id="env_name",
                        className="textInput",
                        value=load_config().get("env_name", "bio"),
                    ),
                ]),
                dmc.Checkbox(
                    label="Remember these settings",
                    id="remember_check",
                    checked=bool(load_config()),  # Dynamically set based on whether load_config() returns data,
                    className="custom-checkbox"
                ),
                html.Div(className="button-container", children=[
                    dmc.Button(
                        "Connect & Search for available servers",
                        id="launch_btn",
                        variant="outline",
                        className="button",
                        fullWidth=True,
                        leftSection=DashIconify(icon="material-symbols:login-rounded"),
                    ),
                ]),
            ],
        ),
    ]
)

## Functions
clientside_callback(
    """
    function updateLoadingState(n_clicks) {
        if (n_clicks > 0) {
            return true;  // Show the loading overlay
        }
        return false;  // Hide the loading overlay
    }
    """,
    Output("loading-overlay", "visible", allow_duplicate=True),
    Input("launch_btn", "n_clicks"),
    prevent_initial_call=True,
)



@callback(
    Output("server-data", "data", allow_duplicate=True),  # Store server data in dcc.Store
    Output("error-dialog", "displayed"),
    Output("error-dialog", "message"),
    Output("_pages_location", "pathname", allow_duplicate=True),
    Output("loading-overlay", "visible"),
    Output("stored-env-name", "data"),  # Store env_name
    Output("stored-dest-folder", "data"),  # Store dest_folder
    Input("launch_btn", "n_clicks"),
    State("username", "value"),
    State("gateway", "value"),
    State("env_name", "value"),
    State("dest_folder", "value"),
    State("remember_check", "checked"),
    prevent_initial_call=True,
)
def handle_login(n_clicks, username, gateway, env_name, dest_folder, remember):
    if n_clicks == 0 or n_clicks is None:
        return no_update, False, "", no_update, False, no_update, no_update

    if not username or not gateway or not dest_folder:
        return no_update, True, "All fields are required.", no_update, False, no_update, no_update  

    if remember:
        save_config({
            "username": username,
            "gateway": gateway,
            "env_name": env_name,
            "dest_folder": dest_folder
        })

    try:
        # Establish SSH session
        establish_ssh_session(username, gateway)

        # Fetch server data
        ai_output = run_command_with_paramiko("ai", load_config=load_config)
        servers = parse_ai_output(ai_output)

        if not servers:
            return [], True, "No servers found.", no_update, False, no_update, no_update

        # Store server data and navigate to /servers
        return servers, False, "", "/servers", False, env_name, dest_folder

    except Exception as e:
        return no_update, True, f"An error occurred: {str(e)}", no_update, False, no_update, no_update