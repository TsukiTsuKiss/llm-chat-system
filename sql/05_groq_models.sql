-- Groqのモデル一覧（最新データ）
SELECT 
    model,
    input_cost_per_1k_tokens as input_cost,
    output_cost_per_1k_tokens as output_cost,
    (input_cost_per_1k_tokens + output_cost_per_1k_tokens) as total_cost,
    notes
FROM model_costs 
WHERE provider = 'Groq'
  AND date_updated = (SELECT MAX(date_updated) FROM model_costs)
ORDER BY total_cost, model;

