"""Single-use Google Books OAuth import. Tokens never enter sessions or storage."""
import asyncio
import base64
import hashlib
import re
from urllib.parse import urlencode

import httpx
from app.config import settings
from app.services import books

SCOPE = 'https://www.googleapis.com/auth/books'
TOKEN_URL = 'https://oauth2.googleapis.com/token'
API = 'https://www.googleapis.com/books/v1/mylibrary/bookshelves'
LIMIT = 1000


class GoogleBooksError(Exception):
    pass


def configured():
    return bool(settings.google_books_client_id and settings.google_books_client_secret)


def authorization_url(redirect_uri, state, verifier):
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    return 'https://accounts.google.com/o/oauth2/v2/auth?' + urlencode({
        'client_id': settings.google_books_client_id, 'redirect_uri': redirect_uri,
        'response_type': 'code', 'scope': SCOPE, 'state': state,
        'code_challenge': challenge, 'code_challenge_method': 'S256', 'access_type': 'online',
    })


async def read_library(code, redirect_uri, verifier, include_owned=False):
    # No refresh token requested or persisted; a failed fetch imports nothing.
    try:
        async with asyncio.timeout(35):
            async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
                response = await client.post(TOKEN_URL, data={
                    'client_id': settings.google_books_client_id,
                    'client_secret': settings.google_books_client_secret, 'code': code,
                    'redirect_uri': redirect_uri, 'grant_type': 'authorization_code',
                    'code_verifier': verifier,
                })
                response.raise_for_status()
                token = response.json().get('access_token')
                if not isinstance(token, str) or not token:
                    raise GoogleBooksError()
                # First occurrence wins: stronger reading evidence comes first.
                shelves = [(4, 'read'), (3, 'reading')]
                if include_owned:
                    shelves += [(2, 'want'), (1, None), (7, None)]
                found = {}
                truncated = False
                for shelf, status in shelves:
                    start = 0
                    while True:
                        r = await client.get(f'{API}/{shelf}/volumes',
                            headers={'Authorization': 'Bearer ' + token},
                            params={'startIndex': start, 'maxResults': 40, 'projection': 'full'})
                        r.raise_for_status()
                        data = r.json()
                        items = data.get('items', [])
                        if not isinstance(items, list):
                            raise GoogleBooksError()
                        for item in items:
                            book = books._google_book(item)
                            if book is None or book.external_id in found:
                                continue
                            if not isinstance(book.external_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,200}', book.external_id):
                                raise GoogleBooksError()
                            if len(book.title) > 500 or len(book.authors) > 300:
                                continue
                            found[book.external_id] = {'title': book.title, 'author': book.authors,
                                'provider_id': book.external_id, 'cover_url': book.cover_url,
                                'year': book.year, 'status': status}
                            if len(found) >= LIMIT:
                                return list(found.values()), True
                        start += len(items)
                        if not items or start >= data.get('totalItems', start):
                            break
                        # Bound pages even if remote totals or duplicate pages are inconsistent.
                        if start >= LIMIT:
                            truncated = True
                            break
                return list(found.values()), truncated
    except (httpx.HTTPError, TimeoutError, ValueError, TypeError, KeyError, AttributeError) as e:
        raise GoogleBooksError() from e
