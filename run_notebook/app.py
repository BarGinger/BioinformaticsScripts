from dash import Dash, page_container  # Import page_container
from dash import html, dcc
import dash
import dash_mantine_components as dmc
from dash import html, dcc, Input, Output, State, no_update, callback, clientside_callback
from session_manager import close_ssh_session  # Import the function to close SSH session


# Initialize the Dash app
app = Dash(__name__, suppress_callback_exceptions=True, use_pages=True)

# Wrap the app layout with MantineProvider
app.layout = html.Div([
    dcc.Location(id="page-location", refresh=True),  # Track the current URL
    dcc.Store(id="navigation-state", data={"navigated": False}),  # Track navigation state
    dcc.Store(id="stored-env-name"),  # Store for env_name
    dcc.Store(id="stored-dest-folder"),  # Store for dest_folder
    dcc.Store(id="selected-hostname"),  # Store for selected hostname
    html.Div(className="logo-container", children=[
        html.Img(src="/assets/UU_logo.png", className="app-logo"),
    ]),
    html.Div(className="jupyter-logo-container", children=[
        html.Img(src="/assets/Jupyter_logo.png", className="jupyter-logo"),
    ]),
    dcc.Store(id="server-data", data=[]),  # Store to hold parsed server data
    dcc.ConfirmDialog(
        id="error-dialog",
        message="",  # This will be dynamically updated
    ),

    html.Div(className="dash-container", children=[
        html.H2("🚀 Remote Jupyter Notebook Launcher"),
        html.Div([
            dmc.MantineProvider(
                theme={"colorScheme": "light"},  # You can customize the theme here
                children=page_container  # Use dash.page_container for multi-page apps
            )
        ]),
    ]),
]),

@callback(
    [Output("page-location", "pathname", allow_duplicate=True), Output("server-data", "data"), Output("navigation-state", "data")],
    [Input("page-location", "pathname")],
    [State("navigation-state", "data")],
    prevent_initial_call=True
)
def redirect_and_clear_session(pathname, navigation_state):
    # Check if the user has already navigated
    if not navigation_state or not navigation_state.get("navigated"):
        # If the app is refreshed and the pathname is not "/", redirect to login
        if pathname != "/":
            close_ssh_session()
            return "/", [], {"navigated": False}

    # Mark the user as having navigated
    return no_update, no_update, {"navigated": True}

if __name__ == "__main__":
    app.run(debug=True)