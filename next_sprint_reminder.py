import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from notion_client import Client
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# Load environment variables
load_dotenv()
NEXT_SPRINT_NOTION_DATABASE_ID = os.getenv("NEXT_SPRINT_NOTION_DATABASE_ID")
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
OFFICIAL_CHANNEL_ID = os.getenv("OFFICIAL_CHANNEL_ID")

# Slack user rotation (edit as needed)
SLACK_USER_ROTATION = [
    {"name": "Annie Chen", "id": "U03J5M6SXJS"},
    {"name": "Sharon Wu", "id": "U052ED4GV8R"},
    {"name": "Casper Chen", "id": "UH13Z1L06"},
]

# Notion/Slack clients
notion = Client(auth=os.getenv("NOTION_API_KEY"))
slack = WebClient(token=SLACK_BOT_TOKEN)

# Notion property names (edit if your DB uses different names)
MEETING_DATE_PROPERTY = "Meeting Date"
MEETING_LINK_PROPERTY = "Meeting Link"  # If the link is in a property, else use page URL

# Helper: Get this week's meeting doc from Notion
def get_this_week_meeting_doc():
    today = datetime.now().date()
    # Query: Only use Meeting Date <= today, sorted by Meeting Date desc
    try:
        response = notion.databases.query(
            database_id=NEXT_SPRINT_NOTION_DATABASE_ID,
            filter={
                "property": MEETING_DATE_PROPERTY,
                "date": {"on_or_before": today.isoformat()}
            },
            sorts=[{"property": MEETING_DATE_PROPERTY, "direction": "descending"}]
        )
        results = response.get("results", [])
        if not results:
            print("No meeting doc found for this week.")
            return None, None
        page = results[0]
        # Try to get meeting link from property, else use page URL
        props = page["properties"]
        meeting_link = None
        if MEETING_LINK_PROPERTY in props and props[MEETING_LINK_PROPERTY]["type"] == "url":
            meeting_link = props[MEETING_LINK_PROPERTY]["url"]
        if not meeting_link:
            meeting_link = page.get("url")
        title = "Untitled Meeting"
        for prop in props.values():
            if prop["type"] == "title" and prop["title"]:
                title = ''.join([t["plain_text"] for t in prop["title"]])
                break
        return meeting_link, title
    except Exception as e:
        print(f"Error fetching meeting doc: {e}")
        return None, None

# Helper: Get this week's responsible Slack user(s)
def get_this_week_slack_users():
    # Week number since a fixed start (e.g., 2024-01-01)
    start_date = datetime(2024, 1, 1)
    week_idx = ((datetime.now() - start_date).days // 7)
    if week_idx % 2 == 0:
        return [SLACK_USER_ROTATION[0]["id"]]  # Annie (even week)
    else:
        return [SLACK_USER_ROTATION[1]["id"], SLACK_USER_ROTATION[2]["id"]]  # Sharon & Casper (odd week)

# Helper: Get this week's meeting type and users
def get_this_week_meeting_type_and_users():
    # Set the rotation start date to 2024/08/05 (Monday of the first Table & Annie week)
    start_date = datetime(2024, 8, 5)
    week_idx = ((datetime.now() - start_date).days // 7)
    if week_idx % 2 == 0:
        # Table week, tag Annie
        return "Scrum Team pre-planning: Table", [SLACK_USER_ROTATION[0]["id"]]
    else:
        # PV & GAP week, tag Sharon & Casper
        return "Scrum Team pre-planning: PV & GAP", [SLACK_USER_ROTATION[1]["id"], SLACK_USER_ROTATION[2]["id"]]

# Compose and send Slack message
def send_reminder():
    meeting_link, meeting_title = get_this_week_meeting_doc()
    if not meeting_link:
        print("No meeting link to send.")
        return
    meeting_type, user_ids = get_this_week_meeting_type_and_users()
    user_mentions = ' '.join([f"<@{uid}>" for uid in user_ids])
    text = (
        f"{user_mentions} :wave: Just a warm reminder that today we will have *{meeting_type}*.\n"
        f"Please remember to update your *Next Sprint Item*!\n"
        f"This week's meeting document: <{meeting_link}|{meeting_title}>"
    )
    try:
        slack.chat_postMessage(
            channel=OFFICIAL_CHANNEL_ID,
            text=text
        )
        print(f"Sent reminder to Slack: {text}")
    except SlackApiError as e:
        print(f"Slack API error: {e.response['error']}")
    except Exception as e:
        print(f"Unexpected error sending Slack message: {e}")

if __name__ == "__main__":
    send_reminder()