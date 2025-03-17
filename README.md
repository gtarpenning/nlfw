
# NLFW

This app reads your emails, identifies recruiting emails, then drafts nice responses that tell them to stop. My unending attempts to remove my information from data-sellers have failed, at least I can automate my responses.

Ideally this would also go online and unsubscribe you from recruiting sites by making "do not sell my data" requests, but they now all have captcha and cloudflare bot detection...

Example output for a config with an interest in climate change:
<img width="1144" alt="demo" src="https://github.com/user-attachments/assets/8ddd9891-ad23-4c27-a156-ebdd0252af4a" />

### Usage 

Make sure to set `OPENAI_API_KEY`, `GMAIL_EMAIL`, and `GMAIL_PASSWORD` (bot password, not login password)