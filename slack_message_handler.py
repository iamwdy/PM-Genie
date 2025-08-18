import os
import json
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from datetime import datetime
from flask import Flask, request, jsonify
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from notion_client import Client
from dotenv import load_dotenv

def http_request(url, method='GET', headers=None, data=None):
    """Helper function to make HTTP requests using urllib"""
    if headers is None:
        headers = {}
    
    req = Request(url, method=method, headers=headers)
    if data:
        if isinstance(data, dict):
            data = json.dumps(data).encode('utf-8')
        req.data = data
    
    try:
        with urlopen(req) as response:
            return {
                'status_code': response.status,
                'text': response.read().decode('utf-8'),
                'json': lambda: json.loads(response.read().decode('utf-8'))
            }
    except HTTPError as e:
        return {'status_code': e.code, 'text': e.read().decode('utf-8')}
    except URLError as e:
        return {'status_code': 500, 'text': str(e)}

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Slack configuration
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET")
SLACK_CHANNEL_ID = os.getenv("SLACK_CHANNEL_ID")  # The channel to monitor
PM_NOTIFICATION_CHANNEL_ID = os.getenv("PM_NOTIFICATION_CHANNEL_ID")  # Channel to notify PM team
TARGET_EMOJI = "pmgenie"  # The emoji that triggers the bot (use :pmgenie: in Slack)
BUSINESS_REQUEST_EMOJI = "business_request"  # Alternative emoji (use :business_request: in Slack)
PM_TEAM_USER_IDS = [
    "U08UUNJ86P7",  # Wendy Wang
    "U052ED4GV8R",  # Sharon Wu
    "U03J5M6SXJS",  # Annie Chen
    "UH13Z1L06",    # Casper Chen
]

# Notion configuration
NOTION_API_KEY = os.getenv("NOTION_API_KEY")
NOTION_DATABASE_ID = os.getenv("SALES_DATABASE_ID")  # The database to create pages in
NOTION_TAG_PROPERTY = "Tag"  # Property name for the tag
NOTION_TAG_VALUE = "2025 H2 Assessing"  # The tag value to set
NOTION_THREAD_LINK_PROPERTY = "Thread Link"  # Property name for the thread link

# Initialize clients
slack_client = WebClient(token=SLACK_BOT_TOKEN)
notion_client = Client(auth=NOTION_API_KEY)

# Track processed messages to prevent duplicates
processed_messages = set()  # Store message timestamps that have been processed

