"""Real v2 document parsers.

``openstax_parser`` is M2's vendored parser and needs the ``[parse]`` extra; it
is imported lazily by the adapter, so importing this package never requires
PyMuPDF or pdfplumber.
"""

from cs30.v2.ingest.openstax import (
    ADAPTER_VERSION,
    OpenStaxPdfParser,
    build_parser_registry,
    openstax_payload_to_document,
)

__all__ = [
    "ADAPTER_VERSION",
    "OpenStaxPdfParser",
    "build_parser_registry",
    "openstax_payload_to_document",
]
