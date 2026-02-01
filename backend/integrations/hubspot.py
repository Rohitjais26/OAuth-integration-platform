import json
import secrets
from fastapi import Request, HTTPException
from fastapi.responses import HTMLResponse
import httpx
import asyncio
import requests

from urllib.parse import unquote_plus

from integrations.integration_item import IntegrationItem
from redis_client import add_key_value_redis, get_value_redis, delete_key_redis

# === HubSpot oauth config ===
CLIENT_ID = "a5e647fe-f024-45c8-8fb7-5a63f211e74b"
CLIENT_SECRET = "9ae41831-05e6-42df-ab0c-849dbde05a8f"

REDIRECT_URI = "http://localhost:8000/integrations/hubspot/oauth2callback"

AUTH_BASE_URL = "https://app.hubspot.com/oauth/authorize"
TOKEN_URL = "https://api.hubspot.com/oauth/v1/token"

# Same idea as notion.py
authorization_url = (
    f"{AUTH_BASE_URL}"
    f"?client_id={CLIENT_ID}"
    f"&response_type=code"
    f"&redirect_uri=http%3A%2F%2Flocalhost%3A8000%2Fintegrations%2Fhubspot%2Foauth2callback"
    f"&scope=crm.objects.contacts.read%20crm.objects.companies.read"
)


async def authorize_hubspot(user_id, org_id):
    state_data = {
        "state": secrets.token_urlsafe(32),
        "user_id": user_id,
        "org_id": org_id,
    }
    encoded_state = json.dumps(state_data)

    # store state for later verification
    await add_key_value_redis(
        f"hubspot_state:{org_id}:{user_id}",
        encoded_state,
        expire=600,
    )

    return f"{authorization_url}&state={encoded_state}"


async def oauth2callback_hubspot(request: Request):
    if request.query_params.get("error"):
        raise HTTPException(
            status_code=400,
            detail=request.query_params.get("error"),
        )

    code = request.query_params.get("code")
    raw_state = request.query_params.get("state")

    if not code or not raw_state:
        raise HTTPException(status_code=400, detail="Missing code or state.")

    try:
        decoded_state = unquote_plus(raw_state)
        state_data = json.loads(decoded_state)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid state")

    original_state = state_data.get("state")
    user_id = state_data.get("user_id")
    org_id = state_data.get("org_id")

    saved_state = await get_value_redis(f"hubspot_state:{org_id}:{user_id}")
    if not saved_state or original_state != json.loads(saved_state).get("state"):
        raise HTTPException(status_code=400, detail="State does not match.")

    # Exchange code -> token
    async with httpx.AsyncClient() as client:
        response, _ = await asyncio.gather(
            client.post(
                TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": REDIRECT_URI,
                    "client_id": CLIENT_ID,
                    "client_secret": CLIENT_SECRET,
                },
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            ),
            delete_key_redis(f"hubspot_state:{org_id}:{user_id}"),
        )

    if response.status_code != 200:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to get HubSpot token: {response.text}",
        )

    # just like notion
    await add_key_value_redis(
        f"hubspot_credentials:{org_id}:{user_id}",
        json.dumps(response.json()),
        expire=600,
    )

    close_window_script = """
    <html>
        <script>
            window.close();
        </script>
    </html>
    """
    return HTMLResponse(content=close_window_script)



async def get_hubspot_credentials(user_id, org_id):
    credentials = await get_value_redis(f"hubspot_credentials:{org_id}:{user_id}")
    if not credentials:
        raise HTTPException(status_code=400, detail="No credentials found.")
    credentials = json.loads(credentials)
    if not credentials:
        raise HTTPException(status_code=400, detail="No credentials found.")
    await delete_key_redis(f"hubspot_credentials:{org_id}:{user_id}")

    return credentials


def make_integration_item_from_contact(contact: dict) -> IntegrationItem:
    contact_id = contact.get("id")
    props = contact.get("properties", {}) or {}

    email = props.get("email")
    first_name = props.get("firstname") or ""
    last_name = props.get("lastname") or ""
    base_name = f"{first_name} {last_name}".strip() or email or contact_id

    name = f"contact {base_name}"

    creation_time = contact.get("createdAt")
    last_modified_time = contact.get("updatedAt")

    return IntegrationItem(
        id=contact_id,
        type="contact",
        name=name,
        creation_time=creation_time,
        last_modified_time=last_modified_time,
        parent_id=None,
    )


async def get_items_hubspot(credentials) -> list[IntegrationItem]:
    credentials = json.loads(credentials)
    access_token = credentials.get("access_token")

    if not access_token:
        raise HTTPException(
            status_code=400,
            detail="Missing access_token in credentials.",
        )

    response = requests.get(
        "https://api.hubspot.com/crm/v3/objects/contacts",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        params={
            "limit": 50,
            "properties": "firstname,lastname,email",
        },
    )

    list_of_integration_items: list[IntegrationItem] = []

    if response.status_code == 200:
        results = response.json().get("results", [])
        for contact in results:
            list_of_integration_items.append(
                make_integration_item_from_contact(contact)
            )

        #print the list to the console
        print(list_of_integration_items)

    return list_of_integration_items
