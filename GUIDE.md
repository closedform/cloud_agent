# Building a Zero-Cost Autonomous Cloud Agent

It feels like every week there's a new "AI Assistant" SaaS launching with a $30/month subscription. And honestly? Paying that much for a wrapper around an API feels wrong. Especially when we know the underlying compute costs are practically zero.

So let's reject the subscription model. Instead of renting an assistant, we're going to build one from first principles.

This is a guide on how to architect a persistent, autonomous agent that runs 24/7, costs $0.00 to operate, and lives on Google's free tier infrastructure.

## The Economics

We want this to be an asset, not a liability. That means no recurring costs.

Google Cloud Platform has an "Always Free" tier that includes an **e2-micro** instance. It's tiny - 2 vCPUs and 1 GB of RAM - but for our purposes, it's infinite. We don't need a supercomputer to make API calls; we just need a persistent state engine that never sleeps.

**The stack:**
- **Compute**: GCP e2-micro (free forever)
- **AI**: Gemini 3 Flash (free tier from AI Studio)
- **Email**: Gmail IMAP/SMTP (free)
- **Calendar**: Google Calendar API (free)

**Total monthly cost: $0.00**

## The Architecture

```
You --email--> Gmail --IMAP--> Agent --Gemini--> Calendar/Research/etc
                                 |
                           (your VM, always on)
                                 |
                              --SMTP--> Response back to you
```

The topology is simple. We have a central "Brain" (the Orchestrator) that acts as a hub, and "Spokes" for input and output.

### 1. The Orchestrator

The core logic is a simple event loop (`orchestrator.py`). It watches an input folder. When you drop a file in - maybe a screenshot of a doctor's appointment or a forwarded email - the Orchestrator wakes up and sends that payload to **Gemini 3 Flash**.

Why Flash? Because it's fast, it's cheap (free for personal use), and it's smart enough to understand natural language. We don't need a PhD-level model to parse "Next Tuesday at 4pm."

### 2. The Input Layer (Email)

We need a way to talk to the bot without SSH-ing into a server. The oldest, most reliable messaging protocol is IMAP.

The email poller (`email_poller.py`) watches a dedicated Gmail account. It filters for emails *only* from your allowlist (security first). When it sees one, it routes based on the subject line:

**Routing rules:**
- `Schedule ...` or `Appointment ...` - Creates calendar events
- `Research: <email>` - AI-powered research, response sent to specified email
- `Calendar: <email>` - Query your calendars, response sent to specified email

This decouples "hearing" from "thinking." Passively listening to email is cheap. Thinking is expensive. We only think when we have to.

### 3. The Execution Layer

The agent needs hands. We wrote a `calendar_client.py` wrapper around the Google Calendar API.

Crucially, we added **dynamic routing**. The agent asks Google: "What calendars do we have?"

If you say "Soccer practice for Brandon," and the agent sees a "Brandon" calendar, it routes it there. If you say "Pottery Class" and that calendar doesn't exist? The agent creates it. It adapts to your ontology rather than forcing you to adapt to its schema.

### 4. The Response Layer

For research and calendar queries, the agent sends responses back via SMTP. Same Gmail credentials, bidirectional communication. Ask a question, get an answer in your inbox.

## What Can It Do?

### Calendar Management

Email with keywords like "schedule" or "appointment" in the subject:

```
Subject: Schedule dentist appointment
Body: Dr. Smith next Tuesday at 2pm, should take about an hour
```

The agent parses natural language, handles recurring events ("every Monday"), and routes to the right calendar.

### Research Mode

Email with subject `Research: your@email.com` and your question in the body:

```
Subject: Research: me@example.com
Body: What are the best practices for Python async programming?
```

The agent researches using Gemini and emails the response.

### Calendar Queries

Email with subject `Calendar: your@email.com` and your question in the body:

```
Subject: Calendar: me@example.com
Body: What events do I have this week on the work calendar?
```

The agent checks your calendars and responds with relevant events.

## Deployment

Here's the beauty of this setup: it runs on a potato.

1. **The Box**: Ubuntu 24.04 LTS on e2-micro (us-east1, us-west1, or us-central1)
2. **The Stack**: Python 3.12 managed by `uv`
3. **Persistence**: `tmux` - launch, detach, walk away

### Quick Setup

```bash
# On your VM
git clone https://github.com/closedform/cloud_agent.git
cd cloud_agent

# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.local/bin/env

# Configure
cp .env.example .env
nano .env  # Add your API keys

# Run in tmux
tmux new -s agent
uv run python orchestrator.py
# Ctrl+B, % to split
uv run python email_poller.py
# Ctrl+B, D to detach
```

### Updating

Once deployed, updates are just:

```bash
cd ~/cloud_agent && git pull && uv sync
# Restart tmux session
```

## Extending the Agent

The architecture is intentionally simple. Add new capabilities by:

1. Writing a new client (like `calendar_client.py`)
2. Adding routing logic to `email_poller.py`
3. Updating the system prompt

Ideas: task management, home automation, expense tracking, flight monitoring, stock alerts.

## Conclusion

We just constructed a highly functional, autonomous agent. It handles natural language, manages complex recurrence rules, routes events contextually, performs research, and answers questions about your schedule.

**Capital expenditure**: A few hours of coding.
**Operating expense**: $0.00.
**Data sovereignty**: 100%.

Not bad for a weekend project.

---

*The full source code is available at [github.com/closedform/cloud_agent](https://github.com/closedform/cloud_agent)*
