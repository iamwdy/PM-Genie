import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from notion_client import Client
import sys # Import sys to read command-line arguments

# 從 .env 文件加載環境變數
load_dotenv()

# --- 配置 ---
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
NOTION_API_KEY = os.getenv("NOTION_API_KEY")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
OFFICIAL_CHANNEL_ID = os.getenv("OFFICIAL_CHANNEL_ID")
# This constant is no longer needed since the last call reminder logic is dynamic.
PM_WEEKLY_MEETING_URL = "https://www.notion.so/inline/PM-Weekly-Meeting_2025-June-218c90dfe385807d94d8d129f33d9aba?source=copy_link"
PM_WEEKLY_MEETING_TEXT = "PM Weekly Meeting"
# Removed MEETING_DOCS_DATABASE_ID and other sprint-related constants.


# 初始化 Slack 和 Notion 客戶端
slack_client = WebClient(token=SLACK_BOT_TOKEN)
notion_client = Client(auth=NOTION_API_KEY)

# Store a cache for Slack user IDs to avoid repeated API calls
slack_user_id_cache = {}

# 定義您的 Notion 屬性名稱 (已根據您提供的截圖進行調整)
TASK_STATUS_PROPERTY = "Status"
TASK_PIC_PROPERTY = "PIC"
TASK_DDL_PROPERTY = "DDL"
TASK_PARENT_RELATION_PROPERTY = "Parent task"
TASK_CREATED_TIME_PROPERTY = "Created Time"
TASK_COUNTDOWN_PROPERTY = "Countdown"
TASK_SUBTASK_PROGRESS_PROPERTY = "Subtask Progress"
TASK_DISCUSS_CHECKBOX_PROPERTY = "Discuss in this week meeting?"
TASK_TOPIC_TYPE_PROPERTY = "Topic Type"

PENDING_STATUSES = ["Not started", "In progress", "On Hold"]
NOT_STARTED_STATUSES = ["Not started"]

LONG_CREATED_THRESHOLD_DAYS = 7

EXCLUDE_PICS = [
    "Jason", "jason@example.com"
] 

STATUS_EMOJI_MAP = {
    "Not started": ":no_entry:",
    "On Hold": ":double_vertical_bar:",
    "In progress": ":loading:",
}

SLACK_USER_MAPPING = {
    "Wendy Wang": "U08UUNJ86P7",
    "Sharon Wu": "U052ED4GV8R",
    "Annie Chen": "U03J5M6SXJS",
    "Casper Chen": "UH13Z1L06",
}

# --- Reminder Types ---
REMINDER_TYPE_WEEKLY_UPDATE = "weekly_update"
REMINDER_TYPE_LAST_CALL = "last_call"
# --- End Reminder Types ---


def get_slack_user_id_by_email(email):
    """
    Looks up a Slack user ID by their email address. Caches results.
    """
    if email in SLACK_USER_MAPPING:
        return SLACK_USER_MAPPING[email]

    if email in slack_user_id_cache:
        return slack_user_id_cache[email]
    
    try:
        response = slack_client.users_lookupByEmail(email=email)
        if response["ok"] and response["user"]:
            user_id = response["user"]["id"]
            slack_user_id_cache[email] = user_id
            return user_id
        else:
            print(f"Warning: Could not find Slack user for email '{email}': {response.get('error', 'Unknown error')}")
            return None
    except SlackApiError as e:
        print(f"Slack API error looking up user by email '{email}': {e.response['error']}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred looking up Slack user by email '{email}': {e}")
        return None

def get_notion_tasks():
    """
    Fetches all tasks from the specified Notion database.
    """
    tasks = []
    try:
        response = notion_client.databases.query(
            database_id=NOTION_DATABASE_ID
        )
        tasks.extend(response["results"])

        while response["has_more"]:
            response = notion_client.databases.query(
                database_id=NOTION_DATABASE_ID,
                start_cursor=response["next_cursor"]
            )
            tasks.extend(response["results"])

        print(f"Successfully fetched {len(tasks)} tasks from Notion.")
        return tasks
    except Exception as e:
        print(f"Error fetching Notion tasks: {e}")
        return []

