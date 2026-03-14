-- プロバイダー別の統計（最新データ）
SELECT 
    provider,
    COUNT(*) as model_count,
    ROUND(AVG(input_cost_per_1k_tokens), 6) as avg_input_cost,
    ROUND(AVG(output_cost_per_1k_tokens), 6) as avg_output_cost,
    ROUND(AVG(input_cost_per_1k_tokens + output_cost_per_1k_tokens), 6) as avg_total_cost,
    ROUND(MIN(input_cost_per_1k_tokens + output_cost_per_1k_tokens), 6) as min_total_cost,
    ROUND(MAX(input_cost_per_1k_tokens + output_cost_per_1k_tokens), 6) as max_total_cost
FROM model_costs
WHERE date_updated = (SELECT MAX(date_updated) FROM model_costs)
GROUP BY provider
ORDER BY avg_total_cost;

