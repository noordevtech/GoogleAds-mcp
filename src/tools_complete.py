"""Complete tools implementation combining all modules."""

import asyncio
from typing import Any, Dict, List, Optional
import base64
import structlog

from mcp.types import Tool
from google.ads.googleads.errors import GoogleAdsException
from google.protobuf import field_mask_pb2

from .auth import GoogleAdsAuthManager
from .error_handler import ErrorHandler
from .tools_campaigns import CampaignTools
from .tools_reporting import ReportingTools
from .utils import currency_to_micros, micros_to_currency

logger = structlog.get_logger(__name__)


class GoogleAdsTools:
    """Complete implementation of all Google Ads API v20 tools."""
    
    def __init__(self, auth_manager: GoogleAdsAuthManager, error_handler: ErrorHandler):
        self.auth_manager = auth_manager
        self.error_handler = error_handler
        
        # Initialize tool modules
        self.campaign_tools = CampaignTools(auth_manager, error_handler)
        self.reporting_tools = ReportingTools(auth_manager, error_handler)
        
        self._tools_registry = self._register_all_tools()
        
    def _register_all_tools(self) -> Dict[str, Dict[str, Any]]:
        """Register all available tools from all modules."""
        tools = {}
        
        # Account Management
        tools.update(self._register_account_tools())
        
        # Campaign Management (from CampaignTools)
        tools.update(self._register_campaign_tools())
        
        # Ad Group Management
        tools.update(self._register_ad_group_tools())
        
        # Ad Management
        tools.update(self._register_ad_tools())
        
        # Asset Management
        tools.update(self._register_asset_tools())
        
        # Budget Management
        tools.update(self._register_budget_tools())
        
        # Keyword Management
        tools.update(self._register_keyword_tools())
        
        # Reporting & Analytics (from ReportingTools)
        tools.update(self._register_reporting_tools())
        
        # Advanced Features
        tools.update(self._register_advanced_tools())
        
        return tools
        
    def _register_account_tools(self) -> Dict[str, Dict[str, Any]]:
        """Register account management tools."""
        return {
            "list_accounts": {
                "description": "List all accessible Google Ads accounts",
                "handler": self.list_accounts,
                "parameters": {},
            },
            "get_account_info": {
                "description": "Get detailed information about a specific account",
                "handler": self.get_account_info,
                "parameters": {
                    "customer_id": {"type": "string", "required": True},
                },
            },
            "get_account_hierarchy": {
                "description": "Get the account hierarchy tree",
                "handler": self.get_account_hierarchy,
                "parameters": {
                    "customer_id": {"type": "string", "required": True},
                },
            },
        }
        
    def _register_campaign_tools(self) -> Dict[str, Dict[str, Any]]:
        """Register campaign management tools."""
        return {
            "create_campaign": {
                "description": "Create a new campaign with budget and settings",
                "handler": self.campaign_tools.create_campaign,
                "parameters": {
                    "customer_id": {"type": "string", "required": True},
                    "name": {"type": "string", "required": True},
                    "budget_amount": {"type": "number", "required": True},
                    "campaign_type": {"type": "string", "default": "SEARCH"},
                    "bidding_strategy": {"type": "string", "default": "MAXIMIZE_CLICKS"},
                    "start_date": {"type": "string"},
                    "end_date": {"type": "string"},
                    "target_locations": {"type": "array"},
                    "target_languages": {"type": "array"},
                },
            },
            "update_campaign": {
                "description": "Update campaign settings",
                "handler": self.campaign_tools.update_campaign,
                "parameters": {
                    "customer_id": {"type": "string", "required": True},
                    "campaign_id": {"type": "string", "required": True},
                    "name": {"type": "string"},
                    "status": {"type": "string"},
                    "start_date": {"type": "string"},
                    "end_date": {"type": "string"},
                },
            },
            "pause_campaign": {
                "description": "Pause a running campaign",
                "handler": self.campaign_tools.pause_campaign,
                "parameters": {
                    "customer_id": {"type": "string", "required": True},
                    "campaign_id": {"type": "string", "required": True},
                },
            },
            "resume_campaign": {
                "description": "Resume a paused campaign",
                "handler": self.campaign_tools.resume_campaign,
                "parameters": {
                    "customer_id": {"type": "string", "required": True},
                    "campaign_id": {"type": "string", "required": True},
                },
            },
            "list_campaigns": {
                "description": "List all campaigns with optional filters",
                "handler": self.campaign_tools.list_campaigns,
                "parameters": {
                    "customer_id": {"type": "string", "required": True},
                    "status": {"type": "string"},
                    "campaign_type": {"type": "string"},
                },
            },
            "get_campaign": {
                "description": "Get detailed campaign information",
                "handler": self.campaign_tools.get_campaign,
                "parameters": {
                    "customer_id": {"type": "string", "required": True},
                    "campaign_id": {"type": "string", "required": True},
                },
            },
        }
        
    def _register_ad_group_tools(self) -> Dict[str, Dict[str, Any]]:
        """Register ad group management tools."""
        return {
            "create_ad_group": {
                "description": "Create a new ad group in a campaign",
                "handler": self.create_ad_group,
                "parameters": {
                    "customer_id": {"type": "string", "required": True},
                    "campaign_id": {"type": "string", "required": True},
                    "name": {"type": "string", "required": True},
                    "cpc_bid_micros": {"type": "number"},
                },
            },
            "update_ad_group": {
                "description": "Update ad group settings",
                "handler": self.update_ad_group,
                "parameters": {
                    "customer_id": {"type": "string", "required": True},
                    "ad_group_id": {"type": "string", "required": True},
                    "name": {"type": "string"},
                    "status": {"type": "string"},
                    "cpc_bid_micros": {"type": "number"},
                },
            },
            "list_ad_groups": {
                "description": "List ad groups with filters",
                "handler": self.list_ad_groups,
                "parameters": {
                    "customer_id": {"type": "string", "required": True},
                    "campaign_id": {"type": "string"},
                    "status": {"type": "string"},
                },
            },
        }
        
    def _register_ad_tools(self) -> Dict[str, Dict[str, Any]]:
        """Register ad management tools."""
        return {
            "create_responsive_search_ad": {
                "description": "Create a responsive search ad",
                "handler": self.create_responsive_search_ad,
                "parameters": {
                    "customer_id": {"type": "string", "required": True},
                    "ad_group_id": {"type": "string", "required": True},
                    "headlines": {"type": "array", "required": True},
                    "descriptions": {"type": "array", "required": True},
                    "final_urls": {"type": "array", "required": True},
                    "path1": {"type": "string"},
                    "path2": {"type": "string"},
                },
            },
            "create_expanded_text_ad": {
                "description": "Create an expanded text ad",
                "handler": self.create_expanded_text_ad,
                "parameters": {
                    "customer_id": {"type": "string", "required": True},
                    "ad_group_id": {"type": "string", "required": True},
                    "headline1": {"type": "string", "required": True},
                    "headline2": {"type": "string", "required": True},
                    "headline3": {"type": "string"},
                    "description1": {"type": "string", "required": True},
                    "description2": {"type": "string"},
                    "final_urls": {"type": "array", "required": True},
                },
            },
            "list_ads": {
                "description": "List ads with filters",
                "handler": self.list_ads,
                "parameters": {
                    "customer_id": {"type": "string", "required": True},
                    "ad_group_id": {"type": "string"},
                    "campaign_id": {"type": "string"},
                    "status": {"type": "string"},
                },
            },
        }
        
    def _register_asset_tools(self) -> Dict[str, Dict[str, Any]]:
        """Register asset management tools."""
        return {
            "upload_image_asset": {
                "description": "Upload an image asset",
                "handler": self.upload_image_asset,
                "parameters": {
                    "customer_id": {"type": "string", "required": True},
                    "image_data": {"type": "string", "required": True},
                    "name": {"type": "string", "required": True},
                },
            },
            "upload_text_asset": {
                "description": "Create a text asset",
                "handler": self.upload_text_asset,
                "parameters": {
                    "customer_id": {"type": "string", "required": True},
                    "text": {"type": "string", "required": True},
                    "name": {"type": "string", "required": True},
                },
            },
            "list_assets": {
                "description": (
                    "List assets with their content (text/phone/url/sitelink/etc.) "
                    "and any account-level or campaign-level linkages."
                ),
                "handler": self.list_assets,
                "parameters": {
                    "customer_id": {"type": "string", "required": True},
                    "asset_type": {"type": "string"},
                },
            },
            "create_call_asset": {
                "description": (
                    "Create a call (phone-number) asset extension. Use "
                    "link_asset_to_account or link_asset_to_campaign with "
                    "field_type='CALL' to attach it."
                ),
                "handler": self.create_call_asset,
                "parameters": {
                    "customer_id": {"type": "string", "required": True},
                    "phone_number": {"type": "string", "required": True},
                    "country_code": {"type": "string", "default": "CA"},
                    "call_conversion_reporting_state": {
                        "type": "string",
                        "default": "USE_ACCOUNT_LEVEL_CALL_CONVERSION_ACTION",
                    },
                    "name": {"type": "string"},
                },
            },
            "create_location_asset": {
                "description": (
                    "Create a location asset linked to a Google Business "
                    "Profile. Requires the customer to have a GBP linked."
                ),
                "handler": self.create_location_asset,
                "parameters": {
                    "customer_id": {"type": "string", "required": True},
                    "business_profile_locations": {"type": "array"},
                    "sync_level": {"type": "string", "default": "ACCOUNT"},
                },
            },
            "create_sitelink_asset": {
                "description": (
                    "Create a sitelink asset (clickable subpage link). "
                    "link_text max 25 chars; description1/2 max 35 chars each."
                ),
                "handler": self.create_sitelink_asset,
                "parameters": {
                    "customer_id": {"type": "string", "required": True},
                    "link_text": {"type": "string", "required": True},
                    "final_urls": {"type": "array", "required": True},
                    "description1": {"type": "string"},
                    "description2": {"type": "string"},
                },
            },
            "create_callout_asset": {
                "description": (
                    "Create a callout asset (non-clickable trust signal). "
                    "Max 25 characters. Recommend creating 6-10 per account."
                ),
                "handler": self.create_callout_asset,
                "parameters": {
                    "customer_id": {"type": "string", "required": True},
                    "callout_text": {"type": "string", "required": True},
                },
            },
            "create_structured_snippet_asset": {
                "description": (
                    "Create a structured snippet asset (categorized list). "
                    "Header must come from Google's approved list (Services, "
                    "Brands, Insurance coverage, etc.). 3-10 values, each "
                    "max 25 chars."
                ),
                "handler": self.create_structured_snippet_asset,
                "parameters": {
                    "customer_id": {"type": "string", "required": True},
                    "header": {"type": "string", "required": True},
                    "values": {"type": "array", "required": True},
                },
            },
            "link_asset_to_campaign": {
                "description": (
                    "Attach an existing asset to a campaign with a field_type "
                    "(CALL, SITELINK, CALLOUT, STRUCTURED_SNIPPET, LOCATION, ...)."
                ),
                "handler": self.link_asset_to_campaign,
                "parameters": {
                    "customer_id": {"type": "string", "required": True},
                    "campaign_id": {"type": "string", "required": True},
                    "asset_resource_name": {"type": "string", "required": True},
                    "field_type": {"type": "string", "required": True},
                },
            },
            "unlink_asset_from_campaign": {
                "description": "Detach a campaign-level asset link by its CampaignAsset resource name.",
                "handler": self.unlink_asset_from_campaign,
                "parameters": {
                    "customer_id": {"type": "string", "required": True},
                    "campaign_asset_resource_name": {"type": "string", "required": True},
                },
            },
            "link_asset_to_account": {
                "description": (
                    "Attach an existing asset at the account level "
                    "(applies to all current and future campaigns). "
                    "Typically the right choice for call/location/sitelink/callout."
                ),
                "handler": self.link_asset_to_account,
                "parameters": {
                    "customer_id": {"type": "string", "required": True},
                    "asset_resource_name": {"type": "string", "required": True},
                    "field_type": {"type": "string", "required": True},
                },
            },
            "unlink_asset_from_account": {
                "description": "Detach an account-level asset link by its CustomerAsset resource name.",
                "handler": self.unlink_asset_from_account,
                "parameters": {
                    "customer_id": {"type": "string", "required": True},
                    "customer_asset_resource_name": {"type": "string", "required": True},
                },
            },
        }
        
    def _register_budget_tools(self) -> Dict[str, Dict[str, Any]]:
        """Register budget management tools."""
        return {
            "create_budget": {
                "description": "Create a shared campaign budget",
                "handler": self.create_budget,
                "parameters": {
                    "customer_id": {"type": "string", "required": True},
                    "name": {"type": "string", "required": True},
                    "amount_micros": {"type": "number", "required": True},
                    "delivery_method": {"type": "string", "default": "STANDARD"},
                },
            },
            "update_budget": {
                "description": "Update budget amount or settings",
                "handler": self.update_budget,
                "parameters": {
                    "customer_id": {"type": "string", "required": True},
                    "budget_id": {"type": "string", "required": True},
                    "amount_micros": {"type": "number"},
                    "name": {"type": "string"},
                },
            },
            "list_budgets": {
                "description": "List all budgets",
                "handler": self.list_budgets,
                "parameters": {
                    "customer_id": {"type": "string", "required": True},
                },
            },
        }
        
    def _register_keyword_tools(self) -> Dict[str, Dict[str, Any]]:
        """Register keyword management tools."""
        return {
            "add_keywords": {
                "description": "Add keywords to an ad group",
                "handler": self.add_keywords,
                "parameters": {
                    "customer_id": {"type": "string", "required": True},
                    "ad_group_id": {"type": "string", "required": True},
                    "keywords": {"type": "array", "required": True},
                },
            },
            "add_negative_keywords": {
                "description": "Add negative keywords (campaign or ad group level)",
                "handler": self.add_negative_keywords,
                "parameters": {
                    "customer_id": {"type": "string", "required": True},
                    "keywords": {"type": "array", "required": True},
                    "campaign_id": {"type": "string"},
                    "ad_group_id": {"type": "string"},
                },
            },
            "list_keywords": {
                "description": "List keywords with performance data",
                "handler": self.list_keywords,
                "parameters": {
                    "customer_id": {"type": "string", "required": True},
                    "ad_group_id": {"type": "string"},
                    "campaign_id": {"type": "string"},
                },
            },
        }
        
    def _register_reporting_tools(self) -> Dict[str, Dict[str, Any]]:
        """Register reporting and analytics tools."""
        return {
            "get_campaign_performance": {
                "description": "Get campaign performance metrics",
                "handler": self.reporting_tools.get_campaign_performance,
                "parameters": {
                    "customer_id": {"type": "string", "required": True},
                    "campaign_id": {"type": "string"},
                    "date_range": {"type": "string", "default": "LAST_30_DAYS"},
                    "metrics": {"type": "array"},
                },
            },
            "get_ad_group_performance": {
                "description": "Get ad group performance metrics",
                "handler": self.reporting_tools.get_ad_group_performance,
                "parameters": {
                    "customer_id": {"type": "string", "required": True},
                    "ad_group_id": {"type": "string"},
                    "date_range": {"type": "string", "default": "LAST_30_DAYS"},
                },
            },
            "get_keyword_performance": {
                "description": "Get keyword performance metrics",
                "handler": self.reporting_tools.get_keyword_performance,
                "parameters": {
                    "customer_id": {"type": "string", "required": True},
                    "ad_group_id": {"type": "string"},
                    "date_range": {"type": "string", "default": "LAST_30_DAYS"},
                },
            },
            "run_gaql_query": {
                "description": "Run custom GAQL queries",
                "handler": self.reporting_tools.run_gaql_query,
                "parameters": {
                    "customer_id": {"type": "string", "required": True},
                    "query": {"type": "string", "required": True},
                },
            },
            "get_search_terms_report": {
                "description": "Get search terms report",
                "handler": self.reporting_tools.get_search_terms_report,
                "parameters": {
                    "customer_id": {"type": "string", "required": True},
                    "campaign_id": {"type": "string"},
                    "ad_group_id": {"type": "string"},
                    "date_range": {"type": "string", "default": "LAST_7_DAYS"},
                },
            },
            "list_search_terms": {
                "description": (
                    "List actual user search queries that triggered ads, with "
                    "the matched keyword and full performance metrics. The "
                    "primary tool for finding wasted ad spend during an audit "
                    "- use it early. Set only_zero_conversions=True to focus "
                    "on terms that cost money but didn't convert (negative "
                    "keyword candidates)."
                ),
                "handler": self.reporting_tools.list_search_terms,
                "parameters": {
                    "customer_id": {"type": "string", "required": True},
                    "campaign_id": {"type": "string"},
                    "ad_group_id": {"type": "string"},
                    "date_range": {"type": "string", "default": "LAST_30_DAYS"},
                    "min_impressions": {"type": "integer", "default": 1},
                    "limit": {"type": "integer", "default": 200},
                    "only_zero_conversions": {"type": "boolean", "default": False},
                },
            },
        }
        
    def _register_advanced_tools(self) -> Dict[str, Dict[str, Any]]:
        """Register advanced feature tools."""
        return {
            "get_recommendations": {
                "description": "Get optimization recommendations",
                "handler": self.get_recommendations,
                "parameters": {
                    "customer_id": {"type": "string", "required": True},
                },
            },
            "apply_recommendation": {
                "description": "Apply a specific recommendation",
                "handler": self.apply_recommendation,
                "parameters": {
                    "customer_id": {"type": "string", "required": True},
                    "recommendation_id": {"type": "string", "required": True},
                },
            },
            "get_change_history": {
                "description": "Get account change history",
                "handler": self.get_change_history,
                "parameters": {
                    "customer_id": {"type": "string", "required": True},
                    "date_range": {"type": "string", "default": "LAST_7_DAYS"},
                },
            },
        }
        
    def get_all_tools(self) -> List[Tool]:
        """Get all tools in MCP format."""
        tools = []
        for name, config in self._tools_registry.items():
            params = config["parameters"]
            properties = {
                key: {k: v for k, v in spec.items() if k != "required"}
                for key, spec in params.items()
            }
            tool = Tool(
                name=name,
                description=config["description"],
                inputSchema={
                    "type": "object",
                    "properties": properties,
                    "required": [k for k, v in params.items() if v.get("required", False)],
                },
            )
            tools.append(tool)
        return tools
        
    async def execute_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        """Execute a tool by name."""
        if name not in self._tools_registry:
            raise ValueError(f"Unknown tool: {name}")
            
        tool_config = self._tools_registry[name]
        handler = tool_config["handler"]
        
        # Validate required parameters
        for param, config in tool_config["parameters"].items():
            if config.get("required", False) and param not in arguments:
                raise ValueError(f"Missing required parameter: {param}")
                
        # Execute the handler
        return await handler(**arguments)
        
    # ------------------------------------------------------------------
    # Account management
    # ------------------------------------------------------------------

    async def list_accounts(self) -> Dict[str, Any]:
        """List all accessible Google Ads accounts."""
        try:
            customers = self.auth_manager.get_accessible_customers()
            return {
                "success": True,
                "accounts": customers,
                "count": len(customers),
            }
        except Exception as e:
            logger.error(f"Failed to list accounts: {e}")
            raise

    async def get_account_info(self, customer_id: str) -> Dict[str, Any]:
        """Get detailed account information."""
        try:
            client = self.auth_manager.get_client(customer_id)
            googleads_service = client.get_service("GoogleAdsService")

            query = """
                SELECT
                    customer.id,
                    customer.descriptive_name,
                    customer.currency_code,
                    customer.time_zone,
                    customer.auto_tagging_enabled,
                    customer.manager,
                    customer.test_account,
                    customer.optimization_score,
                    customer.optimization_score_weight
                FROM customer
                LIMIT 1
            """

            response = googleads_service.search(
                customer_id=customer_id,
                query=query,
            )

            for row in response:
                return {
                    "success": True,
                    "account": {
                        "id": str(row.customer.id),
                        "name": row.customer.descriptive_name,
                        "currency_code": row.customer.currency_code,
                        "time_zone": row.customer.time_zone,
                        "auto_tagging_enabled": row.customer.auto_tagging_enabled,
                        "is_manager": row.customer.manager,
                        "is_test_account": row.customer.test_account,
                        "optimization_score": row.customer.optimization_score,
                        "optimization_score_weight": row.customer.optimization_score_weight,
                    },
                }

            return {"success": False, "error": "Account not found"}

        except GoogleAdsException as e:
            logger.error(f"Failed to get account info: {e}")
            return self.error_handler.format_error_response(e)
        except Exception as e:
            logger.error(f"Failed to get account info: {e}")
            raise

    async def get_account_hierarchy(self, customer_id: str) -> Dict[str, Any]:
        """Get the account hierarchy tree."""
        try:
            client = self.auth_manager.get_client(customer_id)
            googleads_service = client.get_service("GoogleAdsService")

            query = """
                SELECT
                    customer_client.id,
                    customer_client.descriptive_name,
                    customer_client.manager,
                    customer_client.level,
                    customer_client.time_zone,
                    customer_client.currency_code
                FROM customer_client
                WHERE customer_client.level <= 2
            """

            response = googleads_service.search(
                customer_id=customer_id,
                query=query,
            )

            hierarchy = []
            for row in response:
                hierarchy.append({
                    "id": str(row.customer_client.id),
                    "name": row.customer_client.descriptive_name,
                    "is_manager": row.customer_client.manager,
                    "level": row.customer_client.level,
                    "time_zone": row.customer_client.time_zone,
                    "currency_code": row.customer_client.currency_code,
                })

            return {
                "success": True,
                "hierarchy": hierarchy,
                "count": len(hierarchy),
            }

        except GoogleAdsException as e:
            logger.error(f"Failed to get account hierarchy: {e}")
            return self.error_handler.format_error_response(e)
        except Exception as e:
            logger.error(f"Failed to get account hierarchy: {e}")
            raise

    # ------------------------------------------------------------------
    # Ad group management
    # ------------------------------------------------------------------

    async def create_ad_group(
        self,
        customer_id: str,
        campaign_id: str,
        name: str,
        cpc_bid_micros: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Create a new ad group in a campaign."""
        try:
            client = self.auth_manager.get_client(customer_id)
            ad_group_service = client.get_service("AdGroupService")

            operation = client.get_type("AdGroupOperation")
            ad_group = operation.create
            ad_group.name = name
            ad_group.campaign = f"customers/{customer_id}/campaigns/{campaign_id}"
            ad_group.type_ = client.enums.AdGroupTypeEnum.SEARCH_STANDARD
            ad_group.status = client.enums.AdGroupStatusEnum.ENABLED
            if cpc_bid_micros is not None:
                ad_group.cpc_bid_micros = int(cpc_bid_micros)

            response = ad_group_service.mutate_ad_groups(
                customer_id=customer_id,
                operations=[operation],
            )

            resource_name = response.results[0].resource_name
            return {
                "success": True,
                "ad_group_id": resource_name.split("/")[-1],
                "ad_group_resource_name": resource_name,
                "message": f"Ad group '{name}' created successfully",
            }

        except GoogleAdsException as e:
            logger.error(f"Failed to create ad group: {e}")
            return self.error_handler.format_error_response(e)
        except Exception as e:
            logger.error(f"Unexpected error creating ad group: {e}")
            raise

    async def update_ad_group(
        self,
        customer_id: str,
        ad_group_id: str,
        name: Optional[str] = None,
        status: Optional[str] = None,
        cpc_bid_micros: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Update ad group settings."""
        try:
            client = self.auth_manager.get_client(customer_id)
            ad_group_service = client.get_service("AdGroupService")

            operation = client.get_type("AdGroupOperation")
            ad_group = operation.update
            ad_group.resource_name = (
                f"customers/{customer_id}/adGroups/{ad_group_id}"
            )

            update_mask = []

            if name is not None:
                ad_group.name = name
                update_mask.append("name")

            if status is not None:
                status_enum = client.enums.AdGroupStatusEnum
                status_map = {
                    "ENABLED": status_enum.ENABLED,
                    "PAUSED": status_enum.PAUSED,
                    "REMOVED": status_enum.REMOVED,
                }
                ad_group.status = status_map.get(status.upper(), status_enum.PAUSED)
                update_mask.append("status")

            if cpc_bid_micros is not None:
                ad_group.cpc_bid_micros = int(cpc_bid_micros)
                update_mask.append("cpc_bid_micros")

            operation.update_mask.CopyFrom(
                field_mask_pb2.FieldMask(paths=update_mask)
            )

            ad_group_service.mutate_ad_groups(
                customer_id=customer_id,
                operations=[operation],
            )

            return {
                "success": True,
                "ad_group_id": ad_group_id,
                "updated_fields": update_mask,
                "message": f"Ad group {ad_group_id} updated successfully",
            }

        except GoogleAdsException as e:
            logger.error(f"Failed to update ad group: {e}")
            return self.error_handler.format_error_response(e)
        except Exception as e:
            logger.error(f"Unexpected error updating ad group: {e}")
            raise

    async def list_ad_groups(
        self,
        customer_id: str,
        campaign_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Dict[str, Any]:
        """List ad groups with optional filters."""
        try:
            client = self.auth_manager.get_client(customer_id)
            googleads_service = client.get_service("GoogleAdsService")

            query = """
                SELECT
                    ad_group.id,
                    ad_group.name,
                    ad_group.status,
                    ad_group.type,
                    ad_group.cpc_bid_micros,
                    ad_group.campaign,
                    campaign.id,
                    campaign.name,
                    metrics.clicks,
                    metrics.impressions,
                    metrics.cost_micros,
                    metrics.conversions
                FROM ad_group
                WHERE segments.date DURING LAST_30_DAYS
            """

            conditions = []
            if campaign_id:
                conditions.append(f"campaign.id = {campaign_id}")
            if status:
                conditions.append(f"ad_group.status = '{status.upper()}'")

            if conditions:
                query += " AND " + " AND ".join(conditions)

            query += " ORDER BY ad_group.name"

            response = googleads_service.search(
                customer_id=customer_id,
                query=query,
            )

            ad_groups = []
            for row in response:
                ad_groups.append({
                    "id": str(row.ad_group.id),
                    "name": row.ad_group.name,
                    "status": row.ad_group.status.name,
                    "type": row.ad_group.type_.name,
                    "cpc_bid": micros_to_currency(row.ad_group.cpc_bid_micros),
                    "campaign": {
                        "id": str(row.campaign.id),
                        "name": row.campaign.name,
                    },
                    "metrics": {
                        "clicks": row.metrics.clicks,
                        "impressions": row.metrics.impressions,
                        "cost": micros_to_currency(row.metrics.cost_micros),
                        "conversions": row.metrics.conversions,
                    },
                })

            return {
                "success": True,
                "ad_groups": ad_groups,
                "count": len(ad_groups),
            }

        except GoogleAdsException as e:
            logger.error(f"Failed to list ad groups: {e}")
            return self.error_handler.format_error_response(e)
        except Exception as e:
            logger.error(f"Unexpected error listing ad groups: {e}")
            raise

    # ------------------------------------------------------------------
    # Ad management
    # ------------------------------------------------------------------

    async def create_responsive_search_ad(
        self,
        customer_id: str,
        ad_group_id: str,
        headlines: List[str],
        descriptions: List[str],
        final_urls: List[str],
        path1: Optional[str] = None,
        path2: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a responsive search ad."""
        try:
            client = self.auth_manager.get_client(customer_id)
            ad_group_ad_service = client.get_service("AdGroupAdService")

            operation = client.get_type("AdGroupAdOperation")
            ad_group_ad = operation.create
            ad_group_ad.ad_group = (
                f"customers/{customer_id}/adGroups/{ad_group_id}"
            )
            ad_group_ad.status = client.enums.AdGroupAdStatusEnum.ENABLED

            ad = ad_group_ad.ad
            ad.final_urls.extend(final_urls)

            for headline in headlines:
                asset = client.get_type("AdTextAsset")
                asset.text = headline
                ad.responsive_search_ad.headlines.append(asset)

            for description in descriptions:
                asset = client.get_type("AdTextAsset")
                asset.text = description
                ad.responsive_search_ad.descriptions.append(asset)

            if path1:
                ad.responsive_search_ad.path1 = path1
            if path2:
                ad.responsive_search_ad.path2 = path2

            response = ad_group_ad_service.mutate_ad_group_ads(
                customer_id=customer_id,
                operations=[operation],
            )

            resource_name = response.results[0].resource_name
            return {
                "success": True,
                "ad_resource_name": resource_name,
                "ad_id": resource_name.split("~")[-1],
                "message": "Responsive search ad created successfully",
            }

        except GoogleAdsException as e:
            logger.error(f"Failed to create responsive search ad: {e}")
            return self.error_handler.format_error_response(e)
        except Exception as e:
            logger.error(f"Unexpected error creating responsive search ad: {e}")
            raise

    async def create_expanded_text_ad(
        self,
        customer_id: str,
        ad_group_id: str,
        headline1: str,
        headline2: str,
        description1: str,
        final_urls: List[str],
        headline3: Optional[str] = None,
        description2: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create an expanded text ad.

        Note: Google deprecated Expanded Text Ads in June 2022. Most accounts
        will receive a policy violation when invoking this. Prefer
        create_responsive_search_ad for new ads.
        """
        try:
            client = self.auth_manager.get_client(customer_id)
            ad_group_ad_service = client.get_service("AdGroupAdService")

            operation = client.get_type("AdGroupAdOperation")
            ad_group_ad = operation.create
            ad_group_ad.ad_group = (
                f"customers/{customer_id}/adGroups/{ad_group_id}"
            )
            ad_group_ad.status = client.enums.AdGroupAdStatusEnum.ENABLED

            ad = ad_group_ad.ad
            ad.final_urls.extend(final_urls)
            ad.expanded_text_ad.headline_part1 = headline1
            ad.expanded_text_ad.headline_part2 = headline2
            if headline3:
                ad.expanded_text_ad.headline_part3 = headline3
            ad.expanded_text_ad.description = description1
            if description2:
                ad.expanded_text_ad.description2 = description2

            response = ad_group_ad_service.mutate_ad_group_ads(
                customer_id=customer_id,
                operations=[operation],
            )

            resource_name = response.results[0].resource_name
            return {
                "success": True,
                "ad_resource_name": resource_name,
                "ad_id": resource_name.split("~")[-1],
                "message": "Expanded text ad created successfully",
            }

        except GoogleAdsException as e:
            logger.error(f"Failed to create expanded text ad: {e}")
            return self.error_handler.format_error_response(e)
        except Exception as e:
            logger.error(f"Unexpected error creating expanded text ad: {e}")
            raise

    async def list_ads(
        self,
        customer_id: str,
        ad_group_id: Optional[str] = None,
        campaign_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Dict[str, Any]:
        """List ads with optional filters."""
        try:
            client = self.auth_manager.get_client(customer_id)
            googleads_service = client.get_service("GoogleAdsService")

            query = """
                SELECT
                    ad_group_ad.ad.id,
                    ad_group_ad.ad.type,
                    ad_group_ad.ad.final_urls,
                    ad_group_ad.status,
                    ad_group.id,
                    ad_group.name,
                    campaign.id,
                    campaign.name,
                    metrics.clicks,
                    metrics.impressions,
                    metrics.cost_micros,
                    metrics.conversions
                FROM ad_group_ad
                WHERE segments.date DURING LAST_30_DAYS
            """

            conditions = []
            if ad_group_id:
                conditions.append(f"ad_group.id = {ad_group_id}")
            if campaign_id:
                conditions.append(f"campaign.id = {campaign_id}")
            if status:
                conditions.append(f"ad_group_ad.status = '{status.upper()}'")

            if conditions:
                query += " AND " + " AND ".join(conditions)

            response = googleads_service.search(
                customer_id=customer_id,
                query=query,
            )

            ads = []
            for row in response:
                ads.append({
                    "id": str(row.ad_group_ad.ad.id),
                    "type": row.ad_group_ad.ad.type_.name,
                    "status": row.ad_group_ad.status.name,
                    "final_urls": list(row.ad_group_ad.ad.final_urls),
                    "ad_group": {
                        "id": str(row.ad_group.id),
                        "name": row.ad_group.name,
                    },
                    "campaign": {
                        "id": str(row.campaign.id),
                        "name": row.campaign.name,
                    },
                    "metrics": {
                        "clicks": row.metrics.clicks,
                        "impressions": row.metrics.impressions,
                        "cost": micros_to_currency(row.metrics.cost_micros),
                        "conversions": row.metrics.conversions,
                    },
                })

            return {
                "success": True,
                "ads": ads,
                "count": len(ads),
            }

        except GoogleAdsException as e:
            logger.error(f"Failed to list ads: {e}")
            return self.error_handler.format_error_response(e)
        except Exception as e:
            logger.error(f"Unexpected error listing ads: {e}")
            raise

    # ------------------------------------------------------------------
    # Asset management
    # ------------------------------------------------------------------

    async def upload_image_asset(
        self,
        customer_id: str,
        image_data: str,
        name: str,
    ) -> Dict[str, Any]:
        """Upload an image asset. image_data must be base64-encoded bytes."""
        try:
            client = self.auth_manager.get_client(customer_id)
            asset_service = client.get_service("AssetService")

            operation = client.get_type("AssetOperation")
            asset = operation.create
            asset.name = name
            asset.type_ = client.enums.AssetTypeEnum.IMAGE
            asset.image_asset.data = base64.b64decode(image_data)

            response = asset_service.mutate_assets(
                customer_id=customer_id,
                operations=[operation],
            )

            resource_name = response.results[0].resource_name
            return {
                "success": True,
                "asset_resource_name": resource_name,
                "asset_id": resource_name.split("/")[-1],
                "message": f"Image asset '{name}' uploaded successfully",
            }

        except GoogleAdsException as e:
            logger.error(f"Failed to upload image asset: {e}")
            return self.error_handler.format_error_response(e)
        except Exception as e:
            logger.error(f"Unexpected error uploading image asset: {e}")
            raise

    async def upload_text_asset(
        self,
        customer_id: str,
        text: str,
        name: str,
    ) -> Dict[str, Any]:
        """Create a text asset."""
        try:
            client = self.auth_manager.get_client(customer_id)
            asset_service = client.get_service("AssetService")

            operation = client.get_type("AssetOperation")
            asset = operation.create
            asset.name = name
            asset.type_ = client.enums.AssetTypeEnum.TEXT
            asset.text_asset.text = text

            response = asset_service.mutate_assets(
                customer_id=customer_id,
                operations=[operation],
            )

            resource_name = response.results[0].resource_name
            return {
                "success": True,
                "asset_resource_name": resource_name,
                "asset_id": resource_name.split("/")[-1],
                "message": f"Text asset '{name}' created successfully",
            }

        except GoogleAdsException as e:
            logger.error(f"Failed to create text asset: {e}")
            return self.error_handler.format_error_response(e)
        except Exception as e:
            logger.error(f"Unexpected error creating text asset: {e}")
            raise

    async def list_assets(
        self,
        customer_id: str,
        asset_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """List assets with their content (text/phone/url) and linkages.

        Surfaces both account-level (CustomerAsset) and campaign-level
        (CampaignAsset) attachments so the caller can see at a glance which
        extensions are live and where. Filter by asset_type to narrow results
        (CALL, SITELINK, CALLOUT, STRUCTURED_SNIPPET, LOCATION, IMAGE, TEXT,
        etc.).
        """
        try:
            client = self.auth_manager.get_client(customer_id)
            googleads_service = client.get_service("GoogleAdsService")

            query = """
                SELECT
                    asset.id,
                    asset.name,
                    asset.type,
                    asset.resource_name,
                    asset.text_asset.text,
                    asset.call_asset.phone_number,
                    asset.call_asset.country_code,
                    asset.sitelink_asset.link_text,
                    asset.sitelink_asset.description1,
                    asset.sitelink_asset.description2,
                    asset.callout_asset.callout_text,
                    asset.structured_snippet_asset.header,
                    asset.structured_snippet_asset.values,
                    asset.final_urls
                FROM asset
            """

            if asset_type:
                query += f" WHERE asset.type = '{asset_type.upper()}'"

            response = googleads_service.search(
                customer_id=customer_id.replace("-", "").strip(),
                query=query,
            )

            assets_by_rn: Dict[str, Dict[str, Any]] = {}
            for row in response:
                content: Dict[str, Any] = {}
                a = row.asset
                t = a.type_.name
                if t == "TEXT":
                    content = {"text": a.text_asset.text}
                elif t == "CALL":
                    content = {
                        "phone_number": a.call_asset.phone_number,
                        "country_code": a.call_asset.country_code,
                    }
                elif t == "SITELINK":
                    content = {
                        "link_text": a.sitelink_asset.link_text,
                        "description1": a.sitelink_asset.description1,
                        "description2": a.sitelink_asset.description2,
                        "final_urls": list(a.final_urls),
                    }
                elif t == "CALLOUT":
                    content = {"callout_text": a.callout_asset.callout_text}
                elif t == "STRUCTURED_SNIPPET":
                    content = {
                        "header": a.structured_snippet_asset.header,
                        "values": list(a.structured_snippet_asset.values),
                    }

                assets_by_rn[a.resource_name] = {
                    "id": str(a.id),
                    "name": a.name,
                    "type": t,
                    "resource_name": a.resource_name,
                    "content": content,
                    "linked_to_account": [],
                    "linked_to_campaigns": [],
                }

            # Account-level linkages
            try:
                ca_response = googleads_service.search(
                    customer_id=customer_id.replace("-", "").strip(),
                    query=(
                        "SELECT customer_asset.asset, customer_asset.field_type, "
                        "customer_asset.status FROM customer_asset"
                    ),
                )
                for row in ca_response:
                    rn = row.customer_asset.asset
                    if rn in assets_by_rn:
                        assets_by_rn[rn]["linked_to_account"].append({
                            "field_type": row.customer_asset.field_type.name,
                            "status": row.customer_asset.status.name,
                        })
            except GoogleAdsException as e:
                logger.warning(f"Failed to fetch customer_asset linkages: {e}")

            # Campaign-level linkages
            try:
                cap_response = googleads_service.search(
                    customer_id=customer_id.replace("-", "").strip(),
                    query=(
                        "SELECT campaign_asset.asset, campaign_asset.campaign, "
                        "campaign_asset.field_type, campaign_asset.status, "
                        "campaign.name FROM campaign_asset"
                    ),
                )
                for row in cap_response:
                    rn = row.campaign_asset.asset
                    if rn in assets_by_rn:
                        assets_by_rn[rn]["linked_to_campaigns"].append({
                            "campaign_id": row.campaign_asset.campaign.split("/")[-1],
                            "campaign_name": row.campaign.name,
                            "field_type": row.campaign_asset.field_type.name,
                            "status": row.campaign_asset.status.name,
                        })
            except GoogleAdsException as e:
                logger.warning(f"Failed to fetch campaign_asset linkages: {e}")

            assets = list(assets_by_rn.values())
            return {
                "success": True,
                "assets": assets,
                "count": len(assets),
            }

        except GoogleAdsException as e:
            logger.error(f"Failed to list assets: {e}")
            return self.error_handler.format_error_response(e)
        except Exception as e:
            logger.error(f"Unexpected error listing assets: {e}")
            raise

    # ------------------------------------------------------------------
    # Budget management
    # ------------------------------------------------------------------

    async def create_budget(
        self,
        customer_id: str,
        name: str,
        amount_micros: int,
        delivery_method: str = "STANDARD",
    ) -> Dict[str, Any]:
        """Create a shared campaign budget."""
        try:
            client = self.auth_manager.get_client(customer_id)
            budget_service = client.get_service("CampaignBudgetService")

            operation = client.get_type("CampaignBudgetOperation")
            budget = operation.create
            budget.name = name
            budget.amount_micros = int(amount_micros)
            delivery_enum = client.enums.BudgetDeliveryMethodEnum
            delivery_map = {
                "STANDARD": delivery_enum.STANDARD,
                "ACCELERATED": delivery_enum.ACCELERATED,
            }
            budget.delivery_method = delivery_map.get(
                delivery_method.upper(), delivery_enum.STANDARD
            )

            response = budget_service.mutate_campaign_budgets(
                customer_id=customer_id,
                operations=[operation],
            )

            resource_name = response.results[0].resource_name
            return {
                "success": True,
                "budget_id": resource_name.split("/")[-1],
                "budget_resource_name": resource_name,
                "message": f"Budget '{name}' created successfully",
            }

        except GoogleAdsException as e:
            logger.error(f"Failed to create budget: {e}")
            return self.error_handler.format_error_response(e)
        except Exception as e:
            logger.error(f"Unexpected error creating budget: {e}")
            raise

    async def update_budget(
        self,
        customer_id: str,
        budget_id: str,
        amount_micros: Optional[int] = None,
        name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update a campaign budget."""
        try:
            client = self.auth_manager.get_client(customer_id)
            budget_service = client.get_service("CampaignBudgetService")

            operation = client.get_type("CampaignBudgetOperation")
            budget = operation.update
            budget.resource_name = (
                f"customers/{customer_id}/campaignBudgets/{budget_id}"
            )

            update_mask = []
            if amount_micros is not None:
                budget.amount_micros = int(amount_micros)
                update_mask.append("amount_micros")
            if name is not None:
                budget.name = name
                update_mask.append("name")

            operation.update_mask.CopyFrom(
                field_mask_pb2.FieldMask(paths=update_mask)
            )

            budget_service.mutate_campaign_budgets(
                customer_id=customer_id,
                operations=[operation],
            )

            return {
                "success": True,
                "budget_id": budget_id,
                "updated_fields": update_mask,
                "message": f"Budget {budget_id} updated successfully",
            }

        except GoogleAdsException as e:
            logger.error(f"Failed to update budget: {e}")
            return self.error_handler.format_error_response(e)
        except Exception as e:
            logger.error(f"Unexpected error updating budget: {e}")
            raise

    async def list_budgets(self, customer_id: str) -> Dict[str, Any]:
        """List all campaign budgets in the account."""
        try:
            client = self.auth_manager.get_client(customer_id)
            googleads_service = client.get_service("GoogleAdsService")

            query = """
                SELECT
                    campaign_budget.id,
                    campaign_budget.name,
                    campaign_budget.amount_micros,
                    campaign_budget.delivery_method,
                    campaign_budget.status,
                    campaign_budget.explicitly_shared,
                    campaign_budget.reference_count
                FROM campaign_budget
            """

            response = googleads_service.search(
                customer_id=customer_id,
                query=query,
            )

            budgets = []
            for row in response:
                budgets.append({
                    "id": str(row.campaign_budget.id),
                    "name": row.campaign_budget.name,
                    "amount": micros_to_currency(row.campaign_budget.amount_micros),
                    "amount_micros": row.campaign_budget.amount_micros,
                    "delivery_method": row.campaign_budget.delivery_method.name,
                    "status": row.campaign_budget.status.name,
                    "shared": row.campaign_budget.explicitly_shared,
                    "reference_count": row.campaign_budget.reference_count,
                })

            return {
                "success": True,
                "budgets": budgets,
                "count": len(budgets),
            }

        except GoogleAdsException as e:
            logger.error(f"Failed to list budgets: {e}")
            return self.error_handler.format_error_response(e)
        except Exception as e:
            logger.error(f"Unexpected error listing budgets: {e}")
            raise

    # ------------------------------------------------------------------
    # Keyword management
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_match_type(client, match_type: Optional[str]):
        match_enum = client.enums.KeywordMatchTypeEnum
        match_map = {
            "BROAD": match_enum.BROAD,
            "PHRASE": match_enum.PHRASE,
            "EXACT": match_enum.EXACT,
        }
        return match_map.get((match_type or "BROAD").upper(), match_enum.BROAD)

    async def add_keywords(
        self,
        customer_id: str,
        ad_group_id: str,
        keywords: List[Any],
    ) -> Dict[str, Any]:
        """Add keywords to an ad group.

        Each entry in `keywords` may be a string (treated as broad match) or
        a dict with `text` and optional `match_type` and `cpc_bid_micros`.
        """
        try:
            client = self.auth_manager.get_client(customer_id)
            criterion_service = client.get_service("AdGroupCriterionService")

            operations = []
            for entry in keywords:
                if isinstance(entry, str):
                    text = entry
                    match_type = "BROAD"
                    cpc_bid_micros = None
                else:
                    text = entry["text"]
                    match_type = entry.get("match_type", "BROAD")
                    cpc_bid_micros = entry.get("cpc_bid_micros")

                operation = client.get_type("AdGroupCriterionOperation")
                criterion = operation.create
                criterion.ad_group = (
                    f"customers/{customer_id}/adGroups/{ad_group_id}"
                )
                criterion.status = client.enums.AdGroupCriterionStatusEnum.ENABLED
                criterion.keyword.text = text
                criterion.keyword.match_type = self._resolve_match_type(client, match_type)
                if cpc_bid_micros is not None:
                    criterion.cpc_bid_micros = int(cpc_bid_micros)
                operations.append(operation)

            response = criterion_service.mutate_ad_group_criteria(
                customer_id=customer_id,
                operations=operations,
            )

            return {
                "success": True,
                "added": [r.resource_name for r in response.results],
                "count": len(response.results),
                "message": f"Added {len(response.results)} keyword(s) to ad group {ad_group_id}",
            }

        except GoogleAdsException as e:
            logger.error(f"Failed to add keywords: {e}")
            return self.error_handler.format_error_response(e)
        except Exception as e:
            logger.error(f"Unexpected error adding keywords: {e}")
            raise

    async def add_negative_keywords(
        self,
        customer_id: str,
        keywords: List[Any],
        campaign_id: Optional[str] = None,
        ad_group_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Add negative keywords at the campaign or ad-group level."""
        if not (campaign_id or ad_group_id):
            return {
                "success": False,
                "error": "Either campaign_id or ad_group_id is required",
            }

        try:
            client = self.auth_manager.get_client(customer_id)

            normalized = []
            for entry in keywords:
                if isinstance(entry, str):
                    normalized.append({"text": entry, "match_type": "BROAD"})
                else:
                    normalized.append({
                        "text": entry["text"],
                        "match_type": entry.get("match_type", "BROAD"),
                    })

            if ad_group_id:
                criterion_service = client.get_service("AdGroupCriterionService")
                operations = []
                for entry in normalized:
                    operation = client.get_type("AdGroupCriterionOperation")
                    criterion = operation.create
                    criterion.ad_group = (
                        f"customers/{customer_id}/adGroups/{ad_group_id}"
                    )
                    criterion.negative = True
                    criterion.keyword.text = entry["text"]
                    criterion.keyword.match_type = self._resolve_match_type(
                        client, entry["match_type"]
                    )
                    operations.append(operation)
                response = criterion_service.mutate_ad_group_criteria(
                    customer_id=customer_id,
                    operations=operations,
                )
            else:
                criterion_service = client.get_service("CampaignCriterionService")
                operations = []
                for entry in normalized:
                    operation = client.get_type("CampaignCriterionOperation")
                    criterion = operation.create
                    criterion.campaign = (
                        f"customers/{customer_id}/campaigns/{campaign_id}"
                    )
                    criterion.negative = True
                    criterion.keyword.text = entry["text"]
                    criterion.keyword.match_type = self._resolve_match_type(
                        client, entry["match_type"]
                    )
                    operations.append(operation)
                response = criterion_service.mutate_campaign_criteria(
                    customer_id=customer_id,
                    operations=operations,
                )

            return {
                "success": True,
                "added": [r.resource_name for r in response.results],
                "count": len(response.results),
                "level": "ad_group" if ad_group_id else "campaign",
            }

        except GoogleAdsException as e:
            logger.error(f"Failed to add negative keywords: {e}")
            return self.error_handler.format_error_response(e)
        except Exception as e:
            logger.error(f"Unexpected error adding negative keywords: {e}")
            raise

    async def list_keywords(
        self,
        customer_id: str,
        ad_group_id: Optional[str] = None,
        campaign_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """List keywords with performance data."""
        try:
            client = self.auth_manager.get_client(customer_id)
            googleads_service = client.get_service("GoogleAdsService")

            query = """
                SELECT
                    ad_group_criterion.criterion_id,
                    ad_group_criterion.keyword.text,
                    ad_group_criterion.keyword.match_type,
                    ad_group_criterion.status,
                    ad_group_criterion.negative,
                    ad_group_criterion.cpc_bid_micros,
                    ad_group.id,
                    ad_group.name,
                    campaign.id,
                    campaign.name,
                    metrics.clicks,
                    metrics.impressions,
                    metrics.cost_micros,
                    metrics.conversions,
                    metrics.average_cpc
                FROM keyword_view
                WHERE segments.date DURING LAST_30_DAYS
            """

            conditions = []
            if ad_group_id:
                conditions.append(f"ad_group.id = {ad_group_id}")
            if campaign_id:
                conditions.append(f"campaign.id = {campaign_id}")

            if conditions:
                query += " AND " + " AND ".join(conditions)

            response = googleads_service.search(
                customer_id=customer_id,
                query=query,
            )

            keywords = []
            for row in response:
                keywords.append({
                    "criterion_id": str(row.ad_group_criterion.criterion_id),
                    "text": row.ad_group_criterion.keyword.text,
                    "match_type": row.ad_group_criterion.keyword.match_type.name,
                    "status": row.ad_group_criterion.status.name,
                    "negative": row.ad_group_criterion.negative,
                    "cpc_bid": micros_to_currency(
                        row.ad_group_criterion.cpc_bid_micros
                    ),
                    "ad_group": {
                        "id": str(row.ad_group.id),
                        "name": row.ad_group.name,
                    },
                    "campaign": {
                        "id": str(row.campaign.id),
                        "name": row.campaign.name,
                    },
                    "metrics": {
                        "clicks": row.metrics.clicks,
                        "impressions": row.metrics.impressions,
                        "cost": micros_to_currency(row.metrics.cost_micros),
                        "conversions": row.metrics.conversions,
                        "average_cpc": micros_to_currency(row.metrics.average_cpc),
                    },
                })

            return {
                "success": True,
                "keywords": keywords,
                "count": len(keywords),
            }

        except GoogleAdsException as e:
            logger.error(f"Failed to list keywords: {e}")
            return self.error_handler.format_error_response(e)
        except Exception as e:
            logger.error(f"Unexpected error listing keywords: {e}")
            raise

    # ------------------------------------------------------------------
    # Advanced features
    # ------------------------------------------------------------------

    async def get_recommendations(self, customer_id: str) -> Dict[str, Any]:
        """List active optimization recommendations for the account."""
        try:
            client = self.auth_manager.get_client(customer_id)
            googleads_service = client.get_service("GoogleAdsService")

            query = """
                SELECT
                    recommendation.resource_name,
                    recommendation.type,
                    recommendation.impact.base_metrics.clicks,
                    recommendation.impact.base_metrics.impressions,
                    recommendation.impact.base_metrics.cost_micros,
                    recommendation.impact.potential_metrics.clicks,
                    recommendation.impact.potential_metrics.impressions,
                    recommendation.impact.potential_metrics.cost_micros,
                    recommendation.campaign,
                    recommendation.ad_group
                FROM recommendation
            """

            response = googleads_service.search(
                customer_id=customer_id,
                query=query,
            )

            recommendations = []
            for row in response:
                rec = row.recommendation
                recommendations.append({
                    "resource_name": rec.resource_name,
                    "id": rec.resource_name.split("/")[-1],
                    "type": rec.type_.name,
                    "campaign": rec.campaign,
                    "ad_group": rec.ad_group,
                    "impact": {
                        "base": {
                            "clicks": rec.impact.base_metrics.clicks,
                            "impressions": rec.impact.base_metrics.impressions,
                            "cost": micros_to_currency(rec.impact.base_metrics.cost_micros),
                        },
                        "potential": {
                            "clicks": rec.impact.potential_metrics.clicks,
                            "impressions": rec.impact.potential_metrics.impressions,
                            "cost": micros_to_currency(rec.impact.potential_metrics.cost_micros),
                        },
                    },
                })

            return {
                "success": True,
                "recommendations": recommendations,
                "count": len(recommendations),
            }

        except GoogleAdsException as e:
            logger.error(f"Failed to get recommendations: {e}")
            return self.error_handler.format_error_response(e)
        except Exception as e:
            logger.error(f"Unexpected error getting recommendations: {e}")
            raise

    async def apply_recommendation(
        self,
        customer_id: str,
        recommendation_id: str,
    ) -> Dict[str, Any]:
        """Apply a single recommendation by ID."""
        try:
            client = self.auth_manager.get_client(customer_id)
            recommendation_service = client.get_service("RecommendationService")

            operation = client.get_type("ApplyRecommendationOperation")
            if "/" in recommendation_id:
                operation.resource_name = recommendation_id
            else:
                operation.resource_name = (
                    f"customers/{customer_id}/recommendations/{recommendation_id}"
                )

            response = recommendation_service.apply_recommendation(
                customer_id=customer_id,
                operations=[operation],
            )

            return {
                "success": True,
                "applied": [r.resource_name for r in response.results],
                "message": f"Recommendation {recommendation_id} applied",
            }

        except GoogleAdsException as e:
            logger.error(f"Failed to apply recommendation: {e}")
            return self.error_handler.format_error_response(e)
        except Exception as e:
            logger.error(f"Unexpected error applying recommendation: {e}")
            raise

    async def get_change_history(
        self,
        customer_id: str,
        date_range: str = "LAST_7_DAYS",
    ) -> Dict[str, Any]:
        """Return account change events for the requested date range.

        `date_range` accepts named ranges (LAST_7_DAYS, LAST_14_DAYS,
        LAST_30_DAYS, etc.) or a custom "YYYY-MM-DD,YYYY-MM-DD" string.
        change_event requires an explicit date filter.
        """
        try:
            from .utils import get_date_range_dates

            start_date, end_date = get_date_range_dates(date_range)
            start_str = start_date.strftime("%Y-%m-%d")
            end_str = end_date.strftime("%Y-%m-%d")

            client = self.auth_manager.get_client(customer_id)
            googleads_service = client.get_service("GoogleAdsService")

            query = f"""
                SELECT
                    change_event.resource_name,
                    change_event.change_date_time,
                    change_event.change_resource_type,
                    change_event.client_type,
                    change_event.user_email,
                    change_event.resource_change_operation,
                    change_event.campaign,
                    change_event.ad_group
                FROM change_event
                WHERE change_event.change_date_time >= '{start_str}'
                    AND change_event.change_date_time <= '{end_str} 23:59:59'
                ORDER BY change_event.change_date_time DESC
                LIMIT 1000
            """

            response = googleads_service.search(
                customer_id=customer_id,
                query=query,
            )

            events = []
            for row in response:
                events.append({
                    "resource_name": row.change_event.resource_name,
                    "change_date_time": row.change_event.change_date_time,
                    "resource_type": row.change_event.change_resource_type.name,
                    "client_type": row.change_event.client_type.name,
                    "user_email": row.change_event.user_email,
                    "operation": row.change_event.resource_change_operation.name,
                    "campaign": row.change_event.campaign,
                    "ad_group": row.change_event.ad_group,
                })

            return {
                "success": True,
                "events": events,
                "count": len(events),
                "date_range": {"start": start_str, "end": end_str},
            }

        except GoogleAdsException as e:
            logger.error(f"Failed to get change history: {e}")
            return self.error_handler.format_error_response(e)
        except Exception as e:
            logger.error(f"Unexpected error getting change history: {e}")
            raise

    # ------------------------------------------------------------------
    # Asset extensions (call / location / sitelink / callout / snippet)
    # ------------------------------------------------------------------

    _STRUCTURED_SNIPPET_HEADERS = frozenset({
        "Amenities", "Brands", "Courses", "Degree programs", "Destinations",
        "Featured hotels", "Insurance coverage", "Models", "Neighborhoods",
        "Service catalog", "Services", "Shows", "Styles", "Types",
    })

    _ASSET_FIELD_TYPES = frozenset({
        "CALL", "LOCATION", "SITELINK", "CALLOUT", "STRUCTURED_SNIPPET",
        "PRICE", "PROMOTION", "MOBILE_APP", "BUSINESS_NAME", "BUSINESS_LOGO",
        "AD_IMAGE", "MARKETING_IMAGE", "HEADLINE", "DESCRIPTION", "VIDEO",
        "YOUTUBE_VIDEO", "BOOK_ON_GOOGLE", "LEAD_FORM", "HOTEL_CALLOUT",
        "AD_LANDSCAPE_IMAGE", "AD_PORTRAIT_IMAGE",
    })

    @staticmethod
    def _normalize_phone_e164(phone: str) -> str:
        """Normalize a phone string to E.164 (e.g., +15145550199).

        Accepts inputs with separators or whitespace; preserves a leading +.
        Raises ValueError if the result isn't a valid E.164 number.
        """
        import re
        cleaned = "".join(c for c in str(phone) if c.isdigit() or c == "+")
        if not cleaned.startswith("+"):
            cleaned = "+" + cleaned
        if not re.match(r"^\+[1-9]\d{1,14}$", cleaned):
            raise ValueError(
                f"phone_number must be in E.164 format (e.g., +15145550199), got {phone!r}"
            )
        return cleaned

    @classmethod
    def _validate_asset_field_type(cls, field_type: str) -> str:
        ft = (field_type or "").upper()
        if ft not in cls._ASSET_FIELD_TYPES:
            raise ValueError(
                f"field_type {field_type!r} is not supported. Use one of: "
                f"{sorted(cls._ASSET_FIELD_TYPES)}"
            )
        return ft

    async def create_call_asset(
        self,
        customer_id: str,
        phone_number: str,
        country_code: str = "CA",
        call_conversion_reporting_state: str = "USE_ACCOUNT_LEVEL_CALL_CONVERSION_ACTION",
        name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a call asset (phone-number extension).

        The asset itself is account-level; use link_asset_to_account or
        link_asset_to_campaign with field_type='CALL' to attach it.
        """
        try:
            phone = self._normalize_phone_e164(phone_number)
        except ValueError as e:
            return {"success": False, "error": str(e)}

        try:
            client = self.auth_manager.get_client(customer_id)
            asset_service = client.get_service("AssetService")

            operation = client.get_type("AssetOperation")
            asset = operation.create
            if name:
                asset.name = name
            asset.type_ = client.enums.AssetTypeEnum.CALL
            asset.call_asset.phone_number = phone
            asset.call_asset.country_code = country_code.upper()

            reporting_enum = client.enums.CallConversionReportingStateEnum
            reporting_map = {
                "DISABLED": reporting_enum.DISABLED,
                "USE_ACCOUNT_LEVEL_CALL_CONVERSION_ACTION": reporting_enum.USE_ACCOUNT_LEVEL_CALL_CONVERSION_ACTION,
                "USE_RESOURCE_LEVEL_CALL_CONVERSION_ACTION": reporting_enum.USE_RESOURCE_LEVEL_CALL_CONVERSION_ACTION,
            }
            asset.call_asset.call_conversion_reporting_state = reporting_map.get(
                call_conversion_reporting_state.upper(),
                reporting_enum.USE_ACCOUNT_LEVEL_CALL_CONVERSION_ACTION,
            )

            response = asset_service.mutate_assets(
                customer_id=customer_id.replace("-", "").strip(),
                operations=[operation],
            )

            resource_name = response.results[0].resource_name
            return {
                "success": True,
                "asset_resource_name": resource_name,
                "asset_id": resource_name.split("/")[-1],
                "phone_number": phone,
                "country_code": country_code.upper(),
            }

        except GoogleAdsException as e:
            logger.error(f"Failed to create call asset: {e}")
            return self.error_handler.format_error_response(e)
        except Exception as e:
            logger.error(f"Unexpected error creating call asset: {e}")
            raise

    async def create_location_asset(
        self,
        customer_id: str,
        business_profile_locations: Optional[List[str]] = None,
        sync_level: str = "ACCOUNT",
    ) -> Dict[str, Any]:
        """Create a location asset linked to a Google Business Profile.

        The customer must have a GBP linked under Tools > Linked accounts >
        Google Business Profile in the Google Ads UI. ``business_profile_locations``
        is a list of GBP location resource names; if omitted, all linked
        locations are used.
        """
        try:
            client = self.auth_manager.get_client(customer_id)
            asset_service = client.get_service("AssetService")

            operation = client.get_type("AssetOperation")
            asset = operation.create
            asset.type_ = client.enums.AssetTypeEnum.LOCATION

            if business_profile_locations:
                for rn in business_profile_locations:
                    asset.location_asset.business_profile_locations.append(rn)

            response = asset_service.mutate_assets(
                customer_id=customer_id.replace("-", "").strip(),
                operations=[operation],
            )

            resource_name = response.results[0].resource_name
            return {
                "success": True,
                "asset_resource_name": resource_name,
                "asset_id": resource_name.split("/")[-1],
                "sync_level": sync_level.upper(),
            }

        except GoogleAdsException as e:
            # Detect the common "no GBP linked" failure and produce a clearer
            # remediation message.
            err_text = str(e).lower()
            if "business" in err_text or "place" in err_text or "location" in err_text:
                return {
                    "success": False,
                    "error": (
                        "No Google Business Profile linked. Link via the Google "
                        "Ads UI: Tools > Linked accounts > Google Business Profile."
                    ),
                    "raw_error": self.error_handler.format_error_response(e),
                }
            logger.error(f"Failed to create location asset: {e}")
            return self.error_handler.format_error_response(e)
        except Exception as e:
            logger.error(f"Unexpected error creating location asset: {e}")
            raise

    async def create_sitelink_asset(
        self,
        customer_id: str,
        link_text: str,
        final_urls: List[str],
        description1: Optional[str] = None,
        description2: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a sitelink asset (clickable subpage link under the ad)."""
        if not link_text or len(link_text) > 25:
            return {"success": False, "error": "link_text is required and must be 1-25 characters"}
        if not final_urls:
            return {"success": False, "error": "final_urls must contain at least one URL"}
        if description1 and len(description1) > 35:
            return {"success": False, "error": "description1 must be at most 35 characters"}
        if description2 and len(description2) > 35:
            return {"success": False, "error": "description2 must be at most 35 characters"}

        try:
            client = self.auth_manager.get_client(customer_id)
            asset_service = client.get_service("AssetService")

            operation = client.get_type("AssetOperation")
            asset = operation.create
            asset.type_ = client.enums.AssetTypeEnum.SITELINK
            asset.sitelink_asset.link_text = link_text
            if description1:
                asset.sitelink_asset.description1 = description1
            if description2:
                asset.sitelink_asset.description2 = description2
            for url in final_urls:
                asset.final_urls.append(url)

            response = asset_service.mutate_assets(
                customer_id=customer_id.replace("-", "").strip(),
                operations=[operation],
            )

            resource_name = response.results[0].resource_name
            return {
                "success": True,
                "asset_resource_name": resource_name,
                "asset_id": resource_name.split("/")[-1],
                "link_text": link_text,
            }

        except GoogleAdsException as e:
            logger.error(f"Failed to create sitelink asset: {e}")
            return self.error_handler.format_error_response(e)
        except Exception as e:
            logger.error(f"Unexpected error creating sitelink asset: {e}")
            raise

    async def create_callout_asset(
        self,
        customer_id: str,
        callout_text: str,
    ) -> Dict[str, Any]:
        """Create a callout asset (non-clickable trust signal)."""
        if not callout_text or len(callout_text) > 25:
            return {"success": False, "error": "callout_text is required and must be 1-25 characters"}

        try:
            client = self.auth_manager.get_client(customer_id)
            asset_service = client.get_service("AssetService")

            operation = client.get_type("AssetOperation")
            asset = operation.create
            asset.type_ = client.enums.AssetTypeEnum.CALLOUT
            asset.callout_asset.callout_text = callout_text

            response = asset_service.mutate_assets(
                customer_id=customer_id.replace("-", "").strip(),
                operations=[operation],
            )

            resource_name = response.results[0].resource_name
            return {
                "success": True,
                "asset_resource_name": resource_name,
                "asset_id": resource_name.split("/")[-1],
                "callout_text": callout_text,
            }

        except GoogleAdsException as e:
            logger.error(f"Failed to create callout asset: {e}")
            return self.error_handler.format_error_response(e)
        except Exception as e:
            logger.error(f"Unexpected error creating callout asset: {e}")
            raise

    async def create_structured_snippet_asset(
        self,
        customer_id: str,
        header: str,
        values: List[str],
    ) -> Dict[str, Any]:
        """Create a structured snippet asset (categorized value list).

        ``header`` must be one of Google's approved headers (e.g., 'Services',
        'Brands'). ``values`` must contain 3-10 items, each at most 25 chars.
        """
        # Match against approved headers case-insensitively but preserve the
        # canonical capitalization that Google expects.
        canonical = next(
            (h for h in self._STRUCTURED_SNIPPET_HEADERS if h.lower() == (header or "").lower()),
            None,
        )
        if not canonical:
            return {
                "success": False,
                "error": (
                    f"header {header!r} is not a Google-approved header. Use one of: "
                    f"{sorted(self._STRUCTURED_SNIPPET_HEADERS)}"
                ),
            }
        if not values or len(values) < 3 or len(values) > 10:
            return {"success": False, "error": "values must contain 3-10 items"}
        for v in values:
            if not v or len(v) > 25:
                return {
                    "success": False,
                    "error": f"each value must be 1-25 characters; got {v!r}",
                }

        try:
            client = self.auth_manager.get_client(customer_id)
            asset_service = client.get_service("AssetService")

            operation = client.get_type("AssetOperation")
            asset = operation.create
            asset.type_ = client.enums.AssetTypeEnum.STRUCTURED_SNIPPET
            asset.structured_snippet_asset.header = canonical
            for value in values:
                asset.structured_snippet_asset.values.append(value)

            response = asset_service.mutate_assets(
                customer_id=customer_id.replace("-", "").strip(),
                operations=[operation],
            )

            resource_name = response.results[0].resource_name
            return {
                "success": True,
                "asset_resource_name": resource_name,
                "asset_id": resource_name.split("/")[-1],
                "header": canonical,
                "values": list(values),
            }

        except GoogleAdsException as e:
            logger.error(f"Failed to create structured snippet asset: {e}")
            return self.error_handler.format_error_response(e)
        except Exception as e:
            logger.error(f"Unexpected error creating structured snippet asset: {e}")
            raise

    async def link_asset_to_campaign(
        self,
        customer_id: str,
        campaign_id: str,
        asset_resource_name: str,
        field_type: str,
    ) -> Dict[str, Any]:
        """Attach an existing asset to a specific campaign with a field_type."""
        try:
            ft = self._validate_asset_field_type(field_type)
        except ValueError as e:
            return {"success": False, "error": str(e)}

        try:
            client = self.auth_manager.get_client(customer_id)
            campaign_asset_service = client.get_service("CampaignAssetService")

            operation = client.get_type("CampaignAssetOperation")
            link = operation.create
            link.asset = asset_resource_name
            link.campaign = (
                f"customers/{customer_id.replace('-', '').strip()}/campaigns/{campaign_id}"
            )
            link.field_type = getattr(client.enums.AssetFieldTypeEnum, ft)

            response = campaign_asset_service.mutate_campaign_assets(
                customer_id=customer_id.replace("-", "").strip(),
                operations=[operation],
            )

            return {
                "success": True,
                "campaign_asset_resource_name": response.results[0].resource_name,
                "campaign_id": campaign_id,
                "asset_resource_name": asset_resource_name,
                "field_type": ft,
            }

        except GoogleAdsException as e:
            logger.error(f"Failed to link asset to campaign: {e}")
            return self.error_handler.format_error_response(e)
        except Exception as e:
            logger.error(f"Unexpected error linking asset to campaign: {e}")
            raise

    async def unlink_asset_from_campaign(
        self,
        customer_id: str,
        campaign_asset_resource_name: str,
    ) -> Dict[str, Any]:
        """Detach a campaign-level asset link.

        ``campaign_asset_resource_name`` is the resource_name returned by
        link_asset_to_campaign (or surfaced in list_assets under
        linked_to_campaigns).
        """
        try:
            client = self.auth_manager.get_client(customer_id)
            campaign_asset_service = client.get_service("CampaignAssetService")

            operation = client.get_type("CampaignAssetOperation")
            operation.remove = campaign_asset_resource_name

            response = campaign_asset_service.mutate_campaign_assets(
                customer_id=customer_id.replace("-", "").strip(),
                operations=[operation],
            )

            return {
                "success": True,
                "removed": response.results[0].resource_name,
            }

        except GoogleAdsException as e:
            logger.error(f"Failed to unlink campaign asset: {e}")
            return self.error_handler.format_error_response(e)
        except Exception as e:
            logger.error(f"Unexpected error unlinking campaign asset: {e}")
            raise

    async def link_asset_to_account(
        self,
        customer_id: str,
        asset_resource_name: str,
        field_type: str,
    ) -> Dict[str, Any]:
        """Attach an existing asset at the account level (CustomerAsset).

        Account-level assets apply to all current and future campaigns and
        are typically the right choice for call extensions, location
        extensions, sitelinks, and callouts.
        """
        try:
            ft = self._validate_asset_field_type(field_type)
        except ValueError as e:
            return {"success": False, "error": str(e)}

        try:
            client = self.auth_manager.get_client(customer_id)
            customer_asset_service = client.get_service("CustomerAssetService")

            operation = client.get_type("CustomerAssetOperation")
            link = operation.create
            link.asset = asset_resource_name
            link.field_type = getattr(client.enums.AssetFieldTypeEnum, ft)

            response = customer_asset_service.mutate_customer_assets(
                customer_id=customer_id.replace("-", "").strip(),
                operations=[operation],
            )

            return {
                "success": True,
                "customer_asset_resource_name": response.results[0].resource_name,
                "asset_resource_name": asset_resource_name,
                "field_type": ft,
            }

        except GoogleAdsException as e:
            logger.error(f"Failed to link asset to account: {e}")
            return self.error_handler.format_error_response(e)
        except Exception as e:
            logger.error(f"Unexpected error linking asset to account: {e}")
            raise

    async def unlink_asset_from_account(
        self,
        customer_id: str,
        customer_asset_resource_name: str,
    ) -> Dict[str, Any]:
        """Detach an account-level asset link by its CustomerAsset resource name."""
        try:
            client = self.auth_manager.get_client(customer_id)
            customer_asset_service = client.get_service("CustomerAssetService")

            operation = client.get_type("CustomerAssetOperation")
            operation.remove = customer_asset_resource_name

            response = customer_asset_service.mutate_customer_assets(
                customer_id=customer_id.replace("-", "").strip(),
                operations=[operation],
            )

            return {
                "success": True,
                "removed": response.results[0].resource_name,
            }

        except GoogleAdsException as e:
            logger.error(f"Failed to unlink customer asset: {e}")
            return self.error_handler.format_error_response(e)
        except Exception as e:
            logger.error(f"Unexpected error unlinking customer asset: {e}")
            raise