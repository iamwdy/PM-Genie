# Deploying Slack Message Handler to Replit

This guide will help you deploy your Slack message handler to Replit for 24/7 cloud hosting.

## 🚀 Quick Start

### 1. Create a New Replit Project
1. Go to [replit.com](https://replit.com) and sign in
2. Click "Create Repl"
3. Choose "Import from GitHub" or "Upload files"
4. Upload all your project files

### 2. Set Environment Variables
In your Replit project, go to the **Secrets** tab (🔒 icon) and add these environment variables:

```
SLACK_BOT_TOKEN=xoxb-your-bot-token-here
SLACK_SIGNING_SECRET=your-signing-secret-here
SLACK_CHANNEL_ID=your-channel-id
PM_NOTIFICATION_CHANNEL_ID=your-pm-channel-id
NOTION_API_KEY=ntn_your-notion-api-key
SALES_DATABASE_ID=your-sales-database-id
```

### 3. Deploy and Get Your Webhook URL
1. Click the "Run" button in Replit
2. Your app will be available at: `https://your-repl-name.your-username.repl.co`
3. The webhook endpoint will be: `https://your-repl-name.your-username.repl.co/slack/events`

### 4. Configure Slack App
1. Go to your Slack app settings at [api.slack.com](https://api.slack.com/apps)
2. Navigate to **Event Subscriptions**
3. Set the Request URL to: `https://your-repl-name.your-username.repl.co/slack/events`
4. Subscribe to the `reaction_added` event
5. Save changes

## 📁 Files Added for Replit

- **`main.py`** - Entry point optimized for Replit deployment
- **`.replit`** - Replit configuration file
- **`replit.nix`** - System dependencies configuration

## 🔧 Key Features

- **Always On**: Replit keeps your bot running 24/7
- **Automatic HTTPS**: Replit provides SSL certificates
- **Easy Environment Management**: Use Replit's Secrets tab
- **Health Check**: Available at `/health` endpoint

## 🐛 Troubleshooting

### Bot Not Responding
1. Check the Console tab for error messages
2. Verify all environment variables are set correctly
3. Test the health endpoint: `https://your-repl-name.your-username.repl.co/health`

### Slack Events Not Received
1. Verify the webhook URL in Slack app settings
2. Check that the bot has proper permissions in your Slack workspace
3. Ensure the bot is added to the target channel

### Environment Variables
- Use the **Secrets** tab, not `.env` files on Replit
- Environment variables are automatically loaded
- Never commit sensitive tokens to your code

## 📊 Monitoring

- Check the Console tab for real-time logs
- Use the health endpoint to verify the service is running
- Monitor Slack app logs in the Slack API dashboard

## 🔄 Updates

To update your deployment:
1. Upload new files to your Replit project
2. The service will automatically restart
3. No additional configuration needed

---

**Note**: Replit's free tier has some limitations. For production use, consider upgrading to Replit Pro for better reliability and performance.
