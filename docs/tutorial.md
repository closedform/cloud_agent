# Building a Zero-Cost Autonomous Executive Assistant

It feels like every week there's a new "AI Scheduling" SaaS launching with a $30/month subscription. And honestly? Paying that much for a wrapper around a calendar API feels wrong. Especially when we know the underlying compute costs are practically zero.

So let’s reject the subscription model. Instead of renting an assistant, we’re going to build one from first principles.

This is a guide on how to architect a persistent, autonomous agent that manages your Google Calendar and Email. It runs 24/7, costs $0.00 to operate, and lives on your own infrastructure (well, Google's free tier infrastructure).

## The Economics (or: Why we are doing this)

We want this to be an asset, not a liability. That means no recurring costs.

Google Cloud Platform (GCP) has an "Always Free" tier that includes an **e2-micro** instance. It’s tiny—2 vCPUs and 1 GB of RAM—but for our purposes, it’s infinite. We don't need a supercomputer to make API calls; we just need a persistent state engine that never sleeps.

## The Architecture

The topology is simple. We have a central "Brain" (the Orchestrator) that acts as a hub, and a few "Spokes" for input and output.

### 1. The Orchestrator
The core logic is a simple event loop (`src/orchestrator.py`). It watches an input folder. That's it. It's not fancy. It sits there, sleeping, waiting for a file to appear.

When you drop a file in—maybe a screenshot of a doctor's appointment or a forwarded email from your airline—the Orchestrator wakes up. It sends that payload to **Gemini Flash**.

Why Flash? Because it’s fast, it’s cheap (free, actually, for low volume), and it’s smart enough to understand dates. We don't need a PhD-level model to know that "Next Tuesday at 4pm" means `RRULE:FREQ=WEEKLY;BYDAY=TU`.

### 2. The Input Manifold (Email)
We need a way to talk to the bot without SSH-ing into a server. The oldest, most reliable messaging protocol is IMAP.

We built a simple poller (`src/poller.py`) that watches a dedicated Gmail account. It securely filters for emails *only* from you (security first, folks). When it sees one, it rips out the body text and any attachments and dumps them into the Orchestrator's lap.

This decouples the "hearing" from the "thinking." Passively listening to email is cheap. Thinking is expensive. We only think when we have to.

### 3. The Execution Layer
Finally, the agent needs hands. We wrote a `src/clients/calendar.py` wrapper around the Google Calendar API.

Crucially, we added **dynamic routing**. The agent asks Google: "What calendars do we have?"

If you say "Soccer practice for Brandon," and the agent sees a "Brandon" calendar ID, it routes it there. If you say "Pottery Class" and that calendar doesn't exist? The agent creates it. It adapts to your ontology rather than forcing you to adapt to its schema.

## Deployment: The e2-micro

Here is the beauty of this setup: it runs on a potato.

1.  **The Box**: Ubuntu 22.04 LTS on `e2-micro` (us-west1). Use the "Standard Persistent Disk" to stay free.
2.  **The Stack**: Python 3.12 managed by `uv` (because pip is... well, you know).
3.  **Persistence**: `tmux`. We just launch the session, detach, and walk away.

## Conclusion

We just constructed a highly functional, autonomous executive assistant. It handles natural language, manages complex recurrence rules ("First Monday of every month"), and routes events contextually.

Capital expenditure: A few hours of coding.
Operating expense: $0.00.
Data sovereignty: 100%.

Not bad for a weekend project.

---

## Appendix: Deployment Manual

This section acts as a reference manual for deploying the `gcp_agent` to the cloud.

### 1. Create the Free VM
1.  Go to the [Google Cloud Console](https://console.cloud.google.com/).
2.  Navigate to **Compute Engine** > **VM Instances**.
3.  Click **Create Instance**.
4.  **Important Configuration (Tab by Tab)**:

    **Basics**:
    -   **Name**: `personal-assistant`
    -   **Region**: `us-east1`, `us-west1`, or `us-central1`.
    -   **Machine Type**: `e2-micro` (2 vCPU, 1 GB memory).

    **Boot Disk (Critical)**:
    -   Click **Change**.
    -   **Operating System**: Select `Ubuntu` -> `Ubuntu 24.04 LTS` (x86/64). Avoid "Minimal" images.
    -   **Boot Disk Type**: Select **Standard persistent disk** (HDD).
        -   *Warning*: The default "Balanced persistent disk" is NOT free.
    -   **Snapshot Schedule**: Ensure this is unchecked or set to "None".

    **Identity and API Access**:
    -   **Service Account**: "Compute Engine default service account" is fine.
    -   **Access scopes**: "Allow default access" is fine.

    **Firewall**:
    -   Uncheck "Allow HTTP/HTTPS traffic" (Safer for now, we don't need incoming web traffic yet).

    **Advanced Options (Optional)**:
    -   **Security**: "Turn on Secure Boot" is optional but good.
    -   **Management**: Ensure "Deletion protection" is off if you want to be able to delete it easily later.

5.  **Ignore the "Monthly Estimate"**: The sidebar shows the pre-discount price (~$7.00). The "Always Free" credit is applied on your final bill.
6.  Click **Create**.

### 2. Connect to the VM
1.  In the VM list, click the **SSH** button next to your new instance.
2.  A terminal window will open in your browser.

### 3. Install Dependencies
Run these commands in the SSH window to set up Python and the environment:

```bash
# Update and install Python/Git
sudo apt update && sudo apt install -y python3-pip git

# Install uv (our package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env

# Clone your code (Simulated for this guide - you'll upload yours)
mkdir -p ~/projects/assistant
```

### 4. Upload Your Code
Since you have the code locally, the easiest way to transfer it without setting up Git repos is using the **Upload File** button in the SSH window (Gear icon > Upload file).

**Files to Upload:**
1.  Upload the entire `gcp_agent` folder (or zip it locally first: `zip -r agent.zip gcp_agent`).
2.  Unzip it on the server: `unzip agent.zip`.

### 5. Setup & Run (The Fix)
If you uploaded a zip from a Mac/Windows machine, the virtual environment will be broken on Linux. Fix it like this:

```bash
cd ~/gcp_agent

# 1. Clear the old environment and rebuild it for Linux
rm -rf .venv
uv sync

# 2. Run the agent (We need two processes: Brain & Ears)
sudo apt install -y tmux

# Start a new persistent session
tmux new -s agent
```

**Inside the tmux session:**
1.  **Split the screen**: Press `Ctrl+B`, release, then `%`. (You now have a left and right pane).
2.  **Left Pane (Brain)**:
    ```bash
    uv run python -m src.orchestrator
    ```
3.  **Right Pane (Ears)**:
    -   Press `Ctrl+B`, release, then `Right Arrow` to switch.
    -   Run the poller:
    ```bash
    uv run python -m src.poller
    ```

**To leave it running**: Press `Ctrl+B`, release, then `D`. It will keep running in the cloud forever.

### 6. Enable Email (Optional)
To query your agent via email:
1.  **Get an App Password**: Go to [Google Account Security](https://myaccount.google.com/security) > 2-Step Verification > App Passwords. Create one named "PersonalAgent".
2.  **Edit .env on Server**:
    ```bash
    nano .env
    ```
    Add:
    ```bash
    # -- Brain --
    GEMINI_API_KEY="AIzaSy..."   <-- Paste your key from aistudio.google.com

    # -- Email --
    EMAIL_USER="your.bot.email@gmail.com"
    EMAIL_PASS="xxxx xxxx xxxx xxxx"   <-- Your App Password
    ALLOWED_SENDERS="your.personal@gmail.com,spouse@gmail.com"
    POLL_INTERVAL=1800  # Check every 30 minutes
    ```

