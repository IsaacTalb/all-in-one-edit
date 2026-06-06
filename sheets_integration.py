"""Google Sheets adapter for the daily pipeline."""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Dict, List, Optional


class SheetsError(RuntimeError):
    pass



def fetch_sheet_rows(sheet_id: str, worksheet_name: str = "Sheet1") -> List[Dict[str, str]]:
    try:
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build
    except Exception:
        csv_path = Path(r"C:\isc-kfc\all-in-one-edit\sheet_rows.csv")
        if csv_path.exists():
            with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
                return list(csv.DictReader(f))
        raise SheetsError("Google Sheets libraries are unavailable and no sheet_rows.csv fallback exists.")

    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_file(
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"],
        scopes=scopes,
    )
    service = build("sheets", "v4", credentials=creds)
    range_name = f"{worksheet_name}!A:Z"
    response = service.spreadsheets().values().get(spreadsheetId=sheet_id, range=range_name).execute()
    values = response.get("values", [])
    if not values:
        return []
    headers = values[0]
    rows: List[Dict[str, str]] = []
    for row in values[1:]:
        item = {headers[i]: row[i] if i < len(row) else "" for i in range(len(headers))}
        rows.append(item)
    return rows



def update_sheet_row_status(sheet_id: str, worksheet_name: str, row_id: str, status: str) -> None:
    try:
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build
    except Exception:
        return

    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_file(
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"],
        scopes=scopes,
    )
    service = build("sheets", "v4", credentials=creds)
    # Assumes column B is Status and first row is headers. This can be adjusted once the sheet schema is fixed.
    values = service.spreadsheets().values().get(spreadsheetId=sheet_id, range=f"{worksheet_name}!A:Z").execute().get("values", [])
    if not values:
        return
    header = values[0]
    status_col = None
    id_col = None
    for idx, name in enumerate(header):
        if name.strip().lower() == "status":
            status_col = idx
        if name.strip().lower() in {"rowid", "id"}:
            id_col = idx
    if status_col is None or id_col is None:
        return
    for row_idx, row in enumerate(values[1:], start=2):
        if id_col < len(row) and str(row[id_col]) == str(row_id):
            col_letter = chr(ord("A") + status_col)
            service.spreadsheets().values().update(
                spreadsheetId=sheet_id,
                range=f"{worksheet_name}!{col_letter}{row_idx}",
                valueInputOption="RAW",
                body={"values": [[status]]},
            ).execute()
            return