@app.route('/slack/events', methods=['POST'])
def slack_events():
    """Handle Slack events"""
    try:
        data = request.get_json()
        
        # Debug: Log the event type
        print(f"📥 Received Slack event: {data.get('type') if data else 'No data'}")
        
        # Handle URL verification challenge (this is what Slack sends first)
        if data and data.get('type') == 'url_verification':
            challenge = data.get('challenge')
            print(f"✅ URL verification challenge received: {challenge}")
            return jsonify({'challenge': challenge})
        
        # Handle events
        if data and data.get('type') == 'event_callback':
            event = data.get('event', {})
            print(f"📨 Event type: {event.get('type')}")
            
            # Handle reaction added event
            if event.get('type') == 'reaction_added':
                print("⚡ Processing reaction_added event")
                handle_reaction_added(event)
        
        return jsonify({'status': 'ok'})
        
    except Exception as e:
        print(f"❌ Error in slack_events: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

def handle_reaction_added(event):
    """Handle when a reaction is added to a message"""
    try:
        print(f"Handling reaction: {event.get('reaction')}")
        print(f"Target emoji: {TARGET_EMOJI}")
        
        # Check if it's one of the target emojis
        reaction_emoji = event.get('reaction')
        if reaction_emoji not in [TARGET_EMOJI, BUSINESS_REQUEST_EMOJI]:
            print(f"Emoji mismatch: got '{reaction_emoji}', expected one of {[TARGET_EMOJI, BUSINESS_REQUEST_EMOJI]}")
            return
        
        print("Emoji check passed")
        
        # Check if it's in the target channel
        channel_id = event.get('item', {}).get('channel')
        print(f"Channel ID: {channel_id}")
        print(f"Target channel: {SLACK_CHANNEL_ID}")
        
        if channel_id != SLACK_CHANNEL_ID:
            print(f"Channel mismatch: got '{channel_id}', expected '{SLACK_CHANNEL_ID}'")
            return
        
        print("Channel check passed")
        
        # Check if the user is from PM team
        user_id = event.get('user')
        print(f"User ID: {user_id}")
        print(f"PM team members: {PM_TEAM_USER_IDS}")
        
        # if user_id not in PM_TEAM_USER_IDS:
        #     print(f"User not in PM team: {user_id}")
        #     return
        
        print("User check passed - processing reaction")
        
        # Get message details
        item = event.get('item', {})
        message_ts = item.get('ts')
        
        # Check if we've already processed this message
        if message_ts in processed_messages:
            print(f"⚠️  Message {message_ts} already processed, skipping to prevent duplicates")
            return
        
        # Add to processed messages set
        processed_messages.add(message_ts)
        print(f"📝 Added message {message_ts} to processed list")
        
        # Get the original message
        message_info = get_slack_message(channel_id, message_ts)
        if not message_info:
            print("Failed to get message info")
            processed_messages.discard(message_ts)  # Remove from processed set
            return
        
        # Check if the message is from the bot itself (prevent self-reactions)
        bot_user_id = None
        try:
            auth_response = slack_client.auth_test()
            if auth_response['ok']:
                bot_user_id = auth_response['user_id']
        except Exception as e:
            print(f"Warning: Could not get bot user ID: {e}")
        
        if bot_user_id and message_info.get('user_id') == bot_user_id:
            print(f"🤖 Skipping reaction to bot's own message from {bot_user_id}")
            processed_messages.discard(message_ts)  # Remove from processed set
            return
        
        print(f"Got message info: {message_info}")
        
        # Reply to the sales user
        reply_to_sales(channel_id, message_ts, message_info['user_id'])
        
        # Create Notion page
        notion_page_url = create_notion_page(message_info, channel_id, message_ts)
        
        # Notify PM team in their channel
        if notion_page_url:
            notify_pm_team(message_info, notion_page_url, channel_id, message_ts)
        
        print(f"✅ Successfully processed {reaction_emoji} reaction from {user_id} on message {message_ts}")
        print(f"📊 Total processed messages: {len(processed_messages)}")
        
    except Exception as e:
        print(f"Error handling reaction: {e}")
        # Remove from processed set if there was an error, so it can be retried
        if 'message_ts' in locals():
            processed_messages.discard(message_ts)
            print(f"🔄 Removed {message_ts} from processed list due to error")

def get_slack_message(channel_id, message_ts):
    """Get the original message details"""
    try:
        response = http_request(
            f"https://slack.com/api/conversations.history?channel={channel_id}&latest={message_ts}&limit=1&inclusive=true",
            headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"}
        )
        message_data = json.loads(response['text'])
        
        if not message_data.get('ok') or not message_data.get('messages'):
            print(f"Error getting message: {message_data.get('error', 'Unknown error')}")
            return None
            
        message = message_data['messages'][0]
        
        # Check if message has user field
        if 'user' not in message:
            print(f"Message does not have a 'user' field: {message}")
            return None
        
        # Get user info
        user_response = http_request(
            f"https://slack.com/api/users.info?user={message['user']}",
            headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"}
        )
        user_data = json.loads(user_response['text'])
        
        if not user_data.get('ok'):
            print(f"Error getting user info: {user_data.get('error', 'Unknown error')}")
            return None
            
        return {
            'text': message.get('text', ''),
            'user_id': message.get('user', 'unknown_user'),
            'user_name': user_data.get('user', {}).get('real_name', 'Unknown User'),
            'user_email': user_data.get('user', {}).get('profile', {}).get('email', 'unknown@email.com'),
            'timestamp': message['ts'],
            'thread_ts': message.get('thread_ts', message['ts']),
            'channel_id': channel_id
        }
        
    except Exception as e:
        print(f"Error getting message: {e}")
        return None

def reply_to_sales(channel_id, message_ts, user_id):
    """Reply to the sales user in the original channel"""
    try:
        reply_text = f"Hi <@{user_id}>, we received your message and your request is scheduled for assessment now."
        
        response = http_request(
            "https://slack.com/api/chat.postMessage",
            method='POST',
            headers={
                "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
                "Content-Type": "application/json"
            },
            data={
                "channel": channel_id,
                "thread_ts": message_ts,
                "text": reply_text
            }
        )
        
        if response['status_code'] == 200:
            print(f"✅ Replied to sales user in message {message_ts}")
        else:
            print(f"❌ Error replying to sales user: {response.get('text')}")
            
    except Exception as e:
        print(f"Error replying to sales user: {e}")

def notify_pm_team(message_info, notion_page_url, original_channel_id, message_ts):
    """Send notification to PM team channel about new request"""
    try:
        # Get the original user's display name
        user_id = message_info.get('user_id', '')
        display_name = user_id
        
        try:
            user_info = slack_client.users_info(user=user_id)
            if user_info['ok']:
                user_profile = user_info['user']['profile']
                if user_profile.get('real_name'):
                    display_name = user_profile['real_name']
                elif user_profile.get('display_name'):
                    display_name = user_profile['display_name']
                else:
                    display_name = user_info['user']['name']
        except Exception:
            pass
        
        # Create thread link to original message
        thread_link = f"https://slack.com/app_redirect?channel={original_channel_id}&message_ts={message_ts}"
        
        # Create notification message
        notification_text = (
            f"🔔 *New Business Request Added*\n\n"
            f"*Requested by:* {display_name}\n\n"
            f"📋 *Assessment Page:* {notion_page_url}\n"
            f"🔗 *Original Message:* <{thread_link}|View in Slack>\n\n"
            f"<@U08UUNJ86P7> FYI - new business request added for assessment"
        )
        
        response = http_request(
            "https://slack.com/api/chat.postMessage",
            method='POST',
            headers={
                "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
                "Content-Type": "application/json"
            },
            data={
                "channel": PM_NOTIFICATION_CHANNEL_ID,
                "text": notification_text,
                "unfurl_links": False
            }
        )
        
        if response['status_code'] == 200:
            print(f"✅ Notified PM team in channel {PM_NOTIFICATION_CHANNEL_ID}")
        else:
            print(f"❌ Error notifying PM team: {response.get('text')}")
            
    except Exception as e:
        print(f"Error notifying PM team: {e}")

def create_notion_page(message_info, channel_id, message_ts):
    """Create a new page in Notion database"""
    try:
        # Create thread link - improved format for better accessibility
        workspace_url = "https://app.slack.com/client"  # You may want to make this configurable
        thread_link = f"https://slack.com/app_redirect?channel={channel_id}&message_ts={message_ts}"
        
        # Alternative direct link format (uncomment if preferred):
        # thread_link = f"{workspace_url}/T{channel_id[1:]}/{channel_id}/p{message_ts.replace('.', '')}"
        
        # Get user's actual name from Slack
        user_id = message_info.get('user_id', '')
        user_name = user_id  # Default to user_id if we can't get the name
        display_name = user_name  # What we'll show in Notion
        
        try:
            user_info = slack_client.users_info(user=user_id)
            if user_info['ok']:
                user_profile = user_info['user']['profile']
                # Try to get real name first, then display name, then username
                if user_profile.get('real_name'):
                    display_name = user_profile['real_name']
                elif user_profile.get('display_name'):
                    display_name = user_profile['display_name']
                else:
                    display_name = user_info['user']['name']  # Fallback to username
        except Exception as e:
            print(f"Error getting user info: {e}")
        
        # Prepare Notion page properties
        properties = {
            "Name": {
                "title": [
                    {
                        "text": {
                            "content": f"Business Request - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
                        }
                    }
                ]
            },
            NOTION_TAG_PROPERTY: {
                "select": {
                    "name": NOTION_TAG_VALUE
                }
            },
            NOTION_THREAD_LINK_PROPERTY: {
                "url": thread_link
            },
            "Requested By": {
                "rich_text": [
                    {
                        "text": {
                            "content": display_name
                        }
                    }
                ]
            },
            "Date of proposed": {
                "date": {
                    "start": datetime.now().strftime('%Y-%m-%d')
                }
            }
        }
        
        # Prepare page content with the original message
        message_text = message_info.get('text', 'No message content available')
        page_content = [
            {
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {
                                "content": "📩 Original Business Request"
                            }
                        }
                    ]
                }
            },
            {
                "object": "block",
                "type": "quote",
                "quote": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {
                                "content": message_text
                            }
                        }
                    ]
                }
            },
            {
                "object": "block",
                "type": "heading_3",
                "heading_3": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {
                                "content": "📋 Assessment Notes"
                            }
                        }
                    ]
                }
            },
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {
                                "content": "Please add your assessment notes here..."
                            }
                        }
                    ]
                }
            },
            {
                "object": "block",
                "type": "divider",
                "divider": {}
            },
            {
                "object": "block",
                "type": "heading_3",
                "heading_3": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {
                                "content": "🔗 Slack Thread Link"
                            }
                        }
                    ]
                }
            },
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {
                                "content": "Click here to view the original Slack conversation: "
                            }
                        },
                        {
                            "type": "text",
                            "text": {
                                "content": "Slack Thread",
                                "link": {
                                    "url": thread_link
                                }
                            }
                        }
                    ]
                }
            }
        ]
        
        # Create the page in SALES_DATABASE_ID
        sales_database_id = os.getenv("SALES_DATABASE_ID")
        new_page = notion_client.pages.create(
            parent={"database_id": sales_database_id},
            properties=properties,
            children=page_content
        )
        
        page_url = new_page.get('url', 'No URL available')
        print(f"✅ Created Notion page: {new_page['id']}")
        print(f"🔗 Page URL: {page_url}")
        
        # Note: Notion page link is only sent to PM team, not in the original thread
        return page_url
        
    except Exception as e:
        print(f"Error creating Notion page: {e}")
        return None

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()})

