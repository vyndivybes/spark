"""Repository-scoped GitHub reads through the host's existing gh sign-in.

Credentials remain in GitHub CLI storage. Tool callers cannot choose commands,
repositories, endpoints, or write operations.
"""
import argparse
import asyncio
import json
import re
import shutil
import subprocess


class RepositoryReader:
    def __init__(self, repository):
        if not isinstance(repository, str) or not re.fullmatch(
                r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}', repository):
            raise ValueError('Configure a GitHub owner/repository on the host.')
        self.repository = repository

    def read(self, operation):
        commands = {
            'repository': ['repo', 'view', self.repository, '--json',
                           'nameWithOwner,url,description,defaultBranchRef,isPrivate'],
            'pull_requests': ['pr', 'list', '--repo', self.repository, '--state', 'all',
                              '--limit', '10', '--json', 'number,title,state,url'],
            'issues': ['issue', 'list', '--repo', self.repository, '--state', 'all',
                       '--limit', '10', '--json', 'number,title,state,url'],
        }
        if operation not in commands:
            raise ValueError('Unsupported GitHub read operation.')
        command = shutil.which('gh')
        if not command:
            return {'ok':False, 'message':'Install GitHub CLI and sign in on this PC.'}
        try:
            result = subprocess.run([command, *commands[operation]], stdin=subprocess.DEVNULL,
                                    capture_output=True, text=True, encoding='utf-8',
                                    timeout=25, shell=False)
            if result.returncode:
                return {'ok':False, 'message':'GitHub read failed. Check CLI sign-in and repository access.'}
            if len(result.stdout.encode('utf-8')) > 200_000:
                return {'ok':False, 'message':'GitHub response exceeded its limit.'}
            return {'ok':True, 'repository':self.repository, 'operation':operation,
                    'data':json.loads(result.stdout), 'read_only':True}
        except (OSError, subprocess.TimeoutExpired, ValueError):
            return {'ok':False, 'message':'GitHub CLI is unavailable or returned an invalid response.'}


def main():
    parser = argparse.ArgumentParser(description='SPARK read-only GitHub repository MCP')
    parser.add_argument('--repository', required=True)
    reader = RepositoryReader(parser.parse_args().repository)
    from mcp.server.fastmcp import FastMCP
    server = FastMCP('spark-github')

    @server.tool()
    async def github_repository_status() -> dict:
        """Read metadata for the host-selected GitHub repository."""
        return await asyncio.to_thread(reader.read, 'repository')

    @server.tool()
    async def github_list_pull_requests() -> dict:
        """Read the ten most recent pull requests in the host-selected repository."""
        return await asyncio.to_thread(reader.read, 'pull_requests')

    @server.tool()
    async def github_list_issues() -> dict:
        """Read the ten most recent issues in the host-selected repository."""
        return await asyncio.to_thread(reader.read, 'issues')

    server.run(transport='stdio')


if __name__ == '__main__':
    main()
