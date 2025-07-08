from dash import html, dcc, Output, Input, State, no_update, callback, clientside_callback
import dash
import dash_mantine_components as dmc
from dash_iconify import DashIconify
from session_manager import run_command_with_paramiko, parse_ai_output, close_ssh_session

# Register this page with Dash Pages
dash.register_page(__name__, path="/servers")


caption = dmc.TableCaption("Click a row to select a server.")


layout = html.Div([
    dcc.Location(id="page-location-servers", refresh=False),  # Detect page load
    dcc.Store(id="selected-row-index"),  # Store for selected row index
    # Custom confirmation modal
    dmc.Modal(
        title=dmc.Text("Confirmation Required", className="confirmationTitle"),  # Use dmc.Text with the className
        id="confirm-modal",
        children=[
            dmc.Text(id="confirm-modal-message", className="confirmationText"),  # Message will be dynamically updated
            dmc.Space(h=20),  # Add spacing between the message and buttons
            dmc.Group(
                [
                    dmc.Button("Yes", id="confirm-yes-btn", color="green"),  # Yes button
                    dmc.Button("No", id="confirm-no-btn", color="red"),  # No button
                ],
                justify="flex-end",  # Align buttons to the right
            ),
        ],
        opened=False,  # Modal is initially closed
        size="md",  # Medium size
        centered=True,  # Center the modal on the screen
    ),

    dmc.LoadingOverlay(
        visible=False,
        id="loading-overlay-servers",
        zIndex=10,
        loaderProps={
            "variant": "custom",
            "children": 
            dmc.Box(
                children=[
                    dmc.Text(
                        "Fetching available servers... Please wait, this may take a moment",
                        style={"color": "#01283a", "fontSize": "18px", "marginTop": "20px", "fontWeight": "bold"},
                    ),
                    dmc.Image(
                        h=400,
                        radius="md",
                        src="/assets/loading.gif",
                    )
                ]
            )
        },
        overlayProps={"radius": "md", "blur": "0.3"}
    ),
    dmc.Flex(
        [
            dmc.Button(
                "Logout",
                id="logout-btn",
                variant="outline",
                className="button-logout logout-button",
                fullWidth=True,
                leftSection=DashIconify(icon="material-symbols:logout-rounded"),
            ),
            html.H3("🖥️ Available Servers"),
            dmc.Button(
                "Fetch Servers",
                id="fetch-servers-btn",
                variant="outline",
                className="button-fetch-servers",
                fullWidth=True,
                leftSection=DashIconify(icon="material-symbols:refresh"),
            ),
        ],
        direction={"base": "column", "sm": "row"},
        gap={"base": "sm", "sm": "lg"},
        justify={"sm": "space-between", "base": "center"},
        align="center",
    ),    
    html.Div(
        className="server-table-container",
        children=[
            dmc.Table(
                [
                    dmc.TableThead(
                        dmc.TableTr(
                            [
                                dmc.TableTh(dmc.Group([DashIconify(icon="mdi:server", width=35), "Hostname"])),
                                dmc.TableTh(dmc.Group([DashIconify(icon="mdi:cpu-64-bit", width=15), "Available CPU"])),
                                dmc.TableTh(dmc.Group([DashIconify(icon="mdi:gauge", width=20), "Load"])),
                                dmc.TableTh(dmc.Group([DashIconify(icon="mdi:chip", width=15), "Total CPU"])),
                                dmc.TableTh(dmc.Group([DashIconify(icon="mdi:chip", width=20), "CPU Type"])),
                                dmc.TableTh(dmc.Group([DashIconify(icon="mdi:memory", width=15), "Available RAM (GB)"])),
                                dmc.TableTh(dmc.Group([DashIconify(icon="mdi:memory", width=20), "Total RAM (GB)"])),
                                dmc.TableTh(dmc.Group([DashIconify(icon="mdi:application", width=20), "Program"])),
                                dmc.TableTh(dmc.Group([DashIconify(icon="mdi:gpu", width=20), "GPU"])),
                                dmc.TableTh(dmc.Group([DashIconify(icon="mdi:account", width=20), "User"])),
                            ]
                        )
                    ),
                    dmc.TableTbody(id="server-data-table-body"),  # Body will be dynamically updated
                    caption
                ],
                striped=True,
                highlightOnHover=True,
                withColumnBorders=True,
                withTableBorder=True,
                verticalSpacing="md",
                horizontalSpacing="sm",
                className="server-table"
            )
        ]
    ),
    html.Div(id="jupyter-status", style={"marginTop": "1rem", "fontWeight": "bold"}),
])

# Functions
clientside_callback(
    """
    function updateLoadingState(pathname, n_clicks) {
        if (!pathname || pathname !== "/servers") {
            return false;  // Hide the loading overlay if not on the servers page
        }
        if (n_clicks && n_clicks > 0) {
            return true;  // Show the loading overlay
        }
        return false;  // Hide the loading overlay
    }
    """,
    Output("loading-overlay-servers", "visible", allow_duplicate=True),
    Input("page-location-servers", "pathname"),
    Input("fetch-servers-btn", "n_clicks"),
    prevent_initial_call=True,
)


