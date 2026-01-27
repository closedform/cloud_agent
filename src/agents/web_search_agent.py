"""WebSearchAgent - handles web search with Google Search grounding.

Uses gemini-2.5-flash (config.gemini_research_model) for free Google Search grounding tier.
Returns results to parent agent (ResearchAgent) for summarization.
"""

from google.adk import Agent

from src.agents.tools.research_tools import web_search
from src.config import get_config

WEB_SEARCH_AGENT_INSTRUCTION = """You are a web search assistant with access to Google Search grounding.

Your job is to search the web and return a clear summary of your findings to the ResearchAgent.

When searching:
1. Use your web search capability to find current, accurate information
2. Search multiple queries if needed to get comprehensive coverage
3. Synthesize what you find into a coherent summary
4. If you can't find definitive information, say so

Response format:
- Provide a clear, well-organized summary of what you found
- Include key facts, dates, and numbers
- Note the sources of important information
- Highlight any conflicting information or uncertainty
- If the query is ambiguous, note what you searched for

The ResearchAgent may ask follow-up questions based on your summary - be prepared to search again with refined queries.
"""

_config = get_config()

web_search_agent = Agent(
    name="WebSearchAgent",
    model=_config.gemini_research_model,  # gemini-2.5-flash for free Google Search grounding
    instruction=WEB_SEARCH_AGENT_INSTRUCTION,
    tools=[web_search],
    output_key="web_search_results",  # Results flow back via state
)
