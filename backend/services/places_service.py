"""
Google Places API Service
Provides address autocomplete and place search functionality for the CRM.
Uses the Google Places API (New) for improved performance and features.
"""

import os
import logging
from typing import Optional, List, Dict, Any
import httpx

logger = logging.getLogger(__name__)


class PlacesService:
    """Google Places API client for address/place search"""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GOOGLE_PLACES_API_KEY")
        self.base_url = "https://places.googleapis.com/v1"
        self.legacy_url = "https://maps.googleapis.com/maps/api/place"

        if not self.api_key:
            logger.warning("GOOGLE_PLACES_API_KEY not configured - Places API disabled")

    @property
    def is_configured(self) -> bool:
        """Check if the service is properly configured"""
        return bool(self.api_key)

    async def autocomplete(
        self,
        input_text: str,
        types: Optional[List[str]] = None,
        location_bias: Optional[Dict[str, float]] = None,
        session_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get address autocomplete suggestions.

        Args:
            input_text: The text to autocomplete
            types: Filter by place types (e.g., ['address', 'establishment'])
            location_bias: Bias results near a location {lat, lng, radius_meters}
            session_token: Session token for billing optimization

        Returns:
            Dict with suggestions list
        """
        if not self.is_configured:
            return {"error": "Places API not configured", "suggestions": []}

        try:
            headers = {
                "Content-Type": "application/json",
                "X-Goog-Api-Key": self.api_key,
                "X-Goog-FieldMask": "suggestions.placePrediction.placeId,suggestions.placePrediction.structuredFormat,suggestions.placePrediction.text"
            }

            payload = {
                "input": input_text,
                "includedRegionCodes": ["us"]
            }

            # Add type filter if specified
            if types:
                payload["includedPrimaryTypes"] = types

            # Add location bias if specified
            if location_bias:
                payload["locationBias"] = {
                    "circle": {
                        "center": {
                            "latitude": location_bias.get("lat"),
                            "longitude": location_bias.get("lng")
                        },
                        "radius": location_bias.get("radius_meters", 50000)
                    }
                }

            # Add session token for billing optimization
            if session_token:
                payload["sessionToken"] = session_token

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self.base_url}/places:autocomplete",
                    headers=headers,
                    json=payload
                )
                response.raise_for_status()
                data = response.json()

                # Transform response to simpler format
                suggestions = []
                for suggestion in data.get("suggestions", []):
                    pred = suggestion.get("placePrediction", {})
                    if pred:
                        suggestions.append({
                            "place_id": pred.get("placeId"),
                            "description": pred.get("text", {}).get("text", ""),
                            "main_text": pred.get("structuredFormat", {}).get("mainText", {}).get("text", ""),
                            "secondary_text": pred.get("structuredFormat", {}).get("secondaryText", {}).get("text", "")
                        })

                return {"suggestions": suggestions}

        except httpx.HTTPStatusError as e:
            logger.error(f"Places API HTTP error: {e.response.status_code} - {e.response.text}")
            return {"error": f"API error: {e.response.status_code}", "suggestions": []}
        except Exception as e:
            logger.error(f"Places autocomplete error: {e}")
            return {"error": str(e), "suggestions": []}

    async def get_place_details(
        self,
        place_id: str,
        fields: Optional[List[str]] = None,
        session_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get detailed information about a place.

        Args:
            place_id: The Google Place ID
            fields: Specific fields to retrieve
            session_token: Session token to link with autocomplete request

        Returns:
            Dict with place details
        """
        if not self.is_configured:
            return {"error": "Places API not configured"}

        try:
            default_fields = [
                "id",
                "displayName",
                "formattedAddress",
                "addressComponents",
                "location",
                "types",
                "internationalPhoneNumber",
                "websiteUri"
            ]

            field_mask = ",".join(fields or default_fields)

            headers = {
                "X-Goog-Api-Key": self.api_key,
                "X-Goog-FieldMask": field_mask
            }

            if session_token:
                headers["X-Goog-SessionToken"] = session_token

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.base_url}/places/{place_id}",
                    headers=headers
                )
                response.raise_for_status()
                data = response.json()

                # Parse address components into structured format
                parsed_address = self._parse_address_components(
                    data.get("addressComponents", [])
                )

                return {
                    "place_id": data.get("id"),
                    "name": data.get("displayName", {}).get("text"),
                    "formatted_address": data.get("formattedAddress"),
                    "address_components": parsed_address,
                    "location": data.get("location"),
                    "types": data.get("types", []),
                    "phone": data.get("internationalPhoneNumber"),
                    "website": data.get("websiteUri"),
                    "raw": data
                }

        except httpx.HTTPStatusError as e:
            logger.error(f"Places API HTTP error: {e.response.status_code} - {e.response.text}")
            return {"error": f"API error: {e.response.status_code}"}
        except Exception as e:
            logger.error(f"Places details error: {e}")
            return {"error": str(e)}

    async def text_search(
        self,
        query: str,
        location: Optional[Dict[str, float]] = None,
        radius_meters: int = 50000,
        types: Optional[List[str]] = None,
        max_results: int = 10
    ) -> Dict[str, Any]:
        """
        Search for places using a text query.

        Args:
            query: The search query
            location: Center point {lat, lng}
            radius_meters: Search radius
            types: Filter by place types
            max_results: Maximum number of results

        Returns:
            Dict with places list
        """
        if not self.is_configured:
            return {"error": "Places API not configured", "places": []}

        try:
            headers = {
                "Content-Type": "application/json",
                "X-Goog-Api-Key": self.api_key,
                "X-Goog-FieldMask": "places.id,places.displayName,places.formattedAddress,places.location,places.types,places.rating,places.businessStatus"
            }

            payload = {
                "textQuery": query,
                "regionCode": "US",
                "maxResultCount": max_results
            }

            if location:
                payload["locationBias"] = {
                    "circle": {
                        "center": {
                            "latitude": location.get("lat"),
                            "longitude": location.get("lng")
                        },
                        "radius": radius_meters
                    }
                }

            if types:
                payload["includedType"] = types[0] if len(types) == 1 else types

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self.base_url}/places:searchText",
                    headers=headers,
                    json=payload
                )
                response.raise_for_status()
                data = response.json()

                places = []
                for place in data.get("places", []):
                    places.append({
                        "place_id": place.get("id"),
                        "name": place.get("displayName", {}).get("text"),
                        "address": place.get("formattedAddress"),
                        "location": place.get("location"),
                        "types": place.get("types", []),
                        "rating": place.get("rating"),
                        "business_status": place.get("businessStatus")
                    })

                return {"places": places}

        except httpx.HTTPStatusError as e:
            logger.error(f"Places API HTTP error: {e.response.status_code} - {e.response.text}")
            return {"error": f"API error: {e.response.status_code}", "places": []}
        except Exception as e:
            logger.error(f"Places text search error: {e}")
            return {"error": str(e), "places": []}

    def _parse_address_components(self, components: List[Dict]) -> Dict[str, str]:
        """Parse Google address components into a structured format"""
        parsed = {
            "street_number": "",
            "street_name": "",
            "street_address": "",
            "city": "",
            "county": "",
            "state": "",
            "state_code": "",
            "zip_code": "",
            "country": "",
            "country_code": ""
        }

        for component in components:
            types = component.get("types", [])
            long_name = component.get("longText", "")
            short_name = component.get("shortText", "")

            if "street_number" in types:
                parsed["street_number"] = long_name
            elif "route" in types:
                parsed["street_name"] = long_name
            elif "locality" in types:
                parsed["city"] = long_name
            elif "administrative_area_level_2" in types:
                parsed["county"] = long_name
            elif "administrative_area_level_1" in types:
                parsed["state"] = long_name
                parsed["state_code"] = short_name
            elif "postal_code" in types:
                parsed["zip_code"] = long_name
            elif "country" in types:
                parsed["country"] = long_name
                parsed["country_code"] = short_name

        # Combine street number and name
        if parsed["street_number"] and parsed["street_name"]:
            parsed["street_address"] = f"{parsed['street_number']} {parsed['street_name']}"
        elif parsed["street_name"]:
            parsed["street_address"] = parsed["street_name"]

        return parsed


# Singleton instance
_places_service: Optional[PlacesService] = None


def get_places_service() -> PlacesService:
    """Get the singleton PlacesService instance"""
    global _places_service
    if _places_service is None:
        _places_service = PlacesService()
    return _places_service
