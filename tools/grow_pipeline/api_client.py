"""API client for Grow API with pagination support."""
import logging
from typing import Generator, Dict, Any, Optional
import requests
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

logger = logging.getLogger(__name__)


class APIError(Exception):
    """Raised when API request fails."""
    pass


class GrowAPIClient:
    """Client for interacting with Grow API."""

    BASE_URL = "https://grow-api.leveldata.com/external"
    ASSIGNMENTS_ENDPOINT = "/assignments"

    def __init__(self, bearer_token: str):
        """
        Initialize API client.

        Args:
            bearer_token: Bearer token for authentication
        """
        self.bearer_token = bearer_token
        self.headers = {
            "Authorization": f"Bearer {bearer_token}",
            "Content-Type": "application/json",
        }

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=2, min=2, max=32),
        retry=retry_if_exception_type((requests.exceptions.Timeout, APIError)),
        reraise=True,
    )
    def _make_request(self, url: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Make HTTP request with retry logic.

        Args:
            url: Full URL to request
            params: Query parameters

        Returns:
            JSON response as dictionary

        Raises:
            APIError: If request fails after retries
        """
        try:
            response = requests.get(
                url,
                headers=self.headers,
                params=params,
                timeout=30,
            )

            # Retry on server errors and rate limits
            if response.status_code in [429, 500, 502, 503, 504]:
                logger.warning(
                    f"Retryable error {response.status_code}: {response.text}"
                )
                raise APIError(f"HTTP {response.status_code}: {response.text}")

            # Don't retry on client errors
            if response.status_code >= 400:
                logger.error(
                    f"Client error {response.status_code}: {response.text}"
                )
                raise APIError(
                    f"API request failed with status {response.status_code}: {response.text}"
                )

            response.raise_for_status()
            return response.json()

        except requests.exceptions.Timeout as e:
            logger.warning(f"Request timeout: {str(e)}")
            raise
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed: {str(e)}")
            raise APIError(f"Request failed: {str(e)}")

    def _detect_pagination_type(self, response: Dict[str, Any]) -> Optional[str]:
        """
        Detect pagination mechanism from API response.

        Args:
            response: API response dictionary

        Returns:
            Pagination type: 'cursor', 'offset', 'page', 'skip', or None
        """
        # Check for skip-based pagination (common with count/limit/skip)
        if "count" in response and "limit" in response:
            return "skip"

        # Check for cursor-based pagination
        if "next_cursor" in response or "cursor" in response:
            return "cursor"

        # Check for offset-based pagination
        if "offset" in response or "next_offset" in response:
            return "offset"

        # Check for page-based pagination
        if "page" in response or "next_page" in response:
            return "page"

        # Check for metadata with pagination info
        if "meta" in response or "metadata" in response or "pagination" in response:
            meta = response.get("meta") or response.get("metadata") or response.get("pagination", {})
            if "next_page" in meta or "page" in meta:
                return "page"
            if "next_cursor" in meta or "cursor" in meta:
                return "cursor"
            if "offset" in meta:
                return "offset"

        # No pagination detected
        return None

    def _get_next_params(
        self,
        pagination_type: str,
        response: Dict[str, Any],
        current_params: Dict[str, Any],
        records_fetched_so_far: int,
    ) -> Optional[Dict[str, Any]]:
        """
        Get parameters for next page based on pagination type.

        Args:
            pagination_type: Type of pagination ('cursor', 'offset', 'page', 'skip')
            response: Current API response
            current_params: Current request parameters
            records_fetched_so_far: Total records fetched so far

        Returns:
            Parameters for next page, or None if no more pages
        """
        meta = response.get("meta") or response.get("metadata") or response.get("pagination") or response

        if pagination_type == "skip":
            # Skip-based pagination (count/limit/skip)
            total_count = response.get("count", 0)
            limit = response.get("limit") or current_params.get("limit") or 100
            current_skip = current_params.get("skip", 0)

            # Check if we've fetched all records
            if records_fetched_so_far >= total_count:
                return None

            # Calculate next skip value
            params = current_params.copy()
            params["skip"] = current_skip + limit
            params["limit"] = limit
            return params

        elif pagination_type == "cursor":
            next_cursor = meta.get("next_cursor") or response.get("next_cursor")
            if next_cursor:
                params = current_params.copy()
                params["cursor"] = next_cursor
                return params

        elif pagination_type == "offset":
            offset = meta.get("offset", 0)
            limit = meta.get("limit", 100)
            total = meta.get("total")

            # Check if we've reached the end
            if total and offset + limit >= total:
                return None

            params = current_params.copy()
            params["offset"] = offset + limit
            if "limit" not in params:
                params["limit"] = limit
            return params

        elif pagination_type == "page":
            current_page = meta.get("page", 1)
            total_pages = meta.get("total_pages") or meta.get("totalPages")
            next_page = meta.get("next_page")

            # Use explicit next_page if provided
            if next_page:
                params = current_params.copy()
                params["page"] = next_page
                return params

            # Check if we've reached the last page
            if total_pages and current_page >= total_pages:
                return None

            # Try incrementing page number
            params = current_params.copy()
            params["page"] = current_page + 1
            return params

        return None

    def fetch_assignments(self) -> Generator[Dict[str, Any], None, None]:
        """
        Fetch all assignments from API with automatic pagination.

        Yields:
            Individual assignment records (all types)

        Raises:
            APIError: If API request fails
        """
        url = f"{self.BASE_URL}{self.ASSIGNMENTS_ENDPOINT}"
        params = {}  # No type filter - fetch all assignments

        page_num = 0
        total_fetched = 0
        pagination_type = None

        logger.info("Starting to fetch all assignments from Grow API")

        while True:
            page_num += 1
            logger.info(f"Fetching page {page_num} (total records so far: {total_fetched})")

            try:
                response = self._make_request(url, params)
            except Exception as e:
                logger.error(f"Failed to fetch page {page_num}: {str(e)}")
                raise

            # Detect pagination on first request
            if page_num == 1:
                pagination_type = self._detect_pagination_type(response)
                if pagination_type:
                    logger.info(f"Detected pagination type: {pagination_type}")
                else:
                    logger.info("No pagination detected, assuming single page response")

            # Extract records from response
            # Common patterns: response is list, or response has 'data', 'results', 'items', 'assignments' key
            records = None
            if isinstance(response, list):
                records = response
            else:
                for key in ["data", "results", "items", "assignments", "records"]:
                    if key in response:
                        records = response[key]
                        break

            if records is None:
                logger.warning(f"Could not find records in response. Keys: {response.keys()}")
                # If first page and no records found, might be the records themselves
                if page_num == 1 and isinstance(response, dict) and "id" in response:
                    records = [response]
                else:
                    break

            # Yield individual records
            for record in records:
                yield record
                total_fetched += 1

            logger.info(f"Page {page_num}: fetched {len(records)} records")

            # Check if there are more pages
            if not pagination_type:
                # No pagination, we're done
                break

            # Get parameters for next page
            params = self._get_next_params(pagination_type, response, params, total_fetched)
            if not params:
                logger.info("Reached last page")
                break

            # Safety check: if we got 0 records, stop pagination
            if len(records) == 0:
                logger.info("Received empty page, stopping pagination")
                break

        logger.info(f"Finished fetching. Total records: {total_fetched}")
