-- 価格変更があったモデル（2つの日付を比較）
-- 注意: date_updated の値を実際のデータに合わせて変更してください
SELECT 
    old.provider,
    old.model,
    old.date_updated as old_date,
    (old.input_cost_per_1k_tokens + old.output_cost_per_1k_tokens) as old_total_cost,
    new.date_updated as new_date,
    (new.input_cost_per_1k_tokens + new.output_cost_per_1k_tokens) as new_total_cost,
    ROUND((new.input_cost_per_1k_tokens + new.output_cost_per_1k_tokens) - 
          (old.input_cost_per_1k_tokens + old.output_cost_per_1k_tokens), 6) as cost_change,
    ROUND(((new.input_cost_per_1k_tokens + new.output_cost_per_1k_tokens) - 
           (old.input_cost_per_1k_tokens + old.output_cost_per_1k_tokens)) / 
          NULLIF((old.input_cost_per_1k_tokens + old.output_cost_per_1k_tokens), 0) * 100, 2) as change_percent
FROM model_costs old
JOIN model_costs new 
    ON old.provider = new.provider 
    AND old.model = new.model
WHERE old.date_updated = '2025-08-14'
  AND new.date_updated = '2025-11-27'
  AND (old.input_cost_per_1k_tokens != new.input_cost_per_1k_tokens 
       OR old.output_cost_per_1k_tokens != new.output_cost_per_1k_tokens)
ORDER BY cost_change DESC;

