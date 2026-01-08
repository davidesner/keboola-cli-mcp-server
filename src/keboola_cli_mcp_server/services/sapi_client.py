"""Simple Storage API client for docs queries."""

from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx
from pydantic import BaseModel, Field


class DocsQuestionResponse(BaseModel):
    """The AI service response to a docs question."""

    text: str = Field(description='Text of the answer to a documentation query.')
    source_urls: list[str] = Field(
        description='List of URLs to the sources of the answer.',
        default_factory=list,
        alias='sourceUrls',
    )


class AIServiceClient:
    """Simple async client for Keboola AI Service."""

    def __init__(self, base_url: str, token: str):
        self.base_url = base_url
        self.token = token
        self.headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'X-StorageAPI-Token': token,
        }
        self.timeout = httpx.Timeout(connect=5.0, read=60.0, write=10.0, pool=5.0)

    @classmethod
    def from_storage_url(cls, storage_api_url: str, token: str) -> 'AIServiceClient':
        """
        Create an AI service client from a Storage API URL.

        The AI service URL is derived by replacing 'connection.' with 'ai.' in the hostname.
        For example:
            https://connection.us-east4.gcp.keboola.com -> https://ai.us-east4.gcp.keboola.com
        """
        parsed = urlparse(storage_api_url)
        hostname = parsed.netloc

        # Replace 'connection.' with 'ai.' to get AI service URL
        if hostname.startswith('connection.'):
            ai_hostname = hostname.replace('connection.', 'ai.', 1)
        else:
            # Fallback: prepend 'ai.' to hostname suffix
            parts = hostname.split('.', 1)
            if len(parts) > 1:
                ai_hostname = f'ai.{parts[1]}'
            else:
                ai_hostname = f'ai.{hostname}'

        ai_url = urlunparse(('https', ai_hostname, '', '', '', ''))
        return cls(base_url=ai_url, token=token)

    async def docs_question(self, query: str) -> DocsQuestionResponse:
        """
        Answers a question using the Keboola documentation as a source.

        Args:
            query: The query to answer

        Returns:
            Response containing the answer and source URLs
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f'{self.base_url}/docs/question',
                json={'query': query},
                headers=self.headers,
            )
            response.raise_for_status()
            return DocsQuestionResponse.model_validate(response.json())
