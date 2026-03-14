-- 新規追加されたモデル（古い日付にないモデル）
SELECT 
    new.provider,
    new.model,
    new.input_cost_per_1k_tokens as input_cost,
    new.output_cost_per_1k_tokens as output_cost,
    (new.input_cost_per_1k_tokens + new.output_cost_per_1k_tokens) as total_cost,
    new.notes
FROM model_costs new
WHERE new.date_updated = (SELECT MAX(date_updated) FROM model_costs)
  AND NOT EXISTS (
    SELECT 1 
    FROM model_costs old 
    WHERE old.provider = new.provider 
      AND old.model = new.model 
      AND old.date_updated < new.date_updated
  )
ORDER BY new.provider, new.model;