def analyze_tasks(tasks):
    """
    Analyzes tasks, groups them by PIC, and filters out sub-tasks and excluded PICs.
    """
    grouped_by_pic = {}

    for task in tasks:
        task_status = get_property_value(task, TASK_STATUS_PROPERTY, "status", "Unknown Status")
        if task_status == "Done":
            continue

        pic_values_list = get_property_value(task, TASK_PIC_PROPERTY, "people", ["Unassigned"])
        
        is_sub_task = False
        if TASK_PARENT_RELATION_PROPERTY in task["properties"] and \
           task["properties"][TASK_PARENT_RELATION_PROPERTY]["relation"]:
            if task["properties"][TASK_PARENT_RELATION_PROPERTY]["relation"]:
                is_sub_task = True
        
        if is_sub_task:
            continue

        for pic_value in pic_values_list:
            if pic_value in EXCLUDE_PICS:
                continue
            
            if pic_value not in grouped_by_pic:
                grouped_by_pic[pic_value] = []
            
            grouped_by_pic[pic_value].append(task)
    
    def pic_sort_key(pic_name):
        if pic_name == "Unassigned":
            return (2, pic_name)
        elif pic_name not in SLACK_USER_MAPPING:
            return (1, pic_name)
        else:
            return (0, pic_name)

    sorted_pic_names = sorted(grouped_by_pic.keys(), key=pic_sort_key)
    sorted_final_data = {pic: grouped_by_pic[pic] for pic in sorted_pic_names}

    return sorted_final_data

def get_property_value(task_page, property_name, property_type, default_value=None):
    """
    Helper function: Safely retrieves property values from a Notion page.
    """
    if property_type == "title":
        for prop_key, prop_value in task_page["properties"].items():
            if prop_value["type"] == "title":
                if not prop_value["title"]:
                    return default_value
                
                extracted_title = "".join([text_obj["plain_text"] for text_obj in prop_value["title"]])
                return extracted_title if extracted_title else default_value
        return default_value

    if property_name not in task_page["properties"]:
        return default_value

    prop = task_page["properties"][property_name]
    prop_type = prop["type"]

    if prop_type == "status":
        return prop["status"]["name"] if prop["status"] else default_value
    elif prop_type == "people":
        people_list = []
        for p in prop["people"]:
            people_list.append(p["name"])
        return people_list if people_list else ["Unassigned"]
    elif prop_type == "date":
        if prop["date"]:
            start_date = datetime.fromisoformat(prop["date"]["start"]).strftime("%Y-%m-%d")
            return start_date
        return default_value
    elif prop_type == "created_time":
        if prop["created_time"]:
            try:
                dt_object = datetime.fromisoformat(prop["created_time"].replace('Z', '+00:00'))
                return dt_object.strftime("%Y-%m-%d")
            except ValueError:
                return prop["created_time"]
        return default_value
    elif prop_type == "relation":
        return prop["relation"] if prop["relation"] else []
    elif prop_type == "formula":
        if "string" in prop["formula"] and prop["formula"]["string"] is not None:
            return prop["formula"]["string"]
        elif "number" in prop["formula"] and prop["formula"]["number"] is not None:
            return str(prop["formula"]["number"])
        elif "boolean" in prop["formula"] and prop["formula"]["boolean"] is not None:
            return str(prop["formula"]["boolean"])
        return default_value
    elif prop_type == "rollup":
        if "number" in prop["rollup"] and prop["rollup"]["number"] is not None:
            return str(prop["rollup"]["number"])
        elif "array" in prop["rollup"] and prop["rollup"]["array"]:
            extracted_text = []
            for item in prop["rollup"]["array"]:
                if "rich_text" in item and item["rich_text"]:
                    extracted_text.append("".join([rt["plain_text"] for rt in item["rich_text"]]))
                elif "number" in item and item["number"] is not None:
                    extracted_text.append(str(item["number"]))
            return ", ".join(extracted_text) if extracted_text else default_value
        elif "date" in prop["rollup"] and prop["rollup"]["date"]:
            start_date = datetime.fromisoformat(prop["rollup"]["date"]["start"]).strftime("%Y-%m-%d")
            return start_date
        elif "string" in prop["rollup"] and prop["rollup"]["string"] is not None:
            return prop["rollup"]["string"]
        return default_value
    elif prop_type == "rich_text":
        return "".join([text_obj["plain_text"] for text_obj in prop["rich_text"]]) if prop["rich_text"] else default_value
    elif prop_type == "checkbox":
        return prop["checkbox"] if "checkbox" in prop else False
    elif prop_type == "select":
        return prop["select"]["name"] if prop["select"] else default_value
    
    return default_value

