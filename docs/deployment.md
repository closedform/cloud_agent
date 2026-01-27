# Deployment Guide: Google Cloud "Always Free" Personal Assistant

This guide will help you move your autonomous `personal-assistant` from your laptop to a free Google Cloud server that runs 24/7. While currently configured for Calendar tasks, this infrastructure is designed to be the foundation for a general-purpose agent.

## 1. Create the Free VM
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

## 2. Connect to the VM
1.  In the VM list, click the **SSH** button next to your new instance.
2.  A terminal window will open in your browser.

## 3. Install Dependencies
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

## 4. Clone the Repository

```bash
git clone https://github.com/closedform/cloud_agent.git
cd cloud_agent
uv sync
```

## 5. Run the Agent

```bash
# Install tmux for persistent sessions
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

## Updating

To pull updates from GitHub:

```bash
cd ~/cloud_agent
git pull
uv sync
tmux kill-session -t agent
tmux new -s agent -d 'uv run python -m src.orchestrator' \; split-window -h 'uv run python -m src.poller'
```

## 6. Configuration (.env)
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
    ALLOWED_SENDERS="your.personal@gmail.com"
    POLL_INTERVAL=1800  # Check every 30 minutes
    ```