@app.route('/slack/events', methods=['GET'])
def slack_events_test():
    """Test endpoint for Slack webhook URL"""
    return jsonify({
        'status': 'webhook_ready', 
        'message': 'Slack webhook endpoint is accessible',
        'timestamp': datetime.now().isoformat()
    })

@app.route('/', methods=['GET'])
def index():
    """Root endpoint for platform health checks"""
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    # Check required environment variables
    required_vars = [
        'SLACK_BOT_TOKEN', 'SLACK_SIGNING_SECRET', 'SLACK_CHANNEL_ID',
        'NOTION_API_KEY', 'SALES_DATABASE_ID', 'PM_NOTIFICATION_CHANNEL_ID'
    ]
    
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    if missing_vars:
        print(f"Error: Missing environment variables: {missing_vars}")
        exit(1)
    
    print("🚀 Slack message handler started")
    print(f"📺 Monitoring channel: {SLACK_CHANNEL_ID}")
    app.run(host='0.0.0.0', port=3000, debug=True)
    print(f"📢 PM notification channel: {PM_NOTIFICATION_CHANNEL_ID}")
    print(f"😀 Target emojis: {TARGET_EMOJI}, {BUSINESS_REQUEST_EMOJI}")
    print(f"👥 PM team members: {PM_TEAM_USER_IDS}")
    print(f"📊 Notion database: {NOTION_DATABASE_ID}")
    print(f"🏷️  Default tag: {NOTION_TAG_VALUE}")