"""仅用于离线协议测试的本地 MCP Server，不连接 Tavily 或任何外部系统。"""
import asyncio
import os

from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

server = Server('local-tavily-contract-fixture')


@server.list_tools()
async def tools():
    return [Tool(name=name, description='离线测试工具', inputSchema={
        'type': 'object', 'properties': {'query': {'type': 'string'}}, 'required': ['query']})
        for name in ['tavily-search', 'tavily-crawl']]


@server.call_tool()
async def call(name, arguments):
    assert name == 'tavily-search', '不得调用爬取工具'
    assert os.environ.get('TAVILY_API_KEY') == 'local-test-only', '必须通过 env 注入测试凭据'
    assert arguments['query'] == 'polyamide moisture processing technical reference'
    assert arguments['max_results'] == 3
    assert arguments['search_depth'] == 'basic'
    return [TextContent(type='text', text='Detailed Results:\n\nTitle: Local MCP fixture\n'
                        'URL: https://example.org/local-mcp\nContent: Offline fixture, not a real Tavily search.')]


async def main():
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == '__main__':
    asyncio.run(main())
