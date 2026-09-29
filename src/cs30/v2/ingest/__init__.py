"""Real v2 document parsers.

``openstax_parser`` is M2's vendored parser and needs the ``[parse]`` extra; it
is imported lazily by the adapter, so importing this package never requires
PyMuPDF or pdfplumber.  Reading M2's delivered JSON needs neither.
"""

from cs30.v2.ingest.openstax import (
    ADAPTER_VERSION,
    OpenStaxParsedParser,
    OpenStaxPdfParser,
    build_parser_registry,
    openstax_payload_to_document,
)

__all__ = [
    "ADAPTER_VERSION",
    "OpenStaxParsedParser",
    "OpenStaxPdfParser",
    "build_parser_registry",
    "openstax_payload_to_document",
]
