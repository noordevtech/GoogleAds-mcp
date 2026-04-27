"""Reporting and analytics tools for Google Ads API v20."""

from typing import Any, Dict, List, Optional
from datetime import datetime, date, timedelta
import structlog

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

from .utils import (
    micros_to_currency,
    format_date_range,
    derived_metrics,
    gaql_date_filter,
)

logger = structlog.get_logger(__name__)


# Friendly metric names that callers may pass in -> real GAQL field names.
# Add new aliases here when callers ask for them by their common name.
_GAQL_METRIC_ALIASES = {
    "conversion_rate": "conversions_from_interactions_rate",
    "conversion_value": "conversions_value",
    "cpc": "average_cpc",
    "cpm": "average_cpm",
}


# Date ranges accepted by Google Ads GAQL. Validate user input against this
# allow-list before splicing into a query.
_GAQL_DATE_RANGES = frozenset({
    "TODAY", "YESTERDAY",
    "LAST_7_DAYS", "LAST_14_DAYS", "LAST_30_DAYS", "LAST_90_DAYS",
    "THIS_MONTH", "LAST_MONTH",
    "THIS_WEEK_MON_TODAY", "THIS_WEEK_SUN_TODAY",
    "LAST_WEEK_MON_SUN", "LAST_WEEK_SUN_SAT",
    "LAST_BUSINESS_WEEK",
    "THIS_QUARTER", "LAST_QUARTER",
    "THIS_YEAR", "LAST_YEAR",
    "ALL_TIME",
})


