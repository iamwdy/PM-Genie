"""
Configuration management for Slack-Notion Bot
Handles environment variables and provides easy access to settings
"""
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class SlackConfig:
    """Slack-related configuration"""
    BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
    SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET")
    
    # Channels
    MONITORING_CHANNEL = os.getenv("SLACK_CHANNEL_ID")
    PM_NOTIFICATION_CHANNEL = os.getenv("PM_NOTIFICATION_CHANNEL_ID")
    OFFICIAL_CHANNEL = os.getenv("OFFICIAL_CHANNEL_ID")
    TEST_CHANNEL = os.getenv("TEST_CHANNEL_ID")
    
    # Team members
    PM_TEAM_USER_IDS = [
        "U08UUNJ86P7",  # Wendy Wang
        "U052ED4GV8R",  # Sharon Wu
        "U03J5M6SXJS",  # Annie Chen
        "UH13Z1L06",    # Casper Chen
    ]

class NotionConfig:
    """Notion-related configuration"""
    API_KEY = os.getenv("NOTION_API_KEY")
    
    # Databases
    MAIN_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
    SALES_DATABASE_ID = os.getenv("SALES_DATABASE_ID")
    SPRINT_DATABASE_ID = os.getenv("NEXT_SPRINT_NOTION_DATABASE_ID")
    
    # Properties
    TAG_PROPERTY = "Tag"
    TAG_VALUE = "2025 H2 Assessing"
    THREAD_LINK_PROPERTY = "Thread Link"

class BotConfig:
    """Bot behavior configuration"""
    TARGET_EMOJIS = ["pmgenie", "business_request"]
    
    # Feature flags (can be moved to env vars later)
    ENABLE_DUPLICATE_PREVENTION = True
    ENABLE_PM_NOTIFICATIONS = True
    DEBUG_MODE = os.getenv("DEBUG_MODE", "false").lower() == "true"

class ExternalAPIs:
    """External API configuration"""
    IMAGEN_API_KEY = os.getenv("IMAGEN_API_KEY")

def validate_config():
    """Validate that all required environment variables are set"""
    required_vars = [
        ("SLACK_BOT_TOKEN", SlackConfig.BOT_TOKEN),
        ("SLACK_SIGNING_SECRET", SlackConfig.SIGNING_SECRET),
        ("SLACK_CHANNEL_ID", SlackConfig.MONITORING_CHANNEL),
        ("NOTION_API_KEY", NotionConfig.API_KEY),
        ("SALES_DATABASE_ID", NotionConfig.SALES_DATABASE_ID),
        ("PM_NOTIFICATION_CHANNEL_ID", SlackConfig.PM_NOTIFICATION_CHANNEL),
    ]
    
    missing_vars = [var_name for var_name, var_value in required_vars if not var_value]
    
    if missing_vars:
        raise ValueError(f"Missing required environment variables: {missing_vars}")
    
    return True

def get_channel_for_environment(env="development"):
    """Get appropriate channel based on environment"""
    if env == "production":
        return SlackConfig.OFFICIAL_CHANNEL
    else:
        return SlackConfig.TEST_CHANNEL

# Example usage:
# from config import SlackConfig, NotionConfig, validate_config
# validate_config()
# slack_client = WebClient(token=SlackConfig.BOT_TOKEN)
