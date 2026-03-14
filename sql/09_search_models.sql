-- モデル名やプロバイダーで検索（最新データ）
-- 注意: 検索キーワードを変更してください
SELECT 
    provider,
    model,
    input_cost_per_1k_tokens as input_cost,
    output_cost_per_1k_tokens as output_cost,
    (input_cost_per_1k_tokens + output_cost_per_1k_tokens) as total_cost,
    notes
FROM model_costs 
WHERE date_updated = (SELECT MAX(date_updated) FROM model_costs)
  AND (
    provider LIKE '%Groq%'
    OR model LIKE '%llama%'
    OR notes LIKE '%Preview%'
  )
ORDER BY provider, model;

