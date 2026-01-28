"""WebSearchAgent - handles web search with Google Search grounding.

Uses gemini-2.5-flash (config.gemini_research_model) for free Google Search grounding tier.
Returns results to parent agent (ResearchAgent) for summarization.
"""

from google.adk import Agent

from src.agents.tools.email_tools import send_email_response
from src.agents.tools.research_tools import web_search
from src.config import get_config

WEB_SEARCH_AGENT_INSTRUCTION = """You are a web search assistant with access to Google Search grounding.

Your job is to search the web and return a clear summary of your findings to the ResearchAgent.

When searching:
1. Use your web search capability to find current, accurate information
2. Search multiple queries if needed to get comprehensive coverage
3. Synthesize what you find into a coherent summary
4. If you can't find definitive information, say so

IMPORTANT: After completing the search, you MUST call send_email_response to deliver the results to the user. Be friendly and concise in your email.
"""

_config = get_config()

web_search_agent = Agent(
    name="WebSearchAgent",
    model=_config.gemini_research_model,  # gemini-2.5-flash for free Google Search grounding
    instruction=WEB_SEARCH_AGENT_INSTRUCTION,
    tools=[
        web_search,
        send_email_response,  # Sub-agents send their own emails in ADK
    ],
    output_key="web_search_results",
)
