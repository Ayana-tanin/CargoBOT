from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from openpyxl import load_workbook


class ExcelParseError(Exception):
    pass


@dataclass(frozen=True)
class ClientArrivalData:
    client_code: str
    products: list[str]
    rows_count: int
    declared_goods_count: int | None


@dataclass(frozen=True)
class ExcelParseResult:
    arrivals: list[ClientArrivalData]
    total_rows_seen: int

    @property
    def client_codes(self) -> list[str]:
        return [item.client_code for item in self.arrivals]


def _cell_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _parse_goods_count(value: Any) -> int | None:
    text = _cell_str(value)
    if not text:
        return None
    digits = re.sub(r"\D", "", text)
    if not digits:
        return None
    try:
        return int(digits)
    except ValueError:
        return None


def parse_arrivals_from_xlsx(path: str) -> ExcelParseResult:
    """
    Колонка B — код клиента (может повторяться).
    Колонка C — названия товаров.
    В 3-й строке каждого кода (по порядку в файле) — количество товаров.
    """
    try:
        wb = load_workbook(filename=path, read_only=True, data_only=True)
    except Exception as e:  # noqa: BLE001
        raise ExcelParseError(f"Не удалось открыть Excel: {e}") from e

    try:
        ws = wb.worksheets[0]
    except Exception as e:  # noqa: BLE001
        raise ExcelParseError("Excel файл не содержит листов") from e

    by_code: dict[str, list[tuple[Any, Any]]] = defaultdict(list)
    rows_seen = 0

    for row in ws.iter_rows(min_row=1, values_only=True):
        rows_seen += 1
        if not row:
            continue
        code = _cell_str(row[1] if len(row) > 1 else None)
        if not code:
            continue
        col_c = row[2] if len(row) > 2 else None
        col_d = row[3] if len(row) > 3 else None
        by_code[code].append((col_c, col_d))

    try:
        wb.close()
    except Exception:
        pass

    if rows_seen == 0:
        raise ExcelParseError("Excel файл пустой")
    if not by_code:
        raise ExcelParseError("В колонке B не найдено кодов клиентов")

    arrivals: list[ClientArrivalData] = []
    for code, rows in by_code.items():
        rows_count = len(rows)
        declared: int | None = None
        if rows_count >= 3:
            third_c, third_d = rows[2]
            declared = _parse_goods_count(third_d) or _parse_goods_count(third_c)

        products: list[str] = []
        for idx, (col_c, _col_d) in enumerate(rows):
            if idx == 2:
                continue
            text = _cell_str(col_c)
            if text:
                products.append(text)

        arrivals.append(
            ClientArrivalData(
                client_code=code,
                products=products,
                rows_count=rows_count,
                declared_goods_count=declared,
            )
        )

    return ExcelParseResult(arrivals=arrivals, total_rows_seen=rows_seen)


def parse_client_codes_from_xlsx(path: str) -> ExcelParseResult:
    """Совместимость: то же, что parse_arrivals_from_xlsx."""
    return parse_arrivals_from_xlsx(path)
