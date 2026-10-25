"""
Web search tool (Tavily).

Moved unchanged from app/agents/base_agent.py (Plan P2.1).
P2.2 replaces these with async tools.
"""

from langchain_core.tools import BaseTool
from app.services.tool_cache import tool_cache
import os
from pydantic import BaseModel, Field


class WebSearchInput(BaseModel):
    """
    Input schema for web_search tool.
    
    Attributes:
        query: Search query string (required)
    """
    query: str = Field(description="Search query string")


class WebSearchTool(BaseTool):
    """
    Tool to search the web for current information.
    
    This tool uses the Tavily API to search the web for current information,
    research, or up-to-date data. Used by agents when they need recent information
    that might not be in their training data.
    
    Features:
        - Caching: Successful results are cached (1 hour TTL)
        - Global caching: Not user-specific (same query = same result for all users)
        - Error handling: Graceful degradation if API key not set
        - Result formatting: Formats results for easy agent consumption
        
    Use Cases:
        - Latest fitness trends and research
        - Current nutrition facts and guidelines
        - Recent exercise techniques and best practices
        - Up-to-date health information
        
    Cache Strategy:
        - Cache key includes only query (not user_id)
        - TTL: 1 hour (web search results don't change frequently)
        - Only successful results are cached (errors are not cached)
        
    Note:
        - Requires TAVILY_API_KEY environment variable (optional)
        - Application continues to work without web search
        - Returns error message if API key not set or search fails
    """
    name: str = "web_search"
    description: str = "Search the web for current information, research, or up-to-date data. Returns links (URLs) and query-relevant content extracts from websites. Use this when you need recent information that might not be in your training data, such as latest fitness trends, nutrition facts, exercise techniques, or health research. You will receive relevant content extracts (not full pages) along with URLs for reference."
    args_schema: type = WebSearchInput
    
    def _run(self, query: str) -> str:
        """
        Search the web using Tavily API (with caching).
        
        This method performs a web search using the Tavily API, formats results
        for agent consumption, and caches successful results.
        
        Args:
            query: Search query string
            
        Returns:
            str: Formatted search results or error message
            
        Search Configuration:
            - search_depth: "advanced" (extracts query-relevant sections, not generic summaries)
            - max_results: 4 results (manages total token count)
            - chunks_per_source: 2 (balance between detail and token usage)
            - Content limit: ~2000 chars per result (~8000-10000 tokens total)
            - Smart truncation: Cuts at sentence boundaries when needed
            
        Result Format:
            "Title: ...\nURL: ...\nContent: [query-relevant extracts]...\n\n---\n\n..."
            Includes URL and query-relevant content extracts (not full pages to avoid token limits)
            Or error message if search fails
            
        Cache Strategy:
            - Only successful results are cached (errors are not cached)
            - Cache TTL: 1 hour (web search results don't change frequently)
            - Global cache (not user-specific)
            
        Error Handling:
            - Missing API key: Returns informative error message
            - Import error: Returns installation instructions
            - API errors: Returns error message (not cached)
            
        Note:
            - Requires TAVILY_API_KEY environment variable (optional)
            - Application continues to work without web search
        """
        # Check cache first (web_search doesn't have user_id - global cache)
        # Same query returns same result for all users
        cached_result = tool_cache.get("web_search", query=query)
        if cached_result is not None:
            return cached_result
        
        # Perform search using Tavily API
        try:
            from tavily import TavilyClient
            
            # Get API key from environment
            api_key = os.getenv("TAVILY_API_KEY")
            if not api_key:
                # API key not set - return informative error message
                # Application continues to work without web search
                result = (
                    "Error: TAVILY_API_KEY is not set. Web search is unavailable. "
                    "Please set TAVILY_API_KEY in your environment variables to enable web search functionality. "
                    "This is an optional feature - the application will continue to work without it."
                )
            else:
                # Initialize Tavily client and perform search
                client = TavilyClient(api_key=api_key)
                
                # Perform advanced search for query-relevant content extraction
                # Advanced depth: Extracts query-specific sections (better than basic summaries)
                # chunks_per_source: 2 chunks per source (balance between detail and token usage)
                # Max 4 results: Keeps total token count manageable (~8000-10000 tokens max)
                # Note: Not using include_raw_content to avoid massive token usage
                response = client.search(
                    query=query,
                    search_depth="advanced",  # Advanced for query-specific content extraction
                    max_results=4,  # Limit to 4 results to manage total token count
                    chunks_per_source=2  # 2 relevant chunks per source (balance detail vs tokens)
                )
                
                if not response.get("results"):
                    result = f"No results found for query: {query}"
                else:
                    # Format results with intelligent content limits
                    # Target: ~2000-2500 chars per result = ~8000-10000 tokens total
                    formatted_results = []
                    MAX_CONTENT_PER_RESULT = 2000  # Characters per result (not tokens, but close proxy)
                    
                    for result_item in response["results"][:4]:  # Limit to 4 results
                        title = result_item.get("title", "No title")
                        url = result_item.get("url", "")
                        content = result_item.get("content", "")  # Query-relevant extracted content
                        
                        # Build result with URL prominently displayed
                        result_parts = [
                            f"Title: {title}",
                            f"URL: {url}",
                        ]
                        
                        # Include content (query-relevant extracts from advanced search)
                        # Truncate if too long to manage token usage
                        if content:
                            if len(content) > MAX_CONTENT_PER_RESULT:
                                # Truncate but keep it meaningful - try to cut at sentence boundary
                                truncated = content[:MAX_CONTENT_PER_RESULT]
                                # Try to find last sentence boundary
                                last_period = truncated.rfind('. ')
                                last_newline = truncated.rfind('\n')
                                cut_point = max(last_period, last_newline)
                                if cut_point > MAX_CONTENT_PER_RESULT * 0.8:  # Only if we keep most content
                                    content = truncated[:cut_point + 1] + f"\n\n[Content truncated - see full article at: {url}]"
                                else:
                                    content = truncated + f"...\n\n[Content truncated - see full article at: {url}]"
                            
                            result_parts.append(f"Content:\n{content}")
                        else:
                            result_parts.append("Content: No content available")
                        
                        formatted_results.append("\n".join(result_parts))
                    
                    # Join results with separator
                    result = "\n\n---\n\n".join(formatted_results)
            
        except ImportError:
            # Tavily package not installed - return installation instructions
            result = "Error: tavily-python package is not installed. Please install it with: pip install tavily-python"
        except Exception as e:
            # Other errors (API errors, network issues, etc.)
            result = f"Error performing web search: {str(e)}"
        
        # Cache the result (only cache successful results, not errors)
        # Errors are not cached so they can be retried
        if not result.startswith("Error"):
            tool_cache.set("web_search", result, query=query)
        
        return result
