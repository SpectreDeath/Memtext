    async def analyze_adversarial_capital(
        self, 
        events: List[Dict[str, Any]],
        account_risk: float = 1000.0,
        max_pyramid_levels: int = 5
    ) -> Dict[str, Any]:
        """
        Analyze events for adversarial capital tracking using falling-risk pyramid model.
        
        Args:
            events: List of event dictionaries
            account_risk: Total risk capacity to allocate
            max_pyramid_levels: Maximum levels in the pyramid model
            
        Returns:
            Dictionary containing capital tracking analysis
        """
        logger.info("Running Falling-Risk Pyramid for adversarial capital tracking")
        
        # For capital tracking, we need to interpret events as market/movement data
        # We'll use the event frequency or magnitude as our "price" indicator
        
        if not events:
            return {
                "analysis": "falling-risk-pyramid",
                "status": "no_data",
                "interpretation": "No event data provided for capital tracking analysis"
            }
        
        # Extract a representative "price" series from events
        prices = []
        for event in events:
            # Try to get a numeric value representing event magnitude/score
            price = None
            for key in ["value", "score", "magnitude", "impact", "severity"]:
                if key in event and isinstance(event[key], (int, float)):
                    price = float(event[key])
                    break
            
            if price is None:
                # Use timestamp or a hash-based value
                timestamp = event.get("timestamp", 0)
                if timestamp:
                    price = float(timestamp % 10000) / 100.0  # Normalize
                else:
                    event_id = str(event.get("id", "unknown"))
                    price = float(hash(event_id) % 1000) / 10.0
            
            prices.append(price)
        
        if not prices:
            return {
                "analysis": "falling-risk-pyramid",
                "status": "no_valid_data",
                "interpretation": "Could not extract meaningful numeric data from events"
            }
        
        # Use the average price as our market indicator for simplicity
        avg_price = sum(prices) / len(prices)
        
        # Execute the falling-risk-pyramid skill using direct Python code
        try:
            # Construct the Python code to execute
            python_code = """
# Falling-Risk Pyramid Implementation
def compute_pyramid(entry_price, market_price, account_risk, max_pyramid_levels):
    price_distance = abs(market_price - entry_price)
    if price_distance < 0.001 * entry_price:
        price_distance = 0.001 * entry_price
    
    current_level = min(int(price_distance / (0.005 * entry_price)), max_pyramid_levels - 1)
    
    base_units = account_risk / (0.01 * entry_price)
    
    positions = []
    for level in range(current_level + 1):
        scale_factor = 1.0 + 0.5 * level
        units = int(base_units * scale_factor)
        stop_distance = max_pyramid_levels - level
        risk_per_unit = account_risk / (units * stop_distance) if units > 0 else account_risk
        positions.append({
            "level": level,
            "units": units,
            "entry": entry_price * (1 + 0.005 * level) if market_price > entry_price else entry_price * (1 - 0.005 * level),
            "stop_loss": entry_price * (1 - 0.01 * (max_pyramid_levels - level)) if market_price > entry_price else entry_price * (1 + 0.01 * (max_pyramid_levels - level)),
            "risk_per_unit": risk_per_unit,
            "total_risk": units * risk_per_unit
        })
    
    return {
        "current_level": current_level,
        "positions": positions,
        "total_units": sum(p["units"] for p in positions),
        "remaining_capacity": max_pyramid_levels - current_level,
        "status": "success"
    }

# Main execution
result = compute_pyramid(entry_price, market_price, account_risk, max_pyramid_levels)
result
""".replace("entry_price", str(avg_price * 0.95))\
     .replace("market_price", str(avg_price))\
     .replace("account_risk", str(account_risk))\
     .replace("max_pyramid_levels", str(max_pyramid_levels))
            
            skill_request = SkillExecutionRequest(
                skill_id="technical-analysis/falling-risk-pyramid",  # Still needed for metadata
                input_data={},  # Not used since we're providing code directly
                surface="python",
                code=python_code  # Provide the code directly
            )
            
            result = await self.executor.execute(skill_request)
            
            if result.success and result.output:
                output_value = result.output
                
                if isinstance(output_value, dict):
                    # Extract meaningful metrics for interpretation
                    current_level = output_value.get("current_level", 0)
                    total_units = output_value.get("total_units", 0)
                    remaining_capacity = output_value.get("remaining_capacity", max_pyramid_levels)
                    status = output_value.get("status", "unknown")
                    
                    # Generate interpretation
                    interpretation = self._interpret_pyramid_results(
                        current_level, total_units, remaining_capacity, status
                    )
                    
                    return {
                        "analysis": "falling-risk-pyramid",
                        "current_level": current_level,
                        "total_units": total_units,
                        "remaining_capacity": remaining_capacity,
                        "status": status,
                        "interpretation": interpretation,
                        "data_points": len(prices),
                        "avg_price": avg_price,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                else:
                    # Handle non-dict output
                    return {
                        "analysis": "falling-risk-pyramid",
                        "raw_output": output_value,
                        "status": "completed" if result.success else "failed",
                        "interpretation": "Analysis completed but output format unexpected",
                        "data_points": len(prices),
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
            else:
                logger.error(f"Falling-risk pyramid analysis failed: {result.error}")
                return {
                    "analysis": "falling-risk-pyramid",
                    "status": "error",
                    "error": result.error,
                    "interpretation": "Failed to execute falling-risk pyramid analysis"
                }
                
        except Exception as e:
            logger.exception("Error executing falling-risk-pyramid")
            return {
                "analysis": "falling-risk-pyramid",
                "status": "exception",
                "error": str(e),
                "interpretation": "Exception occurred during falling-risk pyramid analysis"
            }