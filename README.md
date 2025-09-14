---

# 📧 Autonomous Email Agent

An **AI-powered email automation agent** that monitors your Gmail inbox, checks messages against your airline policy file, and automatically replies when needed — with a beautiful logging dashboard.

---

## ✨ What It Does

🔹 Polls Gmail inbox for `test1234@gmail.com`
🔹 Extracts **keywords** from your policy file (`data/airlines_policy.md`)
🔹 Matches keywords against **incoming email subjects**
🔹 If match found → replies using **Gemini + RAG on policy**
🔹 If no match → skips email and logs reason
🔹 Real-time **Streamlit Logs UI** for monitoring

---

## ⚡ Quick Start

### 0️⃣ One-time Setup

1. Place your Gmail OAuth file `credentials.json` in:

   ```
   app/email/gmail_client.py
   ```
2. Copy `.env.example` → `.env` and configure:

   ```env
   GEMINI_API_KEY=your_gemini_key_here
   GMAIL_ADDRESS=test1234@gmail.com
   POLL_INTERVAL=60
   ```
3. Ensure your airline policy file exists:

   ```
   data/airlines_policy.md
   ```

---

### 1️⃣ Install & Bootstrap

```bash
bash scripts/bootstrap.sh
```

📌 Installs all dependencies and generates `data/keywords.json`

---

### 2️⃣ Run the Agent (Server + Background Poller)

```bash
uvicorn app.main:app --reload --port 8000
```

✅ On startup, a background task starts polling Gmail every `POLL_INTERVAL` seconds (default: 60).
✅ Replies only if subject **matches a keyword**.

---

### 3️⃣ Start the Logs UI

```bash
streamlit run app/ui/logs_app.py --server.port 8501
```

📊 Features:

* Live metrics
* Search & filtering
* Auto-refresh logs

---

## 🌐 API Endpoints

| Method | Endpoint    | Description                  |
| ------ | ----------- | ---------------------------- |
| GET    | `/health`   | Agent status check           |
| GET    | `/keywords` | List active policy keywords  |
| GET    | `/logs`     | Retrieve last 500 log events |

---

