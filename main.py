#!/usr/bin/env python3
"""
Main entry point for the Slack Message Handler on Replit
"""
import os
from slack_message_handler import app

if __name__ == '__main__':
    # Get port from environment (Replit sets this automatically)
    port = int(os.environ.get('PORT', 3000))
    
    # Check required environment variables
    required_vars = [
        'SLACK_BOT_TOKEN', 'SLACK_SIGNING_SECRET', 'SLACK_CHANNEL_ID',
        'NOTION_API_KEY', 'SALES_DATABASE_ID', 'PM_NOTIFICATION_CHANNEL_ID'
    ]
    
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    if missing_vars:
        print(f"❌ Error: Missing environment variables: {missing_vars}")
        print("Please set these in your Replit Secrets tab")
        exit(1)
    
    print("🚀 Slack message handler starting on Replit...")
    print(f"🌐 Running on port: {port}")
    print(f"📺 Monitoring channel: {os.getenv('SLACK_CHANNEL_ID')}")
    print(f"📢 PM notification channel: {os.getenv('PM_NOTIFICATION_CHANNEL_ID')}")
    
    # Run the Flask app (debug mode for external access on Replit)
    app.run(host='0.0.0.0', port=port, debug=True, threaded=True)
