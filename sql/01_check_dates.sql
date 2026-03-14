-- データベース内の日付とモデル数を確認
SELECT 
    date_updated,
    COUNT(*) as model_count,
    COUNT(DISTINCT provider) as provider_count
FROM model_costs 
GROUP BY date_updated 
ORDER BY date_updated;