def format_slack_message(organized_tasks_by_pic):
    """
    Formats the task analysis into a Slack message, grouped by PIC.
    """
    message_blocks = []
    
    message_blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": "*Weekly Task Status Update: 📈*"
        }
    })
    emoji_explanation_text = (
        "Here's a quick guide to task statuses:\n"
        f"• Not started: {STATUS_EMOJI_MAP.get('Not started', '')}\n"
        f"• On Hold: {STATUS_EMOJI_MAP.get('On Hold', '')}\n"
        f"• In Progress: {STATUS_EMOJI_MAP.get('In progress', '')}\n\n"
        "It's Monday morning! Time to update your meeting items and tackle the week ahead. 💪"
    )
    message_blocks.append({
        "type": "context",
        "elements": [
            {
                "type": "mrkdwn",
                "text": emoji_explanation_text
            }
        ]
    })
    message_blocks.append({"type": "divider"})

    if not organized_tasks_by_pic:
        message_blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "No tasks to report in the Notion database."
            }
        })
    else:
        for pic_name, tasks_list in organized_tasks_by_pic.items():
            slack_user_id = None
            if pic_name in SLACK_USER_MAPPING:
                slack_user_id = SLACK_USER_MAPPING[pic_name]
            
            pic_display = ""
            if slack_user_id:
                pic_display = f"<@{slack_user_id}>"
            elif pic_name == "Unassigned":
                pic_display = "Unassigned"
                if "Wendy Wang" in SLACK_USER_MAPPING:
                    pic_display = f"<@{SLACK_USER_MAPPING['Wendy Wang']}>"
            else:
                pic_display = pic_name

            message_blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{pic_display}*"
                }
            })
            
            if not tasks_list:
                message_blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "  - No tasks assigned to this person."
                    }
                })
            else:
                if pic_name == "Unassigned":
                    message_blocks.append({
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "These tasks are unassigned, please look into them."
                        }
                    })

                pic_tasks_markdown = ""
                for task in tasks_list:
                    task_name = get_property_value(task, "dynamic_title", "title", "Untitled Task")
                    task_status = get_property_value(task, TASK_STATUS_PROPERTY, "status", "Unknown Status")
                    task_ddl = get_property_value(task, TASK_DDL_PROPERTY, "date", "No Due Date")
                    task_countdown = get_property_value(task, TASK_COUNTDOWN_PROPERTY, "formula", None)
                    task_subtask_progress = get_property_value(task, TASK_SUBTASK_PROGRESS_PROPERTY, "rollup", None)
                    task_url = task["url"]
                    
                    status_emoji = STATUS_EMOJI_MAP.get(task_status, "")

                    if task_name != "Untitled Task":
                        pic_tasks_markdown += f"• *{task_name}* (<{task_url}|_Link_>)\n" 
                        pic_tasks_markdown += f"    ◦ Status: {status_emoji}\n"
                        
                        if task_ddl != "No Due Date":
                            ddl_text = f"DDL: *{task_ddl}*"
                            if task_countdown:
                                ddl_text += f" `{task_countdown}`"
                            pic_tasks_markdown += f"    ◦ {ddl_text}\n"
                        else:
                            ddl_text = "Due Date is Required"
                            pic_tasks_markdown += f"    ◦ DDL: `{ddl_text}`\n"

                        if task_subtask_progress:
                            pic_tasks_markdown += f"    ◦ Subtask Progress: `{task_subtask_progress}`\n"
                        
                        pic_tasks_markdown += "\n" 

                if pic_tasks_markdown.strip():
                    message_blocks.append({
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": pic_tasks_markdown.strip()
                        }
                    })
            message_blocks.append({"type": "divider"})

    return message_blocks

def post_slack_message(blocks):
    """
    Posts the formatted message blocks to the specified Slack channel.
    """
    fallback_text = "Notion Task Status Update"
    if blocks and len(blocks) > 0 and "text" in blocks[0] and "text" in blocks[0]["text"]:
        fallback_text = blocks[0]["text"]["text"]

    try:
        response = slack_client.chat_postMessage(
            channel=OFFICIAL_CHANNEL_ID,
            text=fallback_text,
            blocks=blocks
        )
        if response["ok"]:
            print(f"Message successfully posted to Slack channel: {SLACK_CHANNEL_ID}")
        else:
            print(f"Error posting message to Slack: {response['error']}")
    except SlackApiError as e:
        print(f"Slack API error: {e.response['error']}")
    except Exception as e:
        print(f"An unexpected error occurred while posting to Slack: {e}")

def send_weekly_task_update():
    """
    Fetches Notion tasks, analyzes them, and posts the weekly update to Slack.
    """
    print("Generating Weekly Task Update...")
    tasks = get_notion_tasks()
    if tasks:
        organized_tasks_data = analyze_tasks(tasks)
        slack_message_blocks = format_slack_message(organized_tasks_data)
        post_slack_message(slack_message_blocks)
    else:
        print("No tasks fetched or an error occurred. Skipping Slack message post.")
    print("Weekly Task Update process finished.")

