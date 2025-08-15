import os
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from notion_client import Client
from slack_sdk.signature import SignatureVerifier
from slack_sdk.errors import SlackApiError
from slack_sdk import WebClient
import json
import sys
from datetime import datetime

# Load environment variables from .env file
load_dotenv()

# --- Configuration ---
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
NOTION_API_KEY = os.getenv("NOTION_API_KEY")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
SALES_DATABASE_ID = os.getenv("SALES_DATABASE_ID") # For sales requests from reactions
OFFICIAL_CHANNEL_ID = os.getenv("OFFICIAL_CHANNEL_ID")
SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET")

# Define the emoji that triggers task creation from a reaction
TRIGGER_EMOJI = "white_check_mark"

# Initialize Flask app
app = Flask(__name__)

# Initialize Notion client
notion_client = Client(auth=NOTION_API_KEY)

# Initialize Slack WebClient for sending responses and fetching message details
slack_web_client = WebClient(token=SLACK_BOT_TOKEN)

# Initialize Slack Signature Verifier
signature_verifier = SignatureVerifier(SLACK_SIGNING_SECRET)

# --- Manual Slack User ID Mapping (from your previous script) ---
SLACK_USER_MAPPING = {
    "Wendy Wang": "U08UUNJ86P7",
    "Sharon Wu": "U052ED4GV8R",
    "Annie Chen": "U03J5M6SXJS",
    "Casper Chen": "UH13Z1L06",
}
# --- End Manual Slack User ID Mapping ---

def get_notion_person_id_from_slack_input(slack_user_id=None, input_email_or_name=None):
    """
    Attempts to get a Notion person object for assignment.
    """
    if slack_user_id:
        try:
            user_info = slack_web_client.users_info(user=slack_user_id)
            if user_info["ok"] and user_info["user"] and user_info["user"].get("profile") and user_info["user"]["profile"].get("email"):
                return {"email": user_info["user"]["profile"]["email"]}
        except SlackApiError as e:
            app.logger.warning(f"Slack API error fetching user info for {slack_user_id}: {e.response['error']}")
    
    if input_email_or_name:
        if "@" in input_email_or_name:
            return {"email": input_email_or_name}
        else:
            app.logger.warning(f"Cannot directly assign Notion PIC by name: '{input_email_or_name}'. Requires Notion user ID lookup.")
            return None
    
    return None

