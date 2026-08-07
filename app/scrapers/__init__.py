"""Parser dell'HTML di apps.odoo.com."""

from .detail import parse_detail
from .listing import ListingResult, parse_listing

__all__ = ["ListingResult", "parse_detail", "parse_listing"]