class ReportingTools:
    """Reporting and analytics tools."""
    
    def __init__(self, auth_manager, error_handler):
        self.auth_manager = auth_manager
        self.error_handler = error_handler
        
    async def get_campaign_performance(
        self,
        customer_id: str,
        campaign_id: Optional[str] = None,
        date_range: str = "LAST_30_DAYS",
        metrics: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Get campaign performance metrics.

        ``date_range`` accepts a Google Ads named range, 'ALL_TIME' for
        lifetime aggregates, or a custom 'YYYY-MM-DD,YYYY-MM-DD' window.
        """
        try:
            date_clause, date_label = gaql_date_filter(date_range)
        except ValueError as e:
            return {"success": False, "error": str(e)}

        try:
            client = self.auth_manager.get_client(customer_id)
            googleads_service = client.get_service("GoogleAdsService")

            # Default metrics if not specified. Note: friendly aliases like
            # 'conversion_rate' are translated to the real GAQL field name in
            # _GAQL_METRIC_ALIASES below.
            if not metrics:
                metrics = [
                    "clicks", "impressions", "cost_micros", "conversions",
                    "conversions_value", "cost_per_conversion",
                    "ctr", "average_cpc", "conversion_rate",
                ]

            gaql_metrics = [_GAQL_METRIC_ALIASES.get(m, m) for m in metrics]
            metrics_fields = ", ".join([f"metrics.{m}" for m in gaql_metrics])

            where_parts = []
            if date_clause:
                where_parts.append(date_clause)
            if campaign_id:
                where_parts.append(f"campaign.id = {campaign_id}")
            where_str = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""

            query = f"""
                SELECT
                    campaign.id,
                    campaign.name,
                    campaign.status,
                    {metrics_fields}
                FROM campaign
                {where_str}
                ORDER BY metrics.cost_micros DESC
            """

            response = googleads_service.search(
                customer_id=customer_id,
                query=query,
            )

            campaigns = []
            totals = {
                "clicks": 0,
                "impressions": 0,
                "cost": 0.0,
                "conversions": 0.0,
                "conversions_value": 0.0,
            }

            for row in response:
                clicks = row.metrics.clicks
                impressions = row.metrics.impressions
                cost = micros_to_currency(row.metrics.cost_micros)
                conversions = row.metrics.conversions
                conv_value = row.metrics.conversions_value

                campaigns.append({
                    "id": str(row.campaign.id),
                    "name": row.campaign.name,
                    "status": row.campaign.status.name,
                    "metrics": {
                        "clicks": clicks,
                        "impressions": impressions,
                        "cost": cost,
                        "conversions": conversions,
                        "conversions_value": conv_value,
                        "average_cpc": micros_to_currency(row.metrics.average_cpc),
                        **derived_metrics(impressions, clicks, cost, conversions, conv_value),
                    },
                })

                totals["clicks"] += clicks
                totals["impressions"] += impressions
                totals["cost"] += cost
                totals["conversions"] += conversions
                totals["conversions_value"] += conv_value

            total_metrics = {
                **totals,
                **derived_metrics(
                    totals["impressions"],
                    totals["clicks"],
                    totals["cost"],
                    totals["conversions"],
                    totals["conversions_value"],
                ),
            }

            return {
                "success": True,
                "date_range": date_label,
                "campaigns": campaigns,
                "total_metrics": total_metrics,
                "count": len(campaigns),
            }
            
        except GoogleAdsException as e:
            logger.error(f"Failed to get campaign performance: {e}")
            return self.error_handler.format_error_response(e)
        except Exception as e:
            logger.error(f"Unexpected error getting campaign performance: {e}")
            raise
            
    async def get_ad_group_performance(
        self,
        customer_id: str,
        ad_group_id: Optional[str] = None,
        date_range: str = "LAST_30_DAYS",
    ) -> Dict[str, Any]:
        """Get ad group performance metrics.

        ``date_range`` accepts a Google Ads named range, 'ALL_TIME', or a
        custom 'YYYY-MM-DD,YYYY-MM-DD' window.
        """
        try:
            date_clause, date_label = gaql_date_filter(date_range)
        except ValueError as e:
            return {"success": False, "error": str(e)}

        try:
            client = self.auth_manager.get_client(customer_id)
            googleads_service = client.get_service("GoogleAdsService")

            where_parts = []
            if date_clause:
                where_parts.append(date_clause)
            if ad_group_id:
                where_parts.append(f"ad_group.id = {ad_group_id}")
            where_str = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""

            query = f"""
                SELECT
                    ad_group.id,
                    ad_group.name,
                    ad_group.status,
                    campaign.id,
                    campaign.name,
                    metrics.clicks,
                    metrics.impressions,
                    metrics.cost_micros,
                    metrics.conversions,
                    metrics.conversions_value,
                    metrics.ctr,
                    metrics.average_cpc,
                    metrics.conversions_from_interactions_rate,
                    metrics.cost_per_conversion
                FROM ad_group
                {where_str}
                ORDER BY metrics.cost_micros DESC
            """
            
            response = googleads_service.search(
                customer_id=customer_id,
                query=query,
            )
            
            ad_groups = []
            for row in response:
                clicks = row.metrics.clicks
                impressions = row.metrics.impressions
                cost = micros_to_currency(row.metrics.cost_micros)
                conversions = row.metrics.conversions
                conv_value = row.metrics.conversions_value
                ad_groups.append({
                    "id": str(row.ad_group.id),
                    "name": row.ad_group.name,
                    "status": row.ad_group.status.name,
                    "campaign": {
                        "id": str(row.campaign.id),
                        "name": row.campaign.name,
                    },
                    "metrics": {
                        "clicks": clicks,
                        "impressions": impressions,
                        "cost": cost,
                        "conversions": conversions,
                        "conversions_value": conv_value,
                        "average_cpc": micros_to_currency(row.metrics.average_cpc),
                        **derived_metrics(impressions, clicks, cost, conversions, conv_value),
                    },
                })
                
            return {
                "success": True,
                "date_range": date_label,
                "ad_groups": ad_groups,
                "count": len(ad_groups),
            }
            
        except GoogleAdsException as e:
            logger.error(f"Failed to get ad group performance: {e}")
            return self.error_handler.format_error_response(e)
        except Exception as e:
            logger.error(f"Unexpected error getting ad group performance: {e}")
            raise
            
    async def get_keyword_performance(
        self,
        customer_id: str,
        ad_group_id: Optional[str] = None,
        date_range: str = "LAST_30_DAYS",
    ) -> Dict[str, Any]:
        """Get keyword performance metrics.

        ``date_range`` accepts a Google Ads named range, 'ALL_TIME', or a
        custom 'YYYY-MM-DD,YYYY-MM-DD' window.
        """
        try:
            date_clause, date_label = gaql_date_filter(date_range)
        except ValueError as e:
            return {"success": False, "error": str(e)}

        try:
            client = self.auth_manager.get_client(customer_id)
            googleads_service = client.get_service("GoogleAdsService")

            where_parts = ["ad_group_criterion.type = 'KEYWORD'"]
            if date_clause:
                where_parts.append(date_clause)
            if ad_group_id:
                where_parts.append(f"ad_group.id = {ad_group_id}")

            query = f"""
                SELECT
                    ad_group_criterion.keyword.text,
                    ad_group_criterion.keyword.match_type,
                    ad_group_criterion.status,
                    ad_group.id,
                    ad_group.name,
                    campaign.id,
                    campaign.name,
                    metrics.clicks,
                    metrics.impressions,
                    metrics.cost_micros,
                    metrics.conversions,
                    metrics.conversions_value,
                    metrics.ctr,
                    metrics.average_cpc,
                    metrics.conversions_from_interactions_rate
                FROM keyword_view
                WHERE {" AND ".join(where_parts)}
                ORDER BY metrics.impressions DESC
            """
            
            response = googleads_service.search(
                customer_id=customer_id,
                query=query,
            )
            
            keywords = []
            for row in response:
                clicks = row.metrics.clicks
                impressions = row.metrics.impressions
                cost = micros_to_currency(row.metrics.cost_micros)
                conversions = row.metrics.conversions
                conv_value = row.metrics.conversions_value
                keywords.append({
                    "text": row.ad_group_criterion.keyword.text,
                    "match_type": row.ad_group_criterion.keyword.match_type.name,
                    "status": row.ad_group_criterion.status.name,
                    "ad_group": {
                        "id": str(row.ad_group.id),
                        "name": row.ad_group.name,
                    },
                    "campaign": {
                        "id": str(row.campaign.id),
                        "name": row.campaign.name,
                    },
                    "metrics": {
                        "clicks": clicks,
                        "impressions": impressions,
                        "cost": cost,
                        "conversions": conversions,
                        "conversions_value": conv_value,
                        "average_cpc": micros_to_currency(row.metrics.average_cpc),
                        **derived_metrics(impressions, clicks, cost, conversions, conv_value),
                    },
                })
                
            return {
                "success": True,
                "date_range": date_label,
                "keywords": keywords,
                "count": len(keywords),
            }
            
        except GoogleAdsException as e:
            logger.error(f"Failed to get keyword performance: {e}")
            return self.error_handler.format_error_response(e)
        except Exception as e:
            logger.error(f"Unexpected error getting keyword performance: {e}")
            raise
            
    async def run_gaql_query(self, customer_id: str, query: str) -> Dict[str, Any]:
        """Run custom GAQL queries."""
        try:
            client = self.auth_manager.get_client(customer_id)
            googleads_service = client.get_service("GoogleAdsService")
            
            # Clean up the query
            query = query.strip()
            if query.endswith(";"):
                query = query[:-1]
                
            # Use search_stream for large result sets
            stream = googleads_service.search_stream(
                customer_id=customer_id,
                query=query,
            )
            
            rows = []
            fields = set()
            
            for batch in stream:
                for row in batch.results:
                    row_data = {}
                    
                    # Extract fields dynamically
                    for field_name in dir(row):
                        if not field_name.startswith("_"):
                            field_value = getattr(row, field_name)
                            if hasattr(field_value, "__class__"):
                                # Handle nested objects
                                nested_data = self._extract_nested_fields(field_value)
                                if nested_data:
                                    row_data[field_name] = nested_data
                                    fields.add(field_name)
                                    
                    rows.append(row_data)
                    
            return {
                "success": True,
                "query": query,
                "rows": rows,
                "row_count": len(rows),
                "fields": list(fields),
            }
            
        except GoogleAdsException as e:
            logger.error(f"Failed to run GAQL query: {e}")
            return self.error_handler.format_error_response(e)
        except Exception as e:
            logger.error(f"Unexpected error running GAQL query: {e}")
            raise
            
    def _extract_nested_fields(self, obj) -> Dict[str, Any]:
        """Extract fields from nested objects."""
        data = {}
        
        for field_name in dir(obj):
            if not field_name.startswith("_"):
                try:
                    field_value = getattr(obj, field_name)
                    
                    # Skip methods
                    if callable(field_value):
                        continue
                        
                    # Handle enums
                    if hasattr(field_value, "name"):
                        data[field_name] = field_value.name
                    # Handle numbers
                    elif isinstance(field_value, (int, float)):
                        # Convert micros to currency
                        if field_name.endswith("_micros"):
                            data[field_name.replace("_micros", "")] = micros_to_currency(field_value)
                        else:
                            data[field_name] = field_value
                    # Handle strings and booleans
                    elif isinstance(field_value, (str, bool)):
                        data[field_name] = field_value
                    # Handle nested objects recursively
                    elif hasattr(field_value, "__class__"):
                        nested = self._extract_nested_fields(field_value)
                        if nested:
                            data[field_name] = nested
                            
                except Exception:
                    continue
                    
        return data
        
    async def get_search_terms_report(
        self,
        customer_id: str,
        campaign_id: Optional[str] = None,
        ad_group_id: Optional[str] = None,
        date_range: str = "LAST_7_DAYS",
    ) -> Dict[str, Any]:
        """Get search terms report.

        ``date_range`` accepts a Google Ads named range, 'ALL_TIME', or a
        custom 'YYYY-MM-DD,YYYY-MM-DD' window. Note: search_term_view data
        retention is capped at ~24 months by Google regardless.
        """
        try:
            date_clause, date_label = gaql_date_filter(date_range)
        except ValueError as e:
            return {"success": False, "error": str(e)}

        try:
            client = self.auth_manager.get_client(customer_id)
            googleads_service = client.get_service("GoogleAdsService")

            where_parts = []
            if date_clause:
                where_parts.append(date_clause)
            if campaign_id:
                where_parts.append(f"campaign.id = {campaign_id}")
            if ad_group_id:
                where_parts.append(f"ad_group.id = {ad_group_id}")
            where_str = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""

            query = f"""
                SELECT
                    search_term_view.search_term,
                    search_term_view.status,
                    campaign.id,
                    campaign.name,
                    ad_group.id,
                    ad_group.name,
                    metrics.clicks,
                    metrics.impressions,
                    metrics.cost_micros,
                    metrics.conversions,
                    metrics.ctr,
                    metrics.average_cpc
                FROM search_term_view
                {where_str}
                ORDER BY metrics.impressions DESC
                LIMIT 100
            """
            
            response = googleads_service.search(
                customer_id=customer_id,
                query=query,
            )
            
            search_terms = []
            for row in response:
                search_terms.append({
                    "search_term": row.search_term_view.search_term,
                    "status": row.search_term_view.status.name,
                    "campaign": {
                        "id": str(row.campaign.id),
                        "name": row.campaign.name,
                    },
                    "ad_group": {
                        "id": str(row.ad_group.id),
                        "name": row.ad_group.name,
                    },
                    "metrics": {
                        "clicks": row.metrics.clicks,
                        "impressions": row.metrics.impressions,
                        "cost": micros_to_currency(row.metrics.cost_micros),
                        "conversions": row.metrics.conversions,
                        "ctr": f"{row.metrics.ctr:.2%}",
                        "average_cpc": micros_to_currency(row.metrics.average_cpc),
                    },
                })
                
            return {
                "success": True,
                "date_range": date_label,
                "search_terms": search_terms,
                "count": len(search_terms),
            }
            
        except GoogleAdsException as e:
            logger.error(f"Failed to get search terms report: {e}")
            return self.error_handler.format_error_response(e)
        except Exception as e:
            logger.error(f"Unexpected error getting search terms report: {e}")
            raise

    async def list_search_terms(
        self,
        customer_id: str,
        campaign_id: Optional[str] = None,
        ad_group_id: Optional[str] = None,
        date_range: str = "LAST_30_DAYS",
        min_impressions: int = 1,
        limit: int = 200,
        only_zero_conversions: bool = False,
    ) -> Dict[str, Any]:
        """List actual user search queries that triggered ads, with the
        keyword that matched and full performance metrics.

        This is the primary tool for finding wasted ad spend during an
        account audit. Run it early to identify queries that cost money but
        don't convert, then add them as negative keywords. Each row also
        includes the search-term status (ADDED / EXCLUDED / ADDED_EXCLUDED /
        NONE) so you can tell at a glance which queries are still actionable.

        Args:
            customer_id: Account ID to query (required, hyphens accepted).
            campaign_id: Optional campaign filter.
            ad_group_id: Optional ad group filter.
            date_range: Google Ads date range enum (default LAST_30_DAYS).
            min_impressions: Drop terms below this impression count (default 1).
            limit: Cap on rows returned. Hard-capped at 1000.
            only_zero_conversions: If True, only return terms with 0 conversions
                (the "find waste" filter).
        """
        # Validate date range; supports named ranges, ALL_TIME, and custom
        # YYYY-MM-DD,YYYY-MM-DD windows. Note: search_term_view retention is
        # capped at ~24 months by Google regardless of the requested range.
        try:
            date_clause, date_label = gaql_date_filter(date_range)
        except ValueError as e:
            return {"success": False, "error": str(e)}

        try:
            min_impressions = max(0, int(min_impressions))
            limit = min(1000, max(1, int(limit)))
        except (TypeError, ValueError):
            return {"success": False, "error": "min_impressions and limit must be integers"}

        def _digits_only(value: Optional[str], field: str) -> Optional[str]:
            if value is None:
                return None
            cleaned = str(value).replace("-", "").strip()
            if not cleaned.isdigit():
                raise ValueError(f"{field} must be numeric, got {value!r}")
            return cleaned

        try:
            campaign_id_clean = _digits_only(campaign_id, "campaign_id")
            ad_group_id_clean = _digits_only(ad_group_id, "ad_group_id")
        except ValueError as e:
            return {"success": False, "error": str(e)}

        try:
            client = self.auth_manager.get_client(customer_id)
            googleads_service = client.get_service("GoogleAdsService")

            where_clauses = [f"metrics.impressions >= {min_impressions}"]
            if date_clause:
                where_clauses.append(date_clause)
            if campaign_id_clean:
                where_clauses.append(f"campaign.id = {campaign_id_clean}")
            if ad_group_id_clean:
                where_clauses.append(f"ad_group.id = {ad_group_id_clean}")
            if only_zero_conversions:
                where_clauses.append("metrics.conversions = 0")

            query = f"""
                SELECT
                    search_term_view.search_term,
                    search_term_view.status,
                    segments.keyword.info.text,
                    segments.keyword.info.match_type,
                    ad_group.id,
                    ad_group.name,
                    campaign.id,
                    campaign.name,
                    metrics.impressions,
                    metrics.clicks,
                    metrics.cost_micros,
                    metrics.conversions,
                    metrics.conversions_value,
                    metrics.average_cpc,
                    metrics.ctr
                FROM search_term_view
                WHERE {" AND ".join(where_clauses)}
                ORDER BY metrics.cost_micros DESC
                LIMIT {limit}
            """

            response = googleads_service.search(
                customer_id=customer_id.replace("-", "").strip(),
                query=query,
            )

            search_terms = []
            for row in response:
                clicks = row.metrics.clicks
                impressions = row.metrics.impressions
                cost = micros_to_currency(row.metrics.cost_micros)
                conversions = row.metrics.conversions
                conv_value = row.metrics.conversions_value

                search_terms.append({
                    "search_term": row.search_term_view.search_term,
                    "status": row.search_term_view.status.name,
                    "matched_keyword": row.segments.keyword.info.text or None,
                    "matched_keyword_match_type": row.segments.keyword.info.match_type.name,
                    "ad_group": {
                        "id": str(row.ad_group.id),
                        "name": row.ad_group.name,
                    },
                    "campaign": {
                        "id": str(row.campaign.id),
                        "name": row.campaign.name,
                    },
                    "metrics": {
                        "impressions": impressions,
                        "clicks": clicks,
                        "cost": cost,
                        "conversions": conversions,
                        "conversions_value": conv_value,
                        "average_cpc": micros_to_currency(row.metrics.average_cpc),
                        **derived_metrics(impressions, clicks, cost, conversions, conv_value),
                    },
                })

            return {
                "success": True,
                "search_terms": search_terms,
                "count": len(search_terms),
                "filters_applied": {
                    "date_range": date_label,
                    "campaign_id": campaign_id_clean,
                    "ad_group_id": ad_group_id_clean,
                    "min_impressions": min_impressions,
                    "limit": limit,
                    "only_zero_conversions": only_zero_conversions,
                },
            }

        except GoogleAdsException as e:
            logger.error(f"Failed to list search terms: {e}")
            return self.error_handler.format_error_response(e)
        except Exception as e:
            logger.error(f"Unexpected error listing search terms: {e}")
            raise