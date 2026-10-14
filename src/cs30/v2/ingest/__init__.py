"""Real v2 document parsers.

OpenStax PDF parsing uses M2's vendored parser and needs the ``[parse]`` extra;
it is imported lazily, so importing this package never requires PyMuPDF or
pdfplumber. Reading the pinned OpenStax and CK-12 JSON deliveries needs neither.
"""

from cs30.v2.ingest.ck12 import CK12ParsedParser, ck12_payload_to_document
from cs30.v2.ingest.openstax import (
    ADAPTER_VERSION,
    OpenStaxParsedParser,
    OpenStaxPdfParser,
    build_parser_registry,
    openstax_payload_to_document,
)

__all__ = [
    "ADAPTER_VERSION",
    "CK12ParsedParser",
    "OpenStaxParsedParser",
    "OpenStaxPdfParser",
    "build_parser_registry",
    "ck12_payload_to_document",
    "openstax_payload_to_document",
]
