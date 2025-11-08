import requests
import json
import time

# --- Configuration ---
BASE_URL = "https://chatapp-v2-zhgh.onrender.com"  # Adjust if your app runs elsewhere
TOKEN_URL = f"{BASE_URL}/token"
USERS_URL = f"{BASE_URL}/users/"
CHANNELS_URL = f"{BASE_URL}/channels/"
DEFAULT_PASSWORD = "password123"

# --- Test Data ---
users_data = [
    {
        "username": "alice_test",
        "email": "alice@test.com",
        "first_name": "Alice",
        "last_name": "Tester",
        "password": DEFAULT_PASSWORD,
    },
    {
        "username": "bob_test",
        "email": "bob@test.com",
        "first_name": "Bob",
        "last_name": "Check",
        "password": DEFAULT_PASSWORD,
    },
    {
        "username": "charlie_test",
        "email": "charlie@test.com",
        "first_name": "Charlie",
        "last_name": "Debug",
        "password": DEFAULT_PASSWORD,
    },
    {
        "username": "diana_test",
        "email": "diana@test.com",
        "first_name": "Diana",
        "last_name": "Script",
        "password": DEFAULT_PASSWORD,
    },
    {
        "username": "eve_test",
        "email": "eve@test.com",
        "first_name": "Eve",
        "last_name": "Runner",
        "password": DEFAULT_PASSWORD,
    },
]

channels_data = [
    {"name": "General Discussion", "description": "Channel for general chat"},
    {"name": "Project Updates", "description": "Updates related to the project"},
]

# --- Helper Functions ---


def get_token(username, password):
    """Authenticates a user and returns the access token."""
    try:
        response = requests.post(
            TOKEN_URL,
            data={"username": username, "password": password},  # Send as form data
        )
        response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)
        return response.json().get("access_token")
    except requests.exceptions.RequestException as e:
        print(f"Error getting token for {username}: {e}")
        if hasattr(e, "response") and e.response is not None:
            try:
                print(f"Response body: {e.response.json()}")
            except json.JSONDecodeError:
                print(f"Response body: {e.response.text}")
        return None


def make_authenticated_request(method, url, token, **kwargs):
    """Makes an authenticated request with the Bearer token."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",  # Assume JSON for most POST/PATCH
        "Accept": "application/json",
    }
    try:
        response = requests.request(method, url, headers=headers, **kwargs)
        response.raise_for_status()
        # Handle 204 No Content specifically for DELETE/leave
        if response.status_code == 204:
            return None  # Success, but no body
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error during {method} {url}: {e}")
        if hasattr(e, "response") and e.response is not None:
            # Special handling for Conflict (e.g., already joined)
            if e.response.status_code == 409:
                print(
                    f"  -> Note: Received 409 Conflict (maybe already exists/joined?) - {e.response.json().get('detail', e.response.text)}"
                )
                return {"status": "conflict"}  # Indicate conflict rather than failure
            try:
                print(f"Response body: {e.response.json()}")
            except json.JSONDecodeError:
                print(f"Response body: {e.response.text}")
        return None


# --- Main Script ---

created_user_ids = []
created_channel_ids = []
user_credentials = {}  # Store credentials for later authentication

print("--- 1. Creating Users ---")
for user_info in users_data:
    try:
        response = requests.post(USERS_URL, json=user_info)
        response.raise_for_status()
        created_user = response.json()
        user_id = created_user.get("id")
        username = user_info["username"]
        if user_id:
            print(f"User '{username}' created successfully with ID: {user_id}")
            created_user_ids.append(user_id)
            user_credentials[username] = user_info["password"]
        else:
            print(f"Error: User '{username}' created but no ID returned.")
    except requests.exceptions.RequestException as e:
        print(f"Error creating user '{user_info.get('username', 'N/A')}': {e}")
        if hasattr(e, "response") and e.response is not None:
            try:
                print(f"Response body: {e.response.json()}")
            except json.JSONDecodeError:
                print(f"Response body: {e.response.text}")
    time.sleep(0.1)  # Small delay between requests

if not created_user_ids:
    print("\nNo users were created. Aborting channel creation and joining.")
    exit()

print("\n--- 2. Authenticating First User to Create Channels ---")
# Use the first created user to create channels
creator_username = users_data[0]["username"]
creator_password = user_credentials.get(creator_username)
creator_token = None

if creator_password:
    creator_token = get_token(creator_username, creator_password)
else:
    print(f"Could not find credentials for the first user '{creator_username}'.")

if not creator_token:
    print(
        "Failed to authenticate channel creator. Aborting channel creation and joining."
    )
    exit()

print(f"Authenticated '{creator_username}' successfully.")

print("\n--- 3. Creating Channels ---")
for channel_info in channels_data:
    print(f"Creating channel '{channel_info['name']}'...")
    response_data = make_authenticated_request(
        "POST", CHANNELS_URL, creator_token, json=channel_info
    )
    if response_data and "id" in response_data:
        channel_id = response_data["id"]
        print(
            f"Channel '{channel_info['name']}' created successfully with ID: {channel_id}"
        )
        created_channel_ids.append(channel_id)
    else:
        print(f"Failed to create channel '{channel_info['name']}'.")
    time.sleep(0.1)  # Small delay

if not created_channel_ids:
    print("\nNo channels were created. Aborting joining process.")
    exit()

print("\n--- 4. Adding Users to Channels ---")
for username, password in user_credentials.items():
    print(f"\nProcessing user '{username}'...")
    user_token = get_token(username, password)
    if not user_token:
        print(
            f"  Skipping channel joins for '{username}' due to authentication failure."
        )
        continue

    print(f"  Authenticated '{username}'.")
    for channel_id in created_channel_ids:
        channel_join_url = f"{CHANNELS_URL}{channel_id}/join"
        print(f"  Attempting to join channel ID {channel_id}...")
        response_data = make_authenticated_request("POST", channel_join_url, user_token)
        if response_data and response_data.get("status") == "conflict":
            print(
                f"  User '{username}' was already a member of channel {channel_id} (or owner)."
            )
        elif response_data:
            print(f"  User '{username}' successfully joined channel {channel_id}.")
        else:
            print(f"  Failed to join channel {channel_id} for user '{username}'.")
        time.sleep(0.1)  # Small delay

print("\n--- Data Population Script Finished ---")
