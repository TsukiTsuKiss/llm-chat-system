-- 特定モデルの価格履歴
-- 注意: provider と model の値を実際のデータに合わせて変更してください
SELECT 
    date_updated,
    provider,
    model,
    input_cost_per_1k_tokens as input_cost,
    output_cost_per_1k_tokens as output_cost,
    (input_cost_per_1k_tokens + output_cost_per_1k_tokens) as total_cost
FROM model_costs 
WHERE provider = 'OpenAI'
  AND model = 'gpt-4o'
ORDER BY date_updated;