@callback(
    Output("server-data-table-body", "children", allow_duplicate=True),  # Update the table body
    Output("jupyter-status", "children", allow_duplicate=True),         # Update the status message
    Output("loading-overlay-servers", "visible"),  # Update loading overlay visibility
    Output("server-data", "data", allow_duplicate=True),
    Input("fetch-servers-btn", "n_clicks"),       # Triggered by button click
    Input("page-location-servers", "pathname"),  
    Input("server-data", "data"), 
    prevent_initial_call=True
)
def update_server_table(n_clicks, pathname, server_data): 
    if pathname != "/servers" and (n_clicks is None or n_clicks == 0) and (server_data is None or server_data == []):
        return [], "⚠️ No servers fetched yet.", False, server_data

    # Use the shared SSH session to fetch server data
    try:
        if server_data is None or server_data == [] or (n_clicks is not None and n_clicks > 0):
            # Fetch server data using the 'ai' command
            ai_output = run_command_with_paramiko("ai")
            server_data = parse_ai_output(ai_output)

        if not server_data:
            return [], "⚠️ No servers found.", False, server_data

        # Generate table rows dynamically
        rows = [
            html.Tr(
            [
                html.Td(
                    [
                        DashIconify(icon="mdi:server", width=28, style={"marginRight": "6px", "color": "#0000ee"}),
                        html.Span(server.get("HOST", ""), style={"fontWeight": "bold", "color": "#0000ee"})
                    ]
                ),
                html.Td(server.get("CPU_AVAIL", "")),
                html.Td(server.get("LOAD", "")),
                html.Td(server.get("CPU", "")),
                html.Td(server.get("CPU_TYPE", "")),
                html.Td(server.get("GB_AVAIL", "")),
                html.Td(server.get("GB_TOTAL", "")),
                html.Td(server.get("PROGRAM", "")),
                html.Td(server.get("HAS_GPU", "")),
                html.Td(server.get("USER", "")),
            ],
            id={"type": "row", "index": idx},
            n_clicks=0,
            style={"cursor": "pointer", "backgroundColor": "white"},
        ) for idx, server in enumerate(server_data)
        ]
        return rows, "🟢 Servers fetched successfully.", False, server_data
    except Exception as e:
        print(f"Error fetching server data: {e}")
        return [], f"❌ Error fetching server data: {str(e)}", False, server_data


@callback(
    Output("selected-row-index", "data"),  # Store the selected row index
    Input({"type": "row", "index": dash.ALL}, "n_clicks"),  # Listen for clicks on any row
    prevent_initial_call=True
)
def select_row(n_clicks):
    if not n_clicks or all(click is None for click in n_clicks) or all(click == 0 for click in n_clicks):
        return no_update

    # Use dash.callback_context to find the most recently clicked row
    ctx = dash.callback_context
    if not ctx.triggered:
        return no_update

    # Extract the index of the clicked row from the triggered input
    triggered_id = ctx.triggered[0]["prop_id"].split(".")[0]
    row_index = eval(triggered_id).get("index")  # Extract the "index" from the triggered ID

    return row_index


@callback(
    [Output("confirm-modal", "opened", allow_duplicate=True),  # Open the modal
     Output("confirm-modal-message", "children"),  # Update the modal message
     Output("selected-hostname", "data")],  # Store the selected hostname
    Input("selected-row-index", "data"),  # Triggered by row selection
    State("server-data", "data"),         # Use server data from dcc.Store
    prevent_initial_call=True
)
def on_select_server(selected_index, server_data):
    if selected_index is None or not server_data:
        return False, "⚠️ No server selected.", None

    if selected_index >= len(server_data):
        return False, "⚠️ Invalid selection.", None

    # Extract the hostname from the selected server
    selected_server = server_data[selected_index]
    hostname = selected_server.get("HOST", "Unknown")

    # Show confirmation modal with bold server name
    message = html.Div([
        "Are you sure you wish to run the notebook on the ",
        html.Strong(hostname),  # Render the hostname in bold
        " server?"
    ])
    return True, message, hostname

@callback(
    [
     Output("jupyter-status", "children"),  # Update the Jupyter status message
     Output("confirm-modal", "opened", allow_duplicate=True),
     Output("_pages_location", "pathname", allow_duplicate=True),  # Navigate to notebook page
    ],  # Close the modal
     
    [Input("confirm-yes-btn", "n_clicks"),  # Triggered when the user clicks "Yes"
     Input("confirm-no-btn", "n_clicks")
    ],  # Triggered when the user clicks "No"
    [
     State("selected-hostname", "data"),  # Get the selected hostname
     State("server-data", "data"),
     State("stored-env-name", "data"),  # Retrieve env_name from the store
     State("stored-dest-folder", "data"),  # Retrieve dest_folder from the store
    ],
    prevent_initial_call=True
)
def handle_confirmation(yes_clicks, no_clicks, hostname, server_data, env_name, dest_folder):
    ctx = dash.callback_context

    if not ctx.triggered:
        return no_update, no_update, no_update

    # Determine which button was clicked
    triggered_id = ctx.triggered[0]["prop_id"].split(".")[0]

    if triggered_id == "confirm-no-btn":
        return "⚪ Action canceled.", False, no_update

    if triggered_id == "confirm-yes-btn":
        # Navigate to the notebook page instead of running Jupyter here
        return f"🔄 Navigating to notebook session for {hostname}...", False, "/notebook"

    return no_update, False, no_update

@callback(
    Output("_pages_location", "pathname", allow_duplicate=True),
    Input("logout-btn", "n_clicks"),
    prevent_initial_call=True
)
def logout(n_clicks):
    if n_clicks is None or n_clicks == 0:
        return no_update
    close_ssh_session()  # Close the shared SSH session
    return "/"