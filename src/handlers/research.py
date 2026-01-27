"""Research handler - performs web research and emails results."""

from google.genai.types import GenerateContentConfig, GoogleSearch, Tool

from src.clients.email import send_email
from src.config import Config
from src.handlers.base import register_handler
from src.models import Task
from src.services import Services


@register_handler("research")
def handle_research(task: Task, config: Config, services: Services) -> None:
    """Handle research tasks."""
    query = task.body.strip()
    reply_to = task.reply_to

    if not query:
        print("  No query in task body")
        return

    if not reply_to:
        print("  No reply_to address")
        return

    print(f"  Researching: {query[:80]}...")

    prompt = f"""You are a research assistant. Answer the following query thoroughly and concisely.

Query: {query}

Use web search to find current, accurate information. Provide a well-structured response with key facts and insights."""

    try:
        # Use research model (2.5 Flash) for free Google Search grounding
        response = services.gemini_client.models.generate_content(
            model=config.gemini_research_model,
            contents=[prompt],
            config=GenerateContentConfig(tools=[Tool(google_search=GoogleSearch())]),
        )

        result = response.text
        subject_line = query.split("\n")[0][:50]

        send_email(
            to_address=reply_to,
            subject=f"Re: {subject_line}",
            body=result,
            email_user=config.email_user,
            email_pass=config.email_pass,
            smtp_server=config.smtp_server,
            smtp_port=config.smtp_port,
        )
        print(f"  Response sent to {reply_to} (model: {config.gemini_research_model})")

    except Exception as e:
        print(f"  Research error: {e}")
        send_email(
            to_address=reply_to,
            subject="Research Error",
            body=f"Sorry, I encountered an error: {e}",
            email_user=config.email_user,
            email_pass=config.email_pass,
            smtp_server=config.smtp_server,
            smtp_port=config.smtp_port,
        )
