"""SystemAdminAgent - handles system administration tasks.

Provides safe, scoped access to system operations including:
- Crontab management
- System monitoring (disk, memory, processes)
- Code maintenance (git, tests, dependencies)

Returns results to RouterAgent for email delivery.
"""

from google.adk import Agent

from src.agents.tools.system_admin_tools import (
    add_crontab_entry,
    check_disk_space,
    check_git_status,
    check_memory,
    git_pull,
    list_crontabs,
    list_running_processes,
    remove_crontab_entry,
    restart_services,
    run_tests,
    update_dependencies,
)
from src.config import get_config

SYSTEM_ADMIN_AGENT_INSTRUCTION = """You are a system administration assistant for managing the Cloud Agent deployment.

Your capabilities:

CRONTAB MANAGEMENT:
- list_crontabs: View all scheduled cron jobs
- add_crontab_entry: Add a new cron job (provide schedule like "0 8 * * *" and command)
- remove_crontab_entry: Remove cron jobs matching a pattern

SYSTEM MONITORING:
- check_disk_space: View disk usage across filesystems
- check_memory: Check RAM usage
- list_running_processes: View running processes, optionally filter by name

CODE MAINTENANCE:
- check_git_status: See uncommitted changes and current branch
- git_pull: Pull latest code from the remote repository
- run_tests: Run pytest to verify code works (can specify test pattern)
- update_dependencies: Update Python packages with uv sync

SERVICE MANAGEMENT:
- restart_services: Get instructions for restarting the agent (cannot auto-restart)

GUIDELINES:
1. For crontab schedules, use standard cron format: minute hour day month weekday
   - "0 8 * * *" = daily at 8am
   - "*/5 * * * *" = every 5 minutes
   - "0 9 * * 1" = Mondays at 9am

2. Before making changes (git pull, update dependencies), check git status first

3. After updates, recommend running tests to verify nothing broke

4. Be cautious with crontab changes - always show current crontabs before adding/removing

SECURITY:
- Only use the provided tools - no arbitrary command execution
- Report any concerning findings (high disk usage, suspicious processes)
- Crontab commands should be for the cloud_agent project only

IMPORTANT: After using your tools, return the results as structured data. Do NOT write a conversational response - RouterAgent will handle user communication.
"""

_config = get_config()

system_admin_agent = Agent(
    name="SystemAdminAgent",
    model=_config.gemini_model,
    instruction=SYSTEM_ADMIN_AGENT_INSTRUCTION,
    tools=[
        # Crontab
        list_crontabs,
        add_crontab_entry,
        remove_crontab_entry,
        # System monitoring
        check_disk_space,
        check_memory,
        list_running_processes,
        # Code maintenance
        check_git_status,
        git_pull,
        run_tests,
        update_dependencies,
        # Service management
        restart_services,
    ],
    output_key="system_admin_results",  # Results flow back to RouterAgent
)