@app.route("/slack/events", methods=["POST"])
def slack_events():
    """
    Handles incoming Slack events (slash commands and reaction added events).
    """
    if not signature_verifier.is_valid_request(request.get_data(), request.headers):
        app.logger.warning("Invalid Slack request signature.")
        return "Invalid request signature", 403

    if request.json and 'challenge' in request.json:
        return jsonify({'challenge': request.json['challenge']})

    event_payload = request.json
    event_type = event_payload.get("event", {}).get("type")
    
    app.logger.info(f"Received Slack event: {event_type}")

    # Handle the slash command for creating a task
    if request.form and request.form.get("command") == "/create-notion-task":
        payload = request.form.to_dict()
        trigger_id = payload.get("trigger_id")
        user_id = payload.get("user_id")

        modal = {
            "type": "modal",
            "callback_id": "create_notion_task_modal",
            "title": {"type": "plain_text", "text": "Create New Task"},
            "submit": {"type": "plain_text", "text": "Create"},
            "close": {"type": "plain_text", "text": "Cancel"},
            "blocks": [
                {
                    "type": "input",
                    "block_id": "task_name_block",
                    "label": {"type": "plain_text", "text": "Task Name (Required)"},
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "task_name_input",
                        "placeholder": {"type": "plain_text", "text": "e.g., Implement new feature X"}
                    },
                    "optional": False
                },
                {
                    "type": "input",
                    "block_id": "pic_block",
                    "label": {"type": "plain_text", "text": "Assigned PIC (Email or Full Name - Required)"},
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "pic_input",
                        "placeholder": {"type": "plain_text", "text": "e.g., annie.chen@example.com or Annie Chen"},
                        "initial_value": payload.get("user_name", "")
                    },
                    "optional": False
                },
                {
                    "type": "input",
                    "block_id": "ddl_block",
                    "label": {"type": "plain_text", "text": "Due Date (DDL - Required)"},
                    "element": {
                        "type": "datepicker",
                        "action_id": "ddl_datepicker",
                        "placeholder": {"type": "plain_text", "text": "Select a date"}
                    },
                    "optional": False
                },
                {
                    "type": "input",
                    "block_id": "priority_block",
                    "label": {"type": "plain_text", "text": "Priority (Required)"},
                    "element": {
                        "type": "static_select",
                        "action_id": "priority_select",
                        "placeholder": {"type": "plain_text", "text": "Select a priority"},
                        "options": [
                            {"text": {"type": "plain_text", "text": "High"}, "value": "High"},
                            {"text": {"type": "plain_text", "text": "Medium"}, "value": "Medium"},
                            {"text": {"type": "plain_text", "text": "Low"}, "value": "Low"}
                        ]
                    },
                    "optional": False
                },
                {
                    "type": "input",
                    "block_id": "tags_block",
                    "label": {"type": "plain_text", "text": "Tags"},
                    "element": {
                        "type": "static_select",
                        "action_id": "tags_select",
                        "placeholder": {"type": "plain_text", "text": "Select a tag"},
                        "options": [
                            {"text": {"type": "plain_text", "text": "2025 H2 Assessing"}, "value": "2025 H2 Assessing"},
                            {"text": {"type": "plain_text", "text": "2025 H2 Deprioritize"}, "value": "2025 H2 Deprioritize"},
                            {"text": {"type": "plain_text", "text": "In Assessment"}, "value": "In Assessment"}
                        ]
                    },
                    "optional": True
                },
                {
                    "type": "input",
                    "block_id": "parent_task_block",
                    "label": {"type": "plain_text", "text": "Subtask of (Parent Task ID - Optional)"},
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "parent_task_input",
                        "placeholder": {"type": "plain_text", "text": "Enter Notion ID of parent task (optional)"}
                    },
                    "optional": True
                }
            ]
        }

        try:
            slack_web_client.views_open(
                trigger_id=trigger_id,
                view=modal
            )
            return ""
        except SlackApiError as e:
            app.logger.error(f"Error opening Slack modal for creation: {e.response['error']}")
            return jsonify({
                "response_type": "ephemeral",
                "text": f"Error opening task creation form: {e.response['error']}"
            })
    
    # Handle reaction_added event for task creation in a specific database
    elif event_type == "reaction_added":
        reaction = event_payload["event"]["reaction"]
        if reaction == TRIGGER_EMOJI:
            user_id = event_payload["event"]["user"]
            channel_id = event_payload["event"]["item"]["channel"]
            message_ts = event_payload["event"]["item"]["ts"]
            
            try:
                message_response = slack_web_client.conversations_history(
                    channel=channel_id,
                    latest=message_ts,
                    limit=1,
                    inclusive=True
                )
                if message_response["ok"] and message_response["messages"]:
                    original_message = message_response["messages"][0]
                    message_text = original_message.get("text")
                    
                    if not message_text:
                        app.logger.warning("Reaction added to a message with no text. Skipping Notion task creation.")
                        return jsonify({"ok": True})

                    # Create the Notion task in the SALES_DATABASE_ID
                    task_name = f"Slack Request: {message_text[:100]}..." if len(message_text) > 100 else f"Slack Request: {message_text}"
                    slack_link = slack_web_client.chat_getPermalink(channel=channel_id, message_ts=message_ts)["permalink"]
                    
                    notion_properties = {
                        "Name": {
                            "title": [{"text": {"content": task_name}}]
                        },
                        "Slack Message Link": {
                            "url": slack_link
                        },
                        "Created time": {
                            "date": {"start": datetime.now().isoformat()}
                        },
                        "Tags": { # NEW: Add the "Tags" property with a default value
                            "select": {
                                "name": "2025 H2 Assessing"
                            }
                        }
                    }
                    
                    try:
                        new_page = notion_client.pages.create(
                            parent={"database_id": SALES_DATABASE_ID},
                            properties=notion_properties
                        )
                        
                        slack_web_client.chat_postMessage(
                            channel=channel_id,
                            blocks=[{
                                "type": "section",
                                "text": {
                                    "type": "mrkdwn",
                                    "text": f"✅ New Notion task created from a reaction by <@{user_id}>: *<{new_page['url']}|View Task>*"
                                }
                            }]
                        )
                    except Exception as e:
                        app.logger.error(f"Error creating Notion task from reaction: {e}")
                        slack_web_client.chat_postMessage(
                            channel=channel_id,
                            text=f"Error creating Notion task: {e}"
                        )
            except SlackApiError as e:
                app.logger.error(f"Error fetching message details: {e.response['error']}")
                
    return jsonify({"ok": True})


