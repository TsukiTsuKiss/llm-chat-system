-- 最も高いモデル TOP 20（最新データ）
SELECT 
    provider,
    model,
    input_cost_per_1k_tokens as input_cost,
    output_cost_per_1k_tokens as output_cost,
    (input_cost_per_1k_tokens + output_cost_per_1k_tokens) as total_cost,
    notes
FROM model_costs 
WHERE date_updated = (SELECT MAX(date_updated) FROM model_costs)
ORDER BY total_cost DESC, provider, model
LIMIT 20;

