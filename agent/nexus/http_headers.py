# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

"""HTTP header helpers shared by routers."""

from __future__ import annotations

from urllib.parse import quote


def content_disposition(disposition: str, filename: str) -> str:
    """RFC 6266 header with an ASCII fallback plus RFC 5987 UTF-8 filename.

    Starlette encodes header values as latin-1, so a raw non-ASCII name (e.g.
    an em dash in an artifact title) would crash the response.
    """
    ascii_name = (
        filename.encode("ascii", "ignore").decode("ascii").replace('"', "").replace("\\", "")
        or "download"
    )
    return f"{disposition}; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename, safe='')}"