@app.route("/slack/interactive", methods=["POST"])
def slack_interactive():
    """
    Handles interactive Slack events, specifically modal submissions.
    """
    if not signature_verifier.is_valid_request(request.get_data(), request.headers):
        app.logger.warning("Invalid Slack request signature.")
        return "Invalid request signature", 403

    payload = json.loads(request.form["payload"])
    callback_id = payload.get("view", {}).get("callback_id")
    user_id = payload.get("user", {}).get("id")
    
    if payload.get("type") == "view_submission":
        if callback_id == "create_notion_task_modal":
            values = payload.get("view", {}).get("state", {}).get("values", {})
            
            task_name = values.get("task_name_block", {}).get("task_name_input", {}).get("value")
            status = values.get("status_block", {}).get("status_select", {}).get("selected_option", {}).get("value")
            pic_input = values.get("pic_block", {}).get("pic_input", {}).get("value")
            ddl_date = values.get("ddl_block", {}).get("ddl_datepicker", {}).get("selected_date")
            priority = values.get("priority_block", {}).get("priority_select", {}).get("selected_option", {}).get("value")
            tags = values.get("tags_block", {}).get("tags_select", {}).get("selected_option", {}).get("value")
            parent_task_id = values.get("parent_task_block", {}).get("parent_task_input", {}).get("value")

            errors = {}
            if not task_name: errors["task_name_block"] = "Task Name is required."
            if not pic_input: errors["pic_block"] = "Assigned PIC is required."
            if not ddl_date: errors["ddl_block"] = "Due Date (DDL) is required."
            if not priority: errors["priority_block"] = "Priority is required."
            if errors: return jsonify({"response_action": "errors", "errors": errors})

            notion_properties = {
                "Name": {"title": [{"text": {"content": task_name}}]},
                "Status": {"status": {"name": status}},
                "DDL": {"date": {"start": ddl_date}},
                "Priority": {"select": {"name": priority}},
            }
            
            if pic_input:
                notion_person_object = get_notion_person_id_from_slack_input(user_id, pic_input)
                if notion_person_object: notion_properties["PIC"] = {"people": [notion_person_object]}
            if parent_task_id: notion_properties["Parent task"] = {"relation": [{"id": parent_task_id}]}
            if tags: # NEW: Add the tags property if a tag was selected
                notion_properties["Tags"] = {"select": {"name": tags}}

            try:
                new_page = notion_client.pages.create(parent={"database_id": NOTION_DATABASE_ID}, properties=notion_properties)
                slack_web_client.chat_postMessage(channel=OFFICIAL_CHANNEL_ID, blocks=[{"type": "section", "text": {"type": "mrkdwn", "text": f"✅ Task created by <@{user_id}>: *<{new_page['url']}|{task_name}>*"}}, {"type": "context", "elements": [{"type": "mrkdwn", "text": "You can add more details in Notion."}]}])
                return jsonify({"response_action": "clear"})
            except Exception as e:
                app.logger.error(f"Error creating Notion task from modal: {e}")
                return jsonify({"response_action": "errors", "errors": {"task_name_block": f"Error creating task: {e}. Please check logs."}})

        elif callback_id == "update_notion_task_modal":
            values = payload.get("view", {}).get("state", {}).get("values", {})
            task_id_to_update = payload.get("view", {}).get("private_metadata")

            new_status = values.get("update_status_block", {}).get("update_status_select", {}).get("selected_option", {}).get("value")
            new_ddl_date = values.get("update_ddl_block", {}).get("update_ddl_datepicker", {}).get("selected_date")
            new_pic_input = values.get("update_pic_block", {}).get("update_pic_input", {}).get("value")
            new_priority = values.get("update_priority_block", {}).get("update_priority_select", {}).get("selected_option", {}).get("value")
            new_parent_task_id = values.get("update_parent_task_block", {}).get("update_parent_task_input", {}).get("value")
            new_tags = values.get("update_tags_block", {}).get("update_tags_select", {}).get("selected_option", {}).get("value")

            update_properties = {}
            if new_status: update_properties["Status"] = {"status": {"name": new_status}}
            if new_ddl_date: update_properties["DDL"] = {"date": {"start": new_ddl_date}}
            elif new_ddl_date == "": update_properties["DDL"] = {"date": None}
            if new_priority: update_properties["Priority"] = {"select": {"name": new_priority}}
            if new_tags: update_properties["Tags"] = {"select": {"name": new_tags}} # NEW: Add new Tags to update properties

            if new_pic_input:
                notion_person_object = get_notion_person_id_from_slack_input(user_id, new_pic_input)
                if notion_person_object: update_properties["PIC"] = {"people": [notion_person_object]}
            elif new_pic_input == "": update_properties["PIC"] = {"people": []}
            if new_parent_task_id: update_properties["Parent task"] = {"relation": [{"id": new_parent_task_id}]}
            elif new_parent_task_id == "": update_properties["Parent task"] = {"relation": []}

            if not update_properties: return jsonify({"response_action": "errors", "errors": {"task_id_display_block": "No properties selected for update."}})

            try:
                updated_page = notion_client.pages.update(page_id=task_id_to_update, properties=update_properties)
                updated_task_name = updated_page.get("properties", {}).get("Name", {}).get("title", [{}])[0].get("plain_text", "Unknown Task")

                slack_web_client.chat_postMessage(
                    channel=OFFICIAL_CHANNEL_ID,
                    blocks=[{"type": "section", "text": {"type": "mrkdwn", "text": f"✅ Task updated by <@{user_id}>: *<{updated_page['url']}|{updated_task_name}>*"}}, {"type": "context", "elements": [{"type": "mrkdwn", "text": "Changes applied in Notion."}]}]
                )
                return jsonify({"response_action": "clear"})
            except Exception as e:
                app.logger.error(f"Error updating Notion task from modal: {e}")
                return jsonify({"response_action": "errors", "errors": {"task_id_display_block": f"Error updating task: {e}. Please check logs. Ensure Task ID is correct."}})
    
    return jsonify({"ok": True})

if __name__ == "__main__":
    if not all([SLACK_BOT_TOKEN, NOTION_API_KEY, NOTION_DATABASE_ID, SALES_DATABASE_ID, SLACK_SIGNING_SECRET]):
        app.logger.error("Error: One or more essential environment variables are missing. Please check your .env file.")
        sys.exit(1)

    app.run(host="0.0.0.0", port=5001, debug=True)