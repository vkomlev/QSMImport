# app/datasources/lms_api.py
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import requests
from requests import Response

from app.config import Settings


class LmsApiClient:
    """
    HTTP-клиент для LMS Core API.
    Инкапсулирует всю работу с эндпойнтами.
    """

    def __init__(self, settings: Settings) -> None:
        self.base_url: str = str(settings.lms_api_base_url or "").rstrip("/")
        self.api_key: Optional[str] = settings.lms_api_key
        self.timeout: float = settings.lms_api_timeout

        self.log = logging.getLogger(self.__class__.__name__)

        if not self.base_url:
            self.log.warning("⚠️ LMS API base URL is not configured.")
        if not self.api_key:
            self.log.warning("⚠️ LMS API key is not configured.")

    # -------------------------------------------------------------
    # Internal helper
    # -------------------------------------------------------------
    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict] = None,
        json: Optional[dict] = None,
    ) -> Response:
        """
        Унифицированный метод запросов.
        Добавляет api_key в query-параметры.
        Логирует запрос и ответ.
        """
        url = f"{self.base_url}{path}"

        params = params.copy() if params else {}
        if self.api_key:
            params["api_key"] = self.api_key

        self.log.debug(f"HTTP {method} {url} params={params} json={json}")

        resp = requests.request(
            method=method,
            url=url,
            params=params,
            json=json,
            timeout=self.timeout,
        )

        self.log.debug(
            f"Response {resp.status_code} {resp.text[:300]}..."
        )

        resp.raise_for_status()
        return resp

    # -------------------------------------------------------------
    # Public API methods
    # -------------------------------------------------------------

    def get_tasks_meta(self) -> Dict[str, Any]:
        """
        GET /api/v1/meta/tasks
        Возвращает словарь:
        {
          "difficulties": [...],
          "courses": [...],
          "tags": [...],
          "task_types": [...],
          "version": 1
        }
        """
        resp = self._request("GET", "/api/v1/meta/tasks")
        return resp.json()

    def validate_task(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        POST /api/v1/tasks/validate
        payload — TaskValidateRequest
        Возвращает TaskValidateResponse.
        """
        resp = self._request("POST", "/api/v1/tasks/validate", json=payload)
        return resp.json()

    def bulk_upsert_tasks(self, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        POST /api/v1/tasks/bulk-upsert
        items — список TaskUpsertItem
        Возвращает TaskBulkUpsertResponse.
        """
        payload = {"items": items}
        resp = self._request("POST", "/api/v1/tasks/bulk-upsert", json=payload)
        return resp.json()

    def find_tasks_by_external(self, uids: List[str]) -> Dict[str, Any]:
        """
        POST /api/v1/tasks/find-by-external
        Возвращает:
        {
           "items": [
               {"external_uid": "...", "id": 123},
               ...
           ]
        }
        """
        payload = {"uids": uids}
        resp = self._request("POST", "/api/v1/tasks/find-by-external", json=payload)
        return resp.json()

    def get_task_by_external(self, uid: str) -> Optional[Dict[str, Any]]:
        """
        GET /api/v1/tasks/by-external/{external_uid}
        Возвращает TaskRead или None, если 404.
        """
        try:
            resp = self._request("GET", f"/api/v1/tasks/by-external/{uid}")
            return resp.json()
        except requests.HTTPError as ex:
            if ex.response is not None and ex.response.status_code == 404:
                return None
            raise