def send_last_call_reminder():
    """
    Sends a 'last call for update' reminder message to Slack.
    This also lists discussion topics for the meeting.
    """
    print("Sending Last Call Reminder with Discussion Topics...")
    
    tasks = get_notion_tasks() # Fetch all tasks to filter for discussion topics
    
    discussion_topics_by_type_and_pic = {
        "New Topic": {},
        "Follow-up Topic": {}
    }
    
    for task in tasks:
        discuss_checkbox = get_property_value(task, TASK_DISCUSS_CHECKBOX_PROPERTY, "checkbox", False)
        topic_type = get_property_value(task, TASK_TOPIC_TYPE_PROPERTY, "select", "Other Topic")
        is_sub_task = False
        if TASK_PARENT_RELATION_PROPERTY in task["properties"] and \
           task["properties"][TASK_PARENT_RELATION_PROPERTY]["relation"]:
            if task["properties"][TASK_PARENT_RELATION_PROPERTY]["relation"]:
                is_sub_task = True

        if not is_sub_task:
            if topic_type == "New Topic" or (topic_type == "Follow-up Topic" and discuss_checkbox):
                task_name = get_property_value(task, "dynamic_title", "title", "Untitled Topic")
                task_url = task["url"]
                pic_values_list = get_property_value(task, TASK_PIC_PROPERTY, "people", ["Unassigned"])
                
                for pic_name in pic_values_list:
                    if pic_name in EXCLUDE_PICS:
                        continue

                    if pic_name not in discussion_topics_by_type_and_pic[topic_type]:
                        discussion_topics_by_type_and_pic[topic_type][pic_name] = []
                    
                    discussion_topics_by_type_and_pic[topic_type][pic_name].append({
                        "name": task_name,
                        "url": task_url
                    })
    
    reminder_blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*⏰ Last Call for Weekly Updates! ⏰*\n\n"
                        "Please make sure all your weekly items are updated in Notion."
            }
        },
        {
            "type": "divider"
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*Topics for Discussion in This Week's Meeting:*"
            }
        }
    ]

    for topic_type in ["New Topic", "Follow-up Topic"]:
        if topic_type in discussion_topics_by_type_and_pic and discussion_topics_by_type_and_pic[topic_type]:
            reminder_blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{topic_type}:*"
                }
            })
            
            sorted_pics = sorted(discussion_topics_by_type_and_pic[topic_type].keys())
            
            for pic_name in sorted_pics:
                slack_user_id = SLACK_USER_MAPPING.get(pic_name)
                pic_display_name = f"<@{slack_user_id}>" if slack_user_id else f"@{pic_name}"

                reminder_blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*{pic_display_name}*"
                    }
                })

                task_markdown_list = []
                for task_info in discussion_topics_by_type_and_pic[topic_type][pic_name]:
                    task_markdown_list.append(f"- {task_info['name']} (<{task_info['url']}|_Link_>)")
                
                if task_markdown_list:
                     reminder_blocks.append({
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "\n".join(task_markdown_list)
                        }
                    })
            reminder_blocks.append({"type": "divider"})
    
    if not any(discussion_topics_by_type_and_pic.values()):
        reminder_blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "No topics are currently marked for discussion this week. Please check the 'Discuss in this week meeting?' checkbox in Notion if you have items to add."
            }
        })
        reminder_blocks.append({"type": "divider"})

    reminder_blocks.append({
        "type": "context",
        "elements": [
            {
                "type": "mrkdwn",
                "text": f"You can find the meeting notes here: <{PM_WEEKLY_MEETING_URL}|{PM_WEEKLY_MEETING_TEXT}>"
            }
        ]
    })
    post_slack_message(reminder_blocks)
    print("Last Call Reminder process finished.")


# Main execution block
if __name__ == "__main__":
    if not all([SLACK_BOT_TOKEN, NOTION_API_KEY, NOTION_DATABASE_ID, OFFICIAL_CHANNEL_ID]):
        print("Error: One or more environment variables are missing. Please check your .env file.")
        sys.exit(1)

    if len(sys.argv) > 1:
        reminder_type = sys.argv[1]
        if reminder_type == REMINDER_TYPE_WEEKLY_UPDATE:
            send_weekly_task_update()
        elif reminder_type == REMINDER_TYPE_LAST_CALL:
            send_last_call_reminder()
        else:
            print(f"Error: Unknown reminder type '{reminder_type}'. Valid types are '{REMINDER_TYPE_WEEKLY_UPDATE}', '{REMINDER_TYPE_LAST_CALL}', or '{REMINDER_TYPE_SPRINT_REMINDER}'.")
            sys.exit(1)
    else:
        print("Error: No reminder type specified. Please run with an argument (e.g., 'python3 your_script.py weekly_update').")
        sys.exit(1)





