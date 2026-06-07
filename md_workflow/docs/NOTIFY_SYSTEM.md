# MD Workflow Notification & Transfer System

This guide explains how to use the integrated real-time monitoring and high-reliability transfer system.

## 1. Environment Setup (One-Time)

To enable all features, export these variables in your terminal or add them to your `.bashrc`.

### GitHub (For Result Uploads)

* **Purpose:** Uploads massive simulation results in chunks and creates a Master Gist link.

```bash
export GITHUB_TOKEN="your_github_personal_access_token"
```

### Email (For Progress Updates)

* **Purpose:** Sends "Complex X passes Y ns" updates to your inbox.

```bash
export SMTP_SERVER='smtp.gmail.com'
export SMTP_PORT=587
export SMTP_USER='sender@gmail.com'
export SMTP_PASSWORD='your_16_char_app_password' # Use Gmail App Password
export NOTIFY_EMAIL='recipient@gmail.com'
```

### Telegram (Optional)

* **Purpose:** Sends progress updates directly to your chat.

```bash
export TELEGRAM_BOT_TOKEN="your_bot_token"
export TELEGRAM_CHAT_ID="your_chat_id"
```

---

## 2. Running the Workflow

### Real-Time Monitoring

Add `--notify-interval [SECONDS]` to your command.

```bash
# Example: Notify every 10 minutes (600 seconds)
python3 main.py workflow --protein prot.pdb --ligand lig.sdf --notify-interval 600
```

### Auto-Upload Results

Add `--upload` to archive and transfer results automatically when finished.

```bash
python3 main.py workflow --protein prot.pdb --ligand lig.sdf --upload
```

---

## 3. How It Works (Oversimplified)

1. **Monitoring:** A background thread "tails" the GROMACS log. Every interval, it uses **Regex** to grab the "Time" value.
2. **Notification:** It sends: *"Complex {ID} passes {Time} ns right now"* to Email, Telegram, and Console simultaneously.
3. **Chunking:** If results are huge, it splits them into **512MB/128MB/64MB** chunks automatically.
4. **Master Link:** It uploads all chunks and then creates a **GitHub Gist** containing a JSON manifest. **The only link you need is the Gist URL.**

---

## 4. Troubleshooting

* **Email not arriving?** Ensure you used an "App Password" from Google, not your main password.
* **Upload failing?** Ensure your `GITHUB_TOKEN` has `gist` permissions.
* **No notifications?** The system only notifies during the **Production MD** stage (the longest part).
